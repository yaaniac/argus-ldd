"""
Aplicación FastAPI principal.
Sirve tanto la API REST como el dashboard web.
"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import settings
from database import init_db
from .routes import licitaciones, portales, keywords, runs

logger = logging.getLogger(__name__)

# Rutas de templates y static
BASE_DIR = Path(__file__).parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicialización y teardown de la aplicación."""
    logger.info(f"Iniciando {settings.APP_NAME} v{settings.APP_VERSION}")

    # Inicializar base de datos
    await init_db()
    logger.info("Base de datos inicializada")

    # Seed inicial de datos si la DB está vacía
    from api.seed import seed_initial_data
    await seed_initial_data()

    # Iniciar scheduler
    if settings.SCAN_ON_STARTUP:
        from scheduler.scheduler import start_scheduler
        await start_scheduler()
        logger.info(f"Scheduler iniciado (cada {settings.SCAN_INTERVAL_HOURS}h)")

    yield

    # Cleanup
    from scheduler.scheduler import stop_scheduler
    await stop_scheduler()
    logger.info("Aplicación detenida")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="Sistema de monitoreo de licitaciones públicas especializadas en sector forense",
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
    )

    # Montar archivos estáticos
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # Templates Jinja2
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    # ─── API Routes ───────────────────────────────────────────────────────────
    app.include_router(licitaciones.router)
    app.include_router(portales.router)
    app.include_router(keywords.router)
    app.include_router(runs.router)

    # ─── Dashboard Web ────────────────────────────────────────────────────────

    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request):
        return templates.TemplateResponse("index.html", {"request": request})

    @app.get("/licitaciones", response_class=HTMLResponse)
    async def page_licitaciones(request: Request):
        return templates.TemplateResponse("licitaciones.html", {"request": request})

    @app.get("/licitaciones/{licitacion_id}", response_class=HTMLResponse)
    async def page_detalle(request: Request, licitacion_id: int):
        return templates.TemplateResponse(
            "detalle.html",
            {"request": request, "licitacion_id": licitacion_id}
        )

    @app.get("/portales", response_class=HTMLResponse)
    async def page_portales(request: Request):
        return templates.TemplateResponse("portales.html", {"request": request})

    @app.get("/keywords", response_class=HTMLResponse)
    async def page_keywords(request: Request):
        return templates.TemplateResponse("keywords.html", {"request": request})

    @app.get("/historial", response_class=HTMLResponse)
    async def page_historial(request: Request):
        return templates.TemplateResponse("historial.html", {"request": request})

    return app


app = create_app()
