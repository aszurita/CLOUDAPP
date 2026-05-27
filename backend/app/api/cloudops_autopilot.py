from __future__ import annotations

from fastapi import APIRouter, Query

from app.schemas.cloudops_autopilot import CloudOpsOverviewResponse
from app.services.cloudops_autopilot import CloudOpsAutopilotService

router = APIRouter(prefix="/cloudops-autopilot", tags=["CloudOps Autopilot Azure"])


def _svc() -> CloudOpsAutopilotService:
    return CloudOpsAutopilotService()


@router.get("", response_model=CloudOpsOverviewResponse)
def cloudops_overview(app_id: str | None = Query(default=None)) -> CloudOpsOverviewResponse:
    return _svc().overview(app_id=app_id)

