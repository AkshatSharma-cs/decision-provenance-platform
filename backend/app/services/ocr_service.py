"""
ocr_service.py — Person 2 (AI / OCR Engineer)

Pipeline:
    PDF / image file
    -> PyMuPDF rendering (rasterize each page to a bitmap)
    -> OpenCV preprocessing (grayscale, denoise, adaptive threshold, deskew)
    -> Tesseract OCR (pytesseract.image_to_data, word-level TSV output)
    -> OCRDocumentResult (per docs/schemas + docs/contracts/ocr_token.json)

ARCHITECTURE RULE (non-negotiable, see README):
    Tesseract is the source of truth for document text, word coordinates, and
    OCR confidence. This file NEVER calls Gemini and NEVER makes an
    eligibility/trust decision about a field. Whether a value can be trusted
    is decided later by evidence_service.py (fuzzy-matching a Gemini
    extraction_candidate back against the OCRToken list produced here).

This module does not swallow errors. Failures that make a page/document
un-OCR-able raise a subclass of OCRServiceError with enough context to log
and to show the operator (Person 5's adversarial testing depends on this).
Recoverable situations (e.g. one blank page in an otherwise fine document,
or a page whose mean confidence is low) are NOT raised as exceptions — they
are recorded as warnings on the result, because a whole document should not
fail just because one page is blank or noisy. The one exception has its own
rule below (see EmptyDocumentError / OCRExecutionError).
"""

from __future__ import annotations

import io
import logging
import os
from pathlib import Path
from typing import List, Tuple

import cv2
import fitz  # PyMuPDF
import numpy as np
import pytesseract
from PIL import Image, UnidentifiedImageError
from pytesseract import Output

# On Windows (and any machine where the tesseract binary isn't on PATH),
# pytesseract has no way to find it unless told explicitly. Rather than
# requiring every developer to edit code, we read an optional TESSERACT_CMD
# env var (see .env.example) and point pytesseract at it. If unset, we fall
# back to pytesseract's default behavior (look up "tesseract" on PATH),
# which is what already works on Linux/macOS with a normal package-manager
# install.
_TESSERACT_CMD = os.environ.get("TESSERACT_CMD")
if _TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = _TESSERACT_CMD

from app.schemas.ocr import (
    OCRDocumentResult,
    OCRPageResult,
    OCRPageWarning,
    OCRToken,
    PageSourceType,
)

logger = logging.getLogger(__name__)

# --- Tunables -----------------------------------------------------------
# These are intentionally module-level constants rather than magic numbers
# scattered through the pipeline. If Person 1 wants these centralized in
# app/core/config.py instead, they can be moved there without changing any
# public function signature in this file.

RENDER_DPI = 300  # PyMuPDF render resolution for PDF pages; 300 is the
                   # standard sweet spot for Tesseract accuracy vs speed.

# Tesseract reports word confidence on a 0-100 scale (and -1 for non-word
# rows, e.g. block/paragraph/line boundary rows with no text). We normalize
# to 0.0-1.0 to match docs/contracts/ocr_token.json.
MIN_WORD_CONFIDENCE_PCT = 0  # keep every recognized word; low-confidence
                             # words are still evidence candidates and it's
                             # evidence_service.py's job (>=0.90 fuzzy match)
                             # to decide trust, not this file's.

LOW_CONFIDENCE_PAGE_THRESHOLD = 0.60  # below this mean page confidence,
                                       # flag OCRPageWarning.LOW_CONFIDENCE

SUPPORTED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}
SUPPORTED_PDF_SUFFIXES = {".pdf"}

TESSERACT_CONFIG = "--oem 3 --psm 6"  # LSTM engine, "assume a single uniform
                                       # block of text" — matches the layout
                                       # of scanned certificates/marksheets.


# --- Exceptions ----------------------------------------------------------

class OCRServiceError(Exception):
    """Base class for every error this module raises."""


class InvalidDocumentError(OCRServiceError):
    """File does not exist, isn't a supported type, or can't be opened/parsed
    (corrupt PDF, truncated image, encrypted PDF without a password, etc.)."""


class MalformedImageError(OCRServiceError):
    """A page rasterized to something OpenCV/Tesseract could not read, or an
    input image file is corrupt / not decodable."""


