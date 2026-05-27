from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.controltower import (
    ControlTowerDatabase,
    ControlTowerHealthSummary,
    ControlTowerIndexResponse,
    ControlTowerIntegration,
    ControlTowerLock,
    ControlTowerMetricSnapshot,
    ControlTowerOverview,
    ControlTowerRecommendation,
    ControlTowerSession,
    ControlTowerSource,
    ControlTowerTable,
    DatabricksCatalogResponse,
)
from app.services.controltower import ControlTowerService

router = APIRouter(prefix="/controltower", tags=["Database Control Tower AI"])


@router.get("", response_model=ControlTowerIndexResponse, summary="Database Control Tower AI")
def controltower_index() -> dict[str, Any]:
    service = ControlTowerService()
    return {
        "title": service.title,
        "summary": "API local-first para monitoreo y administracion de PostgreSQL Docker, Azure PostgreSQL y Databricks. Multi-database aware.",
        "endpoints": service.endpoints(),
    }


@router.get("/database-sources", response_model=list[ControlTowerSource], summary="Lista fuentes monitoreadas")
def list_database_sources() -> list[dict[str, Any]]:
    return ControlTowerService().sources(include_metrics=True)


@router.get("/database-sources/{source_id}", response_model=ControlTowerSource, summary="Detalle de fuente monitoreada")
def get_database_source(source_id: str) -> dict[str, Any]:
    service = ControlTowerService()
    try:
        config = service._source_or_error(source_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return service.source_payload(config, include_metrics=True)


@router.post("/database-sources/{source_id}/test-connection", summary="Prueba conexion de fuente")
def test_database_source(source_id: str) -> dict[str, Any]:
    try:
        return ControlTowerService().test_connection(source_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/database-sources/{source_id}/refresh", response_model=ControlTowerMetricSnapshot, summary="Refresca metricas de fuente")
def refresh_database_source(source_id: str) -> dict[str, Any]:
    try:
        return ControlTowerService().metrics(source_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/database-sources/{source_id}/metrics", response_model=ControlTowerMetricSnapshot, summary="Metricas actuales")
def database_source_metrics(source_id: str) -> dict[str, Any]:
    try:
        return ControlTowerService().metrics(source_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/database-sources/{source_id}/databases", response_model=list[ControlTowerDatabase], summary="Bases del servidor PostgreSQL")
def database_source_databases(source_id: str) -> list[dict[str, Any]]:
    try:
        return ControlTowerService().databases(source_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/database-sources/{source_id}/tables", response_model=list[ControlTowerTable], summary="Inventario de tablas")
def database_source_tables(source_id: str) -> list[dict[str, Any]]:
    try:
        return ControlTowerService().tables(source_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/database-sources/{source_id}/sessions", response_model=list[ControlTowerSession], summary="Sesiones PostgreSQL")
def database_source_sessions(source_id: str) -> list[dict[str, Any]]:
    try:
        return ControlTowerService().sessions(source_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/database-sources/{source_id}/locks", response_model=list[ControlTowerLock], summary="Locks PostgreSQL")
def database_source_locks(source_id: str) -> list[dict[str, Any]]:
    try:
        return ControlTowerService().locks(source_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/dashboard/database-overview", response_model=ControlTowerOverview, summary="Overview Control Tower")
def database_overview() -> dict[str, Any]:
    return ControlTowerService().overview()


@router.get("/dashboard/health-summary", response_model=ControlTowerHealthSummary, summary="Resumen de salud")
def health_summary() -> dict[str, Any]:
    service = ControlTowerService()
    overview = service.overview()
    sources = overview["sources"]
    by_status: dict[str, int] = {}
    by_provider: dict[str, int] = {}
    for source in sources:
        by_status[source["status"]] = by_status.get(source["status"], 0) + 1
        provider = source["telemetry_provider"]
        by_provider[provider] = by_provider.get(provider, 0) + 1
    return {
        "health_global": overview["health_global"],
        "by_status": by_status,
        "by_provider": by_provider,
        "recommendations": service.recommendations(sources=sources),
    }


@router.get("/dashboard/cloud-integrations", response_model=list[ControlTowerIntegration], summary="Integraciones cloud")
def cloud_integrations() -> list[dict[str, Any]]:
    return ControlTowerService().integrations()


@router.get("/databricks/catalogs", response_model=DatabricksCatalogResponse, summary="Catalogos Databricks")
def databricks_catalogs(db: Session = Depends(get_db)) -> dict[str, Any]:
    return ControlTowerService().databricks_catalog(db)


@router.get("/databricks/schemas", summary="Schemas Databricks")
def databricks_schemas(db: Session = Depends(get_db)) -> dict[str, Any]:
    catalog = ControlTowerService().databricks_catalog(db)
    return {"catalog": catalog["catalog"], "schemas": catalog["schemas"], "configured": catalog["configured"]}


@router.get("/databricks/tables", response_model=list[ControlTowerTable], summary="Tablas Databricks")
def databricks_tables(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    catalog = ControlTowerService().databricks_catalog(db)
    return catalog["tables"]


@router.get("/azure/keyvault/status", summary="Estado Azure Key Vault")
def keyvault_status() -> dict[str, Any]:
    service = ControlTowerService()
    integration = next(item for item in service.integrations() if item["id"] == "key-vault")
    return integration


@router.get("/azure/postgres/{source_id}/metrics", response_model=ControlTowerMetricSnapshot, summary="Metricas Azure PostgreSQL")
def azure_postgres_metrics(source_id: str) -> dict[str, Any]:
    if source_id != "azure_postgres_cloudapp":
        raise HTTPException(status_code=404, detail="Azure PostgreSQL source not found.")
    return ControlTowerService().metrics(source_id)


@router.get("/telemetry/backend-summary", summary="Resumen telemetria backend")
def backend_telemetry_summary(db: Session = Depends(get_db)) -> dict[str, Any]:
    return ControlTowerService().telemetry_summary(db)


@router.get("/recommendations", response_model=list[ControlTowerRecommendation], summary="Recomendaciones DBA")
def controltower_recommendations() -> list[dict[str, Any]]:
    return ControlTowerService().recommendations()


@router.get("/history", summary="Historico Control Tower")
def controltower_history() -> dict[str, Any]:
    return ControlTowerService().history()
