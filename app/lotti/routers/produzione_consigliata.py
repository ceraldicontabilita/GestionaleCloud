"""
Produzione consigliata — Tranche 5 (HACCP features, 04/07/2026).

Punto 2 delle 7 macro-funzionalità: suggerisce cosa produrre oggi o
domani usando storico produzioni, invenduto, giorno della settimana,
festività e andamento corrispettivi. È la funzionalità più "greenfield":
nessuna base di codice esistente oltre ai dati grezzi (produzioni,
vendite_banco, corrispettivi), quindi il motore è scritto qui da zero —
ma riusa gli helper già esistenti in corrispettivi.py invece di
duplicarli.

REGOLA: mai inventare un consiglio senza dati sufficienti. Un prodotto con
meno di 2 osservazioni storiche nello stesso giorno della settimana viene
escluso dai suggerimenti, non forzato con un default arbitrario.

L'utente accetta/modifica/ignora ogni suggerimento (persistito in
`produzione_consigliata_decisioni`): la produzione fisica resta un atto
umano registrato nel flusso normale (ModalRegistraLotto/registra-produzione
-lotto), qui si pianifica soltanto — coerente con le richieste esplicite
di NON collegare scontrino/scarico automatico ("regole importanti").
"""
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.lotti.db import database as db

router = APIRouter(prefix="/produzione-consigliata", tags=["Produzione Consigliata"])

GIORNI_SETTIMANA = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]

FINESTRA_STORICO_GIORNI = 90
SOGLIA_SPRECO_PCT = 20.0          # oltre questa % di invenduto medio, riduce
RIDUZIONE_SPRECO_MAX_PCT = 30.0   # ma mai oltre questo taglio
FATTORE_FESTIVO_PCT = 25.0        # aumento su un giorno festivo/ponte
FATTORE_TREND_MAX_PCT = 15.0      # limite al fattore incassi (prudente)


async def _storico_produzione_per_giorno(giorno_settimana: int) -> dict:
    """Pezzi prodotti storicamente per prodotto, nello stesso giorno della
    settimana, nelle ultime `FINESTRA_STORICO_GIORNI` giornate."""
    limite = (date.today() - timedelta(days=FINESTRA_STORICO_GIORNI)).isoformat()
    docs = await db.produzioni.find(
        {"data_iso": {"$gte": limite}}, {"_id": 0, "ricetta_nome": 1, "pezzi": 1, "data_iso": 1}
    ).to_list(20000)
    per_prodotto: dict = {}
    for d in docs:
        try:
            g = date.fromisoformat(str(d.get("data_iso"))[:10])
        except (ValueError, TypeError):
            continue
        if g.weekday() != giorno_settimana:
            continue
        nome = (d.get("ricetta_nome") or "").strip()
        if not nome:
            continue
        per_prodotto.setdefault(nome, []).append(d.get("pezzi") or 0)
    return per_prodotto


async def _storico_invenduto_per_giorno(giorno_settimana: int) -> dict:
    """Invenduto storico per prodotto, stesso giorno della settimana."""
    limite = (date.today() - timedelta(days=FINESTRA_STORICO_GIORNI)).isoformat()
    docs = await db.vendite_banco.find(
        {"data": {"$gte": limite}, "stato": "chiuso"},
        {"_id": 0, "prodotto_nome": 1, "pezzi_prodotti": 1, "pezzi_invenduto": 1, "data": 1},
    ).to_list(20000)
    per_prodotto: dict = {}
    for d in docs:
        try:
            g = date.fromisoformat(str(d.get("data"))[:10])
        except (ValueError, TypeError):
            continue
        if g.weekday() != giorno_settimana:
            continue
        nome = (d.get("prodotto_nome") or "").strip()
        if not nome:
            continue
        p = per_prodotto.setdefault(nome, {"prodotti": 0, "invenduti": 0, "n": 0})
        p["prodotti"] += d.get("pezzi_prodotti") or 0
        p["invenduti"] += d.get("pezzi_invenduto") or 0
        p["n"] += 1
    return per_prodotto


