"""
evidence_service.py — Person 1 / Person 2 (per README: "Person 1 / Person 2
(evidence_service.py after fuzzy matching + validation)")

    ExtractionCandidate (Gemini's proposal)
            +
    OCRDocumentResult (Tesseract's ground truth)
            ↓
    ValidatedField  (docs/contracts/validated_field.json)

CORE PRINCIPLE: Tesseract OCR is the source of truth. Gemini only proposes a
field_name/value_text/evidence_quote/page_number/model_confidence — none of
that is trusted just because it satisfied Pydantic validation in
extraction_service.py. This file independently re-derives, from the raw OCR
tokens alone, whether the proposed evidence actually exists in the document,
where it actually is, and whether the proposed value is actually consistent
with what's written there. If it can't independently confirm that, the field
is UNTRUSTED — no exceptions, no benefit of the doubt.

This module is 100% deterministic: normalization, exact/substring matching,
and RapidFuzz string similarity only. No LLM call of any kind happens here,
and this file never imports google.genai or app.services.extraction_service.

NOT implemented here (out of scope by design): policy rules, eligibility
decisions, audit hash chains, replay, blockchain. Those are other people's
files.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from rapidfuzz import fuzz

from app.schemas.extraction import ExtractionCandidate, FieldName
from app.schemas.ocr import OCRDocumentResult, OCRPageResult, OCRToken
from app.schemas.validation import (
    BoundingBox,
    FieldTrustStatus,
    ValidatedField,
    ValidationStatus,
)

logger = logging.getLogger(__name__)

# --- Tunables ----------------------------------------------------------

FUZZY_MATCH_THRESHOLD = 90.0  # RapidFuzz partial_ratio scale is 0-100; the
                              # brief's ">= 0.90" similarity requirement.

# Fields whose value_text is expected to contain digits (currency, percentile,
# calendar dates) that must be independently confirmed against the matched
# OCR span, per the brief's rule 9. Everything else (names, course_mode,
# booleans-as-text) is validated on textual similarity alone.
NUMERIC_OR_DATE_FIELDS = frozenset(
    {
        FieldName.FAMILY_INCOME,
        FieldName.BOARD_PERCENTILE,
        FieldName.DATE_OF_BIRTH,
        FieldName.APPLICATION_DATE,
    }
)

# Safety valve for the "find every occurrence on this page" masking loop —
# a legitimate document will never repeat the same evidence 6+ times: if it
# does, something is wrong with normalization, not with the document.
MAX_MATCH_ITERATIONS_PER_PAGE = 5


# --- Internal data structures --------------------------------------------

@dataclass
class _TokenSpan:
    """Where one OCR token landed in a page's normalized, concatenated text."""

    start: int
    end: int
    token: OCRToken


@dataclass
class _Match:
    """One located occurrence of a candidate's evidence_quote in the OCR text."""

    page_number: int
    score: float  # 0-100, RapidFuzz scale (100 for an exact match)
    tokens: List[OCRToken] = field(default_factory=list)


# --- Public API ----------------------------------------------------------

def validate_fields(
    candidates: List[ExtractionCandidate],
    ocr_result: OCRDocumentResult,
) -> List[ValidatedField]:
    """
    Independently verify every ExtractionCandidate against the OCR ground
    truth and return one ValidatedField per candidate (same order, same
    field_name set — this never drops or adds fields).
    """
    return [_validate_single_field(c, ocr_result) for c in candidates]


