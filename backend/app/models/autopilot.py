from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class AutopilotReport(Base):
    __tablename__ = "autopilot_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    run_id: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), default="success", nullable=False, index=True)
    overall_score: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(30), default="medium", nullable=False, index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    metrics_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    findings_json: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    remediation_plan_json: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    infra_suggestions_json: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_context_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    tasks: Mapped[list["AutopilotTask"]] = relationship(
        back_populates="report",
        cascade="all, delete-orphan",
    )


class AutopilotTask(Base):
    __tablename__ = "autopilot_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("autopilot_reports.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(220), nullable=False)
    priority: Mapped[str] = mapped_column(String(30), default="medium", nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(60), default="operations", nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), default="open", nullable=False, index=True)
    owner: Mapped[str] = mapped_column(String(160), default="data-platform-team", nullable=False)
    source: Mapped[str] = mapped_column(String(120), default="autopilot", nullable=False)
    due_hint: Mapped[str | None] = mapped_column(String(120), nullable=True)
    action_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    report: Mapped[AutopilotReport] = relationship(back_populates="tasks")
