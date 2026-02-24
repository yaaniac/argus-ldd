"""
Registro de scrapers disponibles.
Cada scraper se identifica por su `scraper_class` en la tabla portals.
"""
from .base import BaseScraper, LicitacionData
from .comprar import ComprarScraper
from .boletin_nacional import BoletinNacionalScraper
from .portal_compras_pba import PortalComprasPBAScraper
from .boletin_pba import BoletinOficialPBAScraper
from .municipal.generic import GenericMunicipalScraper

# Registro: scraper_class -> clase Python
SCRAPER_REGISTRY: dict[str, type[BaseScraper]] = {
    "ComprarScraper": ComprarScraper,
    "BoletinNacionalScraper": BoletinNacionalScraper,
    "PortalComprasPBAScraper": PortalComprasPBAScraper,
    "BoletinOficialPBAScraper": BoletinOficialPBAScraper,
    "GenericMunicipalScraper": GenericMunicipalScraper,
}


def get_scraper(scraper_class: str, portal_url: str, config: dict | None = None) -> BaseScraper:
    """
    Instancia el scraper correcto según el nombre de clase registrado.
    Lanza KeyError si el scraper no existe.
    """
    cls = SCRAPER_REGISTRY.get(scraper_class)
    if cls is None:
        raise KeyError(
            f"Scraper '{scraper_class}' no registrado. "
            f"Opciones disponibles: {list(SCRAPER_REGISTRY.keys())}"
        )
    return cls(base_url=portal_url, config=config or {})


__all__ = [
    "BaseScraper",
    "LicitacionData",
    "ComprarScraper",
    "BoletinNacionalScraper",
    "PortalComprasPBAScraper",
    "BoletinOficialPBAScraper",
    "GenericMunicipalScraper",
    "SCRAPER_REGISTRY",
    "get_scraper",
]
