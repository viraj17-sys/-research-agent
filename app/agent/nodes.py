import asyncio
import concurrent.futures
import json
import traceback

from pydantic import BaseModel, Field

from app.config import (
    get_planner_llm,
    get_evaluator_llm,
    get_writer_llm,
    get_groq,
    get_settings,
)

from app.state import ResearchState
from app.tools import execute_web_searches


# ============================================================
# TIME BUDGETS
# ============================================================

PLANNER_TIMEOUT = 30
PLANNER_RETRIES = 2
PLANNER_RETRY_DELAY = 3

EVALUATOR_TIMEOUT = 25
EVALUATOR_RETRIES = 2
EVALUATOR_RETRY_DELAY = 3

WRITER_TIMEOUT = 60
WRITER_RETRIES = 2
WRITER_RETRY_DELAY = 2

# Fast-path: skip LLM evaluation if we already have this many sources
FAST_PATH_SOURCE_THRESHOLD = 8


# ============================================================
# DATA MODELS
# ============================================================

class QueryPlan(BaseModel):

    queries: list[str] = Field(
        description=(
            "Two focused web search queries covering "
            "different aspects of the research topic."
        )
    )


class ResearchEvaluation(BaseModel):

    is_sufficient: bool = Field(
        description=(
            "True if the collected evidence is sufficient "
            "for a useful report."
        )
    )

    reason: str = Field(
        description="Short explanation of the decision."
    )

    missing_information: str = Field(
        description="Important missing information, or None."
    )

    follow_up_query: str = Field(
        description=(
            "One focused search query for the largest "
            "information gap."
        )
    )


# ============================================================
# ASYNC BRIDGE HELPERS
# ============================================================

def _run_async_in_isolated_loop(coro_func, *args, **kwargs):
    """
    LangGraph calls our node functions synchronously.
    Run an async coroutine safely without disturbing any outer loop.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro_func(*args, **kwargs))

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            lambda: asyncio.run(coro_func(*args, **kwargs))
        )
        return future.result()


async def _to_thread(fn, *args, **kwargs):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))


async def _invoke_with_timeout(llm, prompt, timeout_s):
    return await asyncio.wait_for(
        _to_thread(llm.invoke, prompt),
        timeout=timeout_s,
    )


def _is_transient_error(err: Exception) -> bool:
    text = str(err).lower()
    return any(
        marker in text
        for marker in (
            "503", "unavailable", "429", "resource_exhausted",
            "timeout", "deadline", "rate limit", "high demand",
            "overloaded", "try again", "connection",
        )
    )


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def build_evidence_context(results, limit=20):

    if not results:
        return "No web evidence available."

    sections = []
    for index, result in enumerate(results[:limit], start=1):
        section = f"""
SOURCE {index}

Search Query:
{result.get("query", "")}

Title:
{result.get("title", "Untitled")}

URL:
{result.get("url", "")}

Content / Snippet:
{result.get("snippet", "")}
"""
        sections.append(section.strip())

    return "\n\n".join(sections)


def extract_text(response) -> str:

    if response is None:
        return ""

    content = getattr(response, "content", response)

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict):
                text = part.get("text", "")
                if text:
                    parts.append(str(text))
            else:
                parts.append(str(part))
        return "\n".join(parts)

    return str(content)


def parse_evaluation_text(text: str) -> ResearchEvaluation:

    if not text:
        return ResearchEvaluation(
            is_sufficient=True,
            reason="Evaluator returned no response. Using available evidence.",
            missing_information="",
            follow_up_query="",
        )

    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.replace("```json", "").replace("```", "").strip()

    try:
        data = json.loads(cleaned)
        return ResearchEvaluation(
            is_sufficient=bool(data.get("is_sufficient", True)),
            reason=str(data.get("reason", "")),
            missing_information=str(data.get("missing_information", "")),
            follow_up_query=str(data.get("follow_up_query", "")),
        )
    except Exception:
        pass

    lower = text.lower()
    insufficient = (
        "insufficient" in lower
        or "not sufficient" in lower
        or "missing information" in lower
        or "information gap" in lower
    )

    return ResearchEvaluation(
        is_sufficient=not insufficient,
        reason=text[:2000],
        missing_information=(
            "Additional information is required." if insufficient else ""
        ),
        follow_up_query="",
    )


def _safe_fallback_evaluation(reason: str) -> ResearchEvaluation:
    return ResearchEvaluation(
        is_sufficient=True,
        reason=reason,
        missing_information="",
        follow_up_query="",
    )


# ============================================================
# STEP 1 — PLAN QUERIES (2 queries only, fast)
# ============================================================

def _plan_queries_sync(topic: str) -> list[str]:
    """Sync planner — runs in a worker thread."""

    prompt = f"""
You are a research planning agent.

Research topic:
{topic}

Create exactly 2 focused, specific web search queries.

Rules:
- Each query must be a concrete, searchable phrase.
- Cover different aspects of the topic.
- Prefer queries between 6 and 15 words.

Return JSON only in exactly this format:
{{"queries": ["query 1", "query 2"]}}

Do not use markdown fences.
Do not add explanations.
"""

    queries = None

    # --- Attempt 1: Gemini structured output ---
    try:
        print("Planning via structured output (Gemini)...")
        llm = get_planner_llm().with_structured_output(QueryPlan)
        plan = llm.invoke(prompt)
        queries = list(plan.queries)
        print("Structured output succeeded.")
    except Exception as e1:
        print("Structured output failed:", e1)

    # --- Attempt 2: Groq plain invoke + JSON parse ---
    if not queries:
        try:
            print("Retrying with Groq plain invoke...")
            fallback = get_groq()
            response = fallback.invoke(prompt)
            text = extract_text(response)

            cleaned = text.strip()
            if cleaned.startswith("```"):
                cleaned = (
                    cleaned.replace("```json", "")
                    .replace("```", "")
                    .strip()
                )
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start != -1 and end != -1:
                cleaned = cleaned[start : end + 1]

            data = json.loads(cleaned)
            queries = data.get("queries", [])
            print("Groq plain invoke + JSON parse succeeded.")
        except Exception as e2:
            print("Groq plain invoke failed:", e2)

    # --- Attempt 3: generic 2-query fallback ---
    if not queries:
        print("Using generic fallback queries.")
        base = topic[:80]
        queries = [
            f"{base} definition and overview",
            f"{base} examples and use cases",
        ]

    queries = [q for q in queries if q and q.strip()][:2]

    if not queries:
        queries = [topic[:80] or "research topic"]

    return queries


async def _plan_queries_async(topic: str) -> list[str]:
    """Planner with retries + hard timeout."""
    last_err = None
    for attempt in range(1, PLANNER_RETRIES + 1):
        try:
            print(f"[plan] Attempt {attempt}/{PLANNER_RETRIES}...")
            queries = await asyncio.wait_for(
                _to_thread(_plan_queries_sync, topic),
                timeout=PLANNER_TIMEOUT,
            )
            if queries:
                return queries
        except asyncio.TimeoutError as e:
            last_err = e
            print(f"[plan] Timed out after {PLANNER_TIMEOUT}s.")
        except Exception as e:
            last_err = e
            print(f"[plan] Error: {e}")
            if not _is_transient_error(e):
                print("[plan] Non-transient — aborting retries.")
                break

        if attempt < PLANNER_RETRIES:
            print(f"[plan] Sleeping {PLANNER_RETRY_DELAY}s before retry...")
            await asyncio.sleep(PLANNER_RETRY_DELAY)

    print("[plan] All attempts failed — using 2-query generic fallback.")
    base = topic[:80]
    return [
        f"{base} definition and overview",
        f"{base} examples and use cases",
    ]


def plan_queries(state: ResearchState) -> dict:
    print("\n==============================")
    print("STEP 1: PLANNING RESEARCH")
    print("==============================")

    queries = _run_async_in_isolated_loop(_plan_queries_async, state["topic"])
    queries = [q for q in queries if q and q.strip()][:2]

    print("\nGenerated search queries:")
    for i, q in enumerate(queries, start=1):
        print(f"{i}. {q}")

    return {
        "search_queries": queries,
        "pending_queries": queries,
        "loop_count": 0,
        "is_sufficient": False,
        "evaluation_reason": "",
        "missing_information": "",
        "final_report": "",
    }


# ============================================================
# STEP 2 — WEB SEARCH
# ============================================================

def search_web(state: ResearchState) -> dict:
    print("\n==============================")
    print("STEP 2: WEB SEARCH")
    print("==============================")

    settings = get_settings()
    pending_queries = state.get("pending_queries", [])

    print(f"Searching {len(pending_queries)} queries...")

    for q in pending_queries:
        print(f"\nSearching: {q}")

    new_results = execute_web_searches(
        pending_queries,
        max_results=settings.SEARCH_RESULTS_PER_QUERY,
    )
    print(
        f"Found {len(new_results)} results across "
        f"{len(pending_queries)} queries."
    )

    previous = state.get("search_results", [])
    combined = previous + new_results

    print(f"\nTotal research results: {len(combined)}")

    return {
        "search_results": combined,
        "pending_queries": [],
    }


# ============================================================
# STEP 3 — EVALUATE RESEARCH (with fast-path skip)
# ============================================================

def _build_evaluation_prompt(state: ResearchState) -> str:
    evidence = build_evidence_context(state.get("search_results", []))
    return f"""
