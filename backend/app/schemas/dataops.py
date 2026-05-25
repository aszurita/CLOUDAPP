from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DataOpsRunRequest(BaseModel):
    actor: str = "demo-user"


class DataOpsPipelineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    pipeline_key: str | None = None
    pipeline_type: str | None = None
    description: str | None
    databricks_job_id: str | None
    config_json: dict[str, Any] = Field(default_factory=dict)
    status: str
    updated_at: datetime

    @field_validator("config_json", mode="before")
    @classmethod
    def _empty_config_when_missing(cls, value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}


class DataOpsPipelineRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    pipeline_id: int
    run_id: str
    databricks_run_id: str | None = None
    business_run_id: str | None = None
    status: str
    bronze_rows: int
    silver_rows: int
    gold_rows: int
    quality_score: float
    quarantine_rows: int
    duration_ms: int
    failed_rules_json: list[dict[str, Any]]
    generated_tables_json: list[str]
    metrics_json: list[dict[str, Any]] = Field(default_factory=list)
    events_json: list[dict[str, Any]] = Field(default_factory=list)
    databricks_run_url: str | None
    ai_summary: str | None
    started_at: datetime
    finished_at: datetime | None
    created_at: datetime

    @field_validator("metrics_json", "events_json", mode="before")
    @classmethod
    def _empty_list_when_missing(cls, value: Any) -> list[dict[str, Any]]:
        return value if isinstance(value, list) else []


class DataOpsCurrentResponse(BaseModel):
    pipeline: DataOpsPipelineRead
    latest_run: DataOpsPipelineRunRead | None


class DataOpsQualityCheckRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: str
    rule_code: str
    layer: str
    status: str
    failed_rows: int
    description: str
    created_at: datetime


class DataOpsGeneratedAssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: str
    layer: str
    asset_name: str
    row_count: int
    storage_path: str | None
    created_at: datetime


class DataOpsQuarantineEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: str
    rule_code: str
    reason: str
    source_file: str | None
    record_ref: str | None
    preview_json: dict[str, Any]
    created_at: datetime
