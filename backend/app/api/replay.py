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


from typing import Any, Dict, List, Optional
from app.db.models import Application, Decision, ExtractedField
from app.schemas.validation import ValidatedField, BoundingBox, FieldTrustStatus, ValidationStatus
from app.services.rules_service import RulesEvaluator


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


@router.post("/{id}/replay")
def simulate_policy_replay(
    id: str,
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission("view")),
):
    """
    Counterfactual Policy Replay:
    Simulates evaluating the application's frozen evidence against a target policy version.
    """
    app = db.query(Application).filter(
        (Application.id == id) | (Application.public_reference == id)
    ).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found.")

    target_policy_version = payload.get("target_policy_version", "CSSS-Demo-v1.1")

    # Latest decision
    latest_decision = db.query(Decision).filter(
        Decision.application_id == app.id
    ).order_by(Decision.decision_version.desc()).first()

    original_policy_version = latest_decision.policy_version if latest_decision else "CSSS-Demo-v1.0"
    original_outcome = latest_decision.outcome if latest_decision else "NEEDS_REVIEW"

    # Build fields map
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

    # Evaluate target policy
    evaluator = RulesEvaluator(policy_version=target_policy_version)
    simulated_rules, simulated_outcome_enum, _ = evaluator.evaluate_rules(
        fields_map=fields_map,
        uploaded_doc_types=uploaded_doc_types,
    )
    simulated_outcome = simulated_outcome_enum.value

    # Build comparison
    orig_rule_map = {}
    if latest_decision:
        for rr in latest_decision.rule_results:
            orig_rule_map[rr.rule_code] = rr.result

    comparison = []
    for sr in simulated_rules:
        orig_res = orig_rule_map.get(sr.rule_code, "UNKNOWN")
        sim_res = sr.result.value
        comparison.append({
            "rule_code": sr.rule_code,
            "original_result": orig_res,
            "simulated_result": sim_res,
            "changed": orig_res != sim_res,
            "explanation": sr.explanation,
        })

    return {
        "application_id": app.id,
        "original_policy_version": original_policy_version,
        "target_policy_version": target_policy_version,
        "original_outcome": original_outcome,
        "simulated_outcome": simulated_outcome,
        "outcome_changed": original_outcome != simulated_outcome,
        "comparison": comparison,
    }
