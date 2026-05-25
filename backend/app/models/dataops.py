from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class DataOpsPipeline(Base):
    __tablename__ = "dataops_pipelines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    databricks_job_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="idle", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    runs: Mapped[list["DataOpsPipelineRun"]] = relationship(back_populates="pipeline")


class DataOpsPipelineRun(Base):
    __tablename__ = "dataops_pipeline_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    pipeline_id: Mapped[int] = mapped_column(ForeignKey("dataops_pipelines.id"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    bronze_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    silver_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    gold_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    quality_score: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    quarantine_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_rules_json: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    generated_tables_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    databricks_run_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_summary_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    pipeline: Mapped[DataOpsPipeline] = relationship(back_populates="runs")
    quality_checks: Mapped[list["DataOpsQualityCheck"]] = relationship(back_populates="run")
    generated_assets: Mapped[list["DataOpsGeneratedAsset"]] = relationship(back_populates="run")
    quarantine_events: Mapped[list["DataOpsQuarantineEvent"]] = relationship(back_populates="run")


class DataOpsQualityCheck(Base):
    __tablename__ = "dataops_quality_checks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("dataops_pipeline_runs.run_id"), nullable=False, index=True)
    rule_code: Mapped[str] = mapped_column(String(120), nullable=False)
    layer: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    failed_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    run: Mapped[DataOpsPipelineRun] = relationship(back_populates="quality_checks")


class DataOpsGeneratedAsset(Base):
    __tablename__ = "dataops_generated_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("dataops_pipeline_runs.run_id"), nullable=False, index=True)
    layer: Mapped[str] = mapped_column(String(30), nullable=False)
    asset_name: Mapped[str] = mapped_column(String(180), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    storage_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    run: Mapped[DataOpsPipelineRun] = relationship(back_populates="generated_assets")


class DataOpsQuarantineEvent(Base):
    __tablename__ = "dataops_quarantine_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("dataops_pipeline_runs.run_id"), nullable=False, index=True)
    rule_code: Mapped[str] = mapped_column(String(120), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    source_file: Mapped[str | None] = mapped_column(String(260), nullable=True)
    record_ref: Mapped[str | None] = mapped_column(String(160), nullable=True)
    preview_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    run: Mapped[DataOpsPipelineRun] = relationship(back_populates="quarantine_events")
