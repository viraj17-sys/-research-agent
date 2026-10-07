import asyncio
import json
import queue
import threading

from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from app.database.database import SessionLocal
from app.database import crud
from app.schemas.chat import ChatRequest
from app.agent.graph import research_graph

from app.safety.content_filter import (
    is_restricted_content,
    RESTRICTION_MESSAGE,
)

router = APIRouter(prefix="/api", tags=["research"])


# ============================================================
# GREETING / CHIT-CHAT GUARD
# ============================================================

GREETING_PATTERNS = {
    "hi", "hii", "hiii", "hello", "hey", "yo", "sup",
    "thanks", "thank you", "thx", "ty",
    "ok", "okay", "k", "cool",
    "bye", "goodbye", "see you",
    "good morning", "good evening", "good night",
    "how are you", "how r u", "whats up", "what's up",
}


def _is_greeting(message: str) -> bool:
    cleaned = message.strip().lower().rstrip("!?.,:;")
    return cleaned in GREETING_PATTERNS


def _event(event_type: str, **data) -> dict:
    return {
        "event": event_type,
        "data": json.dumps({"type": event_type, **data}),
    }


def _build_context_prefix(history_messages, current_message: str, max_turns: int = 2) -> str:
    """
    Produce a SHORT, CLEAN context prefix — never embeds multi-line blocks
    that break the planner's query generation.

    Returns an empty string if there's no useful context.
    """
    if not history_messages:
        return ""

    recent_user = [
        m.content.strip()
        for m in history_messages
        if m.role == "user" and m.content
    ][-max_turns:]

    if not recent_user:
        return ""

    current_lower = current_message.strip().lower()
    vague = (
        len(current_lower.split()) <= 4
        or current_lower in {
            "tell me more", "more", "continue", "deeper",
            "deep dive", "deep more", "explain more", "go deeper",
        }
        or current_lower.startswith("deep")
        or current_lower.startswith("more on")
    )

    if not vague:
        # Current question is self-contained — no prefix needed
        return ""

    # Use the most recent user message as the anchor, single-line and short
    anchor = recent_user[-1].replace("\n", " ").strip()[:120]
    if not anchor:
        return ""

    return f"{anchor} — "


# ============================================================
# MAIN ENDPOINT
# ============================================================

