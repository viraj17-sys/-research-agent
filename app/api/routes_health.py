from fastapi import APIRouter

from app.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/api/health")
def health():
    s = get_settings()
    return {
        "status": "ok",
        "provider": s.LLM_PROVIDER,
        "gemini_model": s.GEMINI_MODEL,
        "groq_model": s.GROQ_MODEL,
    }