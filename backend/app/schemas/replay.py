"""
Pydantic schemas for Decision Replay reconstruction.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.schemas.decision import DecisionDetailResponse, RuleResultSchema
from app.schemas.validation import ValidatedField
from app.schemas.audit import AuditVerifyResponse, AuditLogEntryResponse
from app.schemas.application import DocumentResponse


class ReplayTimelineItem(BaseModel):
    id: str
    action_type: str
    actor_id: str
    occurred_at: str
    entry_hash: str
    previous_entry_hash: str
    entry_hmac: str
    summary: str
    payload: Dict[str, Any]
    snapshot: Optional[Dict[str, Any]] = None


class DecisionVersionSnapshot(BaseModel):
    decision_version: int
    outcome: str
    decision_mode: str
    policy_version: str
    confidence_summary: Dict[str, Any]
    rule_results: List[RuleResultSchema] = []
    created_at: datetime
    supersedes_decision_id: Optional[str] = None


class ApplicationReplayResponse(BaseModel):
    application_id: str
    public_reference: str
    applicant_name: Optional[str] = None
    scheme_code: str
    current_status: str
    current_policy_version: str
    latest_decision: Optional[DecisionDetailResponse] = None
    audit_chain_verification: AuditVerifyResponse
    documents: List[DocumentResponse] = []
    extracted_fields: List[ValidatedField] = []
    decision_history: List[DecisionVersionSnapshot] = []
    timeline: List[ReplayTimelineItem] = []
