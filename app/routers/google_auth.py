"""
Google OAuth Router - Emergent Auth Integration
Gestisce l'autenticazione tramite Google OAuth con Emergent Auth
"""
import httpx
import uuid
import os
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException, Response, Request, Cookie
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
from app.database import Database

router = APIRouter(prefix="/auth/google", tags=["Google OAuth"])

# Models
class SessionRequest(BaseModel):
    session_id: str

class UserResponse(BaseModel):
    user_id: str
    email: str
    name: str
    picture: Optional[str] = None

# Constants
EMERGENT_AUTH_URL = os.environ.get(
    "EMERGENT_AUTH_URL",
    "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data"
)
SESSION_EXPIRY_DAYS = 7

# --- WHITELIST EMAIL: solo questi indirizzi possono autenticarsi ---
# Configurabile via env ALLOWED_EMAILS="email1,email2"; case-insensitive.
_allowed_env = os.environ.get("ALLOWED_EMAILS", "ceraldigroupsrl@gmail.com")
ALLOWED_EMAILS = {e.strip().lower() for e in _allowed_env.split(",") if e.strip()}


@router.post("/session")
async def process_google_session(request: SessionRequest, response: Response):
    """
    Processa il session_id da Emergent Auth e crea una sessione locale.
    Frontend chiama questo endpoint dopo il redirect da Google OAuth.
    """
    db = Database.get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database non disponibile")
    
    try:
        # Chiama Emergent Auth per ottenere i dati utente
        async with httpx.AsyncClient() as client:
            auth_response = await client.get(
                EMERGENT_AUTH_URL,
                headers={"X-Session-ID": request.session_id},
                timeout=10.0
            )
        
        if auth_response.status_code != 200:
            raise HTTPException(
                status_code=401, 
                detail="Sessione Google non valida o scaduta"
            )
        
        user_data = auth_response.json()
        email = user_data.get("email")
        name = user_data.get("name", "")
        picture = user_data.get("picture", "")
        session_token = user_data.get("session_token")
        
        if not email or not session_token:
            raise HTTPException(status_code=400, detail="Dati utente incompleti")

        # --- WHITELIST: blocca email non autorizzate ---
        email_norm = email.strip().lower()
        if ALLOWED_EMAILS and email_norm not in ALLOWED_EMAILS:
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Accesso non autorizzato per {email}. "
                    "Questo gestionale è riservato. Contatta l'amministratore."
                )
            )

        # Cerca utente esistente o creane uno nuovo
        existing_user = await db.users.find_one({"email": email}, {"_id": 0})
        
        if existing_user:
            user_id = existing_user.get("user_id") or existing_user.get("id") or f"user_{uuid.uuid4().hex[:12]}"
            # Aggiorna i dati dell'utente
            await db.users.update_one(
                {"email": email},
                {"$set": {
                    "user_id": user_id,
                    "name": name or existing_user.get("name"),
                    "picture": picture,
                    "last_login": datetime.now(timezone.utc),
                    "auth_provider": "google"
                }}
            )
        else:
            # Crea nuovo utente
            user_id = f"user_{uuid.uuid4().hex[:12]}"
            await db.users.insert_one({
                "user_id": user_id,
                "email": email,
                "name": name,
                "picture": picture,
                "role": "user",
                "is_active": True,
                "auth_provider": "google",
                "created_at": datetime.now(timezone.utc),
                "last_login": datetime.now(timezone.utc)
            })
        
        # Salva la sessione
        expires_at = datetime.now(timezone.utc) + timedelta(days=SESSION_EXPIRY_DAYS)
        await db.user_sessions.update_one(
            {"user_id": user_id},
            {"$set": {
                "session_token": session_token,
                "expires_at": expires_at,
                "created_at": datetime.now(timezone.utc)
            }},
            upsert=True
        )
        
        # Imposta cookie httpOnly
        response.set_cookie(
            key="session_token",
            value=session_token,
            httponly=True,
            secure=True,
            samesite="none",
            path="/",
            max_age=SESSION_EXPIRY_DAYS * 24 * 60 * 60
        )
        
        return {
            "success": True,
            "user": {
                "user_id": user_id,
                "email": email,
                "name": name,
                "picture": picture
            }
        }
        
    except httpx.RequestError as e:
        raise HTTPException(status_code=503, detail=f"Errore comunicazione con auth server: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore interno: {str(e)}")


@router.get("/me")
async def get_current_google_user(
    request: Request,
    session_token: Optional[str] = Cookie(default=None)
):
    """
    Restituisce l'utente corrente basato sul session_token (cookie o header).
    """
    db = Database.get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database non disponibile")
    
    # Prova prima dal cookie, poi dall'header Authorization
    token = session_token
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    
    if not token:
        raise HTTPException(status_code=401, detail="Non autenticato")
    
    # Trova la sessione
    session_doc = await db.user_sessions.find_one(
        {"session_token": token},
        {"_id": 0}
    )
    
    if not session_doc:
        raise HTTPException(status_code=401, detail="Sessione non valida")
    
    # Verifica scadenza
    expires_at = session_doc.get("expires_at")
    if expires_at:
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=401, detail="Sessione scaduta")
    
    # Trova l'utente
    user_id = session_doc.get("user_id")
    user_doc = await db.users.find_one(
        {"$or": [{"user_id": user_id}, {"id": user_id}, {"email": user_id}]},
        {"_id": 0}
    )
    
    if not user_doc:
        raise HTTPException(status_code=404, detail="Utente non trovato")
    
    return {
        "user_id": user_doc.get("user_id") or user_doc.get("id"),
        "email": user_doc.get("email"),
        "name": user_doc.get("name"),
        "picture": user_doc.get("picture"),
        "role": user_doc.get("role", "user")
    }


@router.post("/logout")
async def google_logout(
    response: Response,
    request: Request,
    session_token: Optional[str] = Cookie(default=None)
):
    """
    Logout - elimina sessione e cookie.
    """
    db = Database.get_db()
    
    token = session_token
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    
    if token and db is not None:
        await db.user_sessions.delete_one({"session_token": token})
    
    # Cancella cookie
    response.delete_cookie(
        key="session_token",
        path="/",
        secure=True,
        samesite="none"
    )
    
    return {"success": True, "message": "Logout effettuato"}
