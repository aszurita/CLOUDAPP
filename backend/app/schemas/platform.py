from datetime import datetime

from pydantic import BaseModel, ConfigDict


class EnvironmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    status: str
    region: str
    is_active: bool


class ServiceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    environment_id: int
    name: str
    service_type: str
    status: str
    version: str
    health_url: str | None
    cost_estimate_usd: int


class DeploymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    service_id: int
    commit_sha: str
    status: str
    deployed_by: str
    pipeline_url: str | None
    deployed_at: datetime


class PlatformStatus(BaseModel):
    app_name: str
    environment: str
    database: str
    services_total: int
    services_healthy: int
    environments_total: int
    latest_deployment_status: str | None
    audit_events_total: int
    ai_provider: str
    ai_configured: bool
    ai_model: str
