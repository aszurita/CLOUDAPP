from datetime import datetime
from typing import Any, Literal, Optional
from pydantic import BaseModel, ConfigDict


class LiveMetricsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    collected_at: Optional[datetime] = None
    engine: Optional[str] = None
    database_name: Optional[str] = None
    active_sessions: Optional[int] = None
    waiting_sessions: Optional[int] = None
    lock_waiting_sessions: Optional[int] = None
    idle_in_transaction: Optional[int] = None
    cache_hit_ratio: Optional[float] = None
    xact_commit_delta: Optional[int] = None
    xact_rollback_delta: Optional[int] = None
    deadlocks_delta: Optional[int] = None
    wal_bytes_delta: Optional[int] = None
    replication_lag_seconds: Optional[float] = None
    message: Optional[str] = None


class IncidentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    detected_at: datetime
    engine: Optional[str] = None
    database_name: Optional[str] = None
    incident_type: Optional[str] = None
    risk_score: Optional[float] = None
    impact_level: Optional[str] = None
    root_cause_top1: Optional[str] = None
    status: str
    resolved_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class IncidentDetailResponse(IncidentResponse):
    root_cause_top3: Optional[list] = None
    evidence: Optional[dict] = None
    llm_explanation: Optional[str] = None
    llm_recommended_actions: Optional[list] = None
    dba_action_taken: Optional[str] = None


class IncidentListResponse(BaseModel):
    incidents: list[IncidentResponse]
    total: int
    limit: int
    offset: int


class IncidentEvidenceResponse(BaseModel):
    incident_id: int
    incident_type: Optional[str] = None
    risk_score: Optional[float] = None
    root_cause_top1: Optional[str] = None
    root_cause_top3: Optional[list] = None
    llm_explanation: Optional[str] = None
    llm_recommended_actions: Optional[list] = None
    metrics_timeline: list[dict[str, Any]]
    slow_queries: list[dict[str, Any]]


class ResolveIncidentRequest(BaseModel):
    resolved_by: str = "dba"
    action_taken: str = ""


class PredictRequest(BaseModel):
    engine: str = "postgresql"
    database_name: str = "core_banking_sim"
    window_minutes: int = 10
    horizon_minutes: int = 10


class PredictResponse(BaseModel):
    risk_score: float
    has_predicted_incident: bool
    predicted_incident_type: str
    impact_level: str
    top3_predictions: list[dict]
    rca_top_causes: list[dict]
    primary_cause: str
    primary_evidence_summary: str
    current_metrics: dict[str, Any]
    horizon_minutes: int
    predicted_at: str
    model_version: str


class ExplainRequest(BaseModel):
    incident_id: Optional[int] = None
    use_current_metrics: bool = True
    engine: str = "postgresql"
    database_name: str = "core_banking_sim"
    window_minutes: int = 10
    horizon_minutes: int = 10
    use_llm: bool = False
    persist_incident: bool = False


class CopilotEvidenceItem(BaseModel):
    signal: str
    importance: str


class CopilotAction(BaseModel):
    order: int
    action: str
    sql: Optional[str] = None
    requires_approval: bool
    urgency: str


class CopilotResponse(BaseModel):
    incident_summary: str
    impact_description: str
    severity_classification: str
    affected_operations: list[str]
    top3_causes: list[dict[str, Any]]
    evidence_signals: list[CopilotEvidenceItem]
    recommended_actions: list[CopilotAction]
    diagnostic_sqls: list[dict[str, Any]]
    escalation_needed: bool
    escalation_reason: Optional[str] = None
    generated_at: str
    model_used: str
    tokens_used: Optional[int] = None
    safety_mode: str
    incident_id: Optional[int] = None


class SimulateFaultRequest(BaseModel):
    fault_type: Optional[
        Literal[
            "lock_wait_storm",
            "deadlock",
            "concurrent_commits",
            "missing_index",
            "heavy_workload",
            "vacuum_problem",
            "io_saturation",
            "replication_lag",
        ]
    ] = None
    duration_seconds: int = 60
    intensity: Literal["low", "medium", "high"] = "medium"
    dry_run: bool = True
    approved_by: Optional[str] = None


class FaultJobResponse(BaseModel):
    job_id: str
    fault_type: str
    status: str
    dry_run: bool
    duration_seconds: int
    intensity: str
    started_at: str
    finished_at: Optional[str] = None
    plan: list[str]
    command: Optional[str] = None
    processes: list[dict[str, Any]] = []
    logs: list[dict[str, Any]] = []
    error: Optional[str] = None
