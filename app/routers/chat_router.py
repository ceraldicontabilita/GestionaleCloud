"""
Router Chat Intelligente — Endpoint per domande in linguaggio naturale.

Risponde con query dirette sui dati reali del gestionale: nessun LLM che
genera i numeri, l'interpretazione della domanda è a parole chiave e i
valori restituiti arrivano sempre da una query sul database (o da endpoint
di analisi già esistenti nel gestionale, mai ricalcolati da zero).

Ogni scambio domanda/risposta viene salvato in chat_history, per utente,
così la cronologia non si perde tra una sessione e l'altra.
"""
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, Body, Request

from app.database import Database, Collections

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["Chat Intelligente"])

CHAT_HISTORY_COLLECTION = "chat_history"
STORICO_MAX_VOCI = 20


def _fmt_euro(valore: float) -> str:
    return f"€{valore:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")


def _estrai_anno(domanda: str) -> int:
    match = re.search(r"\b(20\d{2})\b", domanda)
    return int(match.group(1)) if match else datetime.now().year


async def _risposta_fatture(db, domanda: str) -> Dict[str, Any]:
    anno = _estrai_anno(domanda)
    query = {"invoice_date": {"$regex": f"^{anno}"}}
    fatture = await db[Collections.INVOICES].find(
        query, {"_id": 0, "total_amount": 1}
    ).to_list(200000)
    count = len(fatture)
    totale = sum(float(f.get("total_amount") or 0) for f in fatture)
    return {
        "response": f"Nel {anno} hai ricevuto {count} fatture, per un totale di {_fmt_euro(totale)}.",
        "query_type": "fatture",
        "summary": {"count": count, "totale": round(totale, 2), "anno": anno},
        "data_count": count,
    }


async def _risposta_corrispettivi(db, domanda: str) -> Dict[str, Any]:
    anno = _estrai_anno(domanda)
    query = {"data": {"$regex": f"^{anno}"}}
    corrispettivi = await db["corrispettivi"].find(
        query, {"_id": 0, "totale": 1, "pagato_contanti": 1, "pagato_elettronico": 1}
    ).to_list(400)
    count = len(corrispettivi)
    totale = sum(float(c.get("totale") or 0) for c in corrispettivi)
    contanti = sum(float(c.get("pagato_contanti") or 0) for c in corrispettivi)
    elettronico = sum(float(c.get("pagato_elettronico") or 0) for c in corrispettivi)
    return {
        "response": (
            f"Nel {anno} il totale corrispettivi è {_fmt_euro(totale)} su {count} giornate registrate "
            f"({_fmt_euro(contanti)} contanti, {_fmt_euro(elettronico)} elettronico)."
        ),
        "query_type": "corrispettivi",
        "summary": {
            "count": count, "totale": round(totale, 2), "contanti": round(contanti, 2),
            "elettronico": round(elettronico, 2), "anno": anno,
        },
        "data_count": count,
    }


def _f24_anno(doc: Dict[str, Any]) -> "int | None":
    """
    f24_unificato ha più schemi coesistenti (import ZIP grezzo, ai_parser,
    documenti.py in due varianti diverse) — l'anno non è mai garantito come
    campo diretto, va cercato in più punti possibili.
    """
    if doc.get("anno"):
        try:
            return int(str(doc["anno"])[:4])
        except (ValueError, TypeError):
            pass
    for campo in ("data_scadenza", "data_versamento", "created_at", "import_date"):
        val = doc.get(campo)
        if val and len(str(val)) >= 4 and str(val)[:4].isdigit():
            return int(str(val)[:4])
    dati_generali = doc.get("dati_generali") or {}
    if dati_generali.get("data_versamento"):
        val = str(dati_generali["data_versamento"])
        if val[:4].isdigit():
            return int(val[:4])
    for lista in ("tributi_erario", "sezione_erario"):
        tributi = doc.get(lista) or []
        if tributi and tributi[0].get("anno"):
            try:
                return int(str(tributi[0]["anno"])[:4])
            except (ValueError, TypeError):
                pass
    return None


