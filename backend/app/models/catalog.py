from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class CatalogAsset(Base):
    __tablename__ = "catalog_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    asset_urn: Mapped[str] = mapped_column(String(500), unique=True, nullable=False, index=True)
    asset_name: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(220), nullable=False)
    source_system: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    platform: Mapped[str] = mapped_column(String(80), nullable=False)
    database_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    schema_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    table_name: Mapped[str] = mapped_column(String(180), nullable=False)
    layer: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    domain: Mapped[str] = mapped_column(String(120), default="retail-risk", nullable=False)
    owner: Mapped[str] = mapped_column(String(160), default="data-platform-team", nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    documentation_status: Mapped[str] = mapped_column(String(40), default="missing", nullable=False)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    sensitivity_level: Mapped[str] = mapped_column(String(40), default="internal", nullable=False, index=True)
    external_url: Mapped[str | None] = mapped_column(String(700), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    columns: Mapped[list["CatalogColumn"]] = relationship(back_populates="asset", cascade="all, delete-orphan")
    documentation_versions: Mapped[list["CatalogDocumentationVersion"]] = relationship(
        back_populates="asset", cascade="all, delete-orphan"
    )


class CatalogColumn(Base):
    __tablename__ = "catalog_columns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("catalog_assets.id"), nullable=False, index=True)
    column_name: Mapped[str] = mapped_column(String(180), nullable=False)
    data_type: Mapped[str] = mapped_column(String(120), nullable=False)
    nullable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    classification: Mapped[str] = mapped_column(String(40), default="internal", nullable=False, index=True)
    is_sensitive: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sample_safe_value: Mapped[str | None] = mapped_column(String(180), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    asset: Mapped[CatalogAsset] = relationship(back_populates="columns")


class CatalogOwner(Base):
    __tablename__ = "catalog_owners"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    owner_key: Mapped[str] = mapped_column(String(160), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(180), nullable=False)
    email: Mapped[str | None] = mapped_column(String(180), nullable=True)
    domain: Mapped[str] = mapped_column(String(120), default="retail-risk", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class CatalogClassification(Base):
    __tablename__ = "catalog_classifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(80), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class CatalogLineageEdge(Base):
    __tablename__ = "catalog_lineage_edges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    source_asset_urn: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    target_asset_urn: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    lineage_type: Mapped[str] = mapped_column(String(80), default="transformation", nullable=False)
    transformation_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.9, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class CatalogDocumentationVersion(Base):
    __tablename__ = "catalog_documentation_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("catalog_assets.id"), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    generated_by: Mapped[str] = mapped_column(String(40), default="openai", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    asset: Mapped[CatalogAsset] = relationship(back_populates="documentation_versions")


class CatalogSyncRun(Base):
    __tablename__ = "catalog_sync_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    source: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    assets_seen: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    assets_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    assets_updated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
