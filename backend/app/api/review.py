"""
Human Review & Override API Endpoints.
Implements single-transaction review actions, field overrides, and immutable decision versioning.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, require_permission
from app.db.session import get_db
from app.db.models import Application, Decision, DecisionRuleResult, ExtractedField, ReviewAction
from app.schemas.review import (
    BulkReviewSubmitRequest,
    ReviewActionCreate,
    ReviewActionResponse,
)
from app.schemas.decision import DecisionDetailResponse, RuleResultSchema
from app.schemas.validation import ValidatedField, BoundingBox, FieldTrustStatus, ValidationStatus
from app.services.audit_service import AuditService
from app.services.rules_service import RulesEvaluator

router = APIRouter(prefix="/applications", tags=["Review & Overrides"])


@router.get("/{id}/review-actions", response_model=List[ReviewActionResponse])
def get_review_actions(
    id: str,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission("view")),
):
    """Lists all historical review and override actions performed on an application."""
    app = db.query(Application).filter(
        (Application.id == id) | (Application.public_reference == id)
    ).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found.")

    return db.query(ReviewAction).filter(ReviewAction.application_id == app.id).order_by(ReviewAction.created_at.asc()).all()


@router.post("/{id}/review-actions", response_model=DecisionDetailResponse)
def submit_review_action(
    id: str,
    payload: BulkReviewSubmitRequest,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission("override")),
):
    """
    Executes a human reviewer override in ONE atomic DB transaction:
      1. Records ReviewAction rows with mandatory reason
      2. Updates field values in extracted_fields with status=OVERRIDDEN
      3. Appends FIELD_OVERRIDDEN audit event to hash chain
      4. Re-evaluates deterministic policy rules (pure Python)
      5. Creates Decision v(N+1) with supersedes_decision_id pointing to previous version
      6. Appends DECISION_VERSION_CREATED audit event
      7. Updates Application status to HUMAN_CONFIRMED
    """
    app = db.query(Application).filter(
        (Application.id == id) | (Application.public_reference == id)
    ).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found.")

    # Find current latest decision
    latest_decision = db.query(Decision).filter(
        Decision.application_id == app.id
    ).order_by(Decision.decision_version.desc()).first()

    current_version = latest_decision.decision_version if latest_decision else 0
    new_version = current_version + 1
    previous_decision_id = latest_decision.id if latest_decision else None

    # Emit REVIEW_STARTED if not already started
    AuditService.append_audit_event(
        db=db,
        action_type="REVIEW_STARTED",
        payload={
            "application_id": app.id,
            "reviewer_id": user.user_id,
            "reason": payload.reason,
        },
        actor_id=user.user_id,
        application_id=app.id,
    )

    # Process field overrides
    for ov in payload.overrides:
        field_row = db.query(ExtractedField).filter(
            ExtractedField.application_id == app.id,
            ExtractedField.field_name == ov.field_name,
        ).first()

        old_val = field_row.normalized_value if field_row else None
        
        if field_row:
            field_row.normalized_value = ov.new_value
            field_row.status = "OVERRIDDEN"
            field_row.validation_status = "VALID"
            field_row.final_confidence = 1.0
        else:
            field_row = ExtractedField(
                application_id=app.id,
                field_name=ov.field_name,
                normalized_value=ov.new_value,
                status="OVERRIDDEN",
                validation_status="VALID",
                ocr_confidence=1.0,
                evidence_match_score=1.0,
                model_confidence=1.0,
                final_confidence=1.0,
            )
            db.add(field_row)

        # Record ReviewAction
        action = ReviewAction(
            application_id=app.id,
            decision_id=previous_decision_id,
            actor_id=user.user_id,
            action_type="FIELD_OVERRIDDEN",
            field_name=ov.field_name,
            old_value=old_val,
            new_value=ov.new_value,
            reason=ov.reason,
        )
        db.add(action)

        # Append FIELD_OVERRIDDEN audit event
        AuditService.append_audit_event(
            db=db,
            action_type="FIELD_OVERRIDDEN",
            payload={
                "field": ov.field_name,
                "old_value": old_val,
                "new_value": ov.new_value,
                "reason": ov.reason,
            },
            actor_id=user.user_id,
            application_id=app.id,
        )

    db.flush()

    # Re-build validated fields map for rule evaluator
    all_fields = db.query(ExtractedField).filter(ExtractedField.application_id == app.id).all()
    fields_map: Dict[str, ValidatedField] = {}
    for ef in all_fields:
        bbox = None
        if ef.bounding_box and isinstance(ef.bounding_box, dict):
            bbox = BoundingBox(
                x=ef.bounding_box.get("x", 0),
                y=ef.bounding_box.get("y", 0),
                width=ef.bounding_box.get("width", 0),
                height=ef.bounding_box.get("height", 0),
            )
        fields_map[ef.field_name] = ValidatedField(
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

    uploaded_doc_types = [d.doc_type for d in app.documents]
    policy_ver = latest_decision.policy_version if latest_decision else "CSSS-Demo-v1.0"

    evaluator = RulesEvaluator(policy_version=policy_ver)
    rule_results, outcome, confidence_summary = evaluator.evaluate_rules(
        fields_map=fields_map,
        uploaded_doc_types=uploaded_doc_types,
    )

    # If reviewer explicitly forced an outcome override, respect it
    if payload.decision_override in ["ELIGIBLE", "INELIGIBLE", "NEEDS_REVIEW"]:
        decision_outcome = payload.decision_override
    else:
        decision_outcome = outcome.value

    # Create Decision v(N+1)
    new_dec = Decision(
        application_id=app.id,
        decision_version=new_version,
        outcome=decision_outcome,
        decision_mode="HUMAN_CONFIRMED" if not payload.decision_override else "HUMAN_OVERRIDDEN",
        policy_version=policy_ver,
        confidence_summary=confidence_summary,
        supersedes_decision_id=previous_decision_id,
        is_final=True,
    )
    db.add(new_dec)
    db.flush()

    for rr in rule_results:
        db_rr = DecisionRuleResult(
            decision_id=new_dec.id,
            rule_code=rr.rule_code,
            result=rr.result.value,
            input_snapshot=rr.input_snapshot,
            explanation=rr.explanation,
            policy_version=rr.policy_version,
        )
        db.add(db_rr)

    # Update app status
    app.status = "HUMAN_CONFIRMED"

    # Append DECISION_VERSION_CREATED audit event
    AuditService.append_audit_event(
        db=db,
        action_type="DECISION_VERSION_CREATED",
        payload={
            "decision_id": new_dec.id,
            "decision_version": new_version,
            "outcome": decision_outcome,
            "decision_mode": new_dec.decision_mode,
            "policy_version": policy_ver,
            "supersedes_decision_id": previous_decision_id,
            "reason": payload.reason,
        },
        actor_id=user.user_id,
        application_id=app.id,
    )

    # Append FINALIZED audit event
    AuditService.append_audit_event(
        db=db,
        action_type="FINALIZED",
        payload={
            "final_decision_id": new_dec.id,
            "outcome": decision_outcome,
            "decision_version": new_version,
            "actor": user.user_id,
        },
        actor_id=user.user_id,
        application_id=app.id,
    )

    db.commit()
    db.refresh(new_dec)

    return DecisionDetailResponse(
        id=new_dec.id,
        application_id=new_dec.application_id,
        decision_version=new_dec.decision_version,
        outcome=new_dec.outcome,
        decision_mode=new_dec.decision_mode,
        policy_version=new_dec.policy_version,
        confidence_summary=new_dec.confidence_summary or {},
        supersedes_decision_id=new_dec.supersedes_decision_id,
        is_final=new_dec.is_final,
        created_at=new_dec.created_at,
        rule_results=[
            RuleResultSchema(
                rule_code=rr.rule_code,
                result=rr.result,
                input_snapshot=rr.input_snapshot,
                explanation=rr.explanation,
                policy_version=rr.policy_version,
            )
            for rr in new_dec.rule_results
        ],
    )
