"""
Offline smoke test for app/services/extraction_service.py.

This test does NOT call the real Gemini API (no network access, no API key
required) — it monkeypatches `_call_gemini` to return a canned structured
response, so we can verify:
  - normal happy-path normalization (family_income, dates, booleans, etc.)
  - the "no evidence -> null value" contract
  - the hallucination guard (evidence_quote not actually in the OCR text)
  - malformed-output handling (duplicate field, missing field)

Run with: python scripts/test_extraction_service.py
For a real end-to-end call against the live Gemini API, set GEMINI_API_KEY
and use extract_fields() directly with a real OCRDocumentResult.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # repo root, for docs/ access if needed

import app.services.extraction_service as extraction_service
from app.schemas.ocr import OCRDocumentResult, OCRPageResult, PageSourceType


def _fake_ocr_result() -> OCRDocumentResult:
    page2_text = (
        "Gross parental/family income: Rs 4,20,000 per annum\n"
        "Course Mode: Regular"
    )
    page1_text = (
        "Student Name: Priya Kumar\n"
        "Date of Birth: 2006-04-12"
    )
    pages = [
        OCRPageResult(
            page_number=1,
            source_type=PageSourceType.NATIVE_RASTER,
            width_px=1000,
            height_px=1400,
            tokens=[],
            page_text=page1_text,
            mean_confidence=0.95,
            token_count=0,
            warnings=[],
        ),
        OCRPageResult(
            page_number=2,
            source_type=PageSourceType.NATIVE_RASTER,
            width_px=1000,
            height_px=1400,
            tokens=[],
            page_text=page2_text,
            mean_confidence=0.94,
            token_count=0,
            warnings=[],
        ),
    ]
    return OCRDocumentResult(
        file_path="fake.pdf",
        total_pages=2,
        pages=pages,
        low_confidence_page_numbers=[],
        empty_page_numbers=[],
        overall_mean_confidence=0.945,
        warnings=[],
    )


def _canned_response(fields: list[dict]) -> str:
    return json.dumps({"fields": fields})


HAPPY_PATH_FIELDS = [
    {"field_name": "student_name", "value_text": "Priya Kumar", "evidence_quote": "Student Name: Priya Kumar", "page_number": 1, "uncertainty_reason": None, "model_confidence": 0.98},
    {"field_name": "date_of_birth", "value_text": "2006-04-12", "evidence_quote": "Date of Birth: 2006-04-12", "page_number": 1, "uncertainty_reason": None, "model_confidence": 0.95},
    {"field_name": "board_percentile", "value_text": None, "evidence_quote": None, "page_number": None, "uncertainty_reason": "board percentile not present in supplied text", "model_confidence": 0.0},
    {"field_name": "course_mode", "value_text": "Regular", "evidence_quote": "Course Mode: Regular", "page_number": 2, "uncertainty_reason": None, "model_confidence": 0.97},
    {"field_name": "institution_name", "value_text": None, "evidence_quote": None, "page_number": None, "uncertainty_reason": "institution name not present in supplied text", "model_confidence": 0.0},
    {"field_name": "institution_recognized", "value_text": None, "evidence_quote": None, "page_number": None, "uncertainty_reason": "recognition status not present in supplied text", "model_confidence": 0.0},
    {"field_name": "family_income", "value_text": "Rs 4,20,000 per annum", "evidence_quote": "Gross parental/family income: Rs 4,20,000 per annum", "page_number": 2, "uncertainty_reason": None, "model_confidence": 0.96},
    {"field_name": "other_scholarship", "value_text": None, "evidence_quote": None, "page_number": None, "uncertainty_reason": "not mentioned in supplied text", "model_confidence": 0.0},
    {"field_name": "application_date", "value_text": None, "evidence_quote": None, "page_number": None, "uncertainty_reason": "not present in supplied text", "model_confidence": 0.0},
]


def test_happy_path(monkeypatch):
    monkeypatch.setattr(extraction_service, "_build_gemini_client", lambda: object())
    monkeypatch.setattr(extraction_service, "_call_gemini", lambda client, prompt: _canned_response(HAPPY_PATH_FIELDS))

    candidates = extraction_service.extract_fields(_fake_ocr_result())
    by_name = {c.field_name.value: c for c in candidates}

    assert len(candidates) == 9, f"expected 9 candidates, got {len(candidates)}"
    assert by_name["family_income"].value == 420000, by_name["family_income"]
    assert by_name["date_of_birth"].value == "2006-04-12"
    assert by_name["course_mode"].value == "Regular"
    assert by_name["board_percentile"].value is None
    assert by_name["board_percentile"].uncertainty_reason
    print("test_happy_path: PASS")


def test_hallucinated_evidence_is_downgraded(monkeypatch):
    monkeypatch.setattr(extraction_service, "_build_gemini_client", lambda: object())
    fields = [dict(f) for f in HAPPY_PATH_FIELDS]
    # Claim a quote that does NOT appear anywhere in the fake OCR text.
    for f in fields:
        if f["field_name"] == "student_name":
            f["evidence_quote"] = "This sentence was never in the OCR text at all"
    monkeypatch.setattr(extraction_service, "_call_gemini", lambda client, prompt: _canned_response(fields))

    candidates = extraction_service.extract_fields(_fake_ocr_result())
    by_name = {c.field_name.value: c for c in candidates}
    assert by_name["student_name"].value is None, "hallucinated evidence should downgrade value to None"
    assert by_name["student_name"].uncertainty_reason
    print("test_hallucinated_evidence_is_downgraded: PASS")


def test_duplicate_field_raises(monkeypatch):
    monkeypatch.setattr(extraction_service, "_build_gemini_client", lambda: object())
    fields = [dict(f) for f in HAPPY_PATH_FIELDS] + [dict(HAPPY_PATH_FIELDS[0])]  # duplicate student_name
    monkeypatch.setattr(extraction_service, "_call_gemini", lambda client, prompt: _canned_response(fields))

    try:
        extraction_service.extract_fields(_fake_ocr_result())
        raise AssertionError("expected MalformedGeminiOutputError")
    except extraction_service.MalformedGeminiOutputError as exc:
        print(f"test_duplicate_field_raises: PASS ({exc})")


def test_missing_field_is_synthesized_not_fatal(monkeypatch):
    monkeypatch.setattr(extraction_service, "_build_gemini_client", lambda: object())
    fields = [f for f in HAPPY_PATH_FIELDS if f["field_name"] != "other_scholarship"]
    monkeypatch.setattr(extraction_service, "_call_gemini", lambda client, prompt: _canned_response(fields))

    candidates = extraction_service.extract_fields(_fake_ocr_result())
    by_name = {c.field_name.value: c for c in candidates}
    assert len(candidates) == 9
    assert by_name["other_scholarship"].value is None
    assert "did not return" in by_name["other_scholarship"].uncertainty_reason
    print("test_missing_field_is_synthesized_not_fatal: PASS")


def test_malformed_json_raises(monkeypatch):
    monkeypatch.setattr(extraction_service, "_build_gemini_client", lambda: object())
    monkeypatch.setattr(extraction_service, "_call_gemini", lambda client, prompt: "not json at all {{{")

    try:
        extraction_service.extract_fields(_fake_ocr_result())
        raise AssertionError("expected MalformedGeminiOutputError")
    except extraction_service.MalformedGeminiOutputError as exc:
        print(f"test_malformed_json_raises: PASS ({exc})")


def test_missing_api_key_raises(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setattr(extraction_service.settings, "GEMINI_API_KEY", "")
    monkeypatch.setattr(extraction_service.settings, "GROQ_API_KEY", "")
    try:
        extraction_service.extract_fields(_fake_ocr_result())
        raise AssertionError("expected ExtractionConfigError")
    except extraction_service.ExtractionConfigError as exc:
        print(f"test_missing_api_key_raises: PASS ({exc})")


class _FakeMonkeyPatch:
    """Minimal stand-in for pytest's monkeypatch fixture so this script runs
    standalone without pytest installed."""

    def __init__(self):
        self._restores = []

    def setattr(self, target, name, value):
        old = getattr(target, name)
        self._restores.append((target, name, old))
        setattr(target, name, value)

    def delenv(self, name, raising=False):
        import os
        old = os.environ.pop(name, None)
        self._restores.append((os.environ, name, old))

    def undo(self):
        import os
        for target, name, old in reversed(self._restores):
            if target is os.environ:
                if old is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = old
            else:
                setattr(target, name, old)


def main():
    import os
    os.environ.setdefault("GEMINI_API_KEY", "test-key-not-real")

    tests = [
        test_happy_path,
        test_hallucinated_evidence_is_downgraded,
        test_duplicate_field_raises,
        test_missing_field_is_synthesized_not_fatal,
        test_malformed_json_raises,
        test_missing_api_key_raises,
    ]
    for test in tests:
        mp = _FakeMonkeyPatch()
        try:
            test(mp)
        finally:
            mp.undo()
            import os as _os
            _os.environ.setdefault("GEMINI_API_KEY", "test-key-not-real")

    print("\nAll extraction_service smoke tests passed.")


if __name__ == "__main__":
    main()
