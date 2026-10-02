"""Ricariche del portafoglio hotel tramite SumUp Hosted Checkout.

La chiave SumUp resta esclusivamente su Render. Il webhook non viene mai
considerato una prova di pagamento: ogni evento provoca una GET del checkout
e solo la risposta autenticata di SumUp viene applicata al portafoglio.
"""
from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

import aiohttp

from app.config import settings
from app.services.sumup_sync import merchant_effettivo

logger = logging.getLogger(__name__)

TIMEOUT = aiohttp.ClientTimeout(total=20)


class SumUpRicaricheNonConfigurato(RuntimeError):
    pass


class SumUpRicaricheErrore(RuntimeError):
    pass


def _headers() -> dict[str, str]:
    chiave = (settings.SUMUP_API_KEY or "").strip()
    if not chiave:
        raise SumUpRicaricheNonConfigurato("Pagamento SumUp non configurato")
    return {"Authorization": f"Bearer {chiave}", "Content-Type": "application/json"}


def _denaro(valore: Any) -> Decimal:
    try:
        return Decimal(str(valore or "0")).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise SumUpRicaricheErrore("Importo SumUp non valido") from exc


def esito_checkout(dati: Mapping[str, Any]) -> dict[str, Any]:
    """Riduce la risposta SumUp ai soli dati verificabili necessari al wallet."""
    transazioni = dati.get("transactions") or []
    transazione = next(
        (t for t in transazioni if isinstance(t, Mapping) and str(t.get("type") or "PAYMENT").upper() == "PAYMENT"),
        next((t for t in transazioni if isinstance(t, Mapping)), {}),
    )
    stato_checkout = str(dati.get("status") or "PENDING").upper()
    stato_transazione = str(transazione.get("status") or "").upper()
    rimborsato = _denaro(transazione.get("refunded_amount"))
    if stato_transazione == "REFUNDED" and rimborsato <= 0:
        rimborsato = _denaro(transazione.get("amount") or dati.get("amount"))
    return {
        "checkout_id": str(dati.get("id") or "").strip(),
        "riferimento": str(dati.get("checkout_reference") or "").strip(),
        "importo": _denaro(dati.get("amount")),
        "valuta": str(dati.get("currency") or "").upper(),
        "merchant_code": str(dati.get("merchant_code") or "").strip(),
        "stato": stato_checkout,
        "transaction_id": str(
            transazione.get("id") or transazione.get("transaction_id") or ""
        ).strip(),
        "transaction_code": str(transazione.get("transaction_code") or "").strip(),
        "rimborsato": rimborsato,
        "audit": {
            "checkout_status": stato_checkout,
            "transaction_status": stato_transazione,
            "transactions_count": len(transazioni),
        },
    }


async def crea_checkout(
    *, riferimento: str, importo: Decimal, struttura: str, redirect_url: str, webhook_url: str
) -> dict[str, Any]:
    merchant = await merchant_effettivo()
    payload = {
        "checkout_reference": riferimento,
        "amount": float(_denaro(importo)),
        "currency": "EUR",
        "merchant_code": merchant,
        "description": f"Ricarica credito colazioni · {struttura}"[:140],
        "redirect_url": redirect_url,
        "return_url": webhook_url,
        "hosted_checkout": {"enabled": True},
    }
    url = f"{settings.SUMUP_API_BASE.rstrip('/')}/v0.1/checkouts"
    try:
        async with aiohttp.ClientSession(timeout=TIMEOUT, headers=_headers()) as sessione:
            async with sessione.post(url, json=payload) as risposta:
                dati = await risposta.json(content_type=None)
                if risposta.status < 200 or risposta.status >= 300:
                    raise SumUpRicaricheErrore(f"SumUp ha rifiutato il checkout ({risposta.status})")
    except aiohttp.ClientError as exc:
        raise SumUpRicaricheErrore("SumUp non raggiungibile") from exc
    checkout_id = str((dati or {}).get("id") or "").strip()
    hosted_url = str((dati or {}).get("hosted_checkout_url") or "").strip()
    if not checkout_id or not hosted_url.startswith("https://checkout.sumup.com/"):
        raise SumUpRicaricheErrore("SumUp non ha restituito la pagina di pagamento")
    return {
        "id": checkout_id,
        "url": hosted_url,
        "merchant_code": str((dati or {}).get("merchant_code") or merchant),
        "status": str((dati or {}).get("status") or "PENDING").upper(),
    }


