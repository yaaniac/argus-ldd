"""
Sistema de deduplicación de licitaciones.
Evita almacenar la misma licitación dos veces aunque venga de múltiples búsquedas.
"""
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Licitacion, Portal
from scrapers.base import LicitacionData

logger = logging.getLogger(__name__)


class Deduplicator:
    """
    Verifica duplicados contra la base de datos antes de insertar.

    Estrategia de deduplicación (en orden de prioridad):
    1. Hash de contenido (SHA-256 de título + external_id + organismo)
    2. external_id + portal_id (si el portal provee IDs únicos)
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self._cache: set[str] = set()  # Cache en memoria para la sesión actual

    async def preload_cache(self, portal_id: int) -> None:
        """Precarga hashes del portal actual para evitar N+1 queries."""
        result = await self.session.execute(
            select(Licitacion.content_hash).where(Licitacion.portal_id == portal_id)
        )
        hashes = result.scalars().all()
        self._cache.update(hashes)
        logger.debug(f"Cache de deduplicación: {len(self._cache)} hashes cargados")

    async def is_duplicate(self, data: LicitacionData, portal_id: int) -> bool:
        """
        Retorna True si la licitación ya existe en la DB.
        Usa cache en memoria para performance.
        """
        content_hash = data.compute_hash()

        # Verificar en cache primero
        if content_hash in self._cache:
            return True

        # Verificar en DB
        result = await self.session.execute(
            select(Licitacion).where(
                Licitacion.portal_id == portal_id,
                Licitacion.content_hash == content_hash,
            ).limit(1)
        )
        exists = result.scalar_one_or_none() is not None

        if not exists and data.external_id:
            # También verificar por external_id
            result2 = await self.session.execute(
                select(Licitacion).where(
                    Licitacion.portal_id == portal_id,
                    Licitacion.external_id == data.external_id,
                ).limit(1)
            )
            exists = result2.scalar_one_or_none() is not None

        if exists:
            self._cache.add(content_hash)

        return exists

    def mark_seen(self, data: LicitacionData) -> None:
        """Marca el hash como visto en la sesión actual (antes de commitear)."""
        self._cache.add(data.compute_hash())
