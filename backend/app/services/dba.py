import json
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.models import DbaRecommendation, DbaTableProfile


SENSITIVE_COLUMN_TERMS = ("customer", "account", "email", "amount", "transaction", "risk", "phone", "document")


class DbaCopilotService:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def collect_profiles(self) -> list[dict[str, Any]]:
        inspector = inspect(self.engine)
        profiles: list[dict[str, Any]] = []
        default_schema = "public" if self.engine.dialect.name == "postgresql" else None
        table_names = inspector.get_table_names(schema=default_schema)

        for table_name in table_names:
            if table_name == "alembic_version":
                continue
            schema_name = default_schema or "main"
            columns = [
                {
                    "name": column["name"],
                    "type": str(column["type"]),
                    "nullable": bool(column.get("nullable", True)),
                }
                for column in inspector.get_columns(table_name, schema=default_schema)
            ]
            sensitive_columns = [
                column["name"]
                for column in columns
                if any(term in column["name"].lower() for term in SENSITIVE_COLUMN_TERMS)
            ]
            estimated_rows = self._count_rows(schema_name, table_name)
            total_size = self._table_size_bytes(schema_name, table_name)
            risk_level = "high" if len(sensitive_columns) >= 3 else "medium" if sensitive_columns else "low"
            profiles.append(
                {
                    "schema_name": schema_name,
                    "table_name": table_name,
                    "estimated_rows": estimated_rows,
                    "total_size_bytes": total_size,
                    "columns": columns,
                    "sensitive_columns": sensitive_columns,
                    "risk_level": risk_level,
                }
            )

        return profiles

    def refresh_profiles(self, db: Session, ai_summary: str) -> tuple[list[DbaTableProfile], list[DbaRecommendation]]:
        profiles = self.collect_profiles()
        db.query(DbaRecommendation).delete()
        db.query(DbaTableProfile).delete()
        db.flush()

        profile_models: list[DbaTableProfile] = []
        for profile in profiles:
            model = DbaTableProfile(
                schema_name=profile["schema_name"],
                table_name=profile["table_name"],
                estimated_rows=profile["estimated_rows"],
                total_size_bytes=profile["total_size_bytes"],
                columns_json=profile["columns"],
                sensitive_columns_json=profile["sensitive_columns"],
                risk_level=profile["risk_level"],
            )
            db.add(model)
            profile_models.append(model)
        db.flush()

        recommendations: list[DbaRecommendation] = []

        findings = _parse_ai_findings(ai_summary)
        for finding in findings:
            rec_payload = {
                "description": finding.get("description", ""),
                "actions": finding.get("actions", []),
            }
            recommendations.append(
                DbaRecommendation(
                    title=finding.get("title", "Hallazgo DBA"),
                    severity=finding.get("severity", "medium"),
                    recommendation=json.dumps(rec_payload, ensure_ascii=False),
                    category=finding.get("category", "operations"),
                    affected_tables_json=finding.get("affected_tables", []),
                    source="openai",
                )
            )

        if not findings:
            for model in profile_models:
                if model.sensitive_columns_json:
                    rec_payload = {
                        "description": (
                            f"Columnas detectadas: {', '.join(model.sensitive_columns_json)}. "
                            "Clasifica y evalúa mascaramiento antes de exponerlos."
                        ),
                        "actions": [
                            f"Revisar el acceso a las columnas: {', '.join(model.sensitive_columns_json)}.",
                            "Evalúa mascaramiento o cifrado a nivel de columna.",
                            "Restringe permisos de lectura con RBAC o vistas filtradas.",
                        ],
                    }
                    recommendations.append(
                        DbaRecommendation(
                            profile_id=model.id,
                            title=f"Clasificar columnas sensibles en {model.table_name}",
                            severity="high" if model.risk_level == "high" else "medium",
                            recommendation=json.dumps(rec_payload, ensure_ascii=False),
                            category="security",
                            affected_tables_json=[model.table_name],
                            source="system",
                        )
                    )

        db.add_all(recommendations)
        db.commit()
        return profile_models, recommendations

    def _count_rows(self, schema_name: str, table_name: str) -> int:
        if not _safe_identifier(schema_name) or not _safe_identifier(table_name):
            return 0
        qualified = f'"{table_name}"' if self.engine.dialect.name != "postgresql" else f'"{schema_name}"."{table_name}"'
        try:
            with self.engine.connect() as connection:
                return int(connection.execute(text(f"SELECT COUNT(*) FROM {qualified}")).scalar_one())
        except Exception:
            return 0

    def _table_size_bytes(self, schema_name: str, table_name: str) -> int:
        if self.engine.dialect.name != "postgresql":
            return 0
        try:
            with self.engine.connect() as connection:
                value = connection.execute(
                    text("SELECT pg_total_relation_size(:relation_name)"),
                    {"relation_name": f"{schema_name}.{table_name}"},
                ).scalar_one_or_none()
                return int(value or 0)
        except Exception:
            return 0


def _safe_identifier(identifier: str) -> bool:
    return identifier.replace("_", "").isalnum()


def _parse_ai_findings(ai_response: str) -> list[dict]:
    text = ai_response.strip()
    # Strip markdown code fences if model adds them
    if "```" in text:
        for part in text.split("```"):
            part = part.strip().lstrip("json").strip()
            try:
                data = json.loads(part)
                if isinstance(data, dict) and "findings" in data:
                    return data["findings"]
            except (json.JSONDecodeError, ValueError):
                continue
    try:
        data = json.loads(text)
        return data.get("findings", [])
    except (json.JSONDecodeError, ValueError, AttributeError):
        return []
