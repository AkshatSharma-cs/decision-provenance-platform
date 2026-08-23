"""
Pydantic schemas for Applications and Documents.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ApplicationStatus(str, Enum):
    """Application status from docs/CONVENTIONS.md."""
    DRAFT = "DRAFT"
    DOCUMENTS_UPLOADED = "DOCUMENTS_UPLOADED"
    OCR_COMPLETED = "OCR_COMPLETED"
    FIELDS_EXTRACTED = "FIELDS_EXTRACTED"
    FIELDS_VALIDATED = "FIELDS_VALIDATED"
    RULES_EVALUATED = "RULES_EVALUATED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    AUTO_DECISION = "AUTO_DECISION"
    HUMAN_CONFIRMED = "HUMAN_CONFIRMED"
    FINALIZED = "FINALIZED"


class DocumentType(str, Enum):
    APPLICATION_FORM = "application_form"
    INCOME_CERTIFICATE = "income_certificate"
    INSTITUTION_CERTIFICATE = "institution_certificate"
    SCHOLARSHIP_DECLARATION = "scholarship_declaration"
    OTHER = "other"


class ApplicationCreate(BaseModel):
    public_reference: Optional[str] = Field(None, description="Human readable ID e.g. APP-00016")
    applicant_name: Optional[str] = Field(None, description="Applicant full name")
    scheme_code: str = Field("PM-USP-CSSS", description="Scheme identifier")


class DocumentResponse(BaseModel):
    id: str
    application_id: str
    doc_type: str
    file_name: str
    file_size: int
    mime_type: str
    file_hash: str
    created_at: datetime

    class Config:
        from_attributes = True


class ApplicationResponse(BaseModel):
    id: str
    public_reference: str
    applicant_name: Optional[str] = None
    scheme_code: str
    status: str
    created_at: datetime
    updated_at: datetime
    documents: List[DocumentResponse] = []

    class Config:
        from_attributes = True


class ProcessResponse(BaseModel):
    job_id: str
    application_id: str
    status: str
    message: str
    outcome: Optional[str] = None
    decision_version: Optional[int] = None
