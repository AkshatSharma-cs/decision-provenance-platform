"""
extraction_service.py — Person 2 (AI / OCR Engineer)

Turns OCR page text into extraction_candidate objects (docs/contracts/
extraction_candidate.json) using Gemini Flash structured JSON output.

ARCHITECTURE RULES THIS FILE ENFORCES IN CODE, NOT JUST IN THE PROMPT:

1. Gemini receives ONLY the OCR page text and the frozen field schema. It
   never sees the original document image, bounding boxes, OCR confidence
   scores, or anything about eligibility/policy. See `_build_prompt`.

2. Gemini never produces a typed value. Its structured-output schema
   (`GeminiRawExtraction`) only has `value_text` (a plain string
   transcription) — never an int/float/bool. All type conversion
   (family_income -> int, board_percentile -> float, course_mode -> enum,
   institution_recognized / other_scholarship -> bool, dates -> ISO) is done
   by deterministic Python normalizers in this file, in `_normalize_value`.
   Gemini cannot invent a typed value it is never asked to produce.

3. Gemini is never asked for and never allowed to return an eligibility
   verdict, a policy-rule result, or a justification for a decision. The
   system instruction explicitly forbids this, the response schema has no
   field that could carry it, and nothing in this file calls a rules
   evaluator.

4. Every candidate with a non-null `value` must carry an `evidence_quote`.
   This is enforced twice: once at the Pydantic layer (`GeminiRawExtraction`
   and `ExtractionCandidate` model validators in app/schemas/extraction.py)
   and once more here after normalization, so a normalizer bug can't smuggle
   a typed value through without evidence.

5. On malformed/uninterpretable Gemini output, this file fails safely
   (raises `ExtractionServiceError`) rather than attempting to repair,
   guess, or silently drop fields. The one deliberate exception: if Gemini
   omits a field entirely, we do not crash the whole batch — we synthesize
   an explicit null/UNCERTAIN candidate for it (this asserts nothing that
   wasn't already true: "we have no information for this field").

Evidence-matching against real OCR tokens (RapidFuzz >= 0.90) is NOT done
here — that is evidence_service.py's job, consuming both this service's
ExtractionCandidate list and ocr_service.py's OCRToken list. This file does
one cheap, non-authoritative sanity check (see `_quote_appears_in_page_text`)
purely to catch blatant hallucination before it leaves this service; it is
not a substitute for evidence_service.py's real match.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from typing import Callable, Optional, Tuple

from click import prompt
from pydantic import ValidationError

from app.core.config import settings
from app.schemas.extraction import (
    ExtractionCandidate,
    FieldName,
    GeminiExtractionResponse,
    GeminiRawExtraction,
)
from app.schemas.ocr import OCRDocumentResult

logger = logging.getLogger(__name__)

# --- Config Helpers ---------------------------------------------------
def _get_gemini_model_name() -> str:
    return os.environ.get("GEMINI_MODEL") or getattr(settings, "GEMINI_MODEL", "gemini-3.6-flash")

def _get_gemini_timeout_ms() -> int:
    raw = os.environ.get("GEMINI_TIMEOUT_MS")
    return int(raw) if raw else getattr(settings, "GEMINI_TIMEOUT_MS", 30000)

def _get_groq_model_name() -> str:
    return os.environ.get("GROQ_MODEL") or getattr(settings, "GROQ_MODEL", "qwen/qwen3.6-27b")

def _get_groq_timeout_s() -> float:
    raw = os.environ.get("GROQ_TIMEOUT_MS")
    ms = int(raw) if raw else getattr(settings, "GROQ_TIMEOUT_MS", 30000)
    return ms / 1000

# The 9 frozen fields, in the exact order/spelling from docs/CONVENTIONS.md.
REQUIRED_FIELD_NAMES: Tuple[FieldName, ...] = tuple(FieldName)


# --- Exceptions --------------------------------------------------------

class ExtractionServiceError(Exception):
    """Base class for every error this module raises."""


class ExtractionConfigError(ExtractionServiceError):
    """Missing/invalid configuration (e.g. GEMINI_API_KEY not set)."""


class GeminiCallError(ExtractionServiceError):
    """The Gemini API call itself failed (network, auth, rate limit, etc.)."""


class MalformedGeminiOutputError(ExtractionServiceError):
    """Gemini returned a response that isn't valid per GeminiExtractionResponse
    (bad JSON, missing required keys, wrong types, duplicate/unknown field
    names, or a value without the evidence_quote the schema requires).

    We do NOT try to repair or reinterpret this — see module docstring
    point 5. The caller should treat this application/document as needing
    a re-run or manual review, not guess at partial results.
    """


# --- Public API ----------------------------------------------------------

def extract_fields(
    ocr_result: OCRDocumentResult,
    *,
    application_public_reference: Optional[str] = None,
) -> list[ExtractionCandidate]:
    """
    Run Gemini structured extraction over an already-OCR'd document and
    return exactly one ExtractionCandidate per frozen field (9 total).

    Args:
        ocr_result: output of app.services.ocr_service.process_document().
            Only `.pages[i].page_text` and `.pages[i].page_number` are sent
            to Gemini — no images, no confidence scores, no bounding boxes.
        application_public_reference: optional, for logging only (e.g.
            "APP-00016"); never sent to Gemini.

    Raises:
        ExtractionConfigError: GEMINI_API_KEY is not set.
        GeminiCallError: the primary and fallback API calls failed.
        MalformedGeminiOutputError: output could not be trusted as-is.

    Never raises for an individual field being unresolved — that shows up
    as a candidate with value=None and a populated uncertainty_reason,
    exactly per the contract.
    """
    client = _build_gemini_client()

    pages_text = [(p.page_number, p.page_text) for p in ocr_result.pages if p.page_text.strip()]
    if not pages_text:
        # Nothing to send Gemini — every field is trivially "not present".
        # This is not malformed output (Gemini was never called), so no
        # exception; just return null candidates honestly.
        logger.warning(
            "extract_fields called with no non-empty OCR page text (application=%s); "
            "returning all-null candidates without calling Gemini",
            application_public_reference,
        )
        return [_null_candidate(f, "no OCR text was available for this document") for f in REQUIRED_FIELD_NAMES]

    prompt = _build_prompt(pages_text)
    try:
        raw_response = _call_gemini(client, prompt)
    except GeminiCallError as exc:
        logger.warning(
            "Gemini call failed (%s); falling back to Groq (application=%s)",
            exc, application_public_reference,
        )
        groq_client = _build_groq_client()
        raw_response = _call_groq(groq_client, prompt)

    parsed = _parse_and_validate_response(raw_response)

    page_text_by_number = {p.page_number: p.page_text for p in ocr_result.pages}
    candidates = [
        _to_extraction_candidate(item, page_text_by_number) for item in parsed.fields
    ]
    return _reconcile_against_required_fields(candidates)


# --- Gemini client / call -------------------------------------------------

def _build_gemini_client():
    api_key = (os.environ.get("GEMINI_API_KEY") or getattr(settings, "GEMINI_API_KEY", "") or "").strip()
    if not api_key:
        raise ExtractionConfigError(
            "GEMINI_API_KEY is not set (see .env.example) — refusing to proceed "
            "rather than silently skipping extraction"
        )
    from google import genai  # imported lazily so the OCR service (and any

    # code path that doesn't need Gemini) never pays this import cost or
    # requires the dependency.
    return genai.Client(api_key=api_key)

def _build_groq_client():
    api_key = (os.environ.get("GROQ_API_KEY") or getattr(settings, "GROQ_API_KEY", "") or "").strip()
    if not api_key:
        raise ExtractionConfigError(
            "GROQ_API_KEY is not set (see .env.example) — refusing to proceed "
            "rather than silently skipping extraction"
        )
    from groq import Groq  # imported lazily, same reasoning as the Gemini import above

    return Groq(api_key=api_key, timeout=_get_groq_timeout_s())

_SYSTEM_INSTRUCTION = """\
You are a text transcription assistant for a government scholarship application \
pipeline. Your ONLY job is to find, for each named field, a plain-text value in \
the supplied OCR text and quote the exact supporting sentence/phrase.

