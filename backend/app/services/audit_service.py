"""
Tamper-Evident Hash-Chain and HMAC Audit Service.
Implements SHA-256 linear hash chaining + HMAC-SHA256 integrity verification.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    ZERO_HASH,
    canonical_json,
    compute_entry_hash,
    compute_entry_hmac,
)
from app.db.models import AuditLogEntry
from app.schemas.audit import AuditVerifyResponse, BrokenAuditEntry


def get_current_iso_utc() -> str:
    """Format current time as ISO 8601 UTC string (e.g. 2026-08-18T10:42:08Z)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _order_chain_entries(entries: List[AuditLogEntry]) -> List[AuditLogEntry]:
    """Orders entries by following hash-chain links starting from ZERO_HASH."""
    if not entries:
        return []
    by_prev_hash: Dict[str, AuditLogEntry] = {}
    for e in entries:
        by_prev_hash[e.previous_entry_hash] = e

    ordered: List[AuditLogEntry] = []
    visited_ids = set()
    curr_prev = ZERO_HASH
    while curr_prev in by_prev_hash:
        entry = by_prev_hash[curr_prev]
        if entry.id in visited_ids:
            break
        visited_ids.add(entry.id)
        ordered.append(entry)
        curr_prev = entry.entry_hash
        if len(ordered) == len(entries):
            break

    # If any disconnected/tampered entries remain, append them to verify failure
    if len(ordered) < len(entries):
        for e in entries:
            if e.id not in visited_ids:
                ordered.append(e)

    return ordered


class AuditService:
    """
    Manages appending audit events to the tamper-evident hash chain
    and validating cryptographic integrity.
    """

    @staticmethod
    def append_audit_event(
        db: Session,
        action_type: str,
        payload: Dict[str, Any],
        actor_id: str = "system",
        application_id: Optional[str] = None,
        occurred_at: Optional[str] = None,
        auto_commit: bool = False,
    ) -> AuditLogEntry:
        """
        Appends an event to the global/application hash chain.
        Must be called within the same DB transaction as the state change.
        """
        timestamp = occurred_at or get_current_iso_utc()

        # Find previous entry in this application's chain (or global chain)
        query = db.query(AuditLogEntry)
        if application_id:
            query = query.filter(AuditLogEntry.application_id == application_id)
        
        all_entries = query.all()
        if not all_entries:
            previous_hash = ZERO_HASH
        else:
            ordered = _order_chain_entries(all_entries)
            previous_hash = ordered[-1].entry_hash

        # Compute hash and HMAC
        entry_hash = compute_entry_hash(
            previous_hash=previous_hash,
            payload=payload,
            actor_id=actor_id,
            action_type=action_type,
            occurred_at=timestamp,
        )
        entry_hmac = compute_entry_hmac(entry_hash, settings.HMAC_SECRET)

        new_entry = AuditLogEntry(
            application_id=application_id,
            action_type=action_type,
            actor_id=actor_id,
            payload=payload,
            previous_entry_hash=previous_hash,
            entry_hash=entry_hash,
            entry_hmac=entry_hmac,
            occurred_at=timestamp,
        )

        db.add(new_entry)
        if auto_commit:
            db.commit()
            db.refresh(new_entry)
        else:
            db.flush()

        return new_entry

    @staticmethod
    def verify_audit_chain(
        db: Session,
        application_id: Optional[str] = None,
    ) -> AuditVerifyResponse:
        """
        Recomputes every hash and HMAC in chronological sequence.
        If application_id is provided, verifies that application's chain.
        If application_id is None, verifies all application chains + global entries.
        Identifies the exact index and ID of the first broken entry if tampered.
        """
        query = db.query(AuditLogEntry)
        if application_id:
            query = query.filter(AuditLogEntry.application_id == application_id)
            chains = {application_id: _order_chain_entries(query.all())}
        else:
            all_entries = query.all()
            chains: Dict[Optional[str], List[AuditLogEntry]] = {}
            for entry in all_entries:
                chains.setdefault(entry.application_id, []).append(entry)
            chains = {app_k: _order_chain_entries(entries_list) for app_k, entries_list in chains.items()}

        total_entries = sum(len(entries) for entries in chains.values())
        if total_entries == 0:
            return AuditVerifyResponse(
                verified=True,
                total_entries=0,
                first_broken_entry=None,
                message="Audit log is empty (verified)."
            )

        for app_key, entries in chains.items():
            previous = ZERO_HASH
            for idx, entry in enumerate(entries):
                # 1. Verify previous hash link
                if entry.previous_entry_hash != previous:
                    return AuditVerifyResponse(
                        verified=False,
                        total_entries=total_entries,
                        first_broken_entry=BrokenAuditEntry(
                            index=idx,
                            entry_id=entry.id,
                            action_type=entry.action_type,
                            expected_hash=previous,
                            actual_hash=entry.previous_entry_hash,
                            expected_hmac="",
                            actual_hmac=entry.entry_hmac,
                            reason="Broken link: previous_entry_hash does not match preceding entry_hash."
                        ),
                        message=f"Tampering detected at entry {idx} ({entry.action_type}): broken hash link."
                    )

                # 2. Recompute expected hash
                expected_hash = compute_entry_hash(
                    previous_hash=previous,
                    payload=entry.payload,
                    actor_id=entry.actor_id,
                    action_type=entry.action_type,
                    occurred_at=entry.occurred_at,
                )

                if expected_hash != entry.entry_hash:
                    return AuditVerifyResponse(
                        verified=False,
                        total_entries=total_entries,
                        first_broken_entry=BrokenAuditEntry(
                            index=idx,
                            entry_id=entry.id,
                            action_type=entry.action_type,
                            expected_hash=expected_hash,
                            actual_hash=entry.entry_hash,
                            expected_hmac="",
                            actual_hmac=entry.entry_hmac,
                            reason="Payload or metadata altered: hash recomputation mismatch."
                        ),
                        message=f"Tampering detected at entry {idx} ({entry.action_type}): payload altered."
                    )

                # 3. Recompute HMAC signature
                expected_hmac = compute_entry_hmac(entry.entry_hash, settings.HMAC_SECRET)
                if expected_hmac != entry.entry_hmac:
                    return AuditVerifyResponse(
                        verified=False,
                        total_entries=total_entries,
                        first_broken_entry=BrokenAuditEntry(
                            index=idx,
                            entry_id=entry.id,
                            action_type=entry.action_type,
                            expected_hash=entry.entry_hash,
                            actual_hash=entry.entry_hash,
                            expected_hmac=expected_hmac,
                            actual_hmac=entry.entry_hmac,
                            reason="HMAC signature invalid: server secret mismatch or entry fabricated."
                        ),
                        message=f"Tampering detected at entry {idx} ({entry.action_type}): invalid HMAC signature."
                    )

                previous = entry.entry_hash

        return AuditVerifyResponse(
            verified=True,
            total_entries=total_entries,
            first_broken_entry=None,
            message=f"Audit chain fully verified. All {total_entries} events cryptographically intact."
        )
