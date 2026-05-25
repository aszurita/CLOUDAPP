import asyncio

from app.services.sentinel.llm_copilot import (
    DBACopilotService,
    is_safe_diagnostic_sql,
    safe_sql_catalog,
)


def test_safe_sql_validator_accepts_read_only_diagnostics() -> None:
    assert is_safe_diagnostic_sql("SELECT pid, state FROM pg_stat_activity;")
    assert is_safe_diagnostic_sql("SHOW shared_buffers;")
    assert is_safe_diagnostic_sql("WITH locks AS (SELECT * FROM pg_locks) SELECT * FROM locks;")


def test_safe_sql_validator_blocks_writes_and_side_effects() -> None:
    unsafe_sqls = [
        "UPDATE accounts SET balance = 0",
        "DROP TABLE sentinel_incidents",
        "SELECT pg_terminate_backend(123)",
        "SELECT 1; DELETE FROM payments",
        "VACUUM FULL accounts",
        "DO $$ BEGIN RAISE NOTICE 'x'; END $$;",
    ]

    for sql in unsafe_sqls:
        assert not is_safe_diagnostic_sql(sql)


def test_safe_sql_catalog_returns_only_safe_queries() -> None:
    sqls = safe_sql_catalog("lock_wait_storm")

    assert sqls
    assert all(is_safe_diagnostic_sql(item["sql"]) for item in sqls)


def test_copilot_fallback_returns_dba_briefing_without_llm() -> None:
    service = DBACopilotService()
    prediction = {
        "risk_score": 0.91,
        "has_predicted_incident": True,
        "predicted_incident_type": "lock_wait_storm",
        "impact_level": "critical",
        "top3_predictions": [
            {"incident_type": "lock_wait_storm", "probability": 0.91},
            {"incident_type": "deadlock", "probability": 0.07},
        ],
        "horizon_minutes": 10,
    }
    rca_result = {
        "primary_cause": "lock_wait_storm",
        "primary_confidence": 0.88,
        "top_causes": [
            {
                "rank": 1,
                "cause": "lock_wait_storm",
                "confidence": 0.88,
                "evidence_features": [
                    {"feature": "waiting_sessions_max", "value": 31, "importance": 0.12},
                    {"feature": "active_sessions_std", "value": 8.5, "importance": 0.09},
                ],
            }
        ],
    }
    current_metrics = {
        "active_sessions": 44,
        "lock_waiting_sessions": 12,
        "idle_in_transaction": 3,
        "cache_hit_ratio": 0.99,
    }
    slow_queries = [
        {
            "queryid": 42,
            "mean_exec_time": 1200.0,
            "calls_delta": 18,
            "query_fingerprint": "UPDATE transfers SET status = $1 WHERE id = $2",
        }
    ]

    result = asyncio.run(
        service.analyze_incident(
            prediction=prediction,
            rca_result=rca_result,
            current_metrics=current_metrics,
            slow_queries=slow_queries,
            use_llm=False,
        )
    )

    assert result["model_used"] == "deterministic_dba_copilot"
    assert result["severity_classification"] == "critical"
    assert result["escalation_needed"] is True
    assert len(result["recommended_actions"]) >= 2
    assert result["diagnostic_sqls"]
    assert all(is_safe_diagnostic_sql(item["sql"]) for item in result["diagnostic_sqls"])


def test_copilot_normalizes_incomplete_llm_output_and_drops_unsafe_sql() -> None:
    service = DBACopilotService()
    safe_sqls = safe_sql_catalog("deadlock")
    fallback = {
        "incident_summary": "fallback summary",
        "impact_description": "fallback impact",
        "severity_classification": "high",
        "affected_operations": ["transferencias"],
        "top3_causes": [],
        "evidence_signals": [{"signal": "fallback evidence", "importance": "media"}],
        "recommended_actions": [
            {
                "order": 1,
                "action": "fallback action",
                "sql": safe_sqls[0]["sql"],
                "requires_approval": False,
                "urgency": "immediate",
            }
        ],
        "diagnostic_sqls": safe_sqls,
        "escalation_needed": True,
        "escalation_reason": "fallback reason",
        "generated_at": "now",
        "model_used": "fallback",
        "tokens_used": 0,
        "safety_mode": "recommend_approve_execute_audit",
    }

    result = service._normalize_llm_response(
        llm_body={
            "incident_summary": "LLM summary",
            "diagnostic_sqls": [{"title": "bad", "sql": "SELECT pg_terminate_backend(123)"}],
            "recommended_actions": [{"action": "Do something", "sql": "DROP TABLE accounts"}],
            "evidence_signals": [{"signal": "llm evidence", "importance": "urgent"}],
        },
        fallback=fallback,
        diagnostic_sqls=safe_sqls,
        tokens_used=123,
    )

    assert result["incident_summary"] == "LLM summary"
    assert result["model_used"] == service.model
    assert result["tokens_used"] == 123
    assert result["evidence_signals"][0]["importance"] == "media"
    assert result["recommended_actions"][0]["sql"] != "DROP TABLE accounts"
    assert all(is_safe_diagnostic_sql(item["sql"]) for item in result["diagnostic_sqls"])