async def leggi_checkout(checkout_id: str) -> dict[str, Any]:
    checkout_id = str(checkout_id or "").strip()
    if not checkout_id:
        raise SumUpRicaricheErrore("Checkout SumUp mancante")
    url = f"{settings.SUMUP_API_BASE.rstrip('/')}/v0.1/checkouts/{checkout_id}"
    try:
        async with aiohttp.ClientSession(timeout=TIMEOUT, headers=_headers()) as sessione:
            async with sessione.get(url) as risposta:
                dati = await risposta.json(content_type=None)
                if risposta.status == 404:
                    raise SumUpRicaricheErrore("Checkout SumUp non trovato")
                if risposta.status < 200 or risposta.status >= 300:
                    raise SumUpRicaricheErrore(f"Verifica SumUp non riuscita ({risposta.status})")
    except aiohttp.ClientError as exc:
        raise SumUpRicaricheErrore("SumUp non raggiungibile") from exc
    return esito_checkout(dati or {})


async def _rpc_runtime(nome: str, payload: Mapping[str, Any]) -> Any:
    url = (settings.SUPABASE_URL or "").strip().rstrip("/")
    pubblica = (settings.SUPABASE_PUBLISHABLE_KEY or "").strip()
    segreto = (settings.SUPABASE_RUNTIME_SECRET or "").strip()
    if not (url and pubblica and segreto):
        raise RuntimeError("Supabase runtime non configurato")
    headers = {
        "apikey": pubblica,
        "x-gc-api-key": segreto,
        "Content-Type": "application/json",
    }
    async with aiohttp.ClientSession(timeout=TIMEOUT, headers=headers) as sessione:
        async with sessione.post(f"{url}/rest/v1/rpc/{nome}", json=dict(payload)) as risposta:
            corpo = await risposta.json(content_type=None)
            if risposta.status >= 400:
                raise RuntimeError(f"RPC {nome}: HTTP {risposta.status}")
            return corpo


async def sincronizza_ricariche(limite: int = 50) -> dict[str, int | bool]:
    """Controllo di recupero: affianca webhook e ritorno dell'albergatore."""
    if not (settings.SUMUP_API_KEY or "").strip():
        return {"configurato": False, "controllate": 0, "fallite": 0}
    ids = await _rpc_runtime(
        "bb_sumup_ricariche_da_verificare", {"plimite": limite, "psid": None}
    )
    risultato: dict[str, int | bool] = {
        "configurato": True,
        "controllate": 0,
        "fallite": 0,
    }
    for checkout_id in ids or []:
        try:
            esito = await leggi_checkout(str(checkout_id))
            await _rpc_runtime(
                "bb_ricarica_applica_sumup",
                {
                    "pcheckout": esito["checkout_id"],
                    "preference": esito["riferimento"],
                    "pamount": str(esito["importo"]),
                    "pcurrency": esito["valuta"],
                    "pmerchant": esito["merchant_code"],
                    "pstatus": esito["stato"],
                    "ptransaction_id": esito["transaction_id"],
                    "ptransaction_code": esito["transaction_code"],
                    "prefunded": str(esito["rimborsato"]),
                    "praw": esito["audit"],
                },
            )
            risultato["controllate"] += 1
        except Exception as exc:
            risultato["fallite"] += 1
            logger.warning(
                "[RICARICHE-SUMUP] checkout %s: %s", checkout_id, type(exc).__name__
            )
    return risultato

