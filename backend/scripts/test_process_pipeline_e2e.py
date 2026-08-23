"""
End-to-end test of the REAL /applications/{id}/process HTTP flow.

Unlike scripts/test_integration_ocr_extraction_evidence.py (which calls
extraction_service.extract_fields() directly), this script drives the
actual FastAPI endpoints a real client would call:

    POST /api/applications                      (create)
    POST /api/applications/{id}/documents        (upload)
    POST /api/applications/{id}/process          (OCR -> Gemini -> evidence -> rules -> decision)
    GET  /api/applications/{id}/fields
    GET  /api/applications/{id}/decision
    POST /api/audit/verify

It generates its own synthetic income-certificate-style PDF (same idea as
scripts/test_ocr_service.py) since no real sample document is available yet.

Requires GEMINI_API_KEY to be set (in backend/.env or the environment) for
a real extraction call. If it's missing, PipelineService will raise
ExtractionConfigError and this script will fail loudly and tell you why --
it does NOT silently fall back to a mock, unlike the other integration
script. That's intentional: this script's whole purpose is to prove the
real key + real pipeline works end-to-end through the HTTP layer.

Run with:
    cd backend
    python ../test_process_pipeline_e2e.py     (or wherever you place this file)
"""

from __future__ import annotations

import sys
from pathlib import Path
from dotenv import load_dotenv

# Allow running from anywhere -- add backend/ to sys.path so `app.*` imports work.
BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
# Load .env from backend and repo root before importing application services
load_dotenv(BACKEND_DIR / ".env")
load_dotenv(REPO_ROOT / ".env")

import fitz  # PyMuPDF, only to build the synthetic sample document
from fastapi.testclient import TestClient

from app.main import app


def _make_sample_pdf(path: Path) -> None:
    """Two-page synthetic income-certificate-style PDF covering all 9 frozen
    fields, so /process has something real to extract end to end."""
    doc = fitz.open()

    page1 = doc.new_page()
    page1.insert_text((72, 100), "PM-USP Central Sector Scheme of Scholarship", fontsize=16)
    page1.insert_text((72, 140), "Student Name: Ananya Reddy", fontsize=12)
    page1.insert_text((72, 165), "Date of Birth: 2006-02-18", fontsize=12)
    page1.insert_text((72, 190), "Board Percentile: 88.5", fontsize=12)
    page1.insert_text((72, 215), "Course Mode: Regular", fontsize=12)
    page1.insert_text((72, 240), "Date of Application: 2026-08-15", fontsize=12)

    page2 = doc.new_page()
    page2.insert_text((72, 100), "Institution Name: Osmania University", fontsize=12)
    page2.insert_text((72, 125), "Institution Recognized: Yes", fontsize=12)
    page2.insert_text((72, 150), "Gross parental family income: Rs 380000 per annum", fontsize=12)
    page2.insert_text((72, 175), "Other Scholarship: No", fontsize=12)

    doc.save(str(path))
    doc.close()


def main() -> None:
    sample_path = BACKEND_DIR / "_process_pipeline_sample.pdf"
    print(f"Generating synthetic sample PDF at {sample_path}")
    _make_sample_pdf(sample_path)

    with TestClient(app) as client:
        print("\n[1/6] POST /api/applications (create)")
        res = client.post(
            "/api/applications",
            json={"applicant_name": "Ananya Reddy", "scheme_code": "PM-USP-CSSS"},
        )
        assert res.status_code == 201, f"create failed: {res.status_code} {res.text}"
        application = res.json()
        app_id = application["id"]
        print(f"    -> created {application['public_reference']} ({app_id})")

        print("\n[2/6] POST /api/applications/{id}/documents (upload)")
        with open(sample_path, "rb") as f:
            res = client.post(
                f"/api/applications/{app_id}/documents",
                files={"file": (sample_path.name, f, "application/pdf")},
                data={"doc_type": "application_form"},
            )
        assert res.status_code == 201, f"upload failed: {res.status_code} {res.text}"
        document = res.json()
        print(f"    -> uploaded document {document['id']} (hash {document['file_hash'][:12]}...)")

        print("\n[3/6] POST /api/applications/{id}/process (real OCR + real Gemini)")
        res = client.post(f"/api/applications/{app_id}/process")
        if res.status_code != 200:
            print(f"    !! process failed: {res.status_code}")
            print(f"    !! detail: {res.text}")
            if res.status_code == 500 and "GEMINI_API_KEY" in res.text:
                print(
                    "    !! Looks like GEMINI_API_KEY isn't visible to this process. "
                    "Check backend/.env (or wherever settings.GEMINI_API_KEY reads from) "
                    "and that app/main.py's lifespan bridged it into os.environ."
                )
            sys.exit(1)
        result = res.json()
        print(f"    -> status={result['status']} outcome={result['outcome']} decision_version={result['decision_version']}")

        print("\n[4/6] GET /api/applications/{id}/fields")
        res = client.get(f"/api/applications/{app_id}/fields")
        assert res.status_code == 200
        fields = res.json()
        assert len(fields) == 9, f"expected 9 fields, got {len(fields)}"
        by_name = {f["field_name"]: f for f in fields}
        for fname, f in by_name.items():
            print(
                f"    {fname:24s} status={f['status']:10s} validation_status={f['validation_status']:9s} "
                f"value={f['normalized_value']!r}"
            )

        income = by_name["family_income"]
        assert income["status"] == "VALIDATED", f"family_income not validated: {income}"
        assert income["normalized_value"] == 380000, f"unexpected income value: {income['normalized_value']}"
        print("    -> family_income correctly extracted, evidence-matched, and normalized to 380000")

        print("\n[5/6] GET /api/applications/{id}/decision")
        res = client.get(f"/api/applications/{app_id}/decision")
        assert res.status_code == 200
        decision = res.json()
        print(f"    -> outcome={decision['outcome']} decision_mode={decision['decision_mode']} rules={len(decision['rule_results'])}")
        for rr in decision["rule_results"]:
            print(f"       {rr['rule_code']:32s} {rr['result']}")

        print("\n[6/6] POST /api/audit/verify (confirm the hash chain this run produced is intact)")
        res = client.post("/api/audit/verify", json={"application_id": app_id})
        assert res.status_code == 200
        audit = res.json()
        assert audit["verified"] is True, f"audit chain broken: {audit}"
        print(f"    -> verified={audit['verified']} total_entries={audit['total_entries']}")

    sample_path.unlink(missing_ok=True)
    print("\nEnd-to-end /process pipeline test PASSED against the real HTTP API, real Tesseract, real Gemini.")


if __name__ == "__main__":
    main()