async def _giorno_festivo_o_ponte(data_target: date) -> Optional[str]:
    """Riusa il calcolo festività già esistente in corrispettivi.py (stesso
    dato usato per l'alert 'anticipa gli ordini') invece di duplicarlo."""
    from app.lotti.routers.corrispettivi import festivita_imminenti
    fest = await festivita_imminenti(giorni=7)
    for f in fest["festivita"]:
        if f["data"] == data_target.isoformat():
            return f["nome"]
        if f.get("ponte") and f["ponte"]["giorno_ponte"] == data_target.isoformat():
            return f"{f['ponte']['tipo']} ({f['nome']})"
    return None


async def _fattore_trend_incassi() -> Optional[dict]:
    """Confronta gli incassi delle ultime 2 settimane con le 2 precedenti
    (stessi helper di corrispettivi.py — `_campi_rilevati`/`_serie` —
    nessuna nuova logica di rilevamento campi). Fattore dimezzato e
    limitato a ±15%: è un aggiustamento prudente, non una previsione
    esatta, e vale per TUTTI i prodotti allo stesso modo perché i
    corrispettivi non si scompongono per prodotto."""
    from app.lotti.routers.corrispettivi import _campi_rilevati, _serie
    campo_data, campo_importo = await _campi_rilevati()
    if not campo_data or not campo_importo:
        return None
    oggi = date.today()
    recente = await _serie(campo_data, campo_importo, oggi - timedelta(days=13), oggi)
    precedente = await _serie(campo_data, campo_importo, oggi - timedelta(days=27), oggi - timedelta(days=14))
    tot_recente = sum(recente.values())
    tot_precedente = sum(precedente.values())
    if tot_precedente <= 0:
        return None
    variazione_pct = (tot_recente - tot_precedente) / tot_precedente * 100
    fattore_pct = max(-FATTORE_TREND_MAX_PCT, min(FATTORE_TREND_MAX_PCT, variazione_pct / 2))
    return {"variazione_incassi_pct": round(variazione_pct, 1), "fattore_pct": round(fattore_pct, 1)}


async def _prodotti_stagionali() -> dict:
    """Mappa nome→nota stagionale, da prodotti_vendita.stagionale (dato già
    esistente, solo informativo in motivazione: non esiste nel modello dati
    una finestra di mesi precisa per applicarlo come fattore quantitativo)."""
    docs = await db.prodotti_vendita.find(
        {"stagionale": True}, {"_id": 0, "nome": 1, "stagione_note": 1}
    ).to_list(500)
    return {(d.get("nome") or "").strip(): d.get("stagione_note") or "" for d in docs if d.get("nome")}


async def genera_suggerimenti(data_target: date) -> dict:
    giorno_settimana = data_target.weekday()
    storico_prod = await _storico_produzione_per_giorno(giorno_settimana)
    storico_inv = await _storico_invenduto_per_giorno(giorno_settimana)
    festivo = await _giorno_festivo_o_ponte(data_target)
    trend = await _fattore_trend_incassi()
    stagionali = await _prodotti_stagionali()

    suggerimenti = []
    for nome, pezzi_list in storico_prod.items():
        if len(pezzi_list) < 2:
            continue  # dati insufficienti: niente consiglio inventato

        media_produzione = sum(pezzi_list) / len(pezzi_list)
        inv = storico_inv.get(nome)
        media_invenduto = None
        pct_invenduto = None
        if inv and inv["n"] > 0:
            media_invenduto = round(inv["invenduti"] / inv["n"], 1)
            if inv["prodotti"] > 0:
                pct_invenduto = round(inv["invenduti"] / inv["prodotti"] * 100, 1)

        quantita = media_produzione
        motivi = [f"Media {media_produzione:.0f} pz nei {GIORNI_SETTIMANA[giorno_settimana]} delle ultime {len(pezzi_list)} settimane"]

        if pct_invenduto is not None and pct_invenduto >= SOGLIA_SPRECO_PCT:
            riduzione_pct = min(RIDUZIONE_SPRECO_MAX_PCT, pct_invenduto / 2)
            quantita *= (1 - riduzione_pct / 100)
            motivi.append(f"−{riduzione_pct:.0f}% per invenduto medio storico del {pct_invenduto}%")

        if festivo:
            quantita *= (1 + FATTORE_FESTIVO_PCT / 100)
            motivi.append(f"+{FATTORE_FESTIVO_PCT:.0f}% per {festivo}")

        if trend and abs(trend["fattore_pct"]) >= 3:
            quantita *= (1 + trend["fattore_pct"] / 100)
            segno = "+" if trend["fattore_pct"] > 0 else ""
            motivi.append(f"{segno}{trend['fattore_pct']:.0f}% per andamento incassi ({segno}{trend['variazione_incassi_pct']:.0f}% ultime 2 settimane)")

        if nome in stagionali:
            motivi.append(f"prodotto stagionale{': ' + stagionali[nome] if stagionali[nome] else ''}")

        suggerimenti.append({
            "prodotto": nome,
            "quantita_consigliata": round(quantita),
            "media_produzione": round(media_produzione, 1),
            "media_invenduto": media_invenduto,
            "pct_invenduto_storico": pct_invenduto,
            "campioni_produzione": len(pezzi_list),
            "stagionale": nome in stagionali,
            "motivazione": "; ".join(motivi),
        })

    suggerimenti.sort(key=lambda s: -s["quantita_consigliata"])
    piu_richiesti = sorted(suggerimenti, key=lambda s: -s["media_produzione"])[:10]
    piu_sprecati = sorted(
        [s for s in suggerimenti if s["pct_invenduto_storico"] is not None],
        key=lambda s: -s["pct_invenduto_storico"],
    )[:10]

    return {
        "data_target": data_target.isoformat(),
        "giorno_settimana": GIORNI_SETTIMANA[giorno_settimana],
        "festivo_o_ponte": festivo,
        "trend_incassi": trend,
        "suggerimenti": suggerimenti,
        "prodotti_piu_richiesti": piu_richiesti,
        "prodotti_piu_sprecati": piu_sprecati,
    }


