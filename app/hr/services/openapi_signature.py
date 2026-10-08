"""
Client OpenAPI.com — firma elettronica, marca temporale e PEC.

Copre il flusso di firma del contratto di assunzione:
  1. Marca Temporale  -> data e ora certa sul PDF.
  2. eSignature (FES con OTP) -> firma del dipendente per accettazione (eIDAS).
  3. PEC               -> invio del contratto firmato con ricevuta a data certa.

Autenticazione: OAuth V2 di OpenAPI (client credentials). Le credenziali e gli
endpoint provengono ESCLUSIVAMENTE dalle variabili d'ambiente di Render:

  OPENAPI_CLIENT_ID       (obbligatoria)
  OPENAPI_CLIENT_SECRET   (obbligatoria)
  OPENAPI_ENV             "sandbox" (default) | "production"

URL configurabili (hanno default sensati; vanno verificati su console.openapi.com):
  OPENAPI_OAUTH_URL       default https://oauth.openapi.it/token
  OPENAPI_ESIGN_BASE      default https://esignature.openapi.it
  OPENAPI_TIMESTAMP_BASE  default https://timestamp.openapi.it
  OPENAPI_PEC_BASE        default https://pec.openapi.it

NOTA: i payload esatti di ogni prodotto vanno validati contro la documentazione
ufficiale (console.openapi.com -> eSignature / PEC / Marche Temporali / OAuth V2)
e testati in sandbox prima della produzione. I metodi sono isolati apposta per
poterli adeguare senza toccare il resto del modulo contratti.
"""
from __future__ import annotations

import os
import time
import base64
import logging
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


class OpenAPIConfigError(RuntimeError):
    """Configurazione OpenAPI mancante o incompleta (credenziali in env)."""


class OpenAPIError(RuntimeError):
    """Errore restituito da un servizio OpenAPI."""


