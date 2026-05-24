from sqlalchemy.orm import Session

from app.models import AuditEvent


def record_audit_event(
    db: Session,
    event_type: str,
    message: str,
    actor: str = "system",
    severity: str = "info",
    metadata: dict | None = None,
) -> AuditEvent:
    event = AuditEvent(
        event_type=event_type,
        actor=actor,
        message=message,
        severity=severity,
        metadata_json=metadata,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event
