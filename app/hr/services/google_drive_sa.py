"""Download PDF da una cartella Google Drive via service account.

Punto unico riusato da più flussi di import (Documenti, Buste Paga): un solo
posto che sa autenticarsi con Google e scaricare i file, per non duplicare
la stessa logica OAuth in più router.

Credenziali: SOLO nelle env di Render, mai nel codice/chat. Nomi accettati
(stessi del GestionaleCloud, per poter riusare l'Environment Group senza
rinominare nulla): GOOGLE_SERVICE_ACCOUNT_JSON, GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON,
GOOGLE_DRIVE_SA_JSON.
"""
import json
import os
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import HTTPException
from jose import jwt as jose_jwt


def _leggi_credenziali() -> Dict[str, Any]:
    creds_raw = (os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
                 or os.environ.get("GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON")
                 or os.environ.get("GOOGLE_DRIVE_SA_JSON") or "")
    if not creds_raw:
        raise HTTPException(status_code=503, detail=(
            "Manca la chiave del service account nelle env di Render: variabile "
            "GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON (stesso nome del GestionaleCloud) "
            "o GOOGLE_SERVICE_ACCOUNT_JSON — mai in codice o chat."))
    try:
        creds = json.loads(creds_raw)
    except ValueError:
        # Tollera il formato "export .env": a capo scritti come \n letterali e
        # virgolette con la barra (\"), come nel dump del GestionaleCloud.
        try:
            riparato = (creds_raw.strip().strip('"').strip("'")
                        .replace("\\\\n", "\x00").replace("\\n", "\n")
                        .replace("\x00", "\\n").replace('\\"', '"'))
            creds = json.loads(riparato)
        except ValueError:
            raise HTTPException(status_code=503,
                                detail="La chiave del service account non è un JSON valido: ricopiala intera dal pannello")
    if isinstance(creds, str):
        try:
            creds = json.loads(creds)
        except ValueError:
            raise HTTPException(status_code=503,
                                detail="La chiave del service account non è un JSON valido: togli le virgolette esterne")
    if not isinstance(creds, dict) or not creds.get("client_email") or not creds.get("private_key"):
        raise HTTPException(status_code=503,
                            detail="La chiave del service account è incompleta (mancano client_email/private_key)")
    return creds


async def _token(creds: Dict[str, Any], client: httpx.AsyncClient) -> str:
    now = int(time.time())
    assertion = jose_jwt.encode(
        {"iss": creds["client_email"], "scope": "https://www.googleapis.com/auth/drive.readonly",
         "aud": "https://oauth2.googleapis.com/token", "iat": now, "exp": now + 3600},
        creds["private_key"], algorithm="RS256")
    tok = await client.post("https://oauth2.googleapis.com/token", data={
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion})
    if tok.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Autenticazione Google fallita: {tok.text[:200]}")
    return tok.json()["access_token"]


async def elenca_pdf_cartella(folder_id: str, sottocartelle: bool = True,
                              max_pdf: int = 1000) -> List[Dict[str, Any]]:
    """Elenca i PDF di una cartella (e delle sue sottocartelle dirette),
    senza scaricarli. Ritorna [{id, name}, ...]."""
    creds = _leggi_credenziali()
    async with httpx.AsyncClient(timeout=120) as client:
        access = await _token(creds, client)
        headers = {"Authorization": f"Bearer {access}"}

        async def lista(fid: str) -> List[Dict[str, Any]]:
            out, page = [], None
            while True:
                params = {"q": f"'{fid}' in parents and trashed=false",
                          "fields": "nextPageToken,files(id,name,mimeType)", "pageSize": 200,
                          "supportsAllDrives": "true", "includeItemsFromAllDrives": "true"}
                if page:
                    params["pageToken"] = page
                r = await client.get("https://www.googleapis.com/drive/v3/files", params=params, headers=headers)
                r.raise_for_status()
                j = r.json()
                out += j.get("files", [])
                page = j.get("nextPageToken")
                if not page:
                    return out

        files = await lista(folder_id)
        pdfs = [f for f in files if f.get("mimeType") == "application/pdf"]
        if sottocartelle:
            for sub in [f for f in files if f.get("mimeType") == "application/vnd.google-apps.folder"]:
                pdfs += [f for f in await lista(sub["id"]) if f.get("mimeType") == "application/pdf"]
        return pdfs[:max_pdf]


