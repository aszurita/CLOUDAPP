"""Simulation orchestration endpoints for DB Sentinel AI lab faults."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from app.core.paths import find_workspace_root
from app.schemas.sentinel_schemas import FaultJobResponse, SimulateFaultRequest

router = APIRouter()

IA_BASES_ROOT = find_workspace_root(Path(__file__)) / "IA_BASES"

FAULT_CATALOG: dict[str, dict[str, Any]] = {
    "lock_wait_storm": {
        "title": "Lock wait storm",
        "risk": "critical",
        "script": "lab\\fault_injection\\lock_wait.py",
        "args": lambda req: f"--duration {req.duration_seconds} --workers {25 if req.intensity == 'high' else 12}",
        "plan": [
            "Mantener una transaccion bloqueadora sobre una cuenta de prueba.",
            "Generar workers concurrentes que esperan el lock.",
            "Recolectar pg_stat_activity y pg_locks durante la ventana.",
        ],
    },
    "missing_index": {
        "title": "Missing index regression",
        "risk": "high",
        "script": "lab\\fault_injection\\missing_index.py",
        "args": lambda req: f"--duration {req.duration_seconds}",
        "plan": [
            "Eliminar indices de laboratorio temporalmente.",
            "Ejecutar workload de reportería para forzar sequential scans.",
            "Restaurar indices al finalizar.",
        ],
    },
    "heavy_workload": {
        "title": "Heavy workload",
        "risk": "high",
        "script": "lab\\fault_injection\\heavy_workload.py",
        "args": lambda req: f"--duration {req.duration_seconds} --users {120 if req.intensity == 'high' else 60}",
        "plan": [
            "Aumentar usuarios concurrentes del workload bancario.",
            "Mezclar transferencias OLTP con queries analiticas pesadas.",
            "Observar latencia, sesiones activas y presion WAL.",
        ],
    },
    "vacuum_problem": {
        "title": "Vacuum/bloat pressure",
        "risk": "medium",
        "script": "lab\\fault_injection\\vacuum_problem.py",
        "args": lambda req: f"--duration {req.duration_seconds} --batch {1500 if req.intensity == 'high' else 700}",
        "plan": [
            "Generar churn de inserts/deletes sobre tablas de laboratorio.",
            "Aumentar dead tuples y observar autovacuum.",
            "Restaurar parametros y limpiar al finalizar.",
        ],
    },
    "concurrent_commits": {
        "title": "Concurrent commits",
        "risk": "high",
        "script": "lab\\workloads\\transfer_workload.py",
        "args": lambda req: f"--duration {req.duration_seconds} --users {100 if req.intensity == 'high' else 50} --tps 80",
        "plan": [
            "Ejecutar transferencias concurrentes con commits pequenos.",
            "Observar WAL, commits por minuto y latencia de confirmacion.",
            "Correlacionar con el predictor y RCA.",
        ],
    },
    "deadlock": {
        "title": "Deadlock drill",
        "risk": "high",
        "script": None,
        "args": lambda req: "",
        "plan": [
            "Ejecutar dos transacciones con orden de locks invertido.",
            "Confirmar incremento en deadlocks_delta.",
            "Revisar logs y acciones recomendadas por RCA.",
        ],
    },
    "io_saturation": {
        "title": "I/O saturation",
        "risk": "medium",
        "script": None,
        "args": lambda req: "",
        "plan": [
            "Generar carga I/O en el entorno de laboratorio.",
            "Medir blk_read_time_delta, temp_bytes_delta y latencia media.",
            "Detener carga y validar recuperacion.",
        ],
    },
    "replication_lag": {
        "title": "Replication lag",
        "risk": "medium",
        "script": None,
        "args": lambda req: "",
        "plan": [
            "Aumentar carga en primary o pausar replica de laboratorio.",
            "Medir write_lag, flush_lag y replay_lag.",
            "Restaurar replica y verificar catch-up.",
        ],
    },
}

ACTIVE_FAULTS: dict[str, dict[str, Any]] = {}


@router.get("/simulate/faults", summary="Lista fallos disponibles para el lab")
def list_available_faults() -> dict[str, Any]:
    return {
        "faults": [
            {
                "id": fault_id,
                "title": config["title"],
                "risk": config["risk"],
                "api_mode": "dry_run_plan",
                "has_lab_script": bool(config.get("script")),
            }
            for fault_id, config in FAULT_CATALOG.items()
        ]
    }


@router.post(
    "/simulate/fault/{fault_type}",
    response_model=FaultJobResponse,
    summary="Prepara simulacion controlada de fallo",
)
def simulate_fault(
    fault_type: str,
    request: SimulateFaultRequest,
) -> dict[str, Any]:
    if request.fault_type and request.fault_type != fault_type:
        raise HTTPException(status_code=400, detail="fault_type del path y body no coinciden")
    if fault_type not in FAULT_CATALOG:
        raise HTTPException(status_code=404, detail="Fallo no soportado")

    config = FAULT_CATALOG[fault_type]
    command = _build_command(config, request)
    job_id = str(uuid4())[:8]
    status = "planned"
    if not request.dry_run:
        status = "requires_manual_execution"

    job = {
        "job_id": job_id,
        "fault_type": fault_type,
        "status": status,
        "dry_run": request.dry_run,
        "duration_seconds": request.duration_seconds,
        "intensity": request.intensity,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "plan": config["plan"],
        "command": command,
    }
    ACTIVE_FAULTS[job_id] = job
    return job


@router.get("/simulate/fault/{job_id}/status", summary="Estado de simulacion")
def get_fault_status(job_id: str) -> dict[str, Any]:
    if job_id not in ACTIVE_FAULTS:
        raise HTTPException(status_code=404, detail="Job no encontrado")
    return ACTIVE_FAULTS[job_id]


def _build_command(config: dict[str, Any], request: SimulateFaultRequest) -> str | None:
    script = config.get("script")
    if not script:
        return None
    args = config["args"](request)
    return f"cd {IA_BASES_ROOT}; python {script} {args}".strip()
