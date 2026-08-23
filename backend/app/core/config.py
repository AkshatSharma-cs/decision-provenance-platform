"""
Configuration settings for Project Synapse Backend.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Project Synapse Decision Audit API"
    VERSION: str = "1.0.0"
    API_V1_PREFIX: str = "/api"

    # Database
    # Default to a local SQLite database in backend/data if DATABASE_URL is not set
    DATABASE_URL: str = os.getenv("DATABASE_URL") or f"sqlite:///{Path(__file__).resolve().parent.parent.parent}/synapse.db"
    

    # Supabase (Optional in local dev, required for cloud deployment)
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")
    SUPABASE_SERVICE_ROLE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    SUPABASE_BUCKET_NAME: str = os.getenv("SUPABASE_BUCKET_NAME", "synapse-documents")

    # Cryptography / Hash Chain Secret for HMAC
    HMAC_SECRET: str = os.getenv("HMAC_SECRET", "synapse-hmac-server-secret-key-2026-audit-integrity")

    # LLM API Keys
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")

    # OCR / Tesseract
    TESSERACT_CMD: str = os.getenv("TESSERACT_CMD", "")

    # Storage paths for local storage
    LOCAL_STORAGE_DIR: str = os.getenv(
        "LOCAL_STORAGE_DIR",
        str(Path(__file__).resolve().parent.parent.parent / "storage")
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
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()

# Ensure local storage directory exists
Path(settings.LOCAL_STORAGE_DIR).mkdir(parents=True, exist_ok=True)