class OpenAPISignatureClient:
    """Client minimale e riusabile per i prodotti OpenAPI di firma/PEC.

    Un'unica istanza gestisce la cache del token OAuth per insieme di scope.
    """

    def __init__(self) -> None:
        self.client_id = _env("OPENAPI_CLIENT_ID")
        self.client_secret = _env("OPENAPI_CLIENT_SECRET")
        self.environment = _env("OPENAPI_ENV", "sandbox").lower()
        self.oauth_url = _env("OPENAPI_OAUTH_URL", "https://oauth.openapi.it/token")
        self.esign_base = _env("OPENAPI_ESIGN_BASE", "https://esignature.openapi.it").rstrip("/")
        self.timestamp_base = _env("OPENAPI_TIMESTAMP_BASE", "https://timestamp.openapi.it").rstrip("/")
        self.pec_base = _env("OPENAPI_PEC_BASE", "https://pec.openapi.it").rstrip("/")
        # cache token: {scope_key: (token, expire_epoch)}
        self._token_cache: Dict[str, tuple[str, float]] = {}

    # --- configurazione ----------------------------------------------------
    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def _require_config(self) -> None:
        if not self.configured:
            raise OpenAPIConfigError(
                "OpenAPI non configurato: imposta OPENAPI_CLIENT_ID e "
                "OPENAPI_CLIENT_SECRET nelle variabili d'ambiente di Render."
            )

    # --- OAuth V2 ----------------------------------------------------------
    async def _get_token(self, scopes: List[str]) -> str:
        """Ottiene (o riusa dalla cache) un Bearer token per gli scope richiesti."""
        self._require_config()
        key = ",".join(sorted(scopes))
        cached = self._token_cache.get(key)
        now = time.time()
        if cached and cached[1] - 30 > now:
            return cached[0]

        payload = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scopes": scopes,
        }
        async with httpx.AsyncClient(timeout=30) as http:
            resp = await http.post(self.oauth_url, json=payload)
        if resp.status_code >= 400:
            raise OpenAPIError(f"OAuth fallito ({resp.status_code}): {resp.text[:300]}")
        data = resp.json()
        token = data.get("token") or data.get("access_token")
        if not token:
            raise OpenAPIError(f"OAuth: token assente nella risposta: {data}")
        # 'expire' può essere epoch o secondi-di-validità a seconda del prodotto
        expire = data.get("expire") or data.get("expires_at")
        if isinstance(expire, (int, float)) and expire > now:
            exp_epoch = float(expire)
        else:
            exp_epoch = now + float(data.get("expires_in", 3600))
        self._token_cache[key] = (token, exp_epoch)
        return token

    async def _request(self, method: str, url: str, scopes: List[str],
                       *, json_body: Optional[dict] = None,
                       files: Optional[dict] = None) -> dict:
        token = await self._get_token(scopes)
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(timeout=60) as http:
            resp = await http.request(method, url, headers=headers,
                                      json=json_body, files=files)
        if resp.status_code >= 400:
            raise OpenAPIError(f"{url} -> {resp.status_code}: {resp.text[:400]}")
        try:
            return resp.json()
        except ValueError:
            return {"raw": base64.b64encode(resp.content).decode("ascii")}

    # --- Marca Temporale ---------------------------------------------------
    async def apply_timestamp(self, pdf_bytes: bytes, filename: str = "contratto.pdf") -> Dict[str, Any]:
        """Applica una marca temporale (data certa) al PDF.

        Ritorna il dict di risposta del servizio: a seconda della
        configurazione contiene il PDF marcato (PAdES) o il token .tsr.
        """
        url = f"{self.timestamp_base}/richiesta"
        files = {"file": (filename, pdf_bytes, "application/pdf")}
        return await self._request("POST", url, ["timestamp:write"], files=files)

    # --- eSignature (FES con OTP) -----------------------------------------
    async def create_signature_request(self, pdf_bytes: bytes, *, signer_name: str,
                                        signer_email: str, signer_phone: str = "",
                                        title: str = "Contratto di assunzione",
                                        filename: str = "contratto.pdf") -> Dict[str, Any]:
        """Crea una richiesta di Firma Elettronica Semplice con OTP.

        Il firmatario (dipendente) riceve un OTP per firmare per accettazione.
        Ritorna almeno {id, status}.
        """
        url = f"{self.esign_base}/signature_requests"
        body = {
            "title": title,
            "document": {
                "filename": filename,
                "content": base64.b64encode(pdf_bytes).decode("ascii"),
            },
            "signers": [{
                "name": signer_name,
                "email": signer_email,
                "phone": signer_phone,
                "signature_type": "FES",   # Firma Elettronica Semplice
                "otp": True,               # OTP via SMS/email
            }],
        }
        return await self._request("POST", url, ["esignature:write"], json_body=body)

    async def get_signature_status(self, request_id: str) -> Dict[str, Any]:
        """Stato di una richiesta di firma. Quando completata espone il PDF firmato."""
        url = f"{self.esign_base}/signature_requests/{request_id}"
        return await self._request("GET", url, ["esignature:read"])

    # --- PEC ---------------------------------------------------------------
    async def send_pec(self, *, to_addr: str, subject: str, body: str,
                       attachments: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Invia una PEC (data certa legale) con allegati.

        attachments: [{"filename": str, "content": bytes}]
        """
        url = f"{self.pec_base}/messages"
        payload = {
            "to": to_addr,
            "subject": subject,
            "body": body,
            "attachments": [{
                "filename": a["filename"],
                "content": base64.b64encode(a["content"]).decode("ascii"),
            } for a in attachments],
        }
        return await self._request("POST", url, ["pec:write"], json_body=payload)


# Istanza singola riusabile (cache token condivisa).
_client: Optional[OpenAPISignatureClient] = None


def get_client() -> OpenAPISignatureClient:
    global _client
    if _client is None:
        _client = OpenAPISignatureClient()
    return _client
