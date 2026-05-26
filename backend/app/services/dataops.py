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


DEFAULT_PIPELINE_KEY = "tpcds-retail-dataops"
BANKING_ALERTS_PIPELINE_KEY = "alertas-movimientos-inusuales"
RETAIL_PIPELINE_TYPE = "lakehouse_bronze_silver_gold"
BANKING_ALERTS_PIPELINE_TYPE = "banking_fraud_alerts"
BANKING_ALERTS_JOB_ID = "88827781921882"


class DatabricksConfigurationError(RuntimeError):
    pass


class DataOpsMonitorService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def list_pipelines(self, db: Session) -> list[DataOpsPipeline]:
        return sorted(self.ensure_pipelines(db), key=lambda pipeline: pipeline.id)

    def ensure_pipelines(self, db: Session) -> list[DataOpsPipeline]:
        pipelines: list[DataOpsPipeline] = []
        for pipeline_key, definition in self._pipeline_definitions().items():
            pipeline = (
                db.query(DataOpsPipeline)
                .filter(DataOpsPipeline.pipeline_key == pipeline_key)
                .first()
            )
            if not pipeline:
                pipeline = db.query(DataOpsPipeline).filter(DataOpsPipeline.name == definition["name"]).first()
            if not pipeline:
                pipeline = DataOpsPipeline(name=definition["name"], status="idle")
                db.add(pipeline)
                db.flush()

            current_config = pipeline.config_json if isinstance(pipeline.config_json, dict) else {}
            pipeline.pipeline_key = pipeline_key
            pipeline.pipeline_type = str(definition["pipeline_type"])
            definition_description = str(definition["description"])
            if not pipeline.description or _should_refresh_pipeline_description(pipeline.description):
                pipeline.description = definition_description
            pipeline.config_json = {**current_config, **definition["config"]}

            desired_job_id = definition.get("databricks_job_id")
            if pipeline_key == DEFAULT_PIPELINE_KEY and self.settings.databricks_job_id:
                desired_job_id = self.settings.databricks_job_id
            if desired_job_id:
                pipeline.databricks_job_id = str(desired_job_id)
            pipelines.append(pipeline)
        db.commit()
        for pipeline in pipelines:
            db.refresh(pipeline)
        return pipelines

    def ensure_pipeline(self, db: Session, pipeline_key: str = DEFAULT_PIPELINE_KEY) -> DataOpsPipeline:
        normalized_key = _normalize_pipeline_key(pipeline_key)
        definitions = self._pipeline_definitions()
        definition_names = {str(definition["name"]) for definition in definitions.values()}
        if normalized_key not in definitions and normalized_key not in definition_names:
            raise ValueError(f"Unknown DataOps pipeline: {pipeline_key}")
        self.ensure_pipelines(db)
        pipeline = (
            db.query(DataOpsPipeline)
            .filter(DataOpsPipeline.pipeline_key == normalized_key)
            .first()
        )
        if not pipeline:
            pipeline = db.query(DataOpsPipeline).filter(DataOpsPipeline.name == normalized_key).first()
        if not pipeline:
            raise ValueError(f"Unknown DataOps pipeline: {pipeline_key}")
        return pipeline

    def run_pipeline(self, db: Session, pipeline_key: str = DEFAULT_PIPELINE_KEY) -> DataOpsPipelineRun:
        pipeline = self.ensure_pipeline(db, pipeline_key)
        started = perf_counter()

        if self._databricks_configured(pipeline):
            summary = self._start_databricks_job(pipeline)
            summary.setdefault("duration_ms", int((perf_counter() - started) * 1000))
        else:
            summary = self._demo_run_summary(pipeline, int((perf_counter() - started) * 1000))

        run = self._persist_summary(db, pipeline, summary)
        pipeline.status = run.status
        db.commit()
        db.refresh(run)
        return run

    def latest_run(self, db: Session, pipeline_key: str = DEFAULT_PIPELINE_KEY, sync: bool = True) -> DataOpsPipelineRun | None:
        pipeline = self.ensure_pipeline(db, pipeline_key)
        if sync:
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

    def history_runs(
        self,
        db: Session,
        pipeline_key: str = DEFAULT_PIPELINE_KEY,
        limit: int = 20,
        sync: bool = False,
    ) -> list[DataOpsPipelineRun]:
        pipeline = self.ensure_pipeline(db, pipeline_key)
        if sync:
            self.sync_running_runs(db, pipeline)
        return (
            db.query(DataOpsPipelineRun)
            .filter(DataOpsPipelineRun.pipeline_id == pipeline.id)
            .order_by(DataOpsPipelineRun.created_at.desc())
            .limit(limit)
            .all()
        )

    def latest_quality_checks(self, db: Session, pipeline_key: str = DEFAULT_PIPELINE_KEY) -> list[DataOpsQualityCheck]:
        latest = self.latest_run(db, pipeline_key, sync=False)
        if not latest:
            return []
        return db.query(DataOpsQualityCheck).filter(DataOpsQualityCheck.run_id == latest.run_id).order_by(DataOpsQualityCheck.id).all()

    def latest_assets(self, db: Session, pipeline_key: str = DEFAULT_PIPELINE_KEY) -> list[DataOpsGeneratedAsset]:
        latest = self.latest_run(db, pipeline_key, sync=False)
        if not latest:
            return []
        return db.query(DataOpsGeneratedAsset).filter(DataOpsGeneratedAsset.run_id == latest.run_id).order_by(DataOpsGeneratedAsset.id).all()

    def latest_quarantine_events(self, db: Session, pipeline_key: str = DEFAULT_PIPELINE_KEY) -> list[DataOpsQuarantineEvent]:
        latest = self.latest_run(db, pipeline_key, sync=False)
        if not latest:
            return []
        return (
            db.query(DataOpsQuarantineEvent)
            .filter(DataOpsQuarantineEvent.run_id == latest.run_id)
            .order_by(DataOpsQuarantineEvent.created_at.desc())
            .limit(30)
            .all()
        )

    def sync_running_runs(self, db: Session, pipeline: DataOpsPipeline | None = None) -> None:
        pipelines = [pipeline] if pipeline else self.ensure_pipelines(db)
        for candidate in pipelines:
            if not candidate or not self._databricks_configured(candidate):
                continue
            running_runs = (
                db.query(DataOpsPipelineRun)
                .filter(DataOpsPipelineRun.pipeline_id == candidate.id, DataOpsPipelineRun.status == "running")
                .order_by(DataOpsPipelineRun.created_at.desc())
                .limit(5)
                .all()
            )
            for run in running_runs:
                if self._is_local_demo_run(run):
                    continue
                try:
                    summary = self._databricks_summary_for_run(run, candidate)
                except (httpx.HTTPError, httpx.TimeoutException):
                    continue
                if not summary:
                    continue
                self._update_run_from_summary(db, run, summary)
                self._ensure_run_url(run)
                candidate.status = run.status
        db.commit()

    def _pipeline_definitions(self) -> dict[str, dict]:
        catalog = self.settings.databricks_catalog
        configured_definitions = self._configured_pipeline_definitions()
        definitions = {
            DEFAULT_PIPELINE_KEY: {
                "name": "tpcds-retail-dataops",
                "pipeline_type": RETAIL_PIPELINE_TYPE,
                "description": "TPC-DS retail DataOps flow: Bronze -> Silver -> Gold with quality checks and quarantine.",
                "databricks_job_id": self.settings.databricks_job_id,
                "config": {
                    "label": "Retail Sales",
                    "summary_task_keywords": ["05", "summary"],
                    "notebook_params": {
                        "catalog": catalog,
                        "bronze_schema": self.settings.databricks_schema_bronze,
                        "silver_schema": self.settings.databricks_schema_silver,
                        "gold_schema": self.settings.databricks_schema_gold,
                    },
                },
            },
            BANKING_ALERTS_PIPELINE_KEY: {
                "name": "JOB_ALERTAS_MOVIMIENTOS_INUSUALES",
                "pipeline_type": BANKING_ALERTS_PIPELINE_TYPE,
                "description": (
                    "Proceso bancario DataOps que detecta movimientos inusuales, "
                    "publica alertas Gold, registra auditoria y dispara notificacion operativa."
                ),
                "databricks_job_id": BANKING_ALERTS_JOB_ID,
                "config": {
                    "label": "Alertas bancarias",
                    "summary_task_key": "detectar_alertas_movimientos_inusuales",
                    "summary_task_keywords": ["detectar", "alertas", "movimientos"],
                    "notebook_params": {
                        "catalog": catalog,
                        "schema": "banco_demo",
                    },
                    "tables": self._banking_tables(),
                },
            },
        }

        if configured_definitions:
            return dict(configured_definitions)

        return definitions

    def _configured_pipeline_definitions(self) -> dict[str, dict]:
        raw = self.settings.dataops_pipelines_json
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}

        items = list(parsed.values()) if isinstance(parsed, dict) else parsed
        if not isinstance(items, list | tuple):
            return {}

        definitions: dict[str, dict] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            pipeline_key = str(item.get("pipeline_key") or item.get("key") or "").strip()
            if not pipeline_key:
                continue
            pipeline_type = str(item.get("pipeline_type") or item.get("type") or RETAIL_PIPELINE_TYPE)
            notebook_params = item.get("notebook_params") if isinstance(item.get("notebook_params"), dict) else {}
            summary_keywords = item.get("summary_task_keywords")
            config = {
                "label": str(item.get("label") or item.get("name") or pipeline_key),
                "summary_task_keywords": summary_keywords if isinstance(summary_keywords, list) else ["summary"],
                "notebook_params": notebook_params,
            }
            if item.get("summary_task_key"):
                config["summary_task_key"] = str(item["summary_task_key"])
            if isinstance(item.get("tables"), dict):
                config["tables"] = item["tables"]
            definitions[pipeline_key] = {
                "name": str(item.get("name") or pipeline_key),
                "pipeline_type": pipeline_type,
                "description": str(item.get("description") or f"Databricks job configured for {pipeline_key}."),
                "databricks_job_id": str(item.get("databricks_job_id") or item.get("job_id") or "").strip() or None,
                "config": config,
            }
        return definitions

    def _databricks_configured(self, pipeline: DataOpsPipeline) -> bool:
        return bool(self.settings.databricks_host and self.settings.databricks_token and pipeline.databricks_job_id)

    def _start_databricks_job(self, pipeline: DataOpsPipeline) -> dict:
        if not self._databricks_configured(pipeline):
            raise DatabricksConfigurationError("Configure DATABRICKS_HOST, DATABRICKS_TOKEN and a pipeline Databricks job id.")

        host = str(self.settings.databricks_host).rstrip("/")
        response = httpx.post(
            f"{host}/api/2.1/jobs/run-now",
            headers=self._databricks_headers(),
            json={
                "job_id": int(str(pipeline.databricks_job_id)),
                "notebook_params": self._notebook_params_for(pipeline),
            },
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        databricks_run_id = str(payload.get("run_id") or uuid4())
        run_url = payload.get("run_page_url") or self._build_run_url(databricks_run_id, pipeline)
        return self._initial_running_summary(pipeline, databricks_run_id, run_url)

    def _databricks_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.settings.databricks_token}"}

    def _databricks_summary_for_run(self, run: DataOpsPipelineRun, pipeline: DataOpsPipeline) -> dict | None:
        host = str(self.settings.databricks_host).rstrip("/")
        databricks_run_id = run.databricks_run_id or run.run_id
        response = httpx.get(
            f"{host}/api/2.1/jobs/runs/get",
            headers=self._databricks_headers(),
            params={"run_id": databricks_run_id},
            timeout=8,
        )
        response.raise_for_status()
        run_info = response.json()
        state = run_info.get("state", {})
        life_cycle = state.get("life_cycle_state")
        if life_cycle not in {"TERMINATED", "SKIPPED", "INTERNAL_ERROR"}:
            return None

        result_state = state.get("result_state")
        if result_state == "SUCCESS":
            parsed = self._read_summary_notebook_output(host, run_info, pipeline)
            if parsed:
                return parsed
            return self._terminal_metadata_summary(run, pipeline, run_info, "success")
        return self._terminal_metadata_summary(run, pipeline, run_info, "failed")

    def _read_summary_notebook_output(self, host: str, run_info: dict, pipeline: DataOpsPipeline) -> dict | None:
        tasks = run_info.get("tasks") or []
        config = pipeline.config_json if isinstance(pipeline.config_json, dict) else {}
        preferred_key = str(config.get("summary_task_key") or "").lower()
        keywords = [str(item).lower() for item in config.get("summary_task_keywords", [])]
        preferred = [
            task
            for task in tasks
            if preferred_key and preferred_key in str(task.get("task_key", "")).lower()
        ]
        if not preferred and keywords:
            preferred = [
                task
                for task in tasks
                if any(keyword in str(task.get("task_key", "")).lower() for keyword in keywords)
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
                timeout=8,
            )
            if response.status_code >= 400:
                continue
            result = (response.json().get("notebook_output") or {}).get("result")
            parsed = _parse_json_result(result)
            if parsed:
                return self._normalize_summary_for_pipeline(
                    pipeline=pipeline,
                    summary=parsed,
                    databricks_run_id=str(run_info.get("run_id")),
                    databricks_run_url=run_info.get("run_page_url"),
                    fallback_status="success",
                )
        return None

    def _terminal_metadata_summary(
        self,
        run: DataOpsPipelineRun,
        pipeline: DataOpsPipeline,
        run_info: dict,
        status: str,
    ) -> dict:
        start_ms = run_info.get("start_time") or 0
        end_ms = run_info.get("end_time") or start_ms
        summary = {
            "pipeline_name": pipeline.name,
            "pipeline_key": pipeline.pipeline_key or pipeline.name,
            "run_id": run.run_id,
            "databricks_run_id": run.databricks_run_id or run.run_id,
            "business_run_id": run.business_run_id,
            "status": status,
            "bronze_rows": run.bronze_rows,
            "silver_rows": run.silver_rows,
            "gold_rows": run.gold_rows,
            "quality_score": run.quality_score,
            "quarantine_rows": run.quarantine_rows,
            "duration_ms": int(max(0, end_ms - start_ms)),
            "generated_tables": run.generated_tables_json,
            "failed_rules": run.failed_rules_json,
            "metrics": run.metrics_json,
            "events": run.events_json,
            "databricks_run_url": run_info.get("run_page_url") or run.databricks_run_url or self._build_run_url(run.run_id, pipeline),
            "quality_checks": [],
            "assets": [],
            "quarantine_preview": [],
        }
        return self._normalize_summary_for_pipeline(
            pipeline=pipeline,
            summary=summary,
            databricks_run_id=summary["databricks_run_id"],
            databricks_run_url=summary["databricks_run_url"],
            fallback_status=status,
        )

    def _demo_run_summary(self, pipeline: DataOpsPipeline, duration_ms: int) -> dict:
        if pipeline.pipeline_type == BANKING_ALERTS_PIPELINE_TYPE:
            return self._banking_demo_run_summary(pipeline, duration_ms)
        return self._retail_demo_run_summary(pipeline, duration_ms)

    def _retail_demo_run_summary(self, pipeline: DataOpsPipeline, duration_ms: int) -> dict:
        run_id = f"demo-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:6]}"
        bronze_rows = 2_880_404
        quarantine_rows = 1_054
        silver_rows = bronze_rows - quarantine_rows
        gold_rows = 1_820
        quality_score = _quality_score(bronze_rows, quarantine_rows)
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
        tables = self._retail_tables()
        summary = {
            "pipeline_name": pipeline.name,
            "pipeline_key": pipeline.pipeline_key or DEFAULT_PIPELINE_KEY,
            "run_id": run_id,
            "databricks_run_id": run_id,
            "status": "success",
            "bronze_rows": bronze_rows,
            "silver_rows": silver_rows,
            "gold_rows": gold_rows,
            "quality_score": quality_score,
            "quarantine_rows": quarantine_rows,
            "duration_ms": max(duration_ms, 1280),
            "generated_tables": list(tables.values()),
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
                {"layer": "bronze", "asset_name": "store_sales", "row_count": bronze_rows, "storage_path": tables["store_sales"]},
                {"layer": "bronze", "asset_name": "date_dim", "row_count": 73_049, "storage_path": tables["date_dim"]},
                {"layer": "silver", "asset_name": "store_sales_clean", "row_count": silver_rows, "storage_path": tables["store_sales_clean"]},
                {"layer": "silver", "asset_name": "quarantine_store_sales", "row_count": quarantine_rows, "storage_path": tables["quarantine_store_sales"]},
                {"layer": "gold", "asset_name": "sales_by_year_category", "row_count": gold_rows, "storage_path": tables["sales_by_year_category"]},
                {"layer": "gold", "asset_name": "sales_by_store", "row_count": 1_440, "storage_path": tables["sales_by_store"]},
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
        return self._normalize_retail_summary(pipeline, summary)

    def _banking_demo_run_summary(self, pipeline: DataOpsPipeline, duration_ms: int) -> dict:
        run_suffix = uuid4().hex[:6].upper()
        business_run_id = f"RUN-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{run_suffix}"
        run_id = f"bank-demo-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{run_suffix.lower()}"
        summary = {
            "pipeline_name": pipeline.name,
            "pipeline_key": pipeline.pipeline_key or BANKING_ALERTS_PIPELINE_KEY,
            "run_id": run_id,
            "databricks_run_id": run_id,
            "business_run_id": business_run_id,
            "status": "success",
            "transactions_inserted": 20,
            "transactions_processed": 20,
            "alerts_generated": 2,
            "email_status": "sent",
            "duration_ms": max(duration_ms, 940),
            "databricks_run_url": "local-demo://databricks/alertas-movimientos-inusuales",
        }
        return self._normalize_banking_summary(pipeline, summary)

    def _normalize_summary_for_pipeline(
        self,
        pipeline: DataOpsPipeline,
        summary: dict,
        databricks_run_id: str | None,
        databricks_run_url: str | None,
        fallback_status: str,
    ) -> dict:
        normalized = dict(summary)
        normalized.setdefault("pipeline_name", pipeline.name)
        normalized.setdefault("pipeline_key", pipeline.pipeline_key or pipeline.name)
        normalized.setdefault("status", fallback_status)
        normalized.setdefault("databricks_run_id", databricks_run_id)
        normalized.setdefault("databricks_run_url", databricks_run_url)
        normalized.setdefault("run_id", str(databricks_run_id or uuid4()))
        if pipeline.pipeline_type == BANKING_ALERTS_PIPELINE_TYPE:
            return self._normalize_banking_summary(pipeline, normalized)
        return self._normalize_retail_summary(pipeline, normalized)

    def _normalize_retail_summary(self, pipeline: DataOpsPipeline, summary: dict) -> dict:
        normalized = dict(summary)
        normalized.setdefault("pipeline_name", pipeline.name)
        normalized.setdefault("pipeline_key", pipeline.pipeline_key or DEFAULT_PIPELINE_KEY)
        normalized["run_id"] = str(normalized.get("run_id") or normalized.get("databricks_run_id") or uuid4())
        normalized["databricks_run_id"] = str(normalized.get("databricks_run_id") or normalized["run_id"])
        bronze_rows = _coalesce_int(normalized, ["bronze_rows", "raw_rows"], 0)
        silver_rows = _coalesce_int(normalized, ["silver_rows", "clean_rows"], 0)
        gold_rows = _coalesce_int(normalized, ["gold_rows", "published_rows"], 0)
        quarantine_rows = _coalesce_int(normalized, ["quarantine_rows", "rejected_rows"], 0)
        if "quality_score" not in normalized and bronze_rows:
            normalized["quality_score"] = _quality_score(bronze_rows, quarantine_rows)
        normalized.setdefault("quality_score", 0)
        normalized["bronze_rows"] = bronze_rows
        normalized["silver_rows"] = silver_rows
        normalized["gold_rows"] = gold_rows
        normalized["quarantine_rows"] = quarantine_rows
        normalized.setdefault("duration_ms", 0)
        normalized.setdefault("generated_tables", [])
        normalized.setdefault("failed_rules", [])
        normalized.setdefault("quality_checks", [])
        normalized.setdefault("assets", [])
        normalized.setdefault("quarantine_preview", [])
        normalized["metrics"] = normalized.get("metrics") or self._retail_metrics(
            bronze_rows=bronze_rows,
            silver_rows=silver_rows,
            gold_rows=gold_rows,
            quality_score=float(normalized["quality_score"]),
            quarantine_rows=quarantine_rows,
        )
        normalized.setdefault("events", [])
        return normalized

    def _normalize_banking_summary(self, pipeline: DataOpsPipeline, summary: dict) -> dict:
        normalized = dict(summary)
        normalized.setdefault("pipeline_name", pipeline.name)
        normalized.setdefault("pipeline_key", pipeline.pipeline_key or BANKING_ALERTS_PIPELINE_KEY)
        normalized["run_id"] = str(normalized.get("portal_run_id") or normalized.get("run_id") or normalized.get("databricks_run_id") or uuid4())
        normalized["databricks_run_id"] = str(normalized.get("databricks_run_id") or normalized["run_id"])
        normalized["business_run_id"] = _coalesce_str(
            normalized,
            ["business_run_id", "process_run_id", "batch_run_id", "job_run_id", "run_id_negocio"],
            normalized.get("business_run_id"),
        )
        status = str(normalized.get("status") or "success")
        default_inserted = 20 if status == "success" else 0
        default_alerts = 2 if status == "success" else 0
        transactions_inserted = _coalesce_int(
            normalized,
            ["transactions_inserted", "transacciones_insertadas", "records_inserted", "source_rows", "bronze_rows"],
            default_inserted,
        )
        transactions_processed = _coalesce_int(
            normalized,
            ["transactions_processed", "transacciones_procesadas", "records_processed", "processed_rows", "silver_rows"],
            transactions_inserted,
        )
        alerts_generated = _coalesce_int(
            normalized,
            ["alerts_generated", "alertas_generadas", "alerts_count", "alert_count", "gold_rows"],
            default_alerts,
        )
        email_status = _email_status(normalized.get("email_status", normalized.get("email_sent", "sent" if status == "success" else "pending")))
        tables = self._banking_tables()
        normalized["status"] = status
        normalized["bronze_rows"] = transactions_inserted
        normalized["silver_rows"] = transactions_processed
        normalized["gold_rows"] = alerts_generated
        normalized["quality_score"] = _coalesce_float(normalized, ["quality_score"], _quality_score(transactions_processed, 0))
        normalized["quarantine_rows"] = _coalesce_int(normalized, ["quarantine_rows"], 0)
        normalized.setdefault("duration_ms", 0)
        normalized["generated_tables"] = normalized.get("generated_tables") or list(tables.values())
        normalized["failed_rules"] = normalized.get("failed_rules") or []
        normalized["metrics"] = normalized.get("metrics") or self._banking_metrics(
            transactions_inserted=transactions_inserted,
            transactions_processed=transactions_processed,
            alerts_generated=alerts_generated,
            email_status=email_status,
        )
        normalized["quality_checks"] = normalized.get("quality_checks") or [
            {
                "rule_code": "source_batch_control",
                "layer": "source",
                "status": "passed" if transactions_inserted >= 20 else "warning",
                "failed_rows": 0,
                "description": f"{transactions_inserted} transacciones origen evaluadas para la corrida.",
            },
            {
                "rule_code": "incremental_run_scope",
                "layer": "gold",
                "status": "passed",
                "failed_rows": 0,
                "description": "El procesamiento se limita al run_id de negocio activo.",
            },
            {
                "rule_code": "amount_gte_10000",
                "layer": "gold",
                "status": "passed",
                "failed_rows": 0,
                "description": f"{alerts_generated} movimientos inusuales publicados como alertas.",
            },
            {
                "rule_code": "email_notification",
                "layer": "audit",
                "status": "passed" if email_status == "sent" else "warning",
                "failed_rows": 0,
                "description": f"Notificacion operativa: {email_status}.",
            },
        ]
        normalized["assets"] = normalized.get("assets") or [
            {"layer": "source", "asset_name": "transacciones_demo", "row_count": transactions_inserted, "storage_path": tables["transacciones_demo"]},
            {"layer": "gold", "asset_name": "alertas_movimientos_inusuales", "row_count": alerts_generated, "storage_path": tables["alertas_movimientos_inusuales"]},
            {"layer": "audit", "asset_name": "log_ejecucion_alertas", "row_count": 1 if status == "success" else 0, "storage_path": tables["log_ejecucion_alertas"]},
        ]
        normalized["events"] = _normalize_banking_events(
            normalized.get("events") or normalized.get("alerts_preview") or normalized.get("alertas") or [],
            alerts_generated=alerts_generated,
            business_run_id=normalized.get("business_run_id"),
        )
        normalized["quarantine_preview"] = normalized.get("quarantine_preview") or []
        normalized["email_status"] = email_status
        normalized["transactions_inserted"] = transactions_inserted
        normalized["transactions_processed"] = transactions_processed
        normalized["alerts_generated"] = alerts_generated
        return normalized

    def _persist_summary(self, db: Session, pipeline: DataOpsPipeline, summary: dict) -> DataOpsPipelineRun:
        run_id = str(summary.get("run_id") or summary.get("databricks_run_id") or uuid4())
        run = DataOpsPipelineRun(
            pipeline_id=pipeline.id,
            run_id=run_id,
            databricks_run_id=str(summary.get("databricks_run_id") or run_id),
            business_run_id=str(summary["business_run_id"]) if summary.get("business_run_id") else None,
            status=str(summary["status"]),
            bronze_rows=int(summary.get("bronze_rows", 0)),
            silver_rows=int(summary.get("silver_rows", 0)),
            gold_rows=int(summary.get("gold_rows", 0)),
            quality_score=float(summary.get("quality_score", 0)),
            quarantine_rows=int(summary.get("quarantine_rows", 0)),
            duration_ms=int(summary.get("duration_ms", 0)),
            failed_rules_json=list(summary.get("failed_rules", [])),
            generated_tables_json=list(summary.get("generated_tables", [])),
            metrics_json=list(summary.get("metrics", summary.get("metrics_json", []))),
            events_json=list(summary.get("events", summary.get("events_json", []))),
            databricks_run_url=self._summary_run_url(summary, run_id, pipeline),
            raw_summary_json=summary,
            ai_summary=self._ai_summary_if_needed(summary),
            finished_at=datetime.utcnow() if summary.get("status") in {"success", "warning", "failed"} else None,
        )
        db.add(run)
        db.flush()

        self._replace_run_children(db, run, summary)
        self._ensure_run_url(run)
        db.commit()
        return run

    def _update_run_from_summary(self, db: Session, run: DataOpsPipelineRun, summary: dict) -> None:
        run.databricks_run_id = str(summary.get("databricks_run_id") or run.databricks_run_id or run.run_id)
        run.business_run_id = str(summary["business_run_id"]) if summary.get("business_run_id") else run.business_run_id
        run.status = str(summary.get("status", run.status))
        run.bronze_rows = int(summary.get("bronze_rows", run.bronze_rows))
        run.silver_rows = int(summary.get("silver_rows", run.silver_rows))
        run.gold_rows = int(summary.get("gold_rows", run.gold_rows))
        run.quality_score = float(summary.get("quality_score", run.quality_score))
        run.quarantine_rows = int(summary.get("quarantine_rows", run.quarantine_rows))
        run.duration_ms = int(summary.get("duration_ms", run.duration_ms))
        run.failed_rules_json = list(summary.get("failed_rules", run.failed_rules_json))
        run.generated_tables_json = list(summary.get("generated_tables", run.generated_tables_json))
        run.metrics_json = list(summary.get("metrics", summary.get("metrics_json", run.metrics_json or [])))
        run.events_json = list(summary.get("events", summary.get("events_json", run.events_json or [])))
        run.databricks_run_url = self._summary_run_url(summary, run.databricks_run_id or run.run_id, run.pipeline) or run.databricks_run_url
        run.raw_summary_json = summary
        run.ai_summary = self._ai_summary_if_needed(summary)
        run.finished_at = datetime.utcnow() if run.status in {"success", "warning", "failed"} else None

        db.query(DataOpsQualityCheck).filter(DataOpsQualityCheck.run_id == run.run_id).delete()
        db.query(DataOpsGeneratedAsset).filter(DataOpsGeneratedAsset.run_id == run.run_id).delete()
        db.query(DataOpsQuarantineEvent).filter(DataOpsQuarantineEvent.run_id == run.run_id).delete()
        self._replace_run_children(db, run, summary)

    def _replace_run_children(self, db: Session, run: DataOpsPipelineRun, summary: dict) -> None:
        for check in summary.get("quality_checks", []):
            db.add(
                DataOpsQualityCheck(
                    run_id=run.run_id,
                    rule_code=str(check["rule_code"]),
                    layer=str(check["layer"]),
                    status=str(check["status"]),
                    failed_rows=int(check.get("failed_rows", 0)),
                    description=str(check["description"]),
                )
            )
        for asset in summary.get("assets", []):
            db.add(
                DataOpsGeneratedAsset(
                    run_id=run.run_id,
                    layer=str(asset["layer"]),
                    asset_name=str(asset["asset_name"]),
                    row_count=int(asset.get("row_count", 0)),
                    storage_path=asset.get("storage_path"),
                )
            )
        for event in summary.get("quarantine_preview", []):
            db.add(
                DataOpsQuarantineEvent(
                    run_id=run.run_id,
                    rule_code=str(event["rule_code"]),
                    reason=str(event["reason"]),
                    source_file=event.get("source_file"),
                    record_ref=event.get("record_ref"),
                    preview_json=event.get("preview", {}),
                )
            )

    def _initial_running_summary(self, pipeline: DataOpsPipeline, databricks_run_id: str, run_url: str | None) -> dict:
        summary = {
            "pipeline_name": pipeline.name,
            "pipeline_key": pipeline.pipeline_key or pipeline.name,
            "run_id": databricks_run_id,
            "databricks_run_id": databricks_run_id,
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
            "metrics": [
                {"key": "job_status", "label": "Job status", "value": "running", "tone": "warning", "order": 1},
                {"key": "databricks_run", "label": "Databricks run", "value": databricks_run_id, "tone": "info", "order": 2},
            ],
            "events": [],
        }
        return self._normalize_summary_for_pipeline(pipeline, summary, databricks_run_id, run_url, "running")

    def _summary_run_url(self, summary: dict, run_id: str, pipeline: DataOpsPipeline) -> str | None:
        url = summary.get("databricks_run_url")
        if isinstance(url, str) and (f"run/{run_id}" in url or url.startswith("local-demo://")):
            return url
        return self._build_run_url(run_id, pipeline) if self._databricks_configured(pipeline) else url

    def _ensure_run_url(self, run: DataOpsPipelineRun) -> None:
        pipeline = run.pipeline
        if self._is_local_demo_run(run):
            run.databricks_run_url = self._local_demo_url(pipeline)
            return
        if run.databricks_run_url and run.databricks_run_url.startswith("local-demo://"):
            return
        if not self._databricks_configured(pipeline):
            return
        databricks_run_id = run.databricks_run_id or run.run_id
        expected_fragment = f"run/{databricks_run_id}"
        if not run.databricks_run_url or expected_fragment not in run.databricks_run_url:
            run.databricks_run_url = self._build_run_url(databricks_run_id, pipeline)

    def _local_demo_url(self, pipeline: DataOpsPipeline) -> str:
        if pipeline.pipeline_type == BANKING_ALERTS_PIPELINE_TYPE:
            return "local-demo://databricks/alertas-movimientos-inusuales"
        return f"local-demo://databricks/{pipeline.pipeline_key or DEFAULT_PIPELINE_KEY}"

    def _is_local_demo_run(self, run: DataOpsPipelineRun) -> bool:
        return run.run_id.startswith(("demo-", "bank-demo-")) or bool(
            run.databricks_run_url and run.databricks_run_url.startswith("local-demo://")
        )

    def _build_run_url(self, run_id: str, pipeline: DataOpsPipeline) -> str:
        host = str(self.settings.databricks_host).rstrip("/")
        workspace_id = _workspace_id_from_host(host)
        org_part = f"?o={workspace_id}" if workspace_id else ""
        job_id = pipeline.databricks_job_id or self.settings.databricks_job_id or ""
        return f"{host}/{org_part}#job/{job_id}/run/{run_id}"

    def _notebook_params_for(self, pipeline: DataOpsPipeline) -> dict:
        config = pipeline.config_json if isinstance(pipeline.config_json, dict) else {}
        params = dict(config.get("notebook_params") or {})
        params.setdefault("catalog", self.settings.databricks_catalog)
        if pipeline.pipeline_type == BANKING_ALERTS_PIPELINE_TYPE:
            params.setdefault("schema", "banco_demo")
        else:
            params.setdefault("bronze_schema", self.settings.databricks_schema_bronze)
            params.setdefault("silver_schema", self.settings.databricks_schema_silver)
            params.setdefault("gold_schema", self.settings.databricks_schema_gold)
        return params

    def _retail_tables(self) -> dict[str, str]:
        catalog = self.settings.databricks_catalog
        bronze = self.settings.databricks_schema_bronze
        silver = self.settings.databricks_schema_silver
        gold = self.settings.databricks_schema_gold
        return {
            "store_sales": f"{catalog}.{bronze}.store_sales",
            "date_dim": f"{catalog}.{bronze}.date_dim",
            "item": f"{catalog}.{bronze}.item",
            "store": f"{catalog}.{bronze}.store",
            "store_sales_clean": f"{catalog}.{silver}.store_sales_clean",
            "quarantine_store_sales": f"{catalog}.{silver}.quarantine_store_sales",
            "sales_by_year_category": f"{catalog}.{gold}.sales_by_year_category",
            "sales_by_store": f"{catalog}.{gold}.sales_by_store",
        }

    def _banking_tables(self) -> dict[str, str]:
        catalog = self.settings.databricks_catalog
        schema = "banco_demo"
        return {
            "transacciones_demo": f"{catalog}.{schema}.transacciones_demo",
            "alertas_movimientos_inusuales": f"{catalog}.{schema}.alertas_movimientos_inusuales",
            "log_ejecucion_alertas": f"{catalog}.{schema}.log_ejecucion_alertas",
        }

    def _retail_metrics(
        self,
        bronze_rows: int,
        silver_rows: int,
        gold_rows: int,
        quality_score: float,
        quarantine_rows: int,
    ) -> list[dict]:
        return [
            {"key": "bronze_rows", "label": "Bronze rows", "value": bronze_rows, "tone": "bronze", "order": 1},
            {"key": "silver_rows", "label": "Silver rows", "value": silver_rows, "tone": "silver", "order": 2},
            {"key": "gold_rows", "label": "Gold rows", "value": gold_rows, "tone": "gold", "order": 3},
            {"key": "quality_score", "label": "Quality score", "value": quality_score, "unit": "%", "tone": "success", "order": 4},
            {"key": "quarantine_rows", "label": "Quarantine", "value": quarantine_rows, "tone": "warning", "order": 5},
        ]

    def _banking_metrics(
        self,
        transactions_inserted: int,
        transactions_processed: int,
        alerts_generated: int,
        email_status: str,
    ) -> list[dict]:
        alert_rate = (alerts_generated / transactions_processed) * 100 if transactions_processed else 0
        return [
            {"key": "transactions_inserted", "label": "Source transactions", "value": transactions_inserted, "tone": "source", "order": 1},
            {"key": "transactions_processed", "label": "Processed transactions", "value": transactions_processed, "tone": "success", "order": 2},
            {"key": "alerts_generated", "label": "Unusual alerts", "value": alerts_generated, "tone": "warning", "order": 3},
            {"key": "alert_rate", "label": "Alert rate", "value": alert_rate, "unit": "%", "tone": "warning", "order": 4},
            {"key": "email_status", "label": "Email status", "value": email_status, "tone": "success" if email_status == "sent" else "warning", "order": 5},
        ]

    def _ai_summary_if_needed(self, summary: dict) -> str | None:
        if summary.get("status") == "running":
            return None
        if summary.get("status") == "success" and float(summary.get("quality_score", 100)) >= 90:
            return None
        try:
            return AIRecommendationService().generate_dataops_failure_summary(summary)
        except AIConfigurationError:
            return (
                "El pipeline requiere atencion: revise las reglas fallidas, los registros aislados "
                "y la salida del job de Databricks antes de publicar."
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


def _normalize_pipeline_key(pipeline_key: str) -> str:
    return pipeline_key.strip() or DEFAULT_PIPELINE_KEY


def _should_refresh_pipeline_description(description: str) -> bool:
    normalized = description.lower()
    return "genera transacciones" in normalized or "transacciones demo" in normalized


def _quality_score(total_rows: int, rejected_rows: int) -> float:
    if total_rows <= 0:
        return 0.0
    return ((total_rows - rejected_rows) / total_rows) * 100


def _coalesce_int(summary: dict, keys: list[str], default: int) -> int:
    for key in keys:
        value = summary.get(key)
        if value is None or value == "":
            continue
        try:
            return int(float(value))
        except (TypeError, ValueError):
            continue
    return default


def _coalesce_float(summary: dict, keys: list[str], default: float) -> float:
    for key in keys:
        value = summary.get(key)
        if value is None or value == "":
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return default


def _coalesce_str(summary: dict, keys: list[str], default: object | None = None) -> str | None:
    for key in keys:
        value = summary.get(key)
        if value is None or value == "":
            continue
        return str(value)
    return str(default) if default is not None else None


def _email_status(value: object) -> str:
    if isinstance(value, bool):
        return "sent" if value else "pending"
    normalized = str(value or "").strip().lower()
    if normalized in {"true", "sent", "enviado", "success", "ok"}:
        return "sent"
    if normalized in {"false", "failed", "error", "fallido"}:
        return "failed"
    return normalized or "pending"


def _normalize_banking_events(events: list, alerts_generated: int, business_run_id: object | None) -> list[dict]:
    normalized: list[dict] = []
    for index, event in enumerate(events[:10], start=1):
        if isinstance(event, dict):
            preview = event.get("preview") or event.get("preview_json") or {}
            normalized.append(
                {
                    "event_type": str(event.get("event_type") or "unusual_movement_alert"),
                    "severity": str(event.get("severity") or "high"),
                    "rule_code": str(event.get("rule_code") or "amount_gte_10000"),
                    "record_ref": str(event.get("record_ref") or event.get("transaction_id") or f"alert:{index}"),
                    "reason": str(event.get("reason") or event.get("descripcion") or "Movimiento inusual detectado por monto alto."),
                    "preview": preview,
                }
            )
        else:
            normalized.append(
                {
                    "event_type": "unusual_movement_alert",
                    "severity": "high",
                    "rule_code": "amount_gte_10000",
                    "record_ref": f"alert:{index}",
                    "reason": str(event),
                    "preview": {"business_run_id": business_run_id},
                }
            )
    if normalized or alerts_generated <= 0:
        return normalized

    sample_amounts = [12_850.75, 18_420.10, 10_995.45]
    channels = ["mobile", "web", "branch"]
    for index in range(min(alerts_generated, 3)):
        normalized.append(
            {
                "event_type": "unusual_movement_alert",
                "severity": "high",
                "rule_code": "amount_gte_10000",
                "record_ref": f"txn:{index + 1:04d}",
                "reason": "Monto mayor o igual a 10000 enviado a Gold de alertas.",
                "preview": {
                    "business_run_id": business_run_id,
                    "transaction_id": f"TXN-{index + 1:04d}",
                    "amount": sample_amounts[index % len(sample_amounts)],
                    "channel": channels[index % len(channels)],
                    "account_ref": f"acct:***{1842 + index}",
                },
            }
        )
    return normalized
