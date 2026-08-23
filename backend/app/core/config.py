"""
Configuration settings for Project Synapse Backend.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# Determine directory paths
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
REPO_ROOT = BACKEND_DIR.parent

# Load .env proactively into os.environ from known locations
for env_candidate in [
    BACKEND_DIR / ".env",
    REPO_ROOT / ".env",
    Path.cwd() / ".env",
    Path.cwd() / "backend" / ".env",
]:
    if env_candidate.is_file():
        load_dotenv(env_candidate, override=False)


class Settings(BaseSettings):
    PROJECT_NAME: str = "Project Synapse Decision Audit API"
    VERSION: str = "1.0.0"
    API_V1_PREFIX: str = "/api"

    # Database
    # Default to a local SQLite database in backend if DATABASE_URL is not set
    DATABASE_URL: str = os.getenv("DATABASE_URL") or f"sqlite:///{BACKEND_DIR}/synapse.db"

    # Supabase (Optional in local dev, required for cloud deployment)
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")
    SUPABASE_SERVICE_ROLE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    SUPABASE_BUCKET_NAME: str = os.getenv("SUPABASE_BUCKET_NAME", "synapse-documents")

    # Cryptography / Hash Chain Secret for HMAC
    HMAC_SECRET: str = os.getenv("HMAC_SECRET", "synapse-hmac-server-secret-key-2026-audit-integrity")

    # LLM API Keys and Models
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
    GEMINI_TIMEOUT_MS: int = int(os.getenv("GEMINI_TIMEOUT_MS", "30000"))

    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "qwen/qwen3.6-27b")
    GROQ_TIMEOUT_MS: int = int(os.getenv("GROQ_TIMEOUT_MS", "30000"))

    # OCR / Tesseract
    TESSERACT_CMD: str = os.getenv("TESSERACT_CMD", "")

    # Storage paths for local storage
    LOCAL_STORAGE_DIR: str = os.getenv(
        "LOCAL_STORAGE_DIR",
        str(BACKEND_DIR / "storage")
    )

    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "http://127.0.0.1:8000",
        "https://*.vercel.app",
        "https://*.onrender.com",
    ]

    model_config = SettingsConfigDict(
        env_file=(
            str(BACKEND_DIR / ".env"),
            str(REPO_ROOT / ".env"),
            ".env",
        ),
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()

# Clean up any surrounding whitespace in sensitive variables
settings.GEMINI_API_KEY = settings.GEMINI_API_KEY.strip()
settings.GROQ_API_KEY = settings.GROQ_API_KEY.strip()
settings.SUPABASE_URL = settings.SUPABASE_URL.strip()
settings.SUPABASE_SERVICE_ROLE_KEY = settings.SUPABASE_SERVICE_ROLE_KEY.strip()
settings.SUPABASE_KEY = settings.SUPABASE_KEY.strip()

# Always sync configuration into os.environ for external SDKs and submodules
if settings.GEMINI_API_KEY and not os.environ.get("GEMINI_API_KEY"):
    os.environ["GEMINI_API_KEY"] = settings.GEMINI_API_KEY
if settings.GEMINI_MODEL and not os.environ.get("GEMINI_MODEL"):
    os.environ["GEMINI_MODEL"] = settings.GEMINI_MODEL
if settings.GROQ_API_KEY and not os.environ.get("GROQ_API_KEY"):
    os.environ["GROQ_API_KEY"] = settings.GROQ_API_KEY
if settings.GROQ_MODEL and not os.environ.get("GROQ_MODEL"):
    os.environ["GROQ_MODEL"] = settings.GROQ_MODEL
if settings.TESSERACT_CMD and not os.environ.get("TESSERACT_CMD"):
    os.environ["TESSERACT_CMD"] = settings.TESSERACT_CMD

# Ensure local storage directory exists
Path(settings.LOCAL_STORAGE_DIR).mkdir(parents=True, exist_ok=True)
