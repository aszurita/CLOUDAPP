from datetime import date, datetime
from decimal import Decimal
from time import perf_counter
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import engine, get_db
from app.models import (
    AuditEvent,
    AutopilotReport,
    AutopilotTask,
    CatalogAsset,
    CatalogClassification,
    CatalogColumn,
    CatalogLineageEdge,
    CatalogSyncRun,
    DataOpsGeneratedAsset,
    DataOpsPipeline,
    DataOpsPipelineRun,
    DataOpsQualityCheck,
    DataOpsQuarantineEvent,
    DbaRecommendation,
    DbaTableProfile,
    Deployment,
    Environment,
    QueryPolicy,
    QueryReview,
    Service,
)
from app.schemas.autopilot import (
    AutopilotCurrentResponse,
    AutopilotReportRead,
    AutopilotRunRequest,
    AutopilotTaskRead,
    AutopilotTaskStatusUpdateRequest,
)
from app.schemas.catalog import (
    CatalogAssetRead,
    CatalogClassificationRead,
    CatalogClassificationUpdateRequest,
    CatalogColumnDescriptionUpdateRequest,
    CatalogColumnRead,
    CatalogDocumentResponse,
    CatalogLineageEdgeRead,
    CatalogOwnerUpdateRequest,
    CatalogStatusResponse,
    CatalogSyncRequest,
    CatalogSyncRunRead,
)
from app.schemas.dataops import (
    DataOpsCurrentResponse,
    DataOpsGeneratedAssetRead,
    DataOpsPipelineRead,
    DataOpsPipelineRunRead,
    DataOpsQualityCheckRead,
    DataOpsQuarantineEventRead,
    DataOpsRunRequest,
)
from app.schemas.governance import (
    DbaAnalyzeResponse,
    DbaRecommendationRead,
    DbaTableProfileRead,
    DemoQueriesResponse,
    QueryAnalyzeRequest,
    QueryAnalyzeResponse,
    QueryExecuteRequest,
    QueryExecuteResponse,
    QueryPolicyRead,
    QueryReviewRead,
)
from app.schemas.platform import DeploymentRead, EnvironmentRead, PlatformStatus, ServiceRead
from app.services.ai import AIConfigurationError, AIRecommendationService
from app.services.audit import record_audit_event
from app.services.autopilot import AutopilotService
from app.services.catalog import CatalogGovernanceService
from app.services.dataops import DEFAULT_PIPELINE_KEY, DataOpsMonitorService
from app.services.database_inventory import collect_database_inventory
from app.services.dba import DbaCopilotService
from app.services.query_governance import QueryGovernanceEngine

router = APIRouter()


@router.get("/platform/status", response_model=PlatformStatus)
def platform_status(db: Session = Depends(get_db)) -> PlatformStatus:
    settings = get_settings()
    db.execute(text("SELECT 1"))
    latest_deployment = db.query(Deployment).order_by(Deployment.deployed_at.desc()).first()
    services_total = db.query(Service).count()
    services_healthy = db.query(Service).filter(Service.status == "healthy").count()

    record_audit_event(
        db,
        event_type="platform.status_read",
        message="Platform status endpoint was read.",
        metadata={"source": "api"},
    )

    return PlatformStatus(
        app_name=settings.app_name,
        environment=settings.environment,
        database="connected",
        services_total=services_total,
        services_healthy=services_healthy,
        environments_total=db.query(Environment).count(),
        latest_deployment_status=latest_deployment.status if latest_deployment else None,
        audit_events_total=db.query(AuditEvent).count(),
        ai_provider=settings.ai_provider,
        ai_configured=settings.ai_configured,
        ai_model=settings.ai_model,
    )


@router.get("/environments", response_model=list[EnvironmentRead])
def list_environments(db: Session = Depends(get_db)) -> list[Environment]:
    return db.query(Environment).order_by(Environment.id).all()


@router.get("/services", response_model=list[ServiceRead])
def list_services(db: Session = Depends(get_db)) -> list[Service]:
    return db.query(Service).order_by(Service.id).all()


@router.get("/deployments", response_model=list[DeploymentRead])
def list_deployments(db: Session = Depends(get_db)) -> list[Deployment]:
    return db.query(Deployment).order_by(Deployment.deployed_at.desc()).limit(20).all()


