"""
Local smoke test for app/services/ocr_service.py.

Usage:
    python scripts/test_ocr_service.py                  # generates a synthetic
                                                          # sample PDF and OCRs it
    python scripts/test_ocr_service.py /path/to/file.pdf # OCRs a real file

This is a manual sanity check, not a pytest suite — it prints the resulting
OCRDocumentResult as JSON so you can eyeball tokens/confidence/warnings. Wire
it into pytest later if useful (Person 5 may want this in the adversarial
test suite for malformed/blank/rotated inputs).
"""

import sys
from pathlib import Path

# Allow running this script directly (`python scripts/test_ocr_service.py`)
# without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import fitz  # PyMuPDF, only used here to synthesize a sample PDF

from app.services.ocr_service import (
    EmptyDocumentError,
    InvalidDocumentError,
    OCRExecutionError,
    process_document,
)


def _make_sample_pdf(path: Path) -> None:
    """Builds a two-page synthetic 'income certificate'-style PDF so this
    script runs standalone without a real demo-data file present yet."""
    doc = fitz.open()

    page1 = doc.new_page()
    page1.insert_text((72, 100), "Income Certificate", fontsize=18)
    page1.insert_text((72, 140), "Student Name: Priya Kumar", fontsize=12)
    page1.insert_text((72, 160), "Date of Birth: 2006-04-12", fontsize=12)

    page2 = doc.new_page()
    page2.insert_text((72, 100), "Gross parental/family income: Rs 4,20,000 per annum", fontsize=12)
    page2.insert_text((72, 130), "Course Mode: Regular", fontsize=12)

    doc.save(str(path))
    doc.close()


def main() -> None:
    if len(sys.argv) > 1:
        target = Path(sys.argv[1])
    else:
        target = Path(__file__).resolve().parent / "_sample_income_certificate.pdf"
        print(f"No file given, generating a synthetic sample at {target}")
        _make_sample_pdf(target)

    try:
        result = process_document(str(target))
    except InvalidDocumentError as exc:
        print(f"INVALID DOCUMENT: {exc}")
        sys.exit(1)
    except EmptyDocumentError as exc:
        print(f"EMPTY DOCUMENT: {exc}")
        sys.exit(1)
    except OCRExecutionError as exc:
        print(f"OCR ENGINE FAILURE: {exc}")
        sys.exit(1)

    print(result.model_dump_json(indent=2))
    print("\n--- summary ---")
    print(f"pages: {result.total_pages}")
    print(f"overall_mean_confidence: {result.overall_mean_confidence}")
    print(f"low_confidence_pages: {result.low_confidence_page_numbers}")
    print(f"empty_pages: {result.empty_page_numbers}")
    print(f"document warnings: {result.warnings}")


if __name__ == "__main__":
    main()
