from fastapi import APIRouter

from app.api.sentinel.metrics import router as metrics_router

sentinel_router = APIRouter(prefix="/sentinel", tags=["db-sentinel-ai"])
sentinel_router.include_router(metrics_router)
