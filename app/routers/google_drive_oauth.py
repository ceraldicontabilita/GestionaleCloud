"""Collegamento Drive personale riservato all'amministratore del gestionale."""

import hashlib
import html

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from google.oauth2.credentials import Credentials
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.database import Database
from app.services import drive_oauth as oauth
from app.services.supabase_runtime_database import ConcurrentDocumentChange
from app.utils.dependencies import get_current_admin_user

router = APIRouter(prefix="/api/auth/google", tags=["Google Drive OAuth"])
PRIVATE = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}


def session_id(request):
    ident = getattr(request.state, "session_id", None)
    if not ident:
        token = request.cookies.get("access_token") or request.headers.get(
            "Authorization", ""
        )
        if not token:
            raise HTTPException(401, "Accedere prima al gestionale")
        ident = hashlib.sha256(token.encode()).hexdigest()
    return str(ident)


async def status_data(db):
    grant = await db[oauth.COLLECTION].find_one({"id": oauth.GRANT_ID})
    matching = bool(
        grant and grant.get("client_fingerprint") == oauth.client_fingerprint()
    )
    return {
        "client_id_configurato": bool(settings.GOOGLE_CLIENT_ID),
        "client_secret_configurato": bool(settings.GOOGLE_CLIENT_SECRET),
        "redirect_uri": oauth.callback_uri(),
        "refresh_token_configurato": bool(settings.GOOGLE_REFRESH_TOKEN),
        "autorizzazione_salvata": matching,
        "salvataggio_cifrato": matching,
        "account": grant.get("account") if matching else None,
        "cartella_attuale": settings.GOOGLE_DRIVE_DATI_FOLDER_ID,
        "ultimo_collaudo": grant.get("ultimo_collaudo") if matching else None,
        "saved_at": grant.get("saved_at") if matching else None,
    }


@router.get("/status")
async def status(_admin=Depends(get_current_admin_user)):
    try:
        return JSONResponse(await status_data(Database.get_db()), headers=PRIVATE)
    except oauth.DriveOAuthError as exc:
        raise HTTPException(503, str(exc)) from None


@router.get("/drive", response_class=HTMLResponse)
async def panel(_admin=Depends(get_current_admin_user)):
    try:
        data = await status_data(Database.get_db())
    except oauth.DriveOAuthError as exc:
        raise HTTPException(503, str(exc)) from None
    ready = data["client_id_configurato"] and data["client_secret_configurato"]
    message = (
        "Client OAuth configurato"
        if ready
        else "Client ID o client secret non configurati sul servizio"
    )
    connected = (
        "Autorizzazione salvata e cifrata"
        if data["autorizzazione_salvata"]
        else "Account Google da autorizzare"
    )
    return HTMLResponse(
        """<!doctype html><html lang="it"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>Collegamento Google Drive</title><style>body{font:17px system-ui;max-width:760px;margin:40px auto;padding:20px;line-height:1.6}a,button{display:inline-block;padding:14px;border-radius:8px;margin:8px 0;font:inherit}button{cursor:pointer}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style>
    <h1>Google Drive personale</h1><p>"""
        + html.escape(message)
        + " · "
        + html.escape(connected)
        + """</p>
    <p>Il collegamento usa la cartella attuale e salva l'autorizzazione cifrata nel gestionale.</p>
    <p>Callback da autorizzare nel client Google: <code>"""
        + html.escape(data["redirect_uri"])
        + """</code></p>
    <p><a href="/api/auth/google/connect">Collega il tuo account Google</a></p>
    <p>Il collaudo crea un piccolo file di testo riconoscibile nella cartella attuale e lo rilegge per verificarlo.</p>
    <button id="verify">Verifica accesso e salvataggio</button><pre id="result" aria-live="polite"></pre>
    <p><a href="/">Torna al gestionale</a></p><script>
    document.getElementById('verify').onclick=async()=>{const b=document.getElementById('verify');b.disabled=true;
    const p=document.getElementById('result');p.textContent='Verifica in corso...';try{const r=await fetch('/api/auth/google/verify',{method:'POST',credentials:'same-origin'});p.textContent=JSON.stringify(await r.json(),null,2)}catch(e){p.textContent='Verifica non completata: riprovare'}finally{b.disabled=false}};
    </script></html>""",
        headers=PRIVATE,
    )


