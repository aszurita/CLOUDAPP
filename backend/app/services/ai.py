import json
from typing import Any

from openai import AuthenticationError, BadRequestError, OpenAI, OpenAIError

from app.core.config import get_settings


class AIConfigurationError(RuntimeError):
    pass


class AIRecommendationService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def _client(self) -> OpenAI:
        if self.settings.ai_provider != "openai" or not self.settings.openai_api_key:
            raise AIConfigurationError("OpenAI is required for phase 2. Configure OPENAI_API_KEY.")
        return OpenAI(api_key=self.settings.openai_api_key)

    def _supports_temperature(self) -> bool:
        # Reasoning models (o1, o3, o4-*) reject temperature; standard chat models support it
        model = self.settings.openai_model.lower()
        return not (model.startswith("o1") or model.startswith("o3") or model.startswith("o4"))

    def _complete(self, system_prompt: str, payload: dict[str, Any]) -> str:
        client = self._client()
        params: dict[str, Any] = {
            "model": self.settings.openai_model,
            "input": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            "max_output_tokens": self.settings.openai_max_output_tokens,
        }
        if self._supports_temperature():
            params["temperature"] = self.settings.openai_temperature
        try:
            response = client.responses.create(**params)
        except BadRequestError as exc:
            if "temperature" not in str(exc):
                raise
            params.pop("temperature", None)
            response = client.responses.create(**params)
        except AuthenticationError as exc:
            raise AIConfigurationError(
                "OpenAI rejected OPENAI_API_KEY. Create a new key and update CLOUDAPP/backend/.env."
            ) from exc
        except OpenAIError as exc:
            raise AIConfigurationError(f"OpenAI request failed. Check OPENAI_API_KEY in CLOUDAPP/backend/.env. Detail: {exc}") from exc
        text = getattr(response, "output_text", None)
        if text:
            return text.strip()
        return str(response).strip()

    def generate_query_guidance(self, sql: str, evaluation: dict[str, Any]) -> str:
        system_prompt = (
            "You are the DBA copilot for a demo cloud data platform. Explain SQL governance results in Spanish. "
            "Do not approve execution. Do not request secrets. Use concise operational language."
        )
        return self._complete(
            system_prompt,
            {
                "sql": sql,
                "evaluation": evaluation,
                "instruction": "Explain why the query is approved or blocked and suggest a safer SQL pattern if needed.",
            },
        )

    def generate_dba_recommendations(self, profiles: list[dict[str, Any]]) -> str:
        system_prompt = (
            "Eres un DBA copilot para PostgreSQL. Analiza los perfiles de tablas y genera hallazgos estructurados. "
            "Responde EXCLUSIVAMENTE con un objeto JSON válido, sin texto adicional, sin markdown, sin código fences. "
            'Formato exacto: {"findings": [{"category": "security|performance|architecture|operations", '
            '"title": "string", "description": "string", '
            '"severity": "critical|high|medium|low|info", '
            '"affected_tables": ["tabla1"], '
            '"actions": ["Acción concreta 1.", "Acción concreta 2."]}]}. '
            "Genera entre 5 y 10 hallazgos. Cada hallazgo debe tener 2-4 acciones concretas. "
            "Escribe en español. No inventes datos privados. Basa todo en el metadata recibido."
        )
        return self._complete(
            system_prompt,
            {
                "table_profiles": profiles,
                "instruction": "Analiza los perfiles y devuelve el JSON con los hallazgos más importantes.",
            },
        )

    def generate_dataops_failure_summary(self, run_summary: dict[str, Any]) -> str:
        system_prompt = (
            "Eres un copiloto DataOps. Resume fallas de calidad de un pipeline Bronze/Silver/Gold en español. "
            "No solicites secretos ni datos crudos. Usa solo la metadata agregada recibida y propone acciones operativas."
        )
        return self._complete(
            system_prompt,
            {
                "run_summary": run_summary,
                "instruction": "Explica el estado, reglas fallidas, impacto en quarantine y acciones siguientes.",
            },
        )

    def generate_gold_table_plan(self, request_context: dict[str, Any]) -> str:
        system_prompt = (
            "Eres un arquitecto DataOps para Databricks Lakehouse. Convierte una necesidad de negocio "
            "en una propuesta segura para crear o reutilizar una tabla/vista Gold. Responde solo JSON valido, "
            "sin markdown. Usa exclusivamente las tablas y columnas del catalogo recibido. "
            "El campo source_sql debe ser un SELECT de Databricks SQL, nunca CREATE/INSERT/UPDATE/DELETE/DROP/ALTER. "
            "Formato exacto: {\"decision\":\"CREATE_NEW_TABLE|CREATE_NEW_VIEW|REUSE_EXISTING\","
            "\"object_type\":\"TABLE|VIEW\",\"target_catalog\":\"string\",\"target_schema\":\"string\","
            "\"target_name\":\"snake_case\",\"source_tables\":[\"catalog.schema.table\"],"
            "\"source_sql\":\"SELECT ...\",\"explanation\":\"string\",\"confidence\":0.0}."
        )
        return self._complete(
            system_prompt,
            {
                "request_context": request_context,
                "instruction": (
                    "Analiza el prompt, prefiere fuentes Silver para crear Gold de reporting, "
                    "reutiliza Gold si ya resuelve la solicitud y genera un SELECT validable."
                ),
            },
        )

    def generate_catalog_documentation(self, asset_metadata: dict[str, Any]) -> str:
        system_prompt = (
            "Eres un data governance copilot. Documenta activos de datos en español usando solo metadata técnica. "
            "No inventes datos privados, no solicites secretos y no pidas muestras crudas. "
            "Devuelve secciones breves: propósito, uso recomendado, columnas clave, sensibilidad, riesgos y preguntas pendientes."
        )
        return self._complete(
            system_prompt,
            {
                "asset_metadata": asset_metadata,
                "instruction": "Genera documentación operativa para catálogo de datos sin incluir datos crudos.",
            },
        )

    def generate_autopilot_summary(self, report_context: dict[str, Any]) -> str:
        system_prompt = (
            "Eres un copiloto ejecutivo de CloudOps, DBA, DataOps y gobierno de datos. "
            "Resume hallazgos con lenguaje operativo en español, sin secretos, sin datos crudos y sin exagerar. "
            "Devuelve: estado general, riesgos prioritarios, plan de 3 pasos y criterio de cierre."
        )
        return self._complete(
            system_prompt,
            {
                "report_context": report_context,
                "instruction": "Genera un resumen ejecutivo accionable para el reporte Autopilot.",
            },
        )