def _validate_single_field(
    candidate: ExtractionCandidate,
    ocr_result: OCRDocumentResult,
) -> ValidatedField:
    # Rule 1: no proposed value -> MISSING, full stop. Nothing to verify.
    if candidate.value is None:
        return _missing_result(candidate)

    # Rule 2: a value with no evidence_quote can never be trusted. This
    # should already be impossible per ExtractionCandidate's own validator
    # (app/schemas/extraction.py), but we check again here rather than
    # assuming upstream Pydantic validation is a substitute for our own
    # verification — that's the whole point of this file.
    if not candidate.evidence_quote or not candidate.evidence_quote.strip():
        logger.warning(
            "field '%s': value present but evidence_quote missing/blank; treating as UNTRUSTED",
            candidate.field_name.value,
        )
        return _unmatched_result(candidate)

    # Rules 3-8: locate the evidence in the OCR ground truth. We deliberately
    # search EVERY page, not just candidate.page_number — Gemini's claimed
    # page is not trusted either (see module docstring / brief rule 11).
    matches = _find_all_matches_in_document(candidate.evidence_quote, ocr_result)

    if not matches:
        logger.warning(
            "field '%s': evidence_quote not found anywhere in OCR text (claimed page %s)",
            candidate.field_name.value,
            candidate.page_number,
        )
        return _unmatched_result(candidate)

    if len(matches) > 1:
        logger.warning(
            "field '%s': evidence_quote matched %d distinct locations (pages %s); "
            "refusing to guess which one is correct",
            candidate.field_name.value,
            len(matches),
            sorted({m.page_number for m in matches}),
        )
        return _ambiguous_result(candidate)

    match = matches[0]
    if candidate.page_number is not None and match.page_number != candidate.page_number:
        logger.info(
            "field '%s': Gemini claimed page %s but evidence was actually located on page %s; "
            "using the located page, not the claim",
            candidate.field_name.value,
            candidate.page_number,
            match.page_number,
        )

    # Rule 9: for numeric/date fields, the value itself (not just the
    # surrounding sentence) must agree with what's actually on the page.
    numeric_ok, conflict_reason = _verify_numeric_or_date_value(candidate, match)
    if not numeric_ok:
        logger.warning(
            "field '%s': %s",
            candidate.field_name.value,
            conflict_reason,
        )
        return _conflict_result(candidate, match)

    return _validated_result(candidate, match)


# --- Result builders -------------------------------------------------------

def _missing_result(candidate: ExtractionCandidate) -> ValidatedField:
    return ValidatedField(
        field_name=candidate.field_name,
        normalized_value=None,
        status=FieldTrustStatus.UNTRUSTED,
        validation_status=ValidationStatus.MISSING,
        ocr_confidence=0.0,
        evidence_match_score=0.0,
        model_confidence=candidate.model_confidence,
        final_confidence=0.0,
        evidence_quote=None,
        source_page=None,
        bounding_box=None,
    )


def _unmatched_result(candidate: ExtractionCandidate) -> ValidatedField:
    """Evidence quote is missing outright, or could not be located anywhere
    in the OCR text — Gemini supplied unsupported information."""
    return ValidatedField(
        field_name=candidate.field_name,
        normalized_value=None,
        status=FieldTrustStatus.UNTRUSTED,
        validation_status=ValidationStatus.INVALID,
        ocr_confidence=0.0,
        evidence_match_score=0.0,
        model_confidence=candidate.model_confidence,
        final_confidence=0.0,
        evidence_quote=candidate.evidence_quote,  # kept for a human reviewer to see what Gemini claimed
        source_page=None,
        bounding_box=None,
    )


def _ambiguous_result(candidate: ExtractionCandidate) -> ValidatedField:
    """Evidence matched more than once and we cannot deterministically pick
    the right occurrence — we do not guess."""
    return ValidatedField(
        field_name=candidate.field_name,
        normalized_value=None,
        status=FieldTrustStatus.UNTRUSTED,
        validation_status=ValidationStatus.AMBIGUOUS,
        ocr_confidence=0.0,
        evidence_match_score=0.0,
        model_confidence=candidate.model_confidence,
        final_confidence=0.0,
        evidence_quote=candidate.evidence_quote,
        source_page=None,
        bounding_box=None,
    )


def _conflict_result(candidate: ExtractionCandidate, match: "_Match") -> ValidatedField:
    """Text matched (>= threshold) but the actual numeric/date value on the
    page disagrees with what Gemini proposed — e.g. Gemini said 4,20,000 and
    the page says 5,20,000. The sentence is real; the value is not."""
    ocr_conf = _ocr_confidence(match.tokens)
    match_score = round(match.score / 100.0, 4)
    return ValidatedField(
        field_name=candidate.field_name,
        normalized_value=None,
        status=FieldTrustStatus.UNTRUSTED,
        validation_status=ValidationStatus.INVALID,
        ocr_confidence=ocr_conf,  # preserved from OCR tokens, never replaced by model_confidence
        evidence_match_score=match_score,
        model_confidence=candidate.model_confidence,
        final_confidence=0.0,
        evidence_quote=candidate.evidence_quote,
        source_page=match.page_number,
        bounding_box=_union_bounding_box(match.tokens),
    )


def _validated_result(candidate: ExtractionCandidate, match: "_Match") -> ValidatedField:
    ocr_conf = _ocr_confidence(match.tokens)
    match_score = round(match.score / 100.0, 4)
    final_conf = round((ocr_conf + match_score + candidate.model_confidence) / 3.0, 4)
    return ValidatedField(
        field_name=candidate.field_name,
        normalized_value=candidate.value,
        status=FieldTrustStatus.VALIDATED,
        validation_status=ValidationStatus.VALID,
        ocr_confidence=ocr_conf,  # preserved from OCR tokens, never replaced by model_confidence
        evidence_match_score=match_score,
        model_confidence=candidate.model_confidence,
        final_confidence=final_conf,
        evidence_quote=candidate.evidence_quote,
        source_page=match.page_number,
        bounding_box=_union_bounding_box(match.tokens),
    )


def _ocr_confidence(tokens: List[OCRToken]) -> float:
    if not tokens:
        return 0.0
    return round(sum(t.confidence for t in tokens) / len(tokens), 4)


def _union_bounding_box(tokens: List[OCRToken]) -> BoundingBox:
    x = min(t.left for t in tokens)
    y = min(t.top for t in tokens)
    right = max(t.left + t.width for t in tokens)
    bottom = max(t.top + t.height for t in tokens)
    return BoundingBox(x=x, y=y, width=right - x, height=bottom - y)


# --- Numeric/date value verification (rule 9) --------------------------

_DIGIT_RE = re.compile(r"\d")


def _extract_digits(text: Optional[str]) -> str:
    if not text:
        return ""
    return "".join(_DIGIT_RE.findall(text))


def _verify_numeric_or_date_value(
    candidate: ExtractionCandidate,
    match: "_Match",
) -> Tuple[bool, Optional[str]]:
    """
    For family_income / board_percentile / date_of_birth / application_date:
    confirm the digits Gemini's value_text is built from actually appear in
    the OCR tokens that make up the matched evidence span. This catches the
    case where the surrounding sentence matches almost perfectly (say, 48/49
    characters) but the one thing that matters — the number — is wrong,
    which a pure text-similarity score would not reliably catch (a single
    wrong digit barely moves a ~50-character similarity score).
    """
    if candidate.field_name not in NUMERIC_OR_DATE_FIELDS:
        return True, None

    expected_digits = _extract_digits(candidate.value_text)
    if not expected_digits:
        # Nothing digit-like to check against (shouldn't normally happen for
        # these fields, since extraction_service's normalizers require
        # digits to produce a typed value) — don't fail a field over our own
        # inability to check it; text-similarity match already passed.
        return True, None

    matched_raw_text = " ".join(t.token for t in match.tokens)
    actual_digits = _extract_digits(matched_raw_text)

    if expected_digits in actual_digits:
        return True, None

    return False, (
        f"value_text digits '{expected_digits}' do not appear in the matched OCR "
        f"evidence's digits '{actual_digits}' — Gemini's sentence matched the "
        "document but its proposed value does not"
    )