@router.get("")
async def get_produzione_consigliata(data: Optional[str] = Query(None, description="YYYY-MM-DD, default domani")):
    """Suggerimenti di produzione per una data (default: domani), con le
    eventuali decisioni già prese per quella data e quei prodotti."""
    if data:
        try:
            data_target = date.fromisoformat(data)
        except ValueError:
            raise HTTPException(status_code=400, detail="Formato data non valido, usa YYYY-MM-DD")
    else:
        data_target = date.today() + timedelta(days=1)

    risultato = await genera_suggerimenti(data_target)

    decisioni = await db.produzione_consigliata_decisioni.find(
        {"data": data_target.isoformat()}, {"_id": 0}
    ).to_list(500)
    decisioni_per_prodotto = {d["prodotto"]: d for d in decisioni}
    for s in risultato["suggerimenti"]:
        s["decisione"] = decisioni_per_prodotto.get(s["prodotto"])

    return risultato


class DecisioneIn(BaseModel):
    data: str  # YYYY-MM-DD
    prodotto: str
    quantita_consigliata: Optional[float] = None
    quantita_decisa: Optional[float] = None
    stato: str  # "accettato" | "modificato" | "ignorato"
    operatore_nome: str = ""


@router.post("/decisione")
async def registra_decisione(payload: DecisioneIn):
    """Salva la decisione dell'operatore su un suggerimento (accetta,
    modifica la quantità, o ignora). Upsert su (data, prodotto): un solo
    stato attivo per prodotto/giorno, l'ultima decisione vince."""
    if payload.stato not in ("accettato", "modificato", "ignorato"):
        raise HTTPException(status_code=400, detail="stato deve essere accettato|modificato|ignorato")
    doc = {
        "id": str(uuid.uuid4()),
        "data": payload.data,
        "prodotto": payload.prodotto,
        "quantita_consigliata": payload.quantita_consigliata,
        "quantita_decisa": payload.quantita_decisa if payload.stato != "ignorato" else None,
        "stato": payload.stato,
        "operatore_nome": payload.operatore_nome,
        "decisa_il": datetime.now(timezone.utc).isoformat(),
    }
    await db.produzione_consigliata_decisioni.update_one(
        {"data": payload.data, "prodotto": payload.prodotto},
        {"$set": doc},
        upsert=True,
    )
    doc.pop("_id", None)
    return {"ok": True, "decisione": doc}


@router.get("/decisioni")
async def get_decisioni(data: str = Query(..., description="YYYY-MM-DD")):
    """Decisioni già prese per una data (per mostrare lo stato salvato)."""
    docs = await db.produzione_consigliata_decisioni.find(
        {"data": data}, {"_id": 0}
    ).to_list(500)
    return {"data": data, "decisioni": docs}
