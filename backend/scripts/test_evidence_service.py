"""
Offline tests for app/services/evidence_service.py.

Fully deterministic — no Gemini call, no Tesseract call, no network. Builds
OCRDocumentResult / ExtractionCandidate objects by hand so each of the 12
required scenarios is isolated and reproducible.

Run with: python scripts/test_evidence_service.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.schemas.extraction import ExtractionCandidate, FieldName
from app.schemas.ocr import OCRDocumentResult, OCRPageResult, OCRToken, PageSourceType
from app.schemas.validation import FieldTrustStatus, ValidationStatus
from app.services import evidence_service


# --- Helpers to build fixtures quickly --------------------------------------

def _token(text: str, left: int, top: int, width: int = 40, height: int = 20,
           confidence: float = 0.95, line_no: int = 1, block_no: int = 1, page_number: int = 1) -> OCRToken:
    return OCRToken(
        page_number=page_number,
        token=text,
        left=left,
        top=top,
        width=width,
        height=height,
        confidence=confidence,
        line_no=line_no,
        block_no=block_no,
    )


def _tokens_from_words(words: list[str], page_number: int = 1, start_left: int = 100, top: int = 300,
                        gap: int = 45, confidence: float = 0.95, line_no: int = 1) -> list[OCRToken]:
    tokens = []
    left = start_left
    for w in words:
        width = max(20, len(w) * 12)
        tokens.append(_token(w, left, top, width=width, confidence=confidence, line_no=line_no, page_number=page_number))
        left += width + gap
    return tokens


def _page(tokens: list[OCRToken], page_number: int = 1) -> OCRPageResult:
    text = " ".join(t.token for t in tokens)
    mean_conf = sum(t.confidence for t in tokens) / len(tokens) if tokens else 0.0
    return OCRPageResult(
        page_number=page_number,
        source_type=PageSourceType.NATIVE_RASTER,
        width_px=2000,
        height_px=2800,
        tokens=tokens,
        page_text=text,
        mean_confidence=round(mean_conf, 4),
        token_count=len(tokens),
        warnings=[],
    )


def _doc(pages: list[OCRPageResult]) -> OCRDocumentResult:
    confs = [p.mean_confidence for p in pages if p.token_count > 0]
    return OCRDocumentResult(
        file_path="fixture.pdf",
        total_pages=len(pages),
        pages=pages,
        low_confidence_page_numbers=[p.page_number for p in pages if p.mean_confidence < 0.6],
        empty_page_numbers=[],
        overall_mean_confidence=round(sum(confs) / len(confs), 4) if confs else 0.0,
        warnings=[],
    )


def _candidate(
    field_name: FieldName,
    value,
    value_text,
    evidence_quote,
    page_number,
    model_confidence: float = 0.95,
) -> ExtractionCandidate:
    return ExtractionCandidate(
        field_name=field_name,
        value=value,
        value_text=value_text,
        evidence_quote=evidence_quote,
        page_number=page_number,
        uncertainty_reason=None,
        model_confidence=model_confidence,
    )


PASS = []
FAIL = []


def check(name: str, condition: bool, detail: str = ""):
    if condition:
        PASS.append(name)
        print(f"PASS: {name}")
    else:
        FAIL.append(name)
        print(f"FAIL: {name} {detail}")


# --- 1. Exact quote match -> VALIDATED --------------------------------------

def test_1_exact_match():
    words = "Gross parental family income Rs 420000 per annum".split()
    tokens = _tokens_from_words(words, page_number=1)
    doc = _doc([_page(tokens, page_number=1)])
    candidate = _candidate(
        FieldName.FAMILY_INCOME, 420000, "Rs 420000 per annum",
        "Gross parental family income Rs 420000 per annum", page_number=1,
    )
    [result] = evidence_service.validate_fields([candidate], doc)
    check("1. exact match -> VALIDATED", result.status == FieldTrustStatus.VALIDATED and result.validation_status == ValidationStatus.VALID)
    check("1. exact match evidence_match_score == 1.0", result.evidence_match_score == 1.0)


# --- 2. Case/whitespace differences -> VALIDATED ----------------------------

def test_2_case_whitespace_differences():
    words = "GROSS   PARENTAL FAMILY INCOME RS 420000 PER ANNUM".split()
    tokens = _tokens_from_words(words, page_number=1)
    doc = _doc([_page(tokens, page_number=1)])
    candidate = _candidate(
        FieldName.FAMILY_INCOME, 420000, "Rs 420000 per annum",
        "gross parental family income rs 420000 per annum", page_number=1,
    )
    [result] = evidence_service.validate_fields([candidate], doc)
    check("2. case/whitespace -> VALIDATED", result.status == FieldTrustStatus.VALIDATED)


# --- 3. Minor OCR typo, RapidFuzz >= 0.90 -> VALIDATED ----------------------

def test_3_minor_typo_fuzzy_match():
    # OCR misread "family" as "famity" (one character error)
    words = "Gross parental famity income Rs 420000 per annum".split()
    tokens = _tokens_from_words(words, page_number=1)
    doc = _doc([_page(tokens, page_number=1)])
    candidate = _candidate(
        FieldName.FAMILY_INCOME, 420000, "Rs 420000 per annum",
        "Gross parental family income Rs 420000 per annum", page_number=1,
    )
    [result] = evidence_service.validate_fields([candidate], doc)
    check(
        "3. minor OCR typo (fuzzy >= 0.90) -> VALIDATED",
        result.status == FieldTrustStatus.VALIDATED,
        detail=f"got status={result.status}, match_score={result.evidence_match_score}",
    )


# --- 4. Similarity below 0.90 -> UNTRUSTED ----------------------------------

def test_4_similarity_below_threshold():
    words = "Totally unrelated sentence about something else entirely here".split()
    tokens = _tokens_from_words(words, page_number=1)
    doc = _doc([_page(tokens, page_number=1)])
    candidate = _candidate(
        FieldName.FAMILY_INCOME, 420000, "Rs 420000 per annum",
        "Gross parental family income Rs 420000 per annum", page_number=1,
    )
    [result] = evidence_service.validate_fields([candidate], doc)
    check(
        "4. similarity below 0.90 -> UNTRUSTED",
        result.status == FieldTrustStatus.UNTRUSTED and result.validation_status == ValidationStatus.INVALID,
    )


# --- 5. Gemini value absent from OCR -> UNTRUSTED ---------------------------

def test_5_value_absent_from_ocr():
    words = "This page is a certificate cover sheet with no numbers at all".split()
    tokens = _tokens_from_words(words, page_number=1)
    doc = _doc([_page(tokens, page_number=1)])
    candidate = _candidate(
        FieldName.FAMILY_INCOME, 420000, "Rs 420000 per annum",
        "Gross parental family income Rs 420000 per annum", page_number=1,
    )
    [result] = evidence_service.validate_fields([candidate], doc)
    check("5. value absent from OCR -> UNTRUSTED", result.status == FieldTrustStatus.UNTRUSTED)


# --- 6. Evidence quote absent from OCR (empty page) -> UNTRUSTED ------------

def test_6_evidence_quote_absent_empty_page():
    doc = _doc([_page([], page_number=1)])
    candidate = _candidate(
        FieldName.STUDENT_NAME, "Priya Kumar", "Priya Kumar",
        "Student Name: Priya Kumar", page_number=1,
    )
    [result] = evidence_service.validate_fields([candidate], doc)
    check(
        "6. evidence absent from OCR (empty page) -> UNTRUSTED",
        result.status == FieldTrustStatus.UNTRUSTED and result.validation_status == ValidationStatus.INVALID,
    )


# --- 7. Numeric mismatch: Gemini 4,20,000 vs OCR 5,20,000 -> UNTRUSTED ------

def test_7_numeric_mismatch():
    words = "Gross parental family income Rs 520000 per annum".split()
    tokens = _tokens_from_words(words, page_number=1)
    doc = _doc([_page(tokens, page_number=1)])
    candidate = _candidate(
        FieldName.FAMILY_INCOME, 420000, "Rs 4,20,000 per annum",
        "Gross parental family income Rs 4,20,000 per annum", page_number=1,
    )
    [result] = evidence_service.validate_fields([candidate], doc)
    check(
        "7. numeric mismatch 420000 vs 520000 -> UNTRUSTED",
        result.status == FieldTrustStatus.UNTRUSTED and result.validation_status == ValidationStatus.INVALID,
        detail=f"got status={result.status}, normalized_value={result.normalized_value}",
    )


# --- 8. Missing field -> MISSING ---------------------------------------------

def test_8_missing_field():
    doc = _doc([_page(_tokens_from_words(["Nothing", "relevant", "here"]), page_number=1)])
    candidate = ExtractionCandidate(
        field_name=FieldName.OTHER_SCHOLARSHIP,
        value=None,
        value_text=None,
        evidence_quote=None,
        page_number=None,
        uncertainty_reason="not mentioned in supplied text",
        model_confidence=0.0,
    )
    [result] = evidence_service.validate_fields([candidate], doc)
    check(
        "8. missing field -> MISSING",
        result.status == FieldTrustStatus.UNTRUSTED and result.validation_status == ValidationStatus.MISSING,
    )


# --- 9. Multiple possible evidence matches -> AMBIGUOUS ---------------------

def test_9_multiple_possible_matches():
    words_page1 = "Course Mode Regular as per the enclosed marksheet".split()
    words_page2 = "Note Course Mode Regular also applies to the previous year".split()
    doc = _doc(
        [
            _page(_tokens_from_words(words_page1, page_number=1), page_number=1),
            _page(_tokens_from_words(words_page2, page_number=2), page_number=2),
        ]
    )
    candidate = _candidate(
        FieldName.COURSE_MODE, "Regular", "Regular",
        "Course Mode Regular", page_number=1,
    )
    [result] = evidence_service.validate_fields([candidate], doc)
    check(
        "9. multiple possible matches -> AMBIGUOUS",
        result.status == FieldTrustStatus.UNTRUSTED and result.validation_status == ValidationStatus.AMBIGUOUS,
        detail=f"got status={result.status}, validation_status={result.validation_status}",
    )


# --- 10. Multi-token evidence -> correct union bounding box -----------------

def test_10_multi_token_bounding_box():
    words = "Gross parental family income Rs 420000 per annum".split()
    tokens = _tokens_from_words(words, page_number=1, start_left=100, top=500)
    doc = _doc([_page(tokens, page_number=1)])
    candidate = _candidate(
        FieldName.FAMILY_INCOME, 420000, "Rs 420000 per annum",
        "Gross parental family income Rs 420000 per annum", page_number=1,
    )
    [result] = evidence_service.validate_fields([candidate], doc)
    expected_x = min(t.left for t in tokens)
    expected_y = min(t.top for t in tokens)
    expected_right = max(t.left + t.width for t in tokens)
    expected_bottom = max(t.top + t.height for t in tokens)
    ok = (
        result.bounding_box is not None
        and result.bounding_box.x == expected_x
        and result.bounding_box.y == expected_y
        and result.bounding_box.x + result.bounding_box.width == expected_right
        and result.bounding_box.y + result.bounding_box.height == expected_bottom
    )
    check("10. multi-token evidence -> correct union bounding box", ok, detail=str(result.bounding_box))


# --- 11. Evidence on wrong claimed page -> located deterministically --------

def test_11_wrong_claimed_page():
    words_page1 = "Cover sheet with no income information".split()
    words_page2 = "Gross parental family income Rs 420000 per annum".split()
    doc = _doc(
        [
            _page(_tokens_from_words(words_page1, page_number=1), page_number=1),
            _page(_tokens_from_words(words_page2, page_number=2), page_number=2),
        ]
    )
    # Gemini incorrectly claims this evidence is on page 1; it's actually on page 2.
    candidate = _candidate(
        FieldName.FAMILY_INCOME, 420000, "Rs 420000 per annum",
        "Gross parental family income Rs 420000 per annum", page_number=1,
    )
    [result] = evidence_service.validate_fields([candidate], doc)
    check(
        "11. wrong claimed page -> located on real page (2), not the claim (1)",
        result.status == FieldTrustStatus.VALIDATED and result.source_page == 2,
        detail=f"got status={result.status}, source_page={result.source_page}",
    )


# --- 12. Low OCR confidence -> confidence preserved, not replaced -----------

def test_12_low_ocr_confidence_preserved():
    words = "Gross parental family income Rs 420000 per annum".split()
    tokens = _tokens_from_words(words, page_number=1, confidence=0.42)
    doc = _doc([_page(tokens, page_number=1)])
    candidate = _candidate(
        FieldName.FAMILY_INCOME, 420000, "Rs 420000 per annum",
        "Gross parental family income Rs 420000 per annum", page_number=1,
        model_confidence=0.99,  # deliberately high, to prove it does NOT leak into ocr_confidence
    )
    [result] = evidence_service.validate_fields([candidate], doc)
    check(
        "12. low OCR confidence preserved, not replaced by model_confidence",
        result.status == FieldTrustStatus.VALIDATED and abs(result.ocr_confidence - 0.42) < 1e-6 and result.model_confidence == 0.99,
        detail=f"ocr_confidence={result.ocr_confidence}, model_confidence={result.model_confidence}",
    )


def main():
    tests = [
        test_1_exact_match,
        test_2_case_whitespace_differences,
        test_3_minor_typo_fuzzy_match,
        test_4_similarity_below_threshold,
        test_5_value_absent_from_ocr,
        test_6_evidence_quote_absent_empty_page,
        test_7_numeric_mismatch,
        test_8_missing_field,
        test_9_multiple_possible_matches,
        test_10_multi_token_bounding_box,
        test_11_wrong_claimed_page,
        test_12_low_ocr_confidence_preserved,
    ]
    for t in tests:
        t()

    print(f"\n{len(PASS)}/{len(tests)} passed")
    if FAIL:
        print(f"FAILED: {FAIL}")
        sys.exit(1)


if __name__ == "__main__":
    main()
