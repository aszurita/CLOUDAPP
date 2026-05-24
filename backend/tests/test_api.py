from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.session import Base, SessionLocal, engine
from app.main import app
from app.services.ai import AIRecommendationService
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
    assert second.json()["ai_provider"] == "openai"
    assert second.json()["ai_configured"] is False


def test_lists_base_platform_entities() -> None:
    assert len(client.get("/api/environments").json()) == 3
    assert len(client.get("/api/services").json()) >= 3
    assert len(client.get("/api/deployments").json()) >= 2


def test_platform_status_reports_openai_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    get_settings.cache_clear()

    response = client.get("/api/platform/status")

    assert response.status_code == 200
    assert response.json()["ai_provider"] == "openai"
    assert response.json()["ai_configured"] is True
    get_settings.cache_clear()


def test_query_governance_requires_openai_key() -> None:
    get_settings.cache_clear()
    response = client.post("/api/query-governance/analyze", json={"sql": "SELECT * FROM demo_customer_transactions;"})

    assert response.status_code == 503
    assert "OPENAI_API_KEY" in response.json()["detail"]


def test_query_governance_blocks_dangerous_sql(monkeypatch) -> None:
    monkeypatch.setattr(
        AIRecommendationService,
        "generate_query_guidance",
        lambda self, sql, evaluation: "OpenAI explica que la consulta esta bloqueada.",
    )

    response = client.post("/api/query-governance/analyze", json={"sql": "DROP TABLE demo_customers;"})

    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "blocked"
    assert body["risk_level"] == "blocked"
    assert any("DROP" in reason for reason in body["reasons"])


def test_query_governance_blocks_select_star(monkeypatch) -> None:
    monkeypatch.setattr(
        AIRecommendationService,
        "generate_query_guidance",
        lambda self, sql, evaluation: "OpenAI explica que SELECT * esta bloqueado.",
    )

    response = client.post("/api/query-governance/analyze", json={"sql": "SELECT * FROM demo_customer_transactions LIMIT 50;"})

    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "blocked"
    assert body["suggested_sql"] is not None


def test_query_governance_blocks_missing_limit(monkeypatch) -> None:
    monkeypatch.setattr(
        AIRecommendationService,
        "generate_query_guidance",
        lambda self, sql, evaluation: "OpenAI explica que falta LIMIT.",
    )

    response = client.post(
        "/api/query-governance/analyze",
        json={"sql": "SELECT customer_id, transaction_amount FROM demo_customer_transactions;"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "blocked"
    assert any("LIMIT" in reason for reason in body["reasons"])


def test_query_governance_executes_safe_select(monkeypatch) -> None:
    monkeypatch.setattr(
        AIRecommendationService,
        "generate_query_guidance",
        lambda self, sql, evaluation: "OpenAI aprueba el patron seguro.",
    )

    sql = (
        "SELECT customer_id, transaction_date, transaction_amount, channel "
        "FROM demo_customer_transactions "
        "WHERE transaction_date >= '2026-01-01' "
        "LIMIT 50;"
    )
    response = client.post("/api/query-governance/execute", json={"sql": sql})

    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "approved"
    assert body["row_count"] <= 100
    assert "transaction_amount" in body["columns"]


def test_dba_copilot_generates_profiles_and_recommendations(monkeypatch) -> None:
    monkeypatch.setattr(
        AIRecommendationService,
        "generate_dba_recommendations",
        lambda self, profiles: "OpenAI recomienda clasificar columnas sensibles y revisar indices.",
    )

    response = client.post("/api/dba/analyze")

    assert response.status_code == 200
    body = response.json()
    assert body["profiles_count"] >= 1
    assert body["recommendations_count"] >= 1
    assert "OpenAI" in body["ai_summary"]
