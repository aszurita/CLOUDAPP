# Plan De Ejecucion Fase 5: Autopilot Inteligente

## Objetivo

Implementar el flujo 5 de `PlanEjecucion.md`: un boton **Run Autopilot Analysis** que analice la plataforma completa y genere un reporte ejecutivo con riesgos, score operativo, tareas de remediacion e infraestructura sugerida.

La fase 5 no reemplaza a los modulos anteriores. Los conecta:

- Cloud Platform Portal.
- Query Governance.
- DBA Copilot.
- DataOps Monitor.
- Catalog Governance.
- Auditoria operativa.

## Entregable Principal

Vista nueva en el portal:

```text
Autopilot Analysis
```

Con capacidades:

- Ejecutar analisis integral.
- Calcular `Autopilot score`.
- Detectar riesgos por dominio.
- Crear tareas accionables.
- Sugerir infraestructura y controles.
- Persistir historial de reportes.
- Actualizar estado de tareas.
- Generar resumen ejecutivo con IA si OpenAI esta configurado.

## Alcance Implementado

### Backend

Se agregan entidades:

- `autopilot_reports`
- `autopilot_tasks`

Cada reporte guarda:

- `run_id`
- `overall_score`
- `risk_level`
- `summary`
- `metrics_json`
- `findings_json`
- `remediation_plan_json`
- `infra_suggestions_json`
- `ai_summary`
- `raw_context_json`

Cada tarea guarda:

- `title`
- `priority`
- `category`
- `status`
- `owner`
- `due_hint`
- `action_json`

### Endpoints

```text
POST /api/autopilot/analyze
GET  /api/autopilot/latest
GET  /api/autopilot/history
GET  /api/autopilot/reports/{report_id}
POST /api/autopilot/tasks/{task_id}/status
```

### Servicio

`AutopilotService` recolecta senales desde:

- `services`
- `environments`
- `deployments`
- `query_reviews`
- `dba_table_profiles`
- `dba_recommendations`
- `dataops_pipelines`
- `dataops_pipeline_runs`
- `dataops_quality_checks`
- `catalog_assets`
- `catalog_columns`
- `catalog_lineage_edges`
- `catalog_sync_runs`
- `audit_events`

## Logica De Riesgo

El score inicia en `100` y baja segun severidad:

```text
critical = -20
high     = -13
medium   = -7
low      = -3
info     = 0
```

Niveles:

```text
critical <= 55 o hallazgo critical
high     <= 72 o hallazgo high
medium   <= 86 o hallazgo medium
low      > 86
```

## Hallazgos Detectados

El Autopilot puede detectar:

- Servicios no saludables.
- Ambientes en atencion.
- Despliegues fallidos.
- Consultas bloqueadas por gobierno.
- Tablas con riesgo DBA alto.
- Recomendaciones DBA pendientes.
- Pipelines fallidos o en ejecucion.
- Quality score bajo.
- Registros aislados en quarantine.
- Catalog sync fallido.
- Activos sin documentacion.
- Datos sensibles o restricted.
- Lineage incompleto.

## Tareas De Remediacion

Cada hallazgo genera tarea con:

```text
p0 = critical
p1 = high
p2 = medium
p3 = low
```

Owners sugeridos:

```text
platform-team
dba-team
data-platform-team
data-governance-team
```

Estados:

```text
open
in_progress
blocked
done
dismissed
```

## IA

Si OpenAI esta configurado, el backend llama:

```text
AIRecommendationService.generate_autopilot_summary
```

La IA recibe solo metadata agregada:

- metricas
- hallazgos
- plan de remediacion
- contexto tecnico

No recibe:

- secretos
- tokens
- datos crudos
- cadenas de conexion
- filas completas sensibles

Si IA no esta configurada, el reporte funciona igual con resumen deterministico.

## Frontend

Se agrega tab:

```text
Autopilot Analysis
```

La vista muestra:

- Header ejecutivo.
- Boton `Run Analysis`.
- Score.
- Risk level.
- Findings.
- Open tasks.
- Sensitive columns.
- Priority findings.
- Remediation tasks.
- Infrastructure suggestions.
- Historial.

## Demo Script

1. Entrar al portal.
2. Abrir `Autopilot Analysis`.
3. Presionar `Run Analysis`.
4. Mostrar score y risk level.
5. Abrir hallazgos prioritarios.
6. Revisar tareas.
7. Cambiar una tarea a `Start` o `Done`.
8. Mostrar historial de reportes.

## Criterios De Aceptacion

- Existe `Fase5.md`.
- Existen modelos y migracion de Autopilot.
- Backend expone endpoints de analisis, historial y tareas.
- El reporte se persiste en PostgreSQL.
- El portal tiene vista `Autopilot Analysis`.
- Se calculan riesgos usando senales reales internas.
- Se crean tareas de remediacion.
- No se exponen secretos ni datos crudos.
- Tests backend pasan.
- Build frontend pasa.

## Estado

Implementado como MVP funcional de Fase 5.
