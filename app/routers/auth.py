"""
Auth Router — Ceraldi Group ERP
Verifica e chiusura della sessione (PyJWT, cookie httpOnly). L'ingresso e'
solo col PIN (`pin_login.py`, PIN amministratore unico `PIN_HASH_ADMIN` in
`app/services/admin_pin.py`): il vecchio login email + password e' stato
tolto, nessuna pagina lo usava piu'.
"""
import jwt
from fastapi import APIRouter, Response, Request, HTTPException
from dotenv import load_dotenv

from app.config import settings

load_dotenv()

router = APIRouter(prefix="/api", tags=["auth"])

# IMPORTANTE: STESSA chiave del middleware di autenticazione (settings.SECRET_KEY,
# che include il segreto condiviso in sistema_stato.auth_secret). Prima il login
# firmava con os.getenv("SECRET_KEY") o una chiave CASUALE per processo: se
# diversa da quella del middleware, OGNI chiamata API rispondeva 401
# ("Authentication required" su tutte le pagine).
SECRET_KEY          = settings.SECRET_KEY


async def _decode_token(request: Request) -> dict:
    """Decodifica il JWT da cookie o header Authorization. Ritorna il payload."""
    token = request.cookies.get("access_token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Non autenticato")

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="Sessione scaduta") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="Token non valido") from exc

    # Blacklist controllata SOLO dopo che firma/scadenza sono già valide
    # (review Codex su PR #65, stesso fix già fatto nel middleware globale
    # ma dimenticato qui: /api/auth/verify bypassa il middleware essendo
    # pubblico, quindi ha una propria copia dello stesso controllo).
    from app.database import Database
    from app.utils.token_blacklist import TokenBlacklistUnavailable, is_revocato
    try:
        revocato = await is_revocato(Database.get_db(), token)
    except TokenBlacklistUnavailable as exc:
        raise HTTPException(
            status_code=503, detail="Verifica sessione temporaneamente non disponibile"
        ) from exc
    if revocato:
        raise HTTPException(status_code=401, detail="Sessione terminata (logout)")

    return payload


async def verify_token(request: Request) -> str:
    """Verifica JWT da cookie o header Authorization. Ritorna email utente."""
    payload = await _decode_token(request)
    return payload["sub"]


# NB: gli alias legacy /api/login, /api/logout, /api/me sono stati rimossi
# (audit lug 2026): il frontend usa /api/auth/pin-login (pin_login.py),
# /api/auth/logout e /api/auth/verify definiti qui sotto.


@router.get("/auth/verify")
async def verify(request: Request):
    """Compatibilità AuthContext frontend: verifica sessione attiva."""
    from app.utils.ruoli import normalizza_ruolo, RUOLI_VALIDI
    payload = await _decode_token(request)
    email = payload["sub"]
    ruolo = normalizza_ruolo(payload.get("role"))
    if ruolo not in RUOLI_VALIDI:
        raise HTTPException(status_code=403, detail="Ruolo utente non valido")
    from app.database import Database
    from app.services.mfa_service import canonical_identity, get_status
    mfa = await get_status(Database.get_db(), canonical_identity(email, email, ruolo))
    mfa["verified_in_session"] = bool(payload.get("mfa_verified"))
    return {
        "ok":    True,
        "user":  {
            "email": email,
            "name": payload.get("name", "Admin"),
            "role": ruolo,
            "auth_method": payload.get("auth_method"),
            "mfa_enabled": mfa["enabled"],
            "mfa_verified": mfa["verified_in_session"],
        },
        "email": email,
        "mfa": mfa,
    }


@router.post("/auth/logout")
async def auth_logout(request: Request, response: Response):
    """Alias /api/auth/logout. Revoca il token lato server (audit 19/07/2026:
    prima il logout cancellava solo i cookie, un token rubato restava valido
    fino a scadenza naturale)."""
    # Il frontend manda SEMPRE il bearer da localStorage (interceptor axios)
    # E il browser manda il cookie in automatico: normalmente coincidono, ma
    # la sessione scorrevole può rinnovarli in momenti diversi. Revoca
    # ENTRAMBI se presenti e diversi — prima si sceglieva solo il cookie e
    # un bearer copiato/divergente restava valido fino a scadenza (review
    # Codex su PR #65).
    token_cookie = request.cookies.get("access_token")
    token_bearer = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token_bearer = auth_header[7:]

    for token in {t for t in (token_cookie, token_bearer) if t}:
        from app.database import Database
        from app.utils.token_blacklist import revoca_token
        try:
            # verify_exp=False: un token scaduto ma firmato correttamente va
            # comunque revocato (con la sua scadenza reale per il TTL).
            # Un token con firma non valida/malformato NON va in blacklist:
            # /api/auth/logout è pubblico, altrimenti chiunque potrebbe
            # riempire token_blacklist con hash spazzatura senza scadenza
            # (review Codex su PR #65).
            payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"], options={"verify_exp": False})
            exp = payload.get("exp")
        except jwt.InvalidTokenError:
            continue
        try:
            await revoca_token(Database.get_db(), token, exp=exp)
            # HR, Lotti e Menu hanno token propri nati da questa sessione e
            # ne portano la chiave: revocarla li chiude tutti. La registrazione
            # dura quanto il token derivato piu' lungo (HR, 7 giorni) piu'
            # margine, perche' la sessione sopravvive al singolo token ERP.
            import time as _time
            from app.services.group_session import segna_revocata
            from app.utils.token_blacklist import chiave_sessione, revoca_chiave
            chiave = chiave_sessione(payload, token)
            if chiave.startswith("sid:"):
                await revoca_chiave(Database.get_db(), chiave, exp=_time.time() + 8 * 86400)
            segna_revocata(chiave)
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail="Logout sicuro temporaneamente non disponibile: riprovare",
            ) from exc
    from app.utils.session_cookie import SESSION_COOKIE_SECURE
    response.delete_cookie("access_token", path="/", secure=SESSION_COOKIE_SECURE, samesite="lax")
    response.delete_cookie("session_active", path="/", secure=SESSION_COOKIE_SECURE, samesite="lax")
    return {"ok": True}
