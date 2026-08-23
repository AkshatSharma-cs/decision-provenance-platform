"""
Demo and Adversarial Testing API Endpoints.
Allows seeding pre-computed demo cases (APP-00016, APP-00017, APP-00018),
resetting demo state, and testing adversarial tampering detection.
"""

from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.core.security import CurrentUser, require_permission
from app.db.session import get_db
from app.db.models import (
    Application,
    AuditLogEntry,
    Decision,
    DecisionRuleResult,
    Document,
    ExtractedField,
    OCRPage,
    OCRToken,
    ReviewAction,
)
from app.services.seed_service import SeedService

router = APIRouter(prefix="/demo", tags=["Demo & Adversarial Testing"])


@router.post("/seed")
def seed_demo_applications(
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission("upload")),
):
    """Preloads Demo Cases A (APP-00016), B (APP-00017), and C (APP-00018)."""
    SeedService.seed_all_demo_data(db)
    return {"message": "Demo data successfully seeded for APP-00016, APP-00017, and APP-00018."}


@router.post("/reset")
def reset_demo_database(
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission("override")),
):
    """Resets demo applications to clean state."""
    # Delete existing applications and cascade explicitly in leaf-to-root order
    db.query(ReviewAction).delete()
    db.query(DecisionRuleResult).delete()
    db.query(Decision).delete()
    db.query(ExtractedField).delete()
    db.query(OCRToken).delete()
    db.query(OCRPage).delete()
    db.query(Document).delete()
    db.query(AuditLogEntry).delete()
    db.query(Application).delete()
    db.commit()

    # Re-seed
    SeedService.seed_all_demo_data(db)
    return {"message": "Demo database successfully reset and re-seeded with fresh hash chains."}


@router.post("/tamper/{application_ref}")
def simulate_adversarial_tampering(
    application_ref: str,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission("override")),
):
    """
    Adversarial Test #6:
    Intentionally modifies the payload of an audit log entry in the database
    to prove that the audit verification endpoint immediately detects tampering.
    """
    app = db.query(Application).filter(
        (Application.id == application_ref) | (Application.public_reference == application_ref)
    ).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found.")

    entry = db.query(AuditLogEntry).filter(
        AuditLogEntry.application_id == app.id,
        AuditLogEntry.action_type.in_(["FIELD_VALIDATED", "RULE_EVALUATED", "DECISION_CREATED"])
    ).first()

    if not entry:
        raise HTTPException(status_code=404, detail="No eligible audit log entry found to tamper.")

    # Tamper payload silently without updating hash or HMAC
    tampered_payload = dict(entry.payload)
    tampered_payload["TAMPERED_BY_ATTACKER"] = True
    tampered_payload["illegal_modifier"] = "999999"
    entry.payload = tampered_payload
    flag_modified(entry, "payload")

    db.commit()

    return {
        "message": f"Successfully simulated unauthorized payload tampering on entry {entry.id} ({entry.action_type}).",
        "entry_id": entry.id,
        "action_type": entry.action_type,
        "note": "Calling /api/audit/verify will now detect this altered entry and return verified: false."
    }
