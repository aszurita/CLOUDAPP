from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


SourceStatus = Literal["online", "degraded", "offline", "pending"]


class ControlTowerEndpoint(BaseModel):
    method: str
    path: str
    description: str


class ControlTowerIndexResponse(BaseModel):
    title: str
    summary: str
    endpoints: list[ControlTowerEndpoint]


class ControlTowerMetricSnapshot(BaseModel):
    status: SourceStatus
    latency_ms: float | None = None
    active_connections: int | None = None
    total_connections: int | None = None
    idle_connections: int | None = None
    database_size_bytes: int | None = None
    tables_count: int | None = None
    locks_count: int | None = None
    cache_hit_ratio: float | None = None
    xact_commit: int | None = None
    xact_rollback: int | None = None
    deadlocks: int | None = None
    health_score: int
    captured_at: str
    error: str | None = None


class ControlTowerDatabase(BaseModel):
    source_id: str
    database_name: str
    owner: str | None = None
    encoding: str | None = None
    is_template: bool
    allow_connections: bool
    size_bytes: int | None = None
    active_connections: int
    total_connections: int
    is_current: bool
    is_system: bool


class ControlTowerSource(BaseModel):
    id: str
    name: str
    source_type: str
    engine: str
    environment: str
    host: str | None = None
    port: int | None = None
    database_name: str | None = None
    username: str | None = None
    secret_ref: str | None = None
    docker_container_name: str | None = None
    cloud_provider: str
    telemetry_provider: str
    badges: list[str]
    status: SourceStatus
    connection_configured: bool
    metric_snapshot: ControlTowerMetricSnapshot | None = None
    databases_count: int = 0
    databases: list[ControlTowerDatabase] = Field(default_factory=list)
    message: str | None = None


class ControlTowerOverview(BaseModel):
    title: str
    environment: str
    health_global: int
    sources_total: int
    online_sources: int
    local_docker_dbs: int
    cloud_dbs: int
    lakehouses: int
    active_alerts: int
    sources: list[ControlTowerSource]


class ControlTowerTable(BaseModel):
    source_id: str
    schema_name: str
    table_name: str
    estimated_rows: int | None = None
    size_bytes: int | None = None
    table_type: str = "table"
    last_seen_at: str


class ControlTowerSession(BaseModel):
    model_config = ConfigDict(extra="allow")

    pid: int | None = None
    username: str | None = None
    state: str | None = None
    wait_event_type: str | None = None
    wait_event: str | None = None
    query_start: str | None = None
    query: str | None = None


class ControlTowerLock(BaseModel):
    locktype: str | None = None
    relation_name: str | None = None
    mode: str | None = None
    granted: bool | None = None
    lock_count: int


class ControlTowerIntegration(BaseModel):
    id: str
    name: str
    provider: str
    status: Literal["connected", "configured", "pending", "unavailable"]
    signal: str
    description: str
    required_settings: list[str] = []


class ControlTowerRecommendation(BaseModel):
    id: str
    source_id: str
    severity: Literal["critical", "high", "medium", "low"]
    category: str
    title: str
    recommendation: str
    evidence: str
    impact: str
    action_type: Literal["read_only", "approval_required", "configuration"]


class ControlTowerHealthSummary(BaseModel):
    health_global: int
    by_status: dict[str, int]
    by_provider: dict[str, int]
    recommendations: list[ControlTowerRecommendation]


class DatabricksCatalogResponse(BaseModel):
    configured: bool
    host_configured: bool
    token_configured: bool
    warehouse_configured: bool
    catalog: str | None = None
    schemas: list[str]
    tables: list[dict[str, Any]]
    message: str | None = None
