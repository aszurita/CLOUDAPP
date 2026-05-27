from __future__ import annotations

from fastapi import APIRouter

from app.schemas.app_factory import (
    AppFactoryGenerateRequest,
    AppFactoryGenerateResponse,
    AppFactoryPlanRequest,
    AppFactoryPlanResponse,
    AppFactoryStatusResponse,
)
from app.services.app_factory import AppFactoryService

router = APIRouter(prefix="/app-factory", tags=["AI Cloud App Factory"])


def _svc() -> AppFactoryService:
    return AppFactoryService()


@router.get("", response_model=AppFactoryStatusResponse)
def factory_status() -> AppFactoryStatusResponse:
    return _svc().status()


@router.post("/plan", response_model=AppFactoryPlanResponse)
def plan_app(payload: AppFactoryPlanRequest) -> AppFactoryPlanResponse:
    return _svc().plan(payload)


@router.post("/generate", response_model=AppFactoryGenerateResponse)
def generate_app(payload: AppFactoryGenerateRequest) -> AppFactoryGenerateResponse:
    return _svc().generate(payload)