class EmptyDocumentError(OCRServiceError):
    """The document opened successfully but has zero pages (a 0-page PDF),
    or every single page failed OCR / produced empty content. A document
    where SOME pages are empty is not this error — see OCRPageWarning."""


class OCRExecutionError(OCRServiceError):
    """The Tesseract binary/pytesseract call itself failed (missing binary,
    process crash, unsupported language pack, etc.) — distinct from
    "OCR ran but found nothing", which is EmptyDocumentError/warnings."""


# --- Public API ------------------------------------------------------------

def process_document(file_path: str) -> OCRDocumentResult:
    """
    Run the full OCR pipeline over a single document (PDF or image) and
    return a validated OCRDocumentResult.

    Raises:
        InvalidDocumentError: file missing, unsupported type, unopenable/corrupt.
        MalformedImageError: a page/image could not be decoded into pixels.
        EmptyDocumentError: 0 pages, or OCR produced no usable content anywhere.
        OCRExecutionError: the OCR engine itself failed to run.

    Never raises for a single bad page in an otherwise-good multi-page
    document — that page is included in the result with warnings instead.
    """
    path = Path(file_path)
    _validate_file_exists(path)

    page_images = _load_page_images(path)  # List[(page_number, np.ndarray BGR, PageSourceType)]

    page_results: List[OCRPageResult] = []
    document_warnings: List[str] = []

    for page_number, image_bgr, source_type in page_images:
        try:
            page_result = _ocr_single_page(page_number, image_bgr, source_type)
        except MalformedImageError as exc:
            # Preprocessing/decoding failed for this page specifically.
            # Don't silently drop it: record a zero-token page with a
            # document-level warning so the caller/operator can see it.
            logger.error("Page %s of %s failed preprocessing: %s", page_number, path, exc)
            document_warnings.append(f"page {page_number}: preprocessing failed ({exc})")
            page_result = _empty_page_result(page_number, image_bgr, source_type)
        page_results.append(page_result)

    if not page_results:
        raise EmptyDocumentError(f"{path} contains zero pages")

    all_empty = all(p.token_count == 0 for p in page_results)
    if all_empty:
        raise EmptyDocumentError(
            f"{path}: OCR produced zero tokens across all {len(page_results)} page(s); "
            "the document may be blank, unreadable, or the wrong file type."
        )

    low_conf_pages = [p.page_number for p in page_results if OCRPageWarning.LOW_CONFIDENCE in p.warnings]
    empty_pages = [p.page_number for p in page_results if OCRPageWarning.EMPTY_PAGE in p.warnings]

    confidences = [p.mean_confidence for p in page_results if p.token_count > 0]
    overall_mean_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    overall_mean_confidence = max(0.0, min(1.0, round(overall_mean_confidence, 4)))

    if low_conf_pages:
        document_warnings.append(
            f"low OCR confidence (< {LOW_CONFIDENCE_PAGE_THRESHOLD:.0%}) on page(s): {low_conf_pages}"
        )
    if empty_pages:
        document_warnings.append(f"no text found on page(s): {empty_pages}")

    return OCRDocumentResult(
        file_path=str(path),
        total_pages=len(page_results),
        pages=page_results,
        low_confidence_page_numbers=low_conf_pages,
        empty_page_numbers=empty_pages,
        overall_mean_confidence=overall_mean_confidence,
        warnings=document_warnings,
    )


# --- Loading: PDF/image -> per-page BGR numpy arrays ------------------------

def _validate_file_exists(path: Path) -> None:
    if not path.exists() or not path.is_file():
        raise InvalidDocumentError(f"file not found: {path}")
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_PDF_SUFFIXES | SUPPORTED_IMAGE_SUFFIXES:
        raise InvalidDocumentError(
            f"unsupported file type '{suffix}' for {path}; "
            f"expected one of {sorted(SUPPORTED_PDF_SUFFIXES | SUPPORTED_IMAGE_SUFFIXES)}"
        )


def _load_page_images(path: Path) -> List[Tuple[int, np.ndarray, PageSourceType]]:
    suffix = path.suffix.lower()
    if suffix in SUPPORTED_PDF_SUFFIXES:
        return _render_pdf_pages(path)
    return _load_single_image(path)


