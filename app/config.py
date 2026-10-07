from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq


class Settings(BaseSettings):

    LLM_PROVIDER: str = "dual"

    GEMINI_MODEL: str = "gemini-3.8-flash"
    GROQ_MODEL: str = "openai/gpt-oss-20b"

    GEMINI_API_KEY: str = ""
    GROQ_API_KEY: str = ""

    DATABASE_URL: str = (
        "postgresql+psycopg2://postgres:postgres@localhost:5432/research_agent"
    )

    MAX_SEARCH_LOOPS: int = 2
    SEARCH_RESULTS_PER_QUERY: int = 5

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings():
    return Settings()


# ==========================================
# GEMINI
# ==========================================

def get_gemini():
    settings = get_settings()
    if not settings.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is missing in .env")
    return ChatGoogleGenerativeAI(
        model=settings.GEMINI_MODEL,
        google_api_key=settings.GEMINI_API_KEY,
        temperature=0.1,
    )


# ==========================================
# GROQ
# ==========================================

def get_groq():
    settings = get_settings()
    if not settings.GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY is missing in .env")
    return ChatGroq(
        model=settings.GROQ_MODEL,
        api_key=settings.GROQ_API_KEY,
        temperature=0.1,
    )


# ==========================================
# PLANNER — Gemini for reliable structured output
# ==========================================

def get_planner_llm():
    # Groq is preferred when Gemini quota is exhausted.
    # It's less reliable for structured output, but plan_queries has fallbacks.
    return get_groq()


# ==========================================
# EVALUATOR — Gemini preferred, Groq fallback in nodes.py
# ==========================================

def get_evaluator_llm():
    return get_gemini()


# ==========================================
# WRITER — Groq 120b for long structured reports
# ==========================================

def get_writer_llm():
    settings = get_settings()
    if not settings.GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY is missing in .env")
    return ChatGroq(
        model="openai/gpt-oss-20b",
        api_key=settings.GROQ_API_KEY,
        temperature=0.1,
        max_tokens=1500,
    )