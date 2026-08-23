"""
Documents API Endpoints.
Allows fetching document metadata and streaming document binary files for the viewer.
"""

from __future__ import annotations

import os
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, require_permission
from app.db.session import get_db
from app.db.models import Document
from app.schemas.application import DocumentResponse

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.get("/{id}", response_model=DocumentResponse)
def get_document_info(
    id: str,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission("view")),
):
    doc = db.query(Document).filter(Document.id == id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    return doc


@router.get("/{id}/file")
def stream_document_file(
    id: str,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission("view")),
):
    """Streams the raw PDF or image file for rendering in the UI split-screen viewer."""
    doc = db.query(Document).filter(Document.id == id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    if not os.path.exists(doc.storage_path):
        raise HTTPException(status_code=404, detail="Document file not found on disk.")

    return FileResponse(
        path=doc.storage_path,
        media_type=doc.mime_type or "application/pdf",
        filename=doc.file_name,
    )