def _render_pdf_pages(path: Path) -> List[Tuple[int, np.ndarray, PageSourceType]]:
    try:
        doc = fitz.open(str(path))
    except Exception as exc:  # fitz raises its own exception types depending on failure mode
        raise InvalidDocumentError(f"could not open PDF {path}: {exc}") from exc

    if doc.is_encrypted:
        # doc.authenticate("") succeeds for PDFs "encrypted" with an empty
        # owner password; anything else we treat as a real failure rather
        # than silently proceeding with an unreadable document.
        if not doc.authenticate(""):
            doc.close()
            raise InvalidDocumentError(f"{path} is password-protected; cannot OCR")

    if doc.page_count == 0:
        doc.close()
        raise EmptyDocumentError(f"{path} has zero pages")

    zoom = RENDER_DPI / 72.0  # PDF's native unit is 72 DPI
    matrix = fitz.Matrix(zoom, zoom)

    pages: List[Tuple[int, np.ndarray, PageSourceType]] = []
    for page_index in range(doc.page_count):
        page_number = page_index + 1
        try:
            pix = doc[page_index].get_pixmap(matrix=matrix, colorspace=fitz.csRGB, alpha=False)
            img_bytes = pix.tobytes("png")
            image_bgr = _decode_image_bytes(img_bytes, page_number)
        except MalformedImageError:
            raise
        except Exception as exc:
            raise MalformedImageError(f"failed to rasterize page {page_number} of {path}: {exc}") from exc
        pages.append((page_number, image_bgr, PageSourceType.NATIVE_RASTER))

    doc.close()
    return pages


def _load_single_image(path: Path) -> List[Tuple[int, np.ndarray, PageSourceType]]:
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError as exc:
        raise InvalidDocumentError(f"could not read {path}: {exc}") from exc

    image_bgr = _decode_image_bytes(raw, page_number=1)
    return [(1, image_bgr, PageSourceType.IMAGE_FILE)]


def _decode_image_bytes(raw_bytes: bytes, page_number: int) -> np.ndarray:
    """Decode raw image bytes into an OpenCV BGR numpy array, raising
    MalformedImageError instead of letting PIL/OpenCV exceptions leak out
    with an unhelpful stack trace."""
    try:
        pil_image = Image.open(io.BytesIO(raw_bytes))
        pil_image.load()  # force decode now, not lazily later
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise MalformedImageError(f"page {page_number}: not a decodable image ({exc})") from exc

    try:
        rgb = np.array(pil_image.convert("RGB"))
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    except Exception as exc:
        raise MalformedImageError(f"page {page_number}: could not convert to array ({exc})") from exc

    if bgr.size == 0 or 0 in bgr.shape[:2]:
        raise MalformedImageError(f"page {page_number}: decoded image has zero width/height")

    return bgr


# --- OpenCV preprocessing ----------------------------------------------------

def _preprocess_for_ocr(image_bgr: np.ndarray) -> np.ndarray:
    """
    Grayscale -> denoise -> adaptive threshold -> deskew.
    Conservative on purpose: these are scanned government certificates, not
    photos, so we avoid aggressive morphology that could erode thin digits
    (e.g. in income figures) and corrupt the very evidence the rules engine
    depends on.
    """
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    denoised = cv2.fastNlMeansDenoising(gray, h=10)
    binarized = cv2.adaptiveThreshold(
        denoised,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=31,
        C=15,
    )
    deskewed = _deskew(binarized)
    return deskewed


