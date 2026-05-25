from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class DataOpsRunRequest(BaseModel):
    actor: str = "demo-user"


class DataOpsPipelineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    databricks_job_id: str | None
    status: str
    updated_at: datetime


class DataOpsPipelineRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    pipeline_id: int
    run_id: str
    status: str
    bronze_rows: int
    silver_rows: int
    gold_rows: int
    quality_score: float
    quarantine_rows: int
    duration_ms: int
    failed_rules_json: list[dict[str, Any]]
    generated_tables_json: list[str]
    databricks_run_url: str | None
    ai_summary: str | None
    started_at: datetime
    finished_at: datetime | None
    created_at: datetime


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
