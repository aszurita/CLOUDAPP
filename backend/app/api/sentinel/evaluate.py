"""Model evaluation endpoints for DB Sentinel AI."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from app.core.config import get_settings
from app.services.sentinel.model_service import IncidentPredictorService
from app.services.sentinel.rca_service import RootCauseService

router = APIRouter()
settings = get_settings()


@router.get("/evaluate/model/metrics", summary="Metricas de modelos Sentinel cargados")
def model_metrics() -> dict[str, Any]:
    predictor = IncidentPredictorService.get_instance(
        model_path=settings.sentinel_model_path,
        feature_schema_path=settings.sentinel_feature_schema_path,
    )
    rca = RootCauseService.get_instance(settings.sentinel_rca_model_path)
    return {
        "predictor": {
            "model_version": predictor.model_version,
            "trained_at": predictor.trained_at,
            "threshold": predictor.threshold,
            "feature_count": len(predictor.feature_cols),
            "binary": predictor.metrics.get("binary"),
            "multiclass": predictor.metrics.get("multiclass"),
            "impact": predictor.metrics.get("impact"),
        },
        "rca": {
            "model_version": rca.model_version,
            "trained_at": rca.trained_at,
            "selected_model": rca.metrics.get("selected_model"),
            "classes": rca.classes,
            "feature_count": len(rca.feature_cols),
            "val": rca.metrics.get("val"),
            "test": rca.metrics.get("test"),
        },
    }


@router.get("/evaluate/model/shap", summary="Importancia de features Predictor/RCA")
def model_shap(
    model: str = Query(default="predictor", pattern="^(predictor|rca)$"),
    limit: int = Query(default=25, ge=1, le=100),
) -> dict[str, Any]:
    if model == "rca":
        rca = RootCauseService.get_instance(settings.sentinel_rca_model_path)
        return {
            "model": "rca",
            "explainability_method": rca.metrics.get("explainability_method"),
            "top_features": rca.metrics.get("top_features", [])[:limit],
        }

    predictor = IncidentPredictorService.get_instance(
        model_path=settings.sentinel_model_path,
        feature_schema_path=settings.sentinel_feature_schema_path,
    )
    return {
        "model": "predictor",
        "explainability_method": predictor.metrics.get("explainability_method"),
        "top_features": predictor.metrics.get("top_features", [])[:limit],
    }
