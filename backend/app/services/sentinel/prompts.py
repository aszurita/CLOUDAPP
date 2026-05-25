"""Prompts and safe diagnostic SQL catalog for DB Sentinel AI Copilot."""
from __future__ import annotations

META_AGENT_SYSTEM_PROMPT = """
Eres el DBA Copilot de DB Sentinel AI, un asistente para DBAs y equipos DataOps
en entidades financieras. Recibes evidencia de modelos ML; no predices por tu
cuenta. Debes resumir evidencia, impacto operativo, causas raíz probables,
acciones seguras y SQL de diagnóstico de solo lectura.

Reglas:
- Nunca generes SQL que modifique datos o esquema.
- Nunca recomiendes ejecutar mitigaciones sin aprobación DBA.
- Si el riesgo es crítico, recomienda escalamiento inmediato.
- Sé técnico, conciso, accionable y específico.
- Responde JSON válido.
"""

META_AGENT_USER_TEMPLATE = """
Sistema: {engine} - {database_name}
Predicho en: {predicted_at}
Risk score: {risk_score}
Impacto: {impact_level}
Incidente predicho: {predicted_incident_type}
Horizonte: {horizon_minutes} minutos

Evidencia predictor:
{predictor_evidence}

RCA Top-3:
{rca_diagnosis}

Métricas actuales:
{current_metrics}

Queries lentas:
{slow_queries}
"""

SAFE_DIAGNOSTIC_SQLS = {
    "lock_wait_storm": [
        {
            "category": "locks",
            "title": "Sesiones bloqueadas y bloqueadores",
            "sql": """
SELECT
    blocked.pid AS blocked_pid,
    blocked.state AS blocked_state,
    LEFT(blocked.query, 300) AS blocked_query,
    EXTRACT(EPOCH FROM (NOW() - blocked.query_start)) AS blocked_for_seconds,
    blocking.pid AS blocking_pid,
    blocking.state AS blocking_state,
    LEFT(blocking.query, 300) AS blocking_query
FROM pg_stat_activity blocked
JOIN pg_stat_activity blocking
    ON blocking.pid = ANY(pg_blocking_pids(blocked.pid))
WHERE cardinality(pg_blocking_pids(blocked.pid)) > 0
ORDER BY blocked_for_seconds DESC;
            """.strip(),
        },
        {
            "category": "transactions",
            "title": "Transacciones abiertas de larga duración",
            "sql": """
SELECT
    pid,
    state,
    EXTRACT(EPOCH FROM (NOW() - xact_start)) AS xact_seconds,
    wait_event_type,
    wait_event,
    LEFT(query, 300) AS query
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
  AND EXTRACT(EPOCH FROM (NOW() - xact_start)) > 30
  AND pid != pg_backend_pid()
ORDER BY xact_seconds DESC;
            """.strip(),
        },
    ],
    "deadlock": [
        {
            "category": "locks",
            "title": "Locks actuales por relación y modo",
            "sql": """
SELECT
    locktype,
    relation::regclass AS relation_name,
    mode,
    granted,
    COUNT(*) AS lock_count
FROM pg_locks
GROUP BY locktype, relation, mode, granted
ORDER BY granted ASC, lock_count DESC;
            """.strip(),
        },
        {
            "category": "database",
            "title": "Contador de deadlocks por base",
            "sql": """
SELECT
    datname,
    deadlocks,
    xact_commit,
    xact_rollback
FROM pg_stat_database
WHERE datname = current_database();
            """.strip(),
        },
    ],
    "concurrent_commits": [
        {
            "category": "wal",
            "title": "Actividad WAL actual",
            "sql": """
SELECT
    wal_records,
    wal_fpi,
    wal_bytes,
    wal_buffers_full,
    wal_write,
    wal_sync,
    wal_write_time,
    wal_sync_time
FROM pg_stat_wal;
            """.strip(),
        },
        {
            "category": "transactions",
            "title": "Throughput transaccional de la base",
            "sql": """
SELECT
    datname,
    xact_commit,
    xact_rollback,
    blks_read,
    blks_hit,
    temp_files,
    temp_bytes
FROM pg_stat_database
WHERE datname = current_database();
            """.strip(),
        },
    ],
    "generic": [
        {
            "category": "activity",
            "title": "Actividad PostgreSQL no idle",
            "sql": """
SELECT
    pid,
    usename,
    state,
    wait_event_type,
    wait_event,
    EXTRACT(EPOCH FROM (NOW() - query_start)) AS query_seconds,
    LEFT(query, 300) AS query
FROM pg_stat_activity
WHERE state <> 'idle'
  AND pid <> pg_backend_pid()
ORDER BY query_seconds DESC;
            """.strip(),
        },
        {
            "category": "queries",
            "title": "Queries con mayor latencia media",
            "sql": """
SELECT
    queryid,
    calls,
    ROUND(mean_exec_time::numeric, 2) AS mean_exec_time_ms,
    ROUND(total_exec_time::numeric / 1000, 2) AS total_exec_time_sec,
    rows,
    shared_blks_hit,
    shared_blks_read,
    LEFT(query, 300) AS query
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;
            """.strip(),
        },
    ],
}
