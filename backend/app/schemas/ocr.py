"""
Pydantic models for the OCR layer.

These models are the typed form of `docs/contracts/ocr_token.json`. The wire
shape of `OCRToken` MUST stay byte-for-byte compatible with that contract
(same field names, same types, same units) because Person 1 persists it
directly to the `ocr_tokens` table and Person 2's extraction_service.py reads
it back for evidence matching. Do not rename fields here without updating the
contract file and getting sign-off per the README's contract-change rule.

Everything below OCRToken (OCRPageResult, OCRDocumentResult, etc.) is new —
there is no existing contract for a "whole page" or "whole document" OCR
result, so these are additive and do not change any frozen contract.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class OCRToken(BaseModel):
    """
    One word-level OCR token. Matches docs/contracts/ocr_token.json exactly.

    confidence is normalized to the 0.0-1.0 range (Tesseract natively reports
    0-100; CONVENTIONS.md / the contract example both use a 0-1 float, e.g.
    0.96) so every consumer of this contract can assume the same scale.
    """

    page_number: int = Field(..., ge=1)
    token: str
    left: int = Field(..., ge=0)
    top: int = Field(..., ge=0)
    width: int = Field(..., ge=0)
    height: int = Field(..., ge=0)
    confidence: float = Field(..., ge=0.0, le=1.0)
    line_no: int = Field(..., ge=0)
    block_no: int = Field(..., ge=0)


class PageSourceType(str, Enum):
    """How this page's image was obtained, for downstream debugging."""

    NATIVE_RASTER = "NATIVE_RASTER"      # rendered from a PDF page via PyMuPDF
    IMAGE_FILE = "IMAGE_FILE"            # input was already a raster image (jpg/png/tiff)


class OCRPageWarning(str, Enum):
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    EMPTY_PAGE = "EMPTY_PAGE"
    NO_TOKENS_ABOVE_THRESHOLD = "NO_TOKENS_ABOVE_THRESHOLD"


class OCRPageResult(BaseModel):
    """OCR output for a single page, tokens plus the reconstructed page text."""

    page_number: int = Field(..., ge=1)
    source_type: PageSourceType
    width_px: int
    height_px: int
    tokens: List[OCRToken]
    page_text: str
    mean_confidence: float = Field(..., ge=0.0, le=1.0)
    token_count: int
    warnings: List[OCRPageWarning] = Field(default_factory=list)

    @field_validator("token_count")
    @classmethod
    def _token_count_matches(cls, v: int, info) -> int:
        tokens = info.data.get("tokens")
        if tokens is not None and v != len(tokens):
            raise ValueError("token_count must equal len(tokens)")
        return v


class OCRDocumentResult(BaseModel):
    """Whole-document OCR result returned by process_document()."""

    file_path: str
    total_pages: int = Field(..., ge=0)
    pages: List[OCRPageResult]
    low_confidence_page_numbers: List[int] = Field(default_factory=list)
    empty_page_numbers: List[int] = Field(default_factory=list)
    overall_mean_confidence: float = Field(..., ge=0.0, le=1.0)
    warnings: List[str] = Field(default_factory=list)
