"""
Rutas de gestión de keywords de búsqueda.
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from database.models import Keyword

router = APIRouter(prefix="/api/keywords", tags=["keywords"])


class KeywordCreate(BaseModel):
    term: str
    category: Optional[str] = None
    priority: int = 5
    is_active: bool = True


class KeywordUpdate(BaseModel):
    is_active: Optional[bool] = None
    priority: Optional[int] = None
    category: Optional[str] = None


@router.get("")
async def list_keywords(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Keyword).order_by(Keyword.priority.desc(), Keyword.term)
    )
    return [_serialize(k) for k in result.scalars().all()]


@router.post("", status_code=201)
async def create_keyword(data: KeywordCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(
        select(Keyword).where(Keyword.term == data.term.strip())
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Keyword '{data.term}' ya existe")

    kw = Keyword(
        term=data.term.strip(),
        category=data.category,
        priority=data.priority,
        is_active=data.is_active,
    )
    db.add(kw)
    await db.flush()
    return _serialize(kw)


@router.patch("/{keyword_id}")
async def update_keyword(
    keyword_id: int,
    data: KeywordUpdate,
    db: AsyncSession = Depends(get_db),
):
    kw = await _get_or_404(keyword_id, db)
    if data.is_active is not None:
        kw.is_active = data.is_active
    if data.priority is not None:
        kw.priority = data.priority
    if data.category is not None:
        kw.category = data.category
    await db.flush()
    return _serialize(kw)


@router.delete("/{keyword_id}", status_code=204)
async def delete_keyword(keyword_id: int, db: AsyncSession = Depends(get_db)):
    kw = await _get_or_404(keyword_id, db)
    await db.delete(kw)


async def _get_or_404(keyword_id: int, db: AsyncSession) -> Keyword:
    result = await db.execute(select(Keyword).where(Keyword.id == keyword_id))
    kw = result.scalar_one_or_none()
    if not kw:
        raise HTTPException(status_code=404, detail="Keyword no encontrada")
    return kw


def _serialize(k: Keyword) -> dict:
    return {
        "id": k.id,
        "term": k.term,
        "category": k.category,
        "priority": k.priority,
        "is_active": k.is_active,
        "created_at": k.created_at.isoformat() if k.created_at else None,
    }
