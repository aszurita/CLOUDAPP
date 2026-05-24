from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models import AuditEvent, Deployment, Environment, Service
from app.schemas.platform import DeploymentRead, EnvironmentRead, PlatformStatus, ServiceRead
from app.services.audit import record_audit_event

router = APIRouter()


@router.get("/platform/status", response_model=PlatformStatus)
def platform_status(db: Session = Depends(get_db)) -> PlatformStatus:
    settings = get_settings()
    db.execute(text("SELECT 1"))
    latest_deployment = db.query(Deployment).order_by(Deployment.deployed_at.desc()).first()
    services_total = db.query(Service).count()
    services_healthy = db.query(Service).filter(Service.status == "healthy").count()

    record_audit_event(
        db,
        event_type="platform.status_read",
        message="Platform status endpoint was read.",
        metadata={"source": "api"},
    )

    return PlatformStatus(
        app_name=settings.app_name,
        environment=settings.environment,
        database="connected",
        services_total=services_total,
        services_healthy=services_healthy,
        environments_total=db.query(Environment).count(),
        latest_deployment_status=latest_deployment.status if latest_deployment else None,
        audit_events_total=db.query(AuditEvent).count(),
        ai_provider=settings.ai_provider,
        ai_configured=settings.ai_configured,
        ai_model=settings.gemini_model,
    )


@router.get("/environments", response_model=list[EnvironmentRead])
def list_environments(db: Session = Depends(get_db)) -> list[Environment]:
    return db.query(Environment).order_by(Environment.id).all()


@router.get("/services", response_model=list[ServiceRead])
def list_services(db: Session = Depends(get_db)) -> list[Service]:
    return db.query(Service).order_by(Service.id).all()


@router.get("/deployments", response_model=list[DeploymentRead])
def list_deployments(db: Session = Depends(get_db)) -> list[Deployment]:
    return db.query(Deployment).order_by(Deployment.deployed_at.desc()).limit(20).all()
