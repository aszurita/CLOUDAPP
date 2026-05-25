from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CatalogSyncRequest(BaseModel):
    actor: str = "demo-user"


class CatalogStatusResponse(BaseModel):
    provider: str
    external_catalog: str
    datahub_configured: bool
    purview_configured: bool
    assets_total: int
    documented_assets: int
    sensitive_columns: int
    lineage_edges: int
    latest_sync_status: str | None


class CatalogAssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_urn: str
    asset_name: str
    display_name: str
    source_system: str
    platform: str
    database_name: str | None
    schema_name: str | None
    table_name: str
    layer: str
    domain: str
    owner: str
    description: str | None
    documentation_status: str
    quality_score: float | None
    sensitivity_level: str
    external_url: str | None
    last_synced_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CatalogColumnRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_id: int
    column_name: str
    data_type: str
    nullable: bool
    description: str | None
    classification: str
    is_sensitive: bool
    sample_safe_value: str | None
    created_at: datetime


class CatalogClassificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    label: str
    rank: int
    description: str
    created_at: datetime


class CatalogLineageEdgeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_asset_urn: str
    target_asset_urn: str
    lineage_type: str
    transformation_name: str | None
    confidence: float
    created_at: datetime


class CatalogSyncRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    status: str
    assets_seen: int
    assets_created: int
    assets_updated: int
    started_at: datetime
    finished_at: datetime | None
    error_message: str | None


class CatalogDocumentResponse(BaseModel):
    asset: CatalogAssetRead
    documentation: str


class CatalogOwnerUpdateRequest(BaseModel):
    owner: str
    actor: str = "demo-user"


class CatalogClassificationUpdateRequest(BaseModel):
    classification: str
    actor: str = "demo-user"


class CatalogColumnDescriptionUpdateRequest(BaseModel):
    description: str
    actor: str = "demo-user"
