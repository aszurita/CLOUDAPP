from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# ── Dashboard Schema types (the JSON contract) ────────────────────────────────

class QueryDef(BaseModel):
    id: str
    purpose: str
    sql: str


class WidgetDef(BaseModel):
    id: str
    type: Literal["kpi", "bar_chart", "line_chart", "pie_chart", "table"]
    title: str
    query_id: str
    value_field: Optional[str] = None
    x_field: Optional[str] = None
    y_field: Optional[str] = None
    col_span: int = 1


class FilterDef(BaseModel):
    id: str
    label: str
    type: Literal["date", "select", "text"]
    default_value: Optional[str] = None


class DashboardSchema(BaseModel):
    title: str
    description: str
    catalog: str
    schema_name: str
    queries: list[QueryDef]
    widgets: list[WidgetDef]
    filters: list[FilterDef] = []


# ── API request / response ────────────────────────────────────────────────────

class PlanDashboardRequest(BaseModel):
    prompt: str
    catalog: str = "databricks_proyectobg"
    schema_name: str = "tpcds_gold"
    table: Optional[str] = None


class PlanDashboardResponse(BaseModel):
    dashboard_schema: DashboardSchema
    analysis_type: str
    detected_tables: list[str]


class GenerateDashboardRequest(BaseModel):
    prompt: str
    catalog: str = "databricks_proyectobg"
    schema_name: str = "tpcds_gold"
    dashboard_schema: DashboardSchema


class GenerateDashboardResponse(BaseModel):
    id: int
    name: str
    status: str
    message: str


class GoldFactoryRequest(BaseModel):
    prompt: str
    target_catalog: str = "databricks_proyectobg"
    target_schema: str = "tpcds_gold"
    object_type: Literal["TABLE", "VIEW"] = "TABLE"
    write_mode: Literal["OR_REPLACE", "IF_NOT_EXISTS"] = "OR_REPLACE"
    created_by: str = "web-user"


class GoldTablePlan(BaseModel):
    decision: str
    object_type: Literal["TABLE", "VIEW"]
    target_catalog: str
    target_schema: str
    target_name: str
    source_tables: list[str]
    source_sql: str
    generated_sql: str
    explanation: str
    validation_status: str
    validation_messages: list[str]
    dry_run_ok: bool = False
    confidence: float = 0.0


class GoldFactorySubmitRequest(BaseModel):
    prompt: str
    plan: GoldTablePlan
    write_mode: Literal["OR_REPLACE", "IF_NOT_EXISTS"] = "OR_REPLACE"
    created_by: str = "web-user"


class GoldFactorySubmitResponse(BaseModel):
    request_id: int
    status: str
    databricks_job_id: Optional[str] = None
    databricks_run_id: Optional[str] = None
    databricks_run_url: Optional[str] = None
    target_table: str
    message: str


class GoldFactoryRequestStatus(BaseModel):
    request_id: int
    status: str
    target_table: str
    object_type: str
    write_mode: str
    prompt: Optional[str] = None
    created_by: Optional[str] = None
    source_tables: list[str] = Field(default_factory=list)
    validation_status: Optional[str] = None
    validation_messages: list[str] = Field(default_factory=list)
    databricks_job_id: Optional[str] = None
    databricks_run_id: Optional[str] = None
    databricks_run_url: Optional[str] = None
    row_count: Optional[int] = None
    error_message: Optional[str] = None
    sync_error: Optional[str] = None
    generated_sql: Optional[str] = None
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None


class WidgetData(BaseModel):
    widget_id: str
    query_id: str
    columns: list[str]
    rows: list[list[Any]]
    error: Optional[str] = None


class ExecuteDashboardResponse(BaseModel):
    dashboard_id: int
    results: list[WidgetData]
    execution_time_ms: int
    demo_mode: bool = False


class UpdateDashboardRequest(BaseModel):
    name: Optional[str] = None
    dashboard_schema: Optional[DashboardSchema] = None


class DashboardRecord(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    prompt_original: str
    catalog_name: str
    schema_name: str
    dashboard_schema: dict
    status: str
    version: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DashboardListResponse(BaseModel):
    total: int
    dashboards: list[DashboardRecord]


# ── Catalog discovery ─────────────────────────────────────────────────────────

class CatalogItem(BaseModel):
    name: str


class SchemaItem(BaseModel):
    name: str
    catalog_name: str


class TableItem(BaseModel):
    name: str
    schema_name: str
    catalog_name: str
    table_type: str = "TABLE"


# ── Status ────────────────────────────────────────────────────────────────────

class FactoryStatusResponse(BaseModel):
    title: str
    databricks_configured: bool
    warehouse_id: Optional[str] = None
    catalog: str
    total_dashboards: int
