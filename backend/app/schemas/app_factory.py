from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class AppFactoryCapability(BaseModel):
    name: str
    available: bool
    detail: str


class AppFactoryStatusResponse(BaseModel):
    title: str
    mode: Literal["local-generator", "cloud-ready"]
    generated_root: str
    supported_frontends: list[str]
    supported_backends: list[str]
    supported_databases: list[str]
    supported_clouds: list[str]
    capabilities: list[AppFactoryCapability]


class AppFactoryField(BaseModel):
    name: str
    label: str
    type: Literal["text", "email", "number", "currency", "date", "status"]
    required: bool = True


class AppFactoryEntity(BaseModel):
    name: str
    route: str
    display_name: str
    fields: list[AppFactoryField]


class AppFactoryResource(BaseModel):
    name: str
    type: str
    purpose: str
    provisioner: str


class AppFactoryStep(BaseModel):
    name: str
    status: Literal["pending", "running", "success", "blocked", "skipped"]
    detail: str


class AppFactoryPlanRequest(BaseModel):
    prompt: str = Field(min_length=4)
    project_name: str | None = None
    frontend: Literal["React + Vite"] = "React + Vite"
    backend: Literal["FastAPI"] = "FastAPI"
    database: Literal["PostgreSQL"] = "PostgreSQL"
    auth: Literal["JWT demo", "Sin auth"] = "JWT demo"
    cloud: Literal["Azure Container Apps"] = "Azure Container Apps"


class AppFactoryPlanResponse(BaseModel):
    project_name: str
    slug: str
    summary: str
    frontend: str
    backend: str
    database: str
    auth: str
    cloud: str
    entities: list[AppFactoryEntity]
    resources: list[AppFactoryResource]
    steps: list[AppFactoryStep]
    files_preview: list[str]
    estimated_cost_tier: str
    guardrails: list[str]


class AppFactoryGenerateRequest(AppFactoryPlanRequest):
    initialize_git: bool = True
    publish_github: bool = False
    deploy_azure: bool = False
    github_private: bool = True
    github_token: str | None = Field(default=None, repr=False)


class AppFactoryLink(BaseModel):
    label: str
    url: str
    kind: Literal["local", "file", "command", "cloud-template", "github-template", "github", "azure"]


class AppFactoryArtifact(BaseModel):
    label: str
    path: str
    kind: Literal["project", "backend", "frontend", "terraform", "workflow", "documentation"]


class AppFactoryGenerateResponse(BaseModel):
    job_id: str
    status: Literal["success", "partial", "blocked"]
    message: str
    project_name: str
    slug: str
    project_path: str
    generated_at: datetime
    links: list[AppFactoryLink]
    artifacts: list[AppFactoryArtifact]
    steps: list[AppFactoryStep]
    commands: list[str]
    plan: AppFactoryPlanResponse
