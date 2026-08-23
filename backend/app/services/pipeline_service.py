"""
End-to-End Decision Pipeline Service for Project Synapse.
Orchestrates:
  Document Fetch -> OCR (Tesseract) -> Gemini Extraction -> Evidence Linking ->
  Deterministic Validation -> Python Rules Evaluator -> Decision -> Audit Chain
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from app.db.models import (
    Application,
    Document,
    OCRPage,
    OCRToken,
    ExtractedField,
    Decision,
    DecisionRuleResult,
)
from app.schemas.validation import ValidatedField, FieldTrustStatus
from app.schemas.decision import DecisionOutcome, DecisionMode
from app.services.ocr_service import process_document as run_ocr
from app.services.extraction_service import extract_fields as run_gemini_extraction
from app.services.evidence_service import validate_fields as run_evidence_validation
from app.services.rules_service import RulesEvaluator
from app.services.audit_service import AuditService

logger = logging.getLogger(__name__)


class PipelineService:
    """
    Orchestrates the synchronous verification and decision generation pipeline.
    """

    @staticmethod
    def process_application(
        db: Session,
        application_id: str,
        actor_id: str = "processor-001",
        policy_version: str = "CSSS-Demo-v1.0",
    ) -> Dict[str, Any]:
        app: Optional[Application] = db.query(Application).filter(Application.id == application_id).first()
        if not app:
            raise ValueError(f"Application {application_id} not found.")

        if not app.documents:
            raise ValueError(f"Application {app.public_reference} has no uploaded documents to process.")

        # Step 1: Run OCR on all uploaded documents
        all_validated_fields: List[ValidatedField] = []
        uploaded_doc_types = [d.doc_type for d in app.documents]

        for doc in app.documents:
            try:
                ocr_result = run_ocr(doc.storage_path)

                # Persist OCR Pages and Tokens
                # Clear previous OCR data for this doc if re-processing
                db.query(OCRPage).filter(OCRPage.document_id == doc.id).delete()
                
                total_tokens_count = 0
                for page in ocr_result.pages:
                    db_page = OCRPage(
                        document_id=doc.id,
                        page_number=page.page_number,
                        raw_text=page.page_text,
                        width=page.width_px,
                        height=page.height_px,
                    )
                    db.add(db_page)
                    db.flush()

                    for t in page.tokens:
                        db_token = OCRToken(
                            ocr_page_id=db_page.id,
                            token=t.token,
                            left=t.left,
                            top=t.top,
                            width=t.width,
                            height=t.height,
                            confidence=t.confidence,
                            line_no=t.line_no,
                            block_no=t.block_no,
                        )
                        db.add(db_token)
                        total_tokens_count += 1

                # Audit OCR_COMPLETED
                AuditService.append_audit_event(
                    db=db,
                    application_id=app.id,
                    action_type="OCR_COMPLETED",
                    actor_id=actor_id,
                    payload={
                        "document_id": doc.id,
                        "file_name": doc.file_name,
                        "pages_count": len(ocr_result.pages),
                        "tokens_count": total_tokens_count,
                        "mean_confidence": round(ocr_result.overall_mean_confidence, 3),
                    }
                )

                # Step 2: Gemini extraction
                candidates = run_gemini_extraction(
                    ocr_result,
                    application_public_reference=app.public_reference
                )

                AuditService.append_audit_event(
                    db=db,
                    application_id=app.id,
                    action_type="EXTRACTION_COMPLETED",
                    actor_id=actor_id,
                    payload={
                        "document_id": doc.id,
                        "extracted_count": len(candidates),
                        "model": "gemini-flash",
                    }
                )

                # Step 3: Evidence linking & validation
                validated_fields = run_evidence_validation(candidates, ocr_result)
                all_validated_fields.extend(validated_fields)

            except Exception as exc:
                logger.error("Error processing document %s: %s", doc.id, exc)
                # Continue or propagate depending on failure
                raise

        # Step 4: Persist Extracted Fields
        db.query(ExtractedField).filter(ExtractedField.application_id == app.id).delete()
        
        # Aggregate unique fields (in case of multiple docs)
        fields_map: Dict[str, ValidatedField] = {}
        for vf in all_validated_fields:
            fname = vf.field_name.value if hasattr(vf.field_name, "value") else str(vf.field_name)
            # Prefer VALIDATED over UNTRUSTED
            if fname not in fields_map or vf.status == FieldTrustStatus.VALIDATED:
                fields_map[fname] = vf

        for fname, vf in fields_map.items():
            bbox_dict = None
            if vf.bounding_box:
                bbox_dict = {
                    "x": vf.bounding_box.x,
                    "y": vf.bounding_box.y,
                    "width": vf.bounding_box.width,
                    "height": vf.bounding_box.height,
                }

            db_field = ExtractedField(
                application_id=app.id,
                field_name=fname,
                raw_value_text=str(vf.normalized_value) if vf.normalized_value is not None else None,
                normalized_value=vf.normalized_value,
                status=vf.status.value,
                validation_status=vf.validation_status.value,
                ocr_confidence=vf.ocr_confidence,
                evidence_match_score=vf.evidence_match_score,
                model_confidence=vf.model_confidence,
                final_confidence=vf.final_confidence,
                evidence_quote=vf.evidence_quote,
                source_page=vf.source_page,
                bounding_box=bbox_dict,
            )
            db.add(db_field)

            # Audit FIELD_VALIDATED
            AuditService.append_audit_event(
                db=db,
                application_id=app.id,
                action_type="FIELD_VALIDATED",
                actor_id=actor_id,
                payload={
                    "field_name": fname,
                    "status": vf.status.value,
                    "validation_status": vf.validation_status.value,
                    "final_confidence": vf.final_confidence,
                    "normalized_value": vf.normalized_value,
                }
            )

        # Step 5: Deterministic Python Rules Evaluation
        evaluator = RulesEvaluator(policy_version=policy_version)
        rule_results, outcome, confidence_summary = evaluator.evaluate_rules(
            fields_map=fields_map,
            uploaded_doc_types=uploaded_doc_types
        )

        for rr in rule_results:
            AuditService.append_audit_event(
                db=db,
                application_id=app.id,
                action_type="RULE_EVALUATED",
                actor_id=actor_id,
                payload={
                    "rule_code": rr.rule_code,
                    "result": rr.result.value,
                    "explanation": rr.explanation,
                    "input_snapshot": rr.input_snapshot,
                    "policy_version": rr.policy_version,
                }
            )

        # Step 6: Create Decision v1 (AUTOMATED)
        new_decision = Decision(
            application_id=app.id,
            decision_version=1,
            outcome=outcome.value,
            decision_mode=DecisionMode.AUTOMATED.value,
            policy_version=policy_version,
            confidence_summary=confidence_summary,
            supersedes_decision_id=None,
            is_final=False,
        )
        db.add(new_decision)
        db.flush()

        for rr in rule_results:
            db_rr = DecisionRuleResult(
                decision_id=new_decision.id,
                rule_code=rr.rule_code,
                result=rr.result.value,
                input_snapshot=rr.input_snapshot,
                explanation=rr.explanation,
                policy_version=rr.policy_version,
            )
            db.add(db_rr)

        # Update application status
        if outcome == DecisionOutcome.NEEDS_REVIEW:
            app.status = "NEEDS_REVIEW"
        else:
            app.status = "AUTO_DECISION"

        # Update applicant name if extracted
        if "student_name" in fields_map and fields_map["student_name"].normalized_value:
            app.applicant_name = str(fields_map["student_name"].normalized_value)

        # Audit DECISION_CREATED
        AuditService.append_audit_event(
            db=db,
            application_id=app.id,
            action_type="DECISION_CREATED",
            actor_id=actor_id,
            payload={
                "decision_id": new_decision.id,
                "decision_version": 1,
                "outcome": outcome.value,
                "decision_mode": DecisionMode.AUTOMATED.value,
                "policy_version": policy_version,
                "confidence_summary": confidence_summary,
            }
        )

        db.commit()
        db.refresh(app)
        db.refresh(new_decision)

        return {
            "application_id": app.id,
            "public_reference": app.public_reference,
            "status": app.status,
            "outcome": outcome.value,
            "decision_version": new_decision.decision_version,
            "confidence_summary": confidence_summary,
            "rules_count": len(rule_results),
        }
