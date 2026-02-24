#!/usr/bin/env python3
"""
LicitaForense Monitor — CLI principal.

Uso:
  python main.py serve          → Inicia el servidor web
  python main.py search         → Ejecuta búsqueda manual
  python main.py portales list  → Lista portales
  python main.py portales add   → Agrega un portal
  python main.py keywords list  → Lista keywords
  python main.py stats          → Muestra estadísticas
"""
import asyncio
import logging
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
from rich.progress import Progress, SpinnerColumn, TextColumn

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
# Silenciar logs verbose de librerías
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)
logging.getLogger("hpack").setLevel(logging.WARNING)

console = Console()
app = typer.Typer(
    name="licitaforense",
    help="🔬 LicitaForense Monitor — Sistema de monitoreo de licitaciones forenses",
    add_completion=False,
    rich_markup_mode="rich",
)
portales_app = typer.Typer(help="Gestión de portales")
keywords_app = typer.Typer(help="Gestión de keywords")
app.add_typer(portales_app, name="portales")
app.add_typer(keywords_app, name="keywords")


# ─────────────────────────────────────────────────────────────────────────────
# Comando: serve
# ─────────────────────────────────────────────────────────────────────────────

@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", help="Host del servidor"),
    port: int = typer.Option(8000, help="Puerto del servidor"),
    reload: bool = typer.Option(False, help="Auto-reload en desarrollo"),
):
    """
    🚀 Inicia el servidor web de LicitaForense Monitor.
    """
    console.print(Panel(
        f"[bold blue]🔬 LicitaForense Monitor[/bold blue]\n"
        f"Servidor iniciando en [cyan]http://{host}:{port}[/cyan]\n"
        f"Dashboard: [green]http://localhost:{port}/[/green]\n"
        f"API Docs:  [green]http://localhost:{port}/api/docs[/green]",
        title="[bold]Iniciando servidor[/bold]",
        border_style="blue",
    ))

    import uvicorn
    uvicorn.run(
        "api.app:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Comando: search
# ─────────────────────────────────────────────────────────────────────────────

@app.command()
def search(
    keywords: Optional[list[str]] = typer.Option(None, "--keyword", "-k", help="Keywords adicionales"),
    days: int = typer.Option(2, help="Días hacia atrás a buscar"),
    portal: Optional[list[int]] = typer.Option(None, "--portal", "-p", help="IDs de portales específicos"),
):
    """
    🔍 Ejecuta una búsqueda manual de licitaciones.

    Ejemplos:
      python main.py search
      python main.py search -k "kit forense" -k "ADN"
      python main.py search --days 7
    """
    asyncio.run(_run_search(keywords, days, portal))


async def _run_search(
    keywords_override: Optional[list[str]],
    days: int,
    portal_ids: Optional[list[int]],
):
    from datetime import datetime, timedelta
    from database.db import init_db, get_db_context
    from core.orchestrator import SearchOrchestrator
    from api.seed import seed_initial_data

    console.print(Panel(
        "[bold]Iniciando búsqueda manual...[/bold]",
        border_style="green",
    ))

    await init_db()
    await seed_initial_data()

    date_from = datetime.utcnow() - timedelta(days=days)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Escaneando portales...", total=None)

        async with get_db_context() as db:
            orchestrator = SearchOrchestrator(db)
            run = await orchestrator.run(
                triggered_by="cli",
                keywords_override=keywords_override,
                portal_ids=portal_ids,
                date_from=date_from,
            )

        progress.update(task, description="✓ Búsqueda completada")

    # Mostrar resultados
    _print_run_summary(run)


def _print_run_summary(run):
    from database.models import RunStatus
    status_emoji = {
        "success": "✅", "partial": "⚠️", "failed": "❌", "running": "🔄"
    }
    emoji = status_emoji.get(run.status.value, "❓")

    console.print(Panel(
        f"{emoji} [bold]Búsqueda #{run.id}[/bold] — {run.status.value.upper()}\n\n"
        f"Portales escaneados: [cyan]{run.portals_scanned}[/cyan]\n"
        f"Portales fallidos:   [red]{run.portals_failed}[/red]\n"
        f"Licitaciones encontradas: [yellow]{run.licitaciones_found}[/yellow]\n"
        f"[bold green]NUEVAS: {run.licitaciones_new}[/bold green]\n\n"
        f"Duración: {(run.duration_seconds or 0):.1f}s",
        title="Resultado",
        border_style="green" if run.status.value == "success" else "yellow",
    ))


# ─────────────────────────────────────────────────────────────────────────────
# Comando: stats
# ─────────────────────────────────────────────────────────────────────────────

@app.command()
def stats():
    """📊 Muestra estadísticas del sistema."""
    asyncio.run(_show_stats())


async def _show_stats():
    from database.db import init_db, get_db_context
    from database.models import Licitacion, Portal, Keyword, SearchRun
    from sqlalchemy import select, func, desc

    await init_db()

    async with get_db_context() as db:
        total = (await db.execute(select(func.count(Licitacion.id)))).scalar_one()
        nuevas = (await db.execute(
            select(func.count(Licitacion.id)).where(Licitacion.is_new == True)
        )).scalar_one()
        portales_count = (await db.execute(select(func.count(Portal.id)))).scalar_one()
        keywords_count = (await db.execute(
            select(func.count(Keyword.id)).where(Keyword.is_active == True)
        )).scalar_one()
        runs_count = (await db.execute(select(func.count(SearchRun.id)))).scalar_one()

        # Por portal
        por_portal = await db.execute(
            select(Portal.name, func.count(Licitacion.id))
            .join(Licitacion, Licitacion.portal_id == Portal.id, isouter=True)
            .group_by(Portal.id)
            .order_by(desc(func.count(Licitacion.id)))
        )

    console.print(Panel(
        f"[bold blue]🔬 LicitaForense Monitor[/bold blue] — Estadísticas\n\n"
        f"Total licitaciones:   [bold]{total}[/bold]\n"
        f"Nuevas sin revisar:   [bold green]{nuevas}[/bold green]\n"
        f"Portales activos:     [cyan]{portales_count}[/cyan]\n"
        f"Keywords activas:     [cyan]{keywords_count}[/cyan]\n"
        f"Búsquedas realizadas: [cyan]{runs_count}[/cyan]",
        title="Estadísticas",
        border_style="blue",
    ))

    table = Table(title="Por portal", box=box.ROUNDED)
    table.add_column("Portal", style="cyan")
    table.add_column("Licitaciones", justify="right")

    for name, count in por_portal.all():
        table.add_row(name, str(count or 0))

    console.print(table)


# ─────────────────────────────────────────────────────────────────────────────
# Portales CLI
# ─────────────────────────────────────────────────────────────────────────────

@portales_app.command("list")
def portales_list():
    """Lista todos los portales registrados."""
    asyncio.run(_list_portales())


async def _list_portales():
    from database.db import init_db, get_db_context
    from database.models import Portal
    from sqlalchemy import select

    await init_db()
    async with get_db_context() as db:
        result = await db.execute(select(Portal).order_by(Portal.level, Portal.name))
        portales = result.scalars().all()

    table = Table(title="Portales registrados", box=box.ROUNDED)
    table.add_column("ID", style="dim", width=4)
    table.add_column("Nombre", style="cyan")
    table.add_column("Nivel")
    table.add_column("URL", style="blue")
    table.add_column("Estado")
    table.add_column("Habilitado")

    status_style = {"active": "green", "error": "red", "inactive": "dim"}
    for p in portales:
        sty = status_style.get(p.status.value, "")
        table.add_row(
            str(p.id),
            p.name,
            p.level.value,
            p.url[:50] + ("..." if len(p.url) > 50 else ""),
            f"[{sty}]{p.status.value}[/{sty}]",
            "✅" if p.is_enabled else "❌",
        )

    console.print(table)


@portales_app.command("add")
def portales_add(
    name: str = typer.Option(..., prompt="Nombre del portal"),
    url: str = typer.Option(..., prompt="URL del portal"),
    short_name: str = typer.Option(..., prompt="ID corto (sin espacios)"),
    level: str = typer.Option("municipal", prompt="Nivel (nacional/provincial/municipal)"),
    municipality: Optional[str] = typer.Option(None, prompt="Municipio (si aplica)"),
):
    """Agrega un nuevo portal de licitaciones."""
    asyncio.run(_add_portal(name, url, short_name, level, municipality))


async def _add_portal(name, url, short_name, level, municipality):
    from database.db import init_db, get_db_context
    from database.models import Portal, PortalLevel

    await init_db()
    async with get_db_context() as db:
        try:
            portal = Portal(
                name=name,
                short_name=short_name,
                url=url,
                level=PortalLevel(level),
                municipality=municipality,
                scraper_class="GenericMunicipalScraper",
                scraper_config={"municipality_key": short_name, "short_name": short_name},
                is_enabled=True,
            )
            db.add(portal)
            await db.flush()
            console.print(f"[green]✓ Portal '{name}' agregado (ID: {portal.id})[/green]")
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")


# ─────────────────────────────────────────────────────────────────────────────
# Keywords CLI
# ─────────────────────────────────────────────────────────────────────────────

@keywords_app.command("list")
def keywords_list():
    """Lista todas las keywords activas."""
    asyncio.run(_list_keywords())


async def _list_keywords():
    from database.db import init_db, get_db_context
    from database.models import Keyword
    from sqlalchemy import select

    await init_db()
    async with get_db_context() as db:
        result = await db.execute(
            select(Keyword).order_by(Keyword.priority.desc(), Keyword.term)
        )
        keywords = result.scalars().all()

    table = Table(title="Keywords de búsqueda", box=box.ROUNDED)
    table.add_column("ID", style="dim", width=4)
    table.add_column("Término", style="cyan")
    table.add_column("Categoría")
    table.add_column("Prioridad", justify="center")
    table.add_column("Activa", justify="center")

    for kw in keywords:
        table.add_row(
            str(kw.id),
            kw.term,
            kw.category or "—",
            str(kw.priority),
            "✅" if kw.is_active else "❌",
        )

    console.print(table)


@keywords_app.command("add")
def keywords_add(
    term: str = typer.Argument(..., help="Término de búsqueda"),
    category: Optional[str] = typer.Option(None, help="Categoría"),
    priority: int = typer.Option(7, help="Prioridad (1-10)"),
):
    """Agrega una nueva keyword de búsqueda."""
    asyncio.run(_add_keyword(term, category, priority))


async def _add_keyword(term, category, priority):
    from database.db import init_db, get_db_context
    from database.models import Keyword

    await init_db()
    async with get_db_context() as db:
        kw = Keyword(term=term, category=category, priority=priority, is_active=True)
        db.add(kw)
        await db.flush()
        console.print(f"[green]✓ Keyword '{term}' agregada (ID: {kw.id})[/green]")


# ─────────────────────────────────────────────────────────────────────────────
# Entrypoint
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app()
