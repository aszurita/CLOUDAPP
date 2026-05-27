from fastapi.testclient import TestClient
import pytest
import json

from app.core.config import get_settings
from app.db.session import Base, SessionLocal, engine
from app.main import app
from app.services.ai import AIRecommendationService
from app.services.dashboard_factory import DashboardFactoryService
from app.services.seed import seed_demo_data


def setup_module() -> None:
    if engine.dialect.name != "sqlite":
        raise RuntimeError(
            "Tests require an isolated SQLite database. "
            "Refusing to run Base.metadata.drop_all() against a non-SQLite database."
        )
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_demo_data(db)


client = TestClient(app)


@pytest.fixture(autouse=True)
def isolate_openai_env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "phase-test-placeholder")
    monkeypatch.setenv("DATABRICKS_HOST", "")
    monkeypatch.setenv("DATABRICKS_TOKEN", "")
    monkeypatch.setenv("DATABRICKS_JOB_ID", "")
    monkeypatch.setenv("DATAHUB_ENABLED", "false")
    monkeypatch.setenv("DATAHUB_SERVER", "")
    monkeypatch.setenv("DATAHUB_TOKEN", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


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


def test_dataops_pipeline_run_persists_demo_metrics() -> None:
    response = client.post("/api/dataops/pipelines/run", json={"actor": "test-user"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["bronze_rows"] > body["silver_rows"]
    assert body["silver_rows"] >= body["gold_rows"]
    assert body["quality_score"] > 99
    assert body["quarantine_rows"] == 1054
    assert len(body["generated_tables_json"]) >= 3


def test_dataops_monitor_exposes_quality_assets_and_quarantine() -> None:
    client.post("/api/dataops/pipelines/run", json={"actor": "test-user"})

    current = client.get("/api/dataops/pipelines/current")
    quality = client.get("/api/dataops/quality/latest")
    assets = client.get("/api/dataops/assets")
    quarantine = client.get("/api/dataops/quarantine")

    assert current.status_code == 200
    assert current.json()["pipeline"]["name"] == "tpcds-retail-dataops"
    assert current.json()["latest_run"]["status"] == "success"
    assert quality.status_code == 200
    assert any(item["status"] == "failed" for item in quality.json())
    assert assets.status_code == 200
    assert any(item["layer"] == "gold" for item in assets.json())
    assert quarantine.status_code == 200
    assert len(quarantine.json()) >= 1


def test_dataops_monitor_supports_banking_alerts_pipeline() -> None:
    pipelines = client.get("/api/dataops/pipelines")

    assert pipelines.status_code == 200
    assert any(item["pipeline_key"] == "alertas-movimientos-inusuales" for item in pipelines.json())

    response = client.post("/api/dataops/pipelines/alertas-movimientos-inusuales/run", json={"actor": "test-user"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["business_run_id"].startswith("RUN-")
    assert body["databricks_run_id"] is not None
    assert body["quarantine_rows"] == 0
    assert any(metric["key"] == "alerts_generated" and metric["value"] == 2 for metric in body["metrics_json"])
    assert any(metric["key"] == "transactions_inserted" and metric["label"] == "Source transactions" for metric in body["metrics_json"])
    assert any("banco_demo.alertas_movimientos_inusuales" in table for table in body["generated_tables_json"])
    assert len(body["events_json"]) >= 2

    current = client.get("/api/dataops/pipelines/alertas-movimientos-inusuales/current")
    quality = client.get("/api/dataops/pipelines/alertas-movimientos-inusuales/quality/latest")
    assets = client.get("/api/dataops/pipelines/alertas-movimientos-inusuales/assets")
    quarantine = client.get("/api/dataops/pipelines/alertas-movimientos-inusuales/quarantine")

    assert current.status_code == 200
    assert current.json()["pipeline"]["databricks_job_id"] == "88827781921882"
    assert "genera transacciones" not in current.json()["pipeline"]["description"].lower()
    assert current.json()["latest_run"]["business_run_id"] == body["business_run_id"]
    assert quality.status_code == 200
    assert any(item["rule_code"] == "email_notification" for item in quality.json())
    assert all("generadas para la corrida" not in item["description"].lower() for item in quality.json())
    assert assets.status_code == 200
    assert any(item["layer"] == "audit" for item in assets.json())
    assert quarantine.status_code == 200
    assert quarantine.json() == []


def test_dataops_monitor_supports_configured_databricks_jobs(monkeypatch) -> None:
    monkeypatch.delenv("DATABRICKS_JOB_ID", raising=False)
    monkeypatch.setenv(
        "DATAOPS_PIPELINES_JSON",
        json.dumps(
            [
                {
                    "pipeline_key": "riesgo-clientes-gold",
                    "name": "JOB_RIESGO_CLIENTES_GOLD",
                    "pipeline_type": "lakehouse_bronze_silver_gold",
                    "description": "Job configurable para score de riesgo de clientes.",
                    "databricks_job_id": "123456789",
                    "summary_task_key": "emit_run_summary",
                    "notebook_params": {"catalog": "databricks_proyectobg", "gold_schema": "risk_gold"},
                }
            ]
        ),
    )
    get_settings.cache_clear()

    response = client.get("/api/dataops/pipelines")

    assert response.status_code == 200
    pipelines = {item["pipeline_key"]: item for item in response.json()}
    assert set(pipelines) == {"riesgo-clientes-gold"}
    assert "riesgo-clientes-gold" in pipelines
    assert pipelines["riesgo-clientes-gold"]["databricks_job_id"] == "123456789"
    assert pipelines["riesgo-clientes-gold"]["config_json"]["summary_task_key"] == "emit_run_summary"


def test_gold_factory_submit_persists_history() -> None:
    prompt = "Crear una Gold de ventas mensuales por categoria"
    plan_response = client.post(
        "/api/dashboard-factory/gold/plan",
        json={
            "prompt": prompt,
            "target_catalog": "databricks_proyectobg",
            "target_schema": "tpcds_gold",
            "object_type": "TABLE",
        },
    )
    assert plan_response.status_code == 200
    plan = plan_response.json()
    assert plan["validation_status"] == "APPROVED"

    submit_response = client.post(
        "/api/dashboard-factory/gold/submit",
        json={
            "prompt": prompt,
            "plan": plan,
            "write_mode": "OR_REPLACE",
            "created_by": "test-user",
        },
    )
    assert submit_response.status_code == 200
    submitted = submit_response.json()
    assert submitted["status"] == "DEMO_SUCCESS"

    status_response = client.get(f"/api/dashboard-factory/gold/requests/{submitted['request_id']}")
    history_response = client.get("/api/dashboard-factory/gold/history")

    assert status_response.status_code == 200
    assert status_response.json()["target_table"] == submitted["target_table"]
    assert status_response.json()["databricks_run_id"] is None
    assert history_response.status_code == 200
    assert any(item["request_id"] == submitted["request_id"] for item in history_response.json())


def test_gold_factory_repairs_quality_literal_aliases() -> None:
    service = DashboardFactoryService()
    catalog = service._demo_catalog_snapshot("databricks_proyectobg")
    plan = {"source_tables": ["databricks_proyectobg.tpcds_silver.store_sales_clean"]}
    source_sql = (
        "SELECT store_sales_clean AS table_name, ss_quantity_negative AS failed_rule, "
        "COUNT(*) AS failed_records "
        "FROM databricks_proyectobg.tpcds_silver.store_sales_clean "
        "WHERE ss_quantity < 0 "
        "GROUP BY store_sales_clean, ss_quantity_negative"
    )

    repaired = service._repair_gold_source_sql(source_sql, plan, catalog)

    assert "'store_sales_clean' AS table_name" in repaired
    assert "'ss_quantity_negative' AS failed_rule" in repaired
    assert "GROUP BY 'store_sales_clean', 'ss_quantity_negative'" in repaired


def test_gold_factory_submit_records_databricks_run(monkeypatch) -> None:
    service = DashboardFactoryService()
    service.settings.databricks_host = "https://adb-12345.1.azuredatabricks.net"
    service.settings.databricks_token = "token"
    service.settings.databricks_sql_warehouse_id = "warehouse"
    service.settings.databricks_gold_factory_job_id = "54321"
    monkeypatch.setattr(service, "_databricks_ready", lambda: True)
    monkeypatch.setattr(service, "_insert_control_request", lambda **_: None)
    monkeypatch.setattr(service, "_start_gold_factory_job", lambda request_id: {"run_id": 98765})
    plan = {
        "target_catalog": "databricks_proyectobg",
        "target_schema": "tpcds_gold",
        "target_name": "sales_by_month_category",
        "object_type": "TABLE",
        "source_tables": ["databricks_proyectobg.tpcds_silver.store_sales_clean"],
        "source_sql": "SELECT ss_store_sk, COUNT(*) AS total FROM databricks_proyectobg.tpcds_silver.store_sales_clean GROUP BY ss_store_sk",
        "validation_messages": [],
    }

    with SessionLocal() as db:
        response = service.submit_gold_request(
            "Crear Gold de ventas",
            plan,
            "OR_REPLACE",
            "test-user",
            db,
        )

    assert response["status"] == "PENDING"
    assert response["databricks_run_id"] == "98765"
    assert response["databricks_run_url"] == (
        "https://adb-12345.1.azuredatabricks.net/?o=12345#job/54321/run/98765"
    )


def test_catalog_sync_creates_assets_columns_and_lineage() -> None:
    client.post("/api/dataops/pipelines/run", json={"actor": "test-user"})

    sync_response = client.post("/api/catalog/sync", json={"actor": "test-user"})
    assert sync_response.status_code == 200
    sync_body = sync_response.json()
    assert sync_body["status"] == "success"
    assert sync_body["assets_seen"] >= 3

    status = client.get("/api/catalog/status")
    assets = client.get("/api/catalog/assets")
    lineage = client.get("/api/catalog/lineage")

    assert status.status_code == 200
    assert status.json()["external_catalog"] == "not_configured"
    assert status.json()["assets_total"] >= 3
    assert assets.status_code == 200
    assert any(asset["layer"] == "gold" for asset in assets.json())
    assert any(asset["sensitivity_level"] in {"confidential", "restricted"} for asset in assets.json())
    assert lineage.status_code == 200
    assert len(lineage.json()) >= 2

    first_asset_id = assets.json()[0]["id"]
    columns = client.get(f"/api/catalog/assets/{first_asset_id}/columns")
    assert columns.status_code == 200
    assert len(columns.json()) >= 1

    first_column = columns.json()[0]
    assert first_column["description"] is None
    update_column = client.post(
        f"/api/catalog/columns/{first_column['id']}/description",
        json={"description": "Identificador tecnico de ejecucion usado para trazabilidad.", "actor": "test-user"},
    )
    assert update_column.status_code == 200
    assert "trazabilidad" in update_column.json()["description"]

    client.post("/api/catalog/sync", json={"actor": "test-user"})
    refreshed_columns = client.get(f"/api/catalog/assets/{first_asset_id}/columns").json()
    refreshed = next(item for item in refreshed_columns if item["column_name"] == first_column["column_name"])
    assert "trazabilidad" in refreshed["description"]


def test_catalog_documentation_and_metadata_updates(monkeypatch) -> None:
    client.post("/api/dataops/pipelines/run", json={"actor": "test-user"})
    client.post("/api/catalog/sync", json={"actor": "test-user"})
    asset = client.get("/api/catalog/assets").json()[0]

    monkeypatch.setattr(
        AIRecommendationService,
        "generate_catalog_documentation",
        lambda self, metadata: "Propósito: documentación gobernada sin datos crudos. Riesgos: validar owner.",
    )

    doc_response = client.post(f"/api/catalog/assets/{asset['id']}/document", json={"actor": "test-user"})
    assert doc_response.status_code == 200
    assert "datos crudos" in doc_response.json()["documentation"]
    assert doc_response.json()["asset"]["documentation_status"] == "generated"

    owner_response = client.post(
        f"/api/catalog/assets/{asset['id']}/owner",
        json={"owner": "data-governance-team", "actor": "test-user"},
    )
    assert owner_response.status_code == 200
    assert owner_response.json()["owner"] == "data-governance-team"

    classification_response = client.post(
        f"/api/catalog/assets/{asset['id']}/classification",
        json={"classification": "restricted", "actor": "test-user"},
    )
    assert classification_response.status_code == 200
    assert classification_response.json()["sensitivity_level"] == "restricted"


def test_autopilot_analysis_generates_report_tasks_and_history() -> None:
    client.post("/api/dataops/pipelines/run", json={"actor": "test-user"})
    client.post("/api/catalog/sync", json={"actor": "test-user"})

    response = client.post("/api/autopilot/analyze", json={"actor": "test-user", "include_ai": False})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert 0 <= body["overall_score"] <= 100
    assert body["risk_level"] in {"critical", "high", "medium", "low"}
    assert body["metrics_json"]["findings_total"] >= 1
    assert len(body["findings_json"]) >= 1
    assert body["metrics_json"]["catalog_assets"] >= 1
    assert "secret" not in str(body["raw_context_json"]).lower()

    latest = client.get("/api/autopilot/latest")
    history = client.get("/api/autopilot/history")

    assert latest.status_code == 200
    assert latest.json()["latest_report"]["run_id"] == body["run_id"]
    assert history.status_code == 200
    assert any(item["run_id"] == body["run_id"] for item in history.json())

    if body["tasks"]:
        task_id = body["tasks"][0]["id"]
        update = client.post(f"/api/autopilot/tasks/{task_id}/status", json={"status": "done", "actor": "test-user"})
        assert update.status_code == 200
        assert update.json()["status"] == "done"
