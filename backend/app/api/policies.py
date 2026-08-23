"""
Policy Management API Endpoints.
Allows viewing and publishing versioned policy rule configurations.
"""

from __future__ import annotations

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, require_permission
from app.db.session import get_db
from app.db.models import PolicyVersion
from app.schemas.policy import PolicyVersionCreate, PolicyVersionResponse
from app.services.audit_service import AuditService

router = APIRouter(prefix="/policies", tags=["Policies"])


@router.get("", response_model=List[PolicyVersionResponse])
def list_policies(
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission("view")),
):
    """Lists all available policy versions and their rules."""
    return db.query(PolicyVersion).order_by(PolicyVersion.created_at.desc()).all()


@router.post("", response_model=PolicyVersionResponse, status_code=status.HTTP_201_CREATED)
def create_policy_version(
    payload: PolicyVersionCreate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission("publish_policy")),
):
    """Creates a new policy version in DRAFT state."""
    existing = db.query(PolicyVersion).filter(
        PolicyVersion.version_string == payload.version_string
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Policy version '{payload.version_string}' already exists.")

    policy = PolicyVersion(
        scheme_code=payload.scheme_code,
        version_string=payload.version_string,
        title=payload.title,
        description=payload.description,
        status="DRAFT",
        rules_config=payload.rules_config,
    )
    db.add(policy)
    db.flush()

    AuditService.append_audit_event(
        db=db,
        action_type="POLICY_CREATED",
        payload={
            "version_string": policy.version_string,
            "title": policy.title,
            "rules_count": len(policy.rules_config or []),
        },
        actor_id=user.user_id,
    )

    db.commit()
    db.refresh(policy)
    return policy


@router.post("/{id}/publish", response_model=PolicyVersionResponse)
def publish_policy(
    id: str,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission("publish_policy")),
):
    """Publishes an active policy version."""
    policy = db.query(PolicyVersion).filter(
        (PolicyVersion.id == id) | (PolicyVersion.version_string == id)
    ).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found.")

    policy.status = "PUBLISHED"

    AuditService.append_audit_event(
        db=db,
        action_type="POLICY_PUBLISHED",
        payload={
            "policy_id": policy.id,
            "version_string": policy.version_string,
            "publisher": user.user_id,
        },
        actor_id=user.user_id,
    )

    db.commit()
    db.refresh(policy)
    return policy
