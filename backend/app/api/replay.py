"""
Decision Replay API Endpoints.
Reconstructs full historical decision journeys, snapshot audits, and verification badges.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, require_permission
from app.db.session import get_db
from app.db.models import Application
from app.schemas.replay import ApplicationReplayResponse
from app.services.replay_service import ReplayService

router = APIRouter(prefix="/applications", tags=["Replay & Provenance"])


@router.get("/{id}/replay", response_model=ApplicationReplayResponse)
def get_application_replay(
    id: str,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission("view")),
):
    """
    Returns the complete historical reconstruction for an application:
    - Uploaded document hashes
    - OCR tokens & extracted fields
    - Historical decision versions (v1, v2)
    - Full vertical timeline of events
    - Real-time cryptographic hash-chain verification badge
    """
    app = db.query(Application).filter(
        (Application.id == id) | (Application.public_reference == id)
    ).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found.")

    replay_data = ReplayService.reconstruct_replay(db, app.id)
    if not replay_data:
        raise HTTPException(status_code=404, detail="Could not reconstruct replay for this application.")

    return replay_data
