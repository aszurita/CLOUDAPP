"""DBA Copilot endpoints for DB Sentinel AI Phase 7."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models.sentinel_models import SentinelIncident
from app.schemas.sentinel_schemas import CopilotResponse, ExplainRequest
from app.services.sentinel.audit_service import record_sentinel_action
from app.services.sentinel.feature_builder import FeatureBuilder
from app.services.sentinel.llm_copilot import DBACopilotService
from app.services.sentinel.model_service import IncidentPredictorService
from app.services.sentinel.rca_service import RootCauseService

router = APIRouter()
settings = get_settings()


@router.post("/explain", response_model=CopilotResponse, summary="Genera briefing DBA Copilot")
async def explain_current_state(
    request: ExplainRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    features, prediction, rca_result = _build_prediction_context(request, db)
    slow_queries = _load_slow_queries(db, minutes=request.window_minutes)

    copilot = DBACopilotService()
    analysis = await copilot.analyze_incident(
        prediction=prediction,
        rca_result=rca_result,
        current_metrics=features,
        slow_queries=slow_queries,
        use_llm=request.use_llm,
    )

    incident_id = None
    if request.persist_incident:
        incident = _save_incident(
            db=db,
            request=request,
            prediction=prediction,
            rca_result=rca_result,
            features=features,
            analysis=analysis,
        )
        incident_id = incident.id
        record_sentinel_action(
            db,
            incident_id=incident.id,
            action_type="copilot.analysis_generated",
            action_detail=analysis["incident_summary"],
            approved_by="system",
        )
    analysis["incident_id"] = incident_id
    return analysis


def _build_prediction_context(
    request: ExplainRequest,
    db: Session,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if request.incident_id and not request.use_current_metrics:
        incident = db.get(SentinelIncident, request.incident_id)
        if not incident:
            raise HTTPException(status_code=404, detail="Incidente no encontrado")
        features = incident.evidence or {}
        prediction = {
            "engine": incident.engine or request.engine,
            "database_name": incident.database_name or request.database_name,
            "risk_score": incident.risk_score or 0.0,
            "has_predicted_incident": bool((incident.risk_score or 0.0) >= settings.sentinel_risk_threshold),
            "predicted_incident_type": incident.incident_type or "unknown",
            "impact_level": incident.impact_level or "unknown",
            "top3_predictions": [],
            "horizon_minutes": request.horizon_minutes,
        }
        rca_result = {
            "top_causes": incident.root_cause_top3 or [],
            "primary_cause": incident.root_cause_top1 or "unknown",
            "primary_confidence": (incident.root_cause_top3 or [{}])[0].get("confidence", 0.0),
            "primary_evidence_summary": "",
            "model_version": "stored",
        }
        return features, prediction, rca_result

    features = FeatureBuilder(db).build_current_window(
        window_minutes=request.window_minutes,
        database_name=request.database_name,
    )
    if not features:
        raise HTTPException(
            status_code=503,
            detail="No hay suficiente telemetria reciente para explicar.",
        )

    predictor = IncidentPredictorService.get_instance(
        model_path=settings.sentinel_model_path,
        feature_schema_path=settings.sentinel_feature_schema_path,
    )
    prediction = predictor.predict(features)
    prediction["engine"] = request.engine
    prediction["database_name"] = request.database_name
    prediction["horizon_minutes"] = request.horizon_minutes
    rca_result = RootCauseService.get_instance(settings.sentinel_rca_model_path).diagnose(features, top_n=3)
    return features, prediction, rca_result


def _load_slow_queries(db: Session, minutes: int) -> list[dict[str, Any]]:
    since = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    rows = db.execute(
        text(
            """
            SELECT queryid, query_fingerprint, mean_exec_time, calls_delta, rows_delta, wal_bytes_delta
            FROM sentinel_query_samples
            WHERE collected_at > :since
            ORDER BY mean_exec_time DESC
            LIMIT 5
            """
        ),
        {"since": since},
    ).fetchall()
    return [dict(row._mapping) for row in rows]


def _save_incident(
    db: Session,
    request: ExplainRequest,
    prediction: dict[str, Any],
    rca_result: dict[str, Any],
    features: dict[str, Any],
    analysis: dict[str, Any],
) -> SentinelIncident:
    detected_at = datetime.now(timezone.utc)
    incident = SentinelIncident(
        detected_at=detected_at,
        predicted_for=detected_at + timedelta(minutes=request.horizon_minutes),
        engine=request.engine,
        database_name=request.database_name,
        incident_type=prediction.get("predicted_incident_type"),
        risk_score=prediction.get("risk_score"),
        impact_level=analysis.get("severity_classification") or prediction.get("impact_level"),
        root_cause_top1=rca_result.get("primary_cause"),
        root_cause_top3=rca_result.get("top_causes"),
        evidence=features,
        llm_explanation=analysis.get("incident_summary"),
        llm_recommended_actions=analysis.get("recommended_actions"),
        status="open",
    )
    db.add(incident)
    db.commit()
    db.refresh(incident)
    return incident