async def scarica_pdf_cartella(folder_id: str, sottocartelle: bool = True,
                               max_pdf: int = 500) -> Tuple[List[Tuple[str, bytes]], List[str]]:
    """Autentica col service account, scarica tutti i PDF di una cartella Drive
    (e sottocartelle dirette). Ritorna ([(nome, bytes), ...], [nomi_falliti])."""
    creds = _leggi_credenziali()
    scaricati: List[Tuple[str, bytes]] = []
    falliti: List[str] = []
    async with httpx.AsyncClient(timeout=120) as client:
        access = await _token(creds, client)
        headers = {"Authorization": f"Bearer {access}"}

        async def lista(fid: str) -> List[Dict[str, Any]]:
            out, page = [], None
            while True:
                params = {"q": f"'{fid}' in parents and trashed=false",
                          "fields": "nextPageToken,files(id,name,mimeType)", "pageSize": 200,
                          "supportsAllDrives": "true", "includeItemsFromAllDrives": "true"}
                if page:
                    params["pageToken"] = page
                r = await client.get("https://www.googleapis.com/drive/v3/files", params=params, headers=headers)
                r.raise_for_status()
                j = r.json()
                out += j.get("files", [])
                page = j.get("nextPageToken")
                if not page:
                    return out

        files = await lista(folder_id)
        pdfs = [f for f in files if f.get("mimeType") == "application/pdf"]
        if sottocartelle:
            for sub in [f for f in files if f.get("mimeType") == "application/vnd.google-apps.folder"]:
                pdfs += [f for f in await lista(sub["id"]) if f.get("mimeType") == "application/pdf"]

        for f in pdfs[:max_pdf]:
            r = await client.get(f"https://www.googleapis.com/drive/v3/files/{f['id']}",
                                 params={"alt": "media", "supportsAllDrives": "true"}, headers=headers)
            if r.status_code == 200:
                scaricati.append((f.get("name") or f["id"], r.content))
            else:
                falliti.append(f.get("name") or f["id"])
    return scaricati, falliti


async def scarica_per_id(file_ids: List[str]) -> Tuple[List[Tuple[str, str, bytes]], List[str]]:
    """Scarica SOLO i file Drive indicati (per id), non l'intera cartella: usato per
    processare una cartella grande a lotti, un click = un lotto, invece di scaricare
    tutto in una sola richiesta HTTP che altrimenti va in timeout (visto in produzione:
    573 secondi e 502 con una cartella di centinaia di PDF). Ritorna
    ([(id, nome, bytes), ...], [id_falliti])."""
    if not file_ids:
        return [], []
    creds = _leggi_credenziali()
    scaricati: List[Tuple[str, str, bytes]] = []
    falliti: List[str] = []
    async with httpx.AsyncClient(timeout=120) as client:
        access = await _token(creds, client)
        headers = {"Authorization": f"Bearer {access}"}
        for fid in file_ids:
            try:
                meta = await client.get(f"https://www.googleapis.com/drive/v3/files/{fid}",
                                        params={"fields": "name", "supportsAllDrives": "true"}, headers=headers)
                nome = meta.json().get("name", fid) if meta.status_code == 200 else fid
                r = await client.get(f"https://www.googleapis.com/drive/v3/files/{fid}",
                                     params={"alt": "media", "supportsAllDrives": "true"}, headers=headers)
                if r.status_code == 200:
                    scaricati.append((fid, nome, r.content))
                else:
                    falliti.append(fid)
            except Exception:
                falliti.append(fid)
    return scaricati, falliti


def cartella_cedolini_default() -> str:
    return os.environ.get("DRIVE_CEDOLINI_FOLDER_ID") or "1XVdbMzz145N5p8jn4XXSt8YkYtsPOT15"
