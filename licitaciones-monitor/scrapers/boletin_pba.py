"""
Scraper para el Boletín Oficial de la Provincia de Buenos Aires.
URL: https://www.boletinoficial.gba.gov.ar/

Publica licitaciones y contrataciones de la Provincia de Buenos Aires.
"""
import logging
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from .base import BaseScraper, LicitacionData

logger = logging.getLogger(__name__)


class BoletinOficialPBAScraper(BaseScraper):
    """
    Scraper del Boletín Oficial de la Provincia de Buenos Aires (BOPBA).
    """

    BASE_URL = "https://www.boletinoficial.gba.gov.ar"

    def __init__(self, base_url: str = "https://www.boletinoficial.gba.gov.ar", config: dict | None = None):
        super().__init__(base_url, config)

    async def _fetch_licitaciones(
        self,
        keywords: list[str],
        date_from: Optional[datetime],
        client: httpx.AsyncClient,
    ) -> list[LicitacionData]:
        all_results: list[LicitacionData] = []

        for keyword in keywords:
            self.logger.info(f"BOPBA: buscando '{keyword}'")
            try:
                results = await self._buscar(keyword, date_from, client)
                all_results.extend(results)
            except Exception as e:
                self.logger.warning(f"Error en BOPBA buscando '{keyword}': {e}")
            await self._delay()

        return all_results

    async def _buscar(
        self,
        keyword: str,
        date_from: Optional[datetime],
        client: httpx.AsyncClient,
    ) -> list[LicitacionData]:
        results = []

        # Intentar buscador web del BOPBA
        try:
            url = f"{self.BASE_URL}/buscar"
            params = {
                "q": keyword,
                "seccion": "licitaciones",
            }
            if date_from:
                params["desde"] = date_from.strftime("%Y-%m-%d")

            resp = await client.get(url, params=params, timeout=20)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")
            results = self._parse_html(soup, keyword)

        except Exception as e:
            self.logger.debug(f"Buscador BOPBA falló, intentando alternativa: {e}")
            results = await self._try_alternative(keyword, date_from, client)

        return results

    async def _try_alternative(
        self,
        keyword: str,
        date_from: Optional[datetime],
        client: httpx.AsyncClient,
    ) -> list[LicitacionData]:
        """Intenta URL alternativa del BOPBA."""
        try:
            url = f"{self.BASE_URL}/"
            params = {"busqueda": keyword, "tipo": "licitacion"}
            resp = await client.get(url, params=params, timeout=20)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")
            return self._parse_html(soup, keyword)
        except Exception:
            return []

    def _parse_html(self, soup: BeautifulSoup, keyword: str) -> list[LicitacionData]:
        results = []

        rows = (
            soup.select(".aviso-item")
            or soup.select("article.licitacion")
            or soup.select(".resultado-busqueda")
            or soup.select("table tbody tr")
        )

        for row in rows:
            try:
                titulo_el = (
                    row.select_one("h2 a")
                    or row.select_one("h3 a")
                    or row.select_one(".titulo a")
                    or row.select_one("a")
                )
                if not titulo_el:
                    continue

                titulo = titulo_el.get_text(strip=True)
                href = titulo_el.get("href", "")
                url = urljoin(self.BASE_URL, href) if href else self.BASE_URL

                organismo_el = row.select_one(".organismo") or row.select_one(".reparticion")
                fecha_el = row.select_one(".fecha") or row.select_one("time")
                fecha_texto = (
                    fecha_el.get("datetime")
                    if fecha_el and fecha_el.get("datetime")
                    else self._safe_text(fecha_el)
                )

                lic = LicitacionData(
                    titulo=titulo,
                    portal_short_name="boletin-pba",
                    url_detalle=url,
                    organismo=self._safe_text(organismo_el),
                    fecha_publicacion=self._parse_fecha(fecha_texto),
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
