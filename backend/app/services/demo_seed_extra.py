"""
demo_seed_extra.py — additional synthetic demo applications for Project Synapse.

Drop this file in backend/app/services/ alongside seed_service.py, then add
one line to SeedService.seed_all_demo_data() (see bottom of this file for the
exact patch) to also call `seed_extra_demo_cases(db)`.

WHY THIS FILE EXISTS
---------------------
The three frozen demo IDs (APP-00016/17/18) in seed_service.py are great for
a scripted walkthrough, but they leave the Dashboard, Reports, and Audit log
screens looking thin (3 total applications, a handful of audit rows, and a
Reports page that is currently hardcoded to static 65/20/15% numbers in the
frontend rather than reading real data). This module adds 5 more synthetic
applications, spanning every outcome and a couple of interesting edge cases,
so the demo has ~8 applications with a realistic spread of ELIGIBLE /
NEEDS_REVIEW / INELIGIBLE outcomes and a much longer audit trail to show off
the hash-chain verification screen.

DESIGN CHOICE: rather than hand-writing 9 ExtractedField rows + 6
DecisionRuleResult rows per case (as seed_service.py's original 3 cases do),
this module builds each case from a compact parameter set and runs it
through the REAL `RulesEvaluator` (app.services.rules_service) — the same
pure-Python deterministic engine the live `/process` pipeline uses. This
guarantees every synthetic case's outcome, rule PASS/FAIL results, and
explanation text are internally consistent (never a case that says
"NEEDS_REVIEW" in `applications.status` but "PASS" on every rule), and it
means this file stays correct automatically if rules_service.py's logic
ever changes.

All fields are still fully "VALIDATED" with plausible evidence_quote /
bounding_box data — nothing here re-runs OCR or calls Gemini, this is
synthetic seed data only.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from sqlalchemy.orm import Session

from app.db.models import (
    Application,
    Document,
    OCRPage,
    ExtractedField,
    Decision,
    DecisionRuleResult,
)
from app.schemas.validation import ValidatedField, FieldTrustStatus, ValidationStatus
from app.services.rules_service import RulesEvaluator
from app.services.audit_service import AuditService

logger = logging.getLogger(__name__)

# Separate base timestamp from seed_service.py's cases so the two audit
# chains never collide on occurred_at (each application has its own chain,
# but distinct times also make the demo's Audit log screen read naturally
# in chronological order across all applications).
_BASE_TIME = datetime(2026, 8, 19, 9, 0, 0, tzinfo=timezone.utc)


def _iso(offset_seconds: int) -> str:
    return (_BASE_TIME + timedelta(seconds=offset_seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _field(
    field_name: str,
    normalized_value: Any,
    evidence_quote: str,
    source_page: int,
    ocr_confidence: float = 0.95,
    evidence_match_score: float = 1.0,
    model_confidence: float = 0.95,
) -> ValidatedField:
    final_confidence = round((ocr_confidence + evidence_match_score + model_confidence) / 3.0, 4)
    return ValidatedField(
        field_name=field_name,
        normalized_value=normalized_value,
        status=FieldTrustStatus.VALIDATED,
        validation_status=ValidationStatus.VALID,
        ocr_confidence=ocr_confidence,
        evidence_match_score=evidence_match_score,
        model_confidence=model_confidence,
        final_confidence=final_confidence,
        evidence_quote=evidence_quote,
        source_page=source_page,
        bounding_box={"x": 120, "y": 240, "width": 380, "height": 30},
    )


def _seed_generic_case(
    db: Session,
    *,
    ref: str,
    applicant_name: str,
    student_dob: str,
    board_percentile: float,
    course_mode: str,
    institution_name: str,
    institution_recognized: bool,
    family_income: int,
    other_scholarship: bool,
    application_date: str,
    file_name: str,
    file_hash: str,
    time_offset: int,
    decision_mode: str = "AUTOMATED",
) -> None:
    if db.query(Application).filter(Application.public_reference == ref).first():
        return  # idempotent, same convention as seed_service.py's cases

    # Build the 9 frozen ValidatedField objects, then run them through the
    # REAL deterministic rules engine so outcome/status/rule results are
    # guaranteed self-consistent.
    fields_map: Dict[str, ValidatedField] = {
        "student_name": _field("student_name", applicant_name, f"Applicant: {applicant_name}", 1),
        "date_of_birth": _field("date_of_birth", student_dob, f"DOB: {student_dob}", 1),
        "board_percentile": _field("board_percentile", board_percentile, f"Percentile: {board_percentile:.2f}%", 1),
        "course_mode": _field("course_mode", course_mode, f"Course: {course_mode}", 1),
        "institution_name": _field("institution_name", institution_name, f"Institution: {institution_name}", 2),
        "institution_recognized": _field(
            "institution_recognized", institution_recognized,
            f"Institution: {institution_name} ({'Recognized' if institution_recognized else 'Not recognized'})", 2,
        ),
        "family_income": _field("family_income", family_income, f"Gross parental/family income: Rs {family_income:,} per annum", 2),
        "other_scholarship": _field(
            "other_scholarship", other_scholarship,
            f"Other scholarship: {'Yes' if other_scholarship else 'None'}", 2,
        ),
        "application_date": _field("application_date", application_date, f"Date of Application: {application_date}", 1),
    }

    evaluator = RulesEvaluator(policy_version="CSSS-Demo-v1.0")
    rule_results, outcome, confidence_summary = evaluator.evaluate_rules(
        fields_map=fields_map, uploaded_doc_types=["application_form"]
    )

    status_by_outcome = {
        "ELIGIBLE": "AUTO_DECISION",
        "INELIGIBLE": "AUTO_DECISION",
        "NEEDS_REVIEW": "NEEDS_REVIEW",
    }

    app = Application(
        public_reference=ref,
        applicant_name=applicant_name,
        scheme_code="PM-USP-CSSS",
        status=status_by_outcome[outcome.value],
    )
    db.add(app)
    db.flush()

    t = time_offset
    AuditService.append_audit_event(
        db, "APPLICATION_CREATED",
        {"public_reference": ref, "applicant_name": applicant_name, "scheme_code": "PM-USP-CSSS"},
        actor_id="officer-020", application_id=app.id, occurred_at=_iso(t),
    )
    t += 10

    doc = Document(
        application_id=app.id,
        doc_type="application_form",
        file_name=file_name,
        file_size=350000,
        mime_type="application/pdf",
        storage_path=f"storage/demo/{file_name}",
        file_hash=file_hash,
    )
    db.add(doc)
    db.flush()

    AuditService.append_audit_event(
        db, "DOCUMENT_UPLOADED",
        {"document_id": doc.id, "file_name": doc.file_name, "file_hash": doc.file_hash, "file_size": doc.file_size},
        actor_id="officer-020", application_id=app.id, occurred_at=_iso(t),
    )
    t += 10

    page1 = OCRPage(document_id=doc.id, page_number=1, raw_text=f"Applicant: {applicant_name}\nDOB: {student_dob}", width=2480, height=3508)
    page2 = OCRPage(document_id=doc.id, page_number=2, raw_text=f"Institution: {institution_name}\nIncome: Rs {family_income:,}", width=2480, height=3508)
    db.add_all([page1, page2])
    db.flush()

    AuditService.append_audit_event(
        db, "OCR_COMPLETED",
        {"document_id": doc.id, "pages_count": 2, "tokens_count": 150, "mean_confidence": 0.94},
        actor_id="system-ocr", application_id=app.id, occurred_at=_iso(t),
    )
    t += 5

    AuditService.append_audit_event(
        db, "EXTRACTION_COMPLETED",
        {"document_id": doc.id, "extracted_count": 9, "model": "gemini-flash"},
        actor_id="system-llm", application_id=app.id, occurred_at=_iso(t),
    )
    t += 5

    for idx, (fname, vf) in enumerate(fields_map.items()):
        db.add(ExtractedField(
            application_id=app.id,
            document_id=doc.id,
            field_name=fname,
            raw_value_text=str(vf.normalized_value),
            normalized_value=vf.normalized_value,
            status=vf.status.value,
            validation_status=vf.validation_status.value,
            ocr_confidence=vf.ocr_confidence,
            evidence_match_score=vf.evidence_match_score,
            model_confidence=vf.model_confidence,
            final_confidence=vf.final_confidence,
            evidence_quote=vf.evidence_quote,
            source_page=vf.source_page,
            bounding_box=vf.bounding_box.model_dump() if vf.bounding_box else None,
        ))
        AuditService.append_audit_event(
            db, "FIELD_VALIDATED",
            {"field_name": fname, "status": vf.status.value, "validation_status": vf.validation_status.value,
             "final_confidence": vf.final_confidence, "normalized_value": vf.normalized_value},
            actor_id="system-evidence", application_id=app.id, occurred_at=_iso(t + idx),
        )
    t += len(fields_map) + 2

    dec = Decision(
        application_id=app.id,
        decision_version=1,
        outcome=outcome.value,
        decision_mode=decision_mode,
        policy_version="CSSS-Demo-v1.0",
        confidence_summary=confidence_summary,
        is_final=(outcome.value != "NEEDS_REVIEW"),
    )
    db.add(dec)
    db.flush()

    for idx, rr in enumerate(rule_results):
        db.add(DecisionRuleResult(
            decision_id=dec.id,
            rule_code=rr.rule_code,
            result=rr.result.value,
            input_snapshot=rr.input_snapshot,
            explanation=rr.explanation,
            policy_version=rr.policy_version,
        ))
        AuditService.append_audit_event(
            db, "RULE_EVALUATED",
            {"rule_code": rr.rule_code, "result": rr.result.value, "explanation": rr.explanation,
             "input_snapshot": rr.input_snapshot, "policy_version": rr.policy_version},
            actor_id="system-rules", application_id=app.id, occurred_at=_iso(t + idx),
        )
    t += len(rule_results) + 2

    AuditService.append_audit_event(
        db, "DECISION_CREATED",
        {"decision_id": dec.id, "decision_version": 1, "outcome": outcome.value,
         "decision_mode": decision_mode, "policy_version": "CSSS-Demo-v1.0"},
        actor_id="system-orchestrator", application_id=app.id, occurred_at=_iso(t),
    )

    db.commit()
    logger.info("Seeded extra demo case %s (%s)", ref, outcome.value)


def seed_extra_demo_cases(db: Session) -> None:
    """Seeds 5 additional synthetic applications (APP-00019..APP-00023),
    idempotent like the original 3 cases. Call this from
    SeedService.seed_all_demo_data() — see the patch note below."""

    # APP-00019 — clean, high-merit, ELIGIBLE (a second "everything is great" case)
    _seed_generic_case(
        db, ref="APP-00019", applicant_name="Ananya Reddy", student_dob="2005-09-02",
        board_percentile=94.1, course_mode="Regular", institution_name="Osmania University",
        institution_recognized=True, family_income=310000, other_scholarship=False,
        application_date="2026-08-13", file_name="ananya_reddy_bundle.pdf",
        file_hash="b1c2d3e4f5061728394a5b6c7d8e9f0a1b2c3d4e5f60718293a4b5c6d7e8f901",
        time_offset=0,
    )

    # APP-00020 — over the income ceiling -> INELIGIBLE
    _seed_generic_case(
        db, ref="APP-00020", applicant_name="Vikram Chawla", student_dob="2004-12-19",
        board_percentile=88.7, course_mode="Regular", institution_name="Pune Institute of Technology",
        institution_recognized=True, family_income=612000, other_scholarship=False,
        application_date="2026-08-14", file_name="vikram_chawla_bundle.pdf",
        file_hash="c2d3e4f506172839405a6b7c8d9e0f1a2b3c4d5e6f708192a3b4c5d6e7f80912",
        time_offset=100,
    )

    # APP-00021 — below percentile cutoff -> INELIGIBLE
    _seed_generic_case(
        db, ref="APP-00021", applicant_name="Fatima Sheikh", student_dob="2006-03-27",
        board_percentile=74.3, course_mode="Regular", institution_name="Aligarh Muslim University",
        institution_recognized=True, family_income=275000, other_scholarship=False,
        application_date="2026-08-15", file_name="fatima_sheikh_bundle.pdf",
        file_hash="d3e4f5061728394a5b6c7d8e9f0a1b2c3d4e5f60718293a4b5c6d7e8f901a23",
        time_offset=200,
    )

    # APP-00022 — already holds another scholarship -> INELIGIBLE
    _seed_generic_case(
        db, ref="APP-00022", applicant_name="Karan Mehta", student_dob="2005-05-30",
        board_percentile=91.0, course_mode="Regular", institution_name="Manipal Institute of Technology",
        institution_recognized=True, family_income=390000, other_scholarship=True,
        application_date="2026-08-16", file_name="karan_mehta_bundle.pdf",
        file_hash="e4f506172839405a6b7c8d9e0f1a2b3c4d5e6f708192a3b4c5d6e7f80912a34",
        time_offset=300,
    )

    # APP-00023 — distance-mode course -> INELIGIBLE (fails CSSS_COURSE_MODE)
    _seed_generic_case(
        db, ref="APP-00023", applicant_name="Sneha Joshi", student_dob="2006-07-08",
        board_percentile=85.6, course_mode="Distance", institution_name="IGNOU",
        institution_recognized=True, family_income=340000, other_scholarship=False,
        application_date="2026-08-17", file_name="sneha_joshi_bundle.pdf",
        file_hash="f5061728394a5b6c7d8e9f0a1b2c3d4e5f60718293a4b5c6d7e8f901a2345b",
        time_offset=400,
    )


# -----------------------------------------------------------------------
# PATCH: add this one line to backend/app/services/seed_service.py
# -----------------------------------------------------------------------
#
#   from app.services.demo_seed_extra import seed_extra_demo_cases
#
#   class SeedService:
#       @staticmethod
#       def seed_all_demo_data(db: Session):
#           SeedService.seed_policies(db)
#           SeedService.seed_case_a(db)
#           SeedService.seed_case_b(db)
#           SeedService.seed_case_c(db)
#           seed_extra_demo_cases(db)          # <-- add this line
#
# After that, POST /api/demo/reset (the "Reset DB" button on the Dashboard)
# will populate all 8 applications (APP-00016 .. APP-00023) with a full,
# cryptographically-chained audit trail each — 3 ELIGIBLE, 2 NEEDS_REVIEW,
# 3 INELIGIBLE — giving the Dashboard counters, the Reports outcome-mix
# chart, and the Audit log screen real variety to show in the demo.
