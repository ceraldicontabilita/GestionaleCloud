"""
Router Sync - Configurazione Email e Sincronizzazione
"""
from fastapi import APIRouter, HTTPException
from typing import Dict, Any, Optional
from pydantic import BaseModel
from datetime import datetime, timezone
import uuid
import os

from app.database import Database

router = APIRouter()

COLLECTION_EMAIL_ACCOUNTS = "email_accounts"


class ConfiguraEmailRequest(BaseModel):
    """Request per configurare email Aruba/Gmail"""
    email: str
    password: str
    imap_server: str = "imap.gmail.com"
    imap_port: int = 993
    nome: Optional[str] = None


@router.post("/sync/configura-email-aruba")
async def configura_email_aruba(config: ConfiguraEmailRequest) -> Dict[str, Any]:
    """
    Configura un account email per la sincronizzazione automatica.
    Supporta Gmail, Aruba o qualsiasi server IMAP.
    """
    db = Database.get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database non disponibile")
    
    # Verifica se l'email è già configurata
    existing = await db[COLLECTION_EMAIL_ACCOUNTS].find_one({"email": config.email})
    
    account_data = {
        "id": str(uuid.uuid4()) if not existing else existing.get("id", str(uuid.uuid4())),
        "nome": config.nome or f"Account {config.email}",
        "email": config.email,
        "app_password": config.password,
        "imap_server": config.imap_server,
        "imap_port": config.imap_port,
        "attivo": True,
        "cartelle": ["INBOX"],
        "parole_chiave": [],
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    if existing:
        # Aggiorna account esistente
        await db[COLLECTION_EMAIL_ACCOUNTS].update_one(
            {"email": config.email},
            {"$set": account_data}
        )
        message = "Account email aggiornato con successo"
    else:
        # Crea nuovo account
        account_data["created_at"] = datetime.now(timezone.utc).isoformat()
        await db[COLLECTION_EMAIL_ACCOUNTS].insert_one(account_data.copy())
        message = "Account email configurato con successo"
    
    # Aggiorna anche le variabili d'ambiente in memoria (per uso immediato)
    os.environ["EMAIL_USER"] = config.email
    os.environ["EMAIL_PASSWORD"] = config.password
    os.environ["EMAIL_ADDRESS"] = config.email
    os.environ["EMAIL_APP_PASSWORD"] = config.password
    os.environ["GMAIL_EMAIL"] = config.email
    os.environ["GMAIL_APP_PASSWORD"] = config.password
    
    return {
        "success": True,
        "message": message,
        "account": {
            "id": account_data["id"],
            "email": config.email,
            "imap_server": config.imap_server,
            "attivo": True
        }
    }


@router.get("/sync/email-status")
async def get_email_status() -> Dict[str, Any]:
    """
    Verifica lo stato della configurazione email.
    """
    db = Database.get_db()
    
    # Controlla variabili d'ambiente
    env_email = os.environ.get("EMAIL_USER") or os.environ.get("GMAIL_EMAIL")
    env_configured = bool(env_email)
    
    # Controlla database
    db_accounts = []
    if db is not None:
        accounts = await db[COLLECTION_EMAIL_ACCOUNTS].find(
            {"attivo": True},
            {"_id": 0, "app_password": 0}
        ).to_list(10)
        db_accounts = accounts
    
    return {
        "env_configured": env_configured,
        "env_email": env_email,
        "db_accounts_count": len(db_accounts),
        "db_accounts": db_accounts,
        "status": "configured" if (env_configured or db_accounts) else "not_configured"
    }


@router.post("/sync/test-email-connection")
async def test_email_connection(config: ConfiguraEmailRequest) -> Dict[str, Any]:
    """
    Testa la connessione IMAP con le credenziali fornite.
    """
    import imaplib
    
    try:
        # Connetti al server IMAP
        if config.imap_server == "imap.gmail.com":
            mail = imaplib.IMAP4_SSL(config.imap_server, config.imap_port)
        else:
            mail = imaplib.IMAP4_SSL(config.imap_server, config.imap_port)
        
        # Prova il login
        mail.login(config.email, config.password)
        
        # Lista le cartelle disponibili
        status, folders = mail.list()
        folder_count = len(folders) if status == "OK" else 0
        
        # Controlla INBOX
        mail.select("INBOX")
        status, messages = mail.search(None, "ALL")
        message_count = len(messages[0].split()) if status == "OK" and messages[0] else 0
        
        mail.logout()
        
        return {
            "success": True,
            "message": "Connessione riuscita",
            "details": {
                "server": config.imap_server,
                "email": config.email,
                "folders_count": folder_count,
                "inbox_messages": message_count
            }
        }
        
    except imaplib.IMAP4.error as e:
        raise HTTPException(
            status_code=400,
            detail=f"Errore autenticazione IMAP: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Errore connessione: {str(e)}"
        )
