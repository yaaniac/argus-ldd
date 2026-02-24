"""
Orquestador central del sistema de búsqueda.
Coordina scrapers, deduplicación, scoring y persistencia.

Diseño de concurrencia:
- La sesión principal se usa para leer config y escribir el SearchRun final.
- Cada portal escanea con su PROPIA sesión para evitar conflictos async.
"""
import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database.db import get_db_context, AsyncSessionLocal
from database.models import (
    Keyword, Licitacion, LicitacionStatus, Portal, PortalStatus,
    SearchRun, SearchRunPortal, RunStatus,
)
from scrapers import get_scraper, LicitacionData
from .deduplicator import Deduplicator
from .matcher import KeywordMatcher

logger = logging.getLogger(__name__)


class SearchOrchestrator:
    """
    Coordina el proceso completo de búsqueda:
    1. Carga keywords activas de la DB
    2. Carga portales habilitados
    3. Ejecuta scrapers en paralelo (cada uno con su propia sesión)
    4. Deduplica, puntúa y persiste nuevas licitaciones
    5. Registra la ejecución y estadísticas
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def run(
        self,
        triggered_by: str = "scheduler",
        keywords_override: Optional[list[str]] = None,
        portal_ids: Optional[list[int]] = None,
        date_from: Optional[datetime] = None,
    ) -> SearchRun:
        """Ejecuta una búsqueda completa y retorna el SearchRun con resultados."""
        run = SearchRun(
            status=RunStatus.RUNNING,
            triggered_by=triggered_by,
            started_at=datetime.utcnow(),
        )
        self.session.add(run)
        await self.session.flush()

        try:
            keywords = keywords_override or await self._load_keywords()
            run.keywords_used = list(keywords)

            if not keywords:
                logger.warning("No hay keywords activas. Búsqueda abortada.")
                run.status = RunStatus.FAILED
                run.finished_at = datetime.utcnow()
                return run

            if date_from is None:
                date_from = datetime.utcnow() - timedelta(hours=48)

            portals = await self._load_portals(portal_ids)
            run.portals_scanned = len(portals)
            await self.session.flush()

            logger.info(
                f"SearchRun #{run.id}: {len(keywords)} keywords, "
                f"{len(portals)} portales, desde {date_from.date()}"
            )

            # SQLite no soporta escrituras concurrentes: usar semáforo=1
            # PostgreSQL puede usar mayor concurrencia
            max_concurrent = 1 if settings.is_sqlite else 3
            semaphore = asyncio.Semaphore(max_concurrent)
            tasks = [
                self._scan_portal_isolated(
                    portal_id=portal.id,
                    portal_short_name=portal.short_name,
                    portal_url=portal.url,
                    portal_scraper_class=portal.scraper_class,
                    portal_scraper_config=portal.scraper_config,
                    keywords=list(keywords),
                    date_from=date_from,
                    run_id=run.id,
                    semaphore=semaphore,
                )
                for portal in portals
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            total_found = 0
            total_new = 0
            failures = 0
            error_details = []

            for portal, result in zip(portals, results):
                if isinstance(result, Exception):
                    failures += 1
                    error_details.append({
                        "portal": portal.short_name,
                        "error": str(result)[:200],
                    })
                else:
                    found, new = result
                    total_found += found
                    total_new += new

            run.licitaciones_found = total_found
            run.licitaciones_new = total_new
            run.portals_failed = failures
            run.finished_at = datetime.utcnow()
            run.duration_seconds = (run.finished_at - run.started_at).total_seconds()
            run.error_details = error_details or None

            if failures == len(portals):
                run.status = RunStatus.FAILED
            elif failures > 0:
                run.status = RunStatus.PARTIAL
            else:
                run.status = RunStatus.SUCCESS

            await self.session.flush()
            logger.info(
                f"SearchRun #{run.id} finalizado: "
                f"{total_new} nuevas / {total_found} encontradas "
                f"en {run.duration_seconds:.1f}s"
            )

        except Exception as e:
            logger.exception(f"Error crítico en SearchRun #{run.id}: {e}")
            run.status = RunStatus.FAILED
            run.finished_at = datetime.utcnow()
            run.error_details = [{"error": str(e)}]

        return run

    async def _scan_portal_isolated(
        self,
        portal_id: int,
        portal_short_name: str,
        portal_url: str,
        portal_scraper_class: str,
        portal_scraper_config: dict | None,
        keywords: list[str],
        date_from: datetime,
        run_id: int,
        semaphore: asyncio.Semaphore,
    ) -> tuple[int, int]:
        """
        Escanea un portal usando su propia sesión de DB.
        Completamente aislado para evitar conflictos de sesión async.
        """
        async with semaphore:
            async with AsyncSessionLocal() as db:
                portal_run = SearchRunPortal(run_id=run_id, portal_id=portal_id)
                db.add(portal_run)
                await db.flush()

                start = time.time()
                try:
                    scraper = get_scraper(portal_scraper_class, portal_url, portal_scraper_config)
                    raw_results = await scraper.search(keywords, date_from)

                    dedup = Deduplicator(db)
                    await dedup.preload_cache(portal_id)
                    matcher = KeywordMatcher(keywords, operator="OR")

                    found = len(raw_results)
                    new_count = 0

                    for data in raw_results:
                        if await dedup.is_duplicate(data, portal_id):
                            continue

                        match = matcher.match(data.titulo, data.descripcion, data.organismo)

                        lic = Licitacion(
                            portal_id=portal_id,
                            external_id=data.external_id,
                            content_hash=data.compute_hash(),
                            titulo=data.titulo,
                            descripcion=data.descripcion,
                            numero_expediente=data.numero_expediente,
                            numero_licitacion=data.numero_licitacion,
                            organismo=data.organismo,
                            tipo_contratacion=data.tipo_contratacion,
                            monto_estimado=data.monto_estimado,
                            moneda=data.moneda,
                            fecha_publicacion=data.fecha_publicacion,
                            fecha_apertura=data.fecha_apertura,
                            fecha_cierre=data.fecha_cierre,
                            url_detalle=data.url_detalle,
                            url_pliego=data.url_pliego,
                            matched_keywords=match.keywords_found or data.matched_keywords,
                            relevance_score=match.score,
                            status=LicitacionStatus.NUEVA,
                            is_new=True,
                            raw_data=data.raw_data,
                        )
                        db.add(lic)
                        dedup.mark_seen(data)
                        new_count += 1

                    # Actualizar estado del portal
                    portal = await db.get(Portal, portal_id)
                    if portal:
                        portal.last_checked_at = datetime.utcnow()
                        portal.last_success_at = datetime.utcnow()
                        portal.consecutive_errors = 0
                        portal.status = PortalStatus.ACTIVE

                    portal_run.status = "success"
                    portal_run.licitaciones_found = found
                    portal_run.licitaciones_new = new_count
                    portal_run.duration_seconds = time.time() - start

                    await db.commit()

                    logger.info(
                        f"Portal {portal_short_name}: "
                        f"{found} encontradas, {new_count} nuevas"
                    )
                    return found, new_count

                except Exception as e:
                    await db.rollback()
                    elapsed = time.time() - start
                    logger.error(f"Error en portal {portal_short_name}: {e}")

                    # Registrar el error en una sesión limpia
                    async with AsyncSessionLocal() as db2:
                        portal_run2 = SearchRunPortal(
                            run_id=run_id,
                            portal_id=portal_id,
                            status="error",
                            error=str(e)[:500],
                            duration_seconds=elapsed,
                        )
                        db2.add(portal_run2)

                        portal2 = await db2.get(Portal, portal_id)
                        if portal2:
                            portal2.last_checked_at = datetime.utcnow()
                            portal2.last_error = str(e)[:500]
                            portal2.consecutive_errors = (portal2.consecutive_errors or 0) + 1
                            if portal2.consecutive_errors >= 5:
                                portal2.status = PortalStatus.ERROR

                        await db2.commit()

                    raise

    async def _load_keywords(self) -> list[str]:
        result = await self.session.execute(
            select(Keyword.term)
            .where(Keyword.is_active == True)
            .order_by(Keyword.priority.desc())
        )
        return list(result.scalars().all())

    async def _load_portals(self, portal_ids: Optional[list[int]]) -> list[Portal]:
        query = select(Portal).where(Portal.is_enabled == True)
        if portal_ids:
            query = query.where(Portal.id.in_(portal_ids))
        result = await self.session.execute(query.order_by(Portal.level, Portal.name))
        return list(result.scalars().all())
