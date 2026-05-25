from app.services.sentinel.rca_service import RootCauseService


def test_rca_service_diagnose_returns_ranked_causes() -> None:
    service = RootCauseService("./artifacts/root_cause_model.pkl")

    result = service.diagnose({}, top_n=3)

    assert result["model_version"] == "1.0.0"
    assert result["primary_cause"] in service.classes
    assert len(result["top_causes"]) == 3
    assert result["top_causes"][0]["rank"] == 1
    assert result["top_causes"][0]["evidence_features"]
