"""
Seed Service for Project Synapse.
Seeds default policy versions and the 3 frozen Demo Cases:
  - APP-00016 (Case A: Clean Eligible)
  - APP-00017 (Case B: Low Confidence / Missing Doc -> NEEDS_REVIEW)
  - APP-00018 (Case C: Human Override -> Decision v1 NEEDS_REVIEW -> Override -> Decision v2 ELIGIBLE)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List
from sqlalchemy.orm import Session

from app.db.models import (
    Application,
    Document,
    OCRPage,
    OCRToken,
    ExtractedField,
    PolicyVersion,
    Decision,
    DecisionRuleResult,
    ReviewAction,
    AuditLogEntry,
)
from app.schemas.decision import DecisionOutcome, DecisionMode, RuleResultEnum
from app.services.audit_service import AuditService

logger = logging.getLogger(__name__)


def get_iso_time(offset_seconds: int = 0) -> str:
    base = datetime(2026, 8, 18, 10, 0, 0, tzinfo=timezone.utc)
    from datetime import timedelta
    return (base + timedelta(seconds=offset_seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")


class SeedService:
    """
    Handles database seeding for instant demo presentation and testing.
    """

    @staticmethod
    def seed_policies(db: Session):
        """Seeds default policy versions if not present."""
        existing = db.query(PolicyVersion).filter(PolicyVersion.version_string == "CSSS-Demo-v1.0").first()
        if not existing:
            p1 = PolicyVersion(
                scheme_code="PM-USP-CSSS",
                version_string="CSSS-Demo-v1.0",
                title="PM-USP CSSS Standard Guidelines 2026",
                description="Standard verification rules: Board Percentile > 80, Regular course, Recognized institution, Family Income <= ₹4,50,000, No other scholarship.",
                status="PUBLISHED",
                rules_config=[
                    {"code": "CSSS_PERCENTILE_MIN", "name": "Percentile Threshold", "condition": "board_percentile > 80"},
                    {"code": "CSSS_COURSE_MODE", "name": "Course Mode", "condition": "course_mode == 'Regular'"},
                    {"code": "CSSS_INSTITUTION_RECOGNIZED", "name": "Institution Recognition", "condition": "institution_recognized == true"},
                    {"code": "CSSS_NO_OTHER_SCHOLARSHIP", "name": "Single Scholarship", "condition": "other_scholarship == false"},
                    {"code": "CSSS_INCOME_LIMIT", "name": "Family Income Limit", "condition": "family_income <= 450000"},
                    {"code": "CSSS_DOCUMENTS_PRESENT", "name": "Document Completeness", "condition": "all required uploaded"},
                ]
            )
            db.add(p1)

        existing_v2 = db.query(PolicyVersion).filter(PolicyVersion.version_string == "CSSS-Demo-v1.1").first()
        if not existing_v2:
            p2 = PolicyVersion(
                scheme_code="PM-USP-CSSS",
                version_string="CSSS-Demo-v1.1",
                title="PM-USP CSSS Enhanced Verification 2026",
                description="Enhanced rules including dated income certificate validation and strict biometric verification requirements.",
                status="PUBLISHED",
                rules_config=[
                    {"code": "CSSS_PERCENTILE_MIN", "name": "Percentile Threshold", "condition": "board_percentile > 80"},
                    {"code": "CSSS_COURSE_MODE", "name": "Course Mode", "condition": "course_mode == 'Regular'"},
                    {"code": "CSSS_INSTITUTION_RECOGNIZED", "name": "Institution Recognition", "condition": "institution_recognized == true"},
                    {"code": "CSSS_NO_OTHER_SCHOLARSHIP", "name": "Single Scholarship", "condition": "other_scholarship == false"},
                    {"code": "CSSS_INCOME_LIMIT", "name": "Family Income Limit", "condition": "family_income <= 450000"},
                    {"code": "CSSS_DOCUMENTS_PRESENT", "name": "Document Completeness", "condition": "all required uploaded"},
                ]
            )
            db.add(p2)

        db.commit()

    @staticmethod
    def seed_all_demo_data(db: Session):
        """Seeds all policies and demo cases A, B, and C."""
        SeedService.seed_policies(db)
        SeedService.seed_case_a(db)
        SeedService.seed_case_b(db)
        SeedService.seed_case_c(db)

    @staticmethod
    def seed_case_a(db: Session):
        """Case A — APP-00016: Clean, Eligible, Automated, High Evidence Quality."""
        ref = "APP-00016"
        if db.query(Application).filter(Application.public_reference == ref).first():
            return

        app = Application(
            public_reference=ref,
            applicant_name="Rajesh Kumar Sharma",
            scheme_code="PM-USP-CSSS",
            status="AUTO_DECISION",
        )
        db.add(app)
        db.flush()

        # Audit APPLICATION_CREATED
        AuditService.append_audit_event(
            db, "APPLICATION_CREATED",
            {"public_reference": ref, "applicant_name": app.applicant_name, "scheme_code": app.scheme_code},
            actor_id="officer-012", application_id=app.id, occurred_at=get_iso_time(0)
        )

        # Document
        doc1 = Document(
            application_id=app.id,
            doc_type="application_form",
            file_name="rajesh_sharma_application_bundle.pdf",
            file_size=412850,
            mime_type="application/pdf",
            storage_path="storage/demo/rajesh_sharma_application_bundle.pdf",
            file_hash="9f83c12a8169a65d56d7870560b457e5bf885fa2cf9017fb7d0b3f5c7e1f48ab",
        )
        db.add(doc1)
        db.flush()

        AuditService.append_audit_event(
            db, "DOCUMENT_UPLOADED",
            {"document_id": doc1.id, "file_name": doc1.file_name, "file_hash": doc1.file_hash, "file_size": doc1.file_size},
            actor_id="officer-012", application_id=app.id, occurred_at=get_iso_time(10)
        )

        # OCR Page & Tokens
        p1 = OCRPage(document_id=doc1.id, page_number=1, raw_text="CENTRAL SECTOR SCHEME OF SCHOLARSHIP 2026\nApplicant: Rajesh Kumar Sharma\nDOB: 2005-06-15\nPercentile: 86.40%\nCourse: Regular B.Tech", width=2480, height=3508)
        p2 = OCRPage(document_id=doc1.id, page_number=2, raw_text="INCOME & INSTITUTION VERIFICATION\nInstitution: Indian Institute of Technology Delhi (Recognized)\nGross parental/family income: ₹4,20,000 per annum\nOther scholarship: None", width=2480, height=3508)
        db.add_all([p1, p2])
        db.flush()

        AuditService.append_audit_event(
            db, "OCR_COMPLETED",
            {"document_id": doc1.id, "pages_count": 2, "tokens_count": 184, "mean_confidence": 0.965},
            actor_id="system-ocr", application_id=app.id, occurred_at=get_iso_time(20)
        )

        AuditService.append_audit_event(
            db, "EXTRACTION_COMPLETED",
            {"document_id": doc1.id, "extracted_count": 9, "model": "gemini-flash"},
            actor_id="system-llm", application_id=app.id, occurred_at=get_iso_time(25)
        )

        # Extracted Fields
        fields_data = [
            ("student_name", "Rajesh Kumar Sharma", "Rajesh Kumar Sharma", "VALIDATED", "VALID", 0.98, 1.0, 0.97, 0.983, "Applicant: Rajesh Kumar Sharma", 1, {"x": 120, "y": 240, "width": 380, "height": 30}),
            ("date_of_birth", "2005-06-15", "2005-06-15", "VALIDATED", "VALID", 0.97, 1.0, 0.96, 0.976, "DOB: 2005-06-15", 1, {"x": 120, "y": 290, "width": 260, "height": 28}),
            ("board_percentile", 86.4, "86.40%", "VALIDATED", "VALID", 0.96, 1.0, 0.95, 0.970, "Percentile: 86.40%", 1, {"x": 120, "y": 340, "width": 280, "height": 30}),
            ("course_mode", "Regular", "Regular B.Tech", "VALIDATED", "VALID", 0.97, 1.0, 0.96, 0.976, "Course: Regular B.Tech", 1, {"x": 120, "y": 390, "width": 320, "height": 28}),
            ("institution_name", "Indian Institute of Technology Delhi", "Indian Institute of Technology Delhi (Recognized)", "VALIDATED", "VALID", 0.96, 1.0, 0.95, 0.970, "Institution: Indian Institute of Technology Delhi (Recognized)", 2, {"x": 140, "y": 210, "width": 520, "height": 32}),
            ("institution_recognized", True, "Recognized", "VALIDATED", "VALID", 0.95, 1.0, 0.94, 0.963, "Institution: Indian Institute of Technology Delhi (Recognized)", 2, {"x": 480, "y": 210, "width": 180, "height": 32}),
            ("family_income", 420000, "₹4,20,000 per annum", "VALIDATED", "VALID", 0.96, 1.0, 0.94, 0.966, "Gross parental/family income: ₹4,20,000 per annum", 2, {"x": 140, "y": 270, "width": 460, "height": 30}),
            ("other_scholarship", False, "None", "VALIDATED", "VALID", 0.97, 1.0, 0.95, 0.973, "Other scholarship: None", 2, {"x": 140, "y": 330, "width": 290, "height": 28}),
            ("application_date", "2026-08-10", "2026-08-10", "VALIDATED", "VALID", 0.98, 1.0, 0.97, 0.983, "Date of Application: 2026-08-10", 1, {"x": 120, "y": 450, "width": 310, "height": 28}),
        ]

        for idx, (fname, val, raw, st, vst, ocr_c, em_c, m_c, f_c, eq, sp, bb) in enumerate(fields_data):
            ef = ExtractedField(
                application_id=app.id,
                document_id=doc1.id,
                field_name=fname,
                raw_value_text=raw,
                normalized_value=val,
                status=st,
                validation_status=vst,
                ocr_confidence=ocr_c,
                evidence_match_score=em_c,
                model_confidence=m_c,
                final_confidence=f_c,
                evidence_quote=eq,
                source_page=sp,
                bounding_box=bb,
            )
            db.add(ef)
            AuditService.append_audit_event(
                db, "FIELD_VALIDATED",
                {"field_name": fname, "status": st, "validation_status": vst, "final_confidence": f_c, "normalized_value": val},
                actor_id="system-evidence", application_id=app.id, occurred_at=get_iso_time(30 + idx)
            )

        # Decision
        dec = Decision(
            application_id=app.id,
            decision_version=1,
            outcome="ELIGIBLE",
            decision_mode="AUTOMATED",
            policy_version="CSSS-Demo-v1.0",
            confidence_summary={"evidence_quality": "HIGH", "avg_confidence": 0.974, "untrusted_count": 0},
            is_final=False,
        )
        db.add(dec)
        db.flush()

        rules_data = [
            ("CSSS_PERCENTILE_MIN", "PASS", {"board_percentile": 86.4}, "Board percentile 86.4% meets the requirement (> 80.0%)."),
            ("CSSS_COURSE_MODE", "PASS", {"course_mode": "Regular"}, "Enrolled in 'Regular' course mode (satisfies Regular mode requirement)."),
            ("CSSS_INSTITUTION_RECOGNIZED", "PASS", {"institution_recognized": True}, "Institution 'Indian Institute of Technology Delhi' is verified as government-recognized."),
            ("CSSS_NO_OTHER_SCHOLARSHIP", "PASS", {"other_scholarship": False}, "Applicant declared no other state/central government scholarships availed."),
            ("CSSS_INCOME_LIMIT", "PASS", {"family_income": 420000}, "₹4,20,000 is within the ₹4,50,000 limit."),
            ("CSSS_DOCUMENTS_PRESENT", "PASS", {"uploaded_documents_count": 1}, "All mandatory verification documents are present (1 files uploaded)."),
        ]

        for idx, (rcode, rres, isnap, rexp) in enumerate(rules_data):
            rr = DecisionRuleResult(
                decision_id=dec.id,
                rule_code=rcode,
                result=rres,
                input_snapshot=isnap,
                explanation=rexp,
                policy_version="CSSS-Demo-v1.0",
            )
            db.add(rr)
            AuditService.append_audit_event(
                db, "RULE_EVALUATED",
                {"rule_code": rcode, "result": rres, "explanation": rexp, "input_snapshot": isnap, "policy_version": "CSSS-Demo-v1.0"},
                actor_id="system-rules", application_id=app.id, occurred_at=get_iso_time(40 + idx)
            )

        AuditService.append_audit_event(
            db, "DECISION_CREATED",
            {"decision_id": dec.id, "decision_version": 1, "outcome": "ELIGIBLE", "decision_mode": "AUTOMATED", "policy_version": "CSSS-Demo-v1.0"},
            actor_id="system-orchestrator", application_id=app.id, occurred_at=get_iso_time(50)
        )

        db.commit()
        logger.info("Seeded Case A (APP-00016)")

    @staticmethod
    def seed_case_b(db: Session):
        """Case B — APP-00017: Bad / Uncertain Application -> NEEDS_REVIEW."""
        ref = "APP-00017"
        if db.query(Application).filter(Application.public_reference == ref).first():
            return

        app = Application(
            public_reference=ref,
            applicant_name="Priya Patel",
            scheme_code="PM-USP-CSSS",
            status="NEEDS_REVIEW",
        )
        db.add(app)
        db.flush()

        AuditService.append_audit_event(
            db, "APPLICATION_CREATED",
            {"public_reference": ref, "applicant_name": app.applicant_name, "scheme_code": app.scheme_code},
            actor_id="officer-014", application_id=app.id, occurred_at=get_iso_time(100)
        )

        doc1 = Document(
            application_id=app.id,
            doc_type="application_form",
            file_name="priya_patel_blurry_scan.pdf",
            file_size=312400,
            mime_type="application/pdf",
            storage_path="storage/demo/priya_patel_blurry_scan.pdf",
            file_hash="a1b2c3d4e5f67890123456789abcdef0123456789abcdef0123456789abcdef0",
        )
        db.add(doc1)
        db.flush()

        AuditService.append_audit_event(
            db, "DOCUMENT_UPLOADED",
            {"document_id": doc1.id, "file_name": doc1.file_name, "file_hash": doc1.file_hash, "file_size": doc1.file_size},
            actor_id="officer-014", application_id=app.id, occurred_at=get_iso_time(110)
        )

        AuditService.append_audit_event(
            db, "OCR_COMPLETED",
            {"document_id": doc1.id, "pages_count": 1, "tokens_count": 92, "mean_confidence": 0.612, "warning": "low_confidence_scan"},
            actor_id="system-ocr", application_id=app.id, occurred_at=get_iso_time(120)
        )

        # Low confidence income field (61% confidence) & missing institution recognition
        fields_data = [
            ("student_name", "Priya Patel", "Priya Patel", "VALIDATED", "VALID", 0.91, 1.0, 0.90, 0.936, "Applicant: Priya Patel", 1, {"x": 100, "y": 200, "width": 280, "height": 28}),
            ("date_of_birth", "2006-01-12", "2006-01-12", "VALIDATED", "VALID", 0.89, 1.0, 0.88, 0.923, "DOB: 2006-01-12", 1, {"x": 100, "y": 240, "width": 220, "height": 26}),
            ("board_percentile", 82.5, "82.5%", "VALIDATED", "VALID", 0.88, 1.0, 0.87, 0.916, "Percentile: 82.5%", 1, {"x": 100, "y": 280, "width": 240, "height": 28}),
            ("course_mode", "Regular", "Regular", "VALIDATED", "VALID", 0.90, 1.0, 0.89, 0.930, "Course: Regular", 1, {"x": 100, "y": 320, "width": 200, "height": 26}),
            ("institution_name", "Sunrise College of Arts", "Sunrise College of Arts", "VALIDATED", "VALID", 0.78, 0.92, 0.80, 0.833, "Inst: Sunrise College of Arts", 1, {"x": 100, "y": 360, "width": 380, "height": 28}),
            ("institution_recognized", None, None, "UNTRUSTED", "MISSING", 0.0, 0.0, 0.0, 0.0, None, None, None),
            ("family_income", 480000, "₹4,80,000 [blurry]", "UNTRUSTED", "AMBIGUOUS", 0.61, 0.88, 0.65, 0.713, "Income approx: ₹4,80,000", 1, {"x": 100, "y": 400, "width": 320, "height": 28}),
            ("other_scholarship", False, "No", "VALIDATED", "VALID", 0.88, 1.0, 0.87, 0.916, "Other Schol: No", 1, {"x": 100, "y": 440, "width": 210, "height": 26}),
            ("application_date", "2026-08-11", "2026-08-11", "VALIDATED", "VALID", 0.92, 1.0, 0.91, 0.943, "Date: 2026-08-11", 1, {"x": 100, "y": 480, "width": 220, "height": 26}),
        ]

        for idx, (fname, val, raw, st, vst, ocr_c, em_c, m_c, f_c, eq, sp, bb) in enumerate(fields_data):
            ef = ExtractedField(
                application_id=app.id,
                document_id=doc1.id,
                field_name=fname,
                raw_value_text=raw,
                normalized_value=val,
                status=st,
                validation_status=vst,
                ocr_confidence=ocr_c,
                evidence_match_score=em_c,
                model_confidence=m_c,
                final_confidence=f_c,
                evidence_quote=eq,
                source_page=sp,
                bounding_box=bb,
                uncertainty_reason="OCR confidence low (61%) or certificate missing." if st == "UNTRUSTED" else None
            )
            db.add(ef)
            AuditService.append_audit_event(
                db, "FIELD_VALIDATED",
                {"field_name": fname, "status": st, "validation_status": vst, "final_confidence": f_c, "normalized_value": val},
                actor_id="system-evidence", application_id=app.id, occurred_at=get_iso_time(130 + idx)
            )

        dec = Decision(
            application_id=app.id,
            decision_version=1,
            outcome="NEEDS_REVIEW",
            decision_mode="AUTOMATED",
            policy_version="CSSS-Demo-v1.0",
            confidence_summary={"evidence_quality": "LOW", "avg_confidence": 0.689, "untrusted_count": 2},
            is_final=False,
        )
        db.add(dec)
        db.flush()

        rules_data = [
            ("CSSS_PERCENTILE_MIN", "PASS", {"board_percentile": 82.5}, "Board percentile 82.5% meets the requirement (> 80.0%)."),
            ("CSSS_COURSE_MODE", "PASS", {"course_mode": "Regular"}, "Enrolled in 'Regular' course mode."),
            ("CSSS_INSTITUTION_RECOGNIZED", "NEEDS_REVIEW", {}, "Institution recognition certificate missing from upload bundle. Review required."),
            ("CSSS_NO_OTHER_SCHOLARSHIP", "PASS", {"other_scholarship": False}, "Applicant declared no other scholarship."),
            ("CSSS_INCOME_LIMIT", "NEEDS_REVIEW", {}, "Family income certificate missing, illegible, or low-confidence (61% OCR score). Manual review required."),
            ("CSSS_DOCUMENTS_PRESENT", "PASS", {"uploaded_documents_count": 1}, "Application form uploaded."),
        ]

        for idx, (rcode, rres, isnap, rexp) in enumerate(rules_data):
            rr = DecisionRuleResult(
                decision_id=dec.id,
                rule_code=rcode,
                result=rres,
                input_snapshot=isnap,
                explanation=rexp,
                policy_version="CSSS-Demo-v1.0",
            )
            db.add(rr)
            AuditService.append_audit_event(
                db, "RULE_EVALUATED",
                {"rule_code": rcode, "result": rres, "explanation": rexp, "input_snapshot": isnap, "policy_version": "CSSS-Demo-v1.0"},
                actor_id="system-rules", application_id=app.id, occurred_at=get_iso_time(140 + idx)
            )

        AuditService.append_audit_event(
            db, "DECISION_CREATED",
            {"decision_id": dec.id, "decision_version": 1, "outcome": "NEEDS_REVIEW", "decision_mode": "AUTOMATED", "policy_version": "CSSS-Demo-v1.0"},
            actor_id="system-orchestrator", application_id=app.id, occurred_at=get_iso_time(150)
        )

        db.commit()
        logger.info("Seeded Case B (APP-00017)")

    @staticmethod
    def seed_case_c(db: Session):
        """
        Case C — APP-00018: Human Correction / Override Case
        Decision v1 (NEEDS_REVIEW) -> Human Override (₹4,80,000 -> ₹4,08,000) -> Decision v2 (ELIGIBLE)
        """
        ref = "APP-00018"
        if db.query(Application).filter(Application.public_reference == ref).first():
            return

        app = Application(
            public_reference=ref,
            applicant_name="Amit Vikram Singh",
            scheme_code="PM-USP-CSSS",
            status="HUMAN_CONFIRMED",
        )
        db.add(app)
        db.flush()

        AuditService.append_audit_event(
            db, "APPLICATION_CREATED",
            {"public_reference": ref, "applicant_name": app.applicant_name, "scheme_code": app.scheme_code},
            actor_id="officer-015", application_id=app.id, occurred_at=get_iso_time(200)
        )

        doc1 = Document(
            application_id=app.id,
            doc_type="application_form",
            file_name="amit_singh_application.pdf",
            file_size=389100,
            mime_type="application/pdf",
            storage_path="storage/demo/amit_singh_application.pdf",
            file_hash="c3d4e5f67890123456789abcdef0123456789abcdef0123456789abcdef01234",
        )
        db.add(doc1)
        db.flush()

        AuditService.append_audit_event(
            db, "DOCUMENT_UPLOADED",
            {"document_id": doc1.id, "file_name": doc1.file_name, "file_hash": doc1.file_hash, "file_size": doc1.file_size},
            actor_id="officer-015", application_id=app.id, occurred_at=get_iso_time(210)
        )

        AuditService.append_audit_event(
            db, "OCR_COMPLETED",
            {"document_id": doc1.id, "pages_count": 2, "tokens_count": 160, "mean_confidence": 0.88},
            actor_id="system-ocr", application_id=app.id, occurred_at=get_iso_time(220)
        )

        # Fields: initial family_income misread as ₹4,80,000, then overridden to ₹4,08,000
        fields_data = [
            ("student_name", "Amit Vikram Singh", "Amit Vikram Singh", "VALIDATED", "VALID", 0.97, 1.0, 0.96, 0.976, "Applicant: Amit Vikram Singh", 1, {"x": 110, "y": 220, "width": 340, "height": 30}),
            ("date_of_birth", "2005-11-20", "2005-11-20", "VALIDATED", "VALID", 0.96, 1.0, 0.95, 0.970, "DOB: 2005-11-20", 1, {"x": 110, "y": 260, "width": 240, "height": 26}),
            ("board_percentile", 89.2, "89.20%", "VALIDATED", "VALID", 0.98, 1.0, 0.97, 0.983, "Percentile: 89.20%", 1, {"x": 110, "y": 300, "width": 260, "height": 28}),
            ("course_mode", "Regular", "Regular B.Sc", "VALIDATED", "VALID", 0.97, 1.0, 0.96, 0.976, "Course: Regular B.Sc", 1, {"x": 110, "y": 340, "width": 300, "height": 28}),
            ("institution_name", "Delhi University", "Delhi University", "VALIDATED", "VALID", 0.96, 1.0, 0.95, 0.970, "Institution: Delhi University", 2, {"x": 120, "y": 200, "width": 420, "height": 30}),
            ("institution_recognized", True, "Recognized Central University", "VALIDATED", "VALID", 0.95, 1.0, 0.94, 0.963, "Status: Recognized Central University", 2, {"x": 120, "y": 240, "width": 380, "height": 28}),
            ("family_income", 408000, "₹4,08,000 (Overridden from ₹4,80,000)", "OVERRIDDEN", "VALID", 0.96, 1.0, 0.95, 0.970, "Gross family income: ₹4,08,000 per annum (Original verified certificate)", 2, {"x": 120, "y": 280, "width": 480, "height": 32}),
            ("other_scholarship", False, "None", "VALIDATED", "VALID", 0.97, 1.0, 0.96, 0.976, "Other scholarship: None", 2, {"x": 120, "y": 330, "width": 280, "height": 28}),
            ("application_date", "2026-08-12", "2026-08-12", "VALIDATED", "VALID", 0.98, 1.0, 0.97, 0.983, "Date: 2026-08-12", 1, {"x": 110, "y": 420, "width": 290, "height": 28}),
        ]

        for idx, (fname, val, raw, st, vst, ocr_c, em_c, m_c, f_c, eq, sp, bb) in enumerate(fields_data):
            ef = ExtractedField(
                application_id=app.id,
                document_id=doc1.id,
                field_name=fname,
                raw_value_text=raw,
                normalized_value=val,
                status=st,
                validation_status=vst,
                ocr_confidence=ocr_c,
                evidence_match_score=em_c,
                model_confidence=m_c,
                final_confidence=f_c,
                evidence_quote=eq,
                source_page=sp,
                bounding_box=bb,
            )
            db.add(ef)
            AuditService.append_audit_event(
                db, "FIELD_VALIDATED",
                {"field_name": fname, "status": "VALIDATED" if fname != "family_income" else "UNTRUSTED", "validation_status": vst, "final_confidence": f_c, "normalized_value": 480000 if fname == "family_income" else val},
                actor_id="system-evidence", application_id=app.id, occurred_at=get_iso_time(230 + idx)
            )

        # Decision v1 (Initial Automated: NEEDS_REVIEW due to income misread as 480000)
        dec1 = Decision(
            application_id=app.id,
            decision_version=1,
            outcome="NEEDS_REVIEW",
            decision_mode="AUTOMATED",
            policy_version="CSSS-Demo-v1.0",
            confidence_summary={"evidence_quality": "MEDIUM", "avg_confidence": 0.892, "untrusted_count": 1},
            is_final=False,
        )
        db.add(dec1)
        db.flush()

        rules_v1 = [
            ("CSSS_PERCENTILE_MIN", "PASS", {"board_percentile": 89.2}, "Board percentile 89.2% meets requirement (> 80.0%)."),
            ("CSSS_COURSE_MODE", "PASS", {"course_mode": "Regular"}, "Course mode is Regular."),
            ("CSSS_INSTITUTION_RECOGNIZED", "PASS", {"institution_recognized": True}, "Institution recognized."),
            ("CSSS_NO_OTHER_SCHOLARSHIP", "PASS", {"other_scholarship": False}, "No other scholarship."),
            ("CSSS_INCOME_LIMIT", "FAIL", {"family_income": 480000}, "₹4,80,000 exceeds the ₹4,50,000 income limit."),
            ("CSSS_DOCUMENTS_PRESENT", "PASS", {"uploaded_documents_count": 1}, "Documents verified."),
        ]

        for idx, (rcode, rres, isnap, rexp) in enumerate(rules_v1):
            rr = DecisionRuleResult(
                decision_id=dec1.id,
                rule_code=rcode,
                result=rres,
                input_snapshot=isnap,
                explanation=rexp,
                policy_version="CSSS-Demo-v1.0",
            )
            db.add(rr)
            AuditService.append_audit_event(
                db, "RULE_EVALUATED",
                {"rule_code": rcode, "result": rres, "explanation": rexp, "input_snapshot": isnap, "policy_version": "CSSS-Demo-v1.0"},
                actor_id="system-rules", application_id=app.id, occurred_at=get_iso_time(240 + idx)
            )

        AuditService.append_audit_event(
            db, "DECISION_CREATED",
            {"decision_id": dec1.id, "decision_version": 1, "outcome": "NEEDS_REVIEW", "decision_mode": "AUTOMATED", "policy_version": "CSSS-Demo-v1.0"},
            actor_id="system-orchestrator", application_id=app.id, occurred_at=get_iso_time(250)
        )

        # Human Review Started
        AuditService.append_audit_event(
            db, "REVIEW_STARTED",
            {"reviewer_id": "reviewer-004", "application_id": app.id},
            actor_id="reviewer-004", application_id=app.id, occurred_at=get_iso_time(280)
        )

        # Human Review Action: Override
        rev_action = ReviewAction(
            application_id=app.id,
            decision_id=dec1.id,
            actor_id="reviewer-004",
            action_type="FIELD_OVERRIDDEN",
            field_name="family_income",
            old_value=480000,
            new_value=408000,
            reason="Clearer original certificate confirms value ₹4,08,000",
        )
        db.add(rev_action)

        AuditService.append_audit_event(
            db, "FIELD_OVERRIDDEN",
            {
                "field": "family_income",
                "old_value": 480000,
                "new_value": 408000,
                "reason": "Clearer original certificate confirms value"
            },
            actor_id="reviewer-004", application_id=app.id, occurred_at=get_iso_time(290)
        )

        # Decision v2 (Human Confirmed -> ELIGIBLE)
        dec2 = Decision(
            application_id=app.id,
            decision_version=2,
            outcome="ELIGIBLE",
            decision_mode="HUMAN_CONFIRMED",
            policy_version="CSSS-Demo-v1.0",
            confidence_summary={"evidence_quality": "HIGH", "avg_confidence": 0.976, "untrusted_count": 0},
            supersedes_decision_id=dec1.id,
            is_final=True,
        )
        db.add(dec2)
        db.flush()

        rules_v2 = [
            ("CSSS_PERCENTILE_MIN", "PASS", {"board_percentile": 89.2}, "Board percentile 89.2% meets requirement (> 80.0%)."),
            ("CSSS_COURSE_MODE", "PASS", {"course_mode": "Regular"}, "Course mode is Regular."),
            ("CSSS_INSTITUTION_RECOGNIZED", "PASS", {"institution_recognized": True}, "Institution recognized."),
            ("CSSS_NO_OTHER_SCHOLARSHIP", "PASS", {"other_scholarship": False}, "No other scholarship."),
            ("CSSS_INCOME_LIMIT", "PASS", {"family_income": 408000}, "₹4,08,000 is within the ₹4,50,000 limit."),
            ("CSSS_DOCUMENTS_PRESENT", "PASS", {"uploaded_documents_count": 1}, "Documents verified."),
        ]

        for idx, (rcode, rres, isnap, rexp) in enumerate(rules_v2):
            rr2 = DecisionRuleResult(
                decision_id=dec2.id,
                rule_code=rcode,
                result=rres,
                input_snapshot=isnap,
                explanation=rexp,
                policy_version="CSSS-Demo-v1.0",
            )
            db.add(rr2)

        AuditService.append_audit_event(
            db, "DECISION_VERSION_CREATED",
            {
                "decision_id": dec2.id,
                "decision_version": 2,
                "outcome": "ELIGIBLE",
                "decision_mode": "HUMAN_CONFIRMED",
                "policy_version": "CSSS-Demo-v1.0",
                "supersedes_decision_id": dec1.id
            },
            actor_id="reviewer-004", application_id=app.id, occurred_at=get_iso_time(300)
        )

        AuditService.append_audit_event(
            db, "FINALIZED",
            {"final_decision_id": dec2.id, "outcome": "ELIGIBLE", "actor": "reviewer-004"},
            actor_id="reviewer-004", application_id=app.id, occurred_at=get_iso_time(310)
        )

        db.commit()
        logger.info("Seeded Case C (APP-00018)")
