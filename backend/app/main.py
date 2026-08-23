"""
Project Synapse — Main FastAPI Application Entrypoint.
Evidence-Grounded Decision Audit for AI-Assisted Government Workflows.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.db.session import engine, Base, SessionLocal
from app.api.applications import router as applications_router
from app.api.documents import router as documents_router
from app.api.review import router as review_router
from app.api.replay import router as replay_router
from app.api.policies import router as policies_router
from app.api.audit import router as audit_router
from app.api.demo import router as demo_router
from app.services.seed_service import SeedService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("synapse")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initializes tables and seeds default policy versions and demo records."""
    logger.info("Initializing Project Synapse database tables...")
    Base.metadata.create_all(bind=engine)

    # Validate configuration on startup
    if not os.environ.get("GEMINI_API_KEY") and not settings.GEMINI_API_KEY:
        logger.warning(
            "GEMINI_API_KEY is not set in environment or .env. Extraction service calls will fail unless configured."
        )
    else:
        # Ensure it is set in os.environ for services that read os.environ directly
        if settings.GEMINI_API_KEY and not os.environ.get("GEMINI_API_KEY"):
            os.environ["GEMINI_API_KEY"] = settings.GEMINI_API_KEY

    if settings.TESSERACT_CMD and not os.environ.get("TESSERACT_CMD"):
        os.environ["TESSERACT_CMD"] = settings.TESSERACT_CMD

    # Seed initial demo state if empty
    db = SessionLocal()
    try:
        SeedService.seed_all_demo_data(db)
        logger.info("Database initialized with default policies and demo cases (A, B, C).")
    except Exception as exc:
        logger.error("Error during initial data seed: %s", exc)
    finally:
        db.close()

    yield
    logger.info("Project Synapse backend shutdown.")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Evidence-Grounded Decision Audit Platform for AI-Assisted Government Workflows.",
    lifespan=lifespan,
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Routers under /api
app.include_router(applications_router, prefix=settings.API_V1_PREFIX)
app.include_router(documents_router, prefix=settings.API_V1_PREFIX)
app.include_router(review_router, prefix=settings.API_V1_PREFIX)
app.include_router(replay_router, prefix=settings.API_V1_PREFIX)
app.include_router(policies_router, prefix=settings.API_V1_PREFIX)
app.include_router(audit_router, prefix=settings.API_V1_PREFIX)
app.include_router(demo_router, prefix=settings.API_V1_PREFIX)


@app.get("/health", status_code=status.HTTP_200_OK, tags=["Health"])
def health_check():
    """Service health check endpoint."""
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "policy_engine": "pure_python_deterministic",
        "audit_integrity": "sha256_hash_chain_hmac",
    }


@app.get("/", tags=["Root"])
def root():
    return {
        "message": "Welcome to Project Synapse API. Visit /docs for OpenAPI documentation.",
        "project": "Evidence-Grounded Decision Audit for AI-Assisted Government Workflows",
    }
