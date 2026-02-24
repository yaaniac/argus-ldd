"""
Scraper para el Boletín Oficial de la República Argentina.
URL: https://www.boletinoficial.gob.ar/

Secciones relevantes:
- Sección Primera: Decretos, Decisiones, Resoluciones (licitaciones por norma)
- Sección Tercera: Avisos Oficiales (llamados a licitación directa)

Estrategia:
1. Usar la API pública del Boletín Oficial.
2. Filtrar por sección relevante y palabras clave.
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from .base import BaseScraper, LicitacionData

logger = logging.getLogger(__name__)


class BoletinNacionalScraper(BaseScraper):
    """
    Scraper del Boletín Oficial Nacional (BORA).

    El BORA tiene una API pública JSON y también RSS por sección.
    Sección 3 (Avisos Oficiales) contiene los llamados a licitación.
    Sección 1 (Normativa) puede contener resoluciones de licitaciones.
    """

    BASE_URL = "https://www.boletinoficial.gob.ar"
    API_BASE = "https://www.boletinoficial.gob.ar/api/v2"

    # Secciones del Boletín Oficial
    # 1: Primera (Decretos), 2: Segunda (Sociedades), 3: Tercera (Avisos/Licitaciones)
    SECCION_AVISOS = 3
    SECCION_NORMAS = 1

    def __init__(self, base_url: str = "https://www.boletinoficial.gob.ar", config: dict | None = None):
        super().__init__(base_url, config)

    async def _fetch_licitaciones(
        self,
        keywords: list[str],
        date_from: Optional[datetime],
        client: httpx.AsyncClient,
    ) -> list[LicitacionData]:
        results: list[LicitacionData] = []

        # Buscar en sección de avisos (contiene licitaciones)
        avisos = await self._search_section(
            keywords, date_from, self.SECCION_AVISOS, client
        )
        results.extend(avisos)

        await self._delay()

        # Buscar en sección normativa (resoluciones sobre licitaciones)
        normas = await self._search_section(
            keywords, date_from, self.SECCION_NORMAS, client
        )
        results.extend(normas)

        return results

    async def _search_section(
        self,
        keywords: list[str],
        date_from: Optional[datetime],
        seccion: int,
        client: httpx.AsyncClient,
    ) -> list[LicitacionData]:
        results = []

        for keyword in keywords:
            try:
                items = await self._buscar_api(keyword, date_from, seccion, client)
                if not items:
                    items = await self._buscar_web(keyword, date_from, seccion, client)
                results.extend(items)
                await self._delay(1)
            except Exception as e:
                self.logger.warning(f"Error buscando '{keyword}' en sección {seccion}: {e}")

        return results

    async def _buscar_api(
        self,
        keyword: str,
        date_from: Optional[datetime],
        seccion: int,
        client: httpx.AsyncClient,
    ) -> list[LicitacionData]:
        """
        API pública del Boletín Oficial.
        Endpoint: /api/v2/busqueda/buscador
        """
        try:
            params = {
                "terminos": keyword,
                "seccion": seccion,
                "pagina": 1,
                "norma": "",
                "organismo": "",
            }
            if date_from:
                params["fechaDesde"] = date_from.strftime("%d/%m/%Y")
                params["fechaHasta"] = datetime.now().strftime("%d/%m/%Y")

            url = f"{self.API_BASE}/busqueda/buscador"
            resp = await client.get(url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            return self._parse_api_results(data, keyword, seccion)

        except (httpx.HTTPError, ValueError, KeyError) as e:
            self.logger.debug(f"API BORA no disponible: {e}")
            return []

    def _parse_api_results(
        self, data: dict, keyword: str, seccion: int
    ) -> list[LicitacionData]:
        results = []

        # La API puede devolver distintas estructuras
        items = (
            data.get("publicaciones")
            or data.get("data", {}).get("publicaciones")
            or data.get("items")
            or []
        )

        seccion_nombre = {
            1: "Primera (Normativa)",
            2: "Segunda (Sociedades)",
            3: "Tercera (Avisos)"
        }.get(seccion, str(seccion))

        for item in items:
            try:
                nro_norma = item.get("nroNorma") or item.get("numero") or ""
                fecha_pub = self._parse_fecha(
                    item.get("fechaPublicacion") or item.get("fecha")
                )
                url_detalle = (
                    f"{self.BASE_URL}/#!DetalleNorma/"
                    f"{item.get('seccionCodigo', seccion)}/"
                    f"{nro_norma}"
                )

                titulo = (
                    item.get("titulo")
                    or item.get("descripcion")
                    or item.get("objeto")
                    or f"Aviso Boletín Oficial - {seccion_nombre}"
                )
                organismo = (
                    item.get("organismo")
                    or item.get("emisor")
                    or item.get("dependencia")
                )

                lic = LicitacionData(
                    titulo=titulo,
                    portal_short_name="boletin-nacional",
                    url_detalle=url_detalle,
                    external_id=str(item.get("idNorma") or item.get("id") or nro_norma),
                    organismo=organismo,
                    numero_expediente=item.get("expediente"),
                    fecha_publicacion=fecha_pub,
                    matched_keywords=[keyword],
                    raw_data={**item, "_seccion": seccion_nombre},
                )
                results.append(lic)
            except Exception as e:
                self.logger.debug(f"Error parseando item BORA: {e}")
                continue

        return results

    async def _buscar_web(
        self,
        keyword: str,
        date_from: Optional[datetime],
        seccion: int,
        client: httpx.AsyncClient,
    ) -> list[LicitacionData]:
        """
        Fallback: scraping del buscador web del Boletín Oficial.
        """
        results = []
        try:
            # El buscador web del BORA acepta parámetros en la URL
            url = f"{self.BASE_URL}/buscador"
            params = {
                "q": keyword,
                "seccion": seccion,
            }
            if date_from:
                params["fechaDesde"] = date_from.strftime("%d%m%Y")

            resp = await client.get(url, params=params, timeout=20)
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "lxml")
            results = self._parse_web_html(soup, keyword)

        except Exception as e:
            self.logger.debug(f"Fallback web BORA falló: {e}")

        return results

    def _parse_web_html(self, soup: BeautifulSoup, keyword: str) -> list[LicitacionData]:
        results = []

        # Intentar diferentes selectores CSS que puede tener el portal
        rows = (
            soup.select(".norma-item")
            or soup.select("article.resultado")
            or soup.select("tr.resultado-norma")
            or soup.select(".search-result")
        )

        for row in rows:
            try:
                titulo_el = (
                    row.select_one("h3 a")
                    or row.select_one(".titulo-norma a")
                    or row.select_one("a.norma-link")
                )
                if not titulo_el:
                    continue

                titulo = titulo_el.get_text(strip=True)
                href = titulo_el.get("href", "")
                url = urljoin(self.BASE_URL, href) if href else self.BASE_URL

                organismo_el = row.select_one(".organismo") or row.select_one(".emisor")
                fecha_el = row.select_one(".fecha") or row.select_one("time")
                fecha_texto = fecha_el.get("datetime") if fecha_el else self._safe_text(fecha_el)

                lic = LicitacionData(
                    titulo=titulo,
                    portal_short_name="boletin-nacional",
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
