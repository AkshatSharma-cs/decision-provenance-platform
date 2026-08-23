"""
Real end-to-end integration test: PDF -> Tesseract (real) -> Gemini extraction
(real if GEMINI_API_KEY is set, otherwise mocked) -> evidence_service (real,
deterministic).

Per the brief: Tesseract is NOT mocked here under any circumstances. This is
the one test in the suite that exercises the actual OCR binary end to end.

Run with: python scripts/test_integration_ocr_extraction_evidence.py
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Load repo-root .env into the actual process environment, since nothing else
# in this prototype (no FastAPI app entrypoint yet) does that for us. This is
# only done in test scripts, never inside the service files themselves —
# service code should stay a pure function of os.environ, not have import-
# time side effects. Silently continues if python-dotenv isn't installed or
# no .env file exists; GEMINI_API_KEY then just needs to be set some other way.
try:
    from dotenv import load_dotenv

    _REPO_ROOT_ENV = Path(__file__).resolve().parent.parent.parent / ".env"
    load_dotenv(_REPO_ROOT_ENV)
except ImportError:
    pass

import fitz  # PyMuPDF, only to build the synthetic sample document

from app.services.ocr_service import process_document
from app.services import extraction_service
from app.services.evidence_service import validate_fields
from app.schemas.validation import FieldTrustStatus, ValidationStatus


def _make_sample_pdf(path: Path) -> None:
    """Two-page synthetic income-certificate-style PDF, deliberately including
    one field (family_income) with a clean digit run for numeric verification,
    and leaving several frozen fields genuinely absent so MISSING is also
    exercised end to end."""
    doc = fitz.open()

    page1 = doc.new_page()
    page1.insert_text((72, 100), "Income and Course Certificate", fontsize=18)
    page1.insert_text((72, 140), "Student Name: Priya Kumar", fontsize=12)
    page1.insert_text((72, 165), "Date of Birth: 2006-04-12", fontsize=12)

    page2 = doc.new_page()
    page2.insert_text((72, 100), "Gross parental family income: Rs 420000 per annum", fontsize=12)
    page2.insert_text((72, 130), "Course Mode: Regular", fontsize=12)

    doc.save(str(path))
    doc.close()


_MOCK_GEMINI_FIELDS = [
    {
        "field_name": "student_name",
        "value_text": "Priya Kumar",
        "evidence_quote": "Student Name: Priya Kumar",
        "page_number": 1,
        "uncertainty_reason": None,
        "model_confidence": 0.97,
    },
    {
        "field_name": "date_of_birth",
        "value_text": "2006-04-12",
        "evidence_quote": "Date of Birth: 2006-04-12",
        "page_number": 1,
        "uncertainty_reason": None,
        "model_confidence": 0.95,
    },
    {
        "field_name": "board_percentile",
        "value_text": None,
        "evidence_quote": None,
        "page_number": None,
        "uncertainty_reason": "board percentile not present in supplied text",
        "model_confidence": 0.0,
    },
    {
        "field_name": "course_mode",
        "value_text": "Regular",
        "evidence_quote": "Course Mode: Regular",
        "page_number": 2,
        "uncertainty_reason": None,
        "model_confidence": 0.96,
    },
    {
        "field_name": "institution_name",
        "value_text": None,
        "evidence_quote": None,
        "page_number": None,
        "uncertainty_reason": "institution name not present in supplied text",
        "model_confidence": 0.0,
    },
    {
        "field_name": "institution_recognized",
        "value_text": None,
        "evidence_quote": None,
        "page_number": None,
        "uncertainty_reason": "recognition status not present in supplied text",
        "model_confidence": 0.0,
    },
    {
        "field_name": "family_income",
        "value_text": "Rs 420000 per annum",
        "evidence_quote": "Gross parental family income: Rs 420000 per annum",
        "page_number": 2,
        "uncertainty_reason": None,
        "model_confidence": 0.96,
    },
    {
        "field_name": "other_scholarship",
        "value_text": None,
        "evidence_quote": None,
        "page_number": None,
        "uncertainty_reason": "not mentioned in supplied text",
        "model_confidence": 0.0,
    },
    {
        "field_name": "application_date",
        "value_text": None,
        "evidence_quote": None,
        "page_number": None,
        "uncertainty_reason": "not present in supplied text",
        "model_confidence": 0.0,
    },
]


def main() -> None:
    sample_path = Path(__file__).resolve().parent / "_integration_sample.pdf"
    print(f"Generating synthetic sample PDF at {sample_path}")
    _make_sample_pdf(sample_path)

    print("\n[1/3] Running REAL Tesseract OCR via process_document()...")
    ocr_result = process_document(str(sample_path))
    print(f"    -> {ocr_result.total_pages} pages, overall_mean_confidence={ocr_result.overall_mean_confidence}")
    for p in ocr_result.pages:
        print(f"    page {p.page_number}: {p.token_count} tokens, text={p.page_text!r}")

    use_real_gemini = bool(os.environ.get("GEMINI_API_KEY")) and os.environ.get("GEMINI_API_KEY") != "test-key-not-real"
    if use_real_gemini:
        print("\n[2/3] GEMINI_API_KEY is set — calling the REAL Gemini API...")
        candidates = extraction_service.extract_fields(ocr_result, application_public_reference="INTEGRATION-TEST")
    else:
        print("\n[2/3] No real GEMINI_API_KEY available — using a MOCKED Gemini response "
              "(Tesseract above was NOT mocked).")
        os.environ.setdefault("GEMINI_API_KEY", "test-key-not-real")
        original_build_client = extraction_service._build_gemini_client
        original_call_gemini = extraction_service._call_gemini
        extraction_service._build_gemini_client = lambda: object()
        extraction_service._call_gemini = lambda client, prompt: json.dumps({"fields": _MOCK_GEMINI_FIELDS})
        try:
            candidates = extraction_service.extract_fields(ocr_result, application_public_reference="INTEGRATION-TEST")
        finally:
            extraction_service._build_gemini_client = original_build_client
            extraction_service._call_gemini = original_call_gemini

    for c in candidates:
        print(f"    candidate: {c.field_name.value} value={c.value!r} evidence_quote={c.evidence_quote!r}")

    print("\n[3/3] Running REAL evidence_service.validate_fields() (deterministic, no LLM)...")
    validated = validate_fields(candidates, ocr_result)

    by_name = {v.field_name.value: v for v in validated}
    print("\n--- Results ---")
    for v in validated:
        print(
            f"{v.field_name.value:24s} status={v.status.value:10s} validation_status={v.validation_status.value:9s} "
            f"value={v.normalized_value!r} source_page={v.source_page} "
            f"ocr_conf={v.ocr_confidence} match_score={v.evidence_match_score}"
        )

    # Sanity assertions on the known-good synthetic document.
    assert by_name["family_income"].status == FieldTrustStatus.VALIDATED, by_name["family_income"]
    assert by_name["family_income"].normalized_value == 420000
    assert by_name["student_name"].status == FieldTrustStatus.VALIDATED
    assert by_name["date_of_birth"].status == FieldTrustStatus.VALIDATED
    assert by_name["course_mode"].status == FieldTrustStatus.VALIDATED
    assert by_name["board_percentile"].validation_status == ValidationStatus.MISSING
    assert by_name["institution_name"].validation_status == ValidationStatus.MISSING

    print("\nEnd-to-end integration test PASSED (real Tesseract, "
          + ("real" if use_real_gemini else "mocked")
          + " Gemini, real deterministic evidence_service).")

    sample_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
