from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.app_factory import router as app_factory_router
from app.api.cloudops_autopilot import router as cloudops_autopilot_router
from app.api.core_banking_dashboard import router as core_banking_dashboard_router
from app.api.controltower import router as controltower_router
from app.api.dashboard_factory import router as dashboard_factory_router
from app.api.routes import router
from app.api.sentinel import sentinel_router
from app.api.sentinel.metrics import start_auto_collection, stop_auto_collection
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.telemetry import add_request_telemetry_middleware, configure_telemetry
from app.db.session import SessionLocal
from app.services.dashboard_factory import ensure_table

configure_logging()
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_table()
    await start_auto_collection()
    try:
        yield
    finally:
        await stop_auto_collection()


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
configure_telemetry(app, settings)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.frontend_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
add_request_telemetry_middleware(app)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"detail": "Unexpected platform error.", "path": str(request.url.path)},
    )


@app.get("/health")
def health() -> dict[str, str]:
    db_status = "connected"
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
    except Exception:
        db_status = "unavailable"

    return {
        "status": "healthy" if db_status == "connected" else "degraded",
        "database": db_status,
        "environment": settings.environment,
    }


app.include_router(router, prefix=settings.api_prefix)
app.include_router(sentinel_router, prefix=settings.api_prefix)
app.include_router(controltower_router, prefix=settings.api_prefix)
app.include_router(dashboard_factory_router, prefix=settings.api_prefix)
app.include_router(core_banking_dashboard_router, prefix=settings.api_prefix)
app.include_router(app_factory_router, prefix=settings.api_prefix)
app.include_router(cloudops_autopilot_router, prefix=settings.api_prefix)
