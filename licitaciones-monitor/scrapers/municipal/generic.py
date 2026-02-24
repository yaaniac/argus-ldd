"""
Scraper genérico para portales municipales de la Provincia de Buenos Aires.

Estrategia multi-fase:
1. Detectar automáticamente el tipo de portal (CMS, tabla HTML, API)
2. Buscar sección de licitaciones / compras
3. Extraer datos normalizados

Municipios soportados con configuración específica:
- La Plata: https://www.laplata.gov.ar/
- Mar del Plata: https://www.mardelplata.gob.ar/
- Bahía Blanca: https://www.bahia-blanca.gov.ar/
- San Isidro: https://www.sanisidro.gob.ar/
- Quilmes: https://www.quilmes.gov.ar/
- Tigre: https://www.tigre.gov.ar/
- Lanús: https://www.lanus.gob.ar/
- Lomas de Zamora: https://www.lomasdezamora.gov.ar/
"""
import logging
import re
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from scrapers.base import BaseScraper, LicitacionData

logger = logging.getLogger(__name__)


# Configuraciones específicas por municipio (paths de licitaciones, selectores, etc.)
MUNICIPAL_CONFIGS = {
    "la-plata": {
        "base_url": "https://www.laplata.gov.ar",
        "licitaciones_paths": [
            "/licitaciones",
            "/compras-y-contrataciones",
            "/transparencia/licitaciones",
        ],
        "search_params": {"buscar": "{keyword}", "seccion": "licitaciones"},
    },
    "mar-del-plata": {
        "base_url": "https://www.mardelplata.gob.ar",
        "licitaciones_paths": [
            "/licitaciones",
            "/compras",
            "/hacienda/licitaciones",
        ],
        "search_params": {"q": "{keyword}"},
    },
    "bahia-blanca": {
        "base_url": "https://www.bahia-blanca.gov.ar",
        "licitaciones_paths": [
            "/gobierno/licitaciones",
            "/licitaciones",
            "/compras",
        ],
        "search_params": {"busqueda": "{keyword}"},
    },
    "san-isidro": {
        "base_url": "https://www.sanisidro.gob.ar",
        "licitaciones_paths": [
            "/licitaciones",
            "/compras-y-contrataciones",
            "/gobierno/licitaciones",
        ],
        "search_params": {"q": "{keyword}"},
    },
    "quilmes": {
        "base_url": "https://www.quilmes.gov.ar",
        "licitaciones_paths": ["/licitaciones", "/compras"],
        "search_params": {"buscar": "{keyword}"},
    },
    "tigre": {
        "base_url": "https://www.tigre.gov.ar",
        "licitaciones_paths": ["/licitaciones", "/compras-licitaciones"],
        "search_params": {"q": "{keyword}"},
    },
}


