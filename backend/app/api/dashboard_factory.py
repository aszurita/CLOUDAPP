"""
AI Dashboard Factory
====================
Sección: /api/dashboard-factory

Endpoints
---------
GET  /                                          Estado del factory
POST /plan                                      Planifica dashboard desde prompt (sin guardar)
POST /generate                                  Guarda dashboard confirmado en PostgreSQL
POST /dashboards/{id}/execute                   Ejecuta queries y devuelve datos al frontend
GET  /dashboards                                Lista todos los dashboards guardados
GET  /dashboards/{id}                           Detalle de un dashboard
PUT  /dashboards/{id}                           Actualiza nombre / schema
DELETE /dashboards/{id}                         Elimina dashboard
GET  /catalogs                                  Catálogos de Databricks Unity Catalog
GET  /catalogs/{catalog}/schemas                Esquemas de un catálogo
GET  /catalogs/{catalog}/schemas/{schema}/tables  Tablas de un esquema
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.dashboard_factory import (
    CatalogItem,
    DashboardListResponse,
    DashboardRecord,
    ExecuteDashboardResponse,
    FactoryStatusResponse,
    GenerateDashboardRequest,
    GenerateDashboardResponse,
    GoldFactoryRequest,
    GoldFactoryRequestStatus,
    GoldFactorySubmitRequest,
    GoldFactorySubmitResponse,
    GoldTablePlan,
    PlanDashboardRequest,
    PlanDashboardResponse,
    SchemaItem,
    TableItem,
    UpdateDashboardRequest,
)
from app.services.dashboard_factory import DashboardFactoryService

router = APIRouter(prefix="/dashboard-factory", tags=["AI Dashboard Factory"])


def _svc() -> DashboardFactoryService:
    return DashboardFactoryService()


# ── Status ────────────────────────────────────────────────────────────────────


@router.get("", response_model=FactoryStatusResponse, summary="Estado del AI Dashboard Factory")
def factory_status(db: Session = Depends(get_db)) -> dict[str, Any]:
    return _svc().get_status(db)


# ── Planning ──────────────────────────────────────────────────────────────────


@router.post(
    "/plan",
    response_model=PlanDashboardResponse,
    summary="Genera un plan de dashboard (queries + widgets) sin guardarlo",
)
def plan_dashboard(req: PlanDashboardRequest) -> dict[str, Any]:
    return _svc().plan_dashboard(req.prompt, req.catalog, req.schema_name, req.table)


@router.post(
    "/gold/plan",
    response_model=GoldTablePlan,
    summary="Analiza un prompt y propone una tabla/vista Gold validada",
)
def plan_gold_request(req: GoldFactoryRequest) -> dict[str, Any]:
    return _svc().plan_gold_request(
        req.prompt,
        req.target_catalog,
        req.target_schema,
        req.object_type,
    )


@router.post(
    "/gold/submit",
    response_model=GoldFactorySubmitResponse,
    summary="Registra dataops_requests y dispara el Job materializador de Databricks",
)
def submit_gold_request(
    req: GoldFactorySubmitRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        return _svc().submit_gold_request(
            req.prompt,
            req.plan.model_dump(),
            req.write_mode,
            req.created_by,
            db,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/gold/requests/{request_id}",
    response_model=GoldFactoryRequestStatus,
    summary="Consulta estado final de una solicitud Gold en dataops_requests",
)
def get_gold_request_status(request_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    result = _svc().get_gold_request_status(request_id, db)
    if not result:
        raise HTTPException(status_code=404, detail="Solicitud Gold no encontrada.")
    return result


@router.get(
    "/gold/history",
    response_model=list[GoldFactoryRequestStatus],
    summary="Historial local de tablas/vistas Gold materializadas por Job",
)
def list_gold_request_history(limit: int = 50, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return _svc().list_gold_request_history(db, limit=limit)


# ── Generation ────────────────────────────────────────────────────────────────


@router.post(
    "/generate",
    response_model=GenerateDashboardResponse,
    summary="Guarda un dashboard confirmado en PostgreSQL",
)
def generate_dashboard(
    req: GenerateDashboardRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return _svc().generate_dashboard(
        req.prompt, req.catalog, req.schema_name, req.dashboard_schema.model_dump(), db
    )


# ── Execution ─────────────────────────────────────────────────────────────────


@router.post(
    "/dashboards/{dashboard_id}/execute",
    response_model=ExecuteDashboardResponse,
    summary="Ejecuta todas las queries del dashboard y devuelve datos por widget",
)
def execute_dashboard(dashboard_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    result = _svc().execute_dashboard(dashboard_id, db)
    if not result:
        raise HTTPException(status_code=404, detail="Dashboard no encontrado.")
    return result


# ── CRUD ──────────────────────────────────────────────────────────────────────


@router.get(
    "/dashboards",
    response_model=DashboardListResponse,
    summary="Lista todos los dashboards guardados",
)
def list_dashboards(db: Session = Depends(get_db)) -> dict[str, Any]:
    return _svc().list_dashboards(db)


@router.get(
    "/dashboards/{dashboard_id}",
    response_model=DashboardRecord,
    summary="Detalle de un dashboard por ID",
)
def get_dashboard(dashboard_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    result = _svc().get_dashboard(dashboard_id, db)
    if not result:
        raise HTTPException(status_code=404, detail="Dashboard no encontrado.")
    return result


@router.put(
    "/dashboards/{dashboard_id}",
    response_model=DashboardRecord,
    summary="Actualiza nombre o schema de un dashboard",
)
def update_dashboard(
    dashboard_id: int,
    req: UpdateDashboardRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if req.name:
        payload["name"] = req.name
    if req.dashboard_schema:
        payload["dashboard_schema"] = req.dashboard_schema.model_dump()
    result = _svc().update_dashboard(dashboard_id, payload, db)
    if not result:
        raise HTTPException(status_code=404, detail="Dashboard no encontrado.")
    return result


@router.delete(
    "/dashboards/{dashboard_id}",
    status_code=204,
    response_class=Response,
    summary="Elimina un dashboard del historial",
)
def delete_dashboard(dashboard_id: int, db: Session = Depends(get_db)) -> Response:
    if not _svc().delete_dashboard(dashboard_id, db):
        raise HTTPException(status_code=404, detail="Dashboard no encontrado.")
    return Response(status_code=204)


# ── Catalog / Schema / Table discovery ───────────────────────────────────────


@router.get("/catalogs", response_model=list[CatalogItem], summary="Catálogos de Databricks")
def list_catalogs() -> list[dict[str, str]]:
    return _svc().get_catalogs()


@router.get(
    "/catalogs/{catalog}/schemas",
    response_model=list[SchemaItem],
    summary="Esquemas de un catálogo",
)
def list_schemas(catalog: str) -> list[dict[str, str]]:
    return _svc().get_schemas(catalog)


@router.get(
    "/catalogs/{catalog}/schemas/{schema}/tables",
    response_model=list[TableItem],
    summary="Tablas de un esquema",
)
def list_tables(catalog: str, schema: str) -> list[dict[str, str]]:
    return _svc().get_tables(catalog, schema)
