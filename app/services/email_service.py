from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
import smtplib

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.domain import EmailSend, ProviderRequest


class EmailService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()
        templates = Path(__file__).resolve().parents[1] / "templates" / "email"
        self.env = Environment(loader=FileSystemLoader(templates), autoescape=select_autoescape(["html", "xml"]))

    def draft(self, provider_request_id: int) -> EmailSend:
        provider_request = self.db.get(ProviderRequest, provider_request_id)
        if not provider_request:
            raise ValueError("Solicitud por proveedor no encontrada")

        existing = self.db.scalar(
            select(EmailSend)
            .where(
                EmailSend.provider_request_id == provider_request_id,
                EmailSend.status != "ENVIADO",
            )
            .order_by(EmailSend.id.desc())
        )
        if existing:
            return existing

        data = [{
            "producto": item.request_item.product_service.name if item.request_item.product_service else "Sin identificar",
            "cantidad": item.request_item.quantity,
            "marca": item.request_item.brand.name if item.request_item.brand else None,
            "caracteristicas": [
                f"{characteristic.characteristic.name}: {characteristic.normalized_value}"
                for characteristic in item.request_item.characteristics
            ],
        } for item in provider_request.items]

        body = self.env.get_template("quote_request.txt.j2").render(
            proveedor=provider_request.provider,
            articulos=data,
        )
        subject = f"Solicitud de proforma - Solicitud #{provider_request.request_id}"
        email = EmailSend(
            provider_request_id=provider_request.id,
            to_email=provider_request.provider.email,
            subject=subject,
            body_text=body,
            status="BORRADOR",
        )
        self.db.add(email)
        self.db.commit()
        self.db.refresh(email)
        return email

    def update(self, email_id: int, *, to_email: str, subject: str, body_text: str) -> EmailSend:
        record = self.db.get(EmailSend, email_id)
        if not record:
            raise ValueError("Correo no encontrado")
        if record.status == "ENVIADO":
            raise ValueError("Un correo enviado ya no puede editarse")

        record.to_email = to_email.strip()
        record.subject = subject.strip()
        record.body_text = body_text.strip()
        record.status = "BORRADOR"
        record.error_message = None
        self.db.commit()
        self.db.refresh(record)
        return record

    def decide(self, email_id: int, *, authorized: bool) -> EmailSend:
        record = self.db.get(EmailSend, email_id)
        if not record:
            raise ValueError("Correo no encontrado")
        if record.status == "ENVIADO":
            raise ValueError("Un correo enviado ya no puede cambiar de decisión")
        record.status = "AUTORIZADO" if authorized else "RECHAZADO"
        record.error_message = None
        self.db.commit()
        self.db.refresh(record)
        return record

    def send(self, email_id: int) -> EmailSend:
        record = self.db.get(EmailSend, email_id)
        if not record:
            raise ValueError("Correo no encontrado")
        if record.status != "AUTORIZADO":
            raise ValueError("El correo debe estar AUTORIZADO antes de enviarse")
        if not all([self.settings.smtp_host, self.settings.smtp_from]):
            raise ValueError("SMTP no está configurado. Complete las variables SMTP en .env")

        msg = EmailMessage()
        msg["From"] = self.settings.smtp_from
        msg["To"] = record.to_email
        msg["Subject"] = record.subject
        msg.set_content(record.body_text)

        try:
            with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=20) as smtp:
                smtp.ehlo()
                if self.settings.smtp_use_tls:
                    smtp.starttls()
                    smtp.ehlo()
                if self.settings.smtp_user and self.settings.smtp_password:
                    smtp.login(self.settings.smtp_user, self.settings.smtp_password)
                smtp.send_message(msg)
            record.status = "ENVIADO"
            record.sent_at = datetime.now(timezone.utc)
            record.error_message = None
        except Exception as exc:
            record.status = "ERROR"
            record.error_message = str(exc)[:1000]
            self.db.commit()
            raise ValueError("No fue posible enviar el correo mediante SMTP") from exc

        self.db.commit()
        self.db.refresh(record)
        return record
