"""
Security, roles, and cryptographic utilities for Project Synapse.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from enum import Enum
from typing import Any, Dict, List, Optional

from fastapi import Depends, Header, HTTPException, status
from app.core.config import settings


class UserRole(str, Enum):
    """User roles from docs/CONVENTIONS.md."""
    ADMIN = "ADMIN"
    PROCESSOR = "PROCESSOR"
    REVIEWER = "REVIEWER"
    AUDITOR = "AUDITOR"


# Permission definition
PERMISSIONS = {
    UserRole.ADMIN: {"upload", "process", "override", "publish_policy", "verify_audit", "view"},
    UserRole.PROCESSOR: {"upload", "process", "view"},
    UserRole.REVIEWER: {"view", "process", "override", "verify_audit"},
    UserRole.AUDITOR: {"view", "verify_audit"},
}

ZERO_HASH = "0" * 64


def canonical_json(data: Any) -> str:
    """
    Serialize JSON in a strict canonical format for hashing:
    - Keys sorted alphabetically
    - No whitespace around separators
    - UTF-8 representation (ensure_ascii=False)
    """
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_sha256(text: str) -> str:
    """Compute SHA-256 hex digest of a UTF-8 string."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def compute_bytes_sha256(data: bytes) -> str:
    """Compute SHA-256 hex digest of raw binary bytes (e.g. uploaded file)."""
    return hashlib.sha256(data).hexdigest()


def compute_entry_hash(
    previous_hash: str,
    payload: Dict[str, Any],
    actor_id: str,
    action_type: str,
    occurred_at: str,
) -> str:
    """
    Compute hash for an audit log entry:
    entry_hash = SHA256(previous_hash + canonical(payload) + actor_id + action_type + occurred_at)
    """
    canonical_payload = canonical_json(payload)
    raw_material = f"{previous_hash}{canonical_payload}{actor_id}{action_type}{occurred_at}"
    return compute_sha256(raw_material)


def compute_entry_hmac(entry_hash: str, secret: Optional[str] = None) -> str:
    """
    Compute HMAC-SHA256 of entry_hash using the server secret key:
    entry_hmac = HMAC_SHA256(server_secret, entry_hash)
    """
    key = (secret or settings.HMAC_SECRET).encode("utf-8")
    return hmac.new(key, entry_hash.encode("utf-8"), hashlib.sha256).hexdigest()


class CurrentUser:
    """Represents the authenticated actor in the request context."""
    def __init__(self, user_id: str, role: UserRole):
        self.user_id = user_id
        self.role = role

    def has_permission(self, action: str) -> bool:
        return action in PERMISSIONS.get(self.role, set())


def get_current_user(
    x_user_id: Optional[str] = Header(default="admin-001"),
    x_user_role: Optional[str] = Header(default="ADMIN"),
) -> CurrentUser:
    """
    Extracts current user from request headers (or defaults to ADMIN for local demo).
    Can be replaced/extended with Supabase Auth JWT verification in cloud deployment.
    """
    try:
        role = UserRole(x_user_role.upper())
    except Exception:
        role = UserRole.ADMIN

    return CurrentUser(user_id=x_user_id or "admin-001", role=role)


def require_permission(permission: str):
    """Dependency factory that enforces permissions based on role."""
    def _dependency(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not user.has_permission(permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user.role.value}' does not have permission '{permission}'."
            )
        return user
    return _dependency
