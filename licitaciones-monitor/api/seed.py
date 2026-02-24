"""
Seed inicial de la base de datos.
Carga portales y keywords por defecto en la primera ejecución.
"""
import json
import logging
from pathlib import Path

from sqlalchemy import select

from database.db import get_db_context
from database.models import Keyword, Portal, PortalLevel

logger = logging.getLogger(__name__)

PORTALS_REGISTRY = Path("data/portals_registry.json")

# Keywords forenses por defecto
DEFAULT_KEYWORDS = [
    {"term": "equipos forenses", "category": "equipamiento", "priority": 10},
    {"term": "criminalistica", "category": "especialidad", "priority": 10},
    {"term": "laboratorio forense", "category": "infraestructura", "priority": 9},
    {"term": "investigacion criminal", "category": "especialidad", "priority": 9},
    {"term": "pericias", "category": "especialidad", "priority": 8},
    {"term": "ADN", "category": "genetica", "priority": 8},
    {"term": "balistica", "category": "especialidad", "priority": 8},
    {"term": "software forense", "category": "software", "priority": 8},
    {"term": "caligrafo", "category": "especialidad", "priority": 7},
    {"term": "grafologo", "category": "especialidad", "priority": 7},
    {"term": "analisis de documentos", "category": "documentologia", "priority": 7},
    {"term": "microscopio forense", "category": "equipamiento", "priority": 7},
    {"term": "kit forense", "category": "equipamiento", "priority": 8},
    {"term": "luminol", "category": "reactivos", "priority": 6},
    {"term": "dactiloscopía", "category": "especialidad", "priority": 7},
    {"term": "dactiloscopia", "category": "especialidad", "priority": 7},
    {"term": "huellas digitales", "category": "especialidad", "priority": 6},
    {"term": "toxicologia", "category": "especialidad", "priority": 7},
    {"term": "medicina legal", "category": "especialidad", "priority": 7},
]


async def seed_initial_data():
    """
    Inserta datos iniciales solo si la DB está vacía.
    Idempotente: no duplica datos.
    """
    async with get_db_context() as db:
        # Verificar si ya hay datos
        kw_count = (await db.execute(select(Keyword).limit(1))).scalar_one_or_none()
        portal_count = (await db.execute(select(Portal).limit(1))).scalar_one_or_none()

        if not kw_count:
            logger.info("Insertando keywords por defecto...")
            for kw_data in DEFAULT_KEYWORDS:
                db.add(Keyword(**kw_data))
            await db.flush()
            logger.info(f"{len(DEFAULT_KEYWORDS)} keywords insertadas")

        if not portal_count:
            logger.info("Insertando portales por defecto...")
            portals = _load_portals_from_registry()
            for p in portals:
                db.add(p)
            await db.flush()
            logger.info(f"{len(portals)} portales insertados")


def _load_portals_from_registry() -> list[Portal]:
    """Carga portales del JSON de registry."""
    if not PORTALS_REGISTRY.exists():
        logger.warning(f"Registry no encontrado: {PORTALS_REGISTRY}")
        return _default_portals()

    try:
        with open(PORTALS_REGISTRY, encoding="utf-8") as f:
            data = json.load(f)
        portals = []
        for p in data.get("portals", []):
            portals.append(Portal(
                name=p["name"],
                short_name=p["short_name"],
                url=p["url"],
                level=PortalLevel(p["level"]),
                province=p.get("province"),
                municipality=p.get("municipality"),
                scraper_class=p["scraper_class"],
                scraper_config=p.get("scraper_config"),
                is_enabled=p.get("is_enabled", True),
            ))
        return portals
    except Exception as e:
        logger.error(f"Error cargando registry: {e}")
        return _default_portals()


def _default_portals() -> list[Portal]:
    """Portales hardcoded como fallback."""
    return [
        Portal(
            name="Argentina Compra (COMPR.AR)",
            short_name="comprar",
            url="https://www.argentinacompra.gob.ar",
            level=PortalLevel.NACIONAL,
            scraper_class="ComprarScraper",
            is_enabled=True,
        ),
        Portal(
            name="Boletín Oficial de la República Argentina",
            short_name="boletin-nacional",
            url="https://www.boletinoficial.gob.ar",
            level=PortalLevel.NACIONAL,
            scraper_class="BoletinNacionalScraper",
            is_enabled=True,
        ),
        Portal(
            name="Portal Buenos Aires Compra (PBAC)",
            short_name="pbac",
            url="https://pbac.cgpba.gob.ar",
            level=PortalLevel.PROVINCIAL,
            province="Buenos Aires",
            scraper_class="PortalComprasPBAScraper",
            is_enabled=True,
        ),
        Portal(
            name="Boletín Oficial Provincia de Buenos Aires",
            short_name="boletin-pba",
            url="https://www.boletinoficial.gba.gov.ar",
            level=PortalLevel.PROVINCIAL,
            province="Buenos Aires",
            scraper_class="BoletinOficialPBAScraper",
            is_enabled=True,
        ),
    ]
