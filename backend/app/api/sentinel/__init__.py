from fastapi import APIRouter

from app.api.sentinel.engines import router as engines_router
from app.api.sentinel.evaluate import router as evaluate_router
from app.api.sentinel.explain import router as explain_router
from app.api.sentinel.incidents import router as incidents_router
from app.api.sentinel.metrics import router as metrics_router
from app.api.sentinel.predict import router as predict_router
from app.api.sentinel.simulate import router as simulate_router

sentinel_router = APIRouter(prefix="/sentinel", tags=["db-sentinel-ai"])
sentinel_router.include_router(engines_router)
sentinel_router.include_router(evaluate_router)
sentinel_router.include_router(metrics_router)
sentinel_router.include_router(predict_router)
sentinel_router.include_router(explain_router)
sentinel_router.include_router(incidents_router)
sentinel_router.include_router(simulate_router)
