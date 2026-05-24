import json
from typing import Any

from openai import OpenAI

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
        response = client.responses.create(**params)
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
