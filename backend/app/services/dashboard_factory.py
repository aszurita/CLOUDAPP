from __future__ import annotations

import base64
import re
import json
import time
from contextlib import contextmanager
from datetime import datetime
from functools import lru_cache
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.models.dashboard_factory import Dashboard, GoldFactoryRequestRecord
from app.services.ai import AIConfigurationError, AIRecommendationService

# ── Keyword maps ──────────────────────────────────────────────────────────────

_TABLE_MAP: dict[str, str] = {
    "venta": "ventas",
    "sale": "ventas",
    "cliente": "clientes",
    "customer": "clientes",
    "movimiento": "movimientos",
    "movement": "movimientos",
    "calidad": "calidad_datos",
    "quality": "calidad_datos",
    "costo": "costos",
    "cost": "costos",
    "financiero": "financiero",
    "financial": "financiero",
    "inventario": "inventario",
    "inventory": "inventario",
    "pedido": "pedidos",
    "order": "pedidos",
    "producto": "productos",
    "product": "productos",
    "rendimiento": "rendimiento",
    "performance": "rendimiento",
}

_METRIC_MAP: dict[str, tuple[str, str, str]] = {
    "total": ("COUNT", "*", "total_registros"),
    "suma": ("COUNT", "*", "total_registros"),
    "sum": ("COUNT", "*", "total_registros"),
    "promedio": ("COUNT", "*", "total_registros"),
    "average": ("COUNT", "*", "total_registros"),
    "avg": ("COUNT", "*", "total_registros"),
    "cantidad": ("COUNT", "*", "total_registros"),
    "count": ("COUNT", "*", "total_registros"),
    "conteo": ("COUNT", "*", "total_registros"),
    "maximo": ("COUNT", "*", "total_registros"),
    "máximo": ("COUNT", "*", "total_registros"),
    "minimo": ("COUNT", "*", "total_registros"),
    "mínimo": ("COUNT", "*", "total_registros"),
}

_DIMENSION_MAP: dict[str, str] = {
    "categoría": "categoria",
    "categoria": "categoria",
    "category": "categoria",
    "tienda": "tienda",
    "store": "tienda",
    "región": "region",
    "region": "region",
    "mes": "mes",
    "month": "mes",
    "año": "anio",
    "anio": "anio",
    "year": "anio",
    "fecha": "fecha",
    "date": "fecha",
    "producto": "producto",
    "product": "producto",
    "cliente": "cliente",
    "customer": "cliente",
    "ciudad": "ciudad",
    "city": "ciudad",
    "canal": "canal",
    "channel": "canal",
    "estado": "estado",
    "state": "estado",
    "tabla": "tabla",
    "table": "tabla",
    "dominio": "dominio",
    "domain": "dominio",
}

_YEAR_RE = re.compile(r"\b(20\d{2})\b")
_MONTH_RE = re.compile(
    r"\b(enero|febrero|marzo|abril|mayo|junio|julio|agosto"
    r"|septiembre|octubre|noviembre|diciembre)\b"
)
_TOP_RE = re.compile(r"\btop\s*(\d+)\b")

_TIME_DIMS = {"mes", "anio", "fecha"}
_BLOCKED_SQL_RE = re.compile(
    r"\b(create|insert|update|delete|drop|alter|merge|truncate|grant|revoke|copy|vacuum|optimize|restore)\b",
    re.IGNORECASE,
)
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{2,127}$")
_GOLD_TERMINAL_STATUSES = {"SUCCESS", "ERROR", "DEMO_SUCCESS"}


# ── Demo data for offline mode ────────────────────────────────────────────────

def _demo_kpi() -> tuple[list[str], list[list]]:
    return ["total_valor"], [["42,830"]]


def _demo_bar(x_field: str, y_field: str) -> tuple[list[str], list[list]]:
    labels = ["Electrónica", "Ropa", "Hogar", "Deportes", "Alimentos"]
    values = [45200, 32100, 28700, 19500, 14300]
    return [x_field, y_field], [[l, v] for l, v in zip(labels, values)]


def _demo_line(x_field: str, y_field: str) -> tuple[list[str], list[list]]:
    months = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
    values = [12000, 14500, 11800, 16300, 18900, 15200, 17400, 19100, 16800, 21000, 23500, 28000]
    return [x_field, y_field], [[m, v] for m, v in zip(months, values)]


def _demo_pie(x_field: str, y_field: str) -> tuple[list[str], list[list]]:
    return _demo_bar(x_field, y_field)


def _demo_table(columns: list[str]) -> tuple[list[str], list[list]]:
    rows = [
        ["Ejemplo 1", "100", "Activo"],
        ["Ejemplo 2", "250", "Activo"],
        ["Ejemplo 3", "75", "Inactivo"],
        ["Ejemplo 4", "310", "Activo"],
        ["Ejemplo 5", "190", "Activo"],
    ]
    adjusted: list[list] = []
    for row in rows:
        adjusted.append(row[: len(columns)] + ["—"] * max(0, len(columns) - len(row)))
    return columns, adjusted


# ── Service ───────────────────────────────────────────────────────────────────