def _f24_importo(doc: Dict[str, Any]) -> float:
    if doc.get("importo_totale"):
        return float(doc["importo_totale"])
    if doc.get("saldo_finale"):
        return float(doc["saldo_finale"])
    totali = doc.get("totali") or {}
    if totali.get("saldo_netto"):
        return float(totali["saldo_netto"])
    if doc.get("totale_debito"):
        return float(doc["totale_debito"])
    return 0.0


def _f24_pagato(doc: Dict[str, Any]) -> bool:
    if doc.get("pagato") is True:
        return True
    return (doc.get("stato") or "").lower() == "pagato"


async def _risposta_f24(db, domanda: str) -> Dict[str, Any]:
    anno = _estrai_anno(domanda)
    tutti = await db[Collections.F24_MODELS].find({}, {"_id": 0}).to_list(50000)
    f24_list = [f for f in tutti if _f24_anno(f) == anno]
    count = len(f24_list)
    totale = sum(_f24_importo(f) for f in f24_list)
    pagati = sum(1 for f in f24_list if _f24_pagato(f))
    return {
        "response": (
            f"Nel {anno} risultano {count} F24 ({pagati} pagati), "
            f"per un totale di {_fmt_euro(totale)}."
        ),
        "query_type": "f24",
        "summary": {"count": count, "pagati": pagati, "totale": round(totale, 2), "anno": anno},
        "data_count": count,
    }


async def _risposta_dipendenti(db, domanda: str) -> Dict[str, Any]:
    attivi = await db[Collections.EMPLOYEES].count_documents({"attivo": {"$ne": False}})
    totali = await db[Collections.EMPLOYEES].count_documents({})
    return {
        "response": f"Hai {attivi} dipendenti attivi (su {totali} totali in anagrafica).",
        "query_type": "dipendenti",
        "summary": {"attivi": attivi, "totali": totali},
        "data_count": attivi,
    }


async def _risposta_bilancio(db, domanda: str) -> Dict[str, Any]:
    anno = _estrai_anno(domanda)
    try:
        from app.routers.accounting.bilancio import get_riepilogo_bilancio
        riepilogo = await get_riepilogo_bilancio(anno=anno)
        ce = riepilogo.get("conto_economico", {}) or {}
        ricavi = (ce.get("ricavi") or {}).get("totale", 0)
        costi = (ce.get("costi") or {}).get("totale", 0)
        utile = (ce.get("risultato") or {}).get("utile_netto", ricavi - costi)
        return {
            "response": (
                f"Bilancio {anno}: ricavi {_fmt_euro(ricavi)}, costi {_fmt_euro(costi)}, "
                f"utile {_fmt_euro(utile)}."
            ),
            "query_type": "bilancio",
            "summary": {"anno": anno, "ricavi": ricavi, "costi": costi, "utile": utile},
            "data_count": 1,
        }
    except Exception:
        logger.exception(f"Errore calcolo bilancio {anno} per chat")
        return {
            "response": f"Non sono riuscito a calcolare il bilancio {anno} — controlla la pagina Bilancio.",
            "query_type": "bilancio",
            "summary": {"anno": anno},
            "data_count": 0,
        }


async def _risposta_fornitori(db, domanda: str) -> Dict[str, Any]:
    count = await db[Collections.SUPPLIERS].count_documents({})
    return {
        "response": f"Hai {count} fornitori in anagrafica.",
        "query_type": "fornitori",
        "summary": {"count": count},
        "data_count": count,
    }


async def _risposta_panoramica(db, domanda: str) -> Dict[str, Any]:
    anno = _estrai_anno(domanda)
    fatture_count = await db[Collections.INVOICES].count_documents(
        {"invoice_date": {"$regex": f"^{anno}"}}
    )
    dipendenti_attivi = await db[Collections.EMPLOYEES].count_documents({"attivo": {"$ne": False}})
    fornitori_count = await db[Collections.SUPPLIERS].count_documents({})
    return {
        "response": (
            f"Panoramica {anno}: {fatture_count} fatture ricevute, "
            f"{dipendenti_attivi} dipendenti attivi, {fornitori_count} fornitori in anagrafica."
        ),
        "query_type": "panoramica",
        "summary": {
            "anno": anno,
            "fatture": fatture_count,
            "dipendenti_attivi": dipendenti_attivi,
            "fornitori": fornitori_count,
        },
        "data_count": fatture_count + dipendenti_attivi + fornitori_count,
    }


