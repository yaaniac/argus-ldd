"""
Configuración y sesión de base de datos asíncrona.
Soporta SQLite (desarrollo) y PostgreSQL (producción).
"""
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import text

from config import settings
from .models import Base


# Motor asíncrono — SQLite con WAL para mejor concurrencia local
_connect_args = {}
if settings.is_sqlite:
    _connect_args = {"timeout": 30}  # Esperar hasta 30s si la DB está bloqueada

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    future=True,
    connect_args=_connect_args,
    # SQLite: una conexión a la vez para evitar locking
    pool_size=1 if settings.is_sqlite else 5,
    max_overflow=0 if settings.is_sqlite else 10,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def init_db() -> None:
    """Crea tablas y activa WAL mode en SQLite para mejor rendimiento."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # WAL mode permite lecturas concurrentes mientras se escribe
        if settings.is_sqlite:
            await conn.execute(text("PRAGMA journal_mode=WAL"))
            await conn.execute(text("PRAGMA synchronous=NORMAL"))
            await conn.execute(text("PRAGMA busy_timeout=30000"))


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency de FastAPI para obtener sesión de DB."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """Context manager para usar fuera de FastAPI (scheduler, CLI)."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
