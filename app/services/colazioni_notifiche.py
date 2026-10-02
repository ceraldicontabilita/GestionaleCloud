"""Avvisi operativi esterni per le colazioni B&B.

Le operazioni vengono accodate nella stessa transazione Supabase che salva la
prenotazione o gli extra. Lo scheduler le consegna al canale Telegram del
titolare: l'app puo' essere chiusa e l'albergatore non vede alcun avviso.
"""

from __future__ import annotations

import html
import logging
from typing import Any

import aiohttp

from app.config import settings
from app.services.telegram_notifications import is_configured, send_notification

logger = logging.getLogger(__name__)


async def _rpc_runtime(nome: str, payload: dict[str, Any]) -> Any:
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
    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=20), headers=headers
    ) as sessione:
        async with sessione.post(f"{url}/rest/v1/rpc/{nome}", json=payload) as risposta:
            corpo = await risposta.json(content_type=None)
            if risposta.status >= 400:
                raise RuntimeError(f"RPC {nome}: HTTP {risposta.status}")
            return corpo


def _testo(lavoro: dict[str, Any]) -> str:
    dati = lavoro.get("payload") or {}
    tipo = lavoro.get("tipo")
    struttura = html.escape(str(dati.get("struttura") or "Struttura"))
    camera = html.escape(str(dati.get("camera") or "non indicata"))
    periodo = html.escape(str(dati.get("periodo") or ""))
    if tipo == "extra_ospite":
        righe = dati.get("extra") or []
        prodotti = ", ".join(
            f"{int(r.get('qta') or 0)}x {html.escape(str(r.get('nome') or 'Prodotto'))}"
            for r in righe
        ) or "extra aggiornati"
        totale = float(dati.get("totale") or 0)
        return (
            "🛒 <b>Nuovi extra per una colazione</b>\n\n"
            f"🏨 {struttura}\n"
            f"🚪 Camera: <b>{camera}</b>\n"
            f"📦 {prodotti}\n"
            f"💶 Da incassare al bar: <b>€ {totale:.2f}</b>"
        )
    quantita = int(dati.get("quantita") or 0)
    totale = float(dati.get("totale") or 0)
    colazione = html.escape(str(dati.get("colazione") or "Colazione"))
    servizio = "tavolo" if dati.get("servizio_tavolo") else "banco"
    return (
        "☕ <b>Nuovo acquisto colazioni hotel</b>\n\n"
        f"🏨 {struttura}\n"
        f"🚪 Camera: <b>{camera}</b>\n"
        f"📅 {periodo}\n"
        f"🥐 {quantita}x {colazione} · servizio {servizio}\n"
        f"💶 Addebitato: <b>€ {totale:.2f}</b>"
    )


async def processa_notifiche_colazioni(limite: int = 30) -> dict[str, int | bool]:
    """Consegna una volta sola gli eventi accodati, con retry lato database."""

    if not is_configured():
        return {"configurato": False, "presi": 0, "inviati": 0, "falliti": 0}
    lavori = await _rpc_runtime("bb_notifiche_operative_prendi", {"plimite": limite})
    risultato: dict[str, int | bool] = {
        "configurato": True,
        "presi": len(lavori or []),
        "inviati": 0,
        "falliti": 0,
    }
    for lavoro in lavori or []:
        try:
            esito = await send_notification(_testo(lavoro))
            if not esito.get("success"):
                raise RuntimeError(str(esito.get("error") or "invio non riuscito"))
            await _rpc_runtime(
                "bb_notifiche_operative_esito",
                {
                    "pjob": lavoro["job_id"],
                    "pinviato": True,
                    "pprovider": str(esito.get("message_id") or ""),
                    "perrore": "",
                },
            )
            risultato["inviati"] += 1
        except Exception as exc:
            risultato["falliti"] += 1
            logger.error(
                "[NOTIFICHE-COLAZIONI] job %s fallito: %s: %s",
                lavoro.get("job_id"),
                type(exc).__name__,
                exc,
            )
            await _rpc_runtime(
                "bb_notifiche_operative_esito",
                {
                    "pjob": lavoro["job_id"],
                    "pinviato": False,
                    "pprovider": "",
                    "perrore": f"{type(exc).__name__}: {exc}"[:400],
                },
            )
    return risultato
