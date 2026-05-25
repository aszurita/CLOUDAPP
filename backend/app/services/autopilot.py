from __future__ import annotations

import json
from datetime import datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    AuditEvent,
    AutopilotReport,
    AutopilotTask,
    CatalogAsset,
    CatalogColumn,
    CatalogLineageEdge,
    CatalogSyncRun,
    DataOpsPipeline,
    DataOpsPipelineRun,
    DataOpsQualityCheck,
    DbaRecommendation,
    DbaTableProfile,
    Deployment,
    Environment,
    QueryReview,
    Service,
)
from app.services.ai import AIConfigurationError, AIRecommendationService


SEVERITY_WEIGHT = {
    "critical": 20,
    "high": 13,
    "medium": 7,
    "low": 3,
    "info": 0,
}


class AutopilotService:
    def run_analysis(self, db: Session, actor: str = "demo-user", include_ai: bool = True) -> AutopilotReport:
        context = self._collect_context(db)
        findings = self._build_findings(context)
        metrics = self._build_metrics(context, findings)
        score = self._score(findings, metrics)
        risk_level = self._risk_level(score, findings)
        remediation_plan = self._remediation_plan(findings)
        infra_suggestions = self._infra_suggestions(context, findings)
        summary = self._summary(score, risk_level, findings, metrics)
        ai_summary = self._ai_summary(context, findings, remediation_plan) if include_ai and get_settings().ai_configured else None

        report = AutopilotReport(
            run_id=f"autopilot-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:6]}",
            status="success",
            overall_score=score,
            risk_level=risk_level,
            summary=summary,
            metrics_json=metrics,
            findings_json=findings,
            remediation_plan_json=remediation_plan,
            infra_suggestions_json=infra_suggestions,
            ai_summary=ai_summary,
            raw_context_json=context,
        )
        db.add(report)
        db.flush()

        for task in self._tasks_from_findings(findings):
            db.add(AutopilotTask(report_id=report.id, **task))

        db.commit()
        db.refresh(report)
        return report

    def latest_report(self, db: Session) -> AutopilotReport | None:
        return db.query(AutopilotReport).order_by(AutopilotReport.created_at.desc()).first()

    def history(self, db: Session, limit: int = 12) -> list[AutopilotReport]:
        return db.query(AutopilotReport).order_by(AutopilotReport.created_at.desc()).limit(limit).all()

    def update_task_status(self, db: Session, task_id: int, status: str) -> AutopilotTask | None:
        task = db.query(AutopilotTask).filter(AutopilotTask.id == task_id).first()
        if not task:
            return None
        task.status = status
        db.commit()
        db.refresh(task)
        return task

    def _collect_context(self, db: Session) -> dict:
        services = db.query(Service).order_by(Service.id).all()
        environments = db.query(Environment).order_by(Environment.id).all()
        deployments = db.query(Deployment).order_by(Deployment.deployed_at.desc()).limit(10).all()
        query_reviews = db.query(QueryReview).order_by(QueryReview.created_at.desc()).limit(50).all()
        dba_profiles = db.query(DbaTableProfile).order_by(DbaTableProfile.created_at.desc()).limit(30).all()
        dba_recommendations = db.query(DbaRecommendation).order_by(DbaRecommendation.created_at.desc()).limit(20).all()
        catalog_assets = db.query(CatalogAsset).order_by(CatalogAsset.updated_at.desc()).limit(80).all()
        latest_catalog_sync = db.query(CatalogSyncRun).order_by(CatalogSyncRun.started_at.desc()).first()
        pipelines = db.query(DataOpsPipeline).order_by(DataOpsPipeline.id).all()
        dataops_runs = []
        for pipeline in pipelines:
            latest_run = (
                db.query(DataOpsPipelineRun)
                .filter(DataOpsPipelineRun.pipeline_id == pipeline.id)
                .order_by(DataOpsPipelineRun.created_at.desc())
                .first()
            )
            failed_checks = (
                db.query(DataOpsQualityCheck)
                .filter(DataOpsQualityCheck.run_id == latest_run.run_id, DataOpsQualityCheck.status != "passed")
                .count()
                if latest_run
                else 0
            )
            dataops_runs.append(
                {
                    "pipeline": pipeline.name,
                    "pipeline_key": pipeline.pipeline_key,
                    "pipeline_type": pipeline.pipeline_type,
                    "status": latest_run.status if latest_run else pipeline.status,
                    "quality_score": latest_run.quality_score if latest_run else None,
                    "quarantine_rows": latest_run.quarantine_rows if latest_run else 0,
                    "gold_rows": latest_run.gold_rows if latest_run else 0,
                    "failed_checks": failed_checks,
                    "created_at": latest_run.created_at.isoformat() if latest_run else None,
                }
            )

        sensitive_columns = db.query(CatalogColumn).filter(CatalogColumn.is_sensitive.is_(True)).count()
        restricted_assets = db.query(CatalogAsset).filter(CatalogAsset.sensitivity_level == "restricted").count()
        undocumented_assets = (
            db.query(CatalogAsset)
            .filter((CatalogAsset.description.is_(None)) | (CatalogAsset.documentation_status != "generated"))
            .count()
        )
        lineage_edges = db.query(CatalogLineageEdge).count()
        audit_warnings = db.query(AuditEvent).filter(AuditEvent.severity.in_(["warning", "critical"])).count()
        blocked_queries = sum(1 for review in query_reviews if review.decision == "blocked")
        approved_queries = sum(1 for review in query_reviews if review.decision == "approved")

        return {
            "platform": {
                "services_total": len(services),
                "services_unhealthy": [service.name for service in services if service.status != "healthy"],
                "environments_attention": [env.code for env in environments if env.status != "healthy"],
                "deployments_failed": [deployment.commit_sha for deployment in deployments if deployment.status != "success"],
                "monthly_cost_estimate_usd": sum(service.cost_estimate_usd for service in services),
            },
            "query_governance": {
                "reviews_sampled": len(query_reviews),
                "blocked_queries": blocked_queries,
                "approved_queries": approved_queries,
                "latest_blocked_reasons": _latest_items(
                    [reason for review in query_reviews if review.decision == "blocked" for reason in review.reasons_json],
                    limit=5,
                ),
            },
            "dba": {
                "profiles_total": len(dba_profiles),
                "high_risk_profiles": [profile.table_name for profile in dba_profiles if profile.risk_level in {"high", "blocked"}],
                "recommendations_high": [
                    recommendation.title
                    for recommendation in dba_recommendations
                    if recommendation.severity in {"critical", "high"}
                ],
            },
            "dataops": {
                "pipelines_total": len(pipelines),
                "latest_runs": dataops_runs,
            },
            "catalog": {
                "assets_total": db.query(CatalogAsset).count(),
                "restricted_assets": restricted_assets,
                "sensitive_columns": sensitive_columns,
                "undocumented_assets": undocumented_assets,
                "lineage_edges": lineage_edges,
                "latest_sync_status": latest_catalog_sync.status if latest_catalog_sync else None,
                "latest_sync_started_at": latest_catalog_sync.started_at.isoformat() if latest_catalog_sync else None,
            },
            "audit": {
                "warning_events": audit_warnings,
            },
        }

    def _build_findings(self, context: dict) -> list[dict]:
        findings: list[dict] = []
        platform = context["platform"]
        if platform["services_unhealthy"]:
            findings.append(
                _finding(
                    "platform",
                    "high",
                    "Servicios requieren atencion operativa",
                    f"{len(platform['services_unhealthy'])} servicio(s) no estan healthy.",
                    platform["services_unhealthy"],
                    ["Revisar health checks y logs.", "Crear alerta de disponibilidad.", "Validar version desplegada."],
                )
            )
        if platform["environments_attention"]:
            findings.append(
                _finding(
                    "platform",
                    "medium",
                    "Ambientes con estado de atencion",
                    "Hay ambientes activos que no reportan healthy.",
                    platform["environments_attention"],
                    ["Confirmar ventanas de mantenimiento.", "Verificar recursos y secretos por ambiente."],
                )
            )
        if platform["deployments_failed"]:
            findings.append(
                _finding(
                    "devops",
                    "high",
                    "Despliegues recientes con fallo",
                    "El historial reciente contiene despliegues no exitosos.",
                    platform["deployments_failed"],
                    ["Revisar logs de CI/CD.", "Bloquear promocion a PROD hasta validar rollback."],
                )
            )

        query = context["query_governance"]
        if query["blocked_queries"] > 0:
            severity = "high" if query["blocked_queries"] >= 3 else "medium"
            findings.append(
                _finding(
                    "query-governance",
                    severity,
                    "Consultas riesgosas bloqueadas",
                    f"{query['blocked_queries']} consulta(s) fueron bloqueadas por gobierno.",
                    query["latest_blocked_reasons"],
                    ["Reforzar patrones SQL seguros.", "Documentar columnas sensibles consultadas.", "Revisar usuarios recurrentes."],
                )
            )

        dba = context["dba"]
        if dba["high_risk_profiles"]:
            findings.append(
                _finding(
                    "dba",
                    "high",
                    "Tablas con riesgo DBA alto",
                    "Perfiles de base contienen tablas marcadas como high/blocked.",
                    dba["high_risk_profiles"],
                    ["Aplicar indices recomendados.", "Revisar mascaramiento y retencion.", "Priorizar recomendaciones DBA high."],
                )
            )
        if dba["recommendations_high"]:
            findings.append(
                _finding(
                    "dba",
                    "medium",
                    "Recomendaciones DBA pendientes",
                    "Hay recomendaciones de severidad alta listas para ejecutar.",
                    dba["recommendations_high"][:5],
                    ["Convertir recomendaciones en backlog tecnico.", "Asignar owner y fecha objetivo."],
                )
            )

        for run in context["dataops"]["latest_runs"]:
            if run["status"] == "failed":
                findings.append(
                    _finding(
                        "dataops",
                        "critical",
                        f"Pipeline fallido: {run['pipeline']}",
                        "La ultima corrida del pipeline fallo.",
                        [run],
                        ["Abrir salida del job.", "Reprocesar solo cuando reglas de calidad esten controladas."],
                    )
                )
            elif run["status"] == "running":
                findings.append(
                    _finding(
                        "dataops",
                        "medium",
                        f"Pipeline en ejecucion: {run['pipeline']}",
                        "Hay una corrida activa que debe seguirse hasta cierre.",
                        [run],
                        ["Monitorear Databricks.", "Validar que la corrida publique resumen al finalizar."],
                    )
                )
            if run["quality_score"] is not None and run["quality_score"] < 95:
                findings.append(
                    _finding(
                        "dataops",
                        "high",
                        f"Calidad debajo del umbral: {run['pipeline']}",
                        f"Quality score actual: {run['quality_score']}.",
                        [run],
                        ["Revisar reglas fallidas.", "Aislar registros invalidos.", "Actualizar data owner."],
                    )
                )
            if run["quarantine_rows"] > 0:
                findings.append(
                    _finding(
                        "dataops",
                        "medium",
                        f"Quarantine activo: {run['pipeline']}",
                        f"{run['quarantine_rows']} registros aislados en la ultima corrida.",
                        [run],
                        ["Revisar causas de quarantine.", "Confirmar si el patron es recurrente."],
                    )
                )

        catalog = context["catalog"]
        if catalog["latest_sync_status"] == "failed":
            findings.append(
                _finding(
                    "catalog",
                    "high",
                    "Sincronizacion de catalogo fallida",
                    "El ultimo sync de catalogo termino en failed.",
                    [catalog],
                    ["Revisar DataHub/Purview o fallback interno.", "Reintentar sync despues de validar conectividad."],
                )
            )
        if catalog["undocumented_assets"] > 0:
            findings.append(
                _finding(
                    "catalog",
                    "medium",
                    "Activos sin documentacion completa",
                    f"{catalog['undocumented_assets']} activo(s) requieren documentacion o validacion de owner.",
                    [catalog],
                    ["Ejecutar Generate Documentation.", "Asignar steward de negocio."],
                )
            )
        if catalog["sensitive_columns"] > 0 or catalog["restricted_assets"] > 0:
            findings.append(
                _finding(
                    "governance",
                    "medium",
                    "Datos sensibles detectados",
                    "El catalogo contiene columnas o activos restringidos que requieren control operativo.",
                    [catalog],
                    ["Validar clasificacion restricted.", "Confirmar access path y auditoria.", "Documentar politica de uso."],
                )
            )
        if catalog["assets_total"] > 0 and catalog["lineage_edges"] == 0:
            findings.append(
                _finding(
                    "catalog",
                    "medium",
                    "Lineage incompleto",
                    "Hay activos catalogados sin linaje visible.",
                    [catalog],
                    ["Sincronizar linaje.", "Registrar transformaciones criticas."],
                )
            )

        if not findings:
            findings.append(
                _finding(
                    "operations",
                    "info",
                    "Plataforma estable",
                    "No se detectaron riesgos altos con las senales disponibles.",
                    [],
                    ["Mantener monitoreo y ejecutar Autopilot despues de cada corrida critica."],
                )
            )
        return findings

    def _build_metrics(self, context: dict, findings: list[dict]) -> dict:
        severities = {severity: sum(1 for finding in findings if finding["severity"] == severity) for severity in SEVERITY_WEIGHT}
        return {
            "findings_total": len(findings),
            "critical_findings": severities["critical"],
            "high_findings": severities["high"],
            "medium_findings": severities["medium"],
            "open_tasks": len([finding for finding in findings if finding["severity"] != "info"]),
            "services_total": context["platform"]["services_total"],
            "data_pipelines": context["dataops"]["pipelines_total"],
            "catalog_assets": context["catalog"]["assets_total"],
            "sensitive_columns": context["catalog"]["sensitive_columns"],
            "blocked_queries": context["query_governance"]["blocked_queries"],
            "lineage_edges": context["catalog"]["lineage_edges"],
        }

    def _score(self, findings: list[dict], metrics: dict) -> float:
        penalty = sum(SEVERITY_WEIGHT.get(finding["severity"], 0) for finding in findings)
        if metrics["sensitive_columns"] and metrics["catalog_assets"] == 0:
            penalty += 10
        score = max(0, min(100, 100 - penalty))
        return float(score)

    def _risk_level(self, score: float, findings: list[dict]) -> str:
        if any(finding["severity"] == "critical" for finding in findings) or score <= 55:
            return "critical"
        if score <= 72 or any(finding["severity"] == "high" for finding in findings):
            return "high"
        if score <= 86 or any(finding["severity"] == "medium" for finding in findings):
            return "medium"
        return "low"

    def _summary(self, score: float, risk_level: str, findings: list[dict], metrics: dict) -> str:
        top = [finding["title"] for finding in findings if finding["severity"] in {"critical", "high"}][:3]
        if top:
            focus = "; ".join(top)
            return f"Autopilot score {score}/100 con riesgo {risk_level}. Prioridad inmediata: {focus}."
        return (
            f"Autopilot score {score}/100 con riesgo {risk_level}. "
            f"Se analizaron {metrics['services_total']} servicios, {metrics['data_pipelines']} pipelines y "
            f"{metrics['catalog_assets']} activos catalogados."
        )

    def _remediation_plan(self, findings: list[dict]) -> list[dict]:
        plan = []
        for index, finding in enumerate(findings, start=1):
            if finding["severity"] == "info":
                continue
            plan.append(
                {
                    "step": index,
                    "priority": _task_priority(finding["severity"]),
                    "category": finding["category"],
                    "title": finding["title"],
                    "recommended_actions": finding["actions"],
                    "expected_outcome": _expected_outcome(finding["category"]),
                }
            )
        return plan

    def _infra_suggestions(self, context: dict, findings: list[dict]) -> list[dict]:
        suggestions = [
            {
                "area": "observability",
                "title": "Centralizar alertas operativas",
                "suggestion": "Crear alertas para health checks, pipelines DataOps y sync de catalogo en Azure Monitor.",
                "impact": "Menos tiempo entre deteccion y respuesta.",
            },
            {
                "area": "governance",
                "title": "Backlog automatico de gobierno",
                "suggestion": "Convertir tareas Autopilot en issues de GitHub/Azure DevOps con owner y prioridad.",
                "impact": "Cierra el ciclo entre hallazgo y remediacion.",
            },
        ]
        if context["catalog"]["restricted_assets"] or context["catalog"]["sensitive_columns"]:
            suggestions.append(
                {
                    "area": "security",
                    "title": "Control de acceso para activos restricted",
                    "suggestion": "Preparar grupos Entra ID y politicas de acceso por dominio/owner para activos restringidos.",
                    "impact": "Reduce exposicion de datos sensibles.",
                }
            )
        if any(finding["category"] == "dataops" for finding in findings):
            suggestions.append(
                {
                    "area": "dataops",
                    "title": "Estandarizar salida de jobs",
                    "suggestion": "Exigir resumen JSON por job con run_id, metricas, tablas publicadas y eventos operativos.",
                    "impact": "Hace que cada nuevo job aparezca correctamente en el monitor.",
                }
            )
        return suggestions

    def _tasks_from_findings(self, findings: list[dict]) -> list[dict]:
        tasks = []
        for finding in findings:
            if finding["severity"] == "info":
                continue
            tasks.append(
                {
                    "title": finding["title"],
                    "priority": _task_priority(finding["severity"]),
                    "category": finding["category"],
                    "status": "open",
                    "owner": _owner_for_category(finding["category"]),
                    "source": finding["source"],
                    "due_hint": _due_hint(finding["severity"]),
                    "action_json": {
                        "description": finding["description"],
                        "actions": finding["actions"],
                        "evidence": finding["evidence"],
                    },
                }
            )
        return tasks

    def _ai_summary(self, context: dict, findings: list[dict], remediation_plan: list[dict]) -> str | None:
        try:
            return AIRecommendationService().generate_autopilot_summary(
                {
                    "context": context,
                    "findings": findings,
                    "remediation_plan": remediation_plan,
                }
            )
        except AIConfigurationError:
            return None


