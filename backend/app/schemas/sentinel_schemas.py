from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel


class LiveMetricsResponse(BaseModel):
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

    class Config:
        from_attributes = True


class IncidentResponse(BaseModel):
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

    class Config:
        from_attributes = True


class IncidentDetailResponse(IncidentResponse):
    root_cause_top3: Optional[list] = None
    evidence: Optional[dict] = None
    llm_explanation: Optional[str] = None
    llm_recommended_actions: Optional[list] = None
    dba_action_taken: Optional[str] = None


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
    window_minutes: int = 10


class SimulateFaultRequest(BaseModel):
    duration_seconds: int = 60
    intensity: str = "medium"
