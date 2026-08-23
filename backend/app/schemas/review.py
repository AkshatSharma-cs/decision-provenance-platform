"""
Pydantic schemas for Human Review Actions and Overrides.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ReviewActionType(str, Enum):
    CONFIRM_FIELD = "CONFIRM_FIELD"
    EDIT_FIELD = "EDIT_FIELD"
    REJECT_FIELD = "REJECT_FIELD"
    ACCEPT_DECISION = "ACCEPT_DECISION"
    OVERRIDE_DECISION = "OVERRIDE_DECISION"
    REQUEST_DOCUMENT = "REQUEST_DOCUMENT"
    ADD_NOTE = "ADD_NOTE"


class OverrideFieldItem(BaseModel):
    field_name: str
    new_value: Any
    reason: str = Field(..., min_length=3, description="Mandatory reason for override")


class ReviewActionCreate(BaseModel):
    action_type: ReviewActionType
    field_name: Optional[str] = None
    old_value: Optional[Any] = None
    new_value: Optional[Any] = None
    reason: str = Field(..., min_length=3, description="Required explanation for the action")


class ReviewActionResponse(BaseModel):
    id: str
    application_id: str
    decision_id: Optional[str] = None
    actor_id: str
    action_type: str
    field_name: Optional[str] = None
    old_value: Optional[Any] = None
    new_value: Optional[Any] = None
    reason: str
    created_at: datetime

    class Config:
        from_attributes = True


class BulkReviewSubmitRequest(BaseModel):
    overrides: List[OverrideFieldItem] = []
    decision_override: Optional[str] = None  # e.g. "ELIGIBLE" / "INELIGIBLE"
    reason: str = Field(..., min_length=3, description="Overall review justification")
