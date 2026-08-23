"""
SQLAlchemy ORM models for Project Synapse.
Adheres strictly to the frozen field names, table definitions, and status enums in docs/CONVENTIONS.md.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    JSON,
)
from sqlalchemy.orm import relationship

from app.db.session import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


def get_utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Application(Base):
    __tablename__ = "applications"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    public_reference = Column(String(32), unique=True, index=True, nullable=False)
    applicant_name = Column(String(255), nullable=True)
    scheme_code = Column(String(64), default="PM-USP-CSSS", nullable=False)
    status = Column(String(32), default="DRAFT", nullable=False)
    created_at = Column(DateTime(timezone=True), default=get_utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=get_utc_now, onupdate=get_utc_now, nullable=False)

    # Relationships
    documents = relationship("Document", back_populates="application", cascade="all, delete-orphan", order_by="Document.created_at")
    extracted_fields = relationship("ExtractedField", back_populates="application", cascade="all, delete-orphan")
    decisions = relationship("Decision", back_populates="application", cascade="all, delete-orphan", order_by="Decision.decision_version")
    review_actions = relationship("ReviewAction", back_populates="application", cascade="all, delete-orphan", order_by="ReviewAction.created_at")
    audit_entries = relationship("AuditLogEntry", back_populates="application", cascade="all, delete-orphan", order_by="AuditLogEntry.occurred_at")


class Document(Base):
    __tablename__ = "documents"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    application_id = Column(String(36), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True)
    doc_type = Column(String(64), nullable=False, default="application_form")
    file_name = Column(String(255), nullable=False)
    file_size = Column(Integer, nullable=False, default=0)
    mime_type = Column(String(64), nullable=False, default="application/pdf")
    storage_path = Column(String(512), nullable=False)
    file_hash = Column(String(64), nullable=False)  # SHA-256
    created_at = Column(DateTime(timezone=True), default=get_utc_now, nullable=False)

    # Relationships
    application = relationship("Application", back_populates="documents")
    ocr_pages = relationship("OCRPage", back_populates="document", cascade="all, delete-orphan", order_by="OCRPage.page_number")


class OCRPage(Base):
    __tablename__ = "ocr_pages"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    page_number = Column(Integer, nullable=False)
    raw_text = Column(Text, nullable=False, default="")
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=get_utc_now, nullable=False)

    # Relationships
    document = relationship("Document", back_populates="ocr_pages")
    tokens = relationship("OCRToken", back_populates="page", cascade="all, delete-orphan")


class OCRToken(Base):
    __tablename__ = "ocr_tokens"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    ocr_page_id = Column(String(36), ForeignKey("ocr_pages.id", ondelete="CASCADE"), nullable=False, index=True)
    token = Column(String(255), nullable=False)
    left = Column(Integer, nullable=False)
    top = Column(Integer, nullable=False)
    width = Column(Integer, nullable=False)
    height = Column(Integer, nullable=False)
    confidence = Column(Float, nullable=False, default=0.0)
    line_no = Column(Integer, nullable=False, default=0)
    block_no = Column(Integer, nullable=False, default=0)

    # Relationships
    page = relationship("OCRPage", back_populates="tokens")


class ExtractedField(Base):
    __tablename__ = "extracted_fields"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    application_id = Column(String(36), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    field_name = Column(String(64), nullable=False, index=True)
    raw_value_text = Column(Text, nullable=True)
    normalized_value = Column(JSON, nullable=True)
    status = Column(String(32), default="UNTRUSTED", nullable=False)  # UNTRUSTED | VALIDATED | OVERRIDDEN
    validation_status = Column(String(32), default="AMBIGUOUS", nullable=False)  # VALID | INVALID | MISSING | AMBIGUOUS
    ocr_confidence = Column(Float, default=0.0, nullable=False)
    evidence_match_score = Column(Float, default=0.0, nullable=False)
    model_confidence = Column(Float, default=0.0, nullable=False)
    final_confidence = Column(Float, default=0.0, nullable=False)
    evidence_quote = Column(Text, nullable=True)
    source_page = Column(Integer, nullable=True)
    bounding_box = Column(JSON, nullable=True)  # {"x": 120, "y": 300, "width": 340, "height": 34}
    uncertainty_reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=get_utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=get_utc_now, onupdate=get_utc_now, nullable=False)

    # Relationships
    application = relationship("Application", back_populates="extracted_fields")


class PolicyVersion(Base):
    __tablename__ = "policy_versions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    scheme_code = Column(String(64), nullable=False, default="PM-USP-CSSS")
    version_string = Column(String(64), unique=True, index=True, nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(32), default="PUBLISHED", nullable=False)  # DRAFT | PUBLISHED | RETIRED
    effective_from = Column(DateTime(timezone=True), nullable=True)
    effective_to = Column(DateTime(timezone=True), nullable=True)
    rules_config = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), default=get_utc_now, nullable=False)


class Decision(Base):
    __tablename__ = "decisions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    application_id = Column(String(36), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True)
    decision_version = Column(Integer, default=1, nullable=False)
    outcome = Column(String(32), nullable=False)  # ELIGIBLE | INELIGIBLE | NEEDS_REVIEW
    decision_mode = Column(String(32), nullable=False)  # AUTOMATED | HUMAN_CONFIRMED | HUMAN_OVERRIDDEN
    policy_version = Column(String(64), nullable=False, default="CSSS-Demo-v1.0")
    confidence_summary = Column(JSON, nullable=False, default=dict)
    supersedes_decision_id = Column(String(36), nullable=True)
    is_final = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=get_utc_now, nullable=False)

    # Relationships
    application = relationship("Application", back_populates="decisions")
    rule_results = relationship("DecisionRuleResult", back_populates="decision", cascade="all, delete-orphan", order_by="DecisionRuleResult.rule_code")


class DecisionRuleResult(Base):
    __tablename__ = "decision_rule_results"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    decision_id = Column(String(36), ForeignKey("decisions.id", ondelete="CASCADE"), nullable=False, index=True)
    rule_code = Column(String(64), nullable=False)  # e.g. CSSS_INCOME_LIMIT
    result = Column(String(32), nullable=False)  # PASS | FAIL | NOT_EVALUATED | NEEDS_REVIEW
    input_snapshot = Column(JSON, nullable=False, default=dict)
    explanation = Column(Text, nullable=False)
    policy_version = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), default=get_utc_now, nullable=False)

    # Relationships
    decision = relationship("Decision", back_populates="rule_results")


class ReviewAction(Base):
    __tablename__ = "review_actions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    application_id = Column(String(36), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True)
    decision_id = Column(String(36), nullable=True)
    actor_id = Column(String(64), nullable=False)
    action_type = Column(String(64), nullable=False)  # CONFIRM_FIELD | EDIT_FIELD | OVERRIDE_DECISION | etc.
    field_name = Column(String(64), nullable=True)
    old_value = Column(JSON, nullable=True)
    new_value = Column(JSON, nullable=True)
    reason = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=get_utc_now, nullable=False)

    # Relationships
    application = relationship("Application", back_populates="review_actions")


class AuditLogEntry(Base):
    __tablename__ = "audit_log_entries"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    application_id = Column(String(36), ForeignKey("applications.id", ondelete="CASCADE"), nullable=True, index=True)
    action_type = Column(String(64), nullable=False, index=True)
    actor_id = Column(String(64), nullable=False)
    payload = Column(JSON, nullable=False)
    previous_entry_hash = Column(String(64), nullable=False)
    entry_hash = Column(String(64), nullable=False, unique=True, index=True)
    entry_hmac = Column(String(64), nullable=False)
    occurred_at = Column(String(64), nullable=False)  # ISO-8601 string, e.g. "2026-08-18T10:42:08Z"

    # Relationships
    application = relationship("Application", back_populates="audit_entries")
