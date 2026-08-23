"""
Pydantic schemas for Policy Versions and Rules.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class PolicyStatus(str, Enum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    RETIRED = "RETIRED"


class PolicyRuleDef(BaseModel):
    rule_code: str
    name: str
    description: str
    condition_expression: str
    field_dependencies: List[str]


class PolicyVersionCreate(BaseModel):
    scheme_code: str = "PM-USP-CSSS"
    version_string: str = Field(..., description="e.g. CSSS-Demo-v1.0")
    title: str
    description: Optional[str] = None
    rules_config: List[Dict[str, Any]] = []


class PolicyVersionResponse(BaseModel):
    id: str
    scheme_code: str
    version_string: str
    title: str
    description: Optional[str] = None
    status: str
    effective_from: Optional[datetime] = None
    effective_to: Optional[datetime] = None
    rules_config: List[Dict[str, Any]] = []
    created_at: datetime

    class Config:
        from_attributes = True
