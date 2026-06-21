from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.api.routes import audio, cases, characters, checkpoints, edl, logs, pipeline, profiles, research, scripts, steps
from src.api.routes import agent as agent_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load environment variables from .env before anything else
    load_dotenv()

    # Initialise the database (creates tables / extensions if absent)
    from src.db.session import init_db
    init_db()

    yield
    # Nothing to clean up on shutdown


app = FastAPI(
    title="IndianCrimes API",
    description="Backend for the IndianCrimes Hindi true crime YouTube channel pipeline",
    version="1.0.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS — allow all origins (Next.js dev server, production domain, etc.)
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Static file serving — serve generated case assets
# ---------------------------------------------------------------------------

_CASES_DIR = Path("data/cases")
_CASES_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/files/cases", StaticFiles(directory=str(_CASES_DIR)), name="case_files")

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(cases.router, prefix="/api")
app.include_router(pipeline.router, prefix="/api")
app.include_router(logs.router, prefix="/api")
app.include_router(scripts.router, prefix="/api")
app.include_router(characters.router, prefix="/api")
app.include_router(agent_router.router, prefix="/api")
app.include_router(steps.router, prefix="/api")
app.include_router(audio.router, prefix="/api")
app.include_router(edl.router, prefix="/api")
app.include_router(profiles.router, prefix="/api")
app.include_router(checkpoints.router, prefix="/api")
app.include_router(research.router, prefix="/api")


# ---------------------------------------------------------------------------
# Root health check
# ---------------------------------------------------------------------------


@app.get("/")
async def root():
    return {"status": "ok", "service": "IndianCrimes API"}