You are the quality-control component of an autonomous web research agent.

Research topic:
{state["topic"]}

Collected web evidence:
{evidence}

Determine whether the evidence is sufficient for a useful factual research report.

Sufficient means:
- The main topic is covered.
- Multiple useful sources exist.
- Important aspects are represented.
- No major obvious information gap.

If insufficient:
1. Identify the biggest information gap.
2. Generate ONE targeted follow-up search query.

Return ONLY valid JSON in this structure:

{{
    "is_sufficient": true,
    "reason": "Short explanation",
    "missing_information": "",
    "follow_up_query": ""
}}

If more research is required:

{{
    "is_sufficient": false,
    "reason": "Short explanation",
    "missing_information": "What is missing",
    "follow_up_query": "One focused search query"
}}

Do not use Markdown. Return JSON only.
"""


async def _gemini_evaluate(prompt: str) -> ResearchEvaluation:
    last_err = None
    for attempt in range(1, EVALUATOR_RETRIES + 1):
        try:
            print(f"[eval] Gemini attempt {attempt}/{EVALUATOR_RETRIES}...")
            llm = get_evaluator_llm().with_structured_output(ResearchEvaluation)
            result = await asyncio.wait_for(
                _to_thread(llm.invoke, prompt),
                timeout=EVALUATOR_TIMEOUT,
            )
            print("[eval] Gemini succeeded.")
            return result
        except asyncio.TimeoutError as e:
            last_err = e
            print(f"[eval] Gemini timed out after {EVALUATOR_TIMEOUT}s.")
        except Exception as e:
            last_err = e
            print(f"[eval] Gemini error: {e}")
            if not _is_transient_error(e):
                print("[eval] Non-transient — aborting Gemini retries.")
                raise

        if attempt < EVALUATOR_RETRIES:
            print(f"[eval] Sleeping {EVALUATOR_RETRY_DELAY}s before retry...")
            await asyncio.sleep(EVALUATOR_RETRY_DELAY)

    raise last_err or RuntimeError("Gemini evaluator failed after retries")


async def _groq_evaluate(prompt: str) -> ResearchEvaluation:
    fallback = get_groq()
    response = await asyncio.wait_for(
        _to_thread(fallback.invoke, prompt),
        timeout=EVALUATOR_TIMEOUT,
    )
    text = extract_text(response)
    print("\nGroq evaluator response (first 1000 chars):")
    print(text[:1000])
    return parse_evaluation_text(text)


async def _evaluate_async(state: ResearchState) -> dict:
    print("\n==============================")
    print("STEP 3: EVALUATING RESEARCH")
    print("==============================")

    settings = get_settings()
    loop_count = state.get("loop_count", 0)

    # ---- Hard ceiling on loops ----
    if loop_count >= settings.MAX_SEARCH_LOOPS:
        print("\nMaximum research loops reached.")
        return {
            "is_sufficient": True,
            "evaluation_reason": (
                "Maximum research loops reached. "
                "Available evidence will be used."
            ),
            "missing_information": "",
            "pending_queries": [],
            "loop_count": loop_count + 1,
        }

    # ---- FAST-PATH: skip LLM evaluation if we already have enough sources ----
    sources_count = len(state.get("search_results", []))
    if sources_count >= FAST_PATH_SOURCE_THRESHOLD:
        print(
            f"[eval] Fast-path: {sources_count} sources collected "
            f"→ skipping LLM evaluation."
        )
        return {
            "is_sufficient": True,
            "evaluation_reason": (
                f"{sources_count} sources collected — proceeding directly."
            ),
            "missing_information": "",
            "pending_queries": [],
            "loop_count": loop_count + 1,
        }

    prompt = _build_evaluation_prompt(state)

    # ---- Attempt 1: Gemini ----
    try:
        evaluation = await _gemini_evaluate(prompt)
        provider_used = "Gemini"
    except Exception as gemini_err:
        print("\nGemini evaluator failed after retries:")
        print(gemini_err)
        print("\nFalling back to Groq evaluator...")

        # ---- Attempt 2: Groq ----
        try:
            evaluation = await _groq_evaluate(prompt)
            provider_used = "Groq fallback"
        except Exception as groq_err:
            print("\nGroq evaluator failed:")
            print(groq_err)

            # ---- Attempt 3: permissive fallback (never hang) ----
            evaluation = _safe_fallback_evaluation(
                "Both Gemini and Groq evaluators failed. "
                "Proceeding with available evidence."
            )
            provider_used = "Fallback - no evaluator"

    print("\nEvaluator:", provider_used)
    print("Research sufficient:", evaluation.is_sufficient)
    print("Reason:", evaluation.reason)
    print("Missing information:", evaluation.missing_information)
    print("Follow-up query:", evaluation.follow_up_query)

    update = {
        "is_sufficient": evaluation.is_sufficient,
        "evaluation_reason": evaluation.reason,
        "missing_information": evaluation.missing_information,
        "pending_queries": [],
    }

    if not evaluation.is_sufficient:
        follow_up = (evaluation.follow_up_query or "").strip()
        if not follow_up:
            follow_up = f"{state['topic']} detailed explanation"
            print("\nNo follow-up query from evaluator — using fallback:")
            print(follow_up)
        else:
            print("\nAdditional research required. Next query:")
            print(follow_up)

        update["pending_queries"] = [follow_up]
        update["search_queries"] = (
            state.get("search_queries", []) + [follow_up]
        )
        update["loop_count"] = loop_count + 1
    else:
        update["loop_count"] = loop_count + 1
        print("\nResearch is sufficient.")

    return update


def evaluate_results(state: ResearchState) -> dict:
    return _run_async_in_isolated_loop(_evaluate_async, state)


# ============================================================
# STEP 4 — WRITE REPORT (concise, fast)
# ============================================================

def _build_writer_prompt(state: ResearchState) -> str:
    evidence = build_evidence_context(state.get("search_results", []))
    return f"""
