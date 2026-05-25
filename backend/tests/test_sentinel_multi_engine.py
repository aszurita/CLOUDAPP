from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import app
from app.services.sentinel.adapters import (
    CANONICAL_METRIC_FIELDS,
    MySQLAdapter,
    PostgresAdapter,
    SQLServerAdapter,
    get_adapter,
    normalize_engine,
    supported_engines,
)
from app.services.sentinel.adapters.base_adapter import CanonicalMetrics, QuerySample
from app.services.sentinel.collector_service import PostgresCollector

client = TestClient(app)


def test_adapter_registry_resolves_supported_engines() -> None:
    assert isinstance(get_adapter("postgres", "postgresql://u:p@localhost:5432/db", "db"), PostgresAdapter)
    assert isinstance(get_adapter("sqlserver", "dsn", "db"), SQLServerAdapter)
    assert isinstance(get_adapter("mysql", "mysql://u:p@localhost:3306/db", "db"), MySQLAdapter)
    assert normalize_engine("mssql") == "sqlserver"


def test_canonical_metrics_contract_has_required_model_fields() -> None:
    required = {
        "active_sessions",
        "waiting_sessions",
        "lock_waiting_sessions",
        "cache_hit_ratio",
        "xact_commit_delta",
        "wal_bytes_delta",
        "replication_lag_seconds",
        "mean_query_latency_ms",
    }

    assert required.issubset(set(CANONICAL_METRIC_FIELDS))

    metrics = CanonicalMetrics(
        collected_at=datetime.now(timezone.utc),
        engine="postgresql",
        database_name="core_banking_sim",
        active_sessions=3,
        query_samples=[QuerySample(queryid=1, query_fingerprint="SELECT 1", calls_delta=2)],
    )
    payload = metrics.to_dict()

    assert payload["active_sessions"] == 3
    assert payload["query_samples"][0]["query_fingerprint"] == "SELECT 1"
    assert len(metrics.storage_metric_values()) == 21


def test_postgres_adapter_parses_local_dsn_without_ssl() -> None:
    kwargs = PostgresAdapter.conn_kwargs("postgresql://user:pass@localhost:5433/core_banking_sim")

    assert kwargs["host"] == "localhost"
    assert kwargs["port"] == 5433
    assert kwargs["database"] == "core_banking_sim"
    assert kwargs["ssl"] is False


def test_collector_uses_postgres_adapter() -> None:
    collector = PostgresCollector(
        monitor_dsn="postgresql://user:pass@localhost:5433/core_banking_sim",
        storage_dsn="postgresql://user:pass@localhost:5432/cloudapp",
        database_name="core_banking_sim",
    )

    assert isinstance(collector.adapter, PostgresAdapter)


def test_engines_endpoints_expose_multi_engine_contract() -> None:
    response = client.get("/api/sentinel/engines")

    assert response.status_code == 200
    body = response.json()
    engines = {item["id"]: item for item in body["engines"]}
    assert set(engines) >= {"postgresql", "sqlserver", "mysql"}
    assert engines["postgresql"]["status"] == "stable"
    assert engines["sqlserver"]["status"] == "beta"
    assert "canonical_metrics" in body


def test_engine_collect_rejects_path_body_mismatch() -> None:
    response = client.post(
        "/api/sentinel/engines/mysql/collect",
        json={
            "engine": "postgresql",
            "connection_string": "postgresql://user:pass@localhost:5433/core_banking_sim",
            "database_name": "core_banking_sim",
            "timeout_seconds": 1,
        },
    )

    assert response.status_code == 400


def test_supported_engines_metadata_is_dashboard_ready() -> None:
    engines = supported_engines()

    assert all("canonical_metric_count" in engine for engine in engines)
    assert all(engine["canonical_metric_count"] >= 10 for engine in engines)
