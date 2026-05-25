"""Engine capability endpoints for DB Sentinel AI."""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.sentinel.adapters import (
    CANONICAL_METRIC_FIELDS,
    ENGINE_STATUS,
    get_adapter,
    normalize_engine,
    supported_engines,
)

router = APIRouter()

ENGINE_CAPABILITIES: dict[str, dict[str, Any]] = {
    "postgresql": {
        "status": "stable",
        "collector": "pg_stat_activity, pg_locks, pg_stat_database, pg_stat_wal, pg_stat_statements",
        "supported_metrics": CANONICAL_METRIC_FIELDS,
        "supported_incidents": [
            "lock_wait_storm",
            "deadlock",
            "concurrent_commits",
        ],
    },
    "sqlserver": {
        "status": "beta",
        "collector": "Query Store, DMVs, wait stats, locks",
        "supported_metrics": CANONICAL_METRIC_FIELDS,
        "supported_incidents": ["lock_wait_storm", "deadlock", "concurrent_commits"],
    },
    "mysql": {
        "status": "beta",
        "collector": "Performance Schema, processlist, InnoDB status",
        "supported_metrics": CANONICAL_METRIC_FIELDS,
        "supported_incidents": ["lock_wait_storm", "deadlock", "concurrent_commits"],
    },
}


class EngineConnectionRequest(BaseModel):
    engine: str = Field(pattern="^(postgresql|postgres|sqlserver|mssql|mysql)$")
    connection_string: str = Field(min_length=8)
    database_name: str = "core_banking_sim"
    timeout_seconds: int = Field(default=8, ge=1, le=30)


@router.get("/engines", summary="Motores soportados por DB Sentinel AI")
def list_engines() -> dict[str, Any]:
    engines = []
    for engine in supported_engines():
        key = str(engine["id"])
        engines.append({**engine, **ENGINE_CAPABILITIES[key]})
    return {"engines": engines, "canonical_metrics": CANONICAL_METRIC_FIELDS}


@router.get("/engines/{engine}/metrics", summary="Metricas canonicas por motor")
def engine_metrics(engine: str) -> dict[str, Any]:
    normalized = normalize_engine(engine)
    if normalized not in ENGINE_CAPABILITIES:
        raise HTTPException(status_code=404, detail="Motor no soportado")
    return {
        "engine": normalized,
        "adapter": ENGINE_STATUS[normalized],
        **ENGINE_CAPABILITIES[normalized],
    }


@router.post("/engines/test-connection", summary="Prueba conexion multi-engine")
async def test_engine_connection(request: EngineConnectionRequest) -> dict[str, Any]:
    try:
        adapter = get_adapter(
            engine=request.engine,
            connection_string=request.connection_string,
            database_name=request.database_name,
        )
        ok = await asyncio.wait_for(adapter.test_connection(), timeout=request.timeout_seconds)
        return {
            "success": ok,
            "engine": normalize_engine(request.engine),
            "database_name": request.database_name,
            "status": "connected" if ok else "unavailable",
        }
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Tiempo de conexion agotado")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/engines/{engine}/collect", summary="Recolecta telemetria canonica de un motor")
async def collect_from_engine(
    engine: str,
    request: EngineConnectionRequest,
) -> dict[str, Any]:
    normalized_path = normalize_engine(engine)
    normalized_body = normalize_engine(request.engine)
    if normalized_path != normalized_body:
        raise HTTPException(status_code=400, detail="Engine del path y body no coinciden")
    try:
        adapter = get_adapter(
            engine=normalized_path,
            connection_string=request.connection_string,
            database_name=request.database_name,
        )
        metrics = await asyncio.wait_for(adapter.collect(), timeout=request.timeout_seconds)
        payload = metrics.to_dict()
        payload["query_sample_count"] = len(metrics.query_samples)
        payload["query_samples_preview"] = [sample.to_dict() for sample in metrics.query_samples[:5]]
        payload.pop("query_samples", None)
        return payload
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Tiempo de recoleccion agotado")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