@router.post("/query-governance/analyze", response_model=QueryAnalyzeResponse)
def analyze_query(payload: QueryAnalyzeRequest, db: Session = Depends(get_db)) -> QueryAnalyzeResponse:
    evaluation = QueryGovernanceEngine().evaluate(payload.sql)
    ai_explanation = _query_ai_explanation(payload.sql, evaluation.as_dict())
    review = _create_query_review(
        db=db,
        sql_text=payload.sql,
        action="analyze",
        actor=payload.actor,
        evaluation=evaluation.as_dict(),
        ai_explanation=ai_explanation,
    )
    record_audit_event(
        db,
        "query.analyzed",
        f"Query analyzed with decision {evaluation.decision}.",
        actor=payload.actor,
        severity="warning" if evaluation.decision == "blocked" else "info",
        metadata={"query_review_id": review.id, "risk_level": evaluation.risk_level},
    )
    return _query_analyze_response(review)


@router.post("/query-governance/execute", response_model=QueryExecuteResponse)
def execute_query(payload: QueryExecuteRequest, db: Session = Depends(get_db)) -> QueryExecuteResponse:
    evaluation = QueryGovernanceEngine().evaluate(payload.sql)
    ai_explanation = _query_ai_explanation(payload.sql, evaluation.as_dict())
    if evaluation.decision != "approved":
        review = _create_query_review(
            db=db,
            sql_text=payload.sql,
            action="execute",
            actor=payload.actor,
            evaluation=evaluation.as_dict(),
            ai_explanation=ai_explanation,
        )
        record_audit_event(
            db,
            "query.blocked",
            "Blocked query execution attempt.",
            actor=payload.actor,
            severity="warning",
            metadata={"query_review_id": review.id, "reasons": evaluation.reasons},
        )
        raise HTTPException(status_code=400, detail=_query_analyze_response(review).model_dump(mode="json"))

    started = perf_counter()
    columns, rows = _execute_readonly_select(payload.sql)
    execution_ms = round((perf_counter() - started) * 1000)
    review = _create_query_review(
        db=db,
        sql_text=payload.sql,
        action="execute",
        actor=payload.actor,
        evaluation=evaluation.as_dict(),
        ai_explanation=ai_explanation,
        row_count=len(rows),
        execution_ms=execution_ms,
    )
    record_audit_event(
        db,
        "query.executed",
        "Approved read-only query was executed.",
        actor=payload.actor,
        metadata={"query_review_id": review.id, "row_count": len(rows), "execution_ms": execution_ms},
    )
    response = _query_analyze_response(review)
    return QueryExecuteResponse(**response.model_dump(), columns=columns, rows=rows, row_count=len(rows), execution_ms=execution_ms)


@router.get("/query-governance/history", response_model=list[QueryReviewRead])
def query_history(db: Session = Depends(get_db)) -> list[QueryReview]:
    return db.query(QueryReview).order_by(QueryReview.created_at.desc()).limit(30).all()


@router.get("/query-governance/policies", response_model=list[QueryPolicyRead])
def query_policies(db: Session = Depends(get_db)) -> list[QueryPolicy]:
    return db.query(QueryPolicy).filter(QueryPolicy.enabled.is_(True)).order_by(QueryPolicy.id).all()


@router.get("/query-governance/metadata")
def query_metadata() -> dict[str, Any]:
    return collect_database_inventory()


@router.get("/query-governance/demo-queries", response_model=DemoQueriesResponse)
def demo_queries() -> DemoQueriesResponse:
    return DemoQueriesResponse(
        dangerous="SELECT * FROM demo_customer_transactions;",
        safe=(
            "SELECT customer_id, transaction_date, transaction_amount, channel, status "
            "FROM demo_customer_transactions "
            "WHERE transaction_date >= '2026-01-01' "
            "LIMIT 50;"
        ),
    )


@router.post("/dba/analyze", response_model=DbaAnalyzeResponse)
def analyze_dba(db: Session = Depends(get_db)) -> DbaAnalyzeResponse:
    service = DbaCopilotService(engine)
    profiles = service.collect_profiles()
    ai_summary = _dba_ai_summary(profiles)
    profile_models, recommendations = service.refresh_profiles(db, ai_summary)
    record_audit_event(
        db,
        "dba.analyzed",
        "DBA Copilot analyzed PostgreSQL metadata.",
        metadata={"profiles_count": len(profile_models), "recommendations_count": len(recommendations)},
    )
    return DbaAnalyzeResponse(
        profiles_count=len(profile_models),
        recommendations_count=len(recommendations),
        ai_summary=ai_summary,
    )


