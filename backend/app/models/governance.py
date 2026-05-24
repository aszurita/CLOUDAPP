from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class QueryPolicy(Base):
    __tablename__ = "query_policies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(30), default="medium", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class QueryReview(Base):
    __tablename__ = "query_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    sql_text: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    decision: Mapped[str] = mapped_column(String(30), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(30), nullable=False)
    reasons_json: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    recommendations_json: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    ai_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggested_sql: Mapped[str | None] = mapped_column(Text, nullable=True)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    execution_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actor: Mapped[str] = mapped_column(String(120), default="demo-user", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class DbaTableProfile(Base):
    __tablename__ = "dba_table_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    schema_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    table_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    estimated_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    columns_json: Mapped[list[dict]] = mapped_column(JSON, nullable=False)
    sensitive_columns_json: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(30), default="low", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    recommendations: Mapped[list["DbaRecommendation"]] = relationship(back_populates="profile")


class DbaRecommendation(Base):
    __tablename__ = "dba_recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    profile_id: Mapped[int | None] = mapped_column(ForeignKey("dba_table_profiles.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    severity: Mapped[str] = mapped_column(String(30), default="medium", nullable=False)
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(30), default="operations", nullable=False)
    affected_tables_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    source: Mapped[str] = mapped_column(String(30), default="openai", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    profile: Mapped[DbaTableProfile | None] = relationship(back_populates="recommendations")


class DemoCustomer(Base):
    __tablename__ = "demo_customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    customer_code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    segment: Mapped[str] = mapped_column(String(40), nullable=False)
    email: Mapped[str] = mapped_column(String(160), nullable=False)
    account_type: Mapped[str] = mapped_column(String(40), nullable=False)
    risk_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    transactions: Mapped[list["DemoCustomerTransaction"]] = relationship(back_populates="customer")


class DemoCustomerTransaction(Base):
    __tablename__ = "demo_customer_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("demo_customers.id"), nullable=False, index=True)
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    transaction_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    channel: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    merchant_category: Mapped[str] = mapped_column(String(80), nullable=False)
    risk_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    customer: Mapped[DemoCustomer] = relationship(back_populates="transactions")