class DashboardFactoryService:
    def __init__(self) -> None:
        self.settings = get_settings()

    # ── Public methods ────────────────────────────────────────────────────────

    def get_status(self, db: Session) -> dict[str, Any]:
        total = db.query(Dashboard).count()
        return {
            "title": "AI Gold Factory",
            "databricks_configured": self._databricks_ready(),
            "warehouse_id": self.settings.databricks_sql_warehouse_id,
            "catalog": self.settings.databricks_catalog,
            "total_dashboards": total,
        }

    @contextmanager
    def _gold_history_session(self, fallback_db: Session):
        if not self.settings.gold_factory_database_url:
            yield fallback_db
            return

        engine = _gold_history_engine(self.settings.gold_factory_database_url)
        _ensure_gold_request_table(engine)
        session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        history_db = session_factory()
        try:
            yield history_db
        finally:
            history_db.close()

    def plan_gold_request(
        self,
        prompt: str,
        target_catalog: str,
        target_schema: str,
        object_type: str,
    ) -> dict[str, Any]:
        catalog = self._catalog_snapshot(target_catalog)
        similar = self._similar_assets(prompt, catalog)
        context = {
            "user_prompt": prompt,
            "target_catalog": target_catalog,
            "target_schema": target_schema,
            "requested_object_type": object_type,
            "rules": [
                "Preferir tablas Silver como fuente para crear Gold de reporting.",
                "Reutilizar Gold existente si ya resuelve la necesidad.",
                "source_sql debe ser solo SELECT.",
                "No inventar columnas ni tablas.",
            ],
            "similar_assets": similar,
            "catalog": catalog[:80],
        }
        plan = self._ai_gold_plan(context) or self._heuristic_gold_plan(prompt, target_catalog, target_schema, object_type, catalog)
        plan["object_type"] = "VIEW" if str(plan.get("object_type")).upper() == "VIEW" else "TABLE"
        plan["target_catalog"] = str(plan.get("target_catalog") or target_catalog)
        plan["target_schema"] = str(plan.get("target_schema") or target_schema)
        plan["target_name"] = self._safe_target_name(str(plan.get("target_name") or self._target_name_from_prompt(prompt)))
        plan["source_sql"] = str(plan.get("source_sql") or "").strip().rstrip(";")
        plan["source_tables"] = [str(t) for t in plan.get("source_tables", [])][:12]
        plan["source_sql"] = self._repair_gold_source_sql(plan["source_sql"], plan, catalog)
        plan["generated_sql"] = self._build_materialization_sql(
            plan["source_sql"],
            plan["target_catalog"],
            plan["target_schema"],
            plan["target_name"],
            plan["object_type"],
            "OR_REPLACE",
        )

        messages = self._validate_gold_plan(plan, catalog)
        dry_run_ok = False
        if not messages and self._databricks_ready() and self.settings.databricks_sql_warehouse_id:
            try:
                self._execute_sql(f"SELECT * FROM ({plan['source_sql']}) q LIMIT 10")
                dry_run_ok = True
            except Exception as exc:
                messages.append(f"Dry-run falló en Databricks: {str(exc)[:260]}")

        validation_status = "APPROVED" if not messages else "NEEDS_REVIEW"
        return {
            "decision": str(plan.get("decision") or "CREATE_NEW_TABLE"),
            "object_type": plan["object_type"],
            "target_catalog": plan["target_catalog"],
            "target_schema": plan["target_schema"],
            "target_name": plan["target_name"],
            "source_tables": plan["source_tables"],
            "source_sql": plan["source_sql"],
            "generated_sql": plan["generated_sql"],
            "explanation": str(plan.get("explanation") or "Propuesta generada desde el catálogo disponible."),
            "validation_status": validation_status,
            "validation_messages": messages or ["SELECT validado para registrar la solicitud."],
            "dry_run_ok": dry_run_ok,
            "confidence": float(plan.get("confidence") or 0.65),
        }

    def submit_gold_request(
        self,
        prompt: str,
        plan: dict[str, Any],
        write_mode: str,
        created_by: str,
        db: Session,
    ) -> dict[str, Any]:
        catalog = self._catalog_snapshot(str(plan["target_catalog"]))
        plan = dict(plan)
        plan["source_sql"] = self._repair_gold_source_sql(str(plan["source_sql"]), plan, catalog)
        messages = self._validate_gold_plan(plan, catalog)
        if messages:
            raise ValueError("; ".join(messages))
        request_id = int(time.time() * 1000)
        generated_sql = self._build_materialization_sql(
            str(plan["source_sql"]),
            str(plan["target_catalog"]),
            str(plan["target_schema"]),
            str(plan["target_name"]),
            str(plan["object_type"]),
            write_mode,
        )
        with self._gold_history_session(db) as history_db:
            record = self._create_gold_request_record(
                request_id=request_id,
                prompt=prompt,
                plan=plan,
                write_mode=write_mode,
                created_by=created_by,
                generated_sql=generated_sql,
                status="PENDING",
            )
            history_db.add(record)
            history_db.commit()
            history_db.refresh(record)

            if self._databricks_ready() and self.settings.databricks_sql_warehouse_id:
                record.databricks_job_id = str(self.settings.databricks_gold_factory_job_id)
                record.updated_at = datetime.utcnow()
                history_db.commit()
                try:
                    self._insert_control_request(
                        request_id=request_id,
                        prompt=prompt,
                        plan=plan,
                        write_mode=write_mode,
                        created_by=created_by,
                        generated_sql=generated_sql,
                    )
                    run = self._start_gold_factory_job(request_id)
                except Exception as exc:
                    record.status = "ERROR"
                    record.error_message = f"No se pudo iniciar el Job Gold en Databricks: {str(exc)[:500]}"
                    record.finished_at = datetime.utcnow()
                    record.updated_at = datetime.utcnow()
                    history_db.commit()
                    history_db.refresh(record)
                    return {
                        "request_id": request_id,
                        "status": record.status,
                        "databricks_job_id": record.databricks_job_id,
                        "databricks_run_id": record.databricks_run_id,
                        "databricks_run_url": record.databricks_run_url,
                        "target_table": self._target_table_for_record(record),
                        "message": record.error_message,
                    }

                databricks_run_id = str(run.get("run_id") or "").strip()
                databricks_run_url = str(run.get("run_page_url") or "").strip()
                if not databricks_run_url:
                    try:
                        databricks_run_url = self._build_gold_run_url(databricks_run_id) or ""
                    except Exception as exc:
                        databricks_run_url = ""
                        record.sync_error = f"No se pudo construir URL del run: {str(exc)[:300]}"
                record.databricks_run_id = databricks_run_id or None
                record.databricks_run_url = databricks_run_url or None
                record.databricks_job_id = str(self.settings.databricks_gold_factory_job_id)
                record.status = "PENDING"
                record.updated_at = datetime.utcnow()
                history_db.commit()
                return {
                    "request_id": request_id,
                    "status": "PENDING",
                    "databricks_job_id": record.databricks_job_id,
                    "databricks_run_id": databricks_run_id or None,
                    "databricks_run_url": databricks_run_url or None,
                    "target_table": f"{plan['target_catalog']}.{plan['target_schema']}.{plan['target_name']}",
                    "message": "Solicitud registrada, guardada en Postgres y Job de Databricks iniciado.",
                }
            record.status = "DEMO_SUCCESS"
            record.databricks_run_url = "local-demo://databricks/gold-factory"
            record.finished_at = datetime.utcnow()
            record.updated_at = datetime.utcnow()
            history_db.commit()
            return {
                "request_id": request_id,
                "status": "DEMO_SUCCESS",
                "databricks_job_id": None,
                "databricks_run_id": None,
                "databricks_run_url": "local-demo://databricks/gold-factory",
                "target_table": f"{plan['target_catalog']}.{plan['target_schema']}.{plan['target_name']}",
                "message": "Databricks no está configurado; se guardó una solicitud de demo en Postgres.",
            }

    def get_gold_request_status(self, request_id: int, db: Session) -> dict[str, Any] | None:
        with self._gold_history_session(db) as history_db:
            record = (
                history_db.query(GoldFactoryRequestRecord)
                .filter(GoldFactoryRequestRecord.request_id == request_id)
                .first()
            )
            if record:
                self._sync_gold_request_record(history_db, record)
                history_db.commit()
                history_db.refresh(record)
                return self._gold_record_to_status(record)

            if self._databricks_ready() and self.settings.databricks_sql_warehouse_id:
                try:
                    remote = self._fetch_remote_gold_request_status(request_id)
                except Exception:
                    remote = None
                if remote:
                    record = self._upsert_gold_record_from_remote(history_db, remote)
                    history_db.commit()
                    return self._gold_record_to_status(record)
            return None

    def list_gold_request_history(self, db: Session, limit: int = 50) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 100))
        with self._gold_history_session(db) as history_db:
            records = (
                history_db.query(GoldFactoryRequestRecord)
                .order_by(GoldFactoryRequestRecord.created_at.desc())
                .limit(limit)
                .all()
            )
            if self._databricks_ready() and self.settings.databricks_sql_warehouse_id:
                try:
                    for item in self._fetch_remote_gold_history(limit):
                        self._upsert_gold_record_from_remote(history_db, item)
                    history_db.commit()
                except Exception:
                    pass
                records = (
                    history_db.query(GoldFactoryRequestRecord)
                    .order_by(GoldFactoryRequestRecord.created_at.desc())
                    .limit(limit)
                    .all()
                )

            for record in records[:10]:
                self._sync_gold_request_record(history_db, record)
            history_db.commit()
            return [self._gold_record_to_status(record) for record in records]

    def _fetch_remote_gold_request_status(self, request_id: int) -> dict[str, Any] | None:
        table = self._primary_control_table_name()
        sql = f"""
SELECT
  request_id,
  status,
  user_prompt,
  target_catalog,
  target_schema,
  target_name,
  object_type,
  write_mode,
  created_by,
  source_sql,
  error_message,
  generated_sql,
  CAST(created_at AS STRING) AS created_at,
  CAST(started_at AS STRING) AS started_at,
  CAST(finished_at AS STRING) AS finished_at
FROM {table}
WHERE request_id = {request_id}
LIMIT 1
"""
        _, rows = self._execute_sql(sql, wait_timeout="10s", timeout_seconds=15)
        if not rows:
            return None
        return self._remote_gold_status_from_row(rows[0])

    def _fetch_remote_gold_history(self, limit: int) -> list[dict[str, Any]]:
        table = self._primary_control_table_name()
        sql = f"""
SELECT
  request_id,
  status,
  user_prompt,
  target_catalog,
  target_schema,
  target_name,
  object_type,
  write_mode,
  created_by,
  source_sql,
  error_message,
  generated_sql,
  CAST(created_at AS STRING) AS created_at,
  CAST(started_at AS STRING) AS started_at,
  CAST(finished_at AS STRING) AS finished_at
FROM {table}
ORDER BY created_at DESC
LIMIT {limit}
"""
        _, rows = self._execute_sql(sql, wait_timeout="10s", timeout_seconds=15)
        return [self._remote_gold_status_from_row(row) for row in rows]

    def _remote_gold_status_from_row(self, row: list) -> dict[str, Any]:
        target_table = f"{row[3]}.{row[4]}.{row[5]}"
        row_count: int | None = None
        if str(row[1]).upper() == "SUCCESS":
            try:
                _, count_rows = self._execute_sql(
                    f"SELECT COUNT(*) AS total FROM {target_table}",
                    wait_timeout="10s",
                    timeout_seconds=15,
                )
                if count_rows:
                    row_count = int(count_rows[0][0])
            except Exception:
                row_count = None

        return {
            "request_id": int(row[0]),
            "status": str(row[1]).upper(),
            "prompt": row[2],
            "target_table": target_table,
            "target_catalog": row[3],
            "target_schema": row[4],
            "target_name": row[5],
            "object_type": str(row[6]),
            "write_mode": str(row[7]),
            "created_by": row[8],
            "source_sql": row[9],
            "row_count": row_count,
            "error_message": row[10],
            "generated_sql": row[11],
            "created_at": row[12],
            "started_at": row[13],
            "finished_at": row[14],
        }

    def _create_gold_request_record(
        self,
        request_id: int,
        prompt: str,
        plan: dict[str, Any],
        write_mode: str,
        created_by: str,
        generated_sql: str,
        status: str,
    ) -> GoldFactoryRequestRecord:
        now = datetime.utcnow()
        return GoldFactoryRequestRecord(
            request_id=request_id,
            user_prompt=prompt,
            target_catalog=str(plan["target_catalog"]),
            target_schema=str(plan["target_schema"]),
            target_name=str(plan["target_name"]),
            object_type=str(plan["object_type"]),
            write_mode=write_mode,
            status=status,
            created_by=created_by,
            source_tables_json=[str(item) for item in plan.get("source_tables", [])],
            validation_messages_json=[str(item) for item in plan.get("validation_messages", [])],
            raw_plan_json=plan,
            source_sql=str(plan["source_sql"]),
            generated_sql=generated_sql,
            validation_status=str(plan.get("validation_status")) if plan.get("validation_status") else None,
            ai_explanation=str(plan.get("explanation")) if plan.get("explanation") else None,
            confidence=str(plan.get("confidence")) if plan.get("confidence") is not None else None,
            databricks_job_id=None,
            created_at=now,
            updated_at=now,
        )

    def _sync_gold_request_record(self, db: Session, record: GoldFactoryRequestRecord) -> None:
        if not self._databricks_ready() or not self.settings.databricks_sql_warehouse_id:
            return
        if record.status in _GOLD_TERMINAL_STATUSES and not (
            record.status == "SUCCESS" and record.row_count is None and record.object_type.upper() != "VIEW"
        ):
            self._restore_local_gold_sql(record)
            if not record.databricks_run_id or not record.databricks_run_url:
                try:
                    self._ensure_gold_job_reference(record)
                    db.flush()
                except Exception as exc:
                    record.sync_error = f"No se pudo recuperar run_id de Databricks: {str(exc)[:300]}"
            return
        try:
            remote = self._fetch_remote_gold_request_status(record.request_id)
            if remote:
                self._apply_remote_gold_status(record, remote)
                self._ensure_gold_job_reference(record)
                db.flush()
                return
        except Exception as exc:
            record.sync_error = f"No se pudo leer dataops_requests: {str(exc)[:500]}"

        try:
            self._ensure_gold_job_reference(record)
            job_state = self._fetch_gold_job_state(record.databricks_run_id)
            if job_state:
                self._apply_gold_job_state(record, job_state)
        except Exception as exc:
            record.sync_error = f"{record.sync_error or 'No se pudo consultar estado'}; Jobs API: {str(exc)[:300]}"
        record.updated_at = datetime.utcnow()
        db.flush()

    def _upsert_gold_record_from_remote(
        self, db: Session, remote: dict[str, Any]
    ) -> GoldFactoryRequestRecord:
        record = (
            db.query(GoldFactoryRequestRecord)
            .filter(GoldFactoryRequestRecord.request_id == int(remote["request_id"]))
            .first()
        )
        if not record:
            record = GoldFactoryRequestRecord(
                request_id=int(remote["request_id"]),
                user_prompt=str(remote.get("prompt") or "Solicitud Gold importada desde Databricks."),
                target_catalog=str(remote.get("target_catalog") or ""),
                target_schema=str(remote.get("target_schema") or ""),
                target_name=str(remote.get("target_name") or ""),
                object_type=str(remote.get("object_type") or "TABLE"),
                write_mode=str(remote.get("write_mode") or "OR_REPLACE"),
                status=str(remote.get("status") or "UNKNOWN"),
                created_by=str(remote.get("created_by") or "databricks"),
                source_tables_json=[],
                validation_messages_json=[],
                raw_plan_json={},
                source_sql=str(remote.get("source_sql") or ""),
                generated_sql=str(remote.get("generated_sql") or ""),
                databricks_job_id=str(self.settings.databricks_gold_factory_job_id)
                if self.settings.databricks_gold_factory_job_id
                else None,
                created_at=_parse_optional_datetime(remote.get("created_at")) or datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            db.add(record)
            db.flush()
        self._apply_remote_gold_status(record, remote)
        db.flush()
        return record

    def _apply_remote_gold_status(self, record: GoldFactoryRequestRecord, remote: dict[str, Any]) -> None:
        record.status = str(remote.get("status") or record.status).upper()
        record.user_prompt = str(remote.get("prompt") or record.user_prompt)
        record.target_catalog = str(remote.get("target_catalog") or record.target_catalog)
        record.target_schema = str(remote.get("target_schema") or record.target_schema)
        record.target_name = str(remote.get("target_name") or record.target_name)
        record.object_type = str(remote.get("object_type") or record.object_type)
        record.write_mode = str(remote.get("write_mode") or record.write_mode)
        record.created_by = str(remote.get("created_by") or record.created_by)
        if not self._restore_local_gold_sql(record):
            record.source_sql = str(remote.get("source_sql") or record.source_sql)
            record.generated_sql = str(remote.get("generated_sql") or record.generated_sql)
        record.row_count = remote.get("row_count") if remote.get("row_count") is not None else record.row_count
        record.error_message = remote.get("error_message") or record.error_message
        record.created_at = _parse_optional_datetime(remote.get("created_at")) or record.created_at
        record.started_at = _parse_optional_datetime(remote.get("started_at")) or record.started_at
        record.finished_at = _parse_optional_datetime(remote.get("finished_at")) or record.finished_at
        if record.status == "RUNNING" and not record.started_at:
            record.started_at = datetime.utcnow()
        if record.status in _GOLD_TERMINAL_STATUSES and not record.finished_at:
            record.finished_at = datetime.utcnow()
        record.sync_error = None
        record.updated_at = datetime.utcnow()

    def _restore_local_gold_sql(self, record: GoldFactoryRequestRecord) -> bool:
        if not isinstance(record.raw_plan_json, dict):
            return False
        local_source_sql = str(record.raw_plan_json.get("source_sql") or "").strip()
        if not local_source_sql:
            return False
        record.source_sql = local_source_sql
        record.generated_sql = self._build_materialization_sql(
            local_source_sql,
            record.target_catalog,
            record.target_schema,
            record.target_name,
            record.object_type,
            record.write_mode,
        )
        return True

    def _fetch_gold_job_state(self, databricks_run_id: str | None) -> dict[str, Any] | None:
        if not databricks_run_id:
            return None
        import httpx

        host = str(self.settings.databricks_host).rstrip("/")
        with httpx.Client(timeout=8, trust_env=False) as client:
            response = client.get(
                f"{host}/api/2.1/jobs/runs/get",
                headers=self._headers(),
                params={"run_id": databricks_run_id},
            )
        response.raise_for_status()
        return response.json()

    def _ensure_gold_job_reference(self, record: GoldFactoryRequestRecord) -> None:
        if record.databricks_run_id and record.databricks_run_url:
            return
        run_info = self._find_gold_job_run_for_request(record.request_id)
        if not run_info:
            return
        if run_info.get("run_id") and not record.databricks_run_id:
            record.databricks_run_id = str(run_info["run_id"])
        if run_info.get("run_page_url") and not record.databricks_run_url:
            record.databricks_run_url = str(run_info["run_page_url"])
        self._apply_gold_job_state(record, run_info)

    def _find_gold_job_run_for_request(self, request_id: int) -> dict[str, Any] | None:
        if not self.settings.databricks_gold_factory_job_id:
            return None
        import httpx

        host = str(self.settings.databricks_host).rstrip("/")
        with httpx.Client(timeout=12, trust_env=False) as client:
            response = client.get(
                f"{host}/api/2.1/jobs/runs/list",
                headers=self._headers(),
                params={
                    "job_id": int(self.settings.databricks_gold_factory_job_id),
                    "limit": 25,
                    "expand_tasks": "true",
                },
            )
        response.raise_for_status()
        request_id_text = str(request_id)
        for run in response.json().get("runs", []):
            if _gold_run_has_request_id(run, request_id_text):
                return run
        return None

    def _apply_gold_job_state(self, record: GoldFactoryRequestRecord, run_info: dict[str, Any]) -> None:
        state = run_info.get("state") or {}
        life_cycle = str(state.get("life_cycle_state") or "").upper()
        result = str(state.get("result_state") or "").upper()
        state_message = str(state.get("state_message") or "").strip()

        if run_info.get("run_page_url"):
            record.databricks_run_url = str(run_info["run_page_url"])
        if run_info.get("run_id") and not record.databricks_run_id:
            record.databricks_run_id = str(run_info["run_id"])

        if life_cycle in {"PENDING", "QUEUED", "BLOCKED", "RUNNING", "TERMINATING", "WAITING_FOR_RETRY"}:
            record.status = "RUNNING" if life_cycle != "PENDING" else "PENDING"
            record.started_at = record.started_at or datetime.utcnow()
            return

        if life_cycle in {"TERMINATED", "SKIPPED", "INTERNAL_ERROR"}:
            if result == "SUCCESS":
                record.status = "SUCCESS"
                record.error_message = None
                if record.row_count is None:
                    record.row_count = self._count_gold_target_rows(record)
            else:
                record.status = "ERROR"
                record.error_message = state_message or result or life_cycle
            record.finished_at = record.finished_at or datetime.utcnow()

    def _count_gold_target_rows(self, record: GoldFactoryRequestRecord) -> int | None:
        if record.object_type.upper() == "VIEW":
            return None
        try:
            _, rows = self._execute_sql(
                f"SELECT COUNT(*) AS total FROM {self._target_table_for_record(record)}",
                wait_timeout="10s",
                timeout_seconds=15,
            )
            return int(rows[0][0]) if rows else None
        except Exception:
            return None

    def _target_table_for_record(self, record: GoldFactoryRequestRecord) -> str:
        return f"{record.target_catalog}.{record.target_schema}.{record.target_name}"

    def _gold_record_to_status(self, record: GoldFactoryRequestRecord) -> dict[str, Any]:
        return {
            "request_id": record.request_id,
            "status": record.status,
            "target_table": self._target_table_for_record(record),
            "object_type": record.object_type,
            "write_mode": record.write_mode,
            "prompt": record.user_prompt,
            "created_by": record.created_by,
            "source_tables": list(record.source_tables_json or []),
            "validation_status": record.validation_status,
            "validation_messages": list(record.validation_messages_json or []),
            "databricks_job_id": record.databricks_job_id,
            "databricks_run_id": record.databricks_run_id,
            "databricks_run_url": record.databricks_run_url,
            "row_count": record.row_count,
            "error_message": record.error_message,
            "sync_error": record.sync_error,
            "generated_sql": record.generated_sql,
            "created_at": _datetime_to_string(record.created_at),
            "started_at": _datetime_to_string(record.started_at),
            "finished_at": _datetime_to_string(record.finished_at),
        }

    def plan_dashboard(
        self,
        prompt: str,
        catalog: str,
        schema_name: str,
        table: str | None,
    ) -> dict[str, Any]:
        p = prompt.lower()

        # Auto-discover real table from Databricks when none is explicitly selected
        resolved_table = table
        if not resolved_table and self._databricks_ready():
            try:
                avail = self._fetch_tables(catalog, schema_name)
                if avail:
                    kw_name = self._detect_tables(p, None)[0]
                    matched = next(
                        (t["name"] for t in avail
                         if kw_name in t["name"].lower() or t["name"].lower() in kw_name),
                        None,
                    )
                    resolved_table = matched or avail[0]["name"]
            except Exception:
                pass

        tables = self._detect_tables(p, resolved_table)
        metrics = self._detect_metrics(p)
        dimensions = self._detect_dimensions(p)
        time_dims = [d for d in dimensions if d in _TIME_DIMS]
        cat_dims = [d for d in dimensions if d not in _TIME_DIMS]
        filters = self._detect_filters(p)
        analysis_type = self._detect_analysis_type(p)
        top_n = self._detect_top_n(p)
        main_table = tables[0]
        full_table = f"`{catalog}`.`{schema_name}`.`{main_table}`"
        fn, col, alias = self._primary_metric(metrics)
        where = self._where_clause(filters)

        queries: list[dict] = []
        widgets: list[dict] = []

        # ── Always: 1 KPI ──────────────────────────────────────────────────
        kpi_sql = f"SELECT {fn}({col}) AS {alias} FROM {full_table}{where} LIMIT 1"
        queries.append({"id": "q_kpi", "purpose": f"Total de {alias.replace('_', ' ')}", "sql": kpi_sql})
        widgets.append({
            "id": "w_kpi",
            "type": "kpi",
            "title": alias.replace("_", " ").title(),
            "query_id": "q_kpi",
            "value_field": alias,
            "col_span": 1,
        })

        # ── Time dimension → line chart ────────────────────────────────────
        if time_dims:
            tc = time_dims[0]
            order = "ASC"
            line_sql = (
                f"SELECT {tc}, {fn}({col}) AS {alias}\n"
                f"FROM {full_table}{where}\n"
                f"GROUP BY {tc}\n"
                f"ORDER BY {tc} {order}\n"
                f"LIMIT 100"
            )
            queries.append({"id": "q_line", "purpose": f"Evolución por {tc}", "sql": line_sql})
            widgets.append({
                "id": "w_line",
                "type": "line_chart",
                "title": f"Evolución por {tc.title()}",
                "query_id": "q_line",
                "x_field": tc,
                "y_field": alias,
                "col_span": 2,
            })

        # ── Category dimension → bar chart ─────────────────────────────────
        if cat_dims:
            cc = cat_dims[0]
            limit = top_n or 20
            bar_sql = (
                f"SELECT {cc}, {fn}({col}) AS {alias}\n"
                f"FROM {full_table}{where}\n"
                f"GROUP BY {cc}\n"
                f"ORDER BY {alias} DESC\n"
                f"LIMIT {limit}"
            )
            queries.append({"id": "q_bar", "purpose": f"Distribución por {cc}", "sql": bar_sql})
            widgets.append({
                "id": "w_bar",
                "type": "bar_chart",
                "title": f"Por {cc.replace('_', ' ').title()}",
                "query_id": "q_bar",
                "x_field": cc,
                "y_field": alias,
                "col_span": 2,
            })

            # Second category → pie chart (only if no time dim and 2+ cat dims)
            if len(cat_dims) >= 2 and not time_dims:
                cc2 = cat_dims[1]
                pie_sql = (
                    f"SELECT {cc2}, {fn}({col}) AS {alias}\n"
                    f"FROM {full_table}{where}\n"
                    f"GROUP BY {cc2}\n"
                    f"ORDER BY {alias} DESC\n"
                    f"LIMIT 10"
                )
                queries.append({"id": "q_pie", "purpose": f"Distribución por {cc2}", "sql": pie_sql})
                widgets.append({
                    "id": "w_pie",
                    "type": "pie_chart",
                    "title": f"Distribución por {cc2.replace('_', ' ').title()}",
                    "query_id": "q_pie",
                    "x_field": cc2,
                    "y_field": alias,
                    "col_span": 2,
                })

        # ── Always: detail table ───────────────────────────────────────────
        t_limit = top_n or 50
        table_sql = f"SELECT *\nFROM {full_table}{where}\nLIMIT {t_limit}"
        queries.append({"id": "q_table", "purpose": "Tabla de detalle", "sql": table_sql})
        widgets.append({
            "id": "w_table",
            "type": "table",
            "title": "Tabla de Detalle",
            "query_id": "q_table",
            "col_span": 4,
        })

        title = self._build_name(prompt, tables)
        schema = {
            "title": title,
            "description": f"Dashboard generado a partir de: {prompt}",
            "catalog": catalog,
            "schema_name": schema_name,
            "queries": queries,
            "widgets": widgets,
            "filters": [],
        }
        return {"dashboard_schema": schema, "analysis_type": analysis_type, "detected_tables": tables}

    def generate_dashboard(
        self,
        prompt: str,
        catalog: str,
        schema_name: str,
        dashboard_schema: dict,
        db: Session,
    ) -> dict[str, Any]:
        now = datetime.utcnow()
        record = Dashboard(
            name=dashboard_schema.get("title", prompt[:120]),
            description=dashboard_schema.get("description"),
            prompt_original=prompt,
            catalog_name=catalog,
            schema_name=schema_name,
            dashboard_schema=dashboard_schema,
            status="active",
            version=1,
            created_at=now,
            updated_at=now,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return {
            "id": record.id,
            "name": record.name,
            "status": "active",
            "message": "Dashboard guardado correctamente.",
        }

    def execute_dashboard(self, dashboard_id: int, db: Session) -> dict[str, Any]:
        record = db.get(Dashboard, dashboard_id)
        if not record:
            return {}
        schema = record.dashboard_schema
        queries: list[dict] = schema.get("queries", [])
        widgets: list[dict] = schema.get("widgets", [])
        demo_mode = not self._databricks_ready()

        t0 = time.monotonic()
        results: list[dict] = []

        for widget in widgets:
            wid = widget["id"]
            qid = widget["query_id"]
            q = next((q for q in queries if q["id"] == qid), None)
            if q is None:
                results.append({"widget_id": wid, "query_id": qid, "columns": [], "rows": [], "error": "Consulta no encontrada."})
                continue

            if demo_mode:
                cols, rows = self._demo_widget(widget)
                results.append({"widget_id": wid, "query_id": qid, "columns": cols, "rows": rows, "error": None})
            else:
                try:
                    cols, rows = self._execute_sql(q["sql"])
                    results.append({"widget_id": wid, "query_id": qid, "columns": cols, "rows": rows, "error": None})
                except Exception as exc:
                    results.append({"widget_id": wid, "query_id": qid, "columns": [], "rows": [], "error": str(exc)[:300]})

        elapsed_ms = int((time.monotonic() - t0) * 1000)
        return {
            "dashboard_id": dashboard_id,
            "results": results,
            "execution_time_ms": elapsed_ms,
            "demo_mode": demo_mode,
        }

    def list_dashboards(self, db: Session) -> dict[str, Any]:
        records = (
            db.query(Dashboard)
            .filter(Dashboard.status == "active")
            .order_by(Dashboard.created_at.desc())
            .all()
        )
        return {"total": len(records), "dashboards": [self._to_dict(r) for r in records]}

    def get_dashboard(self, dashboard_id: int, db: Session) -> dict[str, Any] | None:
        record = db.get(Dashboard, dashboard_id)
        return self._to_dict(record) if record else None

    def update_dashboard(
        self, dashboard_id: int, payload: dict[str, Any], db: Session
    ) -> dict[str, Any] | None:
        record = db.get(Dashboard, dashboard_id)
        if not record:
            return None
        if "name" in payload and payload["name"]:
            record.name = payload["name"]
        if "dashboard_schema" in payload and payload["dashboard_schema"]:
            record.dashboard_schema = payload["dashboard_schema"]
            record.version = record.version + 1
        record.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(record)
        return self._to_dict(record)

    def delete_dashboard(self, dashboard_id: int, db: Session) -> bool:
        record = db.get(Dashboard, dashboard_id)
        if not record:
            return False
        db.delete(record)
        db.commit()
        return True

    def get_catalogs(self) -> list[dict[str, str]]:
        if self._databricks_ready():
            try:
                return self._fetch_catalogs()
            except Exception:
                pass
        return [{"name": self.settings.databricks_catalog}]

    def get_schemas(self, catalog: str) -> list[dict[str, str]]:
        if self._databricks_ready():
            try:
                return self._fetch_schemas(catalog)
            except Exception:
                pass
        return [
            {"name": self.settings.databricks_schema_gold, "catalog_name": catalog},
            {"name": self.settings.databricks_schema_silver, "catalog_name": catalog},
            {"name": self.settings.databricks_schema_bronze, "catalog_name": catalog},
        ]

    def get_tables(self, catalog: str, schema: str) -> list[dict[str, str]]:
        if self._databricks_ready():
            try:
                return self._fetch_tables(catalog, schema)
            except Exception:
                pass
        return [
            {"name": t, "schema_name": schema, "catalog_name": catalog, "table_type": "TABLE"}
            for t in ["ventas", "clientes", "productos", "movimientos", "pedidos", "calidad_datos"]
        ]

    # ── Gold request factory ─────────────────────────────────────────────────

    def _catalog_snapshot(self, catalog: str) -> list[dict[str, Any]]:
        if self._databricks_ready() and self.settings.databricks_sql_warehouse_id:
            try:
                rows = self._query_catalog_columns(catalog)
                grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
                for row in rows:
                    key = (str(row[0]), str(row[1]), str(row[2]))
                    item = grouped.setdefault(
                        key,
                        {
                            "full_name": f"{row[0]}.{row[1]}.{row[2]}",
                            "catalog": row[0],
                            "schema": row[1],
                            "name": row[2],
                            "table_type": row[3],
                            "columns": [],
                        },
                    )
                    item["columns"].append({"name": row[4], "type": row[5]})
                return list(grouped.values())
            except Exception:
                pass
        return self._demo_catalog_snapshot(catalog)

    def _query_catalog_columns(self, catalog: str) -> list[list]:
        sql = f"""
SELECT
  table_catalog,
  table_schema,
  table_name,
  table_type,
  column_name,
  data_type
FROM system.information_schema.columns
WHERE table_catalog = '{catalog.replace("'", "''")}'
  AND table_schema IN ('raw','bronze','silver','gold','tpcds_bronze','tpcds_silver','tpcds_gold','banco_demo')
ORDER BY table_schema, table_name, ordinal_position
LIMIT 800
"""
        _, rows = self._execute_sql(sql)
        return rows

    def _demo_catalog_snapshot(self, catalog: str) -> list[dict[str, Any]]:
        silver = self.settings.databricks_schema_silver
        gold = self.settings.databricks_schema_gold
        return [
            {
                "full_name": f"{catalog}.{silver}.store_sales_clean",
                "catalog": catalog,
                "schema": silver,
                "name": "store_sales_clean",
                "table_type": "TABLE",
                "columns": [
                    {"name": "ss_sold_date_sk", "type": "BIGINT"},
                    {"name": "ss_item_sk", "type": "BIGINT"},
                    {"name": "ss_store_sk", "type": "BIGINT"},
                    {"name": "ss_quantity", "type": "INT"},
                    {"name": "ss_sales_price", "type": "DOUBLE"},
                ],
            },
            {
                "full_name": f"{catalog}.{self.settings.databricks_schema_bronze}.date_dim",
                "catalog": catalog,
                "schema": self.settings.databricks_schema_bronze,
                "name": "date_dim",
                "table_type": "TABLE",
                "columns": [
                    {"name": "d_date_sk", "type": "BIGINT"},
                    {"name": "d_year", "type": "INT"},
                    {"name": "d_moy", "type": "INT"},
                ],
            },
            {
                "full_name": f"{catalog}.{self.settings.databricks_schema_bronze}.item",
                "catalog": catalog,
                "schema": self.settings.databricks_schema_bronze,
                "name": "item",
                "table_type": "TABLE",
                "columns": [
                    {"name": "i_item_sk", "type": "BIGINT"},
                    {"name": "i_category", "type": "STRING"},
                    {"name": "i_product_name", "type": "STRING"},
                ],
            },
            {
                "full_name": f"{catalog}.{gold}.sales_by_year_category",
                "catalog": catalog,
                "schema": gold,
                "name": "sales_by_year_category",
                "table_type": "TABLE",
                "columns": [
                    {"name": "year", "type": "INT"},
                    {"name": "category", "type": "STRING"},
                    {"name": "total_sales", "type": "DOUBLE"},
                ],
            },
        ]

    def _similar_assets(self, prompt: str, catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
        tokens = {t for t in re.findall(r"[a-zA-Z0-9_áéíóúñ]+", prompt.lower()) if len(t) >= 4}
        scored: list[tuple[int, dict[str, Any]]] = []
        for item in catalog:
            haystack = " ".join(
                [str(item["name"]).lower(), str(item["schema"]).lower()]
                + [str(c["name"]).lower() for c in item.get("columns", [])]
            )
            score = sum(1 for token in tokens if token in haystack)
            if score:
                scored.append((score, item))
        return [item for _, item in sorted(scored, key=lambda pair: pair[0], reverse=True)[:10]]

    def _ai_gold_plan(self, context: dict[str, Any]) -> dict[str, Any] | None:
        try:
            raw = AIRecommendationService().generate_gold_table_plan(context)
            parsed = _parse_json_result(raw)
            return parsed if isinstance(parsed, dict) else None
        except AIConfigurationError:
            return None

    def _heuristic_gold_plan(
        self,
        prompt: str,
        target_catalog: str,
        target_schema: str,
        object_type: str,
        catalog: list[dict[str, Any]],
    ) -> dict[str, Any]:
        source = next((t for t in catalog if "silver" in str(t["schema"]).lower()), catalog[0])
        numeric = next((c["name"] for c in source["columns"] if any(k in c["type"].lower() for k in ("int", "double", "decimal", "bigint"))), None)
        dimension = next((c["name"] for c in source["columns"] if "string" in c["type"].lower()), None)
        if dimension and numeric:
            sql = (
                f"SELECT {dimension}, SUM({numeric}) AS total_{numeric}, COUNT(*) AS total_registros\n"
                f"FROM {source['full_name']}\n"
                f"GROUP BY {dimension}\n"
                f"ORDER BY total_{numeric} DESC"
            )
        else:
            sql = f"SELECT *\nFROM {source['full_name']}\nLIMIT 1000"
        return {
            "decision": "CREATE_NEW_VIEW" if object_type == "VIEW" else "CREATE_NEW_TABLE",
            "object_type": object_type,
            "target_catalog": target_catalog,
            "target_schema": target_schema,
            "target_name": self._target_name_from_prompt(prompt),
            "source_tables": [source["full_name"]],
            "source_sql": sql,
            "explanation": "Plan heurístico generado porque la IA no está configurada; usa una tabla disponible del catálogo.",
            "confidence": 0.45,
        }

    def _validate_gold_plan(self, plan: dict[str, Any], catalog: list[dict[str, Any]]) -> list[str]:
        messages: list[str] = []
        sql = str(plan.get("source_sql") or "").strip()
        if not sql.lower().startswith(("select", "with")):
            messages.append("source_sql debe iniciar con SELECT o WITH.")
        if _BLOCKED_SQL_RE.search(sql):
            messages.append("source_sql contiene una instrucción no permitida.")
        if ";" in sql.rstrip(";"):
            messages.append("source_sql no debe contener múltiples sentencias.")
        if str(plan.get("target_schema") or "").lower() not in {"gold", "tpcds_gold"} and "gold" not in str(plan.get("target_schema") or "").lower():
            messages.append("El destino debe ser un schema Gold para reportes.")
        if not _IDENTIFIER_RE.match(str(plan.get("target_name") or "")):
            messages.append("target_name debe ser snake_case válido.")
        known = {str(item["full_name"]).lower() for item in catalog}
        missing = [t for t in plan.get("source_tables", []) if str(t).lower() not in known]
        if missing:
            messages.append(f"Tablas fuente no encontradas en catálogo: {', '.join(missing[:5])}.")
        return messages

    def _repair_gold_source_sql(
        self,
        source_sql: str,
        plan: dict[str, Any],
        catalog: list[dict[str, Any]],
    ) -> str:
        sql = source_sql.strip().rstrip(";")
        if not sql:
            return sql

        known_columns = self._known_source_columns(plan, catalog)
        literal_tokens: set[str] = set()
        literal_aliases = (
            "table_name",
            "failed_rule",
            "rule_name",
            "quality_rule",
            "validation_rule",
        )
        for alias in literal_aliases:
            pattern = re.compile(
                rf"(?i)(\bSELECT\s+|,\s*)([A-Za-z_][A-Za-z0-9_]*)\s+AS\s+({alias})\b"
            )

            def replace_literal(match: re.Match[str]) -> str:
                token = match.group(2)
                if token.lower() in known_columns:
                    return match.group(0)
                literal_tokens.add(token)
                return f"{match.group(1)}'{token}' AS {match.group(3)}"

            sql = pattern.sub(replace_literal, sql)

        if literal_tokens:
            sql = _quote_group_by_literals(sql, literal_tokens)
        return sql

    def _known_source_columns(self, plan: dict[str, Any], catalog: list[dict[str, Any]]) -> set[str]:
        source_tables = {str(item).lower() for item in plan.get("source_tables", [])}
        columns: set[str] = set()
        for item in catalog:
            full_name = str(item.get("full_name") or "").lower()
            if source_tables and full_name not in source_tables:
                continue
            for column in item.get("columns", []):
                columns.add(str(column.get("name") or "").lower())
        return columns

    def _build_materialization_sql(
        self,
        source_sql: str,
        target_catalog: str,
        target_schema: str,
        target_name: str,
        object_type: str,
        write_mode: str,
    ) -> str:
        exists = "IF NOT EXISTS " if write_mode == "IF_NOT_EXISTS" else "OR REPLACE "
        kind = "VIEW" if object_type == "VIEW" else "TABLE"
        return f"CREATE {exists}{kind} {target_catalog}.{target_schema}.{target_name} AS\n{source_sql.strip().rstrip(';')}"

    def _safe_target_name(self, name: str) -> str:
        normalized = re.sub(r"[^a-zA-Z0-9_]+", "_", name.strip().lower())
        normalized = re.sub(r"_+", "_", normalized).strip("_")
        if not normalized or not normalized[0].isalpha():
            normalized = f"gold_{normalized or 'reporte'}"
        return normalized[:120]

    def _target_name_from_prompt(self, prompt: str) -> str:
        words = re.findall(r"[a-zA-Z0-9áéíóúñ]+", prompt.lower())
        stop = {"quiero", "crear", "tabla", "vista", "gold", "para", "dashboard", "reporte", "con", "por", "del", "de", "la", "el", "los", "las", "un", "una"}
        useful = [w for w in words if w not in stop][:8]
        return self._safe_target_name("_".join(useful) or "reporte_gold")

    def _insert_control_request(
        self,
        request_id: int,
        prompt: str,
        plan: dict[str, Any],
        write_mode: str,
        created_by: str,
        generated_sql: str,
    ) -> None:
        self._ensure_control_table()
        values = {
            "prompt": _sql_string_expr(prompt),
            "source_sql": _sql_string_expr(str(plan["source_sql"])),
            "target_catalog": _sql_string_expr(str(plan["target_catalog"])),
            "target_schema": _sql_string_expr(str(plan["target_schema"])),
            "target_name": _sql_string_expr(str(plan["target_name"])),
            "object_type": _sql_string_expr(str(plan["object_type"])),
            "write_mode": _sql_string_expr(write_mode),
            "created_by": _sql_string_expr(created_by),
            "generated_sql": _sql_string_expr(generated_sql),
        }
        for table in self._control_table_names():
            sql = f"""
INSERT INTO {table} (
  request_id, user_prompt, source_sql, target_catalog, target_schema, target_name,
  object_type, write_mode, status, created_by, created_at, started_at, finished_at,
  error_message, generated_sql
)
VALUES (
  {request_id}, {values["prompt"]}, {values["source_sql"]}, {values["target_catalog"]},
  {values["target_schema"]}, {values["target_name"]}, {values["object_type"]},
  {values["write_mode"]}, 'PENDING', {values["created_by"]}, current_timestamp(),
  NULL, NULL, NULL, {values["generated_sql"]}
)
"""
            self._execute_sql(sql)

    def _ensure_control_table(self) -> None:
        for table in self._control_table_names():
            parts = table.split(".")
            schema = ".".join(parts[:-1])
            if schema:
                self._execute_sql(f"CREATE SCHEMA IF NOT EXISTS {schema}")
            self._execute_sql(
                f"""
CREATE TABLE IF NOT EXISTS {table} (
  request_id BIGINT,
  user_prompt STRING,
  source_sql STRING,
  target_catalog STRING,
  target_schema STRING,
  target_name STRING,
  object_type STRING,
  write_mode STRING,
  status STRING,
  created_by STRING,
  created_at TIMESTAMP,
  started_at TIMESTAMP,
  finished_at TIMESTAMP,
  error_message STRING,
  generated_sql STRING
) USING DELTA
"""
            )

    def _control_table_names(self) -> list[str]:
        catalog = self.settings.databricks_control_catalog
        configured_schema = self.settings.databricks_control_schema
        table_name = self.settings.databricks_control_requests_table
        return [".".join(part for part in [catalog, configured_schema, table_name] if part)]

    def _primary_control_table_name(self) -> str:
        return self._control_table_names()[0]

    def _start_gold_factory_job(self, request_id: int) -> dict[str, Any]:
        import httpx

        host = str(self.settings.databricks_host).rstrip("/")
        notebook_params = {
            "request_id": str(request_id),
            "control_catalog": self.settings.databricks_control_catalog,
            "control_schema": self.settings.databricks_control_schema,
            "control_table": self.settings.databricks_control_requests_table,
            "catalog": self.settings.databricks_control_catalog,
            "schema": self.settings.databricks_control_schema,
            "requests_table": self.settings.databricks_control_requests_table,
        }
        with httpx.Client(timeout=20, trust_env=False) as client:
            response = client.post(
                f"{host}/api/2.1/jobs/run-now",
                headers=self._headers(),
                json={
                    "job_id": int(self.settings.databricks_gold_factory_job_id),
                    "notebook_params": notebook_params,
                },
            )
        response.raise_for_status()
        return response.json()

    def _build_gold_run_url(self, run_id: str) -> str | None:
        if not run_id:
            return None
        host = str(self.settings.databricks_host or "").rstrip("/")
        if not host:
            return None
        workspace_id = _workspace_id_from_host(host)
        org_part = f"?o={workspace_id}" if workspace_id else ""
        return f"{host}/{org_part}#job/{self.settings.databricks_gold_factory_job_id}/run/{run_id}"

    # ── Intent analysis ───────────────────────────────────────────────────────

    def _detect_tables(self, p: str, override: str | None) -> list[str]:
        if override:
            return [override]
        found: list[str] = []
        for kw, tbl in _TABLE_MAP.items():
            if kw in p and tbl not in found:
                found.append(tbl)
        return found or ["datos"]

    def _detect_metrics(self, p: str) -> list[str]:
        return [kw for kw in _METRIC_MAP if kw in p] or ["cantidad"]

    def _detect_dimensions(self, p: str) -> list[str]:
        found: list[str] = []
        for kw, col in _DIMENSION_MAP.items():
            if kw in p and col not in found:
                found.append(col)
        return found

    def _detect_filters(self, p: str) -> dict[str, str]:
        f: dict[str, str] = {}
        m = _YEAR_RE.search(p)
        if m:
            f["anio"] = m.group(1)
        mo = _MONTH_RE.search(p)
        if mo:
            f["mes"] = mo.group(1)
        return f

    def _detect_analysis_type(self, p: str) -> str:
        if any(w in p for w in ("evolución", "tendencia", "temporal", "tiempo", "trend")):
            return "temporal"
        if any(w in p for w in ("comparación", "comparar", "vs", "versus")):
            return "comparison"
        if any(w in p for w in ("top", "ranking", "mejor", "peor", "best", "worst")):
            return "ranking"
        if any(w in p for w in ("calidad", "quality", "completitud", "validez")):
            return "quality"
        return "summary"

    def _detect_top_n(self, p: str) -> int | None:
        m = _TOP_RE.search(p)
        return int(m.group(1)) if m else None

    def _primary_metric(self, metrics: list[str]) -> tuple[str, str, str]:
        for m in metrics:
            if m in _METRIC_MAP:
                fn, col, alias = _METRIC_MAP[m]
                return fn, col, alias
        return "COUNT", "*", "total_registros"

    def _where_clause(self, filters: dict[str, str]) -> str:
        if not filters:
            return ""
        parts = [f"{col} = '{val}'" for col, val in filters.items()]
        return "\nWHERE " + " AND ".join(parts)

    def _build_name(self, prompt: str, tables: list[str]) -> str:
        y = _YEAR_RE.search(prompt)
        suffix = f" {y.group(1)}" if y else ""
        base = prompt.strip()
        if len(base) > 70:
            tbl = tables[0].replace("_", " ").title()
            return f"Dashboard de {tbl}{suffix}"
        return base[:1].upper() + base[1:]

    # ── Databricks SQL execution ──────────────────────────────────────────────

    def _execute_sql(
        self,
        sql: str,
        wait_timeout: str = "50s",
        timeout_seconds: int = 60,
    ) -> tuple[list[str], list[list]]:
        import httpx

        if not self.settings.databricks_sql_warehouse_id:
            raise RuntimeError("DATABRICKS_SQL_WAREHOUSE_ID no configurado.")

        payload = {
            "warehouse_id": self.settings.databricks_sql_warehouse_id,
            "statement": sql,
            "wait_timeout": wait_timeout,
            "format": "JSON_ARRAY",
            "on_wait_timeout": "CANCEL",
        }
        with httpx.Client(timeout=timeout_seconds, trust_env=False) as client:
            resp = client.post(
                self._url("/api/2.0/sql/statements"),
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        state = data.get("status", {}).get("state", "")
        if state != "SUCCEEDED":
            err_msg = data.get("status", {}).get("error", {}).get("message", state)
            raise RuntimeError(f"Consulta falló ({state}): {err_msg[:300]}")

        schema_info = data.get("manifest", {}).get("schema", {})
        columns = [c["name"] for c in schema_info.get("columns", [])]
        rows = data.get("result", {}).get("data_array", [])
        return columns, rows

    def _demo_widget(self, widget: dict) -> tuple[list[str], list[list]]:
        wtype = widget.get("type", "table")
        x = widget.get("x_field", "dimensión")
        y = widget.get("y_field", "valor")
        if wtype == "kpi":
            return _demo_kpi()
        if wtype == "bar_chart":
            return _demo_bar(x, y)
        if wtype == "line_chart":
            return _demo_line(x, y)
        if wtype == "pie_chart":
            return _demo_pie(x, y)
        return _demo_table(["nombre", "valor", "estado"])

    # ── Databricks REST helpers ───────────────────────────────────────────────

    def _databricks_ready(self) -> bool:
        return bool(self.settings.databricks_host and self.settings.databricks_token)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.databricks_token}",
            "Content-Type": "application/json",
        }

    def _url(self, path: str) -> str:
        return f"{(self.settings.databricks_host or '').rstrip('/')}{path}"

    def _fetch_catalogs(self) -> list[dict[str, str]]:
        import httpx

        with httpx.Client(timeout=15, trust_env=False) as client:
            resp = client.get(self._url("/api/2.1/unity-catalog/catalogs"), headers=self._headers())
            resp.raise_for_status()
            return [{"name": c["name"]} for c in resp.json().get("catalogs", [])]

    def _fetch_schemas(self, catalog: str) -> list[dict[str, str]]:
        import httpx

        with httpx.Client(timeout=15, trust_env=False) as client:
            resp = client.get(
                self._url(f"/api/2.1/unity-catalog/schemas?catalog_name={catalog}"),
                headers=self._headers(),
            )
            resp.raise_for_status()
            return [{"name": s["name"], "catalog_name": catalog} for s in resp.json().get("schemas", [])]

    def _fetch_tables(self, catalog: str, schema: str) -> list[dict[str, str]]:
        import httpx

        with httpx.Client(timeout=15, trust_env=False) as client:
            resp = client.get(
                self._url(
                    f"/api/2.1/unity-catalog/tables?catalog_name={catalog}&schema_name={schema}"
                ),
                headers=self._headers(),
            )
            resp.raise_for_status()
            return [
                {
                    "name": t["name"],
                    "schema_name": schema,
                    "catalog_name": catalog,
                    "table_type": t.get("table_type", "TABLE"),
                }
                for t in resp.json().get("tables", [])
            ]

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _to_dict(r: Dashboard) -> dict[str, Any]:
        return {
            "id": r.id,
            "name": r.name,
            "description": r.description,
            "prompt_original": r.prompt_original,
            "catalog_name": r.catalog_name,
            "schema_name": r.schema_name,
            "dashboard_schema": r.dashboard_schema,
            "status": r.status,
            "version": r.version,
            "created_at": r.created_at,
            "updated_at": r.updated_at,
        }


def ensure_table() -> None:
    from app.db.session import engine
    from app.core.config import get_settings
    from app.models.dashboard_factory import Dashboard, DashboardGenerationHistory, GoldFactoryRequestRecord  # noqa: F401

    DashboardGenerationHistory.__table__.create(engine, checkfirst=True)
    Dashboard.__table__.create(engine, checkfirst=True)
    settings = get_settings()
    gold_engine = _gold_history_engine(settings.gold_factory_database_url) if settings.gold_factory_database_url else engine
    _ensure_gold_request_table(gold_engine)


@lru_cache
def _gold_history_engine(database_url: str):
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, pool_pre_ping=True, connect_args=connect_args)


def _ensure_gold_request_table(engine) -> None:
    GoldFactoryRequestRecord.__table__.create(engine, checkfirst=True)
    if engine.dialect.name == "postgresql":
        with engine.begin() as conn:
            conn.execute(
                text(
                    "ALTER TABLE gold_factory_requests "
                    "ALTER COLUMN request_id TYPE BIGINT"
                )
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


def _gold_run_has_request_id(value: Any, request_id: str) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "request_id" and str(item) == request_id:
                return True
            if _gold_run_has_request_id(item, request_id):
                return True
    if isinstance(value, list):
        return any(_gold_run_has_request_id(item, request_id) for item in value)
    return False


def _quote_group_by_literals(sql: str, literal_tokens: set[str]) -> str:
    group_by_re = re.compile(
        r"(?is)\bGROUP\s+BY\s+(.+?)(?=\s+UNION\s+ALL\b|\s+ORDER\s+BY\b|\s+LIMIT\b|$)"
    )

    def replace_group(match: re.Match[str]) -> str:
        group_expr = match.group(1)
        for token in literal_tokens:
            group_expr = re.sub(
                rf"(?<![\w.]){re.escape(token)}(?![\w.])",
                f"'{token}'",
                group_expr,
                flags=re.IGNORECASE,
            )
        return f"GROUP BY {group_expr}"

    return group_by_re.sub(replace_group, sql)


def _sql_string_expr(value: str) -> str:
    encoded = base64.b64encode(value.encode("utf-8")).decode("ascii")
    return f"CAST(unbase64('{encoded}') AS STRING)"


def _parse_optional_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
        return parsed.replace(tzinfo=None)
    except ValueError:
        return None


def _datetime_to_string(value: datetime | None) -> str | None:
    return value.isoformat(sep=" ") if value else None