@router.post("/chat")
async def chat_endpoint(payload: ChatRequest, request: Request):
    user_message = payload.message.strip()
    if not user_message:
        raise HTTPException(status_code=400, detail="Empty message")


    # ========================================================
    # CONTENT SAFETY CHECK
    # Applies to ALL users regardless of age.
    # ========================================================

    if is_restricted_content(user_message):

        db = SessionLocal()

        try:
            chat_id = payload.chat_id

            if not chat_id:
                chat = crud.create_chat(
                    db,
                    "Content Restricted"
                )
                chat_id = str(chat.id)
            else:
                chat = crud.get_chat(db, chat_id)

                if not chat:
                    raise HTTPException(
                        status_code=404,
                        detail="Chat not found"
                    )

            # Save user's message
            crud.add_message(
                db,
                chat_id,
                "user",
                user_message
            )

            # Save safety response
            assistant_msg = crud.add_message(
                db,
                chat_id,
                "assistant",
                RESTRICTION_MESSAGE
            )

            crud.touch_chat(db, chat_id)

            assistant_id = str(assistant_msg.id)

        finally:
            db.close()

        async def restricted_generator():

            yield _event(
                "research_started",
                chat_id=chat_id,
                message=user_message,
            )

            yield _event(
                "content_restricted",
                chat_id=chat_id,
                message_id=assistant_id,
                response=RESTRICTION_MESSAGE,
            )

        return EventSourceResponse(restricted_generator())

    
    # ---- Greeting short-circuit ----
    if _is_greeting(user_message):
        db = SessionLocal()
        try:
            chat_id = payload.chat_id
            if not chat_id:
                chat = crud.create_chat(db, user_message[:60])
                chat_id = str(chat.id)
            else:
                chat = crud.get_chat(db, chat_id)
                if not chat:
                    raise HTTPException(status_code=404, detail="Chat not found")

            crud.add_message(db, chat_id, "user", user_message)

            friendly_reply = (
                "Hey! 👋 I'm your research assistant. "
                "Ask me something specific — like:\n\n"
                "- *What is Agentic RAG and how does it work?*\n"
                "- *Latest developments in multi-agent systems*\n"
                "- *Compare LangGraph vs CrewAI*\n\n"
                "What would you like to research?"
            )

            assistant_msg = crud.add_message(db, chat_id, "assistant", friendly_reply)
            crud.touch_chat(db, chat_id)
            assistant_id = str(assistant_msg.id)
        finally:
            db.close()

        async def simple_generator():
            yield _event("research_started", chat_id=chat_id, message=user_message)
            import base64
            reply_b64 = base64.b64encode(friendly_reply.encode("utf-8")).decode("ascii")
            yield _event(
                "research_completed",
                chat_id=chat_id,
                message_id=assistant_id,
                report_b64=reply_b64,
                report_length=len(friendly_reply),
                sources=[],
            )

        return EventSourceResponse(simple_generator())

    # ---- Prepare DB rows + load prior context ----
    db = SessionLocal()
    try:
        chat_id = payload.chat_id
        if not chat_id:
            chat = crud.create_chat(db, user_message[:60])
            chat_id = str(chat.id)
            history = []
        else:
            chat = crud.get_chat(db, chat_id)
            if not chat:
                raise HTTPException(status_code=404, detail="Chat not found")
            history = crud.get_messages(db, chat_id)

        crud.add_message(db, chat_id, "user", user_message)
        run = crud.start_run(db, chat_id)
        run_id = str(run.id)

        # Build SHORT context prefix (never a multi-line block)
        context_prefix = _build_context_prefix(history, user_message)
        agent_topic = (context_prefix + user_message).strip()[:300]

        print("\n--- Agent topic (with context) ---")
        print(agent_topic)
        print("--- end ---\n")

    finally:
        db.close()

    async def event_generator():
        yield _event("research_started", chat_id=chat_id, message=user_message)

        initial_state = {
            "topic": agent_topic,
            "search_queries": [],
            "pending_queries": [],
            "search_results": [],
            "loop_count": 0,
            "is_sufficient": False,
            "evaluation_reason": "",
            "missing_information": "",
            "final_report": "",
        }

        latest_state = dict(initial_state)

        try:
            updates_queue = queue.Queue()
            finished = object()

            def _stream_graph():
                try:
                    for update in research_graph.stream(initial_state, stream_mode="updates"):
                        updates_queue.put(("update", update))
                except Exception as error:
                    updates_queue.put(("error", error))
                finally:
                    updates_queue.put(("finished", finished))

            threading.Thread(target=_stream_graph, daemon=True).start()
            prev_source_count = 0

            while True:
                kind, item = await asyncio.to_thread(updates_queue.get)
                if kind == "finished":
                    break
                if kind == "error":
                    raise item

                update = item
                for node_name, node_update in update.items():
                    if node_update:
                        latest_state.update(node_update)

                    if node_name == "plan_queries":
                        yield _event(
                            "planning",
                            queries=node_update.get("search_queries", []),
                        )

                    elif node_name == "search_web":
                        results = node_update.get(
                            "search_results", []
                        ) or latest_state.get("search_results", [])
                        total = len(results)
                        yield _event(
                            "search_completed",
                            total_sources=total,
                            new_sources=max(total - prev_source_count, 0),
                        )
                        prev_source_count = total
                        yield _event(
                            "sources_collected",
                            total_sources=total,
                        )

                    elif node_name == "evaluate_results":
                        sufficient = node_update.get("is_sufficient", False)
                        if sufficient:
                            yield _event(
                                "evaluation_completed",
                                is_sufficient=True,
                                reason=node_update.get("evaluation_reason", ""),
                            )
                        else:
                            yield _event(
                                "followup_search",
                                missing=node_update.get("missing_information", ""),
                                next_queries=node_update.get("pending_queries", []),
                            )

                    elif node_name == "write_report":
                        yield _event("writing_started")

            # ---- Persist result ----
report = latest_state.get("final_report", "") or ""
sources = latest_state.get("search_results", [])

# ========================================================
# FINAL OUTPUT SAFETY CHECK
# ========================================================

if is_restricted_content(report):
    print("⚠️ Restricted content detected in AI output.")
    report = RESTRICTION_MESSAGE
    sources = []

            if not report.strip():
                report = (
                    "## Research Report\n\n"
                    "The agent could not generate a report for this follow-up. "
                    "Please try rephrasing your question.\n\n"
                    "### Sources collected\n\n"
                    + "\n".join(
                        f"- [{s.get('title','Untitled')}]({s.get('url','')})"
                        for s in sources[:10]
                    )
                )

            db2 = SessionLocal()
            try:
                assistant_msg = crud.add_message(db2, chat_id, "assistant", report)
                if sources:
                    crud.add_sources(db2, str(assistant_msg.id), sources)
                crud.finish_run(db2, run_id, "completed", str(assistant_msg.id))
                crud.touch_chat(db2, chat_id)
                assistant_id = str(assistant_msg.id)
            finally:
                db2.close()

            import base64
            report_b64 = base64.b64encode(report.encode("utf-8")).decode("ascii")

            yield _event(
                "research_completed",
                chat_id=chat_id,
                message_id=assistant_id,
                report_b64=report_b64,
                report_length=len(report),
                sources=[
                    {
                        "title": s.get("title", ""),
                        "url": s.get("url", ""),
                        "snippet": s.get("snippet", ""),
                    }
                    for s in sources
                ],
            )

        except Exception as exc:
            import traceback
            tb = traceback.format_exc()
            print("\n========== RESEARCH ERROR ==========")
            print(tb)
            print("=====================================\n")

            try:
                db3 = SessionLocal()
                crud.finish_run(db3, run_id, "failed")
                db3.close()
            except Exception:
                pass

            yield _event("error", message=f"{type(exc).__name__}: {exc}")

    return EventSourceResponse(event_generator())