from sqlalchemy.orm import Session

from app.models import Deployment, Environment, PlatformSetting, Service
from app.services.audit import record_audit_event


def seed_demo_data(db: Session) -> None:
    if db.query(Environment).count() > 0:
        return

    dev = Environment(code="DEV", name="Development", status="healthy", region="eastus")
    qa = Environment(code="QA", name="Quality Assurance", status="healthy", region="eastus")
    prod = Environment(code="PROD", name="Production", status="attention", region="eastus")
    db.add_all([dev, qa, prod])
    db.flush()

    api = Service(
        environment_id=dev.id,
        name="cloudops-api",
        service_type="FastAPI",
        status="healthy",
        version="0.1.0",
        health_url="/health",
        cost_estimate_usd=8,
    )
    portal = Service(
        environment_id=dev.id,
        name="cloudops-portal",
        service_type="React Static Web App",
        status="healthy",
        version="0.1.0",
        cost_estimate_usd=2,
    )
    postgres = Service(
        environment_id=prod.id,
        name="platform-postgresql",
        service_type="Azure PostgreSQL",
        status="attention",
        version="16",
        cost_estimate_usd=12,
    )
    db.add_all([api, portal, postgres])
    db.flush()

    db.add_all(
        [
            Deployment(service_id=api.id, commit_sha="local-seed", status="success", deployed_by="github-actions"),
            Deployment(service_id=portal.id, commit_sha="local-seed", status="success", deployed_by="github-actions"),
        ]
    )
    db.add_all(
        [
            PlatformSetting(key="ai_provider", value="gemini", description="Default AI provider for later phases."),
            PlatformSetting(key="gemini_enabled", value="false", description="Placeholder for phase 5 AI features."),
            PlatformSetting(key="databricks_enabled", value="false", description="Placeholder for phase 3 DataOps."),
            PlatformSetting(key="datahub_enabled", value="false", description="Placeholder for phase 4 catalog."),
        ]
    )
    db.commit()
    record_audit_event(db, "platform.seeded", "Demo platform data initialized.")
