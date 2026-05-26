"""
Incident prediction service for DB Sentinel AI.

Loads the Phase 5 model bundle produced by IA_BASES/src/train_incident_predictor.py
and exposes a small predict(features) API for FastAPI endpoints.
"""
from __future__ import annotations

import logging
import pickle
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

from app.core.paths import find_backend_root, find_workspace_root

logger = logging.getLogger(__name__)


class IncidentPredictorService:
    """Singleton service that keeps the incident predictor loaded in memory."""

    _instance: Optional["IncidentPredictorService"] = None

    def __init__(self, model_path: str | Path, feature_schema_path: str | Path | None = None):
        self.model_path = self.resolve_model_path(model_path)
        self.feature_schema_path = Path(feature_schema_path) if feature_schema_path else None
        if not self.model_path.exists():
            raise FileNotFoundError(f"Incident predictor model not found: {self.model_path}")

        with self.model_path.open("rb") as f:
            bundle = pickle.load(f)

        self.binary_predictor = bundle["binary_predictor"]
        self.multiclass_predictor = bundle["multiclass_predictor"]
        self.impact_predictor = bundle.get("impact_predictor")
        self.label_encoder = bundle["label_encoder"]
        self.impact_label_encoder = bundle.get("impact_label_encoder")
        self.feature_cols = list(bundle["feature_cols"])
        self.threshold = float(bundle.get("optimal_threshold", 0.5))
        self.model_version = bundle.get("model_version", "unknown")
        self.trained_at = bundle.get("trained_at")
        self.metrics = bundle.get("metrics", {})

        logger.info(
            "Incident predictor loaded from %s version=%s threshold=%.3f",
            self.model_path,
            self.model_version,
            self.threshold,
        )

    @staticmethod
    def resolve_model_path(model_path: str | Path) -> Path:
        candidate = Path(model_path)
        if candidate.exists():
            return candidate

        backend_model = find_backend_root(Path(__file__)) / "artifacts" / candidate.name
        if backend_model.exists():
            return backend_model

        ia_bases_model = find_workspace_root(Path(__file__)) / "IA_BASES" / "artifacts" / candidate.name
        if ia_bases_model.exists():
            return ia_bases_model
        return candidate

    @classmethod
    def get_instance(
        cls,
        model_path: str | Path,
        feature_schema_path: str | Path | None = None,
    ) -> "IncidentPredictorService":
        resolved_path = cls.resolve_model_path(model_path)
        if cls._instance is None or cls._instance.model_path != resolved_path:
            cls._instance = cls(resolved_path, feature_schema_path)
        return cls._instance

    def _frame_from_features(self, features: dict[str, Any]) -> pd.DataFrame:
        row = {feature: features.get(feature, 0.0) for feature in self.feature_cols}
        return pd.DataFrame([row], columns=self.feature_cols).fillna(0)

    def predict(self, features: dict[str, Any]) -> dict[str, Any]:
        """Predict incident risk and the most likely incident type."""
        x = self._frame_from_features(features)

        risk_score = float(self.binary_predictor.predict_proba(x)[0, 1])
        has_incident = risk_score >= self.threshold

        multi_proba = self.multiclass_predictor.predict_proba(x)[0]
        top_idx = np.argsort(multi_proba)[::-1][:3]
        top_predictions = [
            {
                "rank": rank + 1,
                "incident_type": str(self.label_encoder.classes_[idx]),
                "probability": float(multi_proba[idx]),
            }
            for rank, idx in enumerate(top_idx)
        ]

        impact_predictions = self._predict_impact(x)
        predicted_type = "none"
        if has_incident:
            predicted_type = next(
                (item["incident_type"] for item in top_predictions if item["incident_type"] != "none"),
                "unclassified_risk",
            )
        impact_level = self._risk_to_impact(risk_score)
        if impact_predictions:
            impact_level = impact_predictions[0]["impact_level"]
            if impact_level == "none" and has_incident:
                impact_level = self._risk_to_impact(risk_score)
        return {
            "risk_score": risk_score,
            "threshold": self.threshold,
            "has_predicted_incident": has_incident,
            "impact_level": impact_level,
            "predicted_incident_type": predicted_type,
            "top3_predictions": top_predictions,
            "top3_impact_predictions": impact_predictions,
            "model_version": self.model_version,
            "trained_at": self.trained_at,
        }

    def _predict_impact(self, x: pd.DataFrame) -> list[dict[str, Any]]:
        if self.impact_predictor is None or self.impact_label_encoder is None:
            return []
        proba = self.impact_predictor.predict_proba(x)[0]
        top_idx = np.argsort(proba)[::-1][:3]
        return [
            {
                "rank": rank + 1,
                "impact_level": str(self.impact_label_encoder.classes_[idx]),
                "probability": float(proba[idx]),
            }
            for rank, idx in enumerate(top_idx)
        ]

    @staticmethod
    def _risk_to_impact(score: float) -> str:
        if score >= 0.85:
            return "critical"
        if score >= 0.70:
            return "high"
        if score >= 0.50:
            return "medium"
        return "low"
