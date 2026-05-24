# Plan De Ejecucion Fase 2: Query Governance + DBA Copilot Con ChatGPT/OpenAI

## Resumen

Objetivo de la fase 2: agregar gobierno SQL, ejecucion segura de consultas y DBA Copilot usando PostgreSQL real en Azure y OpenAI/ChatGPT como motor obligatorio de explicacion y recomendaciones.

Entregable principal: portal web desplegado en Azure donde un usuario pueda analizar consultas SQL, bloquear consultas riesgosas, ejecutar consultas seguras de solo lectura, auditar cada intento y ver recomendaciones DBA generadas con OpenAI.

Nota de seguridad: no guardar API keys en codigo, Markdown, Terraform state ni commits. Si una key fue expuesta, se debe revocar y crear una nueva antes de usarla en produccion.

## Configuracion OpenAI

- Variables requeridas:
  - `AI_PROVIDER=openai`
  - `OPENAI_API_KEY=<secret>`
  - `OPENAI_MODEL=chat-latest`
  - `OPENAI_MAX_OUTPUT_TOKENS=800`
  - `OPENAI_TEMPERATURE=0.2`
- La API key solo debe existir en:
  - `backend/.env` local.
  - GitHub Secrets.
  - Azure Key Vault.
  - Secretos de Azure Container Apps.
- El backend debe exponer `ai_provider: openai` y `ai_configured: true` en `/api/platform/status` cuando la key este configurada.

## Implementacion Backend

- Agregar `Query Governance Engine`:
  - Validar consultas SQL antes de ejecutarlas.
  - Bloquear comandos peligrosos: `DROP`, `DELETE`, `UPDATE`, `INSERT`, `ALTER`, `TRUNCATE`, `CREATE`, `GRANT`, `REVOKE`.
  - Bloquear multiples sentencias.
  - Bloquear `SELECT *`.
  - Exigir `LIMIT`.
  - Bloquear tablas internas: `audit_events`, `platform_settings`, `query_reviews`, `query_policies`.
  - Permitir ejecucion solo sobre tablas demo.
  - Registrar todo en auditoria.

- Agregar ejecucion segura de SQL:
  - Solo permitir `SELECT`.
  - Ejecutar en modo solo lectura cuando PostgreSQL lo soporte.
  - Aplicar timeout corto.
  - Devolver maximo 100 filas.
  - Devolver columnas, filas, tiempo de ejecucion y evaluacion de riesgo.

- Agregar `DBA Copilot`:
  - Leer metadata real desde PostgreSQL.
  - Detectar columnas potencialmente sensibles.
  - Calcular riesgo por tabla.
  - Generar recomendaciones con OpenAI.
  - Registrar el analisis en `audit_events`.

- Endpoints nuevos:
  - `POST /api/query-governance/analyze`
  - `POST /api/query-governance/execute`
  - `GET /api/query-governance/history`
  - `GET /api/query-governance/policies`
  - `GET /api/query-governance/demo-queries`
  - `POST /api/dba/analyze`
  - `GET /api/dba/tables`
  - `GET /api/dba/recommendations`

## Base De Datos

- Migracion Alembic: `0002_query_governance_dba.py`.
- Tablas nuevas:
  - `query_policies`
  - `query_reviews`
  - `dba_table_profiles`
  - `dba_recommendations`
  - `demo_customers`
  - `demo_customer_transactions`
- Datos demo:
  - Clientes sinteticos.
  - Transacciones sinteticas.
  - Politicas SQL iniciales.
  - Consulta peligrosa y consulta segura.

## Implementacion Frontend

- Mantener `Platform Overview`.
- Agregar `Query Governance`:
  - Editor SQL.
  - Consulta demo peligrosa.
  - Consulta demo segura.
  - Analisis con OpenAI.
  - Ejecucion solo si la consulta esta aprobada.
  - Historial de consultas.
- Agregar `DBA Copilot`:
  - Boton `Run Analysis`.
  - Tabla de perfiles DBA.
  - Recomendaciones.
  - Resumen generado con OpenAI.

## Seguridad

- OpenAI nunca decide si una consulta se ejecuta.
- La decision de ejecutar o bloquear es deterministica y ocurre en backend.
- A OpenAI solo se envia SQL, reglas activadas y metadata minima.
- No enviar secretos, passwords, `DATABASE_URL` ni datos completos de tablas.

## Test Plan

- Backend:
  - Bloquear `DROP TABLE`.
  - Bloquear `SELECT *`.
  - Bloquear consulta sin `LIMIT`.
  - Aprobar consulta segura.
  - Ejecutar consulta segura y devolver maximo 100 filas.
  - Registrar `query_reviews`.
  - Registrar `audit_events`.
  - Mockear OpenAI en tests para no gastar tokens.

- Frontend:
  - Ver OpenAI configurado.
  - Analizar consulta peligrosa.
  - Ejecutar consulta segura.
  - Ver historial.
  - Ejecutar DBA Copilot.
  - Ver recomendaciones.

- Produccion:
  - Rotar cualquier API key expuesta.
  - Guardar nueva key en Azure Key Vault.
  - Actualizar secreto del Container App.
  - Desplegar backend.
  - Ejecutar migraciones.
  - Desplegar frontend.
  - Confirmar que no hay API keys en Git.

## Criterios Para Pasar A Fase 3

- OpenAI esta activo en Azure.
- `ai_provider` aparece como `openai`.
- `ai_configured` aparece como `true`.
- Query Governance bloquea consultas peligrosas.
- Query Governance ejecuta consultas seguras.
- OpenAI explica riesgos y recomendaciones SQL.
- DBA Copilot genera recomendaciones con OpenAI.
- Auditoria queda registrada en PostgreSQL.
- Frontend y backend funcionan desde URLs publicas de Azure.
- No hay secretos en codigo ni documentacion.
