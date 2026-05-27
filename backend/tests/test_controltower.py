from fastapi import FastAPI

from app.core.config import Settings
from app.core.telemetry import configure_telemetry, get_telemetry_status
from app.services.controltower import AZURE_POSTGRES_CONNECT_TIMEOUT_SECONDS, ControlTowerService


def test_azure_postgres_url_sets_short_connect_timeout() -> None:
    service = ControlTowerService(
        Settings(
            azure_postgres_host="db.example.postgres.database.azure.com",
            azure_postgres_user="cloudapp",
            azure_postgres_password="secret",
        )
    )

    url = service._azure_postgres_url()

    assert url is not None
    assert f"connect_timeout={AZURE_POSTGRES_CONNECT_TIMEOUT_SECONDS}" in url


def test_offline_cloud_source_does_not_query_databases(monkeypatch) -> None:
    service = ControlTowerService(
        Settings(
            azure_postgres_host="db.example.postgres.database.azure.com",
            azure_postgres_user="cloudapp",
            azure_postgres_password="secret",
        )
    )
    config = service._azure_postgres_source()

    monkeypatch.setattr(service, "metrics", lambda _source_id: service._empty_snapshot("offline", 0, "timeout"))

    def fail_if_called(_source_id: str) -> list[dict]:
        raise AssertionError("databases should not be queried after an offline metric snapshot")

    monkeypatch.setattr(service, "databases", fail_if_called)

    payload = service.source_payload(config, include_metrics=True)

    assert payload["status"] == "offline"
    assert payload["databases"] == []
    assert payload["databases_count"] == 0


def test_telemetry_status_reports_runtime_state_without_full_key() -> None:
    settings = Settings(
        applicationinsights_connection_string=(
            "InstrumentationKey=11112222-3333-4444-5555-666677778888;"
            "IngestionEndpoint=https://example.in.applicationinsights.azure.com/;"
            "LiveEndpoint=https://example.livediagnostics.monitor.azure.com/;"
            "ApplicationId=aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeffff"
        ),
        applicationinsights_live_metrics_enabled=True,
    )

    configure_telemetry(FastAPI(), settings)
    status = get_telemetry_status()

    assert status["configured"] is True
    assert status["enabled"] is False
    assert status["status"] == "disabled_pytest"
    assert status["live_metrics_enabled"] is True
    assert status["connection"]["ingestion_endpoint"] == "https://example.in.applicationinsights.azure.com"
    assert status["connection"]["instrumentation_key_suffix"] == "778888"
    assert "11112222-3333-4444-5555-666677778888" not in str(status["connection"])
