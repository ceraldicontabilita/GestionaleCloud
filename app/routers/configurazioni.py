"""
Router Configurazioni Sistema - Email, Parole Chiave, etc.
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
from datetime import datetime, timezone
import uuid
import os

from app.database import Database

router = APIRouter()

COLLECTION_CONFIG = "system_config"
COLLECTION_EMAIL_ACCOUNTS = "email_accounts"


# =============================================================================
# MODELLI
# =============================================================================

class EmailAccountInput(BaseModel):
    """Account email configurabile"""
    nome: str  # Nome descrittivo (es. "Email Principale", "Commercialista")
    email: str
    app_password: str
    imap_server: str = "imap.gmail.com"
    imap_port: int = 993
    attivo: bool = True
    parole_chiave: List[str] = []  # Parole chiave per filtrare email
    cartelle: List[str] = ["INBOX"]  # Cartelle da scansionare
    note: Optional[str] = None


class EmailAccountUpdate(BaseModel):
    """Update account email"""
    nome: Optional[str] = None
    email: Optional[str] = None
    app_password: Optional[str] = None
    imap_server: Optional[str] = None
    imap_port: Optional[int] = None
    attivo: Optional[bool] = None
    parole_chiave: Optional[List[str]] = None
    cartelle: Optional[List[str]] = None
    note: Optional[str] = None


class ParolaChiaveInput(BaseModel):
    """Parola chiave per filtro email"""
    parola: str
    categoria: str = "generale"  # generale, fatture, f24, buste_paga
    attiva: bool = True


# =============================================================================
# ENDPOINT EMAIL ACCOUNTS
# =============================================================================

@router.get("/email-accounts")
async def get_email_accounts() -> List[Dict[str, Any]]:
    """
    Lista tutti gli account email configurati.
    Le password vengono mascherate per sicurezza.
    """
    db = Database.get_db()
    
    accounts = await db[COLLECTION_EMAIL_ACCOUNTS].find(
        {},
        {"_id": 0}
    ).to_list(100)
    
    # Maschera le password - RIMUOVI password reale dalla response
    for acc in accounts:
        if acc.get("app_password"):
            acc["app_password_masked"] = "****" + acc["app_password"][-4:] if len(acc["app_password"]) > 4 else "****"
            del acc["app_password"]  # Mai restituire la password reale
    
    # Se non ci sono account, crea quello di default dalle variabili d'ambiente
    if not accounts:
        env_email = os.environ.get("EMAIL_USER") or os.environ.get("EMAIL_ADDRESS")
        env_password = os.environ.get("EMAIL_APP_PASSWORD") or os.environ.get("EMAIL_PASSWORD")
        
        if env_email and env_password:
            default_account = {
                "id": str(uuid.uuid4()),
                "nome": "Email Principale (da .env)",
                "email": env_email,
                "app_password": env_password,
                "app_password_masked": "****" + env_password[-4:] if len(env_password) > 4 else "****",
                "imap_server": "imap.gmail.com",
                "imap_port": 993,
                "attivo": True,
                "parole_chiave": ["fattura", "F24", "cedolino", "busta paga", "pagamento"],
                "cartelle": ["INBOX"],
                "is_env_default": True,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            await db[COLLECTION_EMAIL_ACCOUNTS].insert_one(default_account.copy())
            # Rimuovi _id per la risposta
            default_account.pop("_id", None)
            default_account.pop("app_password", None)  # Mai restituire password
            accounts = [default_account]
    
    return accounts


@router.post("/email-accounts")
async def create_email_account(account: EmailAccountInput) -> Dict[str, Any]:
    """Crea un nuovo account email."""
    db = Database.get_db()
    
    # Verifica che l'email non sia già configurata
    existing = await db[COLLECTION_EMAIL_ACCOUNTS].find_one({"email": account.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email già configurata")
    
    account_data = account.model_dump()
    account_data["id"] = str(uuid.uuid4())
    account_data["created_at"] = datetime.now(timezone.utc).isoformat()
    account_data["is_env_default"] = False
    
    await db[COLLECTION_EMAIL_ACCOUNTS].insert_one(account_data.copy())
    
    # Rimuovi _id per la risposta
    account_data.pop("_id", None)
    account_data["app_password_masked"] = "****" + account.app_password[-4:]
    
    return {"success": True, "account": account_data}


@router.put("/email-accounts/{account_id}")
async def update_email_account(account_id: str, update: EmailAccountUpdate) -> Dict[str, Any]:
    """Aggiorna un account email esistente."""
    db = Database.get_db()
    
    # Verifica che l'account esista
    existing = await db[COLLECTION_EMAIL_ACCOUNTS].find_one({"id": account_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Account non trovato")
    
    # Prepara i campi da aggiornare
    update_data = {k: v for k, v in update.model_dump(exclude_unset=True).items() if v is not None}
    
    if not update_data:
        return {"success": True, "message": "Nessun campo da aggiornare"}
    
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    # Se è l'account di default da .env, aggiorna anche le variabili d'ambiente nel file
    # (Nota: in produzione questo non funzionerà, solo per sviluppo)
    
    await db[COLLECTION_EMAIL_ACCOUNTS].update_one(
        {"id": account_id},
        {"$set": update_data}
    )
    
    return {"success": True, "message": "Account aggiornato", "updated_fields": list(update_data.keys())}


@router.delete("/email-accounts/{account_id}")
async def delete_email_account(account_id: str) -> Dict[str, Any]:
    """Elimina un account email."""
    db = Database.get_db()
    
    # Verifica che l'account esista
    existing = await db[COLLECTION_EMAIL_ACCOUNTS].find_one({"id": account_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Account non trovato")
    
    # Non permettere l'eliminazione dell'account di default
    if existing.get("is_env_default"):
        raise HTTPException(status_code=400, detail="Non puoi eliminare l'account di default")
    
    await db[COLLECTION_EMAIL_ACCOUNTS].delete_one({"id": account_id})
    
    return {"success": True, "message": "Account eliminato"}


# =============================================================================
# ENDPOINT PAROLE CHIAVE GLOBALI
# =============================================================================

@router.get("/parole-chiave")
async def get_parole_chiave() -> Dict[str, Any]:
    """Lista tutte le parole chiave configurate."""
    db = Database.get_db()
    
    config = await db[COLLECTION_CONFIG].find_one(
        {"tipo": "parole_chiave"},
        {"_id": 0}
    )
    
    if not config:
        # Crea configurazione di default
        default_keywords = {
            "tipo": "parole_chiave",
            "generale": ["fattura", "pagamento", "bonifico", "ricevuta"],
            "fatture": ["fattura", "fatt.", "invoice", "ft.", "documento fiscale"],
            "f24": ["F24", "quietanza", "agenzia entrate", "tributo", "modello f24"],
            "buste_paga": ["cedolino", "busta paga", "stipendio", "LUL", "libro unico"],
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db[COLLECTION_CONFIG].insert_one(default_keywords.copy())
        # Rimuovi _id per la risposta
        default_keywords.pop("_id", None)
        config = default_keywords
    
    return config


@router.put("/parole-chiave")
async def update_parole_chiave(
    categoria: str = Query(..., description="Categoria: generale, fatture, f24, buste_paga"),
    parole: List[str] = Query(..., description="Lista parole chiave")
) -> Dict[str, Any]:
    """Aggiorna le parole chiave per una categoria."""
    db = Database.get_db()
    
    categorie_valide = ["generale", "fatture", "f24", "buste_paga"]
    if categoria not in categorie_valide:
        raise HTTPException(status_code=400, detail=f"Categoria non valida. Usa: {categorie_valide}")
    
    await db[COLLECTION_CONFIG].update_one(
        {"tipo": "parole_chiave"},
        {
            "$set": {
                categoria: parole,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        },
        upsert=True
    )
    
    return {"success": True, "categoria": categoria, "parole": parole}


@router.post("/parole-chiave/aggiungi")
async def aggiungi_parola_chiave(
    categoria: str = Query(...),
    parola: str = Query(...)
) -> Dict[str, Any]:
    """Aggiunge una singola parola chiave a una categoria."""
    db = Database.get_db()
    
    await db[COLLECTION_CONFIG].update_one(
        {"tipo": "parole_chiave"},
        {
            "$addToSet": {categoria: parola},
            "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}
        },
        upsert=True
    )
    
    return {"success": True, "message": f"Parola '{parola}' aggiunta a {categoria}"}


@router.delete("/parole-chiave/rimuovi")
async def rimuovi_parola_chiave(
    categoria: str = Query(...),
    parola: str = Query(...)
) -> Dict[str, Any]:
    """Rimuove una parola chiave da una categoria."""
    db = Database.get_db()
    
    await db[COLLECTION_CONFIG].update_one(
        {"tipo": "parole_chiave"},
        {
            "$pull": {categoria: parola},
            "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}
        }
    )
    
    return {"success": True, "message": f"Parola '{parola}' rimossa da {categoria}"}


# =============================================================================
# ENDPOINT TEST CONNESSIONE EMAIL
# =============================================================================

@router.post("/email-accounts/{account_id}/test")
async def test_email_connection(account_id: str) -> Dict[str, Any]:
    """Testa la connessione a un account email."""
    import imaplib
    
    db = Database.get_db()
    
    account = await db[COLLECTION_EMAIL_ACCOUNTS].find_one({"id": account_id}, {"_id": 0})
    if not account:
        raise HTTPException(status_code=404, detail="Account non trovato")
    
    try:
        # Connessione IMAP
        mail = imaplib.IMAP4_SSL(account["imap_server"], account["imap_port"])
        mail.login(account["email"], account["app_password"])
        
        # Conta email nella inbox
        mail.select("INBOX")
        _, messages = mail.search(None, "ALL")
        email_count = len(messages[0].split()) if messages[0] else 0
        
        mail.logout()
        
        return {
            "success": True,
            "message": "Connessione riuscita!",
            "email": account["email"],
            "email_count": email_count
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Errore connessione: {str(e)}",
            "email": account["email"]
        }
