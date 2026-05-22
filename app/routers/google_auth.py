"""
Google OAuth Router - versione Render (senza Emergent Auth)
L'endpoint /auth/google/session è disabilitato su Render.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/auth/google", tags=["Google OAuth"])

class SessionRequest(BaseModel):
    session_id: str

@router.post("/session")
async def process_google_session(request: SessionRequest):
    """Google OAuth via Emergent non disponibile su Render. Usa il login email/password."""
    raise HTTPException(status_code=503, detail="Google OAuth non disponibile in questa configurazione. Usa login email/password.")

@router.get("/status")
async def google_auth_status():
    return {"enabled": False, "message": "Usa login email/password"}