class GenericMunicipalScraper(BaseScraper):
    """
    Scraper genérico para portales municipales.

    Adaptable a cualquier municipio de la Provincia de Buenos Aires.
    Usa configuración dinámica para detectar la estructura del portal.
    """

    def __init__(self, base_url: str, config: dict | None = None):
        super().__init__(base_url, config)
        self.municipality_key = config.get("municipality_key", "")
        self.known_config = MUNICIPAL_CONFIGS.get(self.municipality_key, {})
        self.portal_short_name = config.get("short_name", "municipal")

    async def _fetch_licitaciones(
        self,
        keywords: list[str],
        date_from: Optional[datetime],
        client: httpx.AsyncClient,
    ) -> list[LicitacionData]:
        all_results: list[LicitacionData] = []

        # Fase 1: Encontrar la sección de licitaciones del portal
        licitaciones_url = await self._find_licitaciones_url(client)

        if not licitaciones_url:
            self.logger.warning(f"No se encontró sección de licitaciones en {self.base_url}")
            return []

        # Fase 2: Buscar por cada keyword
        for keyword in keywords:
            self.logger.info(f"Municipal {self.base_url}: buscando '{keyword}'")
            try:
                results = await self._search_in_portal(
                    licitaciones_url, keyword, date_from, client
                )
                all_results.extend(results)
            except Exception as e:
                self.logger.warning(f"Error buscando '{keyword}': {e}")
            await self._delay()

        return all_results

    async def _find_licitaciones_url(self, client: httpx.AsyncClient) -> Optional[str]:
        """
        Auto-detecta la URL de licitaciones del portal municipal.
        Estrategias:
        1. Usar paths conocidos de la configuración
        2. Parsear el menú de navegación
        3. Buscar links con palabras clave en la página principal
        """
        # 1. Usar configuración conocida
        for path in self.known_config.get("licitaciones_paths", []):
            url = urljoin(self.base_url, path)
            try:
                resp = await client.get(url, timeout=10)
                if resp.status_code == 200:
                    self.logger.info(f"Sección licitaciones encontrada: {url}")
                    return url
            except Exception:
                continue

        # 2. Parsear menú de la página principal
        try:
            resp = await client.get(self.base_url, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")
            url = self._find_licitaciones_link(soup)
            if url:
                return urljoin(self.base_url, url)
        except Exception as e:
            self.logger.debug(f"Error parseando página principal: {e}")

        return None

    def _find_licitaciones_link(self, soup: BeautifulSoup) -> Optional[str]:
        """
        Busca links que contengan palabras clave relacionadas a licitaciones.
        """
        keywords_to_find = [
            "licitaci", "compras", "contratacion", "contratación",
            "adquisicion", "adquisición", "proveedores"
        ]

        # Buscar en navegación principal
        nav_links = (
            soup.select("nav a")
            + soup.select("header a")
            + soup.select(".menu a")
            + soup.select("#menu a")
            + soup.select(".navbar a")
        )

        for link in nav_links:
            href = link.get("href", "")
            text = link.get_text(strip=True).lower()
            href_lower = href.lower()

            for kw in keywords_to_find:
                if kw in text or kw in href_lower:
                    return href

        # Buscar en cualquier link de la página
        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            text = link.get_text(strip=True).lower()
            for kw in keywords_to_find:
                if kw in href.lower() or kw in text:
                    return href

        return None

    async def _search_in_portal(
        self,
        licitaciones_url: str,
        keyword: str,
        date_from: Optional[datetime],
        client: httpx.AsyncClient,
    ) -> list[LicitacionData]:
        """
        Busca keyword en la sección de licitaciones detectada.
        """
        results = []

        # Construir params de búsqueda
        params = self._build_search_params(keyword)

        try:
            resp = await client.get(licitaciones_url, params=params, timeout=20)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            # Verificar si la búsqueda fue exitosa (hay resultados relacionados)
            results = self._extract_licitaciones(soup, keyword, licitaciones_url)

            # Si no hay resultados con búsqueda, tomar todos los items de la página
            # y filtrar por keyword manualmente
            if not results:
                all_items = self._extract_all_items(soup, licitaciones_url)
                results = self._filter_by_keyword(all_items, keyword)

        except Exception as e:
            self.logger.warning(f"Error en búsqueda {licitaciones_url}: {e}")

        return results

    def _build_search_params(self, keyword: str) -> dict:
        """Construye los parámetros de búsqueda según el portal."""
        template_params = self.known_config.get("search_params", {"q": "{keyword}"})
        params = {}
        for k, v in template_params.items():
            params[k] = v.replace("{keyword}", keyword) if isinstance(v, str) else v
        return params

    def _extract_licitaciones(
        self,
        soup: BeautifulSoup,
        keyword: str,
        base_url: str,
    ) -> list[LicitacionData]:
        """
        Extrae licitaciones del HTML usando selectores CSS comunes.
        Funciona con la mayoría de CMSs argentinos.
        """
        results = []

        # Selectores comunes en portales municipales argentinos
        containers = (
            soup.select("table tbody tr")
            or soup.select(".licitacion-item")
            or soup.select("article.licitacion")
            or soup.select(".resultado-item")
            or soup.select(".compra-item")
            or soup.select("ul.licitaciones li")
            or soup.select(".field-items .field-item")
        )

        for item in containers:
            try:
                lic = self._parse_item(item, keyword, base_url)
                if lic and self._is_relevant(lic, keyword):
                    results.append(lic)
            except Exception:
                continue

        return results

    def _extract_all_items(self, soup: BeautifulSoup, base_url: str) -> list[LicitacionData]:
        """Extrae todos los items de la página sin filtro de keyword."""
        results = []
        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            text = link.get_text(strip=True)
            if not text or len(text) < 10:
                continue
            # Filtrar solo links que parezcan licitaciones
            if any(kw in href.lower() or kw in text.lower()
                   for kw in ["licit", "exped", "contrat", "compra"]):
                full_url = urljoin(base_url, href)
                lic = LicitacionData(
                    titulo=text,
                    portal_short_name=self.portal_short_name,
                    url_detalle=full_url,
                    matched_keywords=[],
                    raw_data={"source": "link_extraction"},
                )
                results.append(lic)
        return results

    def _parse_item(
        self,
        item,
        keyword: str,
        base_url: str,
    ) -> Optional[LicitacionData]:
        """Parsea un item individual."""
        titulo_el = (
            item.select_one("a")
            or item.select_one("td:first-child")
            or item.select_one(".titulo")
            or item.select_one("h3")
            or item.select_one("h2")
        )
        if not titulo_el:
            return None

        titulo = titulo_el.get_text(strip=True)
        if not titulo or len(titulo) < 5:
            return None

        href = titulo_el.get("href") if titulo_el.name == "a" else (
            titulo_el.select_one("a") and titulo_el.select_one("a").get("href")
        )
        url = urljoin(base_url, href) if href else base_url

        # Buscar fecha
        fecha_el = item.select_one(".fecha") or item.select_one("td:nth-child(2)")
        # Buscar organismo
        org_el = item.select_one(".organismo") or item.select_one("td:nth-child(3)")

        return LicitacionData(
            titulo=titulo,
            portal_short_name=self.portal_short_name,
            url_detalle=url,
            organismo=self._safe_text(org_el),
            fecha_publicacion=self._parse_fecha(self._safe_text(fecha_el)),
            matched_keywords=[keyword],
            raw_data={"source": "html_parsing"},
        )

    @staticmethod
    def _is_relevant(lic: LicitacionData, keyword: str) -> bool:
        """Verifica que la licitación es relevante para la keyword."""
        keyword_lower = keyword.lower()
        titulo_lower = (lic.titulo or "").lower()
        desc_lower = (lic.descripcion or "").lower()
        return keyword_lower in titulo_lower or keyword_lower in desc_lower

    @staticmethod
    def _filter_by_keyword(
        items: list[LicitacionData],
        keyword: str,
    ) -> list[LicitacionData]:
        """Filtra items por keyword en título/descripción."""
        keyword_lower = keyword.lower()
        return [
            item for item in items
            if (keyword_lower in (item.titulo or "").lower()
                or keyword_lower in (item.descripcion or "").lower())
        ]

    @staticmethod
    def _parse_fecha(texto: Optional[str]) -> Optional[datetime]:
        if not texto:
            return None
        from dateparser import parse
        try:
            return parse(texto, languages=["es"], settings={"DATE_ORDER": "DMY"})
        except Exception:
            return None
