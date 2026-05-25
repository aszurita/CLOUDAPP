from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_phase8_routes_are_registered() -> None:
    paths = {route.path for route in app.routes}

    expected = {
        "/api/sentinel/predict",
        "/api/sentinel/predict/history",
        "/api/sentinel/incidents",
        "/api/sentinel/incidents/{incident_id}",
        "/api/sentinel/incidents/{incident_id}/evidence",
        "/api/sentinel/incidents/{incident_id}/resolve",
        "/api/sentinel/explain",
        "/api/sentinel/explain/{incident_id}",
        "/api/sentinel/simulate/faults",
        "/api/sentinel/simulate/fault/{fault_type}",
        "/api/sentinel/simulate/fault/{job_id}/status",
        "/api/sentinel/evaluate/model/metrics",
        "/api/sentinel/evaluate/model/shap",
        "/api/sentinel/engines",
        "/api/sentinel/engines/{engine}/metrics",
    }

    assert expected.issubset(paths)


def test_engines_endpoint_exposes_postgres_and_planned_adapters() -> None:
    response = client.get("/api/sentinel/engines")

    assert response.status_code == 200
    engines = {item["id"]: item for item in response.json()["engines"]}
    assert engines["postgresql"]["status"] == "stable"
    assert engines["sqlserver"]["status"] == "beta"
    assert "lock_waiting_sessions" in engines["postgresql"]["supported_metrics"]


def test_simulate_fault_endpoint_defaults_to_dry_run_plan() -> None:
    response = client.post(
        "/api/sentinel/simulate/fault/lock_wait_storm",
        json={"duration_seconds": 45, "intensity": "medium"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["fault_type"] == "lock_wait_storm"
    assert body["status"] == "planned"
    assert body["dry_run"] is True
    assert body["command"]
    assert body["plan"]


def test_evaluate_metrics_endpoint_loads_model_metadata() -> None:
    response = client.get("/api/sentinel/evaluate/model/metrics")

    assert response.status_code == 200
    body = response.json()
    assert body["predictor"]["model_version"] == "1.0.0"
    assert body["rca"]["model_version"] == "1.0.0"
    assert body["predictor"]["feature_count"] > 0
    assert body["rca"]["feature_count"] > 0
