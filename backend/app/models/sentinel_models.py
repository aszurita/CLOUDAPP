from datetime import datetime
from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.session import Base


class SentinelMetricSample(Base):
    __tablename__ = "sentinel_metric_samples"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    engine: Mapped[str] = mapped_column(String(20), default="postgresql")
    database_name: Mapped[str | None] = mapped_column(String(100))
    active_sessions: Mapped[int | None] = mapped_column(Integer)
    waiting_sessions: Mapped[int | None] = mapped_column(Integer)
    lock_waiting_sessions: Mapped[int | None] = mapped_column(Integer)
    idle_in_transaction: Mapped[int | None] = mapped_column(Integer)
    locks_granted: Mapped[int | None] = mapped_column(Integer)
    locks_waiting: Mapped[int | None] = mapped_column(Integer)
    long_transactions_count: Mapped[int | None] = mapped_column(Integer)
    xact_commit_delta: Mapped[int | None] = mapped_column(BigInteger)
    xact_rollback_delta: Mapped[int | None] = mapped_column(BigInteger)
    deadlocks_delta: Mapped[int | None] = mapped_column(Integer)
    cache_hit_ratio: Mapped[float | None] = mapped_column(Float)
    wal_bytes_delta: Mapped[int | None] = mapped_column(BigInteger)
    wal_buffers_full_delta: Mapped[int | None] = mapped_column(Integer)
    blk_read_time_delta: Mapped[float | None] = mapped_column(Float)
    temp_files_delta: Mapped[int | None] = mapped_column(Integer)
    temp_bytes_delta: Mapped[int | None] = mapped_column(BigInteger)
    replication_lag_seconds: Mapped[float | None] = mapped_column(Float)
    replica_count: Mapped[int | None] = mapped_column(Integer)
    raw_json: Mapped[dict | None] = mapped_column(JSON)


class SentinelQuerySample(Base):
    __tablename__ = "sentinel_query_samples"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    queryid: Mapped[int | None] = mapped_column(BigInteger)
    query_fingerprint: Mapped[str | None] = mapped_column(Text)
    calls_delta: Mapped[int | None] = mapped_column(BigInteger)
    mean_exec_time: Mapped[float | None] = mapped_column(Float)
    stddev_exec_time: Mapped[float | None] = mapped_column(Float)
    rows_delta: Mapped[int | None] = mapped_column(BigInteger)
    wal_bytes_delta: Mapped[int | None] = mapped_column(BigInteger)


class SentinelIncident(Base):
    __tablename__ = "sentinel_incidents"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    predicted_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    engine: Mapped[str | None] = mapped_column(String(20))
    database_name: Mapped[str | None] = mapped_column(String(100))
    incident_type: Mapped[str | None] = mapped_column(String(100))
    risk_score: Mapped[float | None] = mapped_column(Float)
    impact_level: Mapped[str | None] = mapped_column(String(20))
    root_cause_top1: Mapped[str | None] = mapped_column(String(100))
    root_cause_top3: Mapped[list | None] = mapped_column(JSON)
    evidence: Mapped[dict | None] = mapped_column(JSON)
    llm_explanation: Mapped[str | None] = mapped_column(Text)
    llm_recommended_actions: Mapped[list | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="open")
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dba_action_taken: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    audit_logs: Mapped[list["SentinelAuditLog"]] = relationship("SentinelAuditLog", back_populates="incident")


class SentinelAuditLog(Base):
    __tablename__ = "sentinel_audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    incident_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("sentinel_incidents.id", ondelete="SET NULL"))
    action_type: Mapped[str | None] = mapped_column(String(50))
    action_detail: Mapped[str | None] = mapped_column(Text)
    approved_by: Mapped[str | None] = mapped_column(String(100))
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    incident: Mapped["SentinelIncident | None"] = relationship("SentinelIncident", back_populates="audit_logs")


class SentinelPredictionResult(Base):
    __tablename__ = "sentinel_prediction_results"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    predicted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    risk_score: Mapped[float | None] = mapped_column(Float)
    predicted_incident_type: Mapped[str | None] = mapped_column(String(100))
    actual_incident_type: Mapped[str | None] = mapped_column(String(100))
    was_correct: Mapped[bool | None] = mapped_column(Boolean)
    model_version: Mapped[str | None] = mapped_column(String(50))
