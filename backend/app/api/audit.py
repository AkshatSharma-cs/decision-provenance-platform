"""
Audit Log Verification API Endpoints.
Provides cryptographic validation of the SHA-256 hash chain and HMAC signatures.
"""

from __future__ import annotations

from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, require_permission
from app.db.session import get_db
from app.db.models import AuditLogEntry, Application
from app.schemas.audit import AuditVerifyRequest, AuditVerifyResponse, AuditLogEntryResponse
from app.services.audit_service import AuditService, _order_chain_entries

router = APIRouter(prefix="/audit", tags=["Audit & Cryptography"])


@router.get("", response_model=List[AuditLogEntryResponse])
def get_audit_log(
    application_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission("view")),
):
    """Returns chronological audit log entries, optionally filtered by application ID."""
    query = db.query(AuditLogEntry)
    if application_id:
        # Check if application_id is UUID or public_reference
        app = db.query(Application).filter(
            (Application.id == application_id) | (Application.public_reference == application_id)
        ).first()
        target_id = app.id if app else application_id
        query = query.filter(AuditLogEntry.application_id == target_id)
    
    entries = query.all()
    ordered = _order_chain_entries(entries)
    return ordered


@router.get("/verify", response_model=AuditVerifyResponse, include_in_schema=False)
@router.post("/verify", response_model=AuditVerifyResponse)
def verify_audit_trail(
    payload: Optional[AuditVerifyRequest] = None,
    application_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission("verify_audit")),
):
    """
    Cryptographically verifies the linear SHA-256 hash chain and HMAC-SHA256 signatures.
    Returns:
      - verified: true if all hashes & signatures match in exact sequence
      - first_broken_entry: details of the exact tampered entry if broken
    """
    app_id = (payload.application_id if payload else None) or application_id
    if app_id:
        app = db.query(Application).filter(
            (Application.id == app_id) | (Application.public_reference == app_id)
        ).first()
        if app:
            app_id = app.id

    return AuditService.verify_audit_chain(db, application_id=app_id)
