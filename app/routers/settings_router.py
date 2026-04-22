"""Router Impostazioni — salva/leggi configurazioni da MongoDB."""
from fastapi import APIRouter, Body
from typing import Dict, Any
from datetime import datetime, timezone

from app.database import Database

router = APIRouter(tags=["Impostazioni"])


@router.get("/gmail")
async def get_gmail_settings() -> Dict[str, Any]:
    """Legge le impostazioni Gmail da MongoDB (password oscurata)."""
    db = Database.get_db()
    doc = await db["settings"].find_one({"chiave": "gmail"}, {"_id": 0})
    if not doc:
        # Leggi da .env come fallback
        import os
        return {
            "imap_user": os.environ.get("IMAP_USER", ""),
            "imap_host": os.environ.get("IMAP_HOST", "imap.gmail.com"),
            "has_password": bool(os.environ.get("IMAP_PASSWORD")),
            "sorgente": "env"
        }
    return {
        "imap_user": doc.get("imap_user", ""),
        "imap_host": doc.get("imap_host", "imap.gmail.com"),
        "has_password": bool(doc.get("gmail_app_password")),
        "sorgente": "database",
        "aggiornato_il": doc.get("aggiornato_il")
    }


@router.post("/gmail")
async def salva_gmail_settings(data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """
    Salva le impostazioni Gmail in MongoDB.
    Chiavi accettate: imap_user, gmail_app_password, imap_host
    """
    db = Database.get_db()
    imap_user = data.get("imap_user", "").strip()
    gmail_app_password = data.get("gmail_app_password", "").replace(" ", "")
    imap_host = data.get("imap_host", "imap.gmail.com").strip()

    if not imap_user:
        from fastapi import HTTPException
        raise HTTPException(400, "imap_user obbligatorio")
    if not gmail_app_password or len(gmail_app_password) < 8:
        from fastapi import HTTPException
        raise HTTPException(400, "App Password non valida (minimo 8 caratteri senza spazi)")

    await db["settings"].update_one(
        {"chiave": "gmail"},
        {"$set": {
            "chiave": "gmail",
            "imap_user": imap_user,
            "gmail_app_password": gmail_app_password,
            "imap_host": imap_host,
            "aggiornato_il": datetime.now(timezone.utc).isoformat()
        }},
        upsert=True
    )

    # Test connessione immediato
    test_result = await _test_imap(imap_host, imap_user, gmail_app_password)
    return {
        "status": "ok" if test_result["ok"] else "salvato_con_errore",
        "messaggio": "Credenziali salvate con successo" if test_result["ok"] else
                     f"Salvato, ma test connessione fallito: {test_result['error']}",
        "test_imap": test_result
    }


@router.post("/gmail/test")
async def test_gmail_connection() -> Dict[str, Any]:
    """Testa la connessione IMAP con le credenziali salvate."""
    db = Database.get_db()
    doc = await db["settings"].find_one({"chiave": "gmail"}, {"_id": 0})

    import os
    imap_user = doc.get("imap_user") if doc else os.environ.get("IMAP_USER", "")
    password = doc.get("gmail_app_password") if doc else os.environ.get("IMAP_PASSWORD", "")
    imap_host = doc.get("imap_host") if doc else os.environ.get("IMAP_HOST", "imap.gmail.com")

    result = await _test_imap(imap_host, imap_user, password)
    return result


async def _test_imap(host: str, user: str, password: str) -> Dict[str, Any]:
    """Testa connessione IMAP in modo asincrono."""
    import asyncio
    import imaplib

    def _test():
        try:
            conn = imaplib.IMAP4_SSL(host, 993)
            conn.login(user, password)
            conn.logout()
            return {"ok": True, "messaggio": f"Connessione IMAP riuscita per {user}"}
        except imaplib.IMAP4.error as e:
            return {"ok": False, "error": f"Credenziali non valide: {str(e)}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    return await asyncio.to_thread(_test)
