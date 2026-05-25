from __future__ import annotations

import json
import re
from datetime import datetime
from time import perf_counter
from uuid import uuid4

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    DataOpsGeneratedAsset,
    DataOpsPipeline,
    DataOpsPipelineRun,
    DataOpsQualityCheck,
    DataOpsQuarantineEvent,
)
from app.services.ai import AIConfigurationError, AIRecommendationService


PIPELINE_NAME = "tpcds-retail-dataops"


class DatabricksConfigurationError(RuntimeError):
    pass


class DataOpsMonitorService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def ensure_pipeline(self, db: Session) -> DataOpsPipeline:
        pipeline = db.query(DataOpsPipeline).filter(DataOpsPipeline.name == PIPELINE_NAME).first()
        if pipeline:
            return pipeline
        pipeline = DataOpsPipeline(
            name=PIPELINE_NAME,
            description="TPC-DS retail DataOps flow: Bronze -> Silver -> Gold with quality checks and quarantine.",
            databricks_job_id=self.settings.databricks_job_id,
            status="idle",
        )
        db.add(pipeline)
        db.commit()
        db.refresh(pipeline)
        return pipeline

    def run_pipeline(self, db: Session) -> DataOpsPipelineRun:
        pipeline = self.ensure_pipeline(db)
        started = perf_counter()

        if self._databricks_configured():
            summary = self._start_databricks_job()
            summary.setdefault("duration_ms", round((perf_counter() - started) * 1000))
        else:
            summary = self._demo_run_summary(round((perf_counter() - started) * 1000))

        run = self._persist_summary(db, pipeline, summary)
        pipeline.status = run.status
        db.commit()
        db.refresh(run)
        return run

    def latest_run(self, db: Session) -> DataOpsPipelineRun | None:
        pipeline = self.ensure_pipeline(db)
        self.sync_running_runs(db, pipeline)
        run = (
            db.query(DataOpsPipelineRun)
            .filter(DataOpsPipelineRun.pipeline_id == pipeline.id)
            .order_by(DataOpsPipelineRun.created_at.desc())
            .first()
        )
        if run:
            self._ensure_run_url(run)
            db.commit()
        return run

    def sync_running_runs(self, db: Session, pipeline: DataOpsPipeline | None = None) -> None:
        if not self._databricks_configured():
            return
        pipeline = pipeline or self.ensure_pipeline(db)
        running_runs = (
            db.query(DataOpsPipelineRun)
            .filter(DataOpsPipelineRun.pipeline_id == pipeline.id, DataOpsPipelineRun.status == "running")
            .order_by(DataOpsPipelineRun.created_at.desc())
            .limit(5)
            .all()
        )
        for run in running_runs:
            summary = self._databricks_summary_for_run(run)
            if not summary:
                continue
            self._update_run_from_summary(db, run, summary)
            self._ensure_run_url(run)
            pipeline.status = run.status
        db.commit()

    def _databricks_configured(self) -> bool:
        return bool(self.settings.databricks_host and self.settings.databricks_token and self.settings.databricks_job_id)

    def _start_databricks_job(self) -> dict:
        if not self._databricks_configured():
            raise DatabricksConfigurationError("Configure DATABRICKS_HOST, DATABRICKS_TOKEN and DATABRICKS_JOB_ID.")

        host = str(self.settings.databricks_host).rstrip("/")
        response = httpx.post(
            f"{host}/api/2.1/jobs/run-now",
            headers={"Authorization": f"Bearer {self.settings.databricks_token}"},
            json={
                "job_id": int(str(self.settings.databricks_job_id)),
                "notebook_params": {
                    "catalog": self.settings.databricks_catalog,
                    "bronze_schema": self.settings.databricks_schema_bronze,
                    "silver_schema": self.settings.databricks_schema_silver,
                    "gold_schema": self.settings.databricks_schema_gold,
                },
            },
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        run_id = str(payload.get("run_id") or uuid4())
        run_url = payload.get("run_page_url") or self._build_run_url(run_id)
        return {
            "pipeline_name": PIPELINE_NAME,
            "run_id": run_id,
            "status": "running",
            "bronze_rows": 0,
            "silver_rows": 0,
            "gold_rows": 0,
            "quality_score": 0,
            "quarantine_rows": 0,
            "duration_ms": 0,
            "generated_tables": [],
            "failed_rules": [],
            "databricks_run_url": run_url,
            "quality_checks": [],
            "assets": [],
            "quarantine_preview": [],
        }

    def _databricks_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.settings.databricks_token}"}

    def _databricks_summary_for_run(self, run: DataOpsPipelineRun) -> dict | None:
        host = str(self.settings.databricks_host).rstrip("/")
        response = httpx.get(
            f"{host}/api/2.1/jobs/runs/get",
            headers=self._databricks_headers(),
            params={"run_id": run.run_id},
            timeout=20,
        )
        response.raise_for_status()
        run_info = response.json()
        state = run_info.get("state", {})
        life_cycle = state.get("life_cycle_state")
        if life_cycle not in {"TERMINATED", "SKIPPED", "INTERNAL_ERROR"}:
            return None

        result_state = state.get("result_state")
        if result_state == "SUCCESS":
            return self._read_summary_notebook_output(host, run_info) or self._terminal_metadata_summary(run, run_info, "success")
        return self._terminal_metadata_summary(run, run_info, "failed")

    def _read_summary_notebook_output(self, host: str, run_info: dict) -> dict | None:
        tasks = run_info.get("tasks") or []
        preferred = [
            task for task in tasks
            if "05" in str(task.get("task_key", "")).lower() or "summary" in str(task.get("task_key", "")).lower()
        ]
        candidates = preferred or list(reversed(tasks))
        for task in candidates:
            task_run_id = task.get("run_id")
            if not task_run_id:
                continue
            response = httpx.get(
                f"{host}/api/2.1/jobs/runs/get-output",
                headers=self._databricks_headers(),
                params={"run_id": task_run_id},
                timeout=20,
            )
            if response.status_code >= 400:
                continue
            result = (response.json().get("notebook_output") or {}).get("result")
            parsed = _parse_json_result(result)
            if parsed:
                parsed.setdefault("pipeline_name", PIPELINE_NAME)
                parsed.setdefault("run_id", str(run_info.get("run_id")))
                parsed.setdefault("databricks_run_url", run_info.get("run_page_url"))
                return parsed
        return None

    def _terminal_metadata_summary(self, run: DataOpsPipelineRun, run_info: dict, status: str) -> dict:
        start_ms = run_info.get("start_time") or 0
        end_ms = run_info.get("end_time") or start_ms
        return {
            "pipeline_name": PIPELINE_NAME,
            "run_id": run.run_id,
            "status": status,
            "bronze_rows": run.bronze_rows,
            "silver_rows": run.silver_rows,
            "gold_rows": run.gold_rows,
            "quality_score": run.quality_score,
            "quarantine_rows": run.quarantine_rows,
            "duration_ms": int(max(0, end_ms - start_ms)),
            "generated_tables": run.generated_tables_json,
            "failed_rules": run.failed_rules_json,
            "databricks_run_url": run_info.get("run_page_url") or run.databricks_run_url or self._build_run_url(run.run_id),
            "quality_checks": [],
            "assets": [],
            "quarantine_preview": [],
        }

    def _demo_run_summary(self, duration_ms: int) -> dict:
        run_id = f"demo-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:6]}"
        failed_rules = [
            {
                "rule_code": "quantity_positive",
                "layer": "silver",
                "failed_rows": 460,
                "description": "Store sales rows with quantity <= 0 were sent to quarantine.",
            },
            {
                "rule_code": "sales_price_non_negative",
                "layer": "silver",
                "failed_rows": 594,
                "description": "Store sales rows with negative sales price were isolated.",
            },
        ]
        return {
            "pipeline_name": PIPELINE_NAME,
            "run_id": run_id,
            "status": "success",
            "bronze_rows": 2880404,
            "silver_rows": 2879350,
            "gold_rows": 1820,
            "quality_score": 99.96,
            "quarantine_rows": 1054,
            "duration_ms": max(duration_ms, 1280),
            "generated_tables": [
                "databricks_proyectobg.tpcds_bronze.store_sales",
                "databricks_proyectobg.tpcds_bronze.date_dim",
                "databricks_proyectobg.tpcds_bronze.item",
                "databricks_proyectobg.tpcds_bronze.store",
                "databricks_proyectobg.tpcds_silver.store_sales_clean",
                "databricks_proyectobg.tpcds_silver.quarantine_store_sales",
                "databricks_proyectobg.tpcds_gold.sales_by_year_category",
                "databricks_proyectobg.tpcds_gold.sales_by_store",
            ],
            "failed_rules": failed_rules,
            "databricks_run_url": "local-demo://databricks/tpcds-retail-dataops",
            "quality_checks": [
                {"rule_code": "sold_date_not_null", "layer": "silver", "status": "passed", "failed_rows": 0, "description": "ss_sold_date_sk is present."},
                {"rule_code": "item_not_null", "layer": "silver", "status": "passed", "failed_rows": 0, "description": "ss_item_sk is present."},
                {"rule_code": "quantity_positive", "layer": "silver", "status": "failed", "failed_rows": 460, "description": "ss_quantity must be greater than zero."},
                {"rule_code": "sales_price_non_negative", "layer": "silver", "status": "failed", "failed_rows": 594, "description": "ss_sales_price must be greater than or equal to zero."},
                {"rule_code": "referential_integrity_item_store_date", "layer": "silver", "status": "passed", "failed_rows": 0, "description": "Sales rows must match date, item and store dimensions."},
                {"rule_code": "ticket_item_deduplication", "layer": "silver", "status": "passed", "failed_rows": 0, "description": "Duplicate ticket/item combinations are controlled."},
            ],
            "assets": [
                {"layer": "bronze", "asset_name": "store_sales", "row_count": 2880404, "storage_path": "databricks_proyectobg.tpcds_bronze.store_sales"},
                {"layer": "bronze", "asset_name": "date_dim", "row_count": 73049, "storage_path": "databricks_proyectobg.tpcds_bronze.date_dim"},
                {"layer": "silver", "asset_name": "store_sales_clean", "row_count": 2879350, "storage_path": "databricks_proyectobg.tpcds_silver.store_sales_clean"},
                {"layer": "silver", "asset_name": "quarantine_store_sales", "row_count": 1054, "storage_path": "databricks_proyectobg.tpcds_silver.quarantine_store_sales"},
                {"layer": "gold", "asset_name": "sales_by_year_category", "row_count": 1820, "storage_path": "databricks_proyectobg.tpcds_gold.sales_by_year_category"},
                {"layer": "gold", "asset_name": "sales_by_store", "row_count": 1440, "storage_path": "databricks_proyectobg.tpcds_gold.sales_by_store"},
            ],
            "quarantine_preview": [
                {
                    "rule_code": "quantity_positive",
                    "reason": "ss_quantity must be greater than zero.",
                    "source_file": "store_sales",
                    "record_ref": "ticket:704212 item:11894",
                    "preview": {"ss_ticket_number": "704212", "ss_item_sk": "11894", "ss_quantity": 0},
                },
                {
                    "rule_code": "sales_price_non_negative",
                    "reason": "ss_sales_price must be greater than or equal to zero.",
                    "source_file": "store_sales",
                    "record_ref": "ticket:884512 item:3321",
                    "preview": {"ss_ticket_number": "884512", "ss_item_sk": "3321", "ss_sales_price": -1.0},
                },
            ],
        }

    def _persist_summary(self, db: Session, pipeline: DataOpsPipeline, summary: dict) -> DataOpsPipelineRun:
        run = DataOpsPipelineRun(
            pipeline_id=pipeline.id,
            run_id=str(summary["run_id"]),
            status=str(summary["status"]),
            bronze_rows=int(summary.get("bronze_rows", 0)),
            silver_rows=int(summary.get("silver_rows", 0)),
            gold_rows=int(summary.get("gold_rows", 0)),
            quality_score=float(summary.get("quality_score", 0)),
            quarantine_rows=int(summary.get("quarantine_rows", 0)),
            duration_ms=int(summary.get("duration_ms", 0)),
            failed_rules_json=list(summary.get("failed_rules", [])),
            generated_tables_json=list(summary.get("generated_tables", [])),
            databricks_run_url=self._summary_run_url(summary, str(summary["run_id"])),
            raw_summary_json=summary,
            ai_summary=self._ai_summary_if_needed(summary),
            finished_at=datetime.utcnow() if summary.get("status") in {"success", "warning", "failed"} else None,
        )
        db.add(run)
        db.flush()

        for check in summary.get("quality_checks", []):
            db.add(
                DataOpsQualityCheck(
                    run_id=run.run_id,
                    rule_code=check["rule_code"],
                    layer=check["layer"],
                    status=check["status"],
                    failed_rows=int(check.get("failed_rows", 0)),
                    description=check["description"],
                )
            )
        for asset in summary.get("assets", []):
            db.add(
                DataOpsGeneratedAsset(
                    run_id=run.run_id,
                    layer=asset["layer"],
                    asset_name=asset["asset_name"],
                    row_count=int(asset.get("row_count", 0)),
                    storage_path=asset.get("storage_path"),
                )
            )
        for event in summary.get("quarantine_preview", []):
            db.add(
                DataOpsQuarantineEvent(
                    run_id=run.run_id,
                    rule_code=event["rule_code"],
                    reason=event["reason"],
                    source_file=event.get("source_file"),
                    record_ref=event.get("record_ref"),
                    preview_json=event.get("preview", {}),
                )
            )
        self._ensure_run_url(run)
        db.commit()
        return run

    def _update_run_from_summary(self, db: Session, run: DataOpsPipelineRun, summary: dict) -> None:
        run.status = str(summary.get("status", run.status))
        run.bronze_rows = int(summary.get("bronze_rows", run.bronze_rows))
        run.silver_rows = int(summary.get("silver_rows", run.silver_rows))
        run.gold_rows = int(summary.get("gold_rows", run.gold_rows))
        run.quality_score = float(summary.get("quality_score", run.quality_score))
        run.quarantine_rows = int(summary.get("quarantine_rows", run.quarantine_rows))
        run.duration_ms = int(summary.get("duration_ms", run.duration_ms))
        run.failed_rules_json = list(summary.get("failed_rules", run.failed_rules_json))
        run.generated_tables_json = list(summary.get("generated_tables", run.generated_tables_json))
        run.databricks_run_url = self._summary_run_url(summary, run.run_id) or run.databricks_run_url
        run.raw_summary_json = summary
        run.ai_summary = self._ai_summary_if_needed(summary)
        run.finished_at = datetime.utcnow() if run.status in {"success", "warning", "failed"} else None

        db.query(DataOpsQualityCheck).filter(DataOpsQualityCheck.run_id == run.run_id).delete()
        db.query(DataOpsGeneratedAsset).filter(DataOpsGeneratedAsset.run_id == run.run_id).delete()
        db.query(DataOpsQuarantineEvent).filter(DataOpsQuarantineEvent.run_id == run.run_id).delete()

        for check in summary.get("quality_checks", []):
            db.add(
                DataOpsQualityCheck(
                    run_id=run.run_id,
                    rule_code=check["rule_code"],
                    layer=check["layer"],
                    status=check["status"],
                    failed_rows=int(check.get("failed_rows", 0)),
                    description=check["description"],
                )
            )
        for asset in summary.get("assets", []):
            db.add(
                DataOpsGeneratedAsset(
                    run_id=run.run_id,
                    layer=asset["layer"],
                    asset_name=asset["asset_name"],
                    row_count=int(asset.get("row_count", 0)),
                    storage_path=asset.get("storage_path"),
                )
            )
        for event in summary.get("quarantine_preview", []):
            db.add(
                DataOpsQuarantineEvent(
                    run_id=run.run_id,
                    rule_code=event["rule_code"],
                    reason=event["reason"],
                    source_file=event.get("source_file"),
                    record_ref=event.get("record_ref"),
                    preview_json=event.get("preview", {}),
                )
            )

    def _summary_run_url(self, summary: dict, run_id: str) -> str | None:
        url = summary.get("databricks_run_url")
        if isinstance(url, str) and f"run/{run_id}" in url:
            return url
        return self._build_run_url(run_id) if self._databricks_configured() else url

    def _ensure_run_url(self, run: DataOpsPipelineRun) -> None:
        if not self._databricks_configured():
            return
        expected_fragment = f"run/{run.run_id}"
        if not run.databricks_run_url or expected_fragment not in run.databricks_run_url:
            run.databricks_run_url = self._build_run_url(run.run_id)

    def _build_run_url(self, run_id: str) -> str:
        host = str(self.settings.databricks_host).rstrip("/")
        workspace_id = _workspace_id_from_host(host)
        org_part = f"?o={workspace_id}" if workspace_id else ""
        return f"{host}/{org_part}#job/{self.settings.databricks_job_id}/run/{run_id}"

    def _ai_summary_if_needed(self, summary: dict) -> str | None:
        if summary.get("status") == "running":
            return None
        if summary.get("status") == "success" and float(summary.get("quality_score", 100)) >= 90:
            return None
        try:
            return AIRecommendationService().generate_dataops_failure_summary(summary)
        except AIConfigurationError:
            return (
                "El pipeline requiere atención: revise las reglas fallidas, los registros en quarantine "
                "y la salida del job de Databricks antes de publicar Gold."
            )


def _parse_json_result(result: str | None) -> dict | None:
    if not result:
        return None
    try:
        parsed = json.loads(result)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        start = result.find("{")
        end = result.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            parsed = json.loads(result[start : end + 1])
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None


def _workspace_id_from_host(host: str) -> str | None:
    match = re.search(r"adb-(\d+)", host)
    return match.group(1) if match else None
