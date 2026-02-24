"""
Modelos SQLAlchemy para LicitaForense Monitor.
Diseñados para crecer hacia un SaaS multi-tenant.
"""
import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, ForeignKey,
    Integer, JSON, String, Text, UniqueConstraint, Float
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


# ─────────────────────────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────────────────────────

class PortalLevel(str, enum.Enum):
    NACIONAL = "nacional"
    PROVINCIAL = "provincial"
    MUNICIPAL = "municipal"


class PortalStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"


class RunStatus(str, enum.Enum):
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class LicitacionStatus(str, enum.Enum):
    NUEVA = "nueva"
    VISTA = "vista"
    DESCARTADA = "descartada"
    FAVORITA = "favorita"


# ─────────────────────────────────────────────────────────────────────────────
# Portal
# ─────────────────────────────────────────────────────────────────────────────

class Portal(Base):
    """
    Repositorio de portales de licitaciones.
    Cada portal tiene su scraper asociado por `scraper_class`.
    """
    __tablename__ = "portals"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    short_name = Column(String(50), nullable=False, unique=True)
    url = Column(String(500), nullable=False)
    level = Column(Enum(PortalLevel), nullable=False)
    province = Column(String(100), nullable=True)   # Para portales provinciales/municipales
    municipality = Column(String(100), nullable=True)

    scraper_class = Column(String(100), nullable=False)  # Nombre de la clase scraper
    scraper_config = Column(JSON, nullable=True)          # Config extra para el scraper

    status = Column(Enum(PortalStatus), default=PortalStatus.ACTIVE)
    is_enabled = Column(Boolean, default=True)

    last_checked_at = Column(DateTime, nullable=True)
    last_success_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)
    consecutive_errors = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relations
    licitaciones = relationship("Licitacion", back_populates="portal")
    run_portals = relationship("SearchRunPortal", back_populates="portal")

    def __repr__(self):
        return f"<Portal {self.short_name} ({self.level.value})>"


# ─────────────────────────────────────────────────────────────────────────────
# Keyword
# ─────────────────────────────────────────────────────────────────────────────

class Keyword(Base):
    """
    Palabras clave de búsqueda.
    Soporta operadores lógicos y agrupación.
    """
    __tablename__ = "keywords"

    id = Column(Integer, primary_key=True, index=True)
    term = Column(String(200), nullable=False, unique=True)
    category = Column(String(100), nullable=True)  # p.ej. "forense", "laboratorio"
    is_active = Column(Boolean, default=True)
    priority = Column(Integer, default=5)  # 1-10, mayor = más importante

    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Keyword '{self.term}'>"


# ─────────────────────────────────────────────────────────────────────────────
# Licitacion
# ─────────────────────────────────────────────────────────────────────────────

class Licitacion(Base):
    """
    Licitación / Contratación pública detectada.
    Tabla principal del sistema.
    """
    __tablename__ = "licitaciones"

    id = Column(Integer, primary_key=True, index=True)
    portal_id = Column(Integer, ForeignKey("portals.id"), nullable=False)

    # Identificación única (evita duplicados)
    external_id = Column(String(300), nullable=True)  # ID en el portal origen
    content_hash = Column(String(64), nullable=False)  # SHA256 del contenido normalizado

    # Datos principales
    titulo = Column(String(1000), nullable=False)
    descripcion = Column(Text, nullable=True)
    numero_expediente = Column(String(200), nullable=True)
    numero_licitacion = Column(String(200), nullable=True)
    organismo = Column(String(500), nullable=True)
    tipo_contratacion = Column(String(200), nullable=True)  # "licitación pública", "concurso de precios", etc.

    # Montos
    monto_estimado = Column(Float, nullable=True)
    moneda = Column(String(10), nullable=True)

    # Fechas
    fecha_publicacion = Column(DateTime, nullable=True)
    fecha_apertura = Column(DateTime, nullable=True)
    fecha_cierre = Column(DateTime, nullable=True)

    # URLs
    url_detalle = Column(String(1000), nullable=True)
    url_pliego = Column(String(1000), nullable=True)

    # Datos de matcheo
    matched_keywords = Column(JSON, nullable=True)  # Lista de keywords que matchearon
    relevance_score = Column(Float, default=0.0)    # Score de relevancia calculado

    # Estado
    status = Column(Enum(LicitacionStatus), default=LicitacionStatus.NUEVA)
    is_new = Column(Boolean, default=True)  # True hasta que sea vista

    # Metadata
    raw_data = Column(JSON, nullable=True)  # Datos originales del portal
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relations
    portal = relationship("Portal", back_populates="licitaciones")

    __table_args__ = (
        UniqueConstraint("portal_id", "content_hash", name="uq_portal_contenthash"),
    )

    def __repr__(self):
        return f"<Licitacion '{self.titulo[:50]}...'>"


# ─────────────────────────────────────────────────────────────────────────────
# SearchRun
# ─────────────────────────────────────────────────────────────────────────────

class SearchRun(Base):
    """
    Historial de ejecuciones de búsqueda.
    Permite auditoría y control de frecuencia.
    """
    __tablename__ = "search_runs"

    id = Column(Integer, primary_key=True, index=True)
    status = Column(Enum(RunStatus), default=RunStatus.RUNNING)
    triggered_by = Column(String(50), default="scheduler")  # "scheduler" | "manual" | "api"

    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, nullable=True)

    portals_scanned = Column(Integer, default=0)
    portals_failed = Column(Integer, default=0)
    licitaciones_found = Column(Integer, default=0)
    licitaciones_new = Column(Integer, default=0)

    keywords_used = Column(JSON, nullable=True)
    error_details = Column(JSON, nullable=True)

    # Relations
    portal_runs = relationship("SearchRunPortal", back_populates="run")

    def __repr__(self):
        return f"<SearchRun #{self.id} {self.status.value}>"


class SearchRunPortal(Base):
    """
    Resultado por portal en cada ejecución.
    """
    __tablename__ = "search_run_portals"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("search_runs.id"), nullable=False)
    portal_id = Column(Integer, ForeignKey("portals.id"), nullable=False)

    status = Column(String(20), default="success")
    licitaciones_found = Column(Integer, default=0)
    licitaciones_new = Column(Integer, default=0)
    duration_seconds = Column(Float, nullable=True)
    error = Column(Text, nullable=True)

    # Relations
    run = relationship("SearchRun", back_populates="portal_runs")
    portal = relationship("Portal", back_populates="run_portals")


# ─────────────────────────────────────────────────────────────────────────────
# Alert
# ─────────────────────────────────────────────────────────────────────────────

class Alert(Base):
    """
    Registro de alertas enviadas.
    """
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    channel = Column(String(50), nullable=False)  # "email", "webhook"
    recipient = Column(String(200), nullable=True)
    subject = Column(String(500), nullable=True)
    body_summary = Column(Text, nullable=True)
    licitaciones_count = Column(Integer, default=0)

    sent_at = Column(DateTime, default=datetime.utcnow)
    success = Column(Boolean, default=True)
    error = Column(Text, nullable=True)
