"""
Pydantic models for docs/contracts/validated_field.json.

Reuses `FieldName` from app.schemas.extraction (the same frozen 9-field
enum) rather than redefining it — a second, drifted copy of that enum would
be exactly the kind of duplicate/incompatible schema the team wants to
avoid.

`status` and `validation_status` reuse the exact enum strings already frozen
in docs/CONVENTIONS.md:
    status            (field trust):  UNTRUSTED | VALIDATED | OVERRIDDEN
    validation_status (why/what):     VALID | INVALID | MISSING | AMBIGUOUS

evidence_service.py (the only producer of ValidatedField at this stage)
only ever emits VALIDATED+VALID, UNTRUSTED+INVALID, UNTRUSTED+MISSING, or
UNTRUSTED+AMBIGUOUS. OVERRIDDEN is reserved for the later human-review stage
(Person 1/4) and is never set here.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional, Union

from pydantic import BaseModel, Field, model_validator

from app.schemas.extraction import ExtractedValue, FieldName


class FieldTrustStatus(str, Enum):
    """`extracted_fields.status` in docs/CONVENTIONS.md."""

    UNTRUSTED = "UNTRUSTED"
    VALIDATED = "VALIDATED"
    OVERRIDDEN = "OVERRIDDEN"  # never emitted by evidence_service.py


class ValidationStatus(str, Enum):
    """`extracted_fields.validation_status` in docs/CONVENTIONS.md."""

    VALID = "VALID"
    INVALID = "INVALID"
    MISSING = "MISSING"
    AMBIGUOUS = "AMBIGUOUS"


class BoundingBox(BaseModel):
    x: int = Field(..., ge=0)
    y: int = Field(..., ge=0)
    width: int = Field(..., ge=0)
    height: int = Field(..., ge=0)


class ValidatedField(BaseModel):
    """
    Matches docs/contracts/validated_field.json exactly.

    NOTE on `final_confidence`: the contract's own example includes this
    field but no document defines its formula. This service computes it as
    the unweighted mean of (ocr_confidence, evidence_match_score,
    model_confidence) when status=VALIDATED, and 0.0 otherwise — a simple,
    transparent, easily-replaced default. **This formula has not been
    signed off by the team and should be treated as provisional** until
    someone who owns the frontend confidence display (docs/CONVENTIONS.md's
    "Confidence display rule") confirms it's what they want to show.
    """

    field_name: FieldName
    normalized_value: ExtractedValue = None
    status: FieldTrustStatus
    validation_status: ValidationStatus
    ocr_confidence: float = Field(0.0, ge=0.0, le=1.0)
    evidence_match_score: float = Field(0.0, ge=0.0, le=1.0)
    model_confidence: float = Field(0.0, ge=0.0, le=1.0)
    final_confidence: float = Field(0.0, ge=0.0, le=1.0)
    evidence_quote: Optional[str] = None
    source_page: Optional[int] = Field(default=None, ge=1)
    bounding_box: Optional[BoundingBox] = None

    @model_validator(mode="after")
    def _validated_requires_evidence_and_location(self) -> "ValidatedField":
        if self.status == FieldTrustStatus.VALIDATED:
            if self.validation_status != ValidationStatus.VALID:
                raise ValueError("status=VALIDATED must always pair with validation_status=VALID")
            if not self.evidence_quote or self.source_page is None or self.bounding_box is None:
                raise ValueError("status=VALIDATED requires evidence_quote, source_page, and bounding_box")
        if self.validation_status == ValidationStatus.MISSING and self.normalized_value is not None:
            raise ValueError("validation_status=MISSING must not carry a normalized_value")
        return self