You are a research writer. Write a CONCISE factual report.

Topic: {state["topic"]}

Evidence:
{evidence}

Safety rules:
- Do not generate pornography or sexually explicit material.
- Do not generate erotic stories or sexual roleplay.
- Do not provide instructions for self-harm or suicide.
- Do not provide instructions for dangerous or violent activities.
- Do not provide instructions for creating explosives or weapons.
- If the requested report would require prohibited content, provide a brief safe refusal instead.

Write in Markdown with these sections ONLY:

# {state["topic"]}

## Overview
2-3 sentences.

## Key Points
5-7 bullet points.

## How It Works
One short paragraph.

## Applications
3-4 bullets.

## Challenges
3-4 bullets.

## Conclusion
1-2 sentences.

## Sources
List the URLs used.

Keep the whole report under 700 words. Do not pad. Do not invent facts.
"""


def _fallback_report(state: ResearchState, note: str) -> str:
    sources = state.get("search_results", [])
    return (
        "## Research Report\n\n"
        f"{note}\n\n"
        "### Sources\n\n"
        + "\n".join(
            f"- [{s.get('title', 'Untitled')}]({s.get('url', '')})"
            for s in sources[:15]
        )
    )


async def _write_async(state: ResearchState) -> str:
    prompt = _build_writer_prompt(state)

    last_err = None
    for attempt in range(1, WRITER_RETRIES + 1):
        try:
            print(f"[write] Attempt {attempt}/{WRITER_RETRIES}...")
            llm = get_writer_llm()
            response = await asyncio.wait_for(
                _to_thread(llm.invoke, prompt),
                timeout=WRITER_TIMEOUT,
            )

            print("\n--- RAW WRITER RESPONSE ---")
            print("Type:", type(response))
            print(
                "Content preview:",
                str(getattr(response, "content", ""))[:500],
            )
            print("--- END RAW ---\n")

            report = extract_text(response)
            if report and report.strip():
                print("Final report length:", len(report))
                return report
            else:
                print("Writer returned empty — will retry.")
        except asyncio.TimeoutError as e:
            last_err = e
            print(f"[write] Timed out after {WRITER_TIMEOUT}s.")
        except Exception as e:
            last_err = e
            print(f"[write] Error: {e}")
            if not _is_transient_error(e):
                print("[write] Non-transient — aborting retries.")
                break

        if attempt < WRITER_RETRIES:
            print(f"[write] Sleeping {WRITER_RETRY_DELAY}s before retry...")
            await asyncio.sleep(WRITER_RETRY_DELAY)

    print("[write] All attempts failed. Using fallback report.")
    return _fallback_report(
        state,
        "The report generation failed after retries. "
        "Below are the collected sources.",
    )


def write_report(state: ResearchState) -> dict:
    print("\n==============================")
    print("STEP 4: WRITING FINAL REPORT")
    print("==============================")

    report = _run_async_in_isolated_loop(_write_async, state)
    print("\nFinal report length:", len(report))

    return {"final_report": report}