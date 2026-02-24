"""
Sistema de alertas para nuevas licitaciones.
Soporta email (SMTP) con diseño extensible para Webhook/Slack/WhatsApp.
"""
import logging
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import aiosmtplib
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database.models import Alert, Licitacion, SearchRun

logger = logging.getLogger(__name__)


class AlertNotifier:
    """
    Gestor de alertas multi-canal.
    Actualmente implementa email; fácilmente extensible a webhook/Slack.
    """

    async def notify_new_licitaciones(
        self,
        db: AsyncSession,
        run: SearchRun,
    ) -> None:
        """
        Notifica sobre nuevas licitaciones detectadas en un run.
        """
        if not settings.ALERTS_ENABLED:
            logger.debug("Alertas deshabilitadas en configuración")
            return

        # Obtener licitaciones nuevas del run
        result = await db.execute(
            select(Licitacion)
            .where(Licitacion.is_new == True)
            .order_by(Licitacion.relevance_score.desc())
            .limit(50)
        )
        new_licitaciones = result.scalars().all()

        if not new_licitaciones:
            return

        if settings.SMTP_USER and settings.ALERT_EMAIL_TO:
            await self._send_email(db, new_licitaciones, run)

    async def _send_email(
        self,
        db: AsyncSession,
        licitaciones: list[Licitacion],
        run: SearchRun,
    ) -> None:
        """Envía resumen por email usando SMTP asíncrono."""
        subject = (
            f"🔬 LicitaForense: {len(licitaciones)} nuevas licitaciones detectadas "
            f"— {datetime.now().strftime('%d/%m/%Y')}"
        )
        html_body = self._build_email_html(licitaciones, run)
        text_body = self._build_email_text(licitaciones)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.ALERT_EMAIL_FROM or settings.SMTP_USER
        msg["To"] = settings.ALERT_EMAIL_TO

        msg.attach(MIMEText(text_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        alert = Alert(
            channel="email",
            recipient=settings.ALERT_EMAIL_TO,
            subject=subject,
            licitaciones_count=len(licitaciones),
        )

        try:
            await aiosmtplib.send(
                msg,
                hostname=settings.SMTP_HOST,
                port=settings.SMTP_PORT,
                username=settings.SMTP_USER,
                password=settings.SMTP_PASSWORD,
                use_tls=False,
                start_tls=True,
            )
            alert.success = True
            logger.info(f"Email enviado a {settings.ALERT_EMAIL_TO}: {len(licitaciones)} licitaciones")
        except Exception as e:
            alert.success = False
            alert.error = str(e)
            logger.error(f"Error enviando email: {e}")
        finally:
            db.add(alert)
            await db.flush()

    def _build_email_html(self, licitaciones: list[Licitacion], run: SearchRun) -> str:
        items_html = ""
        for lic in licitaciones[:20]:
            keywords_html = "".join(
                f'<span style="background:#dbeafe;color:#1d4ed8;padding:2px 8px;border-radius:12px;'
                f'font-size:11px;margin-right:4px">{kw}</span>'
                for kw in (lic.matched_keywords or [])[:3]
            )
            score_pct = round((lic.relevance_score or 0) * 100)
            items_html += f"""
            <div style="border:1px solid #e5e7eb;border-radius:8px;padding:16px;margin-bottom:12px;">
              <div style="margin-bottom:8px">{keywords_html}</div>
              <h3 style="margin:0 0 4px;font-size:15px;color:#111827">{lic.titulo}</h3>
              <p style="margin:0 0 8px;color:#6b7280;font-size:13px">{lic.organismo or ''}</p>
              <div style="display:flex;justify-content:space-between;align-items:center">
                <span style="font-size:12px;color:#9ca3af">
                  {lic.fecha_publicacion.strftime('%d/%m/%Y') if lic.fecha_publicacion else ''}
                </span>
                <span style="font-size:12px;font-weight:bold;color:{'#059669' if score_pct > 70 else '#d97706'}"
                >{score_pct}% relevancia</span>
              </div>
              <a href="{lic.url_detalle}" target="_blank"
                 style="display:inline-block;margin-top:8px;font-size:12px;color:#2563eb">
                Ver en portal →
              </a>
            </div>
            """

        return f"""
        <html><body style="font-family:sans-serif;max-width:600px;margin:0 auto;padding:20px">
          <div style="background:#1e3a8a;color:white;padding:20px;border-radius:8px;margin-bottom:24px">
            <h1 style="margin:0;font-size:20px">🔬 LicitaForense Monitor</h1>
            <p style="margin:4px 0 0;opacity:0.8;font-size:14px">
              {len(licitaciones)} nuevas licitaciones detectadas
            </p>
          </div>
          <p style="color:#6b7280;font-size:13px;margin-bottom:16px">
            Búsqueda #{run.id} — {datetime.now().strftime('%d/%m/%Y %H:%M')}
          </p>
          {items_html}
          <div style="border-top:1px solid #e5e7eb;margin-top:24px;padding-top:12px;text-align:center">
            <p style="color:#9ca3af;font-size:12px">LicitaForense Monitor — Sistema automático de monitoreo</p>
          </div>
        </body></html>
        """

    def _build_email_text(self, licitaciones: list[Licitacion]) -> str:
        lines = ["LICITAFORENSE MONITOR - Nuevas licitaciones detectadas", "=" * 60, ""]
        for lic in licitaciones[:20]:
            lines.append(f"• {lic.titulo}")
            if lic.organismo:
                lines.append(f"  Organismo: {lic.organismo}")
            if lic.fecha_publicacion:
                lines.append(f"  Publicación: {lic.fecha_publicacion.strftime('%d/%m/%Y')}")
            lines.append(f"  URL: {lic.url_detalle}")
            lines.append("")
        return "\n".join(lines)
