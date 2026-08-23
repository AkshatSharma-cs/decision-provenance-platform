"""
Audit Log Verification API Endpoints.
Provides cryptographic validation of the SHA-256 hash chain and HMAC signatures.
"""

from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, require_permission
from app.db.session import get_db
from app.schemas.audit import AuditVerifyRequest, AuditVerifyResponse
from app.services.audit_service import AuditService

router = APIRouter(prefix="/audit", tags=["Audit & Cryptography"])


@router.post("/verify", response_model=AuditVerifyResponse)
def verify_audit_trail(
    payload: Optional[AuditVerifyRequest] = None,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission("verify_audit")),
):
    """
    Cryptographically verifies the linear SHA-256 hash chain and HMAC-SHA256 signatures.
    Returns:
      - verified: true if all hashes & signatures match in exact sequence
      - first_broken_entry: details of the exact tampered entry if broken
    """
    app_id = payload.application_id if payload else None
    return AuditService.verify_audit_chain(db, application_id=app_id)