# --- Text normalization ---------------------------------------------------
# Deliberately conservative: strip punctuation/symbols and collapse
# whitespace/case so that common OCR punctuation noise (curly vs straight
# quotes, stray commas, extra spaces) doesn't block a legitimate match, while
# leaving digits and letters untouched so numeric verification above still
# works on the real characters.

def _normalize_word(word: str) -> str:
    normalized = unicodedata.normalize("NFKC", word).lower()
    normalized = re.sub(r"[^\w\s]", "", normalized, flags=re.UNICODE)
    return normalized.strip()


def _normalize_quote(quote: str) -> str:
    words = (_normalize_word(w) for w in quote.split())
    return " ".join(w for w in words if w)


# --- Locating a quote in the OCR ground truth --------------------------

def _build_page_index(tokens: List[OCRToken]) -> Tuple[str, List[_TokenSpan]]:
    """Builds a normalized, space-joined string from a page's OCR tokens plus
    a parallel list of (start,end)->token spans, so a matched character range
    in the normalized string can be mapped back to real OCR tokens (and
    therefore back to real bounding boxes)."""
    parts: List[str] = []
    spans: List[_TokenSpan] = []
    cursor = 0
    for tok in tokens:
        normalized = _normalize_word(tok.token)
        if not normalized:
            continue  # a token that is pure punctuation carries no matchable text
        start = cursor
        parts.append(normalized)
        cursor += len(normalized)
        spans.append(_TokenSpan(start=start, end=cursor, token=tok))
        parts.append(" ")
        cursor += 1
    return "".join(parts), spans


def _tokens_overlapping(spans: List[_TokenSpan], start: int, end: int) -> List[OCRToken]:
    return [s.token for s in spans if s.start < end and s.end > start]


def _find_matches_on_page(
    quote_norm: str,
    page_text_norm: str,
    spans: List[_TokenSpan],
    page_number: int,
) -> List[_Match]:
    matches: List[_Match] = []

    # Step 6: exact substring match first — find every non-overlapping
    # occurrence, since a repeated exact phrase is exactly the "multiple
    # possible matches" case we must not silently resolve.
    search_from = 0
    found_exact = False
    while True:
        idx = page_text_norm.find(quote_norm, search_from)
        if idx == -1:
            break
        end = idx + len(quote_norm)
        matched_tokens = _tokens_overlapping(spans, idx, end)
        if matched_tokens:
            matches.append(_Match(page_number=page_number, score=100.0, tokens=matched_tokens))
            found_exact = True
        search_from = end
    if found_exact:
        return matches

    # Step 7-8: RapidFuzz fuzzy alignment, only if exact matching found
    # nothing at all on this page. We repeatedly locate the best remaining
    # alignment and mask it out, so a phrase that legitimately appears twice
    # (near-)identically is still detected as two matches rather than one.
    working = list(page_text_norm)
    for _ in range(MAX_MATCH_ITERATIONS_PER_PAGE):
        current_text = "".join(working)
        if not current_text.strip():
            break
        alignment = fuzz.partial_ratio_alignment(quote_norm, current_text)
        if alignment is None or alignment.score < FUZZY_MATCH_THRESHOLD:
            break
        dest_start, dest_end = alignment.dest_start, alignment.dest_end
        matched_tokens = _tokens_overlapping(spans, dest_start, dest_end)
        if matched_tokens:
            matches.append(_Match(page_number=page_number, score=alignment.score, tokens=matched_tokens))
        for i in range(dest_start, dest_end):
            working[i] = "\uffff"  # sentinel that can never match real text again

    return matches


def _find_all_matches_in_document(
    evidence_quote: str,
    ocr_result: OCRDocumentResult,
) -> List[_Match]:
    quote_norm = _normalize_quote(evidence_quote)
    if not quote_norm:
        return []

    all_matches: List[_Match] = []
    for page in ocr_result.pages:
        page_text_norm, spans = _build_page_index(page.tokens)
        if not page_text_norm.strip():
            continue
        all_matches.extend(_find_matches_on_page(quote_norm, page_text_norm, spans, page.page_number))
    return all_matches
