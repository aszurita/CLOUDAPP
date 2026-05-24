# Plan De Ejecución Fase 3: DataOps Monitor con Databricks

## Resumen

Objetivo de la fase 3: implementar el flujo 3 de `PlanEjecucion.md` para ejecutar un pipeline DataOps real en Azure Databricks, procesar datos sintéticos en capas `Bronze -> Silver -> Gold`, aplicar reglas de calidad, enviar registros inválidos a `quarantine`, registrar la ejecución en PostgreSQL y mostrar todo desde el portal.

Entregable principal: portal web desplegado en Azure donde un usuario pueda lanzar un job/notebook de Databricks y ver en vivo:

- estado de ejecución
- filas procesadas en `Bronze`, `Silver` y `Gold`
- score de calidad
- registros enviados a `quarantine`
- tiempo de ejecución
- tablas generadas
- resumen operativo y, si falla, explicación asistida por IA

## Precondiciones Obligatorias

Antes de iniciar la construcción de fase 3 se debe cerrar esta puerta mínima de fase 2:

- Desplegar en Azure el backend con rutas públicas de fase 2:
  - `POST /api/query-governance/analyze`
  - `POST /api/query-governance/execute`
  - `POST /api/dba/analyze`
- Confirmar en `GET /api/platform/status`:
  - `ai_provider = openai`
  - `ai_configured = true`
- Corregir el frontend de fase 2 para mostrar:
  - perfiles de tablas DBA
  - resumen `ai_summary` devuelto por `POST /api/dba/analyze`
- Aislar tests backend de `.env` local para que el resultado no dependa de secretos presentes en la máquina.

Sin ese cierre, fase 3 se construye sobre una base funcional incompleta.

## Alcance Del Flujo 3

Este plan debe cumplir exactamente lo que pide `PlanEjecucion.md` para el flujo 3:

- ejecutar notebook/job en Databricks
- mostrar `Bronze`, `Silver` y `Gold`
- mostrar score de calidad
- mostrar cantidad de errores enviados a `quarantine`
- dejar visible el monitoreo del pipeline en el portal

## Implementación DataOps

- Crear carpeta nueva:
  - `/dataops`
- Estructura recomendada:
  - `/dataops/notebooks`
  - `/dataops/config`
  - `/dataops/sample-data`
  - `/dataops/docs`

- Crear datasets sintéticos base:
  - `customer_demo.csv`
  - `transactions_demo.csv`
  - `channels_demo.csv`
  - `risk_events_demo.csv`

- Implementar pipeline Databricks:
  - `01_ingest_bronze`
  - `02_clean_silver`
  - `03_publish_gold`
  - `04_quality_and_quarantine`
  - `05_emit_run_summary`

- Capa `Bronze`:
  - cargar archivos crudos
  - agregar columnas técnicas: `ingestion_ts`, `source_file`, `run_id`
  - guardar estructura sin limpiar para trazabilidad

- Capa `Silver`:
  - limpiar nulos obligatorios
  - normalizar tipos
  - deduplicar
  - validar catálogos permitidos
  - separar registros inválidos hacia `quarantine`

- Capa `Gold`:
  - generar métricas agregadas por cliente
  - generar indicadores por canal
  - producir tabla final lista para catálogo y demo

- Reglas mínimas de calidad:
  - `customer_id` no nulo
  - `transaction_date` no nulo
  - `transaction_amount > 0`
  - `channel` dentro de catálogo esperado
  - integridad referencial entre transacciones y clientes
  - duplicados por llave de negocio controlados

- Tabla `quarantine`:
  - guardar registro rechazado
  - razón de rechazo
  - regla violada
  - archivo origen
  - timestamp
  - `run_id`

- Salida operativa del job:
  - un resumen JSON por ejecución con:
    - `pipeline_name`
    - `run_id`
    - `status`
    - `bronze_rows`
    - `silver_rows`
    - `gold_rows`
    - `quality_score`
    - `quarantine_rows`
    - `duration_ms`
    - `generated_tables`
    - `failed_rules`
    - `databricks_run_url`

## Implementación Backend

- Agregar módulo `DataOps Monitor` en FastAPI.

- Crear integración con Databricks:
  - disparar job/notebook
  - consultar estado de ejecución
  - recuperar resumen JSON emitido por Databricks
  - traducir resultados a modelos internos del portal

- Nuevas tablas en PostgreSQL:
  - `dataops_pipelines`
  - `dataops_pipeline_runs`
  - `dataops_quality_checks`
  - `dataops_generated_assets`
  - `dataops_quarantine_events`

- Nueva migración Alembic:
  - `0004_dataops_monitor.py`

- Persistencia mínima:
  - definición del pipeline
  - historial de corridas
  - métricas Bronze/Silver/Gold
  - score de calidad
  - reglas fallidas
  - conteo de `quarantine`
  - enlaces a ejecución en Databricks

- Endpoints nuevos:
  - `POST /api/dataops/pipelines/run`
  - `GET /api/dataops/pipelines/current`
  - `GET /api/dataops/pipelines/history`
  - `GET /api/dataops/pipelines/{run_id}`
  - `GET /api/dataops/quality/latest`
  - `GET /api/dataops/quarantine`
  - `GET /api/dataops/assets`