async def _risposta_strategia(db, domanda: str) -> Dict[str, Any]:
    """
    Consiglio sul flusso di cassa/andamento, basato sul trend mensile reale
    (stesso endpoint usato dalla pagina Controllo di Gestione — nessun ricalcolo
    parallelo). Il "consiglio" è un confronto numerico esplicito tra gli ultimi
    mesi disponibili, non un giudizio generato liberamente.
    """
    anno = _estrai_anno(domanda)
    try:
        from app.routers.controllo_gestione import get_trend_mensile
        trend = await get_trend_mensile(anno=anno)
        mesi = [m for m in trend.get("trend", []) if m.get("ricavi") or m.get("costi")]
        if len(mesi) < 2:
            return {
                "response": (
                    f"Non ho abbastanza mesi con dati nel {anno} per un confronto di trend "
                    "(servono almeno 2 mesi con corrispettivi o costi registrati)."
                ),
                "query_type": "strategia",
                "summary": {"anno": anno, "mesi_disponibili": len(mesi)},
                "data_count": len(mesi),
            }

        recenti = mesi[-3:] if len(mesi) >= 3 else mesi
        precedenti = mesi[-6:-3] if len(mesi) >= 6 else mesi[:-len(recenti)] or recenti

        def _media(lista, campo):
            return sum(m.get(campo, 0) for m in lista) / len(lista) if lista else 0

        margine_recente = _media(recenti, "margine")
        margine_precedente = _media(precedenti, "margine")
        ricavi_recente = _media(recenti, "ricavi")
        costi_recente = _media(recenti, "costi")

        nomi_recenti = ", ".join(m["mese_nome"] for m in recenti)
        delta = margine_recente - margine_precedente
        if precedenti is recenti or margine_precedente == 0:
            trend_desc = "non ho un periodo precedente comparabile per il confronto"
        elif delta > 0:
            trend_desc = f"il margine medio è migliorato di {_fmt_euro(delta)}/mese rispetto al periodo precedente"
        elif delta < 0:
            trend_desc = f"il margine medio è peggiorato di {_fmt_euro(abs(delta))}/mese rispetto al periodo precedente"
        else:
            trend_desc = "il margine medio è rimasto stabile rispetto al periodo precedente"

        margine_pct = (margine_recente / ricavi_recente * 100) if ricavi_recente else 0
        if margine_pct >= 20:
            valutazione = "un margine sano"
        elif margine_pct >= 5:
            valutazione = "un margine positivo ma da monitorare"
        else:
            valutazione = "un margine molto ridotto o negativo — attenzione ai costi"

        risposta = (
            f"Ultimi mesi con dati ({nomi_recenti}): ricavi medi {_fmt_euro(ricavi_recente)}, "
            f"costi medi {_fmt_euro(costi_recente)}, margine medio {_fmt_euro(margine_recente)} "
            f"({margine_pct:.1f}% dei ricavi — {valutazione}). "
            f"Rispetto al periodo precedente, {trend_desc}."
        )
        return {
            "response": risposta,
            "query_type": "strategia",
            "summary": {
                "anno": anno,
                "mesi_recenti": [m["mese_nome"] for m in recenti],
                "ricavi_medi": round(ricavi_recente, 2),
                "costi_medi": round(costi_recente, 2),
                "margine_medio": round(margine_recente, 2),
                "margine_pct": round(margine_pct, 1),
                "delta_margine_vs_periodo_precedente": round(delta, 2) if precedenti is not recenti else None,
            },
            "data_count": len(mesi),
        }
    except Exception:
        logger.exception(f"Errore analisi strategia {anno} per chat")
        return {
            "response": f"Non sono riuscito ad analizzare il trend {anno} — controlla la pagina Controllo di Gestione.",
            "query_type": "strategia",
            "summary": {"anno": anno},
            "data_count": 0,
        }


