"""
Applications API Endpoints.
Implements the frozen API contracts for application lifecycle, document upload, processing, and decision inspection.
"""

from __future__ import annotations

import os
import shutil
import uuid
from typing import List, Optional
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import CurrentUser, get_current_user, require_permission, compute_bytes_sha256
from app.db.session import get_db
from app.db.models import Application, Document, ExtractedField, Decision
from app.schemas.application import (
    ApplicationCreate,
    ApplicationResponse,
    DocumentResponse,
    ProcessResponse,
)
from app.schemas.validation import ValidatedField, BoundingBox, FieldTrustStatus, ValidationStatus
from app.schemas.decision import DecisionDetailResponse, RuleResultSchema
from app.services.audit_service import AuditService
from app.services.pipeline_service import PipelineService
from app.services.report_service import ReportService
from app.services.ocr_service import (
    InvalidDocumentError,
    MalformedImageError,
    EmptyDocumentError,
    OCRExecutionError,
)
from app.services.extraction_service import (
    ExtractionConfigError,
    GeminiCallError,
    MalformedGeminiOutputError,
)

router = APIRouter(prefix="/applications", tags=["Applications"])


@router.post("", response_model=ApplicationResponse, status_code=status.HTTP_201_CREATED)
def create_application(
    payload: ApplicationCreate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission("upload")),
):
    """Creates a new application in DRAFT state."""
    # Generate human reference e.g. APP-00019 if not provided
    ref = payload.public_reference
    if not ref:
        count = db.query(Application).count() + 1
        ref = f"APP-{count:05d}"

    # Check collision
    if db.query(Application).filter(Application.public_reference == ref).first():
        ref = f"APP-{uuid.uuid4().hex[:6].upper()}"

    app = Application(
        public_reference=ref,
        applicant_name=payload.applicant_name,
        scheme_code=payload.scheme_code,
        status="DRAFT",
    )
    db.add(app)
    db.flush()

    # Append audit event
    AuditService.append_audit_event(
        db=db,
        action_type="APPLICATION_CREATED",
        payload={
            "public_reference": app.public_reference,
            "applicant_name": app.applicant_name,
            "scheme_code": app.scheme_code,
        },
        actor_id=user.user_id,
        application_id=app.id,
    )

    db.commit()
    db.refresh(app)
    return app


@router.get("", response_model=List[ApplicationResponse])
def list_applications(
    status_filter: Optional[str] = None,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission("view")),
):
    """Lists all registered applications with their document count and status."""
    query = db.query(Application).order_by(Application.created_at.desc())
    if status_filter:
        query = query.filter(Application.status == status_filter)
    return query.all()


@router.get("/{id}", response_model=ApplicationResponse)
def get_application(
    id: str,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission("view")),
):
    """Fetches a single application by UUID or public_reference."""
    app = db.query(Application).filter(
        (Application.id == id) | (Application.public_reference == id)
    ).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found.")
    return app


@router.post("/{id}/documents", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    id: str,
    doc_type: str = Form("application_form"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission("upload")),
):
    """
    Uploads a document for an application:
    - Computes SHA-256 hash
    - Stores file in storage directory
    - Appends DOCUMENT_UPLOADED to the hash-chain audit log
    """
    app = db.query(Application).filter(
        (Application.id == id) | (Application.public_reference == id)
    ).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found.")

    contents = await file.read()
    file_size = len(contents)
    file_hash = compute_bytes_sha256(contents)

    # Save to local storage
    app_storage_dir = Path(settings.LOCAL_STORAGE_DIR) / app.id
    app_storage_dir.mkdir(parents=True, exist_ok=True)
    
    file_ext = Path(file.filename or "upload.pdf").suffix or ".pdf"
    unique_fname = f"{uuid.uuid4().hex}_{file.filename}"
    saved_path = app_storage_dir / unique_fname

    with open(saved_path, "wb") as f:
        f.write(contents)

    doc = Document(
        application_id=app.id,
        doc_type=doc_type,
        file_name=file.filename or "document.pdf",
        file_size=file_size,
        mime_type=file.content_type or "application/pdf",
        storage_path=str(saved_path),
        file_hash=file_hash,
    )
    db.add(doc)
    
    # Update application status if was DRAFT
    if app.status == "DRAFT":
        app.status = "DOCUMENTS_UPLOADED"

    db.flush()

    # Audit event
    AuditService.append_audit_event(
        db=db,
        action_type="DOCUMENT_UPLOADED",
        payload={
            "document_id": doc.id,
            "doc_type": doc.doc_type,
            "file_name": doc.file_name,
            "file_size": doc.file_size,
            "file_hash": doc.file_hash,
        },
        actor_id=user.user_id,
        application_id=app.id,
    )

    db.commit()
    db.refresh(doc)
    return doc


