"""Incident management endpoints for DB Sentinel AI."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.sentinel_models import SentinelIncident
from app.schemas.sentinel_schemas import (
    IncidentDetailResponse,
    IncidentEvidenceResponse,
    IncidentListResponse,
    ResolveIncidentRequest,
)
from app.services.sentinel.audit_service import record_sentinel_action

router = APIRouter()


@router.get("/incidents", response_model=IncidentListResponse, summary="Lista incidentes Sentinel")
def list_incidents(
    status: Optional[str] = Query(default="all", pattern="^(open|resolved|all)$"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    since_hours: int = Query(default=168, ge=1, le=24 * 90),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    since = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    query = db.query(SentinelIncident).filter(SentinelIncident.detected_at >= since)
    if status and status != "all":
        query = query.filter(SentinelIncident.status == status)

    total = query.count()
    incidents = (
        query.order_by(SentinelIncident.detected_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {"incidents": incidents, "total": total, "limit": limit, "offset": offset}


@router.get(
    "/incidents/{incident_id}",
    response_model=IncidentDetailResponse,
    summary="Detalle de incidente Sentinel",
)
def get_incident(
    incident_id: int,
    db: Session = Depends(get_db),
) -> SentinelIncident:
    incident = db.get(SentinelIncident, incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incidente no encontrado")
    return incident


@router.get(
    "/incidents/{incident_id}/evidence",
    response_model=IncidentEvidenceResponse,
    summary="Evidencia tecnica de un incidente",
)
def get_incident_evidence(
    incident_id: int,
    window_minutes: int = Query(default=15, ge=5, le=120),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    incident = db.get(SentinelIncident, incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incidente no encontrado")

    detected_at = incident.detected_at
    since = detected_at - timedelta(minutes=window_minutes)
    until = detected_at + timedelta(minutes=5)
    metric_rows = db.execute(
        text(
            """
            SELECT
                collected_at, active_sessions, waiting_sessions, lock_waiting_sessions,
                idle_in_transaction, long_transactions_count, cache_hit_ratio,
                xact_commit_delta, xact_rollback_delta, deadlocks_delta,
                wal_bytes_delta, replication_lag_seconds
            FROM sentinel_metric_samples
            WHERE collected_at BETWEEN :since AND :until
            ORDER BY collected_at ASC
            """
        ),
        {"since": since, "until": until},
    ).fetchall()
    query_rows = db.execute(
        text(
            """
            SELECT
                collected_at, queryid, query_fingerprint, calls_delta,
                mean_exec_time, stddev_exec_time, rows_delta, wal_bytes_delta
            FROM sentinel_query_samples
            WHERE collected_at BETWEEN :since AND :until
            ORDER BY mean_exec_time DESC
            LIMIT 15
            """
        ),
        {"since": since, "until": until},
    ).fetchall()

    return {
        "incident_id": incident.id,
        "incident_type": incident.incident_type,
        "risk_score": incident.risk_score,
        "root_cause_top1": incident.root_cause_top1,
        "root_cause_top3": incident.root_cause_top3,
        "llm_explanation": incident.llm_explanation,
        "llm_recommended_actions": incident.llm_recommended_actions,
        "metrics_timeline": [dict(row._mapping) for row in metric_rows],
        "slow_queries": [dict(row._mapping) for row in query_rows],
    }


@router.patch(
    "/incidents/{incident_id}/resolve",
    response_model=IncidentDetailResponse,
    summary="Marca un incidente como resuelto",
)
def resolve_incident(
    incident_id: int,
    request: ResolveIncidentRequest,
    db: Session = Depends(get_db),
) -> SentinelIncident:
    incident = db.get(SentinelIncident, incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incidente no encontrado")

    incident.status = "resolved"
    incident.resolved_at = datetime.now(timezone.utc)
    incident.dba_action_taken = request.action_taken
    db.add(incident)
    db.commit()
    db.refresh(incident)

    record_sentinel_action(
        db,
        incident_id=incident.id,
        action_type="incident.resolved",
        action_detail=request.action_taken or "Incidente marcado como resuelto.",
        approved_by=request.resolved_by,
    )
    return incident


@router.get("/explain/{incident_id}", summary="Obtiene explicación guardada de un incidente")
def get_saved_explanation(
    incident_id: int,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    incident = db.get(SentinelIncident, incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incidente no encontrado")
    return {
        "incident_id": incident.id,
        "incident_summary": incident.llm_explanation,
        "recommended_actions": incident.llm_recommended_actions or [],
        "root_cause_top3": incident.root_cause_top3 or [],
        "status": incident.status,
    }
