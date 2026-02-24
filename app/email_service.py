"""
Email Service for automated notifications.

This module provides a service class for sending email alerts using SMTP,
with retry logic, context managers, and robust error handling.

Primary use cases:
- Libretto sanitario expiration alerts
- Employee notifications
- Admin alerts
"""

import logging
import os
import smtplib
import time
from contextlib import contextmanager
from datetime import date, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Iterator, Optional

from app.exceptions import ExternalServiceError

logger = logging.getLogger(__name__)

ADMIN_EMAIL = "ceraldigroupsrl@gmail.com"


class EmailService:
    """
    Email service for sending automated notifications via SMTP.

    Provides:
    - Retry logic with exponential backoff
    - Context manager for SMTP connections
    - Structured error handling
    - Email templating for common notifications

    Attributes:
        smtp_email: SMTP sender email address
        smtp_password: SMTP password
        smtp_host: SMTP server hostname
        smtp_port: SMTP server port
        max_retries: Maximum retry attempts for failed sends
        retry_delay: Initial delay between retries (seconds)
    """

    def __init__(
        self,
        smtp_email: Optional[str] = None,
        smtp_password: Optional[str] = None,
        smtp_host: Optional[str] = None,
        smtp_port: Optional[int] = None,
        max_retries: int = 3,
        retry_delay: float = 2.0
    ):
        """
        Initialize EmailService with SMTP configuration.

        Args:
            smtp_email: SMTP email address (defaults to env SMTP_EMAIL)
            smtp_password: SMTP password (defaults to env SMTP_PASSWORD)
            smtp_host: SMTP host (defaults to env SMTP_HOST or 'smtp.gmail.com')
            smtp_port: SMTP port (defaults to env SMTP_PORT or 587)
            max_retries: Maximum retry attempts (default: 3)
            retry_delay: Initial retry delay in seconds (default: 2.0)

        Raises:
            ExternalServiceError: If SMTP credentials are missing
        """
        self.smtp_email = smtp_email or os.environ.get('SMTP_EMAIL', 'ceraldigroupsrl@gmail.com')
        self.smtp_password = smtp_password or os.environ.get('SMTP_PASSWORD')
        self.smtp_host = smtp_host or os.environ.get('SMTP_HOST', 'smtp.gmail.com')
        self.smtp_port = smtp_port or int(os.environ.get('SMTP_PORT', 587))
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        if not self.smtp_password:
            logger.warning("SMTP password not configured - EmailService disabled")

    @contextmanager
    def smtp_connection(self) -> Iterator[smtplib.SMTP]:
        """
        Context manager for SMTP connections with automatic cleanup.

        Yields:
            smtplib.SMTP: Authenticated SMTP connection

        Raises:
            ExternalServiceError: If SMTP connection or authentication fails

        Examples:
            >>> service = EmailService()
            >>> with service.smtp_connection() as smtp:
            ...     smtp.send_message(msg)
        """
        if not self.smtp_password:
            raise ExternalServiceError("SMTP password not configured")

        server = None
        try:
            server = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30)
            server.starttls()
            server.login(self.smtp_email, self.smtp_password)
            logger.info(f"✅ SMTP connection established to {self.smtp_host}:{self.smtp_port}")
            yield server
        except smtplib.SMTPException as e:
            logger.error(f"❌ SMTP connection error: {e}")
            raise ExternalServiceError(f"SMTP connection failed: {str(e)}") from e
        finally:
            if server:
                try:
                    server.quit()
                    logger.info("✅ SMTP connection closed")
                except Exception as e:
                    logger.warning(f"Error closing SMTP connection: {e}")

    def send_email_with_retry(
        self,
        to_email: str,
        subject: str,
        body_html: str,
        from_email: Optional[str] = None
    ) -> bool:
        """
        Send email with exponential backoff retry logic.

        Args:
            to_email: Recipient email address
            subject: Email subject line
            body_html: HTML email body
            from_email: Sender email (defaults to self.smtp_email)

        Returns:
            True if email sent successfully, False otherwise

        Raises:
            ExternalServiceError: If all retry attempts fail

        Examples:
            >>> service = EmailService()
            >>> success = service.send_email_with_retry(
            ...     'user@example.com',
            ...     'Test Subject',
            ...     '<h1>Hello</h1>'
            ... )
        """
        if not self.smtp_password:
            logger.warning("SMTP not configured - skipping email send")
            return False

        from_email = from_email or self.smtp_email

        # Create email message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = from_email
        msg['To'] = to_email

        html_part = MIMEText(body_html, 'html')
        msg.attach(html_part)

        # Retry loop with exponential backoff
        for attempt in range(1, self.max_retries + 1):
            try:
                with self.smtp_connection() as smtp:
                    smtp.send_message(msg)
                    logger.info(f"✅ Email sent to {to_email} (subject: {subject})")
                    return True

            except ExternalServiceError as e:
                if attempt < self.max_retries:
                    delay = self.retry_delay * (2 ** (attempt - 1))  # Exponential backoff
                    logger.warning(f"⚠️ Email send failed (attempt {attempt}/{self.max_retries}), retrying in {delay}s...")
                    time.sleep(delay)
                else:
                    logger.error(f"❌ Email send failed after {self.max_retries} attempts: {e}")
                    raise

        return False

    def send_libretto_alert_email(
        self,
        employee_name: str,
        employee_email: str,
        expiry_date: date,
        days_until_expiry: int
    ) -> bool:
        """
        Send libretto sanitario expiration alert to admin.

        Args:
            employee_name: Full name of employee
            employee_email: Employee's email address
            expiry_date: Libretto expiration date
            days_until_expiry: Days remaining until expiration

        Returns:
            True if email sent successfully, False otherwise

        Examples:
            >>> service = EmailService()
            >>> success = service.send_libretto_alert_email(
            ...     'Mario Rossi',
            ...     'mario.rossi@example.com',
            ...     date(2024, 12, 31),
            ...     15
            ... )
        """
        try:
            subject = f"⚠️ Alert Scadenza Libretto Sanitario - {employee_name}"

            body = f"""
            <html>
            <body style="font-family: Arial, sans-serif;">
                <h2 style="color: #e74c3c;">Alert Scadenza Libretto Sanitario</h2>
                <p><strong>Dipendente:</strong> {employee_name}</p>
                <p><strong>Email:</strong> {employee_email}</p>
                <p><strong>Data Scadenza:</strong> {expiry_date.strftime('%d/%m/%Y')}</p>
                <p><strong>Giorni Rimanenti:</strong> <span style="color: #e74c3c; font-weight: bold;">{days_until_expiry}</span></p>

                <div style="background-color: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; margin: 20px 0;">
                    <p style="margin: 0;"><strong>⚠️ Azione Richiesta:</strong></p>
                    <p style="margin: 5px 0 0 0;">Si prega di contattare il dipendente per rinnovare il libretto sanitario prima della scadenza.</p>
                </div>

                <p style="color: #666; font-size: 12px; margin-top: 30px;">
                    Questo è un messaggio automatico dal sistema HACCP Ceraldi Group S.R.L.
                </p>
            </body>
            </html>
            """

            return self.send_email_with_retry(ADMIN_EMAIL, subject, body)

        except Exception as e:
            logger.error(f"❌ Error sending libretto alert email: {e}")
            return False

    def check_and_send_alerts(self, employees_data: list, alert_days: int = 30) -> int:
        """
        Check employees and send alerts for expiring libretti sanitari.

        Scans employee records and sends email alerts for libretti expiring
        within the specified threshold.

        Args:
            employees_data: List of employee dictionaries with libretto data
            alert_days: Alert threshold in days (default: 30)

        Returns:
            Number of alerts sent successfully

        Examples:
            >>> employees = [
            ...     {
            ...         'nome': 'Mario',
            ...         'cognome': 'Rossi',
            ...         'email': 'mario@example.com',
            ...         'data_scadenza_libretto': date(2024, 12, 15),
            ...         'alert_sent': False
            ...     }
            ... ]
            >>> service = EmailService()
            >>> alerts_sent = service.check_and_send_alerts(employees)
        """
        today = date.today()
        alert_threshold = today + timedelta(days=alert_days)

        alerts_sent = 0

        for employee in employees_data:
            expiry_date = employee.get('data_scadenza_libretto')
            if not expiry_date:
                continue

            # Convert string to date if needed
            if isinstance(expiry_date, str):
                try:
                    expiry_date = date.fromisoformat(expiry_date)
                except (ValueError, TypeError):
                    logger.warning(f"Invalid expiry date for {employee.get('nome')} {employee.get('cognome')}")
                    continue

            # Check if alert needed and not already sent
            if not employee.get('alert_sent', False) and expiry_date <= alert_threshold:
                days_until = (expiry_date - today).days
                employee_name = f"{employee['nome']} {employee['cognome']}"

                if self.send_libretto_alert_email(
                    employee_name,
                    employee['email'],
                    expiry_date,
                    days_until
                ):
                    alerts_sent += 1
                    employee['alert_sent'] = True

        logger.info(f"✅ Sent {alerts_sent} libretto expiration alerts")
        return alerts_sent


# Legacy function wrappers for backwards compatibility
def send_libretto_alert_email(
    employee_name: str,
    employee_email: str,
    expiry_date: date,
    days_until_expiry: int,
    smtp_email: Optional[str] = None,
    smtp_password: Optional[str] = None
) -> bool:
    """
    Send libretto sanitario expiration alert (legacy wrapper).

    Args:
        employee_name: Full name of employee
        employee_email: Employee's email address
        expiry_date: Libretto expiration date
        days_until_expiry: Days remaining until expiration
        smtp_email: SMTP email (optional, uses env if not provided)
        smtp_password: SMTP password (optional, uses env if not provided)

    Returns:
        True if email sent successfully, False otherwise
    """
    service = EmailService(smtp_email=smtp_email, smtp_password=smtp_password)
    return service.send_libretto_alert_email(
        employee_name,
        employee_email,
        expiry_date,
        days_until_expiry
    )


def check_and_send_alerts(employees_db: list) -> int:
    """
    Check employees and send alerts (legacy wrapper).

    Args:
        employees_db: List of employee dictionaries

    Returns:
        Number of alerts sent
    """
    service = EmailService()
    return service.check_and_send_alerts(employees_db)
