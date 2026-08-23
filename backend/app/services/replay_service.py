"""
Historical Decision Replay Service.
Reconstructs exact historical decision states from stored immutable snapshots without re-running live rules.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from app.db.models import Application, Decision, Document, ExtractedField, AuditLogEntry, ReviewAction
from app.schemas.replay import (
    ApplicationReplayResponse,
    DecisionVersionSnapshot,
    ReplayTimelineItem,
)
from app.schemas.decision import DecisionDetailResponse, RuleResultSchema
from app.schemas.validation import ValidatedField, BoundingBox, FieldTrustStatus, ValidationStatus
from app.schemas.application import DocumentResponse
from app.services.audit_service import AuditService


class ReplayService:
    """
    Reconstructs the full decision journey from immutable database records.
    """

    @staticmethod
    def reconstruct_replay(db: Session, application_id: str) -> Optional[ApplicationReplayResponse]:
        app: Optional[Application] = db.query(Application).filter(Application.id == application_id).first()
        if not app:
            return None

        # Verify audit chain for this application
        verification = AuditService.verify_audit_chain(db, application_id=application_id)

        # 1. Documents
        docs_res = [
            DocumentResponse(
                id=d.id,
                application_id=d.application_id,
                doc_type=d.doc_type,
                file_name=d.file_name,
                file_size=d.file_size,
                mime_type=d.mime_type,
                file_hash=d.file_hash,
                created_at=d.created_at,
            )
            for d in app.documents
        ]

        # 2. Extracted Fields
        fields_res: List[ValidatedField] = []
        for ef in app.extracted_fields:
            bbox = None
            if ef.bounding_box and isinstance(ef.bounding_box, dict):
                bbox = BoundingBox(
                    x=ef.bounding_box.get("x", 0),
                    y=ef.bounding_box.get("y", 0),
                    width=ef.bounding_box.get("width", 0),
                    height=ef.bounding_box.get("height", 0),
                )
            fields_res.append(
                ValidatedField(
                    field_name=ef.field_name,
                    normalized_value=ef.normalized_value,
                    status=FieldTrustStatus(ef.status),
                    validation_status=ValidationStatus(ef.validation_status),
                    ocr_confidence=ef.ocr_confidence,
                    evidence_match_score=ef.evidence_match_score,
                    model_confidence=ef.model_confidence,
                    final_confidence=ef.final_confidence,
                    evidence_quote=ef.evidence_quote,
                    source_page=ef.source_page,
                    bounding_box=bbox,
                )
            )

        # 3. Decision History
        decision_history: List[DecisionVersionSnapshot] = []
        for d in app.decisions:
            rule_res = [
                RuleResultSchema(
                    rule_code=rr.rule_code,
                    result=rr.result,
                    input_snapshot=rr.input_snapshot,
                    explanation=rr.explanation,
                    policy_version=rr.policy_version,
                )
                for rr in d.rule_results
            ]
            decision_history.append(
                DecisionVersionSnapshot(
                    decision_version=d.decision_version,
                    outcome=d.outcome,
                    decision_mode=d.decision_mode,
                    policy_version=d.policy_version,
                    confidence_summary=d.confidence_summary or {},
                    rule_results=rule_res,
                    created_at=d.created_at,
                    supersedes_decision_id=d.supersedes_decision_id,
                )
            )

        # Latest decision
        latest_decision_obj = app.decisions[-1] if app.decisions else None
        latest_decision = None
        if latest_decision_obj:
            latest_decision = DecisionDetailResponse(
                id=latest_decision_obj.id,
                application_id=latest_decision_obj.application_id,
                decision_version=latest_decision_obj.decision_version,
                outcome=latest_decision_obj.outcome,
                decision_mode=latest_decision_obj.decision_mode,
                policy_version=latest_decision_obj.policy_version,
                confidence_summary=latest_decision_obj.confidence_summary or {},
                supersedes_decision_id=latest_decision_obj.supersedes_decision_id,
                is_final=latest_decision_obj.is_final,
                created_at=latest_decision_obj.created_at,
                rule_results=[
                    RuleResultSchema(
                        rule_code=rr.rule_code,
                        result=rr.result,
                        input_snapshot=rr.input_snapshot,
                        explanation=rr.explanation,
                        policy_version=rr.policy_version,
                    )
                    for rr in latest_decision_obj.rule_results
                ],
            )

        # 4. Timeline
        timeline: List[ReplayTimelineItem] = []
        for entry in app.audit_entries:
            summary = ReplayService._generate_summary(entry.action_type, entry.payload)
            timeline.append(
                ReplayTimelineItem(
                    id=entry.id,
                    action_type=entry.action_type,
                    actor_id=entry.actor_id,
                    occurred_at=entry.occurred_at,
                    entry_hash=entry.entry_hash,
                    previous_entry_hash=entry.previous_entry_hash,
                    entry_hmac=entry.entry_hmac,
                    summary=summary,
                    payload=entry.payload,
                    snapshot=entry.payload.get("snapshot") or entry.payload,
                )
            )

        policy_ver = latest_decision.policy_version if latest_decision else "CSSS-Demo-v1.0"

        return ApplicationReplayResponse(
            application_id=app.id,
            public_reference=app.public_reference,
            applicant_name=app.applicant_name,
            scheme_code=app.scheme_code,
            current_status=app.status,
            current_policy_version=policy_ver,
            latest_decision=latest_decision,
            audit_chain_verification=verification,
            documents=docs_res,
            extracted_fields=fields_res,
            decision_history=decision_history,
            timeline=timeline,
        )

    @staticmethod
    def _generate_summary(action_type: str, payload: Dict[str, Any]) -> str:
        if action_type == "APPLICATION_CREATED":
            ref = payload.get("public_reference", "")
            return f"Application {ref} created and registered in scheme."
        elif action_type == "DOCUMENT_UPLOADED":
            fname = payload.get("file_name", "document")
            h = payload.get("file_hash", "")[:12]
            return f"Document '{fname}' uploaded (SHA-256: {h}...)."
        elif action_type == "OCR_COMPLETED":
            pages = payload.get("pages_count", 1)
            tokens = payload.get("tokens_count", 0)
            return f"Tesseract OCR extracted {pages} page(s) and {tokens} word tokens."
        elif action_type == "EXTRACTION_COMPLETED":
            cnt = payload.get("extracted_count", 0)
            return f"Gemini extracted {cnt} candidate fields with direct evidence quotations."
        elif action_type == "FIELD_VALIDATED":
            field = payload.get("field_name", "")
            status = payload.get("status", "")
            return f"Field '{field}' validated with status {status}."
        elif action_type == "RULE_EVALUATED":
            rule = payload.get("rule_code", "")
            res = payload.get("result", "")
            return f"Policy rule '{rule}' evaluated: {res}."
        elif action_type == "DECISION_CREATED":
            outcome = payload.get("outcome", "")
            v = payload.get("decision_version", 1)
            return f"Decision v{v} produced outcome: {outcome}."
        elif action_type == "FIELD_OVERRIDDEN":
            field = payload.get("field", "")
            old_val = payload.get("old_value", "")
            new_val = payload.get("new_value", "")
            return f"Reviewer modified '{field}' from {old_val} to {new_val}."
        elif action_type == "DECISION_VERSION_CREATED":
            v = payload.get("decision_version", 2)
            outcome = payload.get("outcome", "")
            return f"New Decision v{v} generated with outcome: {outcome}."
        elif action_type == "FINALIZED":
            return "Application status finalized."
        return f"Event {action_type} recorded in audit log."
