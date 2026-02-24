"""
Scraper para el Portal Buenos Aires Compra (PBAC).
URL: https://pbac.cgpba.gob.ar/

Sistema de contrataciones de la Provincia de Buenos Aires.
Utiliza el sistema PBAC (Portal Buenos Aires Compra) basado en SIGAF.
"""
import logging
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin, urlencode

import httpx
from bs4 import BeautifulSoup

from .base import BaseScraper, LicitacionData

logger = logging.getLogger(__name__)


class PortalComprasPBAScraper(BaseScraper):
    """
    Scraper para el Portal de Compras de la Provincia de Buenos Aires.
    Portal: https://pbac.cgpba.gob.ar/

    El PBAC es el sistema oficial de compras y contrataciones de la PBA.
    Incluye licitaciones públicas, privadas, compras menores, etc.
    """

    BASE_URL = "https://pbac.cgpba.gob.ar"
    SEARCH_PATH = "/compras/search"

    def __init__(self, base_url: str = "https://pbac.cgpba.gob.ar", config: dict | None = None):
        super().__init__(base_url, config)

    async def _fetch_licitaciones(
        self,
        keywords: list[str],
        date_from: Optional[datetime],
        client: httpx.AsyncClient,
    ) -> list[LicitacionData]:
        all_results: list[LicitacionData] = []

        for keyword in keywords:
            self.logger.info(f"PBAC: buscando '{keyword}'")
            try:
                results = await self._buscar_keyword(keyword, date_from, client)
                all_results.extend(results)
            except Exception as e:
                self.logger.warning(f"Error buscando '{keyword}' en PBAC: {e}")
            await self._delay()

        return all_results

    async def _buscar_keyword(
        self,
        keyword: str,
        date_from: Optional[datetime],
        client: httpx.AsyncClient,
    ) -> list[LicitacionData]:
        results = []

        # Intento 1: API pública del PBAC (si existe)
        api_results = await self._try_api(keyword, date_from, client)
        if api_results:
            return api_results

        # Intento 2: Scraping web del portal
        results = await self._scrape_portal(keyword, date_from, client)
        return results

    async def _try_api(
        self,
        keyword: str,
        date_from: Optional[datetime],
        client: httpx.AsyncClient,
    ) -> list[LicitacionData]:
        """
        Intenta la API REST del PBAC si está disponible.
        """
        try:
            params = {
                "q": keyword,
                "estado": "VIGENTE",
                "rows": 50,
                "start": 0,
            }
            if date_from:
                params["fechaDesde"] = date_from.strftime("%Y-%m-%d")

            url = f"{self.BASE_URL}/api/v1/licitaciones/buscar"
            resp = await client.get(url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            return self._parse_api(data, keyword)

        except Exception as e:
            self.logger.debug(f"API PBAC no disponible: {e}")
            return []

    def _parse_api(self, data: dict, keyword: str) -> list[LicitacionData]:
        results = []
        items = data.get("items") or data.get("licitaciones") or data.get("data") or []

        for item in items:
            try:
                url_det = item.get("url") or f"{self.BASE_URL}/licitacion/{item.get('id')}"
                if not url_det.startswith("http"):
                    url_det = urljoin(self.BASE_URL, url_det)

                lic = LicitacionData(
                    titulo=item.get("descripcion") or item.get("objeto") or "Sin título",
                    portal_short_name="pbac",
                    url_detalle=url_det,
                    external_id=str(item.get("nroExpediente") or item.get("id") or ""),
                    organismo=item.get("organismo") or item.get("jurisdiccion"),
                    tipo_contratacion=item.get("modalidad") or item.get("tipo"),
                    numero_licitacion=item.get("nroLicitacion"),
                    fecha_publicacion=self._parse_fecha(item.get("fechaPublicacion")),
                    fecha_apertura=self._parse_fecha(item.get("fechaApertura")),
                    matched_keywords=[keyword],
                    raw_data=item,
                )
                results.append(lic)
            except Exception as e:
                self.logger.debug(f"Error parseando item PBAC API: {e}")
                continue

        return results

    async def _scrape_portal(
        self,
        keyword: str,
        date_from: Optional[datetime],
        client: httpx.AsyncClient,
    ) -> list[LicitacionData]:
        """
        Scraping HTML del portal web PBAC.
        """
        results = []
        try:
            # URL de búsqueda conocida del PBAC
            search_url = f"{self.BASE_URL}/compras/expedientes"
            params = {"palabrasClave": keyword}
            if date_from:
                params["fechaDesde"] = date_from.strftime("%d/%m/%Y")

            resp = await client.get(search_url, params=params, timeout=20)
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "lxml")
            results = self._parse_html(soup, keyword)

            # Si no hay resultados con ese endpoint, probar el buscador general
            if not results:
                results = await self._scrape_buscador(keyword, date_from, client)

        except Exception as e:
            self.logger.warning(f"Scraping PBAC falló: {e}")
            results = await self._scrape_buscador(keyword, date_from, client)

        return results

    async def _scrape_buscador(
        self,
        keyword: str,
        date_from: Optional[datetime],
        client: httpx.AsyncClient,
    ) -> list[LicitacionData]:
        """Buscador alternativo del PBAC."""
        results = []
        try:
            url = f"{self.BASE_URL}/pbac/"
            params = {"busqueda": keyword}
            resp = await client.get(url, params=params, timeout=20)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")
            results = self._parse_html(soup, keyword)
        except Exception as e:
            self.logger.debug(f"Buscador alternativo PBAC falló: {e}")
        return results

    def _parse_html(self, soup: BeautifulSoup, keyword: str) -> list[LicitacionData]:
        results = []

        rows = (
            soup.select("table.licitaciones tbody tr")
            or soup.select(".expediente-item")
            or soup.select("tr.resultado")
            or soup.select(".licitacion-card")
        )

        for row in rows:
            try:
                titulo_el = (
                    row.select_one("td.descripcion a")
                    or row.select_one(".titulo a")
                    or row.select_one("h3 a")
                    or row.select_one("a")
                )
                if not titulo_el:
                    continue

                titulo = titulo_el.get_text(strip=True)
                href = titulo_el.get("href", "")
                url = urljoin(self.BASE_URL, href) if href else self.BASE_URL

                organismo_el = row.select_one(".organismo") or row.select_one("td.organismo")
                nro_el = row.select_one(".nro-expediente") or row.select_one("td.expediente")
                fecha_el = row.select_one(".fecha") or row.select_one("td.fecha")
                apertura_el = row.select_one(".apertura") or row.select_one("td.apertura")
                tipo_el = row.select_one(".tipo") or row.select_one("td.tipo")

                lic = LicitacionData(
                    titulo=titulo,
                    portal_short_name="pbac",
                    url_detalle=url,
                    numero_expediente=self._safe_text(nro_el),
                    organismo=self._safe_text(organismo_el),
                    tipo_contratacion=self._safe_text(tipo_el),
                    fecha_publicacion=self._parse_fecha(self._safe_text(fecha_el)),
                    fecha_apertura=self._parse_fecha(self._safe_text(apertura_el)),
                    matched_keywords=[keyword],
                    raw_data={"source": "web_scraping"},
                )
                results.append(lic)
            except Exception:
                continue

        return results

    @staticmethod
    def _parse_fecha(texto: Optional[str]) -> Optional[datetime]:
        if not texto:
            return None
        from dateparser import parse
        try:
            return parse(texto, languages=["es"], settings={"DATE_ORDER": "DMY"})
        except Exception:
            return None
