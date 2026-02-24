"""
Scraper para Argentina Compra (COMPR.AR) — Portal nacional de contrataciones.
URL: https://www.argentinacompra.gob.ar/

Estrategia:
1. Usar la API pública de búsqueda cuando está disponible.
2. Complementar con scraping HTML del buscador web.
"""
import asyncio
import logging
from datetime import datetime
from typing import Optional
from urllib.parse import urlencode, urljoin

import httpx
from bs4 import BeautifulSoup

from .base import BaseScraper, LicitacionData

logger = logging.getLogger(__name__)


class ComprarScraper(BaseScraper):
    """
    Scraper para el portal Argentina Compra (antiguo COMPR.AR).
    Cubre contrataciones del Estado Nacional Argentino.
    """

    # Endpoint de búsqueda del portal
    SEARCH_URL = "https://www.argentinacompra.gob.ar/prod/secc/buscador.php"
    # API de datos abiertos de Argentina Compra
    API_BASE = "https://api.argentinacompra.gob.ar/prod/v2"

    def __init__(self, base_url: str = "https://www.argentinacompra.gob.ar", config: dict | None = None):
        super().__init__(base_url, config)

    async def _fetch_licitaciones(
        self,
        keywords: list[str],
        date_from: Optional[datetime],
        client: httpx.AsyncClient,
    ) -> list[LicitacionData]:
        results: list[LicitacionData] = []

        for keyword in keywords:
            self.logger.info(f"Argentina Compra: buscando '{keyword}'")
            try:
                keyword_results = await self._search_keyword(keyword, date_from, client)
                results.extend(keyword_results)
            except Exception as e:
                self.logger.warning(f"Error buscando '{keyword}': {e}")
            await self._delay()

        return self._dedupe_by_id(results)

    async def _search_keyword(
        self,
        keyword: str,
        date_from: Optional[datetime],
        client: httpx.AsyncClient,
    ) -> list[LicitacionData]:
        """Busca en el portal web de Argentina Compra."""
        results = []

        # Intentar API primero
        api_results = await self._try_api(keyword, date_from, client)
        if api_results:
            results.extend(api_results)
            return results

        # Fallback: scraping HTML
        html_results = await self._scrape_web(keyword, date_from, client)
        results.extend(html_results)
        return results

    async def _try_api(
        self,
        keyword: str,
        date_from: Optional[datetime],
        client: httpx.AsyncClient,
    ) -> list[LicitacionData]:
        """
        Intenta usar la API pública de Argentina Compra.
        El endpoint puede cambiar; está diseñado para fallar silenciosamente.
        """
        try:
            params = {
                "palabrasClave": keyword,
                "estado": "vigente",
                "pagina": 1,
                "cantidadPorPagina": 50,
            }
            if date_from:
                params["fechaDesde"] = date_from.strftime("%d/%m/%Y")

            url = f"{self.API_BASE}/items/publicaciones"
            resp = await client.get(url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            return self._parse_api_response(data, keyword)

        except (httpx.HTTPError, KeyError, ValueError) as e:
            self.logger.debug(f"API no disponible, usando scraping: {e}")
            return []

    def _parse_api_response(self, data: dict, keyword: str) -> list[LicitacionData]:
        """Parsea respuesta de la API de Argentina Compra."""
        results = []
        items = data.get("data", data.get("items", data.get("resultado", [])))

        if not isinstance(items, list):
            return []

        for item in items:
            try:
                # Parsear fecha de publicacion
                fecha_pub = None
                for date_key in ("fechaPublicacion", "fecha_publicacion", "fechaCreacion"):
                    if item.get(date_key):
                        try:
                            fecha_pub = datetime.fromisoformat(
                                item[date_key].replace("Z", "+00:00")
                            )
                        except (ValueError, AttributeError):
                            pass
                        break

                # Parsear monto
                monto = None
                for monto_key in ("montoEstimado", "monto", "presupuesto"):
                    if item.get(monto_key):
                        try:
                            monto = float(str(item[monto_key]).replace(",", "").replace(".", ""))
                        except (ValueError, TypeError):
                            pass
                        break

                external_id = str(item.get("nroExpediente") or item.get("id") or "")
                url_detalle = item.get("url") or item.get("urlDetalle") or ""
                if url_detalle and not url_detalle.startswith("http"):
                    url_detalle = urljoin(self.base_url, url_detalle)

                lic = LicitacionData(
                    titulo=item.get("descripcion") or item.get("titulo") or "Sin título",
                    portal_short_name="comprar",
                    url_detalle=url_detalle or self.base_url,
                    external_id=external_id,
                    organismo=item.get("organismo") or item.get("reparticion"),
                    tipo_contratacion=item.get("tipoContratacion") or item.get("modalidad"),
                    monto_estimado=monto,
                    fecha_publicacion=fecha_pub,
                    matched_keywords=[keyword],
                    raw_data=item,
                )
                results.append(lic)
            except Exception as e:
                self.logger.debug(f"Error parseando item API: {e}")
                continue

        return results

    async def _scrape_web(
        self,
        keyword: str,
        date_from: Optional[datetime],
        client: httpx.AsyncClient,
    ) -> list[LicitacionData]:
        """
        Scraping HTML del buscador web de Argentina Compra.
        URL de búsqueda: https://www.argentinacompra.gob.ar/buscador/?texto=KEYWORD
        """
        results = []

        try:
            # URL del buscador público
            search_url = f"{self.base_url}/buscador/"
            params = {"texto": keyword}
            if date_from:
                params["fechaDesde"] = date_from.strftime("%d/%m/%Y")

            resp = await client.get(search_url, params=params, timeout=20)
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "lxml")
            results = self._parse_search_html(soup, keyword)
            self.logger.info(f"Web scraping: {len(results)} resultados para '{keyword}'")

        except httpx.HTTPStatusError as e:
            self.logger.warning(f"HTTP {e.response.status_code} en scraping web: {e.request.url}")

            # Fallback: buscar en datos.gob.ar CKAN API
            results = await self._try_datos_gob_ar(keyword, date_from, client)

        except Exception as e:
            self.logger.warning(f"Error en scraping web: {e}")
            results = await self._try_datos_gob_ar(keyword, date_from, client)

        return results

    def _parse_search_html(self, soup: BeautifulSoup, keyword: str) -> list[LicitacionData]:
        """
        Parsea el HTML del buscador de Argentina Compra.
        Los selectores CSS son aproximados al diseño conocido del portal.
        """
        results = []

        # Intentar diferentes estructuras de tabla que puede tener el portal
        rows = (
            soup.select("table.resultados tbody tr")
            or soup.select(".resultado-item")
            or soup.select("article.licitacion")
            or soup.select(".search-result-item")
        )

        for row in rows:
            try:
                # Extraer título
                titulo_el = (
                    row.select_one("td.descripcion a")
                    or row.select_one(".titulo a")
                    or row.select_one("h3 a")
                    or row.select_one("a[href*='licitacion']")
                )
                if not titulo_el:
                    continue

                titulo = titulo_el.get_text(strip=True)
                url_rel = titulo_el.get("href", "")
                url_detalle = urljoin(self.base_url, url_rel) if url_rel else self.base_url

                # Organismo
                organismo_el = row.select_one(".organismo") or row.select_one("td.reparticion")
                organismo = self._safe_text(organismo_el)

                # Número de expediente
                nro_el = row.select_one(".nro-expediente") or row.select_one("td.expediente")
                nro = self._safe_text(nro_el)

                # Fecha publicación
                fecha_el = row.select_one(".fecha") or row.select_one("td.fecha")
                fecha = self._parse_fecha(self._safe_text(fecha_el))

                lic = LicitacionData(
                    titulo=titulo,
                    portal_short_name="comprar",
                    url_detalle=url_detalle,
                    numero_expediente=nro,
                    organismo=organismo,
                    fecha_publicacion=fecha,
                    matched_keywords=[keyword],
                    raw_data={"source": "web_scraping"},
                )
                results.append(lic)
            except Exception as e:
                self.logger.debug(f"Error parseando fila HTML: {e}")
                continue

        return results

    async def _try_datos_gob_ar(
        self,
        keyword: str,
        date_from: Optional[datetime],
        client: httpx.AsyncClient,
    ) -> list[LicitacionData]:
        """
        Alternativa usando la API CKAN de datos.gob.ar.
        Portal de datos abiertos del gobierno argentino.
        """
        results = []
        try:
            # CKAN API de datos abiertos
            url = "https://datos.gob.ar/api/3/action/datastore_search"
            params = {
                "resource_id": "a4e54c96-d8a3-4ab2-a153-f05a36ac4f52",  # Licitaciones COMPR.AR
                "q": keyword,
                "limit": 100,
            }
            resp = await client.get(url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            records = data.get("result", {}).get("records", [])
            for record in records:
                try:
                    lic = LicitacionData(
                        titulo=record.get("descripcion") or record.get("objeto") or "Sin título",
                        portal_short_name="comprar",
                        url_detalle=record.get("url") or self.base_url,
                        external_id=str(record.get("nro_expediente") or record.get("_id") or ""),
                        organismo=record.get("organismo") or record.get("unidad_operativa"),
                        tipo_contratacion=record.get("tipo_contratacion"),
                        matched_keywords=[keyword],
                        raw_data=record,
                    )
                    results.append(lic)
                except Exception:
                    continue

        except Exception as e:
            self.logger.debug(f"datos.gob.ar API error: {e}")

        return results

    @staticmethod
    def _parse_fecha(texto: Optional[str]) -> Optional[datetime]:
        """Intenta parsear fechas en formatos comunes argentinos."""
        if not texto:
            return None
        from dateparser import parse
        return parse(texto, languages=["es"], settings={"DATE_ORDER": "DMY"})

    @staticmethod
    def _dedupe_by_id(items: list[LicitacionData]) -> list[LicitacionData]:
        """Elimina duplicados por external_id o hash de título."""
        seen = set()
        unique = []
        for item in items:
            key = item.external_id or item.titulo.strip().lower()
            if key not in seen:
                seen.add(key)
                unique.append(item)
        return unique
