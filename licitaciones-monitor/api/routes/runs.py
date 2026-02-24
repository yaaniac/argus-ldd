"""
Rutas de ejecuciones de búsqueda (runs).
Permite disparar búsquedas manuales y consultar el historial.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from database.models import SearchRun, SearchRunPortal, Portal
from core.orchestrator import SearchOrchestrator
from database.db import get_db_context

router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.get("")
async def list_runs(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Historial de ejecuciones de búsqueda."""
    from sqlalchemy import func
    total = (await db.execute(
        select(func.count(SearchRun.id))
    )).scalar_one()

    result = await db.execute(
        select(SearchRun)
        .order_by(desc(SearchRun.started_at))
        .offset((page - 1) * size)
        .limit(size)
    )
    runs = result.scalars().all()

    return {
        "total": total,
        "page": page,
        "items": [_serialize_run(r) for r in runs],
    }


@router.get("/{run_id}")
async def get_run(run_id: int, db: AsyncSession = Depends(get_db)):
    """Detalle de una ejecución incluyendo resultados por portal."""
    result = await db.execute(select(SearchRun).where(SearchRun.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Run no encontrado")

    # Cargar portal_runs
    pr_result = await db.execute(
        select(SearchRunPortal, Portal.name, Portal.short_name)
        .join(Portal, SearchRunPortal.portal_id == Portal.id)
        .where(SearchRunPortal.run_id == run_id)
    )
    portal_runs = pr_result.all()

    data = _serialize_run(run)
    data["portales"] = [
        {
            "portal": name,
            "short_name": sname,
            "status": pr.status,
            "found": pr.licitaciones_found,
            "new": pr.licitaciones_new,
            "duration": pr.duration_seconds,
            "error": pr.error,
        }
        for pr, name, sname in portal_runs
    ]
    return data


@router.post("/trigger")
async def trigger_run(
    background_tasks: BackgroundTasks,
    keywords: Optional[list[str]] = None,
    portal_ids: Optional[list[int]] = None,
):
    """
    Dispara una búsqueda manual en segundo plano.
    Retorna inmediatamente con el mensaje de confirmación.
    """
    background_tasks.add_task(_run_search, keywords, portal_ids)
    return {
        "message": "Búsqueda iniciada en segundo plano",
        "keywords": keywords,
        "portales": portal_ids or "todos",
    }


async def _run_search(
    keywords: Optional[list[str]],
    portal_ids: Optional[list[int]],
):
    """Tarea de fondo: ejecuta la búsqueda."""
    async with get_db_context() as db:
        orchestrator = SearchOrchestrator(db)
        await orchestrator.run(
            triggered_by="api",
            keywords_override=keywords,
            portal_ids=portal_ids,
        )


def _serialize_run(r: SearchRun) -> dict:
    return {
        "id": r.id,
        "status": r.status.value,
        "triggered_by": r.triggered_by,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "finished_at": r.finished_at.isoformat() if r.finished_at else None,
        "duration_seconds": r.duration_seconds,
        "portals_scanned": r.portals_scanned,
        "portals_failed": r.portals_failed,
        "licitaciones_found": r.licitaciones_found,
        "licitaciones_new": r.licitaciones_new,
        "keywords_used": r.keywords_used,
        "error_details": r.error_details,
    }
