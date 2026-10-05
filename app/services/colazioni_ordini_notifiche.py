"""Avviso immediato al bar quando un hotel invia un ordine prodotti.

Due canali, entrambi dopo il salvataggio dell'ordine e mai nel suo percorso:
un messaggio Telegram **non silenzioso** (push sul telefono del titolare) e una
email al bar. Se un canale fallisce l'ordine resta valido e l'errore va nel log,
con il nome dell'eccezione; l'altro canale parte lo stesso.
"""

from __future__ import annotations

import asyncio
import html
import logging
import os
from datetime import date
from typing import Any, Mapping

from app.services.telegram_notifications import is_configured, send_notification

logger = logging.getLogger(__name__)

URL_ORDINI = "https://gestionalecloud.onrender.com/convenzioni/#/titolare"
_in_volo: set[asyncio.Task] = set()


def _gg_mm_aaaa(iso: Any) -> str:
    try:
        return date.fromisoformat(str(iso)[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return str(iso or "")


def _euro(valore: Any) -> str:
    try:
        return f"{float(valore):.2f}".replace(".", ",") + " €"
    except (TypeError, ValueError):
        return "—"


def _pagamento(ordine: Mapping[str, Any]) -> str:
    if ordine.get("pagamento_metodo") == "borsellino":
        return "PAGATO dal borsellino"
    return "DA INCASSARE in loco"


def _righe(ordine: Mapping[str, Any]) -> list[str]:
    return [
        f"{int(r.get('quantita') or 0)}× {r.get('nome') or 'Prodotto'} ({_euro(r.get('totale'))})"
        for r in (ordine.get("righe") or [])
    ]


def testo_telegram(ordine: Mapping[str, Any]) -> str:
    esc = lambda v: html.escape(str(v or ""))  # noqa: E731
    righe = "\n".join(f"• {esc(r)}" for r in _righe(ordine))
    nota = f"\n📝 {esc(ordine.get('nota'))}" if ordine.get("nota") else ""
    return (
        "🛒 <b>Nuovo ordine prodotti dall'hotel</b>\n\n"
        f"🏨 {esc(ordine.get('struttura_nome'))} · <code>{esc(ordine.get('id'))}</code>\n"
        f"📅 Consegna <b>{esc(_gg_mm_aaaa(ordine.get('data_consegna')))}</b>"
        f" ore <b>{esc(ordine.get('ora_ritiro'))}</b>\n"
        f"{righe}\n"
        f"💶 Totale <b>{esc(_euro(ordine.get('totale')))}</b> · {esc(_pagamento(ordine))}"
        f"{nota}"
    )


def oggetto_email(ordine: Mapping[str, Any]) -> str:
    return (
        f"Nuovo ordine prodotti · {ordine.get('struttura_nome') or 'Hotel'} · "
        f"consegna {_gg_mm_aaaa(ordine.get('data_consegna'))} ore {ordine.get('ora_ritiro') or ''} · "
        f"{ordine.get('id')}"
    )


def corpo_email(ordine: Mapping[str, Any]) -> str:
    righe = "\n".join(f"  - {r}" for r in _righe(ordine))
    nota = f"\nNota dell'hotel: {ordine.get('nota')}\n" if ordine.get("nota") else ""
    return (
        f"Un hotel ha inviato un ordine di prodotti.\n\n"
        f"Hotel: {ordine.get('struttura_nome')}\n"
        f"Ordine: {ordine.get('id')}\n"
        f"Consegna: {_gg_mm_aaaa(ordine.get('data_consegna'))} alle {ordine.get('ora_ritiro')}\n\n"
        f"Prodotti:\n{righe}\n\n"
        f"Totale: {_euro(ordine.get('totale'))}\n"
        f"Pagamento: {_pagamento(ordine)}\n"
        f"{nota}\n"
        f"Lo trovi in «Ordini prodotti»: {URL_ORDINI}\n"
    )


async def _destinatario_bar() -> str:
    """Email del bar dalle Impostazioni (bar_email); in mancanza, l'account di posta dell'azienda."""
    from app.routers.colazioni import _rpc_bb

    try:
        contatti = await _rpc_bb("bb_ordini_contatti_bar", {})
        email = str((contatti or {}).get("email") or "").strip() if isinstance(contatti, dict) else ""
    except Exception as exc:  # il database non risponde: si prova il ripiego
        logger.warning("Email del bar non letta (%s): uso l'account aziendale", type(exc).__name__)
        email = ""
    if email:
        return email
    from app.hr.services.email_smtp import credenziali_smtp

    cred = credenziali_smtp()
    return os.getenv("REQUEST_NOTIFY_EMAIL") or (cred["user"] if cred else "")


async def notifica_ordine_prodotti(ordine: Mapping[str, Any]) -> dict[str, bool]:
    esito = {"telegram": False, "email": False}
    try:
        if is_configured():
            r = await send_notification(testo_telegram(ordine), disable_notification=False)
            esito["telegram"] = bool(r.get("success"))
            if not esito["telegram"]:
                logger.error("[ORDINI-PRODOTTI] Telegram non inviato per %s: %s", ordine.get("id"), r.get("error"))
        else:
            logger.warning("[ORDINI-PRODOTTI] Telegram non configurato: avviso del %s non inviato", ordine.get("id"))
    except Exception as exc:
        logger.error("[ORDINI-PRODOTTI] Telegram %s: %s: %s", ordine.get("id"), type(exc).__name__, exc)
    try:
        from app.hr.services.email_smtp import invia_email

        destinatario = await _destinatario_bar()
        if not destinatario:
            logger.warning("[ORDINI-PRODOTTI] Nessun indirizzo del bar: email del %s non inviata", ordine.get("id"))
        else:
            await asyncio.to_thread(invia_email, destinatario, oggetto_email(ordine), corpo_email(ordine))
            esito["email"] = True
    except Exception as exc:
        logger.error("[ORDINI-PRODOTTI] Email %s: %s: %s", ordine.get("id"), type(exc).__name__, exc)
    return esito


def avvisa_in_background(ordine: Mapping[str, Any]) -> None:
    """Lancia l'avviso senza far aspettare l'hotel (l'SMTP puo' impiegare decine di secondi)."""
    task = asyncio.create_task(notifica_ordine_prodotti(dict(ordine)))
    _in_volo.add(task)
    task.add_done_callback(_in_volo.discard)