@router.get("/connect")
async def connect(request: Request, _admin=Depends(get_current_admin_user)):
    try:
        uri = oauth.callback_uri()
        # Il cookie ERP deve tornare sul medesimo host del callback.
        from urllib.parse import urlparse

        if request.url.hostname != urlparse(uri).hostname:
            return RedirectResponse(
                uri.replace(oauth.CALLBACK_PATH, "/api/auth/google/drive"),
                headers=PRIVATE,
            )
        url = await oauth.start_authorization(Database.get_db(), session_id(request))
        return RedirectResponse(url, status_code=303, headers=PRIVATE)
    except oauth.DriveOAuthError as exc:
        raise HTTPException(503, str(exc)) from None


@router.get("/callback")
async def callback(request: Request, _admin=Depends(get_current_admin_user)):
    state = request.query_params.get("state") or ""
    code = request.query_params.get("code") or ""
    try:
        if not state:
            raise oauth.DriveOAuthError(
                "Risposta Google senza stato: ripartire dal gestionale"
            )
        pending = await oauth.consume_state(
            Database.get_db(), state, session_id(request)
        )
        if request.query_params.get("error") or not code:
            raise oauth.DriveOAuthError("Autorizzazione Google non completata")
        tokens = await oauth.exchange_code(code, pending)
        creds = Credentials(
            token=tokens["access_token"],
            refresh_token=tokens["refresh_token"],
            token_uri=oauth.TOKEN_URL,
            client_id=settings.GOOGLE_CLIENT_ID,
            client_secret=settings.GOOGLE_CLIENT_SECRET,
            scopes=oauth.SCOPES,
        )
        info = await run_in_threadpool(oauth.inspect_drive, creds)
        await oauth.save_grant(Database.get_db(), tokens, info)
        # Il browser lascia subito l'URL che conteneva il codice monouso.
        return RedirectResponse(
            "/api/auth/google/drive", status_code=303, headers=PRIVATE
        )
    except (oauth.DriveOAuthError, ConcurrentDocumentChange) as exc:
        text = (
            str(exc)
            if isinstance(exc, oauth.DriveOAuthError)
            else "Autorizzazione gia utilizzata: ripartire dal gestionale"
        )
        return HTMLResponse(
            "<h1>Collegamento Google Drive</h1><p>"
            + html.escape(text)
            + '</p><a href="/api/auth/google/drive">Torna al collegamento</a>',
            status_code=400,
            headers=PRIVATE,
        )


@router.post("/verify")
async def verify(_admin=Depends(get_current_admin_user)):
    try:
        db = Database.get_db()
        grant = await db[oauth.COLLECTION].find_one({"id": oauth.GRANT_ID})
        creds = oauth.credentials_from_grant(grant)
        if creds is None:
            raise oauth.DriveOAuthError(
                "Autorizzazione Google mancante: collegare prima l'account"
            )
        info = await run_in_threadpool(oauth.inspect_drive, creds)
        if not info["puo_salvare"]:
            raise oauth.DriveOAuthError(
                "L'account Google non puo aggiungere file nella cartella attuale"
            )
        probe = await run_in_threadpool(oauth.write_probe, creds)
        if grant:
            await db[oauth.COLLECTION].update_one(
                {"id": oauth.GRANT_ID}, {"$set": {"ultimo_collaudo": probe}}
            )
        return JSONResponse(
            {
                "success": True,
                "autenticazione": "oauth_account_personale",
                "accesso": info,
                "salvataggio": probe,
            },
            headers=PRIVATE,
        )
    except oauth.DriveOAuthError as exc:
        raise HTTPException(409, str(exc)) from None
