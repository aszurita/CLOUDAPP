from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AutopilotRunRequest(BaseModel):
    actor: str = "demo-user"
    include_ai: bool = True


class AutopilotTaskStatusUpdateRequest(BaseModel):
    status: str = Field(pattern="^(open|in_progress|blocked|done|dismissed)$")
    actor: str = "demo-user"


class AutopilotTaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    report_id: int
    title: str
    priority: str
    category: str
    status: str
    owner: str
    source: str
    due_hint: str | None
    action_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    @field_validator("action_json", mode="before")
    @classmethod
    def _empty_action_when_missing(cls, value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}


class AutopilotReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: str
    status: str
    overall_score: float
    risk_level: str
    summary: str
    metrics_json: dict[str, Any] = Field(default_factory=dict)
    findings_json: list[dict[str, Any]] = Field(default_factory=list)
    remediation_plan_json: list[dict[str, Any]] = Field(default_factory=list)
    infra_suggestions_json: list[dict[str, Any]] = Field(default_factory=list)
    ai_summary: str | None
    raw_context_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    tasks: list[AutopilotTaskRead] = Field(default_factory=list)

    @field_validator("metrics_json", "raw_context_json", mode="before")
    @classmethod
    def _empty_dict_when_missing(cls, value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    @field_validator("findings_json", "remediation_plan_json", "infra_suggestions_json", mode="before")
    @classmethod
    def _empty_list_when_missing(cls, value: Any) -> list[dict[str, Any]]:
        return value if isinstance(value, list) else []


class AutopilotCurrentResponse(BaseModel):
    latest_report: AutopilotReportRead | None
