from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class CloudOpsToolStatus(BaseModel):
    name: str
    available: bool
    detail: str


class CloudOpsArtifactStatus(BaseModel):
    key: str
    label: str
    path: str
    present: bool
    purpose: str


class CloudOpsGeneratedApp(BaseModel):
    id: str
    name: str
    slug: str
    path: str
    created_at: datetime | None
    updated_at: datetime | None
    status: Literal["ready", "partial", "blocked"]
    readiness_score: int
    artifacts: list[CloudOpsArtifactStatus]
    azure_links: list[str]
    github_url: str | None = None


class CloudOpsAzureResource(BaseModel):
    name: str
    resource_group: str
    type: str
    location: str | None = None
    status: str | None = None
    url: str | None = None


class CloudOpsAzureSnapshot(BaseModel):
    authenticated: bool
    subscription_name: str | None = None
    subscription_id: str | None = None
    tenant_id: str | None = None
    user: str | None = None
    resource_groups: list[CloudOpsAzureResource] = Field(default_factory=list)
    container_apps: list[CloudOpsAzureResource] = Field(default_factory=list)
    registries: list[CloudOpsAzureResource] = Field(default_factory=list)
    postgres_servers: list[CloudOpsAzureResource] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class CloudOpsPlanStep(BaseModel):
    name: str
    stage: Literal["validate", "provision", "build", "release", "observe", "govern"]
    status: Literal["ready", "manual", "warning", "blocked"]
    detail: str


class CloudOpsDeploymentPlan(BaseModel):
    app_id: str | None
    app_slug: str | None
    project_path: str | None
    mode: Literal["readiness", "cloudops-mvp"]
    summary: str
    readiness_score: int
    required_inputs: list[str]
    steps: list[CloudOpsPlanStep]
    matched_azure_resources: list[CloudOpsAzureResource]


class CloudOpsOverviewResponse(BaseModel):
    title: str
    mode: Literal["operations-console"]
    generated_root: str
    tools: list[CloudOpsToolStatus]
    apps: list[CloudOpsGeneratedApp]
    selected_app: CloudOpsGeneratedApp | None
    azure: CloudOpsAzureSnapshot
    plan: CloudOpsDeploymentPlan