STRICT RULES — you will be evaluated on the second half of this task, not \
just the first:
1. You transcribe what is written in the text. You never calculate, infer, \
   guess, round, translate, or "helpfully" correct a value that is not \
   explicitly present in the text.
2. If a field is not present, or the text is ambiguous / contradictory / \
   illegible, you MUST leave value_text and evidence_quote null and instead \
   explain why in uncertainty_reason. Returning your best guess instead of \
   null is a failure, even if you think the guess is probably right.
3. evidence_quote must be copied from the supplied OCR text as closely as \
   possible — the same words, in the same order, from the same page. Do not \
   paraphrase, summarize, or combine multiple sentences into one quote.
4. You do not decide whether the applicant is eligible for anything. You do \
   not apply any policy or income limit. You do not mention eligibility, \
   pass/fail, or approval anywhere in your output. That is not your job and \
   is handled by a separate system.
5. You only report on the exact fields listed below. You never invent an \
   additional field, and you never omit one of the listed fields from your \
   response — if you have nothing for a field, still include it with \
   value_text=null.
6. model_confidence reflects only your confidence in the ACCURACY OF THE \
   TRANSCRIPTION, nothing else (not the applicant's eligibility, not the \
   document's authenticity).
"""

_FIELD_SCHEMA_FOR_PROMPT = """\
Report on exactly these fields, using exactly these field_name strings:

