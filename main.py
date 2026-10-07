from fastapi import FastAPI, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from app.database.database import Base, engine
from app.database import models  # noqa: F401  (register models)

from app.api.routes_health import router as health_router
from app.api.routes_chat import router as chat_router
from app.api.routes_research import router as research_router


app = FastAPI(
    title="Agentic Research Chatbot",
    version="1.0.0",
)


# ---- Optional: enable CORS if you later separate frontend ----
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- Create tables if schema.sql wasn't run ----
@app.on_event("startup")
def _startup():
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        print("Startup DB warning:", e)


# ---- API routers ----
app.include_router(health_router)
app.include_router(chat_router)
app.include_router(research_router)


# ---- Static frontend ----
app.mount("/static", StaticFiles(directory="static"), name="static")


# ---- Favicon routes (silence browser defaults) ----
@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    # Browsers auto-request this; return 204 No Content to keep logs clean.
    return Response(status_code=204)


@app.get(
    "/.well-known/appspecific/com.chrome.devtools.json",
    include_in_schema=False,
)
def chrome_devtools_config():
    # Chrome DevTools auto-requests this; return 204 to keep logs clean.
    return Response(status_code=204)


# ---- Root: serve the frontend ----
@app.get("/")
def serve_index():
    return FileResponse("static/index.html")