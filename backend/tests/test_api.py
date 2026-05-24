from fastapi.testclient import TestClient

from app.db.session import Base, SessionLocal, engine
from app.main import app
from app.services.seed import seed_demo_data


def setup_module() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_demo_data(db)


client = TestClient(app)


def test_health_reports_database_connection() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["database"] == "connected"


def test_platform_status_records_audit_event() -> None:
    first = client.get("/api/platform/status")
    second = client.get("/api/platform/status")

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["audit_events_total"] >= first.json()["audit_events_total"]
    assert second.json()["ai_provider"] == "gemini"
    assert second.json()["ai_configured"] is False


def test_lists_base_platform_entities() -> None:
    assert len(client.get("/api/environments").json()) == 3
    assert len(client.get("/api/services").json()) >= 3
    assert len(client.get("/api/deployments").json()) >= 2