@router.get("/dba/tables", response_model=list[DbaTableProfileRead])
def dba_tables(db: Session = Depends(get_db)) -> list[DbaTableProfile]:
    return db.query(DbaTableProfile).order_by(DbaTableProfile.risk_level.desc(), DbaTableProfile.table_name).all()


@router.get("/dba/recommendations", response_model=list[DbaRecommendationRead])
def dba_recommendations(db: Session = Depends(get_db)) -> list[DbaRecommendation]:
    return db.query(DbaRecommendation).order_by(DbaRecommendation.created_at.desc()).limit(30).all()


@router.get("/dba/sources")
def dba_sources() -> dict[str, Any]:
    return collect_database_inventory()


@router.get("/database/inventory")
def database_inventory() -> dict[str, Any]:
    return collect_database_inventory()


@router.post("/dataops/pipelines/run", response_model=DataOpsPipelineRunRead)
def run_dataops_pipeline(payload: DataOpsRunRequest, db: Session = Depends(get_db)) -> DataOpsPipelineRun:
    return _run_dataops_pipeline_for_key(DEFAULT_PIPELINE_KEY, payload, db)


@router.get("/dataops/pipelines", response_model=list[DataOpsPipelineRead])
def list_dataops_pipelines(db: Session = Depends(get_db)) -> list[DataOpsPipeline]:
    return DataOpsMonitorService().list_pipelines(db)


@router.post("/dataops/pipelines/{pipeline_key}/run", response_model=DataOpsPipelineRunRead)
def run_named_dataops_pipeline(
    pipeline_key: str, payload: DataOpsRunRequest, db: Session = Depends(get_db)
) -> DataOpsPipelineRun:
    return _run_dataops_pipeline_for_key(pipeline_key, payload, db)


def _run_dataops_pipeline_for_key(pipeline_key: str, payload: DataOpsRunRequest, db: Session) -> DataOpsPipelineRun:
    service = DataOpsMonitorService()
    pipeline = _dataops_pipeline_or_404(service, db, pipeline_key)
    record_audit_event(
        db,
        "dataops.pipeline_started",
        "DataOps pipeline execution was requested.",
        actor=payload.actor,
        metadata={"pipeline": pipeline.pipeline_key or pipeline.name, "databricks_job_id": pipeline.databricks_job_id},
    )
    run = service.run_pipeline(db, pipeline.pipeline_key or pipeline.name)
    record_audit_event(
        db,
        f"dataops.pipeline_{run.status}",
        f"DataOps pipeline finished with status {run.status}.",
        actor=payload.actor,
        severity="warning" if run.status == "failed" else "info",
        metadata={
            "pipeline": pipeline.pipeline_key or pipeline.name,
            "run_id": run.run_id,
            "business_run_id": run.business_run_id,
            "quality_score": run.quality_score,
            "quarantine_rows": run.quarantine_rows,
        },
    )
    return run


@router.get("/dataops/pipelines/current", response_model=DataOpsCurrentResponse)
def current_dataops_pipeline(db: Session = Depends(get_db)) -> DataOpsCurrentResponse:
    return _current_dataops_pipeline_for_key(DEFAULT_PIPELINE_KEY, db)


@router.get("/dataops/pipelines/{pipeline_key}/current", response_model=DataOpsCurrentResponse)
def current_named_dataops_pipeline(pipeline_key: str, db: Session = Depends(get_db)) -> DataOpsCurrentResponse:
    return _current_dataops_pipeline_for_key(pipeline_key, db)


def _current_dataops_pipeline_for_key(pipeline_key: str, db: Session) -> DataOpsCurrentResponse:
    service = DataOpsMonitorService()
    pipeline = _dataops_pipeline_or_404(service, db, pipeline_key)
    service.sync_running_runs(db, pipeline)
    latest = service.latest_run(db, pipeline.pipeline_key or pipeline.name, sync=False)
    return DataOpsCurrentResponse(pipeline=pipeline, latest_run=latest)


@router.get("/dataops/pipelines/history", response_model=list[DataOpsPipelineRunRead])
def dataops_pipeline_history(db: Session = Depends(get_db)) -> list[DataOpsPipelineRun]:
    return DataOpsMonitorService().history_runs(db, DEFAULT_PIPELINE_KEY)