def _deskew(binary_image: np.ndarray) -> np.ndarray:
    """Estimate and correct small rotational skew from scanning. Falls back
    to the untouched image if no text-bearing pixels are found (blank page) —
    that is a normal, expected case, not an error."""
    coords = np.column_stack(np.where(binary_image < 128))
    if coords.shape[0] < 20:
        # Effectively a blank/near-blank page — nothing to deskew.
        return binary_image

    angle = cv2.minAreaRect(coords.astype(np.float32))[-1]
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle

    if abs(angle) < 0.3:
        return binary_image  # not worth the interpolation cost/risk

    (h, w) = binary_image.shape[:2]
    center = (w // 2, h // 2)
    rotation_matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    return cv2.warpAffine(
        binary_image,
        rotation_matrix,
        (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )


# --- Tesseract: word-level OCR -----------------------------------------------

def _ocr_single_page(
    page_number: int,
    image_bgr: np.ndarray,
    source_type: PageSourceType,
) -> OCRPageResult:
    height_px, width_px = image_bgr.shape[:2]
    preprocessed = _preprocess_for_ocr(image_bgr)

    try:
        tsv_data = pytesseract.image_to_data(
            preprocessed,
            output_type=Output.DICT,
            config=TESSERACT_CONFIG,
        )
    except pytesseract.TesseractNotFoundError as exc:
        raise OCRExecutionError(
            "tesseract binary not found on PATH — install tesseract-ocr"
        ) from exc
    except pytesseract.TesseractError as exc:
        raise OCRExecutionError(f"tesseract failed on page {page_number}: {exc}") from exc

    tokens = _tsv_to_tokens(tsv_data, page_number)
    page_text = _reconstruct_page_text(tsv_data)

    warnings: List[OCRPageWarning] = []
    if not tokens:
        warnings.append(OCRPageWarning.EMPTY_PAGE)
        mean_confidence = 0.0
    else:
        mean_confidence = max(0.0, min(1.0, round(sum(t.confidence for t in tokens) / len(tokens), 4)))
        if mean_confidence < LOW_CONFIDENCE_PAGE_THRESHOLD:
            warnings.append(OCRPageWarning.LOW_CONFIDENCE)

    return OCRPageResult(
        page_number=page_number,
        source_type=source_type,
        width_px=width_px,
        height_px=height_px,
        tokens=tokens,
        page_text=page_text,
        mean_confidence=mean_confidence,
        token_count=len(tokens),
        warnings=warnings,
    )


def _tsv_to_tokens(tsv_data: dict, page_number: int) -> List[OCRToken]:
    tokens: List[OCRToken] = []
    n = len(tsv_data.get("text", []))
    for i in range(n):
        text = str(tsv_data["text"][i] if tsv_data["text"][i] is not None else "").strip()
        if not text:
            continue  # block/paragraph/line boundary rows carry no word text

        conf_raw = float(tsv_data["conf"][i])
        if conf_raw < 0:
            continue  # Tesseract's sentinel for "not an actual word row"
        if conf_raw < MIN_WORD_CONFIDENCE_PCT:
            continue

        confidence = max(0.0, min(1.0, round(conf_raw / 100.0, 4)))
        tokens.append(
            OCRToken(
                page_number=page_number,
                token=text,
                left=int(tsv_data["left"][i]),
                top=int(tsv_data["top"][i]),
                width=int(tsv_data["width"][i]),
                height=int(tsv_data["height"][i]),
                confidence=confidence,
                line_no=int(tsv_data["line_num"][i]),
                block_no=int(tsv_data["block_num"][i]),
            )
        )
    return tokens


def _reconstruct_page_text(tsv_data: dict) -> str:
    """Rebuild page text preserving line breaks using Tesseract's own
    block/line grouping, rather than a second OCR pass with image_to_string
    (which would re-run recognition and could disagree with image_to_data)."""
    n = len(tsv_data.get("text", []))
    lines: dict[Tuple[int, int], List[str]] = {}
    order: List[Tuple[int, int]] = []
    for i in range(n):
        text = tsv_data["text"][i].strip()
        if not text:
            continue
        key = (int(tsv_data["block_num"][i]), int(tsv_data["line_num"][i]))
        if key not in lines:
            lines[key] = []
            order.append(key)
        lines[key].append(text)

    return "\n".join(" ".join(lines[key]) for key in order)


def _empty_page_result(
    page_number: int,
    image_bgr: np.ndarray,
    source_type: PageSourceType,
) -> OCRPageResult:
    """Used only when preprocessing/decoding raised MalformedImageError for
    this specific page — we still return a well-formed, zero-token page so
    one bad page doesn't take down the whole document's result."""
    try:
        height_px, width_px = image_bgr.shape[:2]
    except Exception:
        height_px, width_px = 0, 0
    return OCRPageResult(
        page_number=page_number,
        source_type=source_type,
        width_px=width_px,
        height_px=height_px,
        tokens=[],
        page_text="",
        mean_confidence=0.0,
        token_count=0,
        warnings=[OCRPageWarning.EMPTY_PAGE],
    )
