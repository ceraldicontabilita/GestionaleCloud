"""
Email Notification Service.
Send email notifications for important events.
"""
from typing import List, Dict, Any
from datetime import date
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class EmailService:
    """
    Email notification service.
    
    Sends notifications for:
    - Invoice payment reminders
    - Low stock alerts
    - HACCP violations
    - Employee document expiry
    - Payroll ready notifications
    """
    
    def __init__(self):
        self.smtp_host = getattr(settings, 'SMTP_HOST', None)
        self.smtp_port = getattr(settings, 'SMTP_PORT', 587)
        self.smtp_user = getattr(settings, 'SMTP_USER', None)
        self.smtp_password = getattr(settings, 'SMTP_PASSWORD', None)
        self.from_email = getattr(settings, 'FROM_EMAIL', self.smtp_user)
        
        self.enabled = all([
            self.smtp_host,
            self.smtp_user,
            self.smtp_password
        ])
        
        if not self.enabled:
            logger.warning(
                "Email service not configured. "
                "Set SMTP_HOST, SMTP_USER, SMTP_PASSWORD in .env"
            )
    
    async def send_invoice_payment_reminder(
        self,
        invoice: Dict[str, Any],
        to_email: str,
        days_overdue: int = 0
    ) -> bool:
        """
        Send payment reminder for invoice.
        
        Args:
            invoice: Invoice dict
            to_email: Recipient email
            days_overdue: Days past due date (0 = reminder before due)
            
        Returns:
            True if sent successfully
        """
        if not self.enabled:
            logger.warning("Email not sent: service not configured")
            return False
        
        subject = (
            f"Promemoria Pagamento Fattura {invoice.get('invoice_number')}"
            if days_overdue <= 0
            else f"Sollecito Pagamento Fattura {invoice.get('invoice_number')} - Scaduta"
        )
        
        body = self._build_invoice_reminder_html(invoice, days_overdue)
        
        return await self._send_email(to_email, subject, body)
    
    async def send_low_stock_alert(
        self,
        products: List[Dict[str, Any]],
        to_email: str
    ) -> bool:
        """
        Send alert for low stock products.
        
        Args:
            products: List of products below min stock
            to_email: Recipient email
            
        Returns:
            True if sent successfully
        """
        if not self.enabled:
            return False
        
        subject = f"⚠️ Allarme Scorte Basse - {len(products)} prodotti"
        
        body = self._build_low_stock_html(products)
        
        return await self._send_email(to_email, subject, body)
    
    async def send_haccp_violation_alert(
        self,
        violations: List[Dict[str, Any]],
        to_email: str
    ) -> bool:
        """
        Send HACCP violation alert.
        
        Critical: temperatures out of range.
        """
        if not self.enabled:
            return False
        
        subject = f"🚨 ALLARME HACCP - {len(violations)} Violazioni"
        
        body = self._build_haccp_alert_html(violations)
        
        return await self._send_email(to_email, subject, body)
    
    async def send_document_expiry_reminder(
        self,
        employee: Dict[str, Any],
        document_type: str,
        expiry_date: date,
        to_email: str
    ) -> bool:
        """
        Send reminder for expiring document.
        
        Args:
            employee: Employee dict
            document_type: Type of document (libretto_sanitario, etc)
            expiry_date: Document expiry date
            to_email: Recipient email
        """
        if not self.enabled:
            return False
        
        days_until_expiry = (expiry_date - date.today()).days
        
        subject = f"Promemoria Scadenza Documento - {employee.get('full_name')}"
        
        body = self._build_document_expiry_html(
            employee,
            document_type,
            expiry_date,
            days_until_expiry
        )
        
        return await self._send_email(to_email, subject, body)
    
    async def send_payroll_ready_notification(
        self,
        month: str,
        employee_count: int,
        to_email: str
    ) -> bool:
        """
        Notify that payroll is ready for distribution.
        """
        if not self.enabled:
            return False
        
        subject = f"Buste Paga Pronte - {month}"
        
        body = f"""
        <html>
        <body style="font-family: Arial, sans-serif;">
            <h2>Buste Paga Pronte</h2>
            <p>Le buste paga del mese <strong>{month}</strong> sono state generate.</p>
            <p><strong>Numero dipendenti:</strong> {employee_count}</p>
            <p>Accedi al sistema per la distribuzione.</p>
            <hr>
            <p style="font-size: 12px; color: #666;">
                ERP HORECA - Sistema di Gestione Aziendale
            </p>
        </body>
        </html>
        """
        
        return await self._send_email(to_email, subject, body)
    
    async def _send_email(
        self,
        to_email: str,
        subject: str,
        html_body: str
    ) -> bool:
        """
        Send HTML email via SMTP.
        
        Args:
            to_email: Recipient email
            subject: Email subject
            html_body: HTML body
            
        Returns:
            True if sent successfully
        """
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.from_email
            msg['To'] = to_email
            
            # Attach HTML
            html_part = MIMEText(html_body, 'html', 'utf-8')
            msg.attach(html_part)
            
            # Connect and send
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
            
            logger.info(f"Email sent to {to_email}: {subject}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {e}")
            return False
    
    def _build_invoice_reminder_html(
        self,
        invoice: Dict[str, Any],
        days_overdue: int
    ) -> str:
        """Build HTML for invoice payment reminder."""
        overdue_text = (
            f"<p style='color: red; font-weight: bold;'>ATTENZIONE: Fattura scaduta da {days_overdue} giorni</p>"
            if days_overdue > 0
            else ""
        )
        
        return f"""
        <html>
        <body style="font-family: Arial, sans-serif;">
            <h2>Promemoria Pagamento Fattura</h2>
            {overdue_text}
            <table style="border-collapse: collapse; width: 100%; max-width: 600px;">
                <tr>
                    <td style="padding: 8px; border: 1px solid #ddd;"><strong>Numero:</strong></td>
                    <td style="padding: 8px; border: 1px solid #ddd;">{invoice.get('invoice_number')}</td>
                </tr>
                <tr>
                    <td style="padding: 8px; border: 1px solid #ddd;"><strong>Data:</strong></td>
                    <td style="padding: 8px; border: 1px solid #ddd;">{invoice.get('date')}</td>
                </tr>
                <tr>
                    <td style="padding: 8px; border: 1px solid #ddd;"><strong>Fornitore:</strong></td>
                    <td style="padding: 8px; border: 1px solid #ddd;">{invoice.get('supplier_name')}</td>
                </tr>
                <tr>
                    <td style="padding: 8px; border: 1px solid #ddd;"><strong>Importo:</strong></td>
                    <td style="padding: 8px; border: 1px solid #ddd;">€{invoice.get('total_amount', 0):.2f}</td>
                </tr>
                <tr>
                    <td style="padding: 8px; border: 1px solid #ddd;"><strong>Scadenza:</strong></td>
                    <td style="padding: 8px; border: 1px solid #ddd;">{invoice.get('due_date')}</td>
                </tr>
            </table>
            <p style="margin-top: 20px;">
                <a href="#" style="background-color: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">
                    Visualizza Fattura
                </a>
            </p>
            <hr>
            <p style="font-size: 12px; color: #666;">
                ERP HORECA - Sistema di Gestione Aziendale
            </p>
        </body>
        </html>
        """
    
    def _build_low_stock_html(self, products: List[Dict[str, Any]]) -> str:
        """Build HTML for low stock alert."""
        products_html = ""
        for product in products[:10]:  # Max 10 in email
            products_html += f"""
            <tr>
                <td style="padding: 8px; border: 1px solid #ddd;">{product.get('name')}</td>
                <td style="padding: 8px; border: 1px solid #ddd; text-align: center;">{product.get('stock', 0)}</td>
                <td style="padding: 8px; border: 1px solid #ddd; text-align: center;">{product.get('min_stock', 0)}</td>
            </tr>
            """
        
        return f"""
        <html>
        <body style="font-family: Arial, sans-serif;">
            <h2>⚠️ Allarme Scorte Basse</h2>
            <p>I seguenti prodotti sono sotto la scorta minima:</p>
            <table style="border-collapse: collapse; width: 100%; max-width: 600px;">
                <thead>
                    <tr style="background-color: #f0f0f0;">
                        <th style="padding: 8px; border: 1px solid #ddd; text-align: left;">Prodotto</th>
                        <th style="padding: 8px; border: 1px solid #ddd;">Stock Attuale</th>
                        <th style="padding: 8px; border: 1px solid #ddd;">Scorta Minima</th>
                    </tr>
                </thead>
                <tbody>
                    {products_html}
                </tbody>
            </table>
            <p style="margin-top: 20px;">
                <a href="#" style="background-color: #dc3545; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">
                    Visualizza Magazzino
                </a>
            </p>
        </body>
        </html>
        """
    
    def _build_haccp_alert_html(self, violations: List[Dict[str, Any]]) -> str:
        """Build HTML for HACCP alert."""
        violations_html = ""
        for violation in violations[:5]:
            violations_html += f"""
            <tr style="background-color: #ffe6e6;">
                <td style="padding: 8px; border: 1px solid #ddd;">{violation.get('equipment_type')}</td>
                <td style="padding: 8px; border: 1px solid #ddd;">{violation.get('temperature')}°C</td>
                <td style="padding: 8px; border: 1px solid #ddd;">{violation.get('recorded_at')}</td>
            </tr>
            """
        
        return f"""
        <html>
        <body style="font-family: Arial, sans-serif;">
            <h2 style="color: #dc3545;">🚨 ALLARME HACCP</h2>
            <p><strong>Rilevate temperature fuori norma!</strong></p>
            <table style="border-collapse: collapse; width: 100%; max-width: 600px;">
                <thead>
                    <tr style="background-color: #dc3545; color: white;">
                        <th style="padding: 8px; border: 1px solid #ddd;">Attrezzatura</th>
                        <th style="padding: 8px; border: 1px solid #ddd;">Temperatura</th>
                        <th style="padding: 8px; border: 1px solid #ddd;">Ora</th>
                    </tr>
                </thead>
                <tbody>
                    {violations_html}
                </tbody>
            </table>
            <p style="margin-top: 20px; color: #dc3545;">
                <strong>AZIONE RICHIESTA: Verificare immediatamente le attrezzature!</strong>
            </p>
        </body>
        </html>
        """
    
    def _build_document_expiry_html(
        self,
        employee: Dict[str, Any],
        document_type: str,
        expiry_date: date,
        days_until_expiry: int
    ) -> str:
        """Build HTML for document expiry reminder."""
        urgency_color = "#dc3545" if days_until_expiry <= 7 else "#ffc107"
        
        doc_names = {
            'libretto_sanitario': 'Libretto Sanitario',
            'contract': 'Contratto',
            'certification': 'Certificazione'
        }
        
        doc_name = doc_names.get(document_type, document_type)
        
        return f"""
        <html>
        <body style="font-family: Arial, sans-serif;">
            <h2 style="color: {urgency_color};">Promemoria Scadenza Documento</h2>
            <p><strong>Dipendente:</strong> {employee.get('full_name')}</p>
            <p><strong>Documento:</strong> {doc_name}</p>
            <p><strong>Scadenza:</strong> {expiry_date.isoformat()}</p>
            <p style="font-size: 18px; color: {urgency_color};">
                <strong>Mancano {days_until_expiry} giorni alla scadenza</strong>
            </p>
            <p>Provvedere al rinnovo del documento.</p>
        </body>
        </html>
        """


# Singleton instance
email_service = EmailService()