@router.get("/dataops/pipelines/{pipeline_key}/history", response_model=list[DataOpsPipelineRunRead])
def named_dataops_pipeline_history(pipeline_key: str, db: Session = Depends(get_db)) -> list[DataOpsPipelineRun]:
    service = DataOpsMonitorService()
    pipeline = _dataops_pipeline_or_404(service, db, pipeline_key)
    return service.history_runs(db, pipeline.pipeline_key or pipeline.name)


@router.get("/dataops/pipelines/{pipeline_key}/quality/latest", response_model=list[DataOpsQualityCheckRead])
def latest_named_dataops_quality(pipeline_key: str, db: Session = Depends(get_db)) -> list[DataOpsQualityCheck]:
    service = DataOpsMonitorService()
    pipeline = _dataops_pipeline_or_404(service, db, pipeline_key)
    return service.latest_quality_checks(db, pipeline.pipeline_key or pipeline.name)


@router.get("/dataops/pipelines/{pipeline_key}/quarantine", response_model=list[DataOpsQuarantineEventRead])
def named_dataops_quarantine(pipeline_key: str, db: Session = Depends(get_db)) -> list[DataOpsQuarantineEvent]:
    service = DataOpsMonitorService()
    pipeline = _dataops_pipeline_or_404(service, db, pipeline_key)
    return service.latest_quarantine_events(db, pipeline.pipeline_key or pipeline.name)


@router.get("/dataops/pipelines/{pipeline_key}/assets", response_model=list[DataOpsGeneratedAssetRead])
def named_dataops_assets(pipeline_key: str, db: Session = Depends(get_db)) -> list[DataOpsGeneratedAsset]:
    service = DataOpsMonitorService()
    pipeline = _dataops_pipeline_or_404(service, db, pipeline_key)
    return service.latest_assets(db, pipeline.pipeline_key or pipeline.name)


@router.get("/dataops/pipelines/{run_id}", response_model=DataOpsPipelineRunRead)
def get_dataops_pipeline_run(run_id: str, db: Session = Depends(get_db)) -> DataOpsPipelineRun:
    service = DataOpsMonitorService()
    service.sync_running_runs(db)
    run = db.query(DataOpsPipelineRun).filter(DataOpsPipelineRun.run_id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="DataOps pipeline run not found.")
    service._ensure_run_url(run)
    db.commit()
    return run


@router.get("/dataops/quality/latest", response_model=list[DataOpsQualityCheckRead])
def latest_dataops_quality(db: Session = Depends(get_db)) -> list[DataOpsQualityCheck]:
    return DataOpsMonitorService().latest_quality_checks(db, DEFAULT_PIPELINE_KEY)


@router.get("/dataops/quarantine", response_model=list[DataOpsQuarantineEventRead])
def dataops_quarantine(db: Session = Depends(get_db)) -> list[DataOpsQuarantineEvent]:
    return DataOpsMonitorService().latest_quarantine_events(db, DEFAULT_PIPELINE_KEY)


@router.get("/dataops/assets", response_model=list[DataOpsGeneratedAssetRead])
def dataops_assets(db: Session = Depends(get_db)) -> list[DataOpsGeneratedAsset]:
    return DataOpsMonitorService().latest_assets(db, DEFAULT_PIPELINE_KEY)


def _dataops_pipeline_or_404(service: DataOpsMonitorService, db: Session, pipeline_key: str) -> DataOpsPipeline:
    try:
        return service.ensure_pipeline(db, pipeline_key)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="DataOps pipeline not found.") from exc


@router.post("/autopilot/analyze", response_model=AutopilotReportRead)
def run_autopilot_analysis(payload: AutopilotRunRequest, db: Session = Depends(get_db)) -> AutopilotReport:
    report = AutopilotService().run_analysis(db, actor=payload.actor, include_ai=payload.include_ai)
    record_audit_event(
        db,
        "autopilot.analysis_completed",
        f"Autopilot analysis completed with risk {report.risk_level}.",
        actor=payload.actor,
        severity="warning" if report.risk_level in {"critical", "high"} else "info",
        metadata={"report_id": report.id, "run_id": report.run_id, "score": report.overall_score},
    )
    return report


@router.get("/autopilot/latest", response_model=AutopilotCurrentResponse)
def latest_autopilot_report(db: Session = Depends(get_db)) -> AutopilotCurrentResponse:
    return AutopilotCurrentResponse(latest_report=AutopilotService().latest_report(db))


@router.get("/autopilot/history", response_model=list[AutopilotReportRead])
def autopilot_history(db: Session = Depends(get_db)) -> list[AutopilotReport]:
    return AutopilotService().history(db)


