"""Configurazione unica dei cookie di sessione."""

import os


def session_cookie_secure() -> bool:
    """True sugli ambienti HTTPS di produzione, False sullo sviluppo HTTP."""
    return bool(
        os.getenv("RENDER")
        or os.getenv("RENDER_SERVICE_ID")
        or os.getenv("ENVIRONMENT", "").strip().lower() == "production"
    )


SESSION_COOKIE_SECURE = session_cookie_secure()
