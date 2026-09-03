"""
digest.py — Promemoria operativo del mattino.

Calcola "cosa controllare oggi" (lotti scaduti da rimuovere, lotti in scadenza)
e lo invia su WhatsApp tramite un gateway self-hosted COMPATIBILE con OpenWA
(rmyndharis/OpenWA): POST /api/sessions/{sessione}/messages/send-text con header
X-API-Key e body {chatId, text}.

Il canale è DISACCOPPIATO: il cervello (cosa è urgente) funziona comunque; se il
gateway WhatsApp non è configurato (env mancanti) il digest si calcola lo stesso
e l'invio risponde "non configurato" senza errori.

Env (tutte opzionali):
  WHATSAPP_API_URL   es. http://IP-del-negozio:2785   (base del gateway OpenWA)
  WHATSAPP_API_KEY   la X-API-Key del gateway
  WHATSAPP_SESSION   nome sessione (default: "default")
  WHATSAPP_TO        destinatario, es. "393331234567@c.us"
  DIGEST_GIORNI      finestra "in scadenza" in giorni (default 7)
"""

import os
import logging
_LOG_INIT = logging.getLogger("uvicorn.error")
import re
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Query
from app.lotti.db import database as db

router = APIRouter(prefix="/digest", tags=["digest"])


def _to_iso(ds) -> str | None:
    if not ds:
        return None
    ds = str(ds).strip()
    if re.match(r"\d{2}/\d{2}/\d{4}", ds):
        p = ds.split("/")
        return f"{p[2]}-{p[1]}-{p[0]}"
    if re.match(r"\d{4}-\d{2}-\d{2}", ds):
        return ds[:10]
    return None


def _fmt(ds) -> str:
    iso = _to_iso(ds)
    if not iso:
        return str(ds or "?")
    a, m, g = iso.split("-")
    return f"{g}/{m}/{a}"


async def calcola_digest(giorni: int = 7) -> dict:
    oggi = datetime.now().date()
    oggi_iso = oggi.isoformat()
    limite_iso = (oggi + timedelta(days=giorni)).isoformat()

    lotti = await db.lotti.find(
        {}, {"_id": 0, "numero_lotto": 1, "prodotto": 1, "data_scadenza": 1, "esaurito": 1}
    ).to_list(8000)

    in_scadenza, gia_scaduti = [], []
    for l in lotti:
        if l.get("esaurito") is True:
            continue
        iso = _to_iso(l.get("data_scadenza"))
        if not iso:
            continue
        if iso < oggi_iso:
            gia_scaduti.append(l)
        elif iso <= limite_iso:
            in_scadenza.append(l)

    key = lambda x: _to_iso(x.get("data_scadenza")) or ""
    in_scadenza.sort(key=key)
    gia_scaduti.sort(key=key)

    # Bozze ordini in attesa di conferma (regola: niente invii automatici).
    # Conta entrambi gli store finché il sistema ordini non è unificato.
    try:
        bozze = await db.ordini_fornitori.count_documents(
            {"stato": {"$in": ["bozza", "confermato"]}, "prodotti.0": {"$exists": True}})
    except Exception:
        bozze = 0

    return {"data": oggi_iso, "giorni": giorni, "in_scadenza": in_scadenza,
            "gia_scaduti": gia_scaduti, "bozze_ordini": bozze}


def componi_testo(d: dict) -> str:
    gs, sc = d["gia_scaduti"], d["in_scadenza"]
    bozze = d.get("bozze_ordini", 0)
    righe = [f"🧾 *Controlli del giorno* — {_fmt(d['data'])}", ""]
    if bozze:
        righe.append(f"🛒 *Ordini bozza da confermare e inviare*: {bozze}")
        righe.append("Entra nel carrello, conferma le righe e premi invio.")
        righe.append("")
    if gs:
        righe.append(f"⛔ *Lotti SCADUTI da rimuovere* ({len(gs)}):")
        for l in gs[:15]:
            righe.append(f"• {l.get('prodotto', '?')} — lotto {l.get('numero_lotto', '?')} (scad. {_fmt(l.get('data_scadenza'))})")
        if len(gs) > 15:
            righe.append(f"…e altri {len(gs) - 15}.")
        righe.append("")
    if sc:
        righe.append(f"⚠️ *In scadenza entro {d['giorni']} giorni* ({len(sc)}):")
        for l in sc[:15]:
            righe.append(f"• {l.get('prodotto', '?')} — lotto {l.get('numero_lotto', '?')} (scad. {_fmt(l.get('data_scadenza'))})")
        if len(sc) > 15:
            righe.append(f"…e altri {len(sc) - 15}.")
        righe.append("")
    if not gs and not sc:
        righe.append("✅ Nessun lotto scaduto o in scadenza. Tutto sotto controllo.")
    righe.append("— Lotti HACCP Ceraldi")
    return "\n".join(righe)


async def invia_whatsapp(testo: str) -> dict:
    # Integrazione WhatsApp rimossa: il digest viene solo calcolato e registrato.
    return {"inviato": False, "motivo": "WhatsApp non più utilizzato"}


async def calcola_e_invia(giorni: int | None = None) -> dict:
    if giorni is None:
        try:
            giorni = int(os.environ.get("DIGEST_GIORNI", "7"))
        except ValueError:
            giorni = 7
    d = await calcola_digest(giorni)
    testo = componi_testo(d)
    esito = await invia_whatsapp(testo)
    conteggi = {"scaduti": len(d["gia_scaduti"]), "in_scadenza": len(d["in_scadenza"])}
    try:
        await db.digest_logs.insert_one(
            {"quando": datetime.now(timezone.utc).isoformat(), **conteggi, "esito": esito}
        )
    except Exception:
        _LOG_INIT.debug("[digest] errore non bloccante ignorato")
    return {"testo": testo, "esito": esito, "conteggi": conteggi}


@router.get("/anteprima")
async def anteprima(giorni: int = Query(7, ge=1, le=60)):
    """Mostra il testo del promemoria SENZA inviarlo (per controllo)."""
    d = await calcola_digest(giorni)
    return {"ok": True, "testo": componi_testo(d), "conteggi": {"scaduti": len(d["gia_scaduti"]), "in_scadenza": len(d["in_scadenza"])}}


@router.post("/invia-ora")
async def invia_ora(giorni: int = Query(7, ge=1, le=60)):
    """Calcola e invia subito il promemoria (test on-demand)."""
    return {"ok": True, **(await calcola_e_invia(giorni))}