- Comportamiento esperado:
  - el backend inicia una corrida en Databricks
  - consulta el estado hasta terminal o devuelve estado asíncrono
  - guarda auditoría de inicio, éxito o fallo
  - si el job falla, genera un resumen con OpenAI a partir de metadata técnica controlada

- IA en fase 3:
  - OpenAI no ejecuta el pipeline
  - OpenAI solo resume fallas, riesgos de calidad y acciones sugeridas
  - no enviar secretos, tokens ni datos crudos completos

## Implementación Frontend

- Agregar nueva vista/tab:
  - `DataOps Monitor`

- Componentes mínimos del flujo 3:
  - botón `Run Pipeline`
  - estado actual: `idle`, `running`, `success`, `failed`
  - cards con:
    - `Bronze rows`
    - `Silver rows`
    - `Gold rows`
    - `Quality score`
    - `Quarantine rows`
    - `Duration`
  - historial de corridas
  - reglas fallidas
  - tablas generadas
  - preview de `quarantine`
  - enlace a ejecución en Databricks
  - panel de resumen IA cuando la corrida falle o quede en riesgo

- UX esperada para demo:
  - una corrida demo lista para lanzar
  - números claros y comparables entre capas
  - visibilidad inmediata de calidad y errores
  - refresco manual y automático del estado

## Infraestructura Y Configuración

- Variables nuevas requeridas en backend:
  - `DATABRICKS_HOST`
  - `DATABRICKS_TOKEN`
  - `DATABRICKS_JOB_ID`
  - `DATABRICKS_CATALOG`
  - `DATABRICKS_SCHEMA_BRONZE`
  - `DATABRICKS_SCHEMA_SILVER`
  - `DATABRICKS_SCHEMA_GOLD`

- Secretos permitidos:
  - `backend/.env` local
  - GitHub Secrets
  - Azure Key Vault
  - secretos de Azure Container Apps

- Cambios de infraestructura:
  - agregar placeholders reales de Databricks en Terraform o documentar provisión manual segura
  - inyectar secretos Databricks al Container App
  - mantener PostgreSQL como base de control operacional
  - documentar costo de uso y apagado del workspace/job

- CI/CD:
  - validar backend y frontend
  - empaquetar artefactos de `/dataops`
  - documentar despliegue del notebook/job
  - si se usa Databricks Asset Bundles, agregar pipeline dedicado

## Seguridad

- El token de Databricks nunca se guarda en código ni Markdown.
- El backend no debe exponer el token al frontend.
- Cada corrida debe registrar auditoría en `audit_events`.
- El portal solo muestra metadata y métricas agregadas.
- La tabla `quarantine` no debe exponer datos sensibles completos en la UI.

## Test Plan

- Backend:
  - mockear cliente Databricks para corrida exitosa
  - mockear cliente Databricks para corrida fallida
  - validar persistencia de `dataops_pipeline_runs`
  - validar persistencia de `dataops_quality_checks`
  - validar auditoría de inicio, éxito y fallo
  - validar resumen IA solo con metadata controlada

- Frontend:
  - lanzar pipeline
  - ver estado `running`
  - ver métricas de `Bronze`, `Silver`, `Gold`
  - ver score de calidad
  - ver conteo de `quarantine`
  - ver historial
  - ver resumen IA si falla

- Integración:
  - ejecutar una corrida real en Databricks
  - confirmar escritura de tablas `Bronze`, `Silver`, `Gold`
  - confirmar que `quarantine` recibe inválidos
  - confirmar que el portal refleja los mismos números

- Producción:
  - actualizar secretos en Key Vault y Container Apps
  - desplegar backend
  - desplegar frontend
  - publicar notebooks/job
  - correr una ejecución demo
  - validar costos y apagado posterior

## Criterios Para Pasar A Fase 4

- El portal ejecuta un job/notebook real en Databricks desde URL pública.
- El portal muestra `Bronze`, `Silver` y `Gold` con conteos reales.
- El portal muestra `quality_score` y registros enviados a `quarantine`.
- Existe historial persistido de corridas en PostgreSQL.
- La ejecución deja auditoría en `audit_events`.
- Si el pipeline falla, el portal muestra resumen operativo con OpenAI.
- Las tablas `Gold` quedan listas para conectarse en la fase 4 a DataHub o Purview.

## Orden De Trabajo Recomendado

1. Cerrar brechas de fase 2 en despliegue, frontend y tests.
2. Crear estructura `/dataops` con datos sintéticos y notebooks.
3. Diseñar resumen JSON estándar de salida del pipeline.
4. Implementar pipeline `Bronze -> Silver -> Gold`.
5. Implementar reglas de calidad y tabla `quarantine`.
6. Crear migración y modelos backend para DataOps Monitor.
7. Integrar FastAPI con Databricks.
8. Crear endpoints de corridas, calidad, activos y `quarantine`.
9. Agregar vista `DataOps Monitor` en React.
10. Conectar polling, historial y métricas al frontend.
11. Configurar secretos Databricks en Azure.
12. Desplegar y validar demo pública.
13. Documentar operación, costo y apagado.

## Asunciones

- Se mantiene el stack actual: React + FastAPI + PostgreSQL + Terraform + Azure.
- Fase 3 continúa usando OpenAI como proveedor IA ya adoptado en fase 2.
- Databricks se usa con datos sintéticos y costos controlados.
- La prioridad es un flujo 3 ejecutable y visible, no todavía catálogo ni lineage enterprise.