@router.post("/{id}/process", response_model=ProcessResponse)
def process_application(
    id: str,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission("process")),
):
    """
    Triggers the end-to-end processing pipeline:
    OCR -> Gemini Extraction -> Evidence Linking -> Validation -> Rules -> Decision -> Audit Chain.
    """
    app = db.query(Application).filter(
        (Application.id == id) | (Application.public_reference == id)
    ).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found.")

    if not app.documents:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot process application {app.public_reference}: no documents uploaded."
        )

    try:
        result = PipelineService.process_application(
            db=db,
            application_id=app.id,
            actor_id=user.user_id,
            policy_version="CSSS-Demo-v1.0",
        )
        return ProcessResponse(
            job_id=str(uuid.uuid4()),
            application_id=app.id,
            status=result["status"],
            outcome=result["outcome"],
            decision_version=result["decision_version"],
            message="Application processed successfully through the evidence-grounded audit pipeline.",
        )
    except (InvalidDocumentError, MalformedImageError, EmptyDocumentError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Document upload could not be processed: {str(exc)}",
        )
    except OCRExecutionError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"OCR execution failure in environment: {str(exc)}",
        )
    except ExtractionConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Extraction configuration error: {str(exc)}",
        )
    except GeminiCallError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Gemini API call failed (transient, retryable): {str(exc)}",
        )
    except MalformedGeminiOutputError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Malformed model output: {str(exc)}",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Processing failed: {str(exc)}",
        )


@router.get("/{id}/fields", response_model=List[ValidatedField])
def get_extracted_fields(
    id: str,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission("view")),
):
    """Returns validated field objects (Contract 3) for the given application."""
    app = db.query(Application).filter(
        (Application.id == id) | (Application.public_reference == id)
    ).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found.")

    result: List[ValidatedField] = []
    for ef in app.extracted_fields:
        bbox = None
        if ef.bounding_box and isinstance(ef.bounding_box, dict):
            bbox = BoundingBox(
                x=ef.bounding_box.get("x", 0),
                y=ef.bounding_box.get("y", 0),
                width=ef.bounding_box.get("width", 0),
                height=ef.bounding_box.get("height", 0),
            )
        result.append(
            ValidatedField(
                field_name=ef.field_name,
                normalized_value=ef.normalized_value,
                status=FieldTrustStatus(ef.status),
                validation_status=ValidationStatus(ef.validation_status),
                ocr_confidence=ef.ocr_confidence,
                evidence_match_score=ef.evidence_match_score,
                model_confidence=ef.model_confidence,
                final_confidence=ef.final_confidence,
                evidence_quote=ef.evidence_quote,
                source_page=ef.source_page,
                bounding_box=bbox,
            )
        )
    return result


@router.get("/{id}/decision", response_model=DecisionDetailResponse)
def get_decision(
    id: str,
    version: Optional[int] = None,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission("view")),
):
    """Returns the latest (or specific version) decision with evaluated rules (Contract 4 & 5)."""
    app = db.query(Application).filter(
        (Application.id == id) | (Application.public_reference == id)
    ).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found.")

    query = db.query(Decision).filter(Decision.application_id == app.id)
    if version:
        query = query.filter(Decision.decision_version == version)
    decision = query.order_by(Decision.decision_version.desc()).first()

    if not decision:
        raise HTTPException(status_code=404, detail="No decision has been generated for this application yet.")

    return DecisionDetailResponse(
        id=decision.id,
        application_id=decision.application_id,
        decision_version=decision.decision_version,
        outcome=decision.outcome,
        decision_mode=decision.decision_mode,
        policy_version=decision.policy_version,
        confidence_summary=decision.confidence_summary or {},
        supersedes_decision_id=decision.supersedes_decision_id,
        is_final=decision.is_final,
        created_at=decision.created_at,
        rule_results=[
            RuleResultSchema(
                rule_code=rr.rule_code,
                result=rr.result,
                input_snapshot=rr.input_snapshot,
                explanation=rr.explanation,
                policy_version=rr.policy_version,
            )
            for rr in decision.rule_results
        ],
    )


@router.get("/{id}/report.pdf")
def download_pdf_report(
    id: str,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission("view")),
):
    """Generates and downloads the official Decision Audit Trail PDF report (ReportLab)."""
    app = db.query(Application).filter(
        (Application.id == id) | (Application.public_reference == id)
    ).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found.")

    pdf_bytes = ReportService.generate_audit_report_pdf(db, app.id)
    if not pdf_bytes:
        raise HTTPException(status_code=500, detail="Could not generate PDF report.")

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=decision_audit_{app.public_reference}.pdf"
        }
    )
