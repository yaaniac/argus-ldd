# 🔬 LicitaForense Monitor

Sistema profesional de monitoreo automático de licitaciones públicas argentinas especializadas en el **sector forense y criminalística**.

---

## ¿Qué hace?

- Busca automáticamente licitaciones en portales nacionales, provinciales y municipales
- Filtra por palabras clave del dominio forense (`ADN`, `balística`, `criminalística`, etc.)
- Detecta publicaciones nuevas desde la última ejecución
- Evita duplicados con un sistema de hashing de contenido
- Calcula un score de relevancia para priorizar resultados
- Envía alertas por email cuando hay nuevas licitaciones
- Expone una API REST + dashboard web

---

## Portales cubiertos

### Nacional
| Portal | Scraper |
|--------|---------|
| Argentina Compra (COMPR.AR) | `ComprarScraper` |
| Boletín Oficial de la Nación | `BoletinNacionalScraper` |

### Provincia de Buenos Aires
| Portal | Scraper |
|--------|---------|
| Portal Buenos Aires Compra (PBAC) | `PortalComprasPBAScraper` |
| Boletín Oficial PBA | `BoletinOficialPBAScraper` |

### Municipios (Buenos Aires)
| Municipio | Estado |
|-----------|--------|
| La Plata | Habilitado |
| Mar del Plata (Gral. Pueyrredon) | Habilitado |
| Bahía Blanca | Habilitado |
| San Isidro | Habilitado |
| Quilmes | Deshabilitado |
| Tigre | Deshabilitado |

> Cualquier municipio adicional se puede agregar desde el dashboard o CLI con un click.

---

## Instalación rápida

```bash
# 1. Clonar / entrar al proyecto
cd licitaciones-monitor

# 2. Crear entorno virtual
python3 -m venv venv
source venv/bin/activate   # macOS/Linux
# venv\Scripts\activate    # Windows

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configurar variables de entorno
cp .env.example .env
# Editar .env si necesitás cambiar puertos, habilitar emails, etc.

# 5. Iniciar el servidor
python main.py serve
```

Abrí `http://localhost:8000` en el navegador.

---

## Uso del CLI

```bash
# Iniciar servidor web
python main.py serve

# Ejecutar búsqueda manual
python main.py search

# Búsqueda con keywords adicionales
python main.py search -k "kit forense" -k "luminol" --days 7

# Ver estadísticas
python main.py stats

# Listar portales
python main.py portales list

# Agregar portal municipal
python main.py portales add

# Listar keywords
python main.py keywords list

# Agregar keyword
python main.py keywords add "reactivos forenses" --category equipamiento --priority 8
```

---

## API REST

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/api/licitaciones` | Lista con filtros (q, portal, status, fecha) |
| GET | `/api/licitaciones/{id}` | Detalle de una licitación |
| PATCH | `/api/licitaciones/{id}/status` | Cambiar estado (vista/favorita/descartada) |
| GET | `/api/stats` | Estadísticas generales |
| GET | `/api/portales` | Lista portales |
| POST | `/api/portales` | Agregar portal |
| PATCH | `/api/portales/{id}` | Actualizar portal |
| GET | `/api/keywords` | Lista keywords |
| POST | `/api/keywords` | Agregar keyword |
| POST | `/api/runs/trigger` | Disparar búsqueda manual |
| GET | `/api/runs` | Historial de ejecuciones |

Documentación interactiva: `http://localhost:8000/api/docs`

---

## Arquitectura

```
licitaciones-monitor/
├── main.py                    # CLI entry point (Typer + Rich)
├── config.py                  # Configuración central (pydantic-settings)
│
├── database/
│   ├── models.py              # SQLAlchemy ORM: Portal, Licitacion, Keyword, SearchRun
│   └── db.py                  # Engine async + session factory
│
├── scrapers/                  # Un scraper por tipo de portal
│   ├── base.py                # Clase abstracta BaseScraper + LicitacionData DTO
│   ├── comprar.py             # Argentina Compra / COMPR.AR
│   ├── boletin_nacional.py    # Boletín Oficial Nacional
│   ├── portal_compras_pba.py  # Portal Buenos Aires Compra (PBAC)
│   ├── boletin_pba.py         # Boletín Oficial PBA
│   └── municipal/
│       └── generic.py         # Scraper genérico auto-adaptativo para municipios
│
├── core/
│   ├── orchestrator.py        # Coordina scrapers, dedup, DB, alertas
│   ├── matcher.py             # Motor de scoring keyword/relevancia
│   └── deduplicator.py        # Deduplicación por SHA-256
│
├── scheduler/
│   └── scheduler.py           # APScheduler — ejecuciones automáticas cada N horas
│
├── api/
│   ├── app.py                 # FastAPI app factory + lifespan
│   ├── seed.py                # Datos iniciales (portales + keywords forenses)
│   └── routes/                # Endpoints REST
│       ├── licitaciones.py
│       ├── portales.py
│       ├── keywords.py
│       └── runs.py
│
├── alerts/
│   └── notifier.py            # Email SMTP + extensible a Webhook/Slack
│
├── templates/                 # Jinja2 + Tailwind + Alpine.js
│   ├── base.html
│   ├── index.html             # Dashboard con KPIs
│   ├── licitaciones.html      # Lista con filtros avanzados
│   ├── detalle.html           # Vista detalle de licitación
│   ├── portales.html          # Gestión de portales
│   ├── keywords.html          # Gestión de keywords
│   └── historial.html         # Historial de ejecuciones
│
└── data/
    └── portals_registry.json  # Configuración declarativa de portales
```

---

## Agregar un nuevo municipio

### Opción 1: Desde el dashboard
1. Ir a `/portales`
2. Click en "+ Agregar portal"
3. Completar nombre, URL y seleccionar `GenericMunicipalScraper`

### Opción 2: Editar el JSON
Agregar en `data/portals_registry.json`:
```json
{
  "name": "Municipalidad de Lomas de Zamora",
  "short_name": "lomas-de-zamora",
  "url": "https://www.lomasdezamora.gov.ar",
  "level": "municipal",
  "province": "Buenos Aires",
  "municipality": "Lomas de Zamora",
  "scraper_class": "GenericMunicipalScraper",
  "scraper_config": {
    "municipality_key": "lomas-de-zamora",
    "short_name": "lomas-de-zamora"
  },
  "is_enabled": true
}
```

### Opción 3: CLI
```bash
python main.py portales add
```

---

## Configurar alertas por email

En `.env`:
```
ALERTS_ENABLED=true
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=tu-cuenta@gmail.com
SMTP_PASSWORD=tu-app-password-de-gmail
ALERT_EMAIL_FROM=tu-cuenta@gmail.com
ALERT_EMAIL_TO=destinatario@ejemplo.com
```

> Para Gmail: activar "contraseñas de aplicación" en la cuenta de Google.

---

## Roadmap hacia SaaS

- [ ] Autenticación multi-tenant (usuarios/organizaciones)
- [ ] Webhooks (Slack, Teams, WhatsApp Business)
- [ ] API pública con rate limiting
- [ ] Exportación a Excel/CSV
- [ ] Scraper para Contratar.gob.ar (OCDS)
- [ ] Integración con más provincias (Córdoba, Santa Fe, Mendoza)
- [ ] Análisis semántico con embeddings para mejor relevancia
- [ ] Notificaciones push (PWA)
- [ ] Deploy con Docker Compose + PostgreSQL