- student_name (string): the applicant's full name.
- date_of_birth (date): applicant's date of birth. Transcribe as it is \
  written; do not reformat or infer a missing part.
- board_percentile (number, 0-100): the applicant's board exam percentile/ \
  percentage score.
- course_mode (string): must literally be "Regular" or "Distance" as written; \
  if the document uses a different word, transcribe that word as-is and let \
  value_text carry it — do not translate it to Regular/Distance yourself.
- institution_name (string): name of the school/college/institution.
- institution_recognized (string): transcribe whatever the document says \
  about recognition status (e.g. "UGC recognized", "Yes", "Not recognized"); \
  do not convert to true/false yourself.
- family_income (string): the family/parental income figure, transcribed \
  exactly as written including currency symbol/commas if present (e.g. \
  "₹4,20,000 per annum"). Do not do any arithmetic or unit conversion.
- other_scholarship (string): transcribe whatever the document says about \
  whether the applicant holds another scholarship.
- application_date (date): the date the application/form itself was \
  filled/submitted, transcribed as written.
"""


def _build_prompt(pages_text: list[Tuple[int, str]]) -> str:
    """Builds the user-turn content sent to Gemini. Contains ONLY: (1) OCR
    page text, page-tagged, and (2) the field schema/instructions. No images,
    no OCR confidence numbers, no bounding boxes, no policy/rules content."""
    pages_block = "\n\n".join(
        f"--- OCR TEXT: PAGE {page_number} ---\n{text}" for page_number, text in pages_text
    )
    return (
        f"{_FIELD_SCHEMA_FOR_PROMPT}\n"
        f"Here is the OCR text extracted from the document, page by page:\n\n"
        f"{pages_block}\n\n"
        "Return your findings as the structured JSON object described by the "
        "response schema, with exactly one entry per field listed above."
    )


def _call_gemini(client, prompt: str) -> str:
    from google.genai import types
    from google.genai import errors as genai_errors

    config = types.GenerateContentConfig(
        system_instruction=_SYSTEM_INSTRUCTION,
        response_mime_type="application/json",
        response_schema=GeminiExtractionResponse,
        temperature=0.0,  # deterministic transcription, not creative generation
        http_options=types.HttpOptions(timeout=_get_gemini_timeout_ms()),
    )

    try:
        response = client.models.generate_content(
            model=_get_gemini_model_name(),
            contents=prompt,
            config=config,
        )
    except genai_errors.APIError as exc:
        raise GeminiCallError(f"Gemini API call failed: {exc}") from exc
    except Exception as exc:  # network/timeout/etc. not covered by APIError
        raise GeminiCallError(f"Gemini API call failed unexpectedly: {exc}") from exc

    text = getattr(response, "text", None)
    if not text:
        raise MalformedGeminiOutputError("Gemini returned an empty response body")
    return text

def _call_groq(client, prompt: str) -> str:
    """
    Groq equivalent of _call_gemini. Groq's chat.completions API doesn't support
    a strict response_schema like Gemini's structured output, so the JSON shape
    is enforced by (a) response_format={"type": "json_object"} — Groq's best-effort
    JSON mode — and (b) the schema being spelled out explicitly in the system
    instruction below. The returned text is still validated byte-for-byte against
    GeminiExtractionResponse in _parse_and_validate_response, same as the Gemini
    path, so a malformed Groq response fails exactly the same way a malformed
    Gemini response would — no special-casing needed downstream.
    """
    import groq as groq_errors  # for exception types

    json_schema_instruction = (
        _SYSTEM_INSTRUCTION
        + "\n\nRespond with ONLY a single JSON object of this exact shape, no "
        "markdown fences, no prose before or after:\n"
        '{"fields": [{"field_name": str, "value_text": str|null, '
        '"evidence_quote": str|null, "page_number": int|null, '
        '"uncertainty_reason": str|null, "model_confidence": float}]}'
    )

    try:
        response = client.chat.completions.create(
            model=_get_groq_model_name(),
            temperature=0.0,  # deterministic transcription, matching the Gemini config
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": json_schema_instruction},
                {"role": "user", "content": prompt},
            ],
        )
    except groq_errors.APIError as exc:
        raise GeminiCallError(f"Groq API call failed: {exc}") from exc
    except Exception as exc:
        raise GeminiCallError(f"Groq API call failed unexpectedly: {exc}") from exc

    text = response.choices[0].message.content if response.choices else None
    if not text:
        raise MalformedGeminiOutputError("Groq returned an empty response body")
    return text

def _parse_and_validate_response(raw_text: str) -> GeminiExtractionResponse:
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise MalformedGeminiOutputError(f"Gemini output is not valid JSON: {exc}") from exc

    try:
        return GeminiExtractionResponse.model_validate(payload)
    except ValidationError as exc:
        raise MalformedGeminiOutputError(f"Gemini output failed schema validation: {exc}") from exc


def _reconcile_against_required_fields(
    candidates: list[ExtractionCandidate],
) -> list[ExtractionCandidate]:
    by_name: dict[FieldName, list[ExtractionCandidate]] = {}
    for c in candidates:
        by_name.setdefault(c.field_name, []).append(c)

    duplicates = {name: items for name, items in by_name.items() if len(items) > 1}
    if duplicates:
        raise MalformedGeminiOutputError(
            f"Gemini returned more than one entry for field(s): {sorted(n.value for n in duplicates)}; "
            "refusing to guess which is correct"
        )

    result: list[ExtractionCandidate] = []
    for field in REQUIRED_FIELD_NAMES:
        if field in by_name:
            result.append(by_name[field][0])
        else:
            logger.warning("Gemini response omitted required field '%s'; recording as unresolved", field.value)
            result.append(_null_candidate(field, "model did not return this field"))
    return result


def _null_candidate(field_name: FieldName, reason: str) -> ExtractionCandidate:
    return ExtractionCandidate(
        field_name=field_name,
        value=None,
        value_text=None,
        evidence_quote=None,
        page_number=None,
        uncertainty_reason=reason,
        model_confidence=0.0,
    )


# --- Raw Gemini item -> contract-shaped ExtractionCandidate ------------------

def _to_extraction_candidate(
    raw: GeminiRawExtraction,
    page_text_by_number: dict[int, str],
) -> ExtractionCandidate:
    if raw.value_text is None:
        # Gemini already told us it found nothing usable; nothing to normalize.
        return ExtractionCandidate(
            field_name=raw.field_name,
            value=None,
            value_text=None,
            evidence_quote=None,
            page_number=None,
            uncertainty_reason=raw.uncertainty_reason,
            model_confidence=0.0,
        )

    # Cheap, non-authoritative hallucination guard: does the claimed evidence
    # quote actually appear (loosely) on the claimed page? Real evidence
    # matching (RapidFuzz >= 0.90) happens downstream in evidence_service.py;
    # this only catches the blatant case where a quote wasn't in the source
    # text at all.
    page_text = page_text_by_number.get(raw.page_number or -1, "")
    if not _quote_plausibly_in_text(raw.evidence_quote or "", page_text):
        logger.warning(
            "field '%s': evidence_quote not found in OCR text for page %s; "
            "downgrading to unresolved rather than trusting it",
            raw.field_name.value,
            raw.page_number,
        )
        return ExtractionCandidate(
            field_name=raw.field_name,
            value=None,
            value_text=raw.value_text,
            evidence_quote=None,
            page_number=None,
            uncertainty_reason=(
                "model's evidence_quote could not be located in the supplied OCR "
                "text for the claimed page; treating as unverified rather than trusting it"
            ),
            model_confidence=0.0,
        )

    value, normalization_failure_reason = _normalize_value(raw.field_name, raw.value_text)

    if normalization_failure_reason is not None:
        # We have text and a plausible quote, but couldn't safely convert it
        # to the field's typed representation. Per "do not guess", we keep
        # value_text/evidence_quote for a human reviewer to see, but value
        # stays null so it can never reach the rules engine un-normalized.
        return ExtractionCandidate(
            field_name=raw.field_name,
            value=None,
            value_text=raw.value_text,
            evidence_quote=raw.evidence_quote,
            page_number=raw.page_number,
            uncertainty_reason=normalization_failure_reason,
            model_confidence=0.0,
        )

    return ExtractionCandidate(
        field_name=raw.field_name,
        value=value,
        value_text=raw.value_text,
        evidence_quote=raw.evidence_quote,
        page_number=raw.page_number,
        uncertainty_reason=None,
        model_confidence=raw.model_confidence,
    )


def _quote_plausibly_in_text(quote: str, page_text: str) -> bool:
    if not quote.strip() or not page_text.strip():
        return False
    normalize = lambda s: re.sub(r"\s+", " ", s).strip().lower()
    return normalize(quote) in normalize(page_text)


# --- Deterministic, Gemini-free value normalization -------------------------
# Each normalizer takes the raw value_text and returns (typed_value, None) on
# success, or (None, "human-readable reason") on failure. None of these call
# Gemini or any LLM — they are plain Python/regex, so there is no path by
# which a "value" can be invented rather than parsed from what Gemini quoted.

_CURRENCY_STRIP_RE = re.compile(r"[₹Rs.,\s]", re.IGNORECASE)
_PERCENT_RE = re.compile(r"[%\s]")

_TRUE_STRINGS = {"yes", "true", "recognized", "recognised", "y", "1", "affirmed", "confirmed"}
_FALSE_STRINGS = {"no", "false", "not recognized", "not recognised", "unrecognized", "unrecognised", "n", "0", "none"}

_DATE_FORMATS = ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d %B %Y", "%d %b %Y", "%B %d, %Y", "%d.%m.%Y")


def _normalize_student_name(text: str) -> Tuple[Optional[str], Optional[str]]:
    cleaned = text.strip()
    if not cleaned:
        return None, "value_text was blank after trimming whitespace"
    return cleaned, None


def _normalize_institution_name(text: str) -> Tuple[Optional[str], Optional[str]]:
    return _normalize_student_name(text)


def _normalize_date(text: str) -> Tuple[Optional[str], Optional[str]]:
    cleaned = text.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).date().isoformat(), None
        except ValueError:
            continue
    return None, f"could not parse '{cleaned}' as a date in any recognized format"


def _normalize_board_percentile(text: str) -> Tuple[Optional[float], Optional[str]]:
    cleaned = _PERCENT_RE.sub("", text).strip()
    try:
        value = float(cleaned)
    except ValueError:
        return None, f"could not parse '{text}' as a number"
    if not (0.0 <= value <= 100.0):
        return None, f"parsed percentile {value} is outside the valid 0-100 range"
    return value, None


def _normalize_course_mode(text: str) -> Tuple[Optional[str], Optional[str]]:
    cleaned = text.strip().lower()
    if cleaned == "regular":
        return "Regular", None
    if cleaned == "distance":
        return "Distance", None
    return None, f"'{text}' is not one of the two allowed course_mode values (Regular, Distance)"


def _normalize_boolean(text: str) -> Tuple[Optional[bool], Optional[str]]:
    cleaned = text.strip().lower()
    if cleaned in _TRUE_STRINGS or any(cleaned.startswith(t) for t in _TRUE_STRINGS):
        return True, None
    if cleaned in _FALSE_STRINGS or any(cleaned.startswith(t) for t in _FALSE_STRINGS):
        return False, None
    return None, f"'{text}' did not map cleanly to true/false"


def _normalize_family_income(text: str) -> Tuple[Optional[int], Optional[str]]:
    cleaned = _CURRENCY_STRIP_RE.sub("", text)
    # after stripping currency/commas/whitespace, keep only leading digits
    # (e.g. "420000perannum" -> "420000") rather than trying to be clever
    # about units — anything after the number is not a value we invent.
    match = re.match(r"^(\d+)", cleaned)
    if not match:
        return None, f"could not find a plain integer amount in '{text}'"
    return int(match.group(1)), None


_NORMALIZERS: dict[FieldName, Callable[[str], Tuple[Optional[object], Optional[str]]]] = {
    FieldName.STUDENT_NAME: _normalize_student_name,
    FieldName.DATE_OF_BIRTH: _normalize_date,
    FieldName.BOARD_PERCENTILE: _normalize_board_percentile,
    FieldName.COURSE_MODE: _normalize_course_mode,
    FieldName.INSTITUTION_NAME: _normalize_institution_name,
    FieldName.INSTITUTION_RECOGNIZED: _normalize_boolean,
    FieldName.FAMILY_INCOME: _normalize_family_income,
    FieldName.OTHER_SCHOLARSHIP: _normalize_boolean,
    FieldName.APPLICATION_DATE: _normalize_date,
}


def _normalize_value(field_name: FieldName, value_text: str) -> Tuple[Optional[object], Optional[str]]:
    normalizer = _NORMALIZERS[field_name]
    return normalizer(value_text)
