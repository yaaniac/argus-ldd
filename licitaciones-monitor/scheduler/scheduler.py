"""
Scheduler de búsquedas automáticas usando APScheduler.
Ejecuta búsquedas periódicas y gestiona el ciclo de vida del job.
"""
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from config import settings
from database.db import get_db_context
from core.orchestrator import SearchOrchestrator
from alerts.notifier import AlertNotifier

logger = logging.getLogger(__name__)

# Instancia global del scheduler
_scheduler: AsyncIOScheduler | None = None


async def start_scheduler():
    """Inicia el scheduler con el job de búsqueda periódica."""
    global _scheduler

    _scheduler = AsyncIOScheduler(timezone="America/Argentina/Buenos_Aires")

    # Job principal: búsqueda periódica
    _scheduler.add_job(
        run_scheduled_search,
        trigger=IntervalTrigger(hours=settings.SCAN_INTERVAL_HOURS),
        id="scheduled_search",
        name="Búsqueda periódica de licitaciones",
        replace_existing=True,
        max_instances=1,  # No ejecutar si ya hay una corriendo
    )

    _scheduler.start()
    logger.info(
        f"Scheduler iniciado — búsquedas cada {settings.SCAN_INTERVAL_HOURS} horas"
    )


async def stop_scheduler():
    """Detiene el scheduler de forma limpia."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler detenido")


async def run_scheduled_search():
    """
    Job ejecutado por el scheduler.
    Corre el ciclo completo: scraping → dedup → DB → alertas.
    """
    logger.info("Iniciando búsqueda programada...")
    try:
        async with get_db_context() as db:
            orchestrator = SearchOrchestrator(db)
            run = await orchestrator.run(triggered_by="scheduler")

            logger.info(
                f"Búsqueda programada finalizada: "
                f"#{run.id} — {run.licitaciones_new} nuevas de {run.licitaciones_found}"
            )

            # Enviar alerta si hay nuevas licitaciones
            if run.licitaciones_new and run.licitaciones_new > 0:
                await _send_alerts(run)

    except Exception as e:
        logger.exception(f"Error en búsqueda programada: {e}")


async def _send_alerts(run):
    """Envía alertas si están habilitadas."""
    if not settings.ALERTS_ENABLED:
        return
    try:
        notifier = AlertNotifier()
        async with get_db_context() as db:
            await notifier.notify_new_licitaciones(db, run)
    except Exception as e:
        logger.error(f"Error enviando alertas: {e}")


def get_next_run_time() -> str | None:
    """Retorna la próxima ejecución programada como string."""
    if not _scheduler or not _scheduler.running:
        return None
    job = _scheduler.get_job("scheduled_search")
    if job and job.next_run_time:
        return job.next_run_time.strftime("%d/%m/%Y %H:%M")
    return None
