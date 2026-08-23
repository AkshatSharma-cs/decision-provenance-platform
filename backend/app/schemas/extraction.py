"""
Pydantic models for the extraction layer (Person 2 -> Person 1).

Two distinct model layers on purpose:

1. `GeminiRawExtraction` — the ONLY shape Gemini is allowed to produce. It is
   deliberately narrower than the final contract: Gemini emits `value_text`
   (a string transcription of what it read), never a typed `value`. Typed
   values (int for family_income, float for board_percentile, bool for
   institution_recognized, etc.) are produced by deterministic Python
   normalizers in extraction_service.py, NOT by Gemini. This is what keeps
   "Gemini must never invent values" enforceable in code rather than just in
   a prompt: Gemini cannot invent a typed value if it is never asked to
   produce one.

2. `ExtractionCandidate` — matches docs/contracts/extraction_candidate.json,
   i.e. what Person 1's evidence_service.py actually consumes.

NOTE ON A CONTRACT ADDITION:
`docs/contracts/extraction_candidate.json` did not previously include
`model_confidence`, but `docs/contracts/validated_field.json` (the very next
stage) already has a `model_confidence` field with no other stated source for
it. That value has to originate somewhere, and the only candidate is Gemini's
own self-reported confidence at extraction time. So `model_confidence` has
been added to `ExtractionCandidate` and to the contract file in this same PR,
per the README's "update the file in the same PR" rule. **This still needs a
team sign-off post** since it changes a frozen contract file — flagging here
so whoever reviews this PR sees it explicitly rather than discovering it by
diffing JSON.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional, Union

from pydantic import BaseModel, Field, model_validator


class FieldName(str, Enum):
    """The exact 9 frozen fields from docs/CONVENTIONS.md. No more, no fewer.
    Using an enum (rather than a bare str) means Gemini's structured-output
    schema itself restricts field_name to these values — it is not just a
    prompt instruction, the API-level response schema enforces it."""

    STUDENT_NAME = "student_name"
    DATE_OF_BIRTH = "date_of_birth"
    BOARD_PERCENTILE = "board_percentile"
    COURSE_MODE = "course_mode"
    INSTITUTION_NAME = "institution_name"
    INSTITUTION_RECOGNIZED = "institution_recognized"
    FAMILY_INCOME = "family_income"
    OTHER_SCHOLARSHIP = "other_scholarship"
    APPLICATION_DATE = "application_date"


# --- Layer 1: the only shape Gemini is allowed to emit ----------------------

class GeminiRawExtraction(BaseModel):
    """
    One field's raw extraction result, exactly as Gemini must return it.

    Deliberately has NO typed `value` — see module docstring. `value_text`
    is a plain transcription (e.g. "Rs 4,20,000 per annum", "2006-04-12",
    "Regular"); turning that into a typed, validated value is
    extraction_service.py's job, done with plain Python, not Gemini.
    """

    field_name: FieldName
    value_text: Optional[str] = Field(
        default=None,
        description="Plain-text transcription of the value as it appears in the "
        "OCR text. Null if the field is absent or the text is too ambiguous "
        "to transcribe with confidence.",
    )
    evidence_quote: Optional[str] = Field(
        default=None,
        description="A quote copied as closely as possible from the supplied "
        "OCR text that supports value_text. Must be null if value_text is null. "
        "Must never be invented or paraphrased — copy, don't compose.",
    )
    page_number: Optional[int] = Field(
        default=None, ge=1, description="Which supplied OCR page the evidence_quote came from."
    )
    uncertainty_reason: Optional[str] = Field(
        default=None,
        description="Required, human-readable reason when value_text is null "
        "(e.g. 'field not present in supplied text', 'two conflicting income "
        "figures found, cannot disambiguate').",
    )
    model_confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Gemini's own confidence that value_text is a correct, "
        "unambiguous transcription. 0.0 when value_text is null.",
    )

    @model_validator(mode="after")
    def _evidence_and_value_are_consistent(self) -> "GeminiRawExtraction":
        # These are checked again, independently, in extraction_service.py
        # after parsing — duplicated on purpose, since this model only
        # guards Gemini's raw output and extraction_service.py's checks
        # guard the final ExtractionCandidate after normalization.
        if self.value_text is None and self.evidence_quote is not None:
            raise ValueError("evidence_quote present but value_text is null")
        if self.value_text is not None and self.evidence_quote is None:
            raise ValueError("value_text present but evidence_quote is missing")
        if self.value_text is None and not self.uncertainty_reason:
            raise ValueError("value_text is null but uncertainty_reason is missing")
        return self


class GeminiExtractionResponse(BaseModel):
    """Wrapper used as the Gemini response_schema — Gemini must return a JSON
    object with a single `fields` array, one entry per FieldName. Wrapping in
    an object (rather than a bare top-level array) is more reliable for
    structured-output mode across providers than a bare list schema."""

    fields: list[GeminiRawExtraction]


# --- Layer 2: docs/contracts/extraction_candidate.json ----------------------

ExtractedValue = Union[str, float, int, bool, None]


class ExtractionCandidate(BaseModel):
    """Matches docs/contracts/extraction_candidate.json (+ model_confidence,
    see module docstring). This is what evidence_service.py consumes."""

    field_name: FieldName
    value: ExtractedValue = None
    value_text: Optional[str] = None
    evidence_quote: Optional[str] = None
    page_number: Optional[int] = Field(default=None, ge=1)
    uncertainty_reason: Optional[str] = None
    model_confidence: float = Field(0.0, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _never_trusted_without_evidence(self) -> "ExtractionCandidate":
        # Mirrors the contract's own words: "must always include
        # evidence_quote or it is rejected". Enforced here as well as in
        # GeminiRawExtraction because `value` here is the *normalized, typed*
        # value produced after Gemini's response — a bug in the normalizer
        # could otherwise smuggle a typed value through without evidence.
        if self.value is not None and not self.evidence_quote:
            raise ValueError(
                f"{self.field_name}: value is set but evidence_quote is missing; "
                "this candidate must not be trusted"
            )
        return self