@router.get("/autopilot/reports/{report_id}", response_model=AutopilotReportRead)
def get_autopilot_report(report_id: int, db: Session = Depends(get_db)) -> AutopilotReport:
    report = db.query(AutopilotReport).filter(AutopilotReport.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Autopilot report not found.")
    return report


@router.post("/autopilot/tasks/{task_id}/status", response_model=AutopilotTaskRead)
def update_autopilot_task_status(
    task_id: int,
    payload: AutopilotTaskStatusUpdateRequest,
    db: Session = Depends(get_db),
) -> AutopilotTask:
    task = AutopilotService().update_task_status(db, task_id, payload.status)
    if not task:
        raise HTTPException(status_code=404, detail="Autopilot task not found.")
    record_audit_event(
        db,
        "autopilot.task_status_updated",
        f"Autopilot task changed to {payload.status}.",
        actor=payload.actor,
        metadata={"task_id": task.id, "report_id": task.report_id, "status": payload.status},
    )
    return task


@router.post("/catalog/sync", response_model=CatalogSyncRunRead)
def sync_catalog(payload: CatalogSyncRequest, db: Session = Depends(get_db)) -> CatalogSyncRun:
    service = CatalogGovernanceService()
    sync_run = service.sync_catalog(db)
    record_audit_event(
        db,
        "catalog.synced",
        f"Catalog sync finished with status {sync_run.status}.",
        actor=payload.actor,
        severity="warning" if sync_run.status == "failed" else "info",
        metadata={
            "sync_run_id": sync_run.id,
            "assets_seen": sync_run.assets_seen,
            "assets_created": sync_run.assets_created,
            "assets_updated": sync_run.assets_updated,
        },
    )
    return sync_run


@router.get("/catalog/status", response_model=CatalogStatusResponse)
def catalog_status(db: Session = Depends(get_db)) -> CatalogStatusResponse:
    return CatalogStatusResponse(**CatalogGovernanceService().status(db))


@router.get("/catalog/assets", response_model=list[CatalogAssetRead])
def catalog_assets(db: Session = Depends(get_db)) -> list[CatalogAsset]:
    return db.query(CatalogAsset).order_by(CatalogAsset.layer, CatalogAsset.asset_name).all()


@router.get("/catalog/assets/{asset_id}", response_model=CatalogAssetRead)
def catalog_asset(asset_id: int, db: Session = Depends(get_db)) -> CatalogAsset:
    asset = db.query(CatalogAsset).filter(CatalogAsset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Catalog asset not found.")
    return asset


@router.get("/catalog/assets/{asset_id}/columns", response_model=list[CatalogColumnRead])
def catalog_asset_columns(asset_id: int, db: Session = Depends(get_db)) -> list[CatalogColumn]:
    asset = db.query(CatalogAsset).filter(CatalogAsset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Catalog asset not found.")
    return db.query(CatalogColumn).filter(CatalogColumn.asset_id == asset_id).order_by(CatalogColumn.id).all()


@router.post("/catalog/columns/{column_id}/description", response_model=CatalogColumnRead)
def update_catalog_column_description(
    column_id: int, payload: CatalogColumnDescriptionUpdateRequest, db: Session = Depends(get_db)
) -> CatalogColumn:
    column = db.query(CatalogColumn).filter(CatalogColumn.id == column_id).first()
    if not column:
        raise HTTPException(status_code=404, detail="Catalog column not found.")
    column.description = payload.description.strip() or None
    db.commit()
    db.refresh(column)
    record_audit_event(
        db,
        "catalog.column_documented",
        "Catalog column description updated.",
        actor=payload.actor,
        metadata={"column_id": column.id, "asset_id": column.asset_id, "column_name": column.column_name},
    )
    return column


@router.get("/catalog/lineage", response_model=list[CatalogLineageEdgeRead])
def catalog_lineage(db: Session = Depends(get_db)) -> list[CatalogLineageEdge]:
    return db.query(CatalogLineageEdge).order_by(CatalogLineageEdge.id).all()


@router.get("/catalog/classifications", response_model=list[CatalogClassificationRead])
def catalog_classifications(db: Session = Depends(get_db)) -> list[CatalogClassification]:
    service = CatalogGovernanceService()
    service.ensure_reference_data(db)
    return db.query(CatalogClassification).order_by(CatalogClassification.rank).all()


@router.post("/catalog/assets/{asset_id}/document", response_model=CatalogDocumentResponse)
def document_catalog_asset(asset_id: int, payload: CatalogSyncRequest, db: Session = Depends(get_db)) -> CatalogDocumentResponse:
    asset = db.query(CatalogAsset).filter(CatalogAsset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Catalog asset not found.")
    documentation = CatalogGovernanceService().generate_documentation(db, asset)
    record_audit_event(
        db,
        "catalog.documented",
        "Catalog asset documentation generated.",
        actor=payload.actor,
        metadata={"asset_id": asset.id, "asset_urn": asset.asset_urn},
    )
    return CatalogDocumentResponse(asset=asset, documentation=documentation)


@router.post("/catalog/assets/{asset_id}/owner", response_model=CatalogAssetRead)
def update_catalog_asset_owner(asset_id: int, payload: CatalogOwnerUpdateRequest, db: Session = Depends(get_db)) -> CatalogAsset:
    asset = db.query(CatalogAsset).filter(CatalogAsset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Catalog asset not found.")
    updated = CatalogGovernanceService().update_owner(db, asset, payload.owner)
    record_audit_event(
        db,
        "catalog.owner_updated",
        "Catalog owner updated.",
        actor=payload.actor,
        metadata={"asset_id": updated.id, "owner": updated.owner},
    )
    return updated


@router.post("/catalog/assets/{asset_id}/classification", response_model=CatalogAssetRead)
def update_catalog_asset_classification(
    asset_id: int, payload: CatalogClassificationUpdateRequest, db: Session = Depends(get_db)
) -> CatalogAsset:
    asset = db.query(CatalogAsset).filter(CatalogAsset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Catalog asset not found.")
    updated = CatalogGovernanceService().update_classification(db, asset, payload.classification)
    record_audit_event(
        db,
        "catalog.classification_updated",
        "Catalog classification updated.",
        actor=payload.actor,
        severity="warning" if updated.sensitivity_level in {"confidential", "restricted"} else "info",
        metadata={"asset_id": updated.id, "classification": updated.sensitivity_level},
    )
    return updated


@router.get("/catalog/sync-runs", response_model=list[CatalogSyncRunRead])
def catalog_sync_runs(db: Session = Depends(get_db)) -> list[CatalogSyncRun]:
    return db.query(CatalogSyncRun).order_by(CatalogSyncRun.started_at.desc()).limit(20).all()


def _query_ai_explanation(sql: str, evaluation: dict[str, Any]) -> str:
    try:
        return AIRecommendationService().generate_query_guidance(sql, evaluation)
    except AIConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _dba_ai_summary(profiles: list[dict[str, Any]]) -> str:
    try:
        return AIRecommendationService().generate_dba_recommendations(profiles)
    except AIConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _create_query_review(
    db: Session,
    sql_text: str,
    action: str,
    actor: str,
    evaluation: dict[str, Any],
    ai_explanation: str,
    row_count: int | None = None,
    execution_ms: int | None = None,
) -> QueryReview:
    review = QueryReview(
        sql_text=sql_text,
        action=action,
        decision=evaluation["decision"],
        risk_level=evaluation["risk_level"],
        reasons_json=evaluation["reasons"],
        recommendations_json=evaluation["recommendations"],
        ai_explanation=ai_explanation,
        suggested_sql=evaluation.get("suggested_sql"),
        row_count=row_count,
        execution_ms=execution_ms,
        actor=actor,
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    return review


def _query_analyze_response(review: QueryReview) -> QueryAnalyzeResponse:
    return QueryAnalyzeResponse(
        id=review.id,
        decision=review.decision,
        risk_level=review.risk_level,
        reasons=review.reasons_json,
        recommendations=review.recommendations_json,
        suggested_sql=review.suggested_sql,
        ai_explanation=review.ai_explanation or "",
        created_at=review.created_at,
    )


def _execute_readonly_select(sql: str) -> tuple[list[str], list[dict[str, Any]]]:
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            if engine.dialect.name == "postgresql":
                connection.execute(text("SET TRANSACTION READ ONLY"))
                connection.execute(text("SET LOCAL statement_timeout = 3000"))
            result = connection.execute(text(sql))
            mappings = result.mappings().fetchmany(100)
            columns = list(result.keys())
            rows = [{key: _json_safe(value) for key, value in row.items()} for row in mappings]
            transaction.rollback()
            return columns, rows
        except Exception:
            transaction.rollback()
            raise


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, date | datetime):
        return value.isoformat()
    return value
