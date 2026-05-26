from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    CatalogAsset,
    CatalogClassification,
    CatalogColumn,
    CatalogDocumentationVersion,
    CatalogLineageEdge,
    CatalogOwner,
    CatalogSyncRun,
    DataOpsGeneratedAsset,
    DataOpsPipeline,
    DataOpsPipelineRun,
    DataOpsQualityCheck,
    DbaTableProfile,
)
from app.services.ai import AIConfigurationError, AIRecommendationService
from app.services.database_inventory import collect_database_inventory


CLASSIFICATIONS = [
    ("public", "Public", 1, "Data safe for broad demo visibility."),
    ("internal", "Internal", 2, "Operational internal metadata or aggregates."),
    ("confidential", "Confidential", 3, "Raw, detailed or potentially identifiable business data."),
    ("restricted", "Restricted", 4, "Sensitive identifiers, financial, risk or access-controlled fields."),
]

SENSITIVE_TERMS = ("customer_id", "customer", "account", "transaction", "amount", "risk", "email", "phone", "address")


class CatalogGovernanceService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def status(self, db: Session) -> dict[str, Any]:
        latest = db.query(CatalogSyncRun).order_by(CatalogSyncRun.started_at.desc()).first()
        return {
            "provider": self.settings.catalog_provider,
            "external_catalog": self._external_catalog_status(),
            "datahub_configured": self._datahub_configured(),
            "purview_configured": bool(self.settings.purview_enabled and self.settings.purview_endpoint),
            "assets_total": db.query(CatalogAsset).count(),
            "documented_assets": db.query(CatalogAsset).filter(CatalogAsset.documentation_status == "generated").count(),
            "sensitive_columns": db.query(CatalogColumn).filter(CatalogColumn.is_sensitive.is_(True)).count(),
            "lineage_edges": db.query(CatalogLineageEdge).count(),
            "latest_sync_status": latest.status if latest else None,
        }

    def sync_catalog(self, db: Session) -> CatalogSyncRun:
        self.ensure_reference_data(db)
        db.query(CatalogAsset).filter(CatalogAsset.platform == "databricks").update({"external_url": None})
        db.commit()
        sync_run = CatalogSyncRun(source="phase2-phase3", status="running")
        db.add(sync_run)
        db.commit()
        db.refresh(sync_run)

        created = 0
        updated = 0
        candidates = self._dataops_asset_candidates(db) + self._postgres_asset_candidates(db)
        try:
            for candidate in candidates:
                asset, was_created = self._upsert_asset(db, candidate)
                self._replace_columns(db, asset, candidate["columns"])
                if was_created:
                    created += 1
                else:
                    updated += 1
                if self._datahub_configured():
                    self._publish_to_datahub(asset)
            self._rebuild_lineage(db)
            sync_run.status = "success"
        except Exception as exc:
            sync_run.status = "failed"
            sync_run.error_message = str(exc)
        finally:
            sync_run.assets_seen = len(candidates)
            sync_run.assets_created = created
            sync_run.assets_updated = updated
            sync_run.finished_at = datetime.utcnow()
            db.commit()
            db.refresh(sync_run)
        return sync_run

    def ensure_reference_data(self, db: Session) -> None:
        for code, label, rank, description in CLASSIFICATIONS:
            if not db.query(CatalogClassification).filter(CatalogClassification.code == code).first():
                db.add(CatalogClassification(code=code, label=label, rank=rank, description=description))
        if not db.query(CatalogOwner).filter(CatalogOwner.owner_key == "data-platform-team").first():
            db.add(
                CatalogOwner(
                    owner_key="data-platform-team",
                    display_name="Data Platform Team",
                    email="data-platform@example.local",
                    domain="retail-risk",
                )
            )
        db.commit()

    def generate_documentation(self, db: Session, asset: CatalogAsset) -> str:
        metadata = self._safe_asset_metadata(asset)
        try:
            documentation = AIRecommendationService().generate_catalog_documentation(metadata)
        except AIConfigurationError:
            documentation = self._fallback_documentation(asset, metadata)

        asset.description = documentation
        asset.documentation_status = "generated"
        db.add(CatalogDocumentationVersion(asset_id=asset.id, content=documentation, generated_by="openai"))
        db.commit()
        db.refresh(asset)
        if self._datahub_configured():
            self._publish_to_datahub(asset)
        return documentation

    def update_owner(self, db: Session, asset: CatalogAsset, owner: str) -> CatalogAsset:
        normalized = owner.strip() or "data-platform-team"
        asset.owner = normalized
        if not db.query(CatalogOwner).filter(CatalogOwner.owner_key == normalized).first():
            db.add(CatalogOwner(owner_key=normalized, display_name=normalized.replace("-", " ").title(), domain=asset.domain))
        db.commit()
        db.refresh(asset)
        return asset

    def update_classification(self, db: Session, asset: CatalogAsset, classification: str) -> CatalogAsset:
        allowed = {code for code, *_ in CLASSIFICATIONS}
        normalized = classification.strip().lower()
        if normalized not in allowed:
            normalized = "restricted"
        asset.sensitivity_level = self._most_restrictive(asset.sensitivity_level, normalized)
        for column in asset.columns:
            column.classification = self._most_restrictive(column.classification, asset.sensitivity_level)
            column.is_sensitive = column.classification in {"confidential", "restricted"}
        db.commit()
        db.refresh(asset)
        return asset

    def _dataops_asset_candidates(self, db: Session) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        pipelines = db.query(DataOpsPipeline).order_by(DataOpsPipeline.id).all()
        for pipeline in pipelines:
            latest_run = (
                db.query(DataOpsPipelineRun)
                .filter(DataOpsPipelineRun.pipeline_id == pipeline.id)
                .order_by(DataOpsPipelineRun.created_at.desc())
                .first()
            )
            if not latest_run:
                continue
            latest_assets = (
                db.query(DataOpsGeneratedAsset)
                .filter(DataOpsGeneratedAsset.run_id == latest_run.run_id)
                .order_by(DataOpsGeneratedAsset.id)
                .all()
            )
            candidates.extend(self._candidate_from_dataops(asset, latest_run) for asset in latest_assets)
        return candidates

    def _postgres_asset_candidates(self, db: Session) -> list[dict[str, Any]]:
        inventory_candidates = self._inventory_asset_candidates()
        if inventory_candidates:
            return inventory_candidates

        profiles = db.query(DbaTableProfile).order_by(DbaTableProfile.table_name).all()
        if not profiles:
            profiles = [
                DbaTableProfile(
                    schema_name="public",
                    table_name="demo_customers",
                    estimated_rows=40,
                    total_size_bytes=0,
                    columns_json=[
                        {"name": "customer_code", "type": "varchar", "nullable": False},
                        {"name": "segment", "type": "varchar", "nullable": False},
                        {"name": "email", "type": "varchar", "nullable": False},
                        {"name": "account_type", "type": "varchar", "nullable": False},
                        {"name": "risk_score", "type": "integer", "nullable": False},
                    ],
                    sensitive_columns_json=["customer_code", "email", "account_type", "risk_score"],
                    risk_level="high",
                ),
                DbaTableProfile(
                    schema_name="public",
                    table_name="demo_customer_transactions",
                    estimated_rows=400,
                    total_size_bytes=0,
                    columns_json=[
                        {"name": "customer_id", "type": "integer", "nullable": False},
                        {"name": "transaction_date", "type": "date", "nullable": False},
                        {"name": "transaction_amount", "type": "numeric", "nullable": False},
                        {"name": "channel", "type": "varchar", "nullable": False},
                        {"name": "risk_flag", "type": "boolean", "nullable": False},
                    ],
                    sensitive_columns_json=["customer_id", "transaction_amount", "risk_flag"],
                    risk_level="high",
                ),
            ]
        return [self._candidate_from_profile(profile) for profile in profiles]

    def _inventory_asset_candidates(self) -> list[dict[str, Any]]:
        try:
            inventory = collect_database_inventory(self.settings)
        except Exception:
            return []

        candidates: list[dict[str, Any]] = []
        for source in inventory.get("sources", []):
            if source.get("status") != "available":
                continue
            platform = "postgres" if source.get("engine") in {"postgresql", "postgres"} else str(source.get("engine") or "database")
            source_key = str(source.get("key") or source.get("role") or platform)
            database_name = str(source.get("database_name") or source.get("label") or source_key)
            role = str(source.get("role") or "database")
            for schema in source.get("schemas", []):
                schema_name = str(schema.get("name") or "main")
                for table in schema.get("tables", []):
                    table_name = str(table.get("name") or "table")
                    if table.get("internal") and role != "monitored_database":
                        layer = "operational"
                    else:
                        layer = "lab" if role == "monitored_database" else "operational"
                    columns = []
                    for column in table.get("columns", []):
                        name = str(column.get("name") or "column")
                        sensitivity = "restricted" if column.get("sensitive") else "internal"
                        columns.append(
                            {
                                "column_name": name,
                                "data_type": str(column.get("type") or "unknown"),
                                "nullable": bool(column.get("nullable", True)),
                                "classification": sensitivity,
                                "is_sensitive": sensitivity == "restricted",
                                "description": self._column_description(name),
                                "sample_safe_value": None,
                            }
                        )
                    asset_sensitivity = "restricted" if any(col["is_sensitive"] for col in columns) else "internal"
                    table_fqn = f"{database_name}.{schema_name}.{table_name}"
                    candidates.append(
                        {
                            "asset_urn": self._dataset_urn(platform, table_fqn),
                            "asset_name": table_name,
                            "display_name": f"{database_name} · {schema_name} · {table_name}",
                            "source_system": source_key,
                            "platform": platform,
                            "database_name": database_name,
                            "schema_name": schema_name,
                            "table_name": table_name,
                            "layer": layer,
                            "domain": self._domain_for_asset(table_name, layer),
                            "owner": "data-platform-team",
                            "description": None,
                            "documentation_status": "missing",
                            "quality_score": None,
                            "sensitivity_level": asset_sensitivity,
                            "external_url": None,
                            "columns": columns,
                        }
                    )
        return candidates

    def _candidate_from_dataops(self, asset: DataOpsGeneratedAsset, run: DataOpsPipelineRun | None) -> dict[str, Any]:
        storage_path = asset.storage_path or asset.asset_name
        parts = storage_path.split(".")
        database_name = parts[0] if len(parts) >= 3 else self.settings.databricks_catalog
        schema_name = parts[-2] if len(parts) >= 2 else f"tpcds_{asset.layer}"
        table_name = parts[-1]
        sensitivity = self._asset_sensitivity(asset.layer, table_name)
        return {
            "asset_urn": self._dataset_urn("databricks", f"{database_name}.{schema_name}.{table_name}"),
            "asset_name": asset.asset_name,
            "display_name": f"{asset.layer.title()} · {asset.asset_name}",
            "source_system": "databricks",
            "platform": "databricks",
            "database_name": database_name,
            "schema_name": schema_name,
            "table_name": table_name,
            "layer": asset.layer,
            "domain": self._domain_for_asset(table_name, asset.layer),
            "owner": "data-platform-team",
            "description": None,
            "documentation_status": "missing",
            "quality_score": run.quality_score if run else None,
            "sensitivity_level": sensitivity,
            "external_url": None,
            "columns": self._dataops_columns_for(table_name, asset.layer, sensitivity),
        }

    def _candidate_from_profile(self, profile: DbaTableProfile) -> dict[str, Any]:
        table_fqn = f"cloudapp.{profile.schema_name}.{profile.table_name}"
        sensitivity = "restricted" if profile.risk_level in {"high", "blocked"} else "confidential"
        columns = []
        for column in profile.columns_json:
            name = str(column.get("name", "column"))
            classification = self._column_classification(name, sensitivity)
            columns.append(
                {
                    "column_name": name,
                    "data_type": str(column.get("type", "unknown")),
                    "nullable": bool(column.get("nullable", True)),
                    "classification": classification,
                    "is_sensitive": classification in {"confidential", "restricted"},
                    "description": self._column_description(name),
                    "sample_safe_value": None,
                }
            )
        return {
            "asset_urn": self._dataset_urn("postgres", table_fqn),
            "asset_name": profile.table_name,
            "display_name": f"PostgreSQL · {profile.table_name}",
            "source_system": "postgres",
            "platform": "postgres",
            "database_name": "cloudapp",
            "schema_name": profile.schema_name,
            "table_name": profile.table_name,
            "layer": "operational",
            "domain": self._domain_for_asset(profile.table_name, "operational"),
            "owner": "data-platform-team",
            "description": None,
            "documentation_status": "missing",
            "quality_score": None,
            "sensitivity_level": sensitivity,
            "external_url": None,
            "columns": columns,
        }

    def _upsert_asset(self, db: Session, candidate: dict[str, Any]) -> tuple[CatalogAsset, bool]:
        asset = db.query(CatalogAsset).filter(CatalogAsset.asset_urn == candidate["asset_urn"]).first()
        created = asset is None
        if not asset:
            asset = CatalogAsset(asset_urn=candidate["asset_urn"], asset_name=candidate["asset_name"], display_name=candidate["display_name"])
            db.add(asset)
        for field in (
            "asset_name",
            "display_name",
            "source_system",
            "platform",
            "database_name",
            "schema_name",
            "table_name",
            "layer",
            "domain",
            "owner",
            "quality_score",
            "external_url",
        ):
            setattr(asset, field, candidate[field])
        if not asset.description:
            asset.description = candidate["description"]
        asset.sensitivity_level = self._most_restrictive(asset.sensitivity_level or "internal", candidate["sensitivity_level"])
        asset.documentation_status = asset.documentation_status or candidate["documentation_status"]
        asset.last_synced_at = datetime.utcnow()
        db.flush()
        return asset, created

    def _replace_columns(self, db: Session, asset: CatalogAsset, columns: list[dict[str, Any]]) -> None:
        existing_descriptions = {
            column.column_name: column.description
            for column in db.query(CatalogColumn).filter(CatalogColumn.asset_id == asset.id).all()
            if column.description and not self._is_generated_column_description(column.description)
        }
        db.query(CatalogColumn).filter(CatalogColumn.asset_id == asset.id).delete()
        for column in columns:
            if existing_descriptions.get(column["column_name"]):
                column["description"] = existing_descriptions[column["column_name"]]
            db.add(CatalogColumn(asset_id=asset.id, **column))

    def _rebuild_lineage(self, db: Session) -> None:
        db.query(CatalogLineageEdge).delete()
        assets = db.query(CatalogAsset).filter(CatalogAsset.platform == "databricks").all()
        by_table = {asset.table_name: asset for asset in assets}
        edge_specs = [
            ("store_sales", "store_sales_clean", "01_ingest_bronze -> 02_clean_silver"),
            ("store_sales", "quarantine_store_sales", "04_quality_and_quarantine"),
            ("store_sales_clean", "sales_by_year_category", "03_publish_gold"),
            ("store_sales_clean", "sales_by_store", "03_publish_gold"),
            ("transacciones_demo", "alertas_movimientos_inusuales", "02_detectar_alertas_movimientos_inusuales"),
            ("alertas_movimientos_inusuales", "log_ejecucion_alertas", "audit_log_ejecucion_alertas"),
        ]
        for source_name, target_name, transformation in edge_specs:
            source = by_table.get(source_name)
            target = by_table.get(target_name)
            if not source or not target:
                continue
            db.add(
                CatalogLineageEdge(
                    source_asset_urn=source.asset_urn,
                    target_asset_urn=target.asset_urn,
                    transformation_name=transformation,
                    confidence=0.95,
                )
            )

    def _dataops_columns_for(self, table_name: str, layer: str, asset_sensitivity: str) -> list[dict[str, Any]]:
        lowered = table_name.lower()
        if "log_ejecucion_alertas" in lowered:
            base = [
                ("run_id", "string", False),
                ("estado", "string", False),
                ("registros_procesados", "integer", False),
                ("alertas_generadas", "integer", False),
                ("fecha_inicio", "timestamp", False),
                ("fecha_fin", "timestamp", True),
                ("email_status", "string", True),
            ]
        elif any(term in lowered for term in ("transacciones", "movimientos", "alertas")):
            base = [
                ("run_id", "string", False),
                ("transaction_id", "string", False),
                ("account_id", "string", True),
                ("transaction_ts", "timestamp", True),
                ("amount", "decimal", True),
                ("channel", "string", True),
                ("rule_code", "string", True),
                ("alert_reason", "string", True),
            ]
        else:
            base = [
                ("run_id", "string", False),
                ("source_file", "string", True),
                ("ingestion_ts", "timestamp", False),
            ]
        if "sales" in table_name or "transaction" in table_name:
            base += [
                ("customer_id", "string", True),
                ("transaction_date", "date", True),
                ("transaction_amount", "decimal", True),
                ("channel", "string", True),
                ("risk_flag", "boolean", True),
            ]
        elif "customer" in table_name:
            base += [("customer_id", "string", False), ("segment", "string", True), ("risk_score", "integer", True)]
        else:
            base += [("business_key", "string", True), ("metric_value", "decimal", True)]
        return [
            {
                "column_name": name,
                "data_type": data_type,
                "nullable": nullable,
                "classification": self._column_classification(name, asset_sensitivity),
                "is_sensitive": self._column_classification(name, asset_sensitivity) in {"confidential", "restricted"},
                "description": self._column_description(name),
                "sample_safe_value": None,
            }
            for name, data_type, nullable in base
        ]

    def _safe_asset_metadata(self, asset: CatalogAsset) -> dict[str, Any]:
        return {
            "asset_name": asset.asset_name,
            "platform": asset.platform,
            "source_system": asset.source_system,
            "database_name": asset.database_name,
            "schema_name": asset.schema_name,
            "table_name": asset.table_name,
            "layer": asset.layer,
            "domain": asset.domain,
            "owner": asset.owner,
            "quality_score": asset.quality_score,
            "sensitivity_level": asset.sensitivity_level,
            "columns": [
                {
                    "name": column.column_name,
                    "type": column.data_type,
                    "nullable": column.nullable,
                    "classification": column.classification,
                    "is_sensitive": column.is_sensitive,
                }
                for column in asset.columns
            ],
        }

    def _fallback_documentation(self, asset: CatalogAsset, metadata: dict[str, Any]) -> str:
        column_names = ", ".join(column["name"] for column in metadata["columns"][:8])
        return (
            f"Propósito: {asset.display_name} registra metadata gobernada de la capa {asset.layer}. "
            f"Uso recomendado: discovery, monitoreo de calidad y análisis controlado. "
            f"Columnas clave: {column_names}. "
            f"Sensibilidad: {asset.sensitivity_level}. "
            "Riesgos: validar owner, retención y clasificación antes de exponer el activo. "
            "Preguntas pendientes: confirmar steward de negocio y SLA de actualización."
        )

    def _publish_to_datahub(self, asset: CatalogAsset) -> None:
        server = str(self.settings.datahub_server).rstrip("/")
        token = self.settings.datahub_token or ""
        payload = {
            "proposal": {
                "entityType": "dataset",
                "entityUrn": asset.asset_urn,
                "changeType": "UPSERT",
                "aspectName": "datasetProperties",
                "aspect": {
                    "value": {
                        "name": asset.display_name,
                        "description": asset.description or "",
                        "customProperties": {
                            "layer": asset.layer,
                            "owner": asset.owner,
                            "sensitivity": asset.sensitivity_level,
                        },
                    },
                    "contentType": "application/json",
                },
            }
        }
        response = httpx.post(
            f"{server}/aspects?action=ingestProposal",
            headers={"Authorization": f"Bearer {token}"} if token else {},
            json=payload,
            timeout=10,
        )
        response.raise_for_status()

    def _external_catalog_status(self) -> str:
        if self._datahub_configured():
            return "datahub_configured"
        if self.settings.purview_enabled and self.settings.purview_endpoint:
            return "purview_configured"
        return "not_configured"

    def _datahub_configured(self) -> bool:
        return bool(self.settings.datahub_enabled and self.settings.datahub_server)

    def _dataset_urn(self, platform: str, name: str) -> str:
        return f"urn:li:dataset:(urn:li:dataPlatform:{platform},{name},PROD)"

    def _asset_sensitivity(self, layer: str, table_name: str) -> str:
        lowered = table_name.lower()
        if layer == "bronze" or "quarantine" in lowered:
            return "confidential"
        if any(term in lowered for term in ("customer", "risk", "transaction", "transacciones", "movimientos", "alertas")):
            return "restricted"
        return "internal"

    def _domain_for_asset(self, table_name: str, layer: str) -> str:
        lowered = table_name.lower()
        if any(term in lowered for term in ("transacciones", "movimientos", "alertas")):
            return "banking-risk"
        if "quarantine" in lowered or "risk" in lowered:
            return "data-quality-risk"
        if "customer" in lowered:
            return "customer-operations"
        if any(term in lowered for term in ("sales", "store", "item", "date_dim")):
            return "retail-sales"
        if layer == "operational":
            return "platform-operations"
        return "data-platform"

    def _column_classification(self, column_name: str, asset_sensitivity: str) -> str:
        lowered = column_name.lower()
        if any(term in lowered for term in SENSITIVE_TERMS):
            return "restricted"
        if asset_sensitivity in {"confidential", "restricted"}:
            return asset_sensitivity
        return "internal"

    def _column_description(self, column_name: str) -> str | None:
        return None

    def _is_generated_column_description(self, description: str) -> bool:
        return description.startswith("Campo técnico o de negocio `") and description.endswith(
            "` documentado por el catálogo de Fase 4."
        )

    def _most_restrictive(self, current: str, candidate: str) -> str:
        ranks = {code: rank for code, _label, rank, _desc in CLASSIFICATIONS}
        return candidate if ranks.get(candidate, 0) > ranks.get(current, 0) else current
