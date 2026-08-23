"""
Pydantic schemas for Audit Log and Verification.
Matches docs/contracts/audit_event.json.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class AuditActionType(str, Enum):
    """Audit event action_type from docs/CONVENTIONS.md."""
    APPLICATION_CREATED = "APPLICATION_CREATED"
    DOCUMENT_UPLOADED = "DOCUMENT_UPLOADED"
    OCR_COMPLETED = "OCR_COMPLETED"
    EXTRACTION_COMPLETED = "EXTRACTION_COMPLETED"
    FIELD_VALIDATED = "FIELD_VALIDATED"
    RULE_EVALUATED = "RULE_EVALUATED"
    DECISION_CREATED = "DECISION_CREATED"
    REVIEW_STARTED = "REVIEW_STARTED"
    FIELD_OVERRIDDEN = "FIELD_OVERRIDDEN"
    DECISION_VERSION_CREATED = "DECISION_VERSION_CREATED"
    FINALIZED = "FINALIZED"


class AuditEventContract(BaseModel):
    """Matches docs/contracts/audit_event.json."""
    model_config = ConfigDict(from_attributes=True)

    action_type: str
    payload: Dict[str, Any]
    actor_id: str
    occurred_at: str
    previous_entry_hash: str
    entry_hash: str
    entry_hmac: str


class AuditLogEntryResponse(AuditEventContract):
    id: str
    application_id: Optional[str] = None


class BrokenAuditEntry(BaseModel):
    index: int
    entry_id: str
    action_type: str
    expected_hash: str
    actual_hash: str
    expected_hmac: str
    actual_hmac: str
    reason: str


class AuditVerifyRequest(BaseModel):
    application_id: Optional[str] = None


class AuditVerifyResponse(BaseModel):
    verified: bool
    total_entries: int
    first_broken_entry: Optional[BrokenAuditEntry] = None
    message: str
