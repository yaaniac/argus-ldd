"""
Clase base abstracta para todos los scrapers.
Define el contrato que cada portal debe implementar.
"""
import asyncio
import hashlib
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from config import settings

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Data Transfer Object
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class LicitacionData:
    """
    Estructura normalizada de una licitación extraída de cualquier portal.
    Independiente de la fuente.
    """
    titulo: str
    portal_short_name: str
    url_detalle: str

    # Opcionales — se rellenan si el portal los provee
    external_id: Optional[str] = None
    descripcion: Optional[str] = None
    numero_expediente: Optional[str] = None
    numero_licitacion: Optional[str] = None
    organismo: Optional[str] = None
    tipo_contratacion: Optional[str] = None

    monto_estimado: Optional[float] = None
    moneda: Optional[str] = "ARS"

    fecha_publicacion: Optional[datetime] = None
    fecha_apertura: Optional[datetime] = None
    fecha_cierre: Optional[datetime] = None

    url_pliego: Optional[str] = None

    matched_keywords: list[str] = field(default_factory=list)
    raw_data: dict = field(default_factory=dict)

    def compute_hash(self) -> str:
        """
        SHA-256 sobre campos clave para deduplicación robusta.
        Ignora fechas de actualización para no generar falsos duplicados.
        """
        key_parts = [
            self.titulo.strip().lower(),
            (self.external_id or "").strip(),
            (self.numero_licitacion or "").strip(),
            (self.organismo or "").strip(),
            self.portal_short_name,
        ]
        raw = "|".join(key_parts)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict:
        d = asdict(self)
        # Convertir datetimes a ISO para serialización
        for k, v in d.items():
            if isinstance(v, datetime):
                d[k] = v.isoformat()
        return d


# ─────────────────────────────────────────────────────────────────────────────
# Base Scraper
# ─────────────────────────────────────────────────────────────────────────────

class BaseScraper(ABC):
    """
    Contrato base para todos los scrapers de portales.

    Cada subclase implementa `_fetch_licitaciones` con la lógica específica
    del portal. El método público `search` agrega reintentos, delays y
    manejo de errores de forma uniforme.
    """

    # Headers comunes para simular browser
    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
    }

    def __init__(self, base_url: str, config: dict | None = None):
        self.base_url = base_url.rstrip("/")
        self.config = config or {}
        self.logger = logging.getLogger(self.__class__.__name__)

    @abstractmethod
    async def _fetch_licitaciones(
        self,
        keywords: list[str],
        date_from: Optional[datetime],
        client: httpx.AsyncClient,
    ) -> list[LicitacionData]:
        """
        Implementación específica del portal.
        Recibe el cliente HTTP ya configurado.
        """
        ...

    async def search(
        self,
        keywords: list[str],
        date_from: Optional[datetime] = None,
    ) -> list[LicitacionData]:
        """
        Punto de entrada público. Gestiona cliente HTTP, delays y errores.
        """
        headers = {**self.DEFAULT_HEADERS, **self.config.get("extra_headers", {})}

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(settings.API_TIMEOUT),
            headers=headers,
            follow_redirects=True,
            verify=False,  # Algunos portales municipales tienen certs vencidos
        ) as client:
            try:
                results = await self._fetch_licitaciones(keywords, date_from, client)
                self.logger.info(
                    f"[{self.__class__.__name__}] {len(results)} licitaciones encontradas"
                )
                return results
            except httpx.TimeoutException as e:
                self.logger.warning(f"[{self.__class__.__name__}] Timeout: {e}")
                raise
            except httpx.HTTPStatusError as e:
                self.logger.warning(
                    f"[{self.__class__.__name__}] HTTP {e.response.status_code}: {e.request.url}"
                )
                raise
            except Exception as e:
                self.logger.error(f"[{self.__class__.__name__}] Error inesperado: {e}", exc_info=True)
                raise

    @staticmethod
    def _safe_text(element) -> Optional[str]:
        """Extrae texto de un elemento BeautifulSoup de forma segura."""
        if element is None:
            return None
        return element.get_text(strip=True) or None

    @staticmethod
    def _delay(seconds: float | None = None):
        """Delay configurable entre requests."""
        return asyncio.sleep(seconds or settings.REQUEST_DELAY_SECONDS)
