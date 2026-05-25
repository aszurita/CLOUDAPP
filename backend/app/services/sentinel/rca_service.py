"""
Root Cause Analysis service for DB Sentinel AI.

Loads the Phase 6 RCA bundle and returns Top-N likely causes with DBA-friendly
evidence features and recommended actions.
"""
from __future__ import annotations

import logging
import pickle
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class RootCauseService:
    """Singleton service that keeps the RCA model loaded in memory."""

    _instance: Optional["RootCauseService"] = None

    def __init__(self, model_path: str | Path):
        self.model_path = self.resolve_model_path(model_path)
        if not self.model_path.exists():
            raise FileNotFoundError(f"RCA model not found: {self.model_path}")

        with self.model_path.open("rb") as f:
            bundle = pickle.load(f)

        self.classifier = bundle["rca_classifier"]
        self.label_encoder = bundle["label_encoder"]
        self.feature_cols = list(bundle["feature_cols"])
        self.model_version = bundle.get("model_version", "unknown")
        self.trained_at = bundle.get("trained_at")
        self.classes = list(bundle.get("classes", self.label_encoder.classes_))
        self.metrics = bundle.get("metrics", {})
        self.global_importance = list(bundle.get("global_importance", []))
        self.cause_runbooks = dict(bundle.get("cause_runbooks", {}))

        logger.info(
            "RCA model loaded from %s version=%s classes=%s",
            self.model_path,
            self.model_version,
            self.classes,
        )

    @staticmethod
    def resolve_model_path(model_path: str | Path) -> Path:
        candidate = Path(model_path)
        if candidate.exists():
            return candidate
        project_root = Path(__file__).resolve().parents[5]
        ia_bases_model = project_root / "IA_BASES" / "artifacts" / candidate.name
        if ia_bases_model.exists():
            return ia_bases_model
        return candidate

    @classmethod
    def get_instance(cls, model_path: str | Path) -> "RootCauseService":
        resolved_path = cls.resolve_model_path(model_path)
        if cls._instance is None or cls._instance.model_path != resolved_path:
            cls._instance = cls(resolved_path)
        return cls._instance

    def _frame_from_features(self, features: dict[str, Any]) -> pd.DataFrame:
        row = {feature: features.get(feature, 0.0) for feature in self.feature_cols}
        return pd.DataFrame([row], columns=self.feature_cols).fillna(0)

    def diagnose(self, features: dict[str, Any], top_n: int = 3) -> dict[str, Any]:
        x = self._frame_from_features(features)
        proba = self.classifier.predict_proba(x)[0]
        top_idx = np.argsort(proba)[::-1][:top_n]
        top_causes = [
            self._format_cause(rank + 1, int(class_idx), float(proba[class_idx]), x)
            for rank, class_idx in enumerate(top_idx)
        ]

        primary = top_causes[0] if top_causes else None
        evidence_summary = self._summary(primary) if primary else ""
        return {
            "top_causes": top_causes,
            "primary_cause": primary["cause"] if primary else "unknown",
            "primary_confidence": primary["confidence"] if primary else 0.0,
            "primary_evidence_summary": evidence_summary,
            "model_version": self.model_version,
            "trained_at": self.trained_at,
        }

    def _format_cause(self, rank: int, class_idx: int, confidence: float, x: pd.DataFrame) -> dict[str, Any]:
        cause = str(self.label_encoder.classes_[class_idx])
        runbook = self.cause_runbooks.get(cause, {})
        evidence = self._evidence_features(x)
        return {
            "rank": rank,
            "cause": cause,
            "confidence": confidence,
            "summary": runbook.get("summary", ""),
            "recommended_actions": runbook.get("actions", []),
            "evidence_features": evidence,
        }

    def _evidence_features(self, x: pd.DataFrame, limit: int = 5) -> list[dict[str, Any]]:
        if not self.global_importance:
            return []
        rows = sorted(
            self.global_importance,
            key=lambda item: float(item.get("importance", 0.0)),
            reverse=True,
        )[:limit]
        evidence = []
        for item in rows:
            feature = str(item.get("feature"))
            value = float(x.iloc[0][feature]) if feature in x.columns else 0.0
            evidence.append(
                {
                    "feature": feature,
                    "value": value,
                    "importance": float(item.get("importance", 0.0)),
                    "direction": "supports_cause",
                }
            )
        return evidence

    @staticmethod
    def _summary(primary: dict[str, Any]) -> str:
        parts = [
            f"{item['feature']}={item['value']:.2f}"
            for item in primary.get("evidence_features", [])[:3]
        ]
        return ", ".join(parts)
