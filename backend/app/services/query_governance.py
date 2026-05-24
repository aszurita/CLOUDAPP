import re
from dataclasses import dataclass

import sqlparse


DANGEROUS_KEYWORDS = ("DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "TRUNCATE", "CREATE", "GRANT", "REVOKE")
INTERNAL_TABLES = ("audit_events", "platform_settings", "query_reviews", "query_policies", "alembic_version")
ALLOWED_QUERY_TABLES = ("demo_customers", "demo_customer_transactions")
SENSITIVE_TERMS = ("customer", "account", "email", "amount", "transaction", "risk", "phone", "document")


@dataclass(frozen=True)
class QueryGovernanceEvaluation:
    decision: str
    risk_level: str
    reasons: list[str]
    recommendations: list[str]
    suggested_sql: str | None = None

    def as_dict(self) -> dict:
        return {
            "decision": self.decision,
            "risk_level": self.risk_level,
            "reasons": self.reasons,
            "recommendations": self.recommendations,
            "suggested_sql": self.suggested_sql,
        }


class QueryGovernanceEngine:
    def evaluate(self, sql: str) -> QueryGovernanceEvaluation:
        normalized = sql.strip()
        reasons: list[str] = []
        recommendations: list[str] = []
        suggested_sql: str | None = None

        if not normalized:
            return QueryGovernanceEvaluation(
                decision="blocked",
                risk_level="blocked",
                reasons=["La consulta esta vacia."],
                recommendations=["Escribe una consulta SELECT sobre tablas demo."],
            )

        statements = [statement for statement in sqlparse.parse(normalized) if statement.value.strip().strip(";")]
        if len(statements) != 1:
            reasons.append("La consola bloquea multiples sentencias en una sola solicitud.")
            recommendations.append("Ejecuta una sola consulta SELECT por revision.")

        statement = statements[0] if statements else None
        statement_type = statement.get_type().upper() if statement is not None else "UNKNOWN"
        if statement_type != "SELECT":
            reasons.append("Solo se permiten consultas SELECT de solo lectura.")
            recommendations.append("Convierte la operacion en una consulta SELECT segura.")

        for keyword in DANGEROUS_KEYWORDS:
            if re.search(rf"\b{keyword}\b", normalized, flags=re.IGNORECASE):
                reasons.append(f"Comando peligroso detectado: {keyword}.")
                recommendations.append("Elimina operaciones DDL/DML; esta consola es solo lectura.")

        if re.search(r"^\s*select\s+\*", normalized, flags=re.IGNORECASE | re.DOTALL):
            reasons.append("SELECT * esta bloqueado por riesgo de extraccion masiva.")
            recommendations.append("Selecciona columnas explicitas y necesarias para la revision.")
            suggested_sql = (
                "SELECT customer_id, transaction_date, transaction_amount, channel, status "
                "FROM demo_customer_transactions "
                "WHERE transaction_date >= '2026-01-01' "
                "LIMIT 50;"
            )

        if not re.search(r"\blimit\s+\d+\b", normalized, flags=re.IGNORECASE):
            reasons.append("La consulta no incluye LIMIT.")
            recommendations.append("Agrega LIMIT 100 o menos para controlar la cantidad de filas.")

        referenced_internal = [table for table in INTERNAL_TABLES if re.search(rf"\b{table}\b", normalized, flags=re.IGNORECASE)]
        if referenced_internal:
            reasons.append("La consulta intenta acceder a tablas internas de plataforma.")
            recommendations.append("Usa solamente tablas demo permitidas para la consola SQL.")

        if not any(re.search(rf"\b{table}\b", normalized, flags=re.IGNORECASE) for table in ALLOWED_QUERY_TABLES):
            reasons.append("La consulta debe usar tablas demo permitidas.")
            recommendations.append("Usa demo_customers o demo_customer_transactions.")

        if reasons:
            return QueryGovernanceEvaluation(
                decision="blocked",
                risk_level="blocked",
                reasons=_dedupe(reasons),
                recommendations=_dedupe(recommendations),
                suggested_sql=suggested_sql,
            )

        risk_level = "medium" if any(term in normalized.lower() for term in SENSITIVE_TERMS) else "low"
        return QueryGovernanceEvaluation(
            decision="approved",
            risk_level=risk_level,
            reasons=["La consulta cumple las reglas de solo lectura y control de volumen."],
            recommendations=["Ejecuta la consulta y revisa si las columnas sensibles requieren mascara en fases futuras."],
        )


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))
