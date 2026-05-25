"""
Prediction endpoints for DB Sentinel AI Phase 5.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models.sentinel_models import SentinelPredictionResult
from app.schemas.sentinel_schemas import PredictRequest, PredictResponse
from app.services.sentinel.feature_builder import FeatureBuilder
from app.services.sentinel.model_service import IncidentPredictorService
from app.services.sentinel.rca_service import RootCauseService

router = APIRouter()
settings = get_settings()
logger = logging.getLogger(__name__)


@router.post("/predict", response_model=PredictResponse, summary="Predice incidentes futuros")
def predict_incident(
    request: PredictRequest,
    db: Session = Depends(get_db),
) -> PredictResponse:
    feature_builder = FeatureBuilder(db)
    features = feature_builder.build_current_window(
        window_minutes=request.window_minutes,
        database_name=request.database_name,
    )
    if not features:
        raise HTTPException(
            status_code=503,
            detail="No hay suficiente telemetria reciente para predecir. Ejecuta el collector primero.",
        )

    predictor = IncidentPredictorService.get_instance(
        model_path=settings.sentinel_model_path,
        feature_schema_path=settings.sentinel_feature_schema_path,
    )
    prediction = predictor.predict(features)
    rca_result = RootCauseService.get_instance(settings.sentinel_rca_model_path).diagnose(
        features,
        top_n=3,
    )
    primary_cause = (
        rca_result["primary_cause"]
        if prediction["has_predicted_incident"]
        else "none"
    )
    predicted_at = datetime.now(timezone.utc)
    _record_prediction_result(db, prediction=prediction, predicted_at=predicted_at)

    return PredictResponse(
        risk_score=prediction["risk_score"],
        has_predicted_incident=prediction["has_predicted_incident"],
        predicted_incident_type=prediction["predicted_incident_type"],
        impact_level=prediction["impact_level"],
        top3_predictions=prediction["top3_predictions"],
        rca_top_causes=rca_result["top_causes"],
        primary_cause=primary_cause,
        primary_evidence_summary=rca_result["primary_evidence_summary"],
        current_metrics=features,
        horizon_minutes=request.horizon_minutes,
        predicted_at=predicted_at.isoformat(),
        model_version=prediction["model_version"],
    )


@router.get("/predict/history", summary="Historial de predicciones Sentinel")
def prediction_history(
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    rows = (
        db.query(SentinelPredictionResult)
        .order_by(SentinelPredictionResult.predicted_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": row.id,
            "predicted_at": row.predicted_at,
            "window_start": row.window_start,
            "window_end": row.window_end,
            "risk_score": row.risk_score,
            "predicted_incident_type": row.predicted_incident_type,
            "actual_incident_type": row.actual_incident_type,
            "was_correct": row.was_correct,
            "model_version": row.model_version,
        }
        for row in rows
    ]


@router.get("/model/metadata", summary="Metadata del predictor cargado")
def model_metadata() -> dict[str, Any]:
    predictor = IncidentPredictorService.get_instance(
        model_path=settings.sentinel_model_path,
        feature_schema_path=settings.sentinel_feature_schema_path,
    )
    return {
        "model_path": str(predictor.model_path),
        "model_version": predictor.model_version,
        "trained_at": predictor.trained_at,
        "threshold": predictor.threshold,
        "feature_count": len(predictor.feature_cols),
        "metrics": predictor.metrics,
    }


@router.get("/model/shap", summary="Feature importance del predictor")
def model_feature_importance(
    limit: int = Query(default=25, ge=1, le=100),
) -> list[dict[str, Any]]:
    predictor = IncidentPredictorService.get_instance(
        model_path=settings.sentinel_model_path,
        feature_schema_path=settings.sentinel_feature_schema_path,
    )
    top_features = predictor.metrics.get("top_features", [])
    return top_features[:limit]


@router.get("/rca/metadata", summary="Metadata del modelo RCA cargado")
def rca_metadata() -> dict[str, Any]:
    rca = RootCauseService.get_instance(settings.sentinel_rca_model_path)
    return {
        "model_path": str(rca.model_path),
        "model_version": rca.model_version,
        "trained_at": rca.trained_at,
        "classes": rca.classes,
        "feature_count": len(rca.feature_cols),
        "metrics": rca.metrics,
    }


@router.post("/diagnose", summary="Diagnostica causa raiz con RCA")
def diagnose_current_window(
    request: PredictRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    features = FeatureBuilder(db).build_current_window(
        window_minutes=request.window_minutes,
        database_name=request.database_name,
    )
    if not features:
        raise HTTPException(
            status_code=503,
            detail="No hay suficiente telemetria reciente para diagnosticar.",
        )
    return RootCauseService.get_instance(settings.sentinel_rca_model_path).diagnose(features, top_n=3)


def _record_prediction_result(
    db: Session,
    prediction: dict[str, Any],
    predicted_at: datetime,
) -> None:
    try:
        row = SentinelPredictionResult(
            predicted_at=predicted_at,
            risk_score=prediction.get("risk_score"),
            predicted_incident_type=prediction.get("predicted_incident_type"),
            model_version=prediction.get("model_version"),
        )
        db.add(row)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("No se pudo guardar historial de prediccion Sentinel")
