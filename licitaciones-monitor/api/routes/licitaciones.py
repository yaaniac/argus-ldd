"""
Rutas de licitaciones — API REST + vistas HTML.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select, desc, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from database.models import Licitacion, Portal, LicitacionStatus

router = APIRouter()


# ──────────────────────────────────────────────
# API JSON endpoints
# ──────────────────────────────────────────────

@router.get("/api/licitaciones")
async def list_licitaciones(
    q: Optional[str] = Query(None, description="Búsqueda en título/descripción"),
    portal_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None, description="Filtrar por keyword matcheada"),
    fecha_desde: Optional[str] = Query(None),
    fecha_hasta: Optional[str] = Query(None),
    solo_nuevas: bool = Query(False),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Lista licitaciones con filtros avanzados."""
    query = select(Licitacion).join(Portal)

    # Filtros
    if q:
        q_lower = f"%{q.lower()}%"
        query = query.where(
            or_(
                func.lower(Licitacion.titulo).like(q_lower),
                func.lower(Licitacion.descripcion).like(q_lower),
                func.lower(Licitacion.organismo).like(q_lower),
            )
        )
    if portal_id:
        query = query.where(Licitacion.portal_id == portal_id)
    if status:
        query = query.where(Licitacion.status == status)
    if solo_nuevas:
        query = query.where(Licitacion.is_new == True)
    if fecha_desde:
        try:
            dt = datetime.fromisoformat(fecha_desde)
            query = query.where(Licitacion.fecha_publicacion >= dt)
        except ValueError:
            pass
    if fecha_hasta:
        try:
            dt = datetime.fromisoformat(fecha_hasta)
            query = query.where(Licitacion.fecha_publicacion <= dt)
        except ValueError:
            pass

    # Total count
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar_one()

    # Paginación
    offset = (page - 1) * size
    query = query.order_by(desc(Licitacion.created_at)).offset(offset).limit(size)
    result = await db.execute(query)
    licitaciones = result.scalars().all()

    return {
        "total": total,
        "page": page,
        "size": size,
        "pages": (total + size - 1) // size,
        "items": [_serialize_licitacion(lic) for lic in licitaciones],
    }


@router.get("/api/licitaciones/{licitacion_id}")
async def get_licitacion(
    licitacion_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Detalle de una licitación."""
    result = await db.execute(
        select(Licitacion).where(Licitacion.id == licitacion_id)
    )
    lic = result.scalar_one_or_none()
    if not lic:
        raise HTTPException(status_code=404, detail="Licitación no encontrada")

    # Marcar como vista
    if lic.is_new:
        lic.is_new = False
        if lic.status == LicitacionStatus.NUEVA:
            lic.status = LicitacionStatus.VISTA
        await db.flush()

    return _serialize_licitacion(lic, full=True)


@router.patch("/api/licitaciones/{licitacion_id}/status")
async def update_status(
    licitacion_id: int,
    status: str,
    db: AsyncSession = Depends(get_db),
):
    """Actualiza el estado de una licitación."""
    result = await db.execute(
        select(Licitacion).where(Licitacion.id == licitacion_id)
    )
    lic = result.scalar_one_or_none()
    if not lic:
        raise HTTPException(status_code=404, detail="Licitación no encontrada")

    valid_statuses = [s.value for s in LicitacionStatus]
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Estado inválido. Opciones: {valid_statuses}")

    lic.status = status
    await db.flush()
    return {"id": licitacion_id, "status": status}


@router.get("/api/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    """Estadísticas generales del sistema."""
    total = (await db.execute(select(func.count(Licitacion.id)))).scalar_one()
    nuevas = (await db.execute(
        select(func.count(Licitacion.id)).where(Licitacion.is_new == True)
    )).scalar_one()
    hoy = (await db.execute(
        select(func.count(Licitacion.id)).where(
            func.date(Licitacion.created_at) == func.date(func.now())
        )
    )).scalar_one()

    por_portal = await db.execute(
        select(Portal.name, Portal.short_name, func.count(Licitacion.id))
        .join(Licitacion, Licitacion.portal_id == Portal.id, isouter=True)
        .group_by(Portal.id)
        .order_by(desc(func.count(Licitacion.id)))
    )

    return {
        "total_licitaciones": total,
        "nuevas": nuevas,
        "hoy": hoy,
        "por_portal": [
            {"portal": name, "short_name": sn, "total": cnt}
            for name, sn, cnt in por_portal.all()
        ],
    }


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _serialize_licitacion(lic: Licitacion, full: bool = False) -> dict:
    d = {
        "id": lic.id,
        "titulo": lic.titulo,
        "organismo": lic.organismo,
        "tipo_contratacion": lic.tipo_contratacion,
        "numero_licitacion": lic.numero_licitacion,
        "numero_expediente": lic.numero_expediente,
        "fecha_publicacion": lic.fecha_publicacion.isoformat() if lic.fecha_publicacion else None,
        "fecha_apertura": lic.fecha_apertura.isoformat() if lic.fecha_apertura else None,
        "url_detalle": lic.url_detalle,
        "portal_id": lic.portal_id,
        "status": lic.status.value if lic.status else "nueva",
        "is_new": lic.is_new,
        "matched_keywords": lic.matched_keywords or [],
        "relevance_score": round(lic.relevance_score or 0, 2),
        "created_at": lic.created_at.isoformat() if lic.created_at else None,
        "monto_estimado": lic.monto_estimado,
        "moneda": lic.moneda,
    }
    if full:
        d["descripcion"] = lic.descripcion
        d["url_pliego"] = lic.url_pliego
        d["fecha_cierre"] = lic.fecha_cierre.isoformat() if lic.fecha_cierre else None
    return d