# Ordine rilevante: la prima parola chiave che matcha decide l'intento.
_INTENTI = [
    (("consigli", "strategia", "flusso di cassa", "flussi di cassa", "conviene"), _risposta_strategia),
    (("corrispettiv", "incassat", "incasso"), _risposta_corrispettivi),
    (("f24",), _risposta_f24),
    (("bilanci",), _risposta_bilancio),
    (("dipendent", "personale"), _risposta_dipendenti),
    (("fornitor",), _risposta_fornitori),
    (("fattur",), _risposta_fatture),
    (("panoramica", "generale", "situazione"), _risposta_panoramica),
]


def _session_id(request: Request, data: Dict[str, Any]) -> str:
    """
    Identifica a chi appartiene la cronologia: preferisce l'utente autenticato
    (impostato da AuthenticationMiddleware), poi un session_id esplicito dal
    client, poi un default condiviso (comunque salvato, mai perso).
    """
    user_id = getattr(request.state, "user_id", None)
    if user_id:
        return f"user:{user_id}"
    client_session = data.get("session_id")
    if client_session:
        return f"session:{client_session}"
    return "default"


async def _salva_scambio(db, session_id: str, domanda: str, risultato: Dict[str, Any]) -> None:
    try:
        await db[CHAT_HISTORY_COLLECTION].insert_one({
            "id": str(uuid.uuid4()),
            "session_id": session_id,
            "domanda": domanda,
            "risposta": risultato.get("response"),
            "query_type": risultato.get("query_type"),
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception:
        logger.exception("Errore salvataggio chat_history")


async def _recupera_storico(db, session_id: str, limit: int = STORICO_MAX_VOCI) -> List[Dict[str, Any]]:
    try:
        voci = await db[CHAT_HISTORY_COLLECTION].find(
            {"session_id": session_id}, {"_id": 0}
        ).sort("created_at", -1).to_list(limit)
        return list(reversed(voci))
    except Exception:
        logger.exception("Errore lettura chat_history")
        return []


@router.get("/history")
async def chat_history(request: Request, session_id: str = None) -> Dict[str, Any]:
    """Cronologia della chat per l'utente/sessione corrente — non si perde tra un accesso e l'altro."""
    db = Database.get_db()
    sid = _session_id(request, {"session_id": session_id})
    voci = await _recupera_storico(db, sid)
    return {"session_id": sid, "storico": voci, "count": len(voci)}


@router.post("/ask")
async def chat_ask(request: Request, data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Risponde a domande in linguaggio naturale sui dati reali del gestionale."""
    domanda = data.get("question", data.get("domanda", "") or "")
    domanda_lower = domanda.lower()
    db = Database.get_db()
    sid = _session_id(request, data)

    handler = None
    for keywords, fn in _INTENTI:
        if any(k in domanda_lower for k in keywords):
            handler = fn
            break

    if handler is None:
        risultato = {
            "response": (
                "Posso rispondere su corrispettivi, fatture, F24, dipendenti, fornitori, bilancio "
                "e darti un confronto sull'andamento ricavi/costi — prova ad esempio \"Totale "
                "corrispettivo anno 2025\" oppure \"Dammi un consiglio sul flusso di cassa\"."
            ),
            "query_type": "non_riconosciuto",
        }
    else:
        try:
            risultato = await handler(db, domanda)
        except Exception:
            logger.exception(f"Errore chat_ask su domanda: {domanda}")
            risultato = {
                "response": "Si è verificato un errore interrogando i dati. Riprova o consulta la sezione specifica.",
                "query_type": "errore",
            }

    await _salva_scambio(db, sid, domanda, risultato)

    risultato["status"] = "ok"
    risultato["risposta"] = risultato.get("response")
    risultato["session_id"] = sid
    return risultato