def _finding(category: str, severity: str, title: str, description: str, evidence: list, actions: list[str]) -> dict:
    return {
        "category": category,
        "severity": severity,
        "title": title,
        "description": description,
        "evidence": _json_safe(evidence),
        "actions": actions,
        "source": f"autopilot.{category}",
    }


def _latest_items(items: list[str], limit: int) -> list[str]:
    seen = []
    for item in items:
        if item not in seen:
            seen.append(item)
        if len(seen) >= limit:
            break
    return seen


def _json_safe(value):
    return json.loads(json.dumps(value, default=str))


def _task_priority(severity: str) -> str:
    if severity == "critical":
        return "p0"
    if severity == "high":
        return "p1"
    if severity == "medium":
        return "p2"
    return "p3"


def _due_hint(severity: str) -> str:
    if severity == "critical":
        return "hoy"
    if severity == "high":
        return "24-48h"
    if severity == "medium":
        return "esta semana"
    return "backlog"


def _owner_for_category(category: str) -> str:
    owners = {
        "platform": "platform-team",
        "devops": "platform-team",
        "query-governance": "data-governance-team",
        "dba": "dba-team",
        "dataops": "data-platform-team",
        "catalog": "data-governance-team",
        "governance": "data-governance-team",
    }
    return owners.get(category, "data-platform-team")


def _expected_outcome(category: str) -> str:
    outcomes = {
        "platform": "Servicios estables y alertas operativas activas.",
        "devops": "Pipeline CI/CD confiable antes de promocionar cambios.",
        "query-governance": "Menos consultas bloqueadas y patron SQL seguro documentado.",
        "dba": "Menor riesgo de rendimiento, seguridad y crecimiento no controlado.",
        "dataops": "Pipelines trazables con calidad monitoreada y salida operativa clara.",
        "catalog": "Activos documentados, clasificados y con linaje visible.",
        "governance": "Controles claros sobre datos restricted y columnas sensibles.",
    }
    return outcomes.get(category, "Riesgo operativo reducido.")
