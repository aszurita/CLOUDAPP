from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class DashboardGenerationHistory(Base):
    """Legacy table — kept for backward compat with migration 0009."""

    __tablename__ = "dashboard_generation_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    catalog_name: Mapped[str] = mapped_column(String(120), nullable=False)
    schema_name: Mapped[str] = mapped_column(String(120), nullable=False)
    table_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    sql_generated: Mapped[str | None] = mapped_column(Text, nullable=True)
    dashboard_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    dashboard_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    databricks_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    embed_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="created", nullable=False)
    chart_types: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )


class Dashboard(Base):
    """Schema-driven dashboard — renders entirely in React from a JSON schema.
    Databricks is used only as a data source (SQL execution via SQL Warehouse).
    """

    __tablename__ = "dashboards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_original: Mapped[str] = mapped_column(Text, nullable=False)
    catalog_name: Mapped[str] = mapped_column(String(120), nullable=False)
    schema_name: Mapped[str] = mapped_column(String(120), nullable=False)
    dashboard_schema: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), default="active", nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )


class GoldFactoryRequestRecord(Base):
    """Local audit trail for AI Gold Factory materialization jobs."""

    __tablename__ = "gold_factory_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    request_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    user_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    target_catalog: Mapped[str] = mapped_column(String(120), nullable=False)
    target_schema: Mapped[str] = mapped_column(String(120), nullable=False)
    target_name: Mapped[str] = mapped_column(String(160), nullable=False)
    object_type: Mapped[str] = mapped_column(String(20), nullable=False)
    write_mode: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="PENDING", nullable=False, index=True)
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)
    source_tables_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    validation_messages_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    raw_plan_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    source_sql: Mapped[str] = mapped_column(Text, nullable=False)
    generated_sql: Mapped[str] = mapped_column(Text, nullable=False)
    validation_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    ai_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[str | None] = mapped_column(String(20), nullable=True)
    databricks_job_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    databricks_run_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    databricks_run_url: Mapped[str | None] = mapped_column(String(600), nullable=True)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
