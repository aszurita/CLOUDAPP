from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class QueryAnalyzeRequest(BaseModel):
    sql: str
    actor: str = "demo-user"


class QueryEvaluation(BaseModel):
    decision: str
    risk_level: str
    reasons: list[str]
    recommendations: list[str]
    suggested_sql: str | None = None


class QueryAnalyzeResponse(QueryEvaluation):
    id: int
    ai_explanation: str
    created_at: datetime


class QueryExecuteRequest(BaseModel):
    sql: str
    actor: str = "demo-user"


class QueryExecuteResponse(QueryAnalyzeResponse):
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    execution_ms: int


class QueryReviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sql_text: str
    action: str
    decision: str
    risk_level: str
    reasons_json: list[str]
    recommendations_json: list[str]
    ai_explanation: str | None
    suggested_sql: str | None
    row_count: int | None
    execution_ms: int | None
    actor: str
    created_at: datetime


class QueryPolicyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    description: str
    severity: str
    enabled: bool


class DemoQueriesResponse(BaseModel):
    dangerous: str
    safe: str


class DbaAnalyzeResponse(BaseModel):
    profiles_count: int
    recommendations_count: int
    ai_summary: str


class DbaTableProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    schema_name: str
    table_name: str
    estimated_rows: int
    total_size_bytes: int
    columns_json: list[dict[str, Any]]
    sensitive_columns_json: list[str]
    risk_level: str
    created_at: datetime


class DbaRecommendationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    profile_id: int | None
    title: str
    severity: str
    recommendation: str
    category: str
    affected_tables_json: list[str]
    source: str
    created_at: datetime
