from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.services.core_banking_dashboard import CoreBankingDashboardService

router = APIRouter(prefix="/core-banking", tags=["Core Banking Dashboard"])


@router.get("/dashboard", summary="Dashboard ejecutivo core_banking_sim")
def core_banking_dashboard() -> dict:
    try:
        return CoreBankingDashboardService().dashboard()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/tables", summary="Inventario de tablas core_banking_sim")
def core_banking_tables() -> list[dict]:
    try:
        return CoreBankingDashboardService().tables()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/movements", summary="Movimientos recientes core_banking_sim")
def core_banking_movements(limit: int = Query(default=30, ge=1, le=80)) -> list[dict]:
    try:
        return CoreBankingDashboardService().movements(limit=limit)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
