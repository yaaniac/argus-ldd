"""
Rutas de gestión de portales.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from database.models import Portal, PortalLevel, PortalStatus
from scrapers import SCRAPER_REGISTRY

router = APIRouter(prefix="/api/portales", tags=["portales"])


class PortalCreate(BaseModel):
    name: str
    short_name: str
    url: str
    level: str  # "nacional" | "provincial" | "municipal"
    province: Optional[str] = None
    municipality: Optional[str] = None
    scraper_class: str = "GenericMunicipalScraper"
    scraper_config: Optional[dict] = None
    is_enabled: bool = True


class PortalUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    is_enabled: Optional[bool] = None
    scraper_config: Optional[dict] = None


@router.get("")
async def list_portales(db: AsyncSession = Depends(get_db)):
    """Lista todos los portales registrados."""
    result = await db.execute(
        select(Portal).order_by(Portal.level, Portal.name)
    )
    portales = result.scalars().all()
    return [_serialize(p) for p in portales]


@router.post("", status_code=201)
async def create_portal(data: PortalCreate, db: AsyncSession = Depends(get_db)):
    """Registra un nuevo portal de licitaciones."""
    # Validar scraper_class
    if data.scraper_class not in SCRAPER_REGISTRY:
        raise HTTPException(
            status_code=400,
            detail=f"Scraper '{data.scraper_class}' no existe. "
                   f"Opciones: {list(SCRAPER_REGISTRY.keys())}",
        )

    # Verificar short_name único
    existing = await db.execute(
        select(Portal).where(Portal.short_name == data.short_name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Ya existe portal con short_name '{data.short_name}'")

    try:
        level = PortalLevel(data.level)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Level inválido: {data.level}")

    portal = Portal(
        name=data.name,
        short_name=data.short_name,
        url=data.url,
        level=level,
        province=data.province,
        municipality=data.municipality,
        scraper_class=data.scraper_class,
        scraper_config=data.scraper_config,
        is_enabled=data.is_enabled,
    )
    db.add(portal)
    await db.flush()
    return _serialize(portal)


@router.get("/{portal_id}")
async def get_portal(portal_id: int, db: AsyncSession = Depends(get_db)):
    portal = await _get_or_404(portal_id, db)
    return _serialize(portal)


@router.patch("/{portal_id}")
async def update_portal(
    portal_id: int,
    data: PortalUpdate,
    db: AsyncSession = Depends(get_db),
):
    portal = await _get_or_404(portal_id, db)
    if data.name is not None:
        portal.name = data.name
    if data.url is not None:
        portal.url = data.url
    if data.is_enabled is not None:
        portal.is_enabled = data.is_enabled
    if data.scraper_config is not None:
        portal.scraper_config = data.scraper_config
    await db.flush()
    return _serialize(portal)


@router.delete("/{portal_id}", status_code=204)
async def delete_portal(portal_id: int, db: AsyncSession = Depends(get_db)):
    portal = await _get_or_404(portal_id, db)
    await db.delete(portal)


@router.get("/scrapers/disponibles")
async def list_scrapers():
    """Lista los scrapers disponibles para asignar a portales."""
    return list(SCRAPER_REGISTRY.keys())


async def _get_or_404(portal_id: int, db: AsyncSession) -> Portal:
    result = await db.execute(select(Portal).where(Portal.id == portal_id))
    portal = result.scalar_one_or_none()
    if not portal:
        raise HTTPException(status_code=404, detail="Portal no encontrado")
    return portal


def _serialize(p: Portal) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "short_name": p.short_name,
        "url": p.url,
        "level": p.level.value,
        "province": p.province,
        "municipality": p.municipality,
        "scraper_class": p.scraper_class,
        "scraper_config": p.scraper_config,
        "status": p.status.value,
        "is_enabled": p.is_enabled,
        "last_checked_at": p.last_checked_at.isoformat() if p.last_checked_at else None,
        "last_success_at": p.last_success_at.isoformat() if p.last_success_at else None,
        "last_error": p.last_error,
        "consecutive_errors": p.consecutive_errors,
    }
