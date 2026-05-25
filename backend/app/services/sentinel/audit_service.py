"""Audit helpers for DB Sentinel AI DBA actions."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.sentinel_models import SentinelAuditLog


def record_sentinel_action(
    db: Session,
    action_type: str,
    action_detail: str,
    incident_id: int | None = None,
    approved_by: str = "system",
) -> SentinelAuditLog:
    entry = SentinelAuditLog(
        incident_id=incident_id,
        action_type=action_type,
        action_detail=action_detail,
        approved_by=approved_by,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry
