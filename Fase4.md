# Plan De Ejecución Fase 4: Catálogo Y Gobierno Con DataHub/Purview

## Estado Previo De Fase 3

La revisión del repositorio confirma que la Fase 3 está implementada como MVP funcional del flujo DataOps:

- Existe estructura `/dataops` con notebooks, configuración, datos demo y runbook.
- El backend tiene modelos, esquemas, servicio y endpoints de `DataOps Monitor`.
- La base tiene migración para:
  - `dataops_pipelines`
  - `dataops_pipeline_runs`
  - `dataops_quality_checks`
  - `dataops_generated_assets`
  - `dataops_quarantine_events`
- El portal React incluye la vista `DataOps Monitor`.
- El backend puede lanzar Databricks real cuando existen secretos y usa modo demo cuando no están configurados.
- Se persisten métricas Bronze, Silver, Gold, quality score, quarantine, assets, historial y auditoría.
- Tests backend y build frontend pasan localmente.

Nota operativa: para considerar Fase 3 cerrada en producción, todavía se debe validar con URL pública y secretos reales de Databricks en Azure Container Apps si eso no se hizo aún. A nivel de código y demo local, Fase 3 queda lista para construir Fase 4.

## Resumen

Objetivo de la fase 4: implementar el flujo 4 de `PlanEjecucion.md` para catalogar y gobernar los activos generados por Fase 3, conectando el portal con DataHub como opción MVP y dejando Microsoft Purview como opción enterprise en Azure.

Entregable principal: portal web donde el usuario pueda ver activos de datos catalogados, owners, clasificación, documentación generada con IA, estado de calidad, enlaces a tablas Gold/Silver/Bronze y lineage básico desde ingesta hasta publicación.

El flujo 4 debe demostrar:

- Ingesta o sincronización de metadata desde PostgreSQL y Databricks/DataOps.
- Catálogo de activos visible en el portal.
- Owners y dominios de negocio.
- Clasificación de campos sensibles.
- Documentación automática asistida por OpenAI.
- Lineage básico `Bronze -> Silver -> Gold`.
- Auditoría de cambios de metadata.

## Alcance Del Flujo 4

Esta fase implementa el módulo:

```text
Data Catalog & Governance Center
```

Debe conectarse con los activos ya generados por:

- Query Governance y DBA Copilot de Fase 2.
- DataOps Monitor y tablas `Bronze/Silver/Gold` de Fase 3.
- PostgreSQL operacional del portal.
- DataHub o Purview como catálogo externo.

Para mantener el MVP realista:

- Implementar primero DataHub API como integración principal.
- Mantener Purview documentado y preparado por configuración.
- Si DataHub no está configurado, el portal debe usar un catálogo interno persistido en PostgreSQL.

## Arquitectura Propuesta

```text
Frontend React
  ↓
FastAPI Catalog Governance Module
  ↓
PostgreSQL operational metadata
  ↓
Connectors
  ├── DataHub API
  ├── Purview API, opcional enterprise
  ├── DataOps generated assets
  └── DBA table profiles
  ↓
OpenAI
  ├── documentación
  ├── clasificación sugerida
  └── resumen de gobierno
```

## Implementación Backend

Agregar módulo `Catalog Governance Center` en FastAPI.

### Modelos Nuevos

Crear tablas:

- `catalog_assets`
- `catalog_columns`
- `catalog_owners`
- `catalog_classifications`
- `catalog_lineage_edges`
- `catalog_documentation_versions`
- `catalog_sync_runs`

### Migración

Crear migración Alembic:

- `0006_catalog_governance.py`

La migración debe incluir índices por:

- `asset_urn`
- `asset_name`
- `source_system`
- `layer`
- `owner`
- `classification`
- `sync_run_id`

### Entidades

`catalog_assets`:

- `id`
- `asset_urn`
- `asset_name`
- `display_name`
- `source_system`
- `platform`
- `database_name`
- `schema_name`
- `table_name`
- `layer`
- `domain`
- `owner`
- `description`
- `documentation_status`
- `quality_score`
- `sensitivity_level`
- `external_url`
- `last_synced_at`

`catalog_columns`:

- `id`
- `asset_id`
- `column_name`
- `data_type`
- `nullable`
- `description`
- `classification`
- `is_sensitive`
- `sample_safe_value`

`catalog_lineage_edges`:

- `id`
- `source_asset_urn`
- `target_asset_urn`
- `lineage_type`
- `transformation_name`
- `confidence`

`catalog_sync_runs`:

- `id`
- `source`
- `status`
- `assets_seen`
- `assets_created`
- `assets_updated`
- `started_at`
- `finished_at`
- `error_message`

## Integración DataHub

Variables requeridas:

- `DATAHUB_SERVER`
- `DATAHUB_TOKEN`
- `DATAHUB_ENABLED`

Comportamiento:

- Si `DATAHUB_ENABLED=true`, el backend sincroniza metadata con DataHub.
- Si falta configuración, el backend usa catálogo interno y deja estado `external_catalog=not_configured`.
- Nunca exponer `DATAHUB_TOKEN` al frontend.

Funciones mínimas:

- Construir URNs para tablas Databricks y PostgreSQL.
- Crear o actualizar datasets en DataHub.
- Publicar descripciones generadas.
- Publicar owners.
- Publicar tags/glossary terms para sensibilidad.
- Leer metadata existente cuando aplique.

Activos DataHub sugeridos:

```text
urn:li:dataset:(urn:li:dataPlatform:databricks,databricks_proyectobg.tpcds_bronze.store_sales,PROD)
urn:li:dataset:(urn:li:dataPlatform:databricks,databricks_proyectobg.tpcds_silver.store_sales_clean,PROD)
urn:li:dataset:(urn:li:dataPlatform:databricks,databricks_proyectobg.tpcds_gold.sales_by_year_category,PROD)
urn:li:dataset:(urn:li:dataPlatform:postgres,cloudapp.public.demo_customer_transactions,PROD)
```

## Integración Purview Opcional

Variables preparadas:

- `PURVIEW_ACCOUNT_NAME`
- `PURVIEW_ENDPOINT`
- `PURVIEW_TENANT_ID`
- `PURVIEW_CLIENT_ID`
- `PURVIEW_CLIENT_SECRET`
- `PURVIEW_ENABLED`

Para MVP no es obligatorio implementar Purview completo, pero la arquitectura debe permitir cambiar el proveedor de catálogo mediante:

```text
CATALOG_PROVIDER=internal|datahub|purview
```

## Sincronización De Metadata

Fuentes iniciales:

- `dataops_generated_assets`
- `dataops_pipeline_runs`
- `dataops_quality_checks`
- `dba_table_profiles`
- `dba_recommendations`
- `demo_customer_transactions`
- `demo_customers`

Reglas de sincronización:

- Cada tabla Gold generada en Fase 3 se registra como activo de negocio.
- Cada tabla Silver se registra como activo controlado de calidad.
- Cada tabla Bronze se registra como activo crudo de trazabilidad.
- Cada asset debe tener `owner`, `domain`, `layer`, `quality_score` y `documentation_status`.
- Si no hay owner real, usar `data-platform-team` como owner temporal.

## Clasificación Y Sensibilidad

Clasificaciones mínimas:

- `public`
- `internal`
- `confidential`
- `restricted`

Reglas determinísticas:

- Columnas con `customer_id`, `account`, `transaction`, `amount`, `risk`, `email`, `phone`, `address` se marcan como sensibles o candidatas a revisión.
- Tablas Gold con agregados quedan `internal` salvo que incluyan identificadores directos.
- Tablas Bronze quedan `confidential` por ser datos crudos.
- Eventos de quarantine no deben exponer datos sensibles completos.

OpenAI puede sugerir clasificación, pero la regla determinística debe mandar.

## Documentación Con IA

Agregar servicio:

```text
CatalogDocumentationService
```

Debe generar:

- Descripción funcional de la tabla.
- Uso recomendado.
- Riesgos de uso.
- Columnas importantes.
- Owner sugerido.
- Clasificación sugerida.
- Preguntas pendientes para data owner.

Entrada permitida a OpenAI:

- Nombre de tabla.
- Nombre de columnas.
- Tipos.
- Capa.
- Métricas agregadas.
- Reglas de calidad.
- Metadata técnica.

No enviar:

- Tokens.
- Secretos.
- Datos crudos completos.
- Filas completas de quarantine.
- Cadenas de conexión.

## Endpoints Nuevos

Crear endpoints:

- `POST /api/catalog/sync`
- `GET /api/catalog/status`
- `GET /api/catalog/assets`
- `GET /api/catalog/assets/{asset_id}`
- `GET /api/catalog/assets/{asset_id}/columns`
- `GET /api/catalog/lineage`
- `GET /api/catalog/classifications`
- `POST /api/catalog/assets/{asset_id}/document`
- `POST /api/catalog/assets/{asset_id}/owner`
- `POST /api/catalog/assets/{asset_id}/classification`
- `GET /api/catalog/sync-runs`

Comportamiento esperado:

- `POST /api/catalog/sync` toma activos existentes de Fase 2 y Fase 3.
- El backend registra auditoría en `audit_events`.
- El frontend puede mostrar catálogo aunque DataHub/Purview no estén configurados.
- Si DataHub está configurado, se publica metadata externa y se guarda el enlace.

## Implementación Frontend

Agregar nueva vista/tab:

```text
Catalog Governance
```

Componentes mínimos:

- Botón `Sync Catalog`.
- Lista de activos catalogados.
- Filtros por:
  - capa
  - dominio
  - owner
  - clasificación
  - estado de documentación
- Panel de detalle del activo.
- Columnas y clasificación.
- Quality score heredado de Fase 3.
- Lineage básico `Bronze -> Silver -> Gold`.
- Botón `Generate Documentation`.
- Panel de documentación IA.
- Historial de sincronizaciones.
- Enlace a DataHub/Purview si está disponible.

UX esperada para demo:

- El usuario sincroniza catálogo.
- Ve tablas Gold creadas por DataOps Monitor.
- Abre un activo.
- Genera documentación con IA.
- Ve campos sensibles marcados.
- Ve lineage desde Bronze hasta Gold.
- Cambia owner o clasificación y queda auditado.

## Seguridad

- No exponer tokens de DataHub, Purview, Databricks ni OpenAI.
- No mostrar datos crudos sensibles.
- La UI debe mostrar previews sanitizados.
- Toda escritura de metadata debe registrar `audit_events`.
- La IA no decide permisos de acceso.
- La clasificación determinística debe prevalecer sobre sugerencias IA.
- Si hay conflicto de clasificación, elegir la más restrictiva.

## Infraestructura Y Configuración

Actualizar documentación y Terraform con placeholders seguros:

- `DATAHUB_SERVER`
- `DATAHUB_TOKEN`
- `DATAHUB_ENABLED`
- `CATALOG_PROVIDER`
- `PURVIEW_ENDPOINT`
- `PURVIEW_ENABLED`

Agregar secretos en Azure Container Apps:

- `datahub-token`
- `purview-client-secret`, solo si se implementa Purview.

Actualizar `docs/environment.md` con variables de Fase 4.

## Test Plan

Backend:

- Sincronizar activos desde `dataops_generated_assets`.
- Crear assets Bronze, Silver y Gold.
- Crear columnas con clasificación determinística.
- Generar documentación IA con OpenAI mockeado.
- Validar que no se envían datos crudos completos a IA.
- Validar lineage `Bronze -> Silver -> Gold`.
- Validar auditoría de sync, documentación, owner y clasificación.
- Validar fallback cuando DataHub no está configurado.
- Mockear DataHub para publicación exitosa y fallo controlado.

Frontend:

- Ver tab `Catalog Governance`.
- Ejecutar `Sync Catalog`.
- Listar activos.
- Filtrar por capa y clasificación.
- Abrir detalle.
- Ver columnas.
- Ver lineage.
- Generar documentación.
- Cambiar owner o clasificación.
- Ver estado de sincronización.

Integración:

- Ejecutar Fase 3.
- Sincronizar catálogo.
- Confirmar que las tablas Gold aparecen como activos catalogados.
- Confirmar que DataHub recibe metadata si está configurado.
- Confirmar que el portal conserva catálogo interno si DataHub falla.

Producción:

- Configurar secretos en Key Vault.
- Inyectar variables al Container App.
- Desplegar backend.
- Ejecutar migraciones.
- Desplegar frontend.
- Ejecutar sync demo.
- Validar costos y apagado de servicios externos.

## Criterios Para Pasar A Fase 5

- El portal muestra un catálogo funcional de activos.
- Las tablas generadas por Fase 3 aparecen en el catálogo.
- Cada activo tiene owner, dominio, capa y clasificación.
- El portal muestra columnas sensibles o candidatas a revisión.
- El portal genera documentación IA sin enviar datos crudos completos.
- Existe lineage básico entre Bronze, Silver y Gold.
- Los cambios de metadata quedan auditados.
- Existe historial de sincronizaciones.
- DataHub funciona si está configurado o el catálogo interno funciona como fallback.
- Fase 5 puede consumir el catálogo para generar el reporte `Run Autopilot Analysis`.

## Orden De Trabajo Recomendado

1. Crear migración `0006_catalog_governance.py`.
2. Crear modelos y esquemas de catálogo.
3. Implementar servicio de clasificación determinística.
4. Implementar sincronización desde activos DataOps.
5. Implementar catálogo interno persistido en PostgreSQL.
6. Implementar endpoints de catálogo.
7. Agregar documentación IA con OpenAI.
8. Agregar auditoría para acciones de metadata.
9. Agregar vista `Catalog Governance` en React.
10. Implementar detalle, filtros, documentación y lineage.
11. Agregar cliente DataHub opcional.
12. Documentar configuración DataHub/Purview.
13. Agregar tests backend y validar build frontend.
14. Ejecutar demo completa Fase 2 -> Fase 3 -> Fase 4.

## Asunciones

- Se mantiene React + FastAPI + PostgreSQL + Azure Container Apps.
- OpenAI sigue siendo el proveedor IA principal.
- DataHub es la opción recomendada para MVP por costo y velocidad.
- Purview queda preparado para una versión enterprise alineada con Azure.
- La prioridad de Fase 4 es gobierno visible y útil, no un catálogo enterprise completo desde el primer intento.
