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
    DataOpsGeneratedAsset,
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
from app.schemas.dataops import (
    DataOpsCurrentResponse,
    DataOpsGeneratedAssetRead,
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
from app.services.dataops import DataOpsMonitorService
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


@router.post("/dataops/pipelines/run", response_model=DataOpsPipelineRunRead)
def run_dataops_pipeline(payload: DataOpsRunRequest, db: Session = Depends(get_db)) -> DataOpsPipelineRun:
    service = DataOpsMonitorService()
    record_audit_event(
        db,
        "dataops.pipeline_started",
        "DataOps pipeline execution was requested.",
        actor=payload.actor,
        metadata={"pipeline": "tpcds-retail-dataops"},
    )
    run = service.run_pipeline(db)
    record_audit_event(
        db,
        f"dataops.pipeline_{run.status}",
        f"DataOps pipeline finished with status {run.status}.",
        actor=payload.actor,
        severity="warning" if run.status == "failed" else "info",
        metadata={"run_id": run.run_id, "quality_score": run.quality_score, "quarantine_rows": run.quarantine_rows},
    )
    return run


@router.get("/dataops/pipelines/current", response_model=DataOpsCurrentResponse)
def current_dataops_pipeline(db: Session = Depends(get_db)) -> DataOpsCurrentResponse:
    service = DataOpsMonitorService()
    pipeline = service.ensure_pipeline(db)
    service.sync_running_runs(db, pipeline)
    latest = service.latest_run(db)
    return DataOpsCurrentResponse(pipeline=pipeline, latest_run=latest)


@router.get("/dataops/pipelines/history", response_model=list[DataOpsPipelineRunRead])
def dataops_pipeline_history(db: Session = Depends(get_db)) -> list[DataOpsPipelineRun]:
    DataOpsMonitorService().sync_running_runs(db)
    return db.query(DataOpsPipelineRun).order_by(DataOpsPipelineRun.created_at.desc()).limit(20).all()


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
    latest = DataOpsMonitorService().latest_run(db)
    if not latest:
        return []
    return db.query(DataOpsQualityCheck).filter(DataOpsQualityCheck.run_id == latest.run_id).order_by(DataOpsQualityCheck.id).all()


@router.get("/dataops/quarantine", response_model=list[DataOpsQuarantineEventRead])
def dataops_quarantine(db: Session = Depends(get_db)) -> list[DataOpsQuarantineEvent]:
    DataOpsMonitorService().sync_running_runs(db)
    return db.query(DataOpsQuarantineEvent).order_by(DataOpsQuarantineEvent.created_at.desc()).limit(30).all()


@router.get("/dataops/assets", response_model=list[DataOpsGeneratedAssetRead])
def dataops_assets(db: Session = Depends(get_db)) -> list[DataOpsGeneratedAsset]:
    DataOpsMonitorService().sync_running_runs(db)
    return db.query(DataOpsGeneratedAsset).order_by(DataOpsGeneratedAsset.created_at.desc()).limit(50).all()


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
