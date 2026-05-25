"""
DBA Copilot for DB Sentinel AI.

The ML models predict and diagnose. This service turns their output into a DBA
brief: business impact, evidence, safe diagnostic SQL, and recommended actions.
It has a deterministic fallback so demos work without external LLM calls.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from app.core.config import get_settings
from app.services.sentinel.prompts import (
    META_AGENT_SYSTEM_PROMPT,
    META_AGENT_USER_TEMPLATE,
    SAFE_DIAGNOSTIC_SQLS,
)

logger = logging.getLogger(__name__)

FORBIDDEN_SQL = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE|ALTER|CREATE|REPLACE|GRANT|REVOKE|VACUUM|ANALYZE\s+\w|CALL|DO|COPY|"
    r"PG_TERMINATE_BACKEND|PG_CANCEL_BACKEND|PG_RELOAD_CONF|PG_ROTATE_LOGFILE|PG_SWITCH_WAL|SETVAL|NEXTVAL)\b",
    re.IGNORECASE,
)
ALLOWED_SQL_START = re.compile(r"^\s*(SELECT|WITH|SHOW|EXPLAIN)\b", re.IGNORECASE)


def is_safe_diagnostic_sql(sql: str) -> bool:
    """Allow only read-only diagnostic SQL."""
    normalized = sql.strip()
    if not normalized:
        return False
    if ";" in normalized.rstrip(";"):
        return False
    if not ALLOWED_SQL_START.search(normalized):
        return False
    return FORBIDDEN_SQL.search(normalized) is None


def safe_sql_catalog(cause: str) -> list[dict[str, str]]:
    sqls = [
        *SAFE_DIAGNOSTIC_SQLS.get(cause, []),
        *SAFE_DIAGNOSTIC_SQLS.get("generic", []),
    ]
    return [item for item in sqls if is_safe_diagnostic_sql(item.get("sql", ""))]


class DBACopilotService:
    """Generates DBA-facing explanations and recommended next steps."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.model = self.settings.sentinel_llm_model

    async def analyze_incident(
        self,
        prediction: dict[str, Any],
        rca_result: dict[str, Any],
        current_metrics: dict[str, Any],
        slow_queries: list[dict[str, Any]],
        use_llm: bool = False,
    ) -> dict[str, Any]:
        cause = rca_result.get("primary_cause") or prediction.get("predicted_incident_type") or "generic"
        diagnostic_sqls = safe_sql_catalog(cause)

        if use_llm and self._llm_configured():
            try:
                return await self._analyze_with_llm(
                    prediction=prediction,
                    rca_result=rca_result,
                    current_metrics=current_metrics,
                    slow_queries=slow_queries,
                    diagnostic_sqls=diagnostic_sqls,
                )
            except Exception:
                logger.exception("DBA Copilot LLM call failed; using deterministic fallback")

        return self._fallback_analysis(
            prediction=prediction,
            rca_result=rca_result,
            current_metrics=current_metrics,
            slow_queries=slow_queries,
            diagnostic_sqls=diagnostic_sqls,
        )

    def _llm_configured(self) -> bool:
        key = self.settings.sentinel_openai_api_key or self.settings.openai_api_key
        return bool(key and not key.startswith("phase-"))

    async def _analyze_with_llm(
        self,
        prediction: dict[str, Any],
        rca_result: dict[str, Any],
        current_metrics: dict[str, Any],
        slow_queries: list[dict[str, Any]],
        diagnostic_sqls: list[dict[str, str]],
    ) -> dict[str, Any]:
        from openai import AsyncOpenAI

        key = self.settings.sentinel_openai_api_key or self.settings.openai_api_key
        client = AsyncOpenAI(api_key=key)
        user_message = META_AGENT_USER_TEMPLATE.format(
            engine=prediction.get("engine", "postgresql"),
            database_name=prediction.get("database_name", "core_banking_sim"),
            predicted_at=datetime.now(timezone.utc).isoformat(),
            risk_score=f"{prediction.get('risk_score', 0):.4f}",
            impact_level=prediction.get("impact_level", "unknown"),
            predicted_incident_type=prediction.get("predicted_incident_type", "unknown"),
            horizon_minutes=prediction.get("horizon_minutes", 10),
            predictor_evidence=self._format_predictor_evidence(prediction),
            rca_diagnosis=self._format_rca(rca_result),
            current_metrics=self._format_metrics(current_metrics),
            slow_queries=self._format_queries(slow_queries),
        )
        completion = await client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": META_AGENT_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=2000,
        )
        body = json.loads(completion.choices[0].message.content or "{}")
        fallback = self._fallback_analysis(
            prediction=prediction,
            rca_result=rca_result,
            current_metrics=current_metrics,
            slow_queries=slow_queries,
            diagnostic_sqls=diagnostic_sqls,
        )
        return self._normalize_llm_response(
            llm_body=body,
            fallback=fallback,
            diagnostic_sqls=diagnostic_sqls,
            tokens_used=completion.usage.total_tokens if completion.usage else None,
        )

    def _fallback_analysis(
        self,
        prediction: dict[str, Any],
        rca_result: dict[str, Any],
        current_metrics: dict[str, Any],
        slow_queries: list[dict[str, Any]],
        diagnostic_sqls: list[dict[str, str]],
    ) -> dict[str, Any]:
        risk_score = float(prediction.get("risk_score", 0.0) or 0.0)
        impact_level = prediction.get("impact_level") or self._severity_from_risk(risk_score)
        has_incident = bool(prediction.get("has_predicted_incident", False))
        predicted_type = prediction.get("predicted_incident_type", "none")
        primary_cause = rca_result.get("primary_cause", "unknown")
        confidence = float(rca_result.get("primary_confidence", 0.0) or 0.0)
        severity = self._severity_from_context(risk_score, impact_level, has_incident)
        affected_operations = self._affected_operations(primary_cause, predicted_type)
        evidence = self._evidence_signals(prediction, rca_result, current_metrics, slow_queries)

        return {
            "incident_summary": self._summary(predicted_type, primary_cause, risk_score, confidence, has_incident),
            "impact_description": self._impact_description(severity, affected_operations, primary_cause),
            "severity_classification": severity,
            "affected_operations": affected_operations,
            "top3_causes": rca_result.get("top_causes", []),
            "evidence_signals": evidence,
            "recommended_actions": self._recommended_actions(primary_cause, severity, diagnostic_sqls),
            "diagnostic_sqls": diagnostic_sqls,
            "escalation_needed": severity in {"critical", "high"},
            "escalation_reason": self._escalation_reason(severity, risk_score, primary_cause),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "model_used": "deterministic_dba_copilot",
            "tokens_used": 0,
            "safety_mode": "recommend_approve_execute_audit",
        }

    @staticmethod
    def _severity_from_risk(score: float) -> str:
        if score >= 0.85:
            return "critical"
        if score >= 0.70:
            return "high"
        if score >= 0.50:
            return "medium"
        return "low"

    def _severity_from_context(self, score: float, impact_level: str, has_incident: bool) -> str:
        if not has_incident and score < 0.50:
            return "low"
        if impact_level in {"critical", "high", "medium", "low"}:
            return impact_level
        return self._severity_from_risk(score)

    @staticmethod
    def _affected_operations(cause: str, incident_type: str) -> list[str]:
        if cause in {"lock_wait_storm", "deadlock"} or incident_type in {"lock_wait_storm", "deadlock"}:
            return ["transferencias", "pagos en línea", "actualización de saldos", "operaciones transaccionales"]
        if cause == "concurrent_commits":
            return ["lotes contables", "transferencias masivas", "confirmación de pagos", "registro de movimientos"]
        return ["consultas de saldo", "transferencias", "pagos", "canales digitales"]

    @staticmethod
    def _summary(predicted_type: str, primary_cause: str, risk: float, confidence: float, has_incident: bool) -> str:
        if not has_incident:
            return (
                f"No hay incidente inminente según el umbral actual; riesgo {risk:.2f}. "
                f"El RCA preventivo vigila {primary_cause} como causa más probable si la señal empeora."
            )
        return (
            f"Se predice un incidente tipo {predicted_type} con riesgo {risk:.2f}. "
            f"La causa raíz más probable es {primary_cause} con confianza {confidence:.2%}."
        )

    @staticmethod
    def _impact_description(severity: str, operations: list[str], cause: str) -> str:
        ops = ", ".join(operations[:3])
        if severity in {"critical", "high"}:
            return (
                f"Impacto potencial alto sobre {ops}. La causa {cause} puede elevar latencia, "
                "generar timeouts y afectar experiencia de clientes en canales digitales."
            )
        if severity == "medium":
            return f"Riesgo moderado para {ops}; conviene investigar antes de que escale."
        return f"Riesgo bajo; mantener observación de {ops} y revisar tendencia de la ventana."

    def _evidence_signals(
        self,
        prediction: dict[str, Any],
        rca_result: dict[str, Any],
        metrics: dict[str, Any],
        slow_queries: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        signals: list[dict[str, str]] = []
        for cause in rca_result.get("top_causes", [])[:3]:
            signals.append(
                {
                    "signal": f"{cause['cause']} rank {cause['rank']} con confianza {cause['confidence']:.2%}",
                    "importance": "alta" if cause["rank"] == 1 else "media",
                }
            )
            for item in cause.get("evidence_features", [])[:2]:
                signals.append(
                    {
                        "signal": f"{item['feature']}={float(item.get('value', 0.0)):.2f}",
                        "importance": "alta" if item.get("importance", 0) else "media",
                    }
                )
        top_pred = prediction.get("top3_predictions", [])
        if top_pred:
            signals.append(
                {
                    "signal": f"Predicción principal: {top_pred[0].get('incident_type')} ({top_pred[0].get('probability', 0):.2%})",
                    "importance": "alta",
                }
            )
        if metrics.get("lock_waiting_sessions", 0):
            signals.append({"signal": f"lock_waiting_sessions={metrics['lock_waiting_sessions']}", "importance": "alta"})
        if slow_queries:
            signals.append({"signal": f"{len(slow_queries)} query fingerprints lentos en muestra reciente", "importance": "media"})
        return signals[:12]

    @staticmethod
    def _recommended_actions(cause: str, severity: str, diagnostic_sqls: list[dict[str, str]]) -> list[dict[str, Any]]:
        urgency = "immediate" if severity in {"critical", "high"} else "investigate_first"
        cause_actions = {
            "lock_wait_storm": [
                "Identificar bloqueadores y duración de transacciones.",
                "Revisar sesiones idle-in-transaction antes de terminar cualquier backend.",
                "Coordinar con aplicación antes de cancelar transacciones de negocio.",
            ],
            "deadlock": [
                "Revisar patrones de adquisición de locks y orden transaccional.",
                "Correlacionar deadlocks con query fingerprints recientes.",
                "Preparar ajuste de retry/backoff en aplicación si se confirma recurrencia.",
            ],
            "concurrent_commits": [
                "Revisar presión WAL y latencia de fsync.",
                "Identificar lotes o jobs que concentran commits.",
                "Evaluar batching o escalonamiento del workload de escritura.",
            ],
        }
        actions = cause_actions.get(cause, ["Investigar métricas activas y queries lentas."])
        output = []
        for idx, action in enumerate(actions, start=1):
            output.append(
                {
                    "order": idx,
                    "action": action,
                    "sql": diagnostic_sqls[min(idx - 1, len(diagnostic_sqls) - 1)]["sql"] if diagnostic_sqls else None,
                    "requires_approval": idx >= 2,
                    "urgency": urgency,
                }
            )
        return output

    def _normalize_llm_response(
        self,
        llm_body: dict[str, Any],
        fallback: dict[str, Any],
        diagnostic_sqls: list[dict[str, str]],
        tokens_used: int | None,
    ) -> dict[str, Any]:
        result = dict(fallback)
        for key in (
            "incident_summary",
            "impact_description",
            "severity_classification",
            "affected_operations",
            "top3_causes",
            "escalation_needed",
            "escalation_reason",
        ):
            value = llm_body.get(key)
            if value not in (None, "", []):
                result[key] = value

        result["evidence_signals"] = self._sanitize_evidence_signals(
            llm_body.get("evidence_signals") or result["evidence_signals"]
        )
        result["diagnostic_sqls"] = self._sanitize_diagnostic_sqls(
            llm_body.get("diagnostic_sqls") or diagnostic_sqls
        ) or diagnostic_sqls
        result["recommended_actions"] = self._sanitize_recommended_actions(
            llm_body.get("recommended_actions") or result["recommended_actions"],
            result["diagnostic_sqls"],
            result["severity_classification"],
        )
        result["generated_at"] = datetime.now(timezone.utc).isoformat()
        result["model_used"] = self.model
        result["tokens_used"] = tokens_used
        result["safety_mode"] = "recommend_approve_execute_audit"
        return result

    @staticmethod
    def _sanitize_evidence_signals(items: list[dict[str, Any]]) -> list[dict[str, str]]:
        output = []
        for item in items[:12]:
            if not isinstance(item, dict):
                continue
            signal = str(item.get("signal") or item.get("feature") or "").strip()
            if not signal:
                continue
            importance = str(item.get("importance") or "media").lower()
            if importance not in {"alta", "media", "baja"}:
                importance = "media"
            output.append({"signal": signal, "importance": importance})
        return output

    @staticmethod
    def _sanitize_diagnostic_sqls(items: list[dict[str, Any]]) -> list[dict[str, str]]:
        output = []
        for item in items:
            if not isinstance(item, dict):
                continue
            sql = str(item.get("sql") or "").strip()
            if not is_safe_diagnostic_sql(sql):
                continue
            output.append(
                {
                    "category": str(item.get("category") or "diagnostic"),
                    "title": str(item.get("title") or "Consulta diagnostica"),
                    "sql": sql,
                }
            )
        return output

    @staticmethod
    def _sanitize_recommended_actions(
        actions: list[dict[str, Any]],
        diagnostic_sqls: list[dict[str, str]],
        severity: str,
    ) -> list[dict[str, Any]]:
        urgency_default = "immediate" if severity in {"critical", "high"} else "investigate_first"
        valid_urgencies = {"immediate", "within_5min", "investigate_first"}
        output = []
        for idx, item in enumerate(actions[:6], start=1):
            if not isinstance(item, dict):
                continue
            action_text = str(item.get("action") or item.get("title") or "").strip()
            if not action_text:
                continue
            sql = item.get("sql")
            if sql and not is_safe_diagnostic_sql(sql):
                sql = None
            if not sql and diagnostic_sqls:
                sql = diagnostic_sqls[min(idx - 1, len(diagnostic_sqls) - 1)]["sql"]
            urgency = str(item.get("urgency") or urgency_default)
            if urgency not in valid_urgencies:
                urgency = urgency_default
            output.append(
                {
                    "order": int(item.get("order") or idx),
                    "action": action_text,
                    "sql": sql,
                    "requires_approval": bool(item.get("requires_approval", idx >= 2)),
                    "urgency": urgency,
                }
            )
        return output

    @staticmethod
    def _escalation_reason(severity: str, score: float, cause: str) -> str | None:
        if severity == "critical":
            return f"Riesgo crítico ({score:.2f}) con causa probable {cause}."
        if severity == "high":
            return f"Riesgo alto ({score:.2f}); requiere revisión DBA prioritaria."
        return None

    @staticmethod
    def _format_predictor_evidence(prediction: dict[str, Any]) -> str:
        items = prediction.get("top3_predictions", [])
        return "\n".join(
            f"- {item.get('incident_type')}: {item.get('probability', 0):.2%}" for item in items
        ) or "No disponible"

    @staticmethod
    def _format_rca(rca: dict[str, Any]) -> str:
        lines = []
        for cause in rca.get("top_causes", [])[:3]:
            features = ", ".join(
                f"{item.get('feature')}={float(item.get('value', 0)):.2f}"
                for item in cause.get("evidence_features", [])[:3]
            )
            lines.append(f"{cause.get('rank')}. {cause.get('cause')} ({cause.get('confidence', 0):.2%}): {features}")
        return "\n".join(lines) or "No disponible"

    @staticmethod
    def _format_metrics(metrics: dict[str, Any]) -> str:
        keys = [
            "active_sessions",
            "waiting_sessions",
            "lock_waiting_sessions",
            "idle_in_transaction",
            "cache_hit_ratio",
            "wal_bytes_delta",
            "rollback_ratio",
        ]
        return "\n".join(f"- {key}: {metrics.get(key, 'N/A')}" for key in keys)

    @staticmethod
    def _format_queries(queries: list[dict[str, Any]]) -> str:
        if not queries:
            return "No hay queries lentas reportadas."
        return "\n".join(
            f"- queryid={query.get('queryid')}: mean={float(query.get('mean_exec_time') or 0):.2f}ms, "
            f"calls={query.get('calls_delta')}, {str(query.get('query_fingerprint') or '')[:120]}"
            for query in queries[:5]
        )


# Backward-compatible alias for the typo present in the phase draft.
DBACopiloitService = DBACopilotService
