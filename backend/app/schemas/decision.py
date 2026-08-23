"""
Pydantic models for Decisions and Rule Results.
Matches docs/contracts/decision.json and docs/contracts/rule_result.json.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class RuleResultEnum(str, Enum):
    """Rule result enum from docs/CONVENTIONS.md."""
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_EVALUATED = "NOT_EVALUATED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class DecisionOutcome(str, Enum):
    """Decision outcome enum from docs/CONVENTIONS.md."""
    ELIGIBLE = "ELIGIBLE"
    INELIGIBLE = "INELIGIBLE"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class DecisionMode(str, Enum):
    """Decision mode enum from docs/CONVENTIONS.md."""
    AUTOMATED = "AUTOMATED"
    HUMAN_CONFIRMED = "HUMAN_CONFIRMED"
    HUMAN_OVERRIDDEN = "HUMAN_OVERRIDDEN"


class RuleResultSchema(BaseModel):
    """Matches docs/contracts/rule_result.json."""
    rule_code: str
    result: RuleResultEnum
    input_snapshot: Dict[str, Any] = Field(default_factory=dict)
    explanation: str
    policy_version: str

    class Config:
        from_attributes = True


class DecisionSchema(BaseModel):
    """Matches docs/contracts/decision.json."""
    decision_version: int
    outcome: DecisionOutcome
    decision_mode: DecisionMode
    policy_version: str
    confidence_summary: Dict[str, Any] = Field(default_factory=dict)
    supersedes_decision_id: Optional[str] = None

    class Config:
        from_attributes = True


class DecisionDetailResponse(DecisionSchema):
    """Decision with rule results for API response."""
    id: str
    application_id: str
    is_final: bool
    created_at: datetime
    rule_results: List[RuleResultSchema] = []

    class Config:
        from_attributes = True
