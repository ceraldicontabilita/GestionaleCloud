"""OAuth Drive personale: grant offline cifrato, stato monouso e PKCE."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import secrets
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlparse

import httpx
from cryptography.fernet import Fernet
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

from app.config import settings

COLLECTION = "google_drive_oauth"
GRANT_ID = "authorized_user"
STATE_COLLECTION = "google_drive_oauth_states"
CALLBACK_PATH = "/api/auth/google/callback"
SCOPES = ["https://www.googleapis.com/auth/drive"]
TOKEN_URL = "https://oauth2.googleapis.com/token"
_cache = (0.0, None)


class DriveOAuthError(RuntimeError):
    pass


def _cipher():
    if not settings.SECRET_KEY:
        raise DriveOAuthError("Chiave del gestionale non configurata")
    key = hashlib.sha256(("drive-oauth-v1:" + settings.SECRET_KEY).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def seal(value):
    return _cipher().encrypt(value.encode()).decode()


def unseal(value):
    try:
        return _cipher().decrypt(value.encode()).decode()
    except Exception:
        raise DriveOAuthError("Autorizzazione cifrata non leggibile") from None


def client_fingerprint():
    return hashlib.sha256((settings.GOOGLE_CLIENT_ID or "").encode()).hexdigest()


def callback_uri():
    uri = settings.GOOGLE_REDIRECT_URI
    if uri.startswith("/"):
        uri = "https://impresasemplice.online" + uri
    parsed = urlparse(uri)
    if (
        parsed.scheme != "https"
        or parsed.netloc
        not in {"impresasemplice.online", "gestionalecloud.onrender.com"}
        or parsed.path != CALLBACK_PATH
        or parsed.query
        or parsed.fragment
    ):
        raise DriveOAuthError(
            "Callback OAuth non valido: configurare l'URI HTTPS del gestionale"
        )
    return uri


def invalidate_cache():
    global _cache
    _cache = (0.0, None)


def _read_grant_sync():
    global _cache
    if time.monotonic() - _cache[0] < 15:
        return _cache[1]
    if not (
        settings.SUPABASE_URL
        and settings.SUPABASE_PUBLISHABLE_KEY
        and settings.SUPABASE_RUNTIME_SECRET
    ):
        return None
    try:
        r = httpx.post(
            settings.SUPABASE_URL.rstrip("/") + "/rest/v1/rpc/gc_fetch_collection",
            headers={
                "apikey": settings.SUPABASE_PUBLISHABLE_KEY,
                "x-gc-api-key": settings.SUPABASE_RUNTIME_SECRET,
            },
            json={"p_collection": COLLECTION, "p_limit": 200, "p_offset": 0},
            timeout=15,
        )
        r.raise_for_status()
        grant = next((d for d in r.json() if d.get("id") == GRANT_ID), None)
        _cache = (time.monotonic(), grant)
        return grant
    except Exception:
        raise DriveOAuthError("Archivio autorizzazioni Drive non disponibile") from None


def credentials_from_grant(grant=None):
    if not (settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET):
        return None
    refresh = None
    if grant and grant.get("client_fingerprint") == client_fingerprint():
        refresh = unseal(grant["refresh_token_encrypted"])
    if not refresh:
        refresh = settings.GOOGLE_REFRESH_TOKEN
    if not refresh:
        return None
    return Credentials(
        token=None,
        refresh_token=refresh,
        token_uri=TOKEN_URL,
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        scopes=SCOPES,
    )


def load_credentials():
    if not (settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET):
        return None
    return credentials_from_grant(_read_grant_sync())


async def start_authorization(db, session_id):
    if not (settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET):
        raise DriveOAuthError("Client ID e client secret OAuth non configurati")
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(48)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )
    now = datetime.now(timezone.utc)
    await db[STATE_COLLECTION].insert_one(
        {
            "id": "state:" + hashlib.sha256(state.encode()).hexdigest(),
            "session_binding": hashlib.sha256(session_id.encode()).hexdigest(),
            "consumed": False,
            "expires_at": (now + timedelta(minutes=10)).isoformat(),
            "created_at": now.isoformat(),
            "verifier_encrypted": seal(verifier),
            "redirect_uri": callback_uri(),
            "client_fingerprint": client_fingerprint(),
        }
    )
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(
        {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "redirect_uri": callback_uri(),
            "response_type": "code",
            "scope": " ".join(SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )


async def consume_state(db, state, session_id):
    ident = "state:" + hashlib.sha256(state.encode()).hexdigest()
    async with db.transaction():
        doc = await db[STATE_COLLECTION].find_one({"id": ident})
        if (
            not doc
            or doc.get("consumed")
            or datetime.fromisoformat(doc["expires_at"]) <= datetime.now(timezone.utc)
            or doc["session_binding"] != hashlib.sha256(session_id.encode()).hexdigest()
            or doc.get("client_fingerprint") != client_fingerprint()
        ):
            raise DriveOAuthError(
                "Autorizzazione scaduta o sessione diversa: ripartire dal gestionale"
            )
        result = await db[STATE_COLLECTION].update_one(
            {"id": ident, "consumed": False},
            {"$set": {"consumed": True}, "$unset": {"verifier_encrypted": ""}},
        )
        if result.matched_count != 1:
            raise DriveOAuthError("Autorizzazione gia utilizzata")
    return doc


async def exchange_code(code, pending):
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                TOKEN_URL,
                data={
                    "code": code,
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "redirect_uri": pending["redirect_uri"],
                    "grant_type": "authorization_code",
                    "code_verifier": unseal(pending["verifier_encrypted"]),
                },
            )
        if r.status_code != 200:
            raise DriveOAuthError(
                "Google non ha confermato l'autorizzazione: ripetere il collegamento"
            )
        data = r.json()
        if not data.get("refresh_token") or not data.get("access_token"):
            raise DriveOAuthError(
                "Google non ha rilasciato l'autorizzazione offline: ripetere il consenso"
            )
        if SCOPES[0] not in str(data.get("scope") or "").split():
            raise DriveOAuthError("Permesso Google Drive non concesso")
        return data
    except DriveOAuthError:
        raise
    except Exception:
        raise DriveOAuthError(
            "Collegamento Google temporaneamente non disponibile"
        ) from None


def inspect_drive(creds):
    folder = settings.GOOGLE_DRIVE_DATI_FOLDER_ID
    if not folder:
        raise DriveOAuthError("Cartella Drive attuale non configurata")
    service = build("drive", "v3", credentials=creds, cache_discovery=False)
    try:
        meta = (
            service.files()
            .get(
                fileId=folder,
                fields="id,name,driveId,capabilities(canAddChildren)",
                supportsAllDrives=True,
            )
            .execute()
        )
        account = (
            service.about().get(fields="user(emailAddress),storageQuota").execute()
        )
        return {
            "cartella_id": meta["id"],
            "cartella_nome": meta.get("name"),
            "drive_personale": not bool(meta.get("driveId")),
            "puo_salvare": bool(meta.get("capabilities", {}).get("canAddChildren")),
            "account": account.get("user", {}).get("emailAddress"),
            "quota": account.get("storageQuota", {}),
        }
    except Exception:
        raise DriveOAuthError(
            "L'account Google non ha accesso verificato alla cartella Drive attuale"
        ) from None
    finally:
        service.close()


async def save_grant(db, tokens, info):
    grant = {
        "id": GRANT_ID,
        "client_fingerprint": client_fingerprint(),
        "refresh_token_encrypted": seal(tokens["refresh_token"]),
        "scopes": SCOPES,
        "account": info.get("account"),
        "cartella_verificata": info["cartella_id"],
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    await db[COLLECTION].update_one({"id": GRANT_ID}, {"$set": grant}, upsert=True)
    reread = await db[COLLECTION].find_one({"id": GRANT_ID})
    if (
        not reread
        or unseal(reread["refresh_token_encrypted"]) != tokens["refresh_token"]
    ):
        raise DriveOAuthError("Salvataggio dell'autorizzazione non confermato")
    invalidate_cache()
    return {
        "salvato": True,
        "cifrato": True,
        "riletto": True,
        "saved_at": grant["saved_at"],
    }


def write_probe(creds):
    service = build("drive", "v3", credentials=creds, cache_discovery=False)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    name = f"GESTIONALECLOUD_OAUTH_COLLAUDO_{stamp}_{secrets.token_hex(3)}.txt"
    content = (
        "Verifica OAuth Google Drive GestionaleCloud\n"
        + stamp
        + "\nNessun dato contabile.\n"
    ).encode()
    try:
        created = (
            service.files()
            .create(
                body={
                    "name": name,
                    "parents": [settings.GOOGLE_DRIVE_DATI_FOLDER_ID],
                    "appProperties": {"gestionale_oauth_collaudo": "true"},
                },
                media_body=MediaIoBaseUpload(
                    io.BytesIO(content), mimetype="text/plain"
                ),
                fields="id,name,webViewLink",
                supportsAllDrives=True,
            )
            .execute()
        )
        reread = (
            service.files()
            .get_media(fileId=created["id"], supportsAllDrives=True)
            .execute()
        )
        if reread != content:
            raise DriveOAuthError("File salvato ma rilettura non confermata")
        return {
            "salvato": True,
            "riletto": True,
            "file_id": created["id"],
            "nome": name,
            "url": created.get("webViewLink"),
            "sha256": hashlib.sha256(content).hexdigest(),
            "bytes": len(content),
        }
    except DriveOAuthError:
        raise
    except Exception:
        raise DriveOAuthError(
            "Google non ha confermato il salvataggio del file di collaudo: verificare permessi e quota"
        ) from None
    finally:
        service.close()
