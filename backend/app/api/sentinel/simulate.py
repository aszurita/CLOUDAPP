"""Simulation orchestration endpoints for DB Sentinel AI lab faults."""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from app.core.paths import find_workspace_root
from app.core.config import get_settings
from app.schemas.sentinel_schemas import FaultJobResponse, SimulateFaultRequest

router = APIRouter()

IA_BASES_ROOT = find_workspace_root(Path(__file__)) / "IA_BASES"
LOCAL_LAB_DSN = "postgresql://sentinel:sentinel_lab_2026@localhost:5433/core_banking_sim"

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
        "script": "lab\\workloads\\transfer_workload.py",
        "args": lambda req: (
            f"--users {_deadlock_drill_users(req.intensity)} "
            f"--duration {req.duration_seconds} "
            f"--tps {_deadlock_drill_tps(req.intensity)}"
        ),
        "plan": [
            "Ejecutar transferencias bancarias concurrentes con alta presion.",
            "Forzar cruces de locks entre cuentas origen y destino.",
            "Observar deadlocks_delta, waiting_sessions y la prediccion del modelo.",
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
        status = "starting"

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

    if not request.dry_run:
        if not config.get("script"):
            raise HTTPException(status_code=400, detail="Este fallo no tiene script local ejecutable.")
        _ensure_local_lab_execution()
        thread = threading.Thread(target=_run_local_fault_demo, args=(job_id, fault_type, request), daemon=True)
        thread.start()

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


def _ensure_local_lab_execution() -> None:
    settings = get_settings()
    monitor_url = settings.sentinel_monitor_db_url or LOCAL_LAB_DSN
    parsed = urlparse(monitor_url.replace("postgresql+psycopg://", "postgresql://", 1))
    if parsed.hostname not in {"localhost", "127.0.0.1", "postgres"}:
        raise HTTPException(
            status_code=400,
            detail="La ejecución real de fallos solo está habilitada para el lab local Docker.",
        )
    if not IA_BASES_ROOT.exists():
        raise HTTPException(status_code=400, detail=f"No se encontró IA_BASES en {IA_BASES_ROOT}.")


def _run_local_fault_demo(job_id: str, fault_type: str, request: SimulateFaultRequest) -> None:
    job = ACTIVE_FAULTS[job_id]
    job["status"] = "running"
    job["plan"] = _execution_plan(fault_type, job["plan"])
    job["processes"] = []
    env = os.environ.copy()
    env["DATABASE_URL"] = get_settings().sentinel_monitor_db_url or LOCAL_LAB_DSN

    try:
        if fault_type == "lock_wait_storm":
            workload_seconds = max(request.duration_seconds + 180, 360)
            transfer_users, transfer_tps, lock_workers = _lock_wait_demo_params(request.intensity)
            workload = _start_python_process(
                job_id=job_id,
                name="normal-transfer",
                script=IA_BASES_ROOT / "lab" / "workloads" / "transfer_workload.py",
                args=["--users", str(transfer_users), "--duration", str(workload_seconds), "--tps", str(transfer_tps)],
                env=env,
            )
            job["processes"].append({"name": "normal-transfer", "pid": workload.pid})
            time.sleep(8)
            fault = _start_python_process(
                job_id=job_id,
                name="lock-wait-storm",
                script=IA_BASES_ROOT / "lab" / "fault_injection" / "lock_wait.py",
                args=["--duration", str(request.duration_seconds), "--workers", str(lock_workers)],
                env=env,
            )
            job["processes"].append({"name": "lock-wait-storm", "pid": fault.pid})
            job["status"] = "fault_running"
            fault.wait()
            job["status"] = "workload_finishing"
            workload.wait(timeout=max(60, workload_seconds))
        else:
            config = FAULT_CATALOG[fault_type]
            script = IA_BASES_ROOT / str(config["script"])
            args = _split_args(config["args"](request))
            fault = _start_python_process(job_id=job_id, name=fault_type, script=script, args=args, env=env)
            job["processes"].append({"name": fault_type, "pid": fault.pid})
            job["status"] = "fault_running"
            fault.wait()

        job["status"] = "completed"
        job["finished_at"] = datetime.now(timezone.utc).isoformat()
    except Exception as exc:
        job["status"] = "failed"
        job["error"] = str(exc)
        job["finished_at"] = datetime.now(timezone.utc).isoformat()


def _start_python_process(
    job_id: str,
    name: str,
    script: Path,
    args: list[str],
    env: dict[str, str],
) -> subprocess.Popen:
    if not script.exists():
        raise FileNotFoundError(f"No se encontró script de demo: {script}")
    log_dir = IA_BASES_ROOT / "lab" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    stdout_path = log_dir / f"{job_id}-{name}-{stamp}.out.log"
    stderr_path = log_dir / f"{job_id}-{name}-{stamp}.err.log"
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    process = subprocess.Popen(
        [sys.executable, str(script), *args],
        cwd=str(IA_BASES_ROOT),
        env=env,
        stdout=stdout_path.open("w", encoding="utf-8"),
        stderr=stderr_path.open("w", encoding="utf-8"),
        creationflags=creationflags,
    )
    ACTIVE_FAULTS[job_id].setdefault("logs", []).append(
        {"name": name, "stdout": str(stdout_path), "stderr": str(stderr_path)}
    )
    return process


def _lock_wait_demo_params(intensity: str) -> tuple[int, float, int]:
    if intensity == "high":
        return 45, 20.0, 45
    if intensity == "low":
        return 18, 8.0, 18
    return 30, 15.0, 30


def _deadlock_drill_users(intensity: str) -> int:
    if intensity == "high":
        return 100
    if intensity == "low":
        return 25
    return 50


def _deadlock_drill_tps(intensity: str) -> int:
    if intensity == "high":
        return 80
    if intensity == "low":
        return 20
    return 40


def _execution_plan(fault_type: str, base_plan: list[str]) -> list[str]:
    if fault_type != "lock_wait_storm":
        return ["Ejecutar fallo local controlado en Docker.", *base_plan]
    return [
        "Arrancar workload normal de transferencias bancarias.",
        "Esperar unos segundos para generar actividad base.",
        "Mantener una transaccion bloqueadora sobre una cuenta de prueba.",
        "Generar workers concurrentes que esperan el lock.",
        "Recolectar metricas para que el dashboard muestre lock waits, fingerprints y RCA.",
    ]


def _split_args(raw: str) -> list[str]:
    return [part for part in raw.split(" ") if part]
