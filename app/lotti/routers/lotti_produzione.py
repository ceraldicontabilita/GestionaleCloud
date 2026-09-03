"""
Router per gestione lotti di produzione: CRUD lotti, recall, registro,
registra-produzione-lotto, genera-lotto, anteprima-codice-lotto.
"""

import re
import logging
_LOG_INIT = logging.getLogger("uvicorn.error")
import uuid
import json
from datetime import datetime, timezone, date, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import HTMLResponse, Response

from app.lotti.db import database as db
from pymongo.errors import DuplicateKeyError
from app.lotti.auth import require_admin
from app.lotti.servizi.lotti_service import crea_lotto

router = APIRouter(tags=["Lotti Produzione"])


# MongoDB connection (stessa logica degli altri router)
def _json_loads_safe(s: Optional[str]) -> list:
    """Deserializza JSON string in lista; ritorna [] se None o malformato."""
    if not s:
        return []
    try:
        return json.loads(s)
    except Exception:
        return []


def set_database(database):
    """Permette override del db dall'esterno (compatibilità)."""
    global db
    db = database


# ── Funzioni helper di lotto (rimangono qui perché usate solo da questo router) ──

PRODOTTI_IN_KG = [
    "semola",
    "farina",
    "zucchero",
    "sale",
    "lievito",
    "burro",
    "olio",
    "latte",
    "panna",
    "ricotta",
    "mozzarella",
    "pomodoro",
    "sugo",
    "pasta",
    "riso",
    "frutta",
    "verdura",
    "carne",
    "pesce",
    "caffè",
]


def determina_unita_misura(prodotto: str) -> str:
    """Determina l'unità di misura appropriata per un prodotto."""
    nome_lower = prodotto.lower()
    for keyword in PRODOTTI_IN_KG:
        if keyword in nome_lower:
            return "kg"
    return "pz"


def genera_abbreviazione_prodotto(prodotto: str) -> str:
    """Genera un'abbreviazione di max 10 caratteri dal nome del prodotto."""
    stop_words = {
        "di",
        "al",
        "con",
        "e",
        "a",
        "il",
        "la",
        "lo",
        "le",
        "gli",
        "da",
        "in",
        "su",
        "per",
    }
    parole = [
        p
        for p in re.sub(r"[^a-zA-Z\s]", "", prodotto).upper().split()
        if p.lower() not in stop_words
    ]
    if len(parole) == 1:
        return parole[0][:10]
    elif len(parole) == 2:
        return f"{parole[0][:5]}_{parole[1][:4]}"
    else:
        return "_".join([p[:4] for p in parole[:2]])[:10]


def genera_codice_lotto(
    prodotto: str, progressivo: int, quantita: float, unita: str, data_produzione: str
) -> str:
    """Genera il codice lotto nel formato: ABBRPRODOTTO-NNN-QTAunita-DDMMYYYY"""
    abbreviazione = genera_abbreviazione_prodotto(prodotto)
    try:
        data_obj = datetime.strptime(data_produzione, "%Y-%m-%d")
        data_fmt = data_obj.strftime("%d%m%Y")
    except (ValueError, TypeError):
        data_fmt = re.sub(r"[^0-9]", "", data_produzione)
    qty_str = str(int(quantita)) if quantita == int(quantita) else str(quantita)
    return f"{abbreviazione}-{progressivo:03d}-{qty_str}{unita}-{data_fmt}"


async def get_prossimo_progressivo(prodotto: str) -> int:
    """Incrementa e restituisce il progressivo per un prodotto."""
    chiave = genera_abbreviazione_prodotto(prodotto)
    result = await db.contatori_lotti.find_one_and_update(
        {"prodotto_chiave": chiave}, {"$inc": {"progressivo": 1}}, upsert=True, return_document=True
    )
    return result.get("progressivo", 1) if result else 1


# ── CRUD Lotti ────────────────────────────────────────────────────────────────
# GET /lotti, GET /lotti/{id}, DELETE /lotti/{id} → gestiti da lotti.py
# (con normalizzazione schema e filtri data — evita conflitto FastAPI)


@router.get("/lotti/recall/cerca")
async def recall_lotti_per_ingrediente(
    ingrediente: str = Query(...),
    data_da: str = Query(None),
    data_a: str = Query(None),
    fornitore: str = Query(None),
    frigo: str = Query(None),
    mesi: int = Query(2, description="Quanti mesi indietro cercare (default 2)"),
    limit: int = Query(200),
):
    """Cerca tutti i lotti che contengono un determinato ingrediente (per recall ASL).
    Di default cerca solo negli ultimi 2 mesi."""
    from datetime import timedelta

    testo = ingrediente.strip()
    pattern = re.escape(testo[:60])

    # Calcola data di inizio automatica (ultimi N mesi) se non specificata dall'utente
    if not data_da:
        data_da = (datetime.now(timezone.utc) - timedelta(days=mesi * 31)).strftime("%Y-%m-%d")

    base_query = {"ingredienti_dettaglio": {"$elemMatch": {"$regex": pattern, "$options": "i"}}}
    lotti = (
        await db.lotti.find(base_query, {"_id": 0})
        .to_list(3000)
    )

    if not lotti:
        parole = [p for p in testo.split() if len(p) > 2][:3]
        if parole:
            pattern_corto = re.escape(" ".join(parole))
            base_query = {
                "ingredienti_dettaglio": {"$elemMatch": {"$regex": pattern_corto, "$options": "i"}}
            }
            lotti = (
                await db.lotti.find(base_query, {"_id": 0})
                .sort("data_produzione", -1)
                .limit(limit)
                .to_list(limit)
            )

    def parse_data(d_str):
        if not d_str:
            return None
        try:
            fmt = "%d/%m/%Y" if "/" in d_str else "%Y-%m-%d"
            return datetime.strptime(d_str, fmt).date()
        except Exception:
            return None

    dt_da = parse_data(data_da)
    dt_a = parse_data(data_a)
    risultati = []
    for lotto in lotti:
        if dt_da or dt_a:
            dt_lotto = parse_data(lotto.get("data_produzione", ""))
            if dt_lotto:
                if dt_da and dt_lotto < dt_da:
                    continue
                if dt_a and dt_lotto > dt_a:
                    continue
        if frigo and frigo.strip():
            if frigo.strip().lower() not in (lotto.get("frigo_numero") or "").lower():
                continue
        ing_match = [
            ing
            for ing in (lotto.get("ingredienti_dettaglio") or [])
            if testo.lower()[:30] in ing.lower()
            or any(p.lower() in ing.lower() for p in testo.split()[:3] if len(p) > 3)
        ]
        fornitore_estratto = ""
        if ing_match:
            parti = ing_match[0].split(" - ")
            if len(parti) >= 2:
                fornitore_estratto = parti[1].split(" n°")[0].strip()
        if fornitore and fornitore.strip():
            testo_cerca = (
                fornitore_estratto + " " + " ".join(lotto.get("ingredienti_dettaglio") or [])
            ).lower()
            if fornitore.strip().lower() not in testo_cerca:
                continue
        risultati.append(
            {
                "id": lotto.get("id"),
                "prodotto": lotto.get("prodotto"),
                "numero_lotto": lotto.get("numero_lotto"),
                "data_produzione": lotto.get("data_produzione"),
                "data_scadenza": lotto.get("data_scadenza"),
                "quantita": lotto.get("quantita"),
                "unita_misura": lotto.get("unita_misura"),
                "allergeni_testo": lotto.get("allergeni_testo"),
                "frigo_numero": lotto.get("frigo_numero", ""),
                "ingrediente_trovato": ing_match[0] if ing_match else testo,
                "fornitore": fornitore_estratto,
                "tracciato_via_componente": False,
            }
        )

    # Cerca anche nei lotti_componenti[] (tracciabilità indiretta)
    componenti_query = {"lotti_componenti.lotto_id": {"$exists": True}}
    lotti_con_comp = (
        await db.lotti.find(
            componenti_query,
            {
                "_id": 0,
                "id": 1,
                "prodotto": 1,
                "numero_lotto": 1,
                "data_produzione": 1,
                "data_scadenza": 1,
                "quantita": 1,
                "unita_misura": 1,
                "frigo_numero": 1,
                "lotti_componenti": 1,
            },
        )
        .to_list(3000)
    )
    ids_gia_trovati = {r["id"] for r in risultati if r.get("id")}
    for lotto in lotti_con_comp:
        if lotto.get("id") in ids_gia_trovati:
            continue
        componenti = lotto.get("lotti_componenti") or []
        match_comp = [
            c
            for c in componenti
            if testo.lower() in (c.get("nome") or "").lower()
            or testo.lower() in (c.get("numero_lotto") or "").lower()
        ]
        if not match_comp:
            continue
        risultati.append(
            {
                "id": lotto.get("id"),
                "prodotto": lotto.get("prodotto"),
                "numero_lotto": lotto.get("numero_lotto"),
                "data_produzione": lotto.get("data_produzione"),
                "data_scadenza": lotto.get("data_scadenza"),
                "quantita": lotto.get("quantita"),
                "unita_misura": lotto.get("unita_misura"),
                "allergeni_testo": "",
                "frigo_numero": lotto.get("frigo_numero", ""),
                "ingrediente_trovato": match_comp[0].get("nome", testo),
                "fornitore": "",
                "tracciato_via_componente": True,
            }
        )

    # Ordinamento per data VERA (data_produzione è a formato misto dd/mm/yyyy +
    # ISO): prima si ordinava e si tagliava a `limit` nel DB in ordine
    # lessicografico ("31/12/2024" > "2026-07-01"), col rischio di ESCLUDERE
    # dal richiamo ASL i lotti più recenti scritti in ISO. Ora si raccoglie
    # tutto il match, si ordina in Python sulla data reale e si taglia in fondo.
    risultati.sort(key=lambda r: parse_data(r.get("data_produzione", "")) or date.min, reverse=True)
    risultati = risultati[:limit]
    return {"ingrediente_cercato": testo, "totale_lotti": len(risultati), "lotti": risultati}


# ── Registro richiami eseguiti (Reg. CE 178/2002) ────────────────────────────
# `/lotti/recall/cerca` sopra è solo una RICERCA on-demand — nulla viene
# persistito. Qui invece si registra FORMALMENTE che un richiamo è stato
# davvero avviato sui lotti trovati, con operatore/motivo/esito, e ogni
# lotto coinvolto riceve un evento "recall" nel proprio registro movimenti
# (colma il gap esplicitamente documentato in Tranche 3: "i richiami sono
# ricerche on-demand, non eventi persistiti — non compaiono in cronologia").


@router.post("/lotti/recall/esegui")
async def registra_richiamo_eseguito(
    payload: dict,
    motivo: str = Query(""),
    operatore_id: Optional[str] = Query(None),
    operatore_nome: Optional[str] = Query(None),
):
    """Body: {"ingrediente": str, "filtri": {...}, "lotti_ids": [...]}
    (stessi dati già in mano al frontend dopo una ricerca /recall/cerca)."""
    ingrediente = (payload.get("ingrediente") or "").strip()
    filtri = payload.get("filtri") or {}
    lotti_ids = payload.get("lotti_ids") or []
    if not lotti_ids:
        raise HTTPException(status_code=400, detail="Nessun lotto selezionato")

    lotti_coinvolti = await db.lotti.find(
        {"id": {"$in": lotti_ids}},
        {"_id": 0, "id": 1, "numero_lotto": 1, "prodotto": 1, "quantita": 1, "frigo_numero": 1},
    ).to_list(len(lotti_ids))

    richiamo_id = str(uuid.uuid4())
    doc = {
        "id": richiamo_id,
        "ingrediente": ingrediente,
        "filtri": filtri,
        "lotti_coinvolti": lotti_coinvolti,
        "n_lotti": len(lotti_coinvolti),
        "motivo": motivo,
        "operatore_id": operatore_id or "",
        "operatore_nome": operatore_nome or "",
        "stato": "aperto",
        "azione_correttiva": "",
        "data_ora_apertura": datetime.now(timezone.utc).isoformat(),
        "data_ora_chiusura": None,
    }
    await db.richiami_eseguiti.insert_one(dict(doc))
    doc.pop("_id", None)

    # TRANCHE 4 (decisione Enzo 24/07/2026): il richiamo BLOCCA i lotti nel
    # BACKEND — niente più produzioni/banco/trasferimenti finché un
    # amministratore non sblocca con motivazione. Ogni blocco è tracciato.
    _adesso = datetime.now(timezone.utc).isoformat()
    for lt in lotti_coinvolti:
        await db.lotti.update_one({"id": lt["id"]}, {"$set": {
            "stato": "bloccato_richiamo", "richiamo_ref": richiamo_id,
            "bloccato_il": _adesso,
            "bloccato_da": operatore_nome or operatore_id or "",
            "bloccato_motivo": motivo or f"Richiamo: {ingrediente}"}})
        await db.blocchi_lotti.insert_one({
            "id": str(uuid.uuid4()), "lotto_id": lt["id"],
            "numero_lotto": lt.get("numero_lotto", ""), "azione": "blocco",
            "data": _adesso, "utente": operatore_nome or operatore_id or "",
            "motivazione": motivo or f"Richiamo: {ingrediente}",
            "richiamo_ref": richiamo_id,
            "quantita": lt.get("quantita"), "note": ""})

    from app.lotti.servizi.movimenti_lotto_service import registra_movimento
    for lt in lotti_coinvolti:
        try:
            await registra_movimento(
                lt["id"], "recall",
                numero_lotto=lt.get("numero_lotto", ""),
                operatore_id=operatore_id or "", operatore_nome=operatore_nome or "",
                motivo=motivo or f"Richiamo per ingrediente: {ingrediente}",
                documento_collegato={"tipo": "richiamo", "id": richiamo_id},
            )
        except Exception:
            _LOG_INIT.exception("[lotti_produzione] registrazione movimento recall fallita (non bloccante)")

    return {"ok": True, "richiamo": doc}


@router.get("/lotti/recall/eseguiti")
async def lista_richiami_eseguiti(stato: Optional[str] = Query(None), limit: int = Query(100)):
    query: dict = {}
    if stato:
        query["stato"] = stato
    docs = await db.richiami_eseguiti.find(query, {"_id": 0}).sort("data_ora_apertura", -1).to_list(limit)
    return {"totale": len(docs), "richiami": docs}


@router.patch("/lotti/recall/eseguiti/{richiamo_id}/concludi")
async def concludi_richiamo(richiamo_id: str, azione_correttiva: str = Query(...)):
    richiamo = await db.richiami_eseguiti.find_one({"id": richiamo_id}, {"_id": 0})
    if not richiamo:
        raise HTTPException(status_code=404, detail="Richiamo non trovato")
    await db.richiami_eseguiti.update_one(
        {"id": richiamo_id},
        {"$set": {
            "stato": "concluso",
            "azione_correttiva": azione_correttiva,
            "data_ora_chiusura": datetime.now(timezone.utc).isoformat(),
        }},
    )
    return {"ok": True}


# ── Giacenza prodotti finiti (frigo/abbattitore) ────────────────────────────────
# Il DB non distingue "Frigo" da "Abbattitore": ModalRegistraLotto scrive
# entrambi nello stesso campo libero `frigo_numero` (vedi commenti lì) — qui
# contano insieme come "prodotto già pronto, non ancora portato al banco".
# Usato per avvisare l'operatore PRIMA di produrre di nuovo un prodotto che
# è già in giacenza (richiesta Enzo 03/07/2026: "non farmi produrre altri
# babà se ne abbiamo già in frigo/abbattitore, fammeli scalare al banco").
async def giacenza_prodotti_finiti(nomi: list) -> dict:
    """Per ogni nome prodotto in `nomi`: lotti di produzione non consumati/
    smaltiti, con `frigo_numero` valorizzato (= ancora in frigo/abbattitore,
    non al banco) e NON scaduti (uno scaduto non è più vendibile: non deve
    bloccare una nuova produzione). Ritorna {prodotto: {totale, lotti[]}}."""
    if not nomi:
        return {}
    from app.lotti.routers.utils import parse_data_flessibile
    oggi = date.today()
    out: dict = {}
    async for l in db.lotti.find(
        {
            "prodotto": {"$in": nomi},
            "frigo_numero": {"$nin": [None, ""]},
            "consumato": {"$ne": True},
            "esaurito": {"$ne": True},
            "stato": {"$nin": ["smaltito", "esaurito"]},
        },
        {"_id": 0, "id": 1, "prodotto": 1, "quantita": 1, "unita_misura": 1,
         "numero_lotto": 1, "frigo_numero": 1, "data_produzione": 1, "data_scadenza": 1},
    ):
        scad = parse_data_flessibile(l.get("data_scadenza"))
        if scad and scad < oggi:
            continue
        q = l.get("quantita") or 0
        if q <= 0:
            continue
        voce = out.setdefault(l["prodotto"], {"totale": 0, "lotti": []})
        voce["totale"] += q
        voce["lotti"].append({
            "id": l.get("id"), "numero_lotto": l.get("numero_lotto", ""),
            "quantita": q, "unita_misura": l.get("unita_misura", "pz"),
            "frigo_numero": l.get("frigo_numero", ""),
            "data_produzione": l.get("data_produzione", ""),
        })
    return out


@router.patch("/lotti/{lotto_id}/consuma")
async def marca_lotto_consumato(
    lotto_id: str,
    quantita: Optional[float] = Query(None),
    operatore_id: Optional[str] = Query(None),
    operatore_nome: Optional[str] = Query(None),
):
    """Marca il lotto come consumato/esaurito senza eliminarlo dal registro
    storico. Con `quantita` valorizzata consuma solo QUELLA quantità (consumo
    parziale, es. "mando 3 dei 5 babà in frigo al banco"): il lotto resta
    attivo con la quantità residua, `consumato=True` solo quando arriva a 0."""
    lotto = await db.lotti.find_one({"$or": [{"id": lotto_id}, {"lotto_id": lotto_id}]}, {"_id": 0})
    if not lotto:
        raise HTTPException(status_code=404, detail="Lotto non trovato")
    disponibile = lotto.get("quantita") or 0
    if quantita is None or quantita >= disponibile:
        quantita_consumata = disponibile
        update = {"consumato": True, "data_consumo": datetime.now(timezone.utc).isoformat(), "quantita": 0}
    else:
        if quantita <= 0:
            raise HTTPException(status_code=400, detail="quantita deve essere positiva")
        quantita_consumata = quantita
        update = {"quantita": round(disponibile - quantita, 3)}
    await db.lotti.update_one({"$or": [{"id": lotto_id}, {"lotto_id": lotto_id}]}, {"$set": update})
    try:
        from app.lotti.servizi.movimenti_lotto_service import registra_movimento
        await registra_movimento(
            lotto.get("id", lotto_id), "uso",
            numero_lotto=lotto.get("numero_lotto", ""),
            quantita=quantita_consumata,
            operatore_id=operatore_id or "", operatore_nome=operatore_nome or "",
            motivo="Consumo lotto",
        )
    except Exception:
        _LOG_INIT.exception("[lotti_produzione] registrazione movimento consumo fallita (non bloccante)")
    return {"message": "Lotto marcato come consumato", "quantita_residua": update.get("quantita", 0)}


@router.post("/lotti/{lotto_id}/manda-al-banco")
async def manda_lotto_al_banco(
    lotto_id: str,
    pezzi: float = Query(...),
    reparto: str = Query("pasticceria"),
    operatore_id: Optional[str] = Query(None),
    operatore_nome: Optional[str] = Query(None),
    operation_id: Optional[str] = Query(None),
):
    """Scala (in tutto o in parte) un lotto già in frigo/abbattitore e lo
    registra come inviato al banco — l'azione "Manda al banco" mostrata
    all'operatore quando tenta di produrre un prodotto già in giacenza,
    invece di fargliene produrre altro."""
    # IDEMPOTENZA (tranche 4): stesso operation_id → stesso risultato, mai
    # doppio scarico anche se la rete rispedisce la richiesta.
    if operation_id:
        try:
            await db.operazioni_idempotenti.insert_one(
                {"_id": f"banco_{operation_id}",
                 "creato": datetime.now(timezone.utc).isoformat()})
        except DuplicateKeyError:
            prec = await db.operazioni_idempotenti.find_one({"_id": f"banco_{operation_id}"})
            return (prec or {}).get("risultato") or {"ok": True, "gia_eseguita": True}
    lotto = await db.lotti.find_one({"id": lotto_id}, {"_id": 0})
    if not lotto:
        raise HTTPException(status_code=404, detail="Lotto non trovato")
    if lotto.get("stato") == "bloccato_richiamo":
        raise HTTPException(status_code=423,
            detail="Lotto BLOCCATO da richiamo: operazione non consentita (serve lo sblocco amministrativo)")
    disponibile = lotto.get("quantita") or 0
    if pezzi <= 0 or pezzi > disponibile:
        raise HTTPException(status_code=400, detail=f"Quantità non valida: disponibili {disponibile}")

    if pezzi >= disponibile:
        await db.lotti.update_one({"id": lotto_id}, {"$set": {
            "consumato": True, "data_consumo": datetime.now(timezone.utc).isoformat(), "quantita": 0}})
    else:
        await db.lotti.update_one({"id": lotto_id}, {"$set": {"quantita": round(disponibile - pezzi, 3)}})

    from app.lotti.routers.vendita_banco import registra_vendita_banco, VenditaBancoIn
    vendita = await registra_vendita_banco(VenditaBancoIn(
        prodotto_id=lotto_id,
        prodotto_nome=lotto.get("prodotto", ""),
        reparto=reparto,
        pezzi_prodotti=int(pezzi),
        lotto_id=lotto_id,
        numero_lotto=lotto.get("numero_lotto"),
        operatore_nome=operatore_nome,
        operatore_id=operatore_id,
    ))
    movimento_id = None
    try:
        from app.lotti.servizi.movimenti_lotto_service import registra_movimento, costruisci_posizione
        mov = await registra_movimento(
            lotto_id, "banco",
            numero_lotto=lotto.get("numero_lotto", ""),
            posizione_da=lotto.get("posizione"),
            posizione_a=costruisci_posizione(tipo="banco", reparto=reparto,
                                              operatore_id=operatore_id or "",
                                              operatore_nome=operatore_nome or "",
                                              quantita=pezzi),
            quantita=pezzi,
            operatore_id=operatore_id or "", operatore_nome=operatore_nome or "",
            motivo="Mandato al banco",
            documento_collegato={"tipo": "vendita_banco", "id": vendita.get("id")},
        )
        movimento_id = mov.get("id")
    except Exception:
        _LOG_INIT.exception("[lotti_produzione] registrazione movimento banco fallita (non bloccante)")
    # Richiesta Enzo 20/07/2026: "manda al banco" non diceva DA QUALE frigo/
    # congelatore veniva presa la merce, né dava modo di stamparne conferma —
    # ora la risposta porta tutto ciò che serve al frontend per confermarlo
    # (toast con la posizione) e stampare la distinta di movimentazione.
    _risposta = {
        "status": "ok", "lotto_id": lotto_id, "pezzi_mandati": pezzi, "vendita": vendita,
        "movimento_id": movimento_id,
        "prodotto": lotto.get("prodotto", ""),
        "numero_lotto": lotto.get("numero_lotto", ""),
        "frigo_numero": lotto.get("frigo_numero", ""),
    }
    if operation_id:
        await db.operazioni_idempotenti.update_one(
            {"_id": f"banco_{operation_id}"}, {"$set": {"risultato": _risposta}}, upsert=True)
    return _risposta

@router.patch("/lotti/{lotto_id}/smalti")
async def smalti_lotto(
    lotto_id: str,
    motivo: str = "smaltito_scaduto",
    note: str = "",
    operatore_id: Optional[str] = Query(None),
    operatore_nome: Optional[str] = Query(None),
):
    """
    Smaltisce formalmente un lotto scaduto o non conforme.
    Cambia stato in 'smaltito' e registra data + motivo per la tracciabilità HACCP.
    Reg. CE 852/2004 — obbligo di documentare lo smaltimento.
    """
    lotto = await db.lotti.find_one({"$or": [{"id": lotto_id}, {"lotto_id": lotto_id}]}, {"_id": 0})
    if not lotto:
        raise HTTPException(status_code=404, detail="Lotto non trovato")
    result = await db.lotti.update_one(
        {"$or": [{"id": lotto_id}, {"lotto_id": lotto_id}]},
        {
            "$set": {
                "stato": "smaltito",
                "esaurito": True,  # campo storico gemello: senza, i filtri sul flag lo vedono ancora "aperto"
                "motivo_smaltimento": motivo,
                "note_smaltimento": note,
                "data_smaltimento": datetime.now(timezone.utc).isoformat(),
                "smaltito_da": "operatore",
            }
        },
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Lotto non trovato")
    try:
        from app.lotti.servizi.movimenti_lotto_service import registra_movimento
        await registra_movimento(
            lotto.get("id", lotto_id), "smaltimento",
            numero_lotto=lotto.get("numero_lotto", ""),
            posizione_da=lotto.get("posizione"),
            quantita=lotto.get("quantita"),
            operatore_id=operatore_id or "", operatore_nome=operatore_nome or "",
            motivo=motivo, azione_correttiva_haccp=note or None,
        )
    except Exception:
        _LOG_INIT.exception("[lotti_produzione] registrazione movimento smaltimento fallita (non bloccante)")
    return {"status": "ok", "lotto_id": lotto_id, "motivo": motivo}


@router.post("/lotti/smalti-batch")
async def smalti_batch_lotti(
    payload: dict,
    motivo: str = "smaltito_scaduto",
    operatore_id: Optional[str] = Query(None),
    operatore_nome: Optional[str] = Query(None),
):
    """
    Smaltisce in batch i lotti IDs forniti.
    Body: {"ids": ["id1", "id2", ...]}
    Aggiunge campo 'stato: smaltito' anche ai lotti che non lo avevano.
    """
    lotti_ids = payload.get("ids", [])
    if not lotti_ids:
        return {"smaltiti": 0}
    lotti_prima = await db.lotti.find(
        {"id": {"$in": lotti_ids}}, {"_id": 0, "id": 1, "numero_lotto": 1, "quantita": 1, "posizione": 1}
    ).to_list(len(lotti_ids))
    result = await db.lotti.update_many(
        {"id": {"$in": lotti_ids}},
        {
            "$set": {
                "stato": "smaltito",
                "esaurito": True,
                "motivo_smaltimento": motivo,
                "data_smaltimento": datetime.now(timezone.utc).isoformat(),
            }
        },
    )
    try:
        from app.lotti.servizi.movimenti_lotto_service import registra_movimento
        for lt in lotti_prima:
            await registra_movimento(
                lt.get("id"), "smaltimento",
                numero_lotto=lt.get("numero_lotto", ""),
                posizione_da=lt.get("posizione"),
                quantita=lt.get("quantita"),
                operatore_id=operatore_id or "", operatore_nome=operatore_nome or "",
                motivo=motivo,
            )
    except Exception:
        _LOG_INIT.exception("[lotti_produzione] registrazione movimenti smaltimento batch fallita (non bloccante)")
    return {"smaltiti": result.modified_count}


@router.post("/lotti/{lotto_id}/sposta-posizione")
async def sposta_posizione_lotto(
    lotto_id: str,
    tipo: str = Query(..., description="frigo|congelatore|abbattitore|banco|magazzino"),
    numero: str = Query("", description="Numero/nome apparecchio (es. 'Frigorifero N°1')"),
    nome: str = Query("", description="Nome leggibile, se diverso dal numero"),
    reparto: str = Query(""),
    motivo: str = Query(""),
    operatore_id: Optional[str] = Query(None),
    operatore_nome: Optional[str] = Query(None),
):
    """Sposta un lotto da una posizione all'altra (Tranche 1 — Cosa usare
    oggi / Gemello digitale del lotto). Aggiorna `posizione` strutturata E
    `frigo_numero` (retrocompatibilità con LottiList/ModalRegistraLotto/
    stampa/supervisor_operativo, che leggono ancora quel campo)."""
    lotto = await db.lotti.find_one({"id": lotto_id}, {"_id": 0})
    if not lotto:
        raise HTTPException(status_code=404, detail="Lotto non trovato")

    from app.lotti.servizi.movimenti_lotto_service import costruisci_posizione, registra_movimento

    posizione_da = lotto.get("posizione")
    posizione_a = costruisci_posizione(
        tipo=tipo, numero=numero or nome, nome=nome or numero, reparto=reparto,
        operatore_id=operatore_id or "", operatore_nome=operatore_nome or "",
        quantita=lotto.get("quantita"),
    )
    if posizione_a is None:
        raise HTTPException(status_code=400, detail="Tipo o numero posizione mancante")

    update = {"posizione": posizione_a}
    # frigo_numero storico: valorizzato per frigo/congelatore/abbattitore, svuotato per banco/magazzino
    update["frigo_numero"] = posizione_a["numero"] if posizione_a["tipo"] in ("frigo", "congelatore", "abbattitore") else ""
    await db.lotti.update_one({"id": lotto_id}, {"$set": update})

    try:
        await registra_movimento(
            lotto_id, "spostamento",
            numero_lotto=lotto.get("numero_lotto", ""),
            posizione_da=posizione_da, posizione_a=posizione_a,
            quantita=lotto.get("quantita"),
            operatore_id=operatore_id or "", operatore_nome=operatore_nome or "",
            motivo=motivo or "Spostamento posizione",
        )
    except Exception:
        _LOG_INIT.exception("[lotti_produzione] registrazione movimento spostamento fallita (non bloccante)")
    return {"status": "ok", "lotto_id": lotto_id, "posizione": posizione_a}


@router.post("/lotti/{lotto_id}/congela")
async def congela_lotto(
    lotto_id: str,
    numero: str = Query("", description="Numero/nome congelatore"),
    nome: str = Query(""),
    motivo: str = Query(""),
    operatore_id: Optional[str] = Query(None),
    operatore_nome: Optional[str] = Query(None),
):
    """Congela un lotto già prodotto: sposta in congelatore e allunga la
    scadenza al valore da abbattitore negativo. Se il lotto è nato da
    produzione ha già `scadenza_abbattuto` calcolata (vedi
    registra-produzione-lotto); altrimenti la ricalcola dagli ingredienti
    con il motore shelf_life.py (stessa fonte usata ovunque — mai
    inventare una shelf-life qui)."""
    lotto = await db.lotti.find_one({"id": lotto_id}, {"_id": 0})
    if not lotto:
        raise HTTPException(status_code=404, detail="Lotto non trovato")

    nuova_scadenza = lotto.get("scadenza_abbattuto")
    if not nuova_scadenza:
        from app.lotti.routers.utils import _calcola_scadenza
        ingredienti_nomi = lotto.get("ingredienti_dettaglio") or []
        try:
            scad = _calcola_scadenza(
                ingredienti_nomi, lotto.get("data_produzione") or datetime.now().strftime("%d/%m/%Y"),
                nome_prodotto=lotto.get("prodotto", ""), metodo_conservazione="abbattitore_negativo",
            )
            nuova_scadenza = scad[1] or scad[0]
        except Exception:
            _LOG_INIT.exception("[lotti_produzione] ricalcolo scadenza congelamento fallito")
            nuova_scadenza = lotto.get("data_scadenza")

    from app.lotti.servizi.movimenti_lotto_service import costruisci_posizione, registra_movimento

    posizione_da = lotto.get("posizione")
    posizione_a = costruisci_posizione(
        tipo="congelatore", numero=numero or nome, nome=nome or numero,
        operatore_id=operatore_id or "", operatore_nome=operatore_nome or "",
        quantita=lotto.get("quantita"),
    )
    update = {
        "data_scadenza_pre_congelamento": lotto.get("data_scadenza"),
        "data_scadenza": nuova_scadenza,
        "congelato_il": datetime.now(timezone.utc).isoformat(),
    }
    if posizione_a:
        update["posizione"] = posizione_a
        update["frigo_numero"] = posizione_a["numero"]
    await db.lotti.update_one({"id": lotto_id}, {"$set": update})

    try:
        await registra_movimento(
            lotto_id, "congelamento",
            numero_lotto=lotto.get("numero_lotto", ""),
            posizione_da=posizione_da, posizione_a=posizione_a,
            quantita=lotto.get("quantita"),
            operatore_id=operatore_id or "", operatore_nome=operatore_nome or "",
            motivo=motivo or f"Congelato — nuova scadenza {nuova_scadenza}",
        )
    except Exception:
        _LOG_INIT.exception("[lotti_produzione] registrazione movimento congelamento fallita (non bloccante)")
    return {"status": "ok", "lotto_id": lotto_id, "data_scadenza": nuova_scadenza, "posizione": posizione_a}


@router.post("/lotti/{lotto_id}/recupera")
async def recupera_lotto(
    lotto_id: str,
    quantita: Optional[float] = Query(None, description="Quantità recuperata; default: tutta la residua"),
    motivo: str = Query("", description="Es. nome della nuova preparazione in cui viene riutilizzato"),
    operatore_id: Optional[str] = Query(None),
    operatore_nome: Optional[str] = Query(None),
    # AUDIT 25/07/2026: il corpo usava `operation_id` senza averlo mai
    # dichiarato → NameError, quindi errore 500 a OGNI tocco di "Recupera".
    operation_id: Optional[str] = Query(None),
):
    """Segna un lotto (in tutto o in parte) come recuperato per l'uso in
    una nuova produzione — es. pan di spagna avanzato tagliato per un'altra
    torta. Scala la quantità come un consumo; l'operatore poi seleziona
    questo lotto come componente quando registra la nuova produzione
    (meccanismo `lotti_componenti` già esistente, che collega i due lotti
    nella tracciabilità/recall). Qui NON si forza un lotto di destinazione:
    a differenza di 'consuma', l'evento registrato è 'recupero' per essere
    distinguibile in cronologia da uno scarto/uso normale."""
    # IDEMPOTENZA (tranche 4): stesso operation_id → stesso risultato, mai
    # doppio scarico anche se la rete rispedisce la richiesta.
    if operation_id:
        try:
            await db.operazioni_idempotenti.insert_one(
                {"_id": f"banco_{operation_id}",
                 "creato": datetime.now(timezone.utc).isoformat()})
        except DuplicateKeyError:
            prec = await db.operazioni_idempotenti.find_one({"_id": f"banco_{operation_id}"})
            return (prec or {}).get("risultato") or {"ok": True, "gia_eseguita": True}
    lotto = await db.lotti.find_one({"id": lotto_id}, {"_id": 0})
    if not lotto:
        raise HTTPException(status_code=404, detail="Lotto non trovato")
    if lotto.get("stato") == "bloccato_richiamo":
        raise HTTPException(status_code=423,
            detail="Lotto BLOCCATO da richiamo: operazione non consentita (serve lo sblocco amministrativo)")
    disponibile = lotto.get("quantita") or 0
    if quantita is None or quantita >= disponibile:
        quantita_recuperata = disponibile
        update = {"consumato": True, "data_consumo": datetime.now(timezone.utc).isoformat(), "quantita": 0}
    else:
        if quantita <= 0:
            raise HTTPException(status_code=400, detail="quantita deve essere positiva")
        quantita_recuperata = quantita
        update = {"quantita": round(disponibile - quantita, 3)}
    await db.lotti.update_one({"id": lotto_id}, {"$set": update})

    try:
        from app.lotti.servizi.movimenti_lotto_service import registra_movimento
        await registra_movimento(
            lotto_id, "recupero",
            numero_lotto=lotto.get("numero_lotto", ""),
            posizione_da=lotto.get("posizione"),
            quantita=quantita_recuperata,
            operatore_id=operatore_id or "", operatore_nome=operatore_nome or "",
            motivo=motivo or "Recuperato in nuova produzione",
        )
    except Exception:
        _LOG_INIT.exception("[lotti_produzione] registrazione movimento recupero fallita (non bloccante)")
    _risposta = {"status": "ok", "lotto_id": lotto_id, "quantita_recuperata": quantita_recuperata,
                 "quantita_residua": update.get("quantita", 0)}
    # Se la rete rispedisce la stessa richiesta, il secondo giro deve
    # restituire la STESSA risposta, non un generico "già eseguita".
    if operation_id:
        await db.operazioni_idempotenti.update_one(
            {"_id": f"banco_{operation_id}"}, {"$set": {"risultato": _risposta}}, upsert=True)
    return _risposta


# ── Anteprima codice lotto ────────────────────────────────────────────────────


@router.get("/anteprima-codice-lotto/{prodotto}")
async def anteprima_codice_lotto(
    prodotto: str,
    quantita: float = Query(1),
    unita_misura: str = Query(None),
    data_produzione: str = Query(...),
):
    """Genera un'anteprima del codice lotto SENZA salvare."""
    if not unita_misura:
        unita_misura = determina_unita_misura(prodotto)
    chiave = genera_abbreviazione_prodotto(prodotto)
    contatore = await db.contatori_lotti.find_one({"prodotto_chiave": chiave}, {"_id": 0})
    prossimo = (contatore.get("progressivo", 0) if contatore else 0) + 1
    codice_lotto = genera_codice_lotto(prodotto, prossimo, quantita, unita_misura, data_produzione)
    abbreviazione = genera_abbreviazione_prodotto(prodotto)
    return {
        "codice_lotto": codice_lotto,
        "abbreviazione": abbreviazione,
        "progressivo": prossimo,
        "quantita": quantita,
        "unita_misura": unita_misura,
        "formato": f"{abbreviazione}-{prossimo:03d}-{int(quantita) if quantita == int(quantita) else quantita}{unita_misura}-DDMMYYYY",
    }


# ── Unità di misura ───────────────────────────────────────────────────────────


@router.get("/unita-misura/{prodotto}")
async def get_unita_misura(prodotto: str):
    unita = determina_unita_misura(prodotto)
    return {"prodotto": prodotto, "unita_misura": unita}


@router.get("/prodotti-in-kg")
async def get_prodotti_in_kg():
    return {"prodotti": PRODOTTI_IN_KG}


# ── Scala lotti fornitori (FIFO) ──────────────────────────────────────────────


def _parse_data_fattura(s):
    """Converte una data fattura ('DD/MM/YYYY' o ISO) in datetime ordinabile.
    Senza data valida → datetime.max, così il lotto va consumato per ultimo."""
    s = (str(s or "")).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(s, fmt)
        except (ValueError, TypeError):
            continue
    return datetime.max


async def _candidati_lotti_fifo(ing: dict) -> list:
    """Trova i lotti_fornitori candidati per un ingrediente e li ordina FIFO
    (data fattura piu' vecchia, poi scadenza). NON consuma nulla: e' la base
    CONDIVISA tra lo scarico in produzione (scala_lotti_fornitori_per_ricetta) e
    il peek del lotto attivo (peek_lotto_fifo_attivo). Un solo criterio FIFO."""
    nome_ing = (ing.get("nome") or "").strip()
    if not nome_ing:
        return []
    nome_norm = nome_ing.lower().strip()
    parole = [p for p in nome_norm.split() if len(p) > 2]

    search_patterns = [nome_norm]
    if len(parole) >= 2:
        search_patterns.append(" ".join(parole[:2]))
    if len(parole) >= 1 and len(parole[0]) >= 5:
        search_patterns.append(parole[0])

    try:
        diz_entry = await db.dizionario_prodotti.find_one(
            {
                "$or": [
                    {"nome_normalizzato": {"$regex": re.escape(nome_norm[:20]), "$options": "i"}},
                    {"aliases": {"$elemMatch": {"$regex": re.escape(nome_norm[:20]), "$options": "i"}}},
                ]
            },
            {"_id": 0, "aliases": 1, "nome_normalizzato": 1},
        )
        if diz_entry:
            for alias in diz_entry.get("aliases") or []:
                alias_parole = alias.split()
                if alias_parole:
                    p = " ".join(alias_parole[:2])
                    if p not in search_patterns and len(p) >= 3:
                        search_patterns.append(p)
    except Exception:
        _LOG_INIT.debug("[lotti_produzione] errore non bloccante ignorato")

    canonico = (ing.get("ingrediente_canonico") or "").strip()
    if not canonico:
        try:
            from app.lotti.routers.lotti_fornitori import calcola_nome_canonico
            canonico = (await calcola_nome_canonico(nome_ing, usa_llm=False)) or ""
        except Exception:
            canonico = ""

    lotti_candidati = []
    _proj = {
        "_id": 0, "id": 1, "lotto_id_fornitore": 1, "fornitore": 1,
        "prodotto_nome": 1, "quantita_disponibile": 1, "unita_misura": 1,
        "data_fattura": 1, "data_scadenza": 1, "esaurito": 1,
        "fattura_ref": 1, "allergeni_testo": 1,
    }
    if canonico:
        can_low = canonico.lower().strip()
        lotti_can = (
            await db.lotti_fornitori.find(
                {
                    "esaurito": {"$ne": True},
                    "quantita_disponibile": {"$gt": 0},
                    "$or": [
                        {"nome_canonico": {"$regex": f"^{re.escape(canonico)}$", "$options": "i"}},
                        {"prodotto_nome_norm": can_low},
                    ],
                },
                _proj,
            ).to_list(2000)
        )
        for lotto_f in lotti_can:
            if not any(x["id"] == lotto_f["id"] for x in lotti_candidati):
                lotti_candidati.append(lotto_f)

    if not lotti_candidati:
        for pattern in search_patterns:
            if len(pattern) < 3:
                continue
            lotti_trovati = (
                await db.lotti_fornitori.find(
                    {
                        "esaurito": {"$ne": True},
                        "quantita_disponibile": {"$gt": 0},
                        "prodotto_nome_norm": {"$regex": re.escape(pattern), "$options": "i"},
                    },
                    _proj,
                ).to_list(2000)
            )
            for lotto_f in lotti_trovati:
                if not any(x["id"] == lotto_f["id"] for x in lotti_candidati):
                    lotti_candidati.append(lotto_f)
            if lotti_candidati:
                break

    # REGOLA ENZO 23/07/2026: l'ingrediente si associa al lotto più vecchio
    # DEGLI ULTIMI 60 GIORNI — un lotto di mesi/anni fa non rappresenta più il
    # fornitore reale in etichetta. I lotti oltre i 60gg NON si buttano: vanno
    # in coda come riserva per lo scarico (ordinati dal più recente), così la
    # giacenza vecchia si consuma comunque se quella recente finisce. Se non
    # c'è NULLA negli ultimi 60gg, si usa il più recente disponibile.
    _chiave = lambda l: (  # noqa: E731 — FIFO: fattura più vecchia, poi scadenza
        _parse_data_fattura(l.get("data_fattura")),
        _parse_data_fattura(l.get("data_scadenza")),
    )
    soglia = datetime.now() - timedelta(days=60)
    recenti = [l for l in lotti_candidati
               if _parse_data_fattura(l.get("data_fattura")) >= soglia]
    ids_recenti = {l["id"] for l in recenti}
    vecchi = [l for l in lotti_candidati if l["id"] not in ids_recenti]
    recenti.sort(key=_chiave)                    # più vecchio dei recenti PRIMA
    vecchi.sort(key=_chiave, reverse=True)       # riserva: dal più recente
    return recenti + vecchi


# Peso in grammi del singolo pezzo, per convertire lotti in PZ ↔ ricette in
# g/kg. Regola uova di Enzo: uovo 60 g, tuorlo 19 g, albume 33 g.
async def _peso_pezzo_g_per_ing(nome_ing: str) -> float:
    n = (nome_ing or "").lower()
    if "tuorl" in n:
        return 19.0
    if "album" in n:
        return 33.0
    if "uov" in n:
        return 60.0
    doc = await db.dizionario_prodotti.find_one(
        {"peso_pezzo_g": {"$gt": 0}, "$or": [
            {"ingrediente_canonico": {"$regex": f"^{re.escape(nome_ing)}$", "$options": "i"}},
            {"nome_canonico": {"$regex": f"^{re.escape(nome_ing)}$", "$options": "i"}},
        ]},
        {"_id": 0, "peso_pezzo_g": 1},
    )
    return float(doc["peso_pezzo_g"]) if doc and doc.get("peso_pezzo_g") else 0.0


def _fattore_lotto_vs_ing(unita_lotto: str, unita_ing: str, peso_pezzo_g: float):
    """Quante unità-INGREDIENTE vale 1 unità-LOTTO. None = non convertibile
    (si ricade sul confronto diretto storico). Peso≈volume (densità 1) come
    nel comportamento esistente KG↔LT."""
    ul = (unita_lotto or "").strip().upper()
    ui = (unita_ing or "").strip().lower()
    PESO_KG = ("KG", "LT", "L")          # kg / litri equivalenti
    PESO_G = ("G", "GR", "ML")
    PEZZI_L = ("PZ", "NR", "N", "CF", "CONF", "PZE")
    if ul in PESO_KG:
        if ui in ("kg", "lt", "l"):
            return 1.0
        if ui in ("g", "ml"):
            return 1000.0
        if ui in ("pz", "pezzi", "cf") and peso_pezzo_g > 0:
            return 1000.0 / peso_pezzo_g
    elif ul in PESO_G:
        if ui in ("g", "ml"):
            return 1.0
        if ui in ("kg", "lt", "l"):
            return 0.001
        if ui in ("pz", "pezzi", "cf") and peso_pezzo_g > 0:
            return 1.0 / peso_pezzo_g
    elif ul in PEZZI_L:
        if ui in ("pz", "pezzi", "cf"):
            return 1.0
        if peso_pezzo_g > 0:
            if ui in ("g", "ml"):
                return peso_pezzo_g
            if ui in ("kg", "lt", "l"):
                return peso_pezzo_g / 1000.0
    return None


async def peek_lotto_fifo_attivo(ing: dict) -> Optional[dict]:
    """Ritorna il lotto fornitore FIFO-ATTIVO per un ingrediente (il piu' vecchio
    per data_fattura con giacenza residua) SENZA consumarlo. Single source per
    "da dove arriva OGGI questo ingrediente" — sostituisce i campi congelati
    all'import (fornitore/numero_fattura/data_fattura) che davano il last-wins."""
    candidati = await _candidati_lotti_fifo(ing)
    return candidati[0] if candidati else None


async def scala_lotti_fornitori_per_ricetta(
    ricetta: dict, moltiplicatore: float, numero_lotto_produzione: str
) -> dict:
    """Scala automaticamente i lotti fornitori per ogni ingrediente (FIFO)."""
    ingredienti_dettaglio = ricetta.get("ingredienti_dettaglio", [])
    lotti_scalati = []
    lotti_esauriti = []
    ingredienti_non_trovati = []
    ingredienti_insufficienti = []
    conversioni_non_disponibili = []

    for ing in ingredienti_dettaglio:
        nome_ing = ing.get("nome", "").strip()
        if not nome_ing:
            continue
        try:
            quantita_base = float(str(ing.get("quantita", 0) or 0).replace(",", "."))
        except (ValueError, TypeError):
            continue
        if quantita_base <= 0:
            continue
        unita = ing.get("unita_misura") or ing.get("unita", "g")
        quantita_scalata = quantita_base * moltiplicatore

        lotti_candidati = await _candidati_lotti_fifo(ing)
        if not lotti_candidati:
            ingredienti_non_trovati.append(nome_ing)
            continue
        # (candidati gia' ordinati FIFO dal helper condiviso)

        quantita_rimasta = quantita_scalata  # nell'unità della RICETTA
        peso_pezzo_g = await _peso_pezzo_g_per_ing(nome_ing)
        for lotto in lotti_candidati:
            if quantita_rimasta <= 0:
                break
            qt_lotto_disp = float(lotto.get("quantita_disponibile", 0) or 0)
            unita_lotto = lotto.get("unita_misura", "PZ").upper()
            # CONVERSIONE tra famiglie di unità (fix 02/07/2026): prima un
            # lotto uova in PZ contro una ricetta in grammi veniva confrontato
            # numero-contro-numero, bruciando TUTTE le giacenze in un colpo.
            fattore = _fattore_lotto_vs_ing(unita_lotto, unita, peso_pezzo_g)
            if fattore and fattore > 0:
                disp_in_ing = qt_lotto_disp * fattore
                consumo_ing = min(disp_in_ing, quantita_rimasta)
                qt_da_consumare = consumo_ing / fattore     # in unità-LOTTO
            else:
                # FIX 24/07/2026 (tranche 4): unità NON convertibili (es. lotto
                # in CT e ricetta in g senza contenuto confezione censito) →
                # NON si scala per approssimazione: lotto saltato e segnalato.
                conversioni_non_disponibili.append({
                    "ingrediente": nome_ing, "lotto_id": lotto["id"],
                    "prodotto": lotto.get("prodotto_nome", ""),
                    "unita_lotto": unita_lotto, "unita_ricetta": unita,
                })
                continue
            qt_nuova = max(0, qt_lotto_disp - qt_da_consumare)
            esaurito = qt_nuova <= 0.001
            await db.lotti_fornitori.update_one(
                {"id": lotto["id"]},
                {
                    "$set": {
                        "quantita_disponibile": round(qt_nuova, 3),
                        "esaurito": esaurito,
                        "ultimo_utilizzo": datetime.now(timezone.utc).isoformat(),
                        "ricetta_ultimo_utilizzo": ricetta.get("nome", ""),
                    },
                    "$push": {
                        "storico_utilizzi": {
                            "data": datetime.now(timezone.utc).isoformat(),
                            "quantita_usata": round(qt_da_consumare, 3),
                            "ricetta": ricetta.get("nome", ""),
                            "lotto_produzione": numero_lotto_produzione,
                            "quantita_rimasta": round(qt_nuova, 3),
                        }
                    },
                },
            )
            lotti_scalati.append(
                {
                    "ingrediente": nome_ing,
                    "lotto_id": lotto["id"],
                    "lotto_id_fornitore": lotto.get("lotto_id_fornitore", ""),
                    "fornitore": lotto.get("fornitore", ""),
                    "prodotto": lotto.get("prodotto_nome", ""),
                    "quantita_consumata": round(qt_da_consumare, 3),
                    "quantita_rimasta": round(qt_nuova, 3),
                    "unita": unita_lotto,
                    "esaurito": esaurito,
                }
            )
            if esaurito:
                lotti_esauriti.append(
                    {
                        "lotto_id": lotto["id"],
                        "prodotto": lotto.get("prodotto_nome", ""),
                        "fornitore": lotto.get("fornitore", ""),
                    }
                )
            quantita_rimasta -= consumo_ing

        # FIX 24/07/2026 (audit flussi): se i lotti non coprono il fabbisogno,
        # il mancante NON va più ignorato in silenzio — si segnala quanto
        # manca (in unità-ricetta), così tablet e riordini lo vedono.
        if quantita_rimasta > 0.001:
            ingredienti_insufficienti.append({
                "ingrediente": nome_ing,
                "richiesto": round(quantita_scalata, 3),
                "mancante": round(quantita_rimasta, 3),
                "unita": unita,
            })

    return {
        "lotti_scalati": lotti_scalati,
        "lotti_esauriti": lotti_esauriti,
        "ingredienti_non_trovati": ingredienti_non_trovati,
        "ingredienti_insufficienti": ingredienti_insufficienti,
        "conversioni_non_disponibili": conversioni_non_disponibili,
    }


async def _riordini_post_produzione(lotti_scalati, ricetta_nome: str):
    """MOTORE UNICO post-produzione (02/07/2026, richiesta Enzo: "se produco una
    ricetta e la giacenza scende al punto di riordino, l'ordine deve partire
    dalle ricette"). Dopo il consumo FIFO, per ogni ingrediente scalato:
    1. calcola la disponibilità VERA residua dai lotti fornitori (il campo
       dizionario.quantita_disponibile_kg era STANTIO: si aggiornava solo
       all'import fatture, quindi il vecchio check non scattava mai);
    2. la sincronizza sul dizionario (così anche il giro delle 07:00 e i
       prodotti-suggeriti vedono il consumo);
    3. se sotto scorta_minima O esaurita → bozza riordino via
       aggiungi_a_bozza_riordino (per fornitore, miglior prezzo, dedup
       incrociata su tutti gli ordini aperti).
    Sostituisce DUE vecchi percorsi paralleli: 'automatico_scorta' (bozza
    cumulativa su campo stantio) e 'automatico_lotti' (righe qty=1 senza id).
    Best-effort: non blocca mai la produzione."""
    from app.lotti.routers.ordini_fornitori import aggiungi_a_bozza_riordino
    esiti = []
    visti = set()
    for ls in (lotti_scalati or []):
        nome_ing = (ls.get("ingrediente") or "").strip()
        k = nome_ing.lower()
        if not nome_ing or k in visti:
            continue
        visti.add(k)
        try:
            # match ancorato: il contains-match sul prefisso agganciava il
            # primo prodotto arbitrario che conteneva la stringa
            diz = await db.dizionario_prodotti.find_one(
                {"$or": [
                    {"ingrediente_canonico": {"$regex": f"^{re.escape(nome_ing)}$", "$options": "i"}},
                    {"nome_canonico": {"$regex": f"^{re.escape(nome_ing)}$", "$options": "i"}},
                    {"nome_normalizzato": {"$regex": f"^{re.escape(k[:60])}", "$options": "i"}},
                ]},
                {"_id": 0, "id": 1, "nome_normalizzato": 1, "nome_canonico": 1,
                 "scorta_minima": 1, "unita_confezione": 1},
            )
            # disponibilità vera residua dai lotti fornitori (fonte di verità
            # FIFO), CONVERTITA in kg per unità del lotto: prima 180 PZ di
            # uova venivano sommati come "180 kg" e scritti nel dizionario
            prodotto_lotto = (ls.get("prodotto") or nome_ing).lower()
            parole = [w for w in prodotto_lotto.split() if len(w) > 2]
            pattern = " ".join(parole[:2]) or prodotto_lotto
            agg = await db.lotti_fornitori.aggregate([
                {"$match": {"esaurito": {"$ne": True},
                            "prodotto_nome_norm": {"$regex": rf"^{re.escape(pattern)}(?![a-z0-9])",
                                                     "$options": "i"}}},
                {"$group": {"_id": {"$toUpper": {"$ifNull": ["$unita_misura", "PZ"]}},
                            "tot": {"$sum": "$quantita_disponibile"}}},
            ]).to_list(20)
            peso_pz = await _peso_pezzo_g_per_ing(nome_ing)
            rimasti = 0.0
            non_convertibile = False
            for gr in agg:
                fatt = _fattore_lotto_vs_ing(str(gr.get("_id") or "PZ"), "kg", peso_pz)
                if fatt and fatt > 0:
                    rimasti += float(gr.get("tot") or 0) * fatt
                elif float(gr.get("tot") or 0) > 0:
                    non_convertibile = True
            if non_convertibile and rimasti <= 0:
                # nessun dato convertibile in kg: meglio non scrivere numeri
                # sbagliati né generare ordini fantasma
                continue
            scorta_min = float((diz or {}).get("scorta_minima") or 0)
            if diz:
                await db.dizionario_prodotti.update_one(
                    {"id": diz["id"]},
                    {"$set": {"quantita_disponibile_kg": round(max(rimasti, 0), 3)}},
                )
            sotto = (scorta_min > 0 and rimasti < scorta_min) or rimasti <= 0.001
            if not sotto:
                continue
            qta = round(max(scorta_min * 2 - rimasti, 1), 2) if scorta_min > 0 else 1
            nome_ord = ((diz or {}).get("nome_canonico") or nome_ing).title()
            r = await aggiungi_a_bozza_riordino(
                nome=nome_ord,
                prodotto_id=(diz or {}).get("id") or "",
                quantita=qta,
                unita="kg",  # qta è calcolata in kg (scorta e residuo in kg)
                richiesto_da=f"produzione {ricetta_nome}",
                nota=f"sotto scorta dopo produzione {ricetta_nome} (residuo {rimasti:.2f} kg)",
            )
            esiti.append({"prodotto": nome_ord, "residuo": round(rimasti, 3),
                          "gia_in_ordine": bool(r.get("gia_in_ordine"))})
        except Exception:
            _LOG_INIT.debug("[lotti_produzione] riordino post-produzione non bloccante")
    return esiti


# ── Registra produzione e crea lotto ─────────────────────────────────────────


@router.post("/registra-produzione-lotto")
async def registra_produzione_e_crea_lotto(
    ricetta_id: str = Query(...),
    pezzi: int = Query(...),
    pezzi_base: int = Query(...),
    costo_totale: float = Query(...),
    data_produzione: str = Query(...),
    frigo_numero: str = Query(None),
    lotti_componenti_json: Optional[str] = Query(None),
    operatore_id: Optional[str] = Query(None),  # ← dipendente tablet
    operatore_nome: Optional[str] = Query(None),  # ← nome leggibile
    data_scadenza: Optional[str] = Query(None),   # ← scadenza corretta a mano dal tablet
    memorizza_durata: bool = Query(False),        # ← ricorda la durata per questo prodotto
    operation_id: Optional[str] = Query(None),    # ← idempotenza doppio tocco (tranche 4)
):
    """
    Registra una produzione e:
    1. Salva l'evento nella collection produzioni
    2. Scala i lotti fornitori in modo FIFO
    3. Crea un lotto di produzione
    """
    if operation_id:
        try:
            await db.operazioni_idempotenti.insert_one(
                {"_id": f"prod_{operation_id}",
                 "creato": datetime.now(timezone.utc).isoformat()})
        except DuplicateKeyError:
            prec = await db.operazioni_idempotenti.find_one({"_id": f"prod_{operation_id}"})
            return (prec or {}).get("risultato") or {"ok": True, "gia_eseguita": True}
    ricetta = await db.ricette.find_one({"id": ricetta_id}, {"_id": 0})
    if not ricetta:
        raise HTTPException(status_code=404, detail=f"Ricetta con id '{ricetta_id}' non trovata")

    try:
        dt = datetime.strptime(data_produzione, "%Y-%m-%d")
        data_fmt = dt.strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        data_fmt = data_produzione

    porzioni_base = float(ricetta.get("porzioni", pezzi_base) or pezzi_base)
    moltiplicatore = pezzi / porzioni_base if porzioni_base > 0 else 1

    # Scala lotti fornitori
    lotti_info = await scala_lotti_fornitori_per_ricetta(ricetta, moltiplicatore, "TEMP")
    # Punto 3: se in produzione si esaurisce l'ULTIMO lotto di un prodotto → bozza ordine automatica
    try:
        lotti_info["da_riordinare"] = await _riordini_post_produzione(lotti_info.get("lotti_scalati", []), ricetta.get("nome", ""))
    except Exception:
        lotti_info["da_riordinare"] = []

    # Genera lotto
    progressivo = await get_prossimo_progressivo(ricetta["nome"])
    unita = determina_unita_misura(ricetta["nome"])
    numero_lotto = genera_codice_lotto(ricetta["nome"], progressivo, pezzi, unita, data_produzione)

    # Aggiorna numero lotto nei lotti scalati: lo scarico FIFO è avvenuto con
    # placeholder "TEMP" (il numero si genera solo ora) — senza questo update
    # lo storico_utilizzi restava "TEMP" per sempre e il RECALL per lotto
    # fornitore non risaliva mai ai lotti di produzione coinvolti.
    for ls in lotti_info["lotti_scalati"]:
        await db.lotti_fornitori.update_one(
            {"id": ls["lotto_id"]},
            {"$set": {"ricetta_ultimo_utilizzo": ricetta["nome"],
                      "storico_utilizzi.$[u].lotto_produzione": numero_lotto}},
            array_filters=[{"u.lotto_produzione": "TEMP"}],
        )

    from app.lotti.routers.utils import _calcola_scadenza, _rileva_allergeni

    # Calcola scadenza dalla deperibilità degli ingredienti
    ingredienti_nomi = [ing.get("nome", "") for ing in ricetta.get("ingredienti_dettaglio", [])]
    if not ingredienti_nomi:
        ingredienti_nomi = ricetta.get("ingredienti", [])
    scad_info = _calcola_scadenza(ingredienti_nomi, data_produzione, nome_prodotto=ricetta.get("nome", ""))
    data_scad_frigo = scad_info[0]  # formato "dd/mm/yyyy"
    data_scad_abb = scad_info[1]
    ing_critico = scad_info[2]
    giorni_frigo = scad_info[3]
    mesi_abb = scad_info[5]
    # Durata memorizzata per il prodotto (correzioni precedenti di Enzo)
    data_scad_frigo, giorni_frigo = _scadenza_con_override(ricetta, data_produzione, data_scad_frigo, giorni_frigo)

    # Scadenza corretta A MANO dal tablet: vince su tutto; se richiesto, la
    # durata (giorni dalla produzione) viene memorizzata sulla ricetta così le
    # prossime produzioni partono già giuste (es. panettone artigianale 90gg,
    # non "domani" per via delle uova).
    if data_scadenza:
        dt_scad = _parse_data_prod(data_scadenza)
        dt_prod = _parse_data_prod(data_produzione)
        if dt_scad:
            data_scad_frigo = dt_scad.strftime("%d/%m/%Y")
            if dt_prod:
                giorni_custom = (dt_scad - dt_prod).days
                if giorni_custom > 0:
                    giorni_frigo = giorni_custom
                    if memorizza_durata and giorni_custom <= 730:
                        await db.ricette.update_one(
                            {"id": ricetta_id},
                            {"$set": {"scadenza_giorni_override": giorni_custom}})

    allergeni_info = _rileva_allergeni(ingredienti_nomi)

    lotto_doc = {
        "id": str(uuid.uuid4()),
        "prodotto": ricetta["nome"],
        "ingredienti_dettaglio": [
            ing.get("nome", "") for ing in ricetta.get("ingredienti_dettaglio", [])
        ],
        "data_produzione": data_fmt,
        "data_scadenza": data_scad_frigo,
        "numero_lotto": numero_lotto,
        "etichetta": f"{ricetta['nome']} - prodotto il giorno {data_fmt}",
        "quantita": pezzi,
        "unita_misura": unita,
        "costo_totale": costo_totale,
        "costo_pezzo": round(costo_totale / pezzi, 4) if pezzi > 0 else 0,
        "progressivo": progressivo,
        "frigo_numero": frigo_numero or "",
        "lotti_fornitori": lotti_info,
        "scadenza_abbattuto": data_scad_abb,
        "mesi_abbattuto": mesi_abb,
        "ingrediente_critico": ing_critico,
        "conservazione_note": f"Frigo (0-4°C): {giorni_frigo} giorni | Abbattuto (-18°C): {mesi_abb} mesi",
        "allergeni_testo": allergeni_info.get("testo_etichetta", ""),
        "allergeni_presenti": allergeni_info.get("allergeni_presenti", []),
        "lotti_componenti": _json_loads_safe(lotti_componenti_json),
        "operatore_id": operatore_id or "",  # ← dipendente che ha prodotto
        "operatore_nome": operatore_nome or "",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    lotto_doc = await crea_lotto(lotto_doc, origine="produzione")
    from app.lotti.eventi import publish
    await publish("PRODUZIONE_REGISTRATA", {
        "lotto_numero": lotto_doc.get("numero_lotto") or lotto_doc.get("numero", ""),
        "ricetta": lotto_doc.get("prodotto") or lotto_doc.get("nome", ""),
        "reparto": lotto_doc.get("reparto", ""),
        "pezzi": lotto_doc.get("pezzi") or lotto_doc.get("quantita", 0),
    })

    # Salva evento produzione
    await db.produzioni.insert_one(
        {
            "id": str(uuid.uuid4()),
            "ricetta_id": ricetta_id,
            "ricetta_nome": ricetta["nome"],
            "pezzi": pezzi,
            "data": data_fmt,
            "data_iso": data_produzione,
            "costo_totale": costo_totale,
            "costo_pezzo": round(costo_totale / pezzi, 4) if pezzi > 0 else 0,
            "numero_lotto": numero_lotto,
            "lotti_fornitori_scalati": len(lotti_info["lotti_scalati"]),
            # Dettaglio completo dello scarico: serve allo storno (DELETE produzione)
            # per restituire le quantità ai lotti fornitori giusti.
            "lotti_scalati_dettaglio": lotti_info["lotti_scalati"],
            "operatore_id": operatore_id or "",  # ← chi ha prodotto
            "operatore_nome": operatore_nome or "",
            "reparto": ricetta.get("reparto", ""),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )

    # Il check scorta post-produzione ora vive in _riordini_post_produzione
    # (chiamato dentro scala_lotti_fornitori_per_ricetta): un motore solo.

    if operation_id:
        _snap = {k: lotto_doc.get(k) for k in
                 ("id", "numero_lotto", "prodotto", "quantita", "data_scadenza",
                  "frigo_numero", "lotti_fornitori")}
        _snap["gia_eseguita"] = True
        await db.operazioni_idempotenti.update_one(
            {"_id": f"prod_{operation_id}"}, {"$set": {"risultato": _snap}}, upsert=True)
    return lotto_doc


@router.post("/lotti/{lotto_id}/sblocca-richiamo")
async def sblocca_lotto_richiamo(
    lotto_id: str,
    motivo: str = Query(..., min_length=3),
    note: str = Query(""),
    operatore: str = Query(""),
    _admin=Depends(require_admin),
):
    """Sblocco AMMINISTRATIVO di un lotto bloccato da richiamo (tranche 4):
    solo il titolare, sempre con motivazione, tutto tracciato."""
    lotto = await db.lotti.find_one({"id": lotto_id}, {"_id": 0})
    if not lotto:
        raise HTTPException(404, "Lotto non trovato")
    if lotto.get("stato") != "bloccato_richiamo":
        return {"ok": True, "gia_sbloccato": True}
    adesso = datetime.now(timezone.utc).isoformat()
    await db.lotti.update_one({"id": lotto_id}, {"$set": {
        "stato": "sbloccato", "sbloccato_il": adesso, "sbloccato_motivo": motivo}})
    await db.blocchi_lotti.insert_one({
        "id": str(uuid.uuid4()), "lotto_id": lotto_id,
        "numero_lotto": lotto.get("numero_lotto", ""), "azione": "sblocco",
        "data": adesso, "utente": operatore or "amministratore",
        "motivazione": motivo, "richiamo_ref": lotto.get("richiamo_ref", ""),
        "quantita": lotto.get("quantita"), "note": note})
    return {"ok": True}


@router.get("/lotti/{lotto_id}/blocchi")
async def storico_blocchi_lotto(lotto_id: str):
    """Registro blocchi/sblocchi del lotto (dossier richiamo)."""
    return await db.blocchi_lotti.find(
        {"lotto_id": lotto_id}, {"_id": 0}).sort("data", 1).to_list(100)


# ── Scadenza: override per prodotto (Enzo 23/07/2026: "il panettone
#    artigianale dura 3 mesi, non 1 giorno per le uova") ─────────────────────

def _parse_data_prod(s: str):
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt)
        except (ValueError, TypeError):
            continue
    return None


def _scadenza_con_override(ricetta: dict, data_produzione: str, data_scad: str, giorni: int):
    """Se la ricetta ha una durata corretta a mano (scadenza_giorni_override),
    vince sul calcolo dagli ingredienti."""
    try:
        g = int(ricetta.get("scadenza_giorni_override") or 0)
    except (TypeError, ValueError):
        g = 0
    if g <= 0:
        return data_scad, giorni
    dt = _parse_data_prod(data_produzione)
    if not dt:
        return data_scad, giorni
    return (dt + timedelta(days=g)).strftime("%d/%m/%Y"), g


@router.get("/anteprima-scadenza/{ricetta_id}")
async def anteprima_scadenza(ricetta_id: str, data_produzione: str = Query(...)):
    """Scadenza PROPOSTA per una produzione: calcolo dagli ingredienti +
    eventuale durata memorizzata per il prodotto. Il tablet la mostra PRIMA
    di registrare, così l'operatore può correggerla."""
    from app.lotti.routers.utils import _calcola_scadenza
    ricetta = await db.ricette.find_one({"id": ricetta_id}, {"_id": 0})
    if not ricetta:
        raise HTTPException(404, "Ricetta non trovata")
    nomi = [i.get("nome", "") for i in ricetta.get("ingredienti_dettaglio", [])] or ricetta.get("ingredienti", [])
    scad = _calcola_scadenza(nomi, data_produzione, nome_prodotto=ricetta.get("nome", ""))
    data_scad, giorni = _scadenza_con_override(ricetta, data_produzione, scad[0], scad[3])
    return {
        "data_scadenza": data_scad,           # dd/mm/yyyy
        "giorni": giorni,
        "scadenza_abbattuto": scad[1],
        "ingrediente_critico": scad[2],
        "durata_memorizzata": bool(ricetta.get("scadenza_giorni_override")),
    }


# ── Genera lotto da ricetta (legacy) ─────────────────────────────────────────


@router.post("/genera-lotto/{ricetta_nome}")
async def genera_lotto_da_ricetta(
    ricetta_nome: str,
    data_produzione: str = Query(...),
    data_scadenza: str = Query(None),
    quantita: float = Query(1),
    unita_misura: str = Query(None),
    frigo_numero: str = Query(None),
):
    from app.lotti.routers.utils import _calcola_scadenza, _rileva_allergeni

    ricetta = await db.ricette.find_one(
        {"nome": {"$regex": f"^{ricetta_nome}$", "$options": "i"}}, {"_id": 0}
    )
    if not ricetta:
        raise HTTPException(status_code=404, detail=f"Ricetta '{ricetta_nome}' non trovata")

    ingredienti_base = []
    if ricetta.get("ricetta_base_id"):
        base = await db.ricette.find_one({"id": ricetta["ricetta_base_id"]}, {"_id": 0})
        if base:
            ingredienti_base = base.get("ingredienti", [])
    ingredienti_variante = ricetta.get("ingredienti", [])
    if ingredienti_base:
        nomi_base_lower = {i.lower() for i in ingredienti_base}
        extra = [i for i in ingredienti_variante if i.lower() not in nomi_base_lower]
        ingredienti_totali = ingredienti_base + extra
    else:
        ingredienti_totali = ingredienti_variante

    if not unita_misura:
        unita_misura = determina_unita_misura(ricetta["nome"])

    fornitori_esclusi_docs = await db.fornitori.find({"escluso": True}, {"_id": 0}).to_list(1000)
    nomi_esclusi = [f["nome"] for f in fornitori_esclusi_docs]

    ingredienti_dettaglio = []
    ingredienti_per_scadenza = []
    for ingrediente in ingredienti_totali:
        # Fonte unica: lotti_fornitori (unificazione materie_prime 03/07/2026).
        # REGOLA ENZO 23/07/2026: l'etichetta indica il lotto FIFO-ATTIVO (il
        # più vecchio degli ultimi 60 giorni, stessa regola dello scarico —
        # peek condiviso), NON più il lotto più recente: così etichetta,
        # registro lotti e scarico raccontano lo stesso fornitore.
        materia = await peek_lotto_fifo_attivo({"nome": ingrediente})
        if materia and nomi_esclusi and (materia.get("fornitore") or "") in nomi_esclusi:
            materia = None
        if materia is None:
            # fallback storico: match libero sul nome, lotto più recente
            query = {
                "prodotto_nome": {"$regex": re.escape(ingrediente), "$options": "i"},
                "solo_magazzino": {"$ne": True},
            }
            if nomi_esclusi:
                query["fornitore"] = {"$nin": nomi_esclusi}
            materia = await db.lotti_fornitori.find_one(
                query, {"_id": 0}, sort=[("data_fattura", -1)]
            )
        if materia and materia.get("prodotto_nome"):
            # stesso formato informativo del vecchio materie_prime.descrizione_completa
            dettaglio = (
                f"{materia['prodotto_nome']}  {materia.get('allergeni_testo', '')} - "
                f"{materia.get('fornitore', '')} n° fatt {materia.get('fattura_ref', '')} - "
                f"{materia.get('data_fattura', '')}"
            )
            ingredienti_dettaglio.append(dettaglio)
            ingredienti_per_scadenza.append(materia["prodotto_nome"])
        else:
            ingredienti_dettaglio.append(ingrediente)
            ingredienti_per_scadenza.append(ingrediente)

    allergeni_info = _rileva_allergeni(ingredienti_per_scadenza + ingredienti_dettaglio)
    scadenza_info = _calcola_scadenza(ingredienti_per_scadenza, data_produzione, nome_prodotto=ricetta.get("nome", ""))
    data_scad_frigo, data_scad_abb, ing_critico, giorni_frigo, giorni_abb, mesi_abb = scadenza_info
    data_scad_frigo, giorni_frigo = _scadenza_con_override(ricetta, data_produzione, data_scad_frigo, giorni_frigo)

    if not data_scadenza:
        data_scadenza = data_scad_frigo

    progressivo = await get_prossimo_progressivo(ricetta["nome"])
    numero_lotto = genera_codice_lotto(
        ricetta["nome"], progressivo, quantita, unita_misura, data_produzione
    )

    try:
        data_obj = datetime.strptime(data_produzione, "%Y-%m-%d")
        data_formattata = data_obj.strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        data_formattata = data_produzione

    lotto_id = str(uuid.uuid4())
    lotto_doc = {
        "id": lotto_id,
        "prodotto": ricetta["nome"],
        "ingredienti_dettaglio": ingredienti_dettaglio,
        "data_produzione": data_formattata,
        "data_scadenza": data_scadenza,
        "numero_lotto": numero_lotto,
        "etichetta": f"{ricetta['nome']} - prodotto il giorno {data_formattata}",
        "quantita": quantita,
        "unita_misura": unita_misura,
        "scadenza_abbattuto": data_scad_abb,
        "mesi_abbattuto": mesi_abb,
        "ingrediente_critico": ing_critico,
        "conservazione_note": f"Frigo (0-4°C): {giorni_frigo} giorni | Abbattuto (-18°C): {mesi_abb} mesi",
        "frigo_numero": frigo_numero or "",
        "allergeni": allergeni_info["allergeni_presenti"],
        "allergeni_testo": allergeni_info["testo_etichetta"],
        "progressivo": progressivo,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    lotto_doc = await crea_lotto(lotto_doc, origine="produzione")
    return lotto_doc


# ── Registro lotti mensile HTML ──────────────────────────────────────────────

MESI_ITALIANO = [
    "Gennaio",
    "Febbraio",
    "Marzo",
    "Aprile",
    "Maggio",
    "Giugno",
    "Luglio",
    "Agosto",
    "Settembre",
    "Ottobre",
    "Novembre",
    "Dicembre",
]


@router.get("/registro-lotti/{anno}/{mese}", response_class=HTMLResponse)
async def get_registro_lotti_mensile(anno: int, mese: int):
    from app.lotti.routers.utils import parse_data_flessibile
    # Filtro su anno/mese REALI, non regex "/{mese}/{anno}": data_produzione è a
    # formato misto (dd/mm/yyyy + ISO) e la regex escludeva i lotti in ISO
    # (pesce, colazione) dal registro ASL mensile.
    _tutti = await db.lotti.find({}, {"_id": 0}).sort("created_at", 1).to_list(50000)
    lotti = []
    for l in _tutti:
        d = parse_data_flessibile(l.get("data_produzione"))
        if d and d.year == anno and d.month == mese:
            lotti.append(l)

    totale_lotti = len(lotti)
    prodotti_unici = len(set(item.get("prodotto", "") for item in lotti))
    con_allergeni = sum(1 for item in lotti if item.get("allergeni"))

    rows = ""
    for i, lotto in enumerate(lotti, 1):
        numero_lotto = lotto.get("numero_lotto", "N/A")
        prodotto = lotto.get("prodotto", "N/A")
        data_prod = lotto.get("data_produzione", "N/A")
        data_scad = lotto.get("data_scadenza", "N/A")
        if data_scad and "-" in str(data_scad):
            try:
                data_scad = datetime.fromisoformat(str(data_scad).replace("Z", "")).strftime(
                    "%d/%m/%Y"
                )
            except Exception:
                _LOG_INIT.debug("[lotti_produzione] errore non bloccante ignorato")
        quantita = f"{lotto.get('quantita', '')} {lotto.get('unita_misura', '')}"
        ingredienti = lotto.get("ingredienti_dettaglio", [])
        ing_text = ", ".join([str(x)[:30] for x in ingredienti[:3]])
        if len(ingredienti) > 3:
            ing_text += f" (+{len(ingredienti)-3} altri)"
        allergeni = lotto.get("allergeni", [])
        allergeni_html = (
            f'<span style="background:#ffebee;color:#c62828;padding:2px 5px;border-radius:3px;font-size:7pt;font-weight:bold;">'
            f'{", ".join([a.upper()[:10] for a in allergeni])}</span>'
            if allergeni
            else '<span style="color:#999;">Nessuno</span>'
        )
        conservazione = (
            "Frigo 0-4°C"
            if "frigo" in str(lotto.get("conservazione_note", "")).lower()
            else "Ambiente"
        )
        rows += f"""<tr>
            <td style="text-align:center"><strong>{i}</strong></td>
            <td><span style="font-family:monospace;font-size:7pt;background:#e0e0e0;padding:2px 5px;border-radius:3px">{numero_lotto[:25]}</span></td>
            <td><strong>{prodotto[:25]}</strong></td>
            <td style="white-space:nowrap">{data_prod}</td>
            <td style="white-space:nowrap">{data_scad}</td>
            <td style="text-align:center">{quantita}</td>
            <td style="font-size:7pt">{ing_text[:60]}</td>
            <td>{allergeni_html}</td>
            <td style="font-size:8pt">{conservazione}</td>
        </tr>"""

    if not lotti:
        rows = '<tr><td colspan="9" style="text-align:center;padding:30px;color:#999;">Nessun lotto registrato per questo mese</td></tr>'

    return HTMLResponse(content=f"""<!DOCTYPE html><html lang="it"><head>
<meta charset="UTF-8">
<title>Registro Lotti - {MESI_ITALIANO[mese-1]} {anno}</title>
<style>
@page {{ size: A4; margin: 12mm; }}
@media print {{ .no-print {{ display: none; }} }}
body {{ font-family: Arial, sans-serif; font-size: 10pt; color: #333; }}
.header {{ border: 2px solid #1565c0; padding: 20px; margin-bottom: 20px; background: #e3f2fd; border-radius: 8px; }}
.header h1 {{ color: #0d47a1; margin: 0; font-size: 20pt; text-align: center; }}
.stats {{ display: flex; justify-content: space-around; background: #e8f5e9; padding: 15px; border-radius: 8px; margin: 20px 0; }}
.stat {{ text-align: center; }}
.stat-v {{ font-size: 24pt; font-weight: bold; color: #2e7d32; }}
table {{ width: 100%; border-collapse: collapse; font-size: 8pt; }}
th {{ background: #1565c0; color: white; padding: 8px 5px; text-align: left; }}
td {{ border: 1px solid #ddd; padding: 6px 5px; vertical-align: top; }}
tr:nth-child(even) {{ background: #f5f5f5; }}
.btn {{ padding: 12px 30px; font-size: 14pt; background: #1565c0; color: white; border: none; border-radius: 5px; cursor: pointer; margin: 5px; }}
</style></head><body>
<div class="header">
<h1>REGISTRO DEI LOTTI DI PRODUZIONE</h1>
<p style="text-align:center"><strong>CERALDI GROUP S.R.L.</strong> - Piazza Carità 14, 80134 Napoli</p>
<p style="text-align:center">Periodo: <strong>{MESI_ITALIANO[mese-1].upper()} {anno}</strong> | Generato il: {datetime.now().strftime('%d/%m/%Y ore %H:%M')}</p>
</div>
<div class="stats">
<div class="stat"><div class="stat-v">{totale_lotti}</div><div>LOTTI REGISTRATI</div></div>
<div class="stat"><div class="stat-v">{prodotti_unici}</div><div>PRODOTTI DIVERSI</div></div>
<div class="stat"><div class="stat-v">{con_allergeni}</div><div>CON ALLERGENI</div></div>
</div>
<div class="no-print" style="text-align:center;margin:20px 0">
<button onclick="window.print()" class="btn">Stampa / Salva PDF</button>
<a href="/api/registro-lotti/{anno}/{mese}/csv" class="btn" style="text-decoration:none">Scarica CSV</a>
</div>
<table><thead><tr>
<th>N°</th><th>NUMERO LOTTO</th><th>PRODOTTO</th><th>DATA PROD.</th>
<th>DATA SCAD.</th><th>QTÀ</th><th>INGREDIENTI</th><th>ALLERGENI</th><th>CONSERVAZIONE</th>
</tr></thead><tbody>{rows}</tbody></table>
<div style="margin-top:30px;text-align:center;font-size:8pt;color:#999;border-top:1px solid #ddd;padding-top:10px">
<p>Conforme a Reg. (CE) 178/2002 | Conservare per almeno 5 anni</p></div>
</body></html>""")


@router.get("/registro-lotti/{anno}/{mese}/csv")
async def get_registro_lotti_csv(anno: int, mese: int):
    from app.lotti.routers.utils import parse_data_flessibile
    # anno/mese reali (data_produzione a formato misto: la regex escludeva le ISO)
    _tutti = await db.lotti.find({}, {"_id": 0}).sort("created_at", 1).to_list(50000)
    lotti = []
    for l in _tutti:
        d = parse_data_flessibile(l.get("data_produzione"))
        if d and d.year == anno and d.month == mese:
            lotti.append(l)
    lines = [
        "N°;Numero Lotto;Prodotto;Data Produzione;Data Scadenza;Quantità;Unità;Ingredienti;Allergeni"
    ]
    for i, row in enumerate(lotti, 1):
        ingredienti = row.get("ingredienti_dettaglio", [])
        ing_str = ", ".join([str(x)[:30] for x in ingredienti[:5]]).replace(";", ",")
        allergeni = ", ".join(row.get("allergeni", [])).replace(";", ",")
        lines.append(
            f'{i};"{row.get("numero_lotto","").replace(";",",")}";"{row.get("prodotto","").replace(";",",")}";"{row.get("data_produzione","")}";"{row.get("data_scadenza","")}";{row.get("quantita","")};"{row.get("unita_misura","")}";"{ing_str}";"{allergeni}"'
        )
    return Response(
        content="\n".join(lines).encode("utf-8-sig"),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="registro_lotti_{anno}_{mese:02d}.csv"'
        },
    )


@router.get("/registro-lotti/{anno}", response_class=HTMLResponse)
async def get_registro_lotti_annuale(anno: int):
    from app.lotti.routers.utils import parse_data_flessibile
    # anno reale (data_produzione a formato misto: la regex "/{anno}$" prendeva
    # solo le dd/mm/yyyy → i lotti ISO sparivano dal registro annuale).
    _tutti = await db.lotti.find({}, {"_id": 0}).sort("created_at", 1).to_list(50000)
    lotti = [
        l for l in _tutti
        if (parse_data_flessibile(l.get("data_produzione")) or date(1900, 1, 1)).year == anno
    ]
    lotti_per_mese = {}
    for lotto_a in lotti:
        d = parse_data_flessibile(lotto_a.get("data_produzione"))
        if d:
            lotti_per_mese.setdefault(d.month, []).append(lotto_a)
    righe = ""
    totale_anno = 0
    for mese in range(1, 13):
        lotti_mese = lotti_per_mese.get(mese, [])
        n = len(lotti_mese)
        totale_anno += n
        unici = len(set(item.get("prodotto", "") for item in lotti_mese))
        righe += f"""<tr><td><strong>{MESI_ITALIANO[mese-1]}</strong></td><td>{n}</td><td>{unici}</td>
        <td><a href="/api/registro-lotti/{anno}/{mese}" target="_blank" style="color:#1565c0;font-weight:bold">Dettaglio</a></td></tr>"""
    righe += f'<tr style="background:#e8f5e9;font-weight:bold"><td>TOTALE ANNO</td><td>{totale_anno}</td><td>{len(set(item.get("prodotto","") for item in lotti))}</td><td>-</td></tr>'
    return HTMLResponse(
        content=f"""<!DOCTYPE html><html lang="it"><head><meta charset="UTF-8">
<title>Registro Lotti Annuale - {anno}</title>
<style>body{{font-family:Arial,sans-serif;font-size:10pt;max-width:800px;margin:30px auto;padding:20px}}
h1{{color:#1565c0}}table{{width:100%;border-collapse:collapse;margin:20px 0}}
th{{background:#1565c0;color:white;padding:10px}}td{{border:1px solid #ddd;padding:8px;text-align:center}}</style>
</head><body><h1>REGISTRO LOTTI ANNUALE - {anno}</h1>
<p><strong>CERALDI GROUP S.R.L.</strong> - Piazza Carità 14, 80134 Napoli</p>
<button onclick="window.print()" style="padding:10px 25px;background:#1565c0;color:white;border:none;border-radius:5px;cursor:pointer;margin:10px 0">Stampa</button>
<table><tr><th>MESE</th><th>LOTTI</th><th>PRODOTTI DISTINTI</th><th>AZIONE</th></tr>{righe}</table>
<p style="color:#999;font-size:9pt;margin-top:20px">Conforme a Reg. (CE) 178/2002</p></body></html>"""
    )


@router.post("/lotti/ricalcola-tracciabilita")
async def ricalcola_tracciabilita_lotti(solo_mancanti: bool = True):
    """
    Ricalcola lotti_scalati per i lotti di produzione che non hanno tracciabilità.
    Se solo_mancanti=True (default) processa solo quelli senza lotti_scalati.
    Chiamato dopo la creazione manuale di un lotto o come manutenzione.
    """
    query = {
        "$or": [
            {"lotti_fornitori": {"$exists": False}},
            {"lotti_fornitori": None},
            {"lotti_fornitori.lotti_scalati": {"$exists": False}},
            {"lotti_fornitori.lotti_scalati": {"$size": 0}},
        ]
    }
    if not solo_mancanti:
        query = {}

    lotti_da_processare = await db.lotti.find(query, {"_id": 0}).to_list(200)
    aggiornati = 0
    errori = []

    for lotto in lotti_da_processare:
        ricetta_id = lotto.get("ricetta_id")
        ricetta_nome = lotto.get("prodotto", "")
        numero_lotto = lotto.get("numero_lotto") or lotto.get("id", "")

        # Cerca la ricetta nel DB — prima esatta, poi fuzzy
        ricetta = None
        if ricetta_id:
            ricetta = await db.ricette.find_one({"id": ricetta_id}, {"_id": 0})
        if not ricetta and ricetta_nome:
            # Prova match esatto
            ricetta = await db.ricette.find_one(
                {"nome": {"$regex": f"^{re.escape(ricetta_nome)}$", "$options": "i"}}, {"_id": 0}
            )
        if not ricetta and ricetta_nome:
            # Prova match parziale sulle prime 3 parole
            parole = ricetta_nome.lower().split()[:3]
            for parola in parole:
                if len(parola) > 3:
                    ricetta = await db.ricette.find_one(
                        {"nome": {"$regex": re.escape(parola), "$options": "i"}}, {"_id": 0}
                    )
                    if ricetta:
                        break

        if not ricetta:
            # Senza ricetta, costruiamo lotti_scalati dai dizionario_prodotti per ogni ingrediente
            ing_dettaglio = lotto.get("ingredienti_dettaglio", [])
            scalati_da_dizionario = []
            for ing_str in ing_dettaglio:
                # Estrae nome e quantità dalla stringa "Nome (qx unità)"
                import re as re_mod

                m = re_mod.match(r"^(.+?)\s*\((\d[\d,.]*)\s*(\w+)\)", str(ing_str))
                if m:
                    nome_ing = m.group(1).strip()
                    # Cerca nel dizionario prodotti
                    diz = await db.dizionario_prodotti.find_one(
                        {
                            "nome_normalizzato": {
                                "$regex": re_mod.escape(nome_ing[:15].lower()),
                                "$options": "i",
                            }
                        },
                        {"_id": 0},
                    )
                    if diz:
                        scalati_da_dizionario.append(
                            {
                                "ingrediente": nome_ing,
                                "lotto_id": f"DIZ-{diz.get('id','?')}",
                                "lotto_id_fornitore": f"DIZ-{diz.get('id','?')}",
                                "fornitore": diz.get("fornitore", ""),
                                "prodotto": diz.get("nome_normalizzato", nome_ing),
                                "quantita_consumata": None,
                                "quantita_rimasta": round(
                                    float(diz.get("quantita_disponibile_kg", 0) or 0), 3
                                ),
                                "unita": diz.get("unita_confezione", "KG"),
                                "esaurito": float(diz.get("quantita_disponibile_kg", 0) or 0) <= 0,
                                "da_dizionario": True,
                            }
                        )
            if scalati_da_dizionario:
                await db.lotti.update_one(
                    {"id": lotto["id"]},
                    {
                        "$set": {
                            "lotti_fornitori": {
                                "lotti_scalati": scalati_da_dizionario,
                                "ingredienti_non_trovati": [],
                                "fonte": "dizionario_prodotti",
                            }
                        }
                    },
                )
                aggiornati += 1
            continue

        try:
            risultato = await scala_lotti_fornitori_per_ricetta(ricetta, 1.0, numero_lotto)
            await db.lotti.update_one({"id": lotto["id"]}, {"$set": {"lotti_fornitori": risultato}})
            aggiornati += 1
        except Exception as e:
            errori.append(f"{numero_lotto}: {str(e)}")

    return {"processati": len(lotti_da_processare), "aggiornati": aggiornati, "errori": errori}


@router.post("/lotti/ricalcola-scadenze", tags=["Lotti Produzione"])
async def endpoint_ricalcola_scadenze_lotti():
    """Ricalcola le scadenze per i lotti che le hanno vuote o mancanti."""
    return await ricalcola_scadenze_lotti()


async def ricalcola_scadenze_lotti():
    """Ricalcola la data di scadenza per tutti i lotti che la hanno vuota o mancante."""
    from app.lotti.routers.utils import _calcola_scadenza

    lotti_senza_scad = await db.lotti.find(
        {
            "$or": [
                {"data_scadenza": ""},
                {"data_scadenza": None},
                {"data_scadenza": {"$exists": False}},
            ]
        },
        {"_id": 0},
    ).to_list(10000)

    aggiornati = 0
    for lotto in lotti_senza_scad:
        ingredienti = lotto.get("ingredienti_dettaglio", [])
        if isinstance(ingredienti, list):
            nomi_ing = [i if isinstance(i, str) else i.get("nome", "") for i in ingredienti]
        else:
            nomi_ing = []

        data_prod = lotto.get("data_produzione", "")
        if not data_prod:
            continue

        try:
            scad_info = _calcola_scadenza(nomi_ing, data_prod)
            data_scad_frigo, data_scad_abb, ing_critico, giorni_frigo, giorni_abb, mesi_abb = (
                scad_info
            )
            await db.lotti.update_one(
                {"id": lotto["id"]},
                {
                    "$set": {
                        "data_scadenza": data_scad_frigo,
                        "scadenza_abbattuto": data_scad_abb,
                        "ingrediente_critico": ing_critico,
                        "conservazione_note": f"Frigo (0-4°C): {giorni_frigo} giorni | Abbattuto (-18°C): {mesi_abb} mesi",
                    }
                },
            )
            aggiornati += 1
        except Exception as e:
            _LOG_INIT.warning(
                f"[ricalcola-scadenze] lotto "
                f"{lotto.get('numero_lotto') or lotto.get('id')} saltato: {e}"
            )
            continue

    return {"message": f"Ricalcolate scadenze per {aggiornati} lotti", "aggiornati": aggiornati}


# ============================================================================
# RICHIAMO AVANZATO (additivo — NON modifica /lotti/recall/cerca esistente)
#   1) Recall ESATTO per numero di lotto fornitore
#   2) Scheda di richiamo/ritiro stampabile (A4) per ASL
# ============================================================================


def _riga_recall_prod(lp: dict, via: str) -> dict:
    """Normalizza un lotto di produzione in una riga di recall."""
    return {
        "id": lp.get("id"),
        "prodotto": lp.get("prodotto"),
        "numero_lotto": lp.get("numero_lotto"),
        "data_produzione": lp.get("data_produzione"),
        "data_scadenza": lp.get("data_scadenza"),
        "quantita": lp.get("quantita"),
        "unita_misura": lp.get("unita_misura"),
        "frigo_numero": lp.get("frigo_numero", ""),
        "allergeni_testo": lp.get("allergeni_testo", ""),
        "tracciato_via": via,
    }


async def _recall_per_lotto_fornitore(lotto_fornitore: str, fornitore: Optional[str] = None) -> dict:
    """Recall ESATTO a partire dal numero di lotto fornitore.

    Match esatto (case-insensitive) su lotti_fornitori.lotto_id_fornitore, poi
    risale ai lotti di produzione che lo hanno consumato tramite il legame
    strutturato storico_utilizzi[].lotto_produzione. Fallback su
    lotti_componenti[] e ingredienti_dettaglio[]."""
    testo = (lotto_fornitore or "").strip()
    if not testo:
        return {
            "lotto_fornitore_cercato": "",
            "fornitore": (fornitore or "").strip(),
            "supplier_lots": [],
            "totale_lotti_produzione": 0,
            "lotti_produzione": [],
        }

    esatto = {"$regex": f"^{re.escape(testo)}$", "$options": "i"}
    q_forn = {"$or": [{"lotto_id_fornitore": esatto}, {"fattura_ref": esatto}]}
    if fornitore and fornitore.strip():
        q_forn["fornitore"] = {"$regex": re.escape(fornitore.strip()), "$options": "i"}
    supplier_lots = await db.lotti_fornitori.find(q_forn, {"_id": 0}).to_list(200)

    codici_prod = set()
    supplier_out = []
    for sl in supplier_lots:
        usi_norm = []
        for u in (sl.get("storico_utilizzi") or []):
            lp_cod = (u.get("lotto_produzione") or "").strip()
            if lp_cod:
                codici_prod.add(lp_cod)
            usi_norm.append({
                "lotto_produzione": lp_cod,
                "quantita_usata": u.get("quantita_usata"),
                "data": u.get("data"),
                "ricetta": u.get("ricetta"),
            })
        supplier_out.append({
            "lotto_id_fornitore": sl.get("lotto_id_fornitore", ""),
            "fattura_ref": sl.get("fattura_ref", ""),
            "tipo_tracciabilita": sl.get("tipo_tracciabilita", ""),
            "fornitore": sl.get("fornitore", ""),
            "prodotto": sl.get("prodotto_nome", ""),
            "data_fattura": sl.get("data_fattura", ""),
            "data_scadenza": sl.get("data_scadenza", ""),
            "quantita_disponibile": sl.get("quantita_disponibile"),
            "esaurito": sl.get("esaurito", False),
            "utilizzi": usi_norm,
        })

    lotti_prod = []
    visti = set()
    if codici_prod:
        for lp in await db.lotti.find({"numero_lotto": {"$in": list(codici_prod)}}, {"_id": 0}).to_list(500):
            visti.add(lp.get("numero_lotto"))
            lotti_prod.append(_riga_recall_prod(lp, "storico_utilizzi"))

    comp_q = {"lotti_componenti": {"$elemMatch": {"$or": [
        {"numero_lotto": esatto}, {"lotto_id": esatto},
    ]}}}
    for lp in await db.lotti.find(comp_q, {"_id": 0}).to_list(500):
        if lp.get("numero_lotto") in visti:
            continue
        visti.add(lp.get("numero_lotto"))
        lotti_prod.append(_riga_recall_prod(lp, "componente"))

    ing_q = {"ingredienti_dettaglio": {"$elemMatch": {"$regex": re.escape(testo), "$options": "i"}}}
    for lp in await db.lotti.find(ing_q, {"_id": 0}).to_list(500):
        if lp.get("numero_lotto") in visti:
            continue
        visti.add(lp.get("numero_lotto"))
        lotti_prod.append(_riga_recall_prod(lp, "ingredienti"))

    return {
        "lotto_fornitore_cercato": testo,
        "fornitore": (fornitore or "").strip(),
        "supplier_lots": supplier_out,
        "totale_lotti_produzione": len(lotti_prod),
        "lotti_produzione": lotti_prod,
    }


@router.get("/lotti/recall/per-lotto-fornitore")
async def recall_per_lotto_fornitore(
    lotto_fornitore: str = Query(..., description="Numero di lotto del fornitore (match esatto)"),
    fornitore: Optional[str] = Query(None, description="Filtro opzionale per nome fornitore"),
):
    """Recall ESATTO per numero di lotto fornitore: individua i lotti fornitore
    con quel numero e risale ai lotti di produzione che li hanno consumati."""
    return await _recall_per_lotto_fornitore(lotto_fornitore, fornitore)


@router.get("/lotti/recall/scheda", response_class=HTMLResponse)
async def scheda_richiamo(
    ingrediente: Optional[str] = Query(None),
    lotto_fornitore: Optional[str] = Query(None),
    fornitore: Optional[str] = Query(None),
    data_da: Optional[str] = Query(None),
    data_a: Optional[str] = Query(None),
    mesi: int = Query(12),
    motivo: str = Query(""),
    operatore: str = Query(""),
):
    """Scheda di richiamo/ritiro lotti, stampabile in A4 (per ASL).
    Si basa su un INGREDIENTE oppure su un NUMERO DI LOTTO FORNITORE esatto."""
    sup = []
    if lotto_fornitore and lotto_fornitore.strip():
        criterio_tipo = "Numero lotto fornitore"
        criterio_val = lotto_fornitore.strip()
        if fornitore and fornitore.strip():
            criterio_val += f" (fornitore: {fornitore.strip()})"
        dati = await _recall_per_lotto_fornitore(lotto_fornitore, fornitore)
        lotti = dati["lotti_produzione"]
        sup = dati.get("supplier_lots") or []
    elif ingrediente and ingrediente.strip():
        criterio_tipo = "Ingrediente / materia prima"
        criterio_val = ingrediente.strip()
        dati = await recall_lotti_per_ingrediente(
            ingrediente=ingrediente, data_da=data_da, data_a=data_a,
            fornitore=fornitore, frigo=None, mesi=mesi, limit=500,
        )
        lotti = dati["lotti"]
    else:
        return HTMLResponse(
            content="<h2 style='font-family:Arial'>Specificare il parametro 'ingrediente' oppure 'lotto_fornitore'.</h2>",
            status_code=400,
        )

    rows = ""
    for i, lt in enumerate(lotti, 1):
        nl = str(lt.get("numero_lotto", "N/A"))
        prod = str(lt.get("prodotto", "N/A"))
        dp = lt.get("data_produzione", "N/A")
        ds = lt.get("data_scadenza", "N/A")
        qta = f"{lt.get('quantita', '')} {lt.get('unita_misura', '')}".strip()
        frigo = lt.get("frigo_numero", "") or "-"
        if lt.get("tracciato_via_componente"):
            via = "via semilavorato"
        else:
            via = lt.get("tracciato_via", "") or ""
        trovato = lt.get("ingrediente_trovato", "") or ""
        riscontro = (trovato or via)[:45]
        rows += f"""<tr>
            <td style="text-align:center"><strong>{i}</strong></td>
            <td><span style="font-family:monospace;font-size:8pt;background:#eee;padding:2px 5px;border-radius:3px">{nl[:30]}</span></td>
            <td><strong>{prod[:30]}</strong></td>
            <td style="white-space:nowrap">{dp}</td>
            <td style="white-space:nowrap">{ds}</td>
            <td style="text-align:center">{qta}</td>
            <td style="text-align:center">{frigo}</td>
            <td style="font-size:8pt">{riscontro}</td>
        </tr>"""
    if not lotti:
        rows = '<tr><td colspan="8" style="text-align:center;padding:30px;color:#999;">Nessun lotto di produzione coinvolto trovato per questo criterio.</td></tr>'

    sup_html = ""
    if sup:
        righe_sup = "".join(
            f"<li>{s.get('fornitore', '')} — {s.get('prodotto', '')} — rif. <strong>{s.get('lotto_id_fornitore') or ('fattura ' + str(s.get('fattura_ref', '')))}</strong> — data fattura {s.get('data_fattura', '')}</li>"
            for s in sup
        )
        sup_html = f"<div class='sup'><strong>Lotto/i fornitore individuati:</strong><ul>{righe_sup}</ul></div>"

    motivo_html = motivo.strip() if (motivo and motivo.strip()) else "_______________________________________________"
    operatore_html = operatore.strip() if (operatore and operatore.strip()) else "____________________"
    ora = datetime.now().strftime("%d/%m/%Y ore %H:%M")
    totale = len(lotti)

    return HTMLResponse(content=f"""<!DOCTYPE html><html lang="it"><head>
<meta charset="UTF-8">
<title>Scheda di Richiamo/Ritiro Lotti</title>
<style>
@page {{ size: A4; margin: 12mm; }}
@media print {{ .no-print {{ display: none; }} }}
body {{ font-family: Arial, sans-serif; font-size: 10pt; color: #333; }}
.header {{ border: 2px solid #c62828; padding: 18px; margin-bottom: 16px; background: #ffebee; border-radius: 8px; }}
.header h1 {{ color: #b71c1c; margin: 0; font-size: 19pt; text-align: center; letter-spacing: 1px; }}
.header p {{ margin: 4px 0; }}
.crit {{ background: #fff3e0; border: 1px solid #ffb74d; border-radius: 6px; padding: 10px 14px; margin: 14px 0; }}
.crit p {{ margin: 5px 0; }}
.sup {{ background: #f5f5f5; border-radius: 6px; padding: 8px 14px; margin: 10px 0; font-size: 9pt; }}
.sup ul {{ margin: 6px 0 0 0; }}
table {{ width: 100%; border-collapse: collapse; font-size: 9pt; margin-top: 6px; }}
th {{ background: #c62828; color: white; padding: 8px 5px; text-align: left; }}
td {{ border: 1px solid #ddd; padding: 6px 5px; vertical-align: top; }}
tr:nth-child(even) {{ background: #fafafa; }}
.firme {{ display: flex; justify-content: space-between; margin-top: 40px; }}
.firme div {{ width: 30%; border-top: 1px solid #333; padding-top: 6px; text-align: center; font-size: 9pt; }}
.btn {{ padding: 12px 30px; font-size: 14pt; background: #c62828; color: white; border: none; border-radius: 5px; cursor: pointer; }}
.tot {{ font-size: 13pt; font-weight: bold; color: #b71c1c; }}
</style></head><body>
<div class="header">
<h1>SCHEDA DI RICHIAMO / RITIRO LOTTI</h1>
<p style="text-align:center"><strong>CERALDI GROUP S.R.L.</strong> - Piazza Carità 14, 80134 Napoli</p>
<p style="text-align:center">Generata il: {ora}</p>
</div>
<div class="crit">
<p><strong>Criterio di ricerca:</strong> {criterio_tipo} &rarr; <strong>{criterio_val}</strong></p>
<p><strong>Motivo del richiamo/ritiro:</strong> {motivo_html}</p>
<p><strong>Lotti di produzione coinvolti:</strong> <span class="tot">{totale}</span></p>
</div>
{sup_html}
<div class="no-print" style="text-align:center;margin:14px 0">
<button onclick="window.print()" class="btn">Stampa / Salva PDF</button>
</div>
<table><thead><tr>
<th>N&deg;</th><th>NUMERO LOTTO</th><th>PRODOTTO</th><th>DATA PROD.</th>
<th>DATA SCAD.</th><th>QT&Agrave;</th><th>FRIGO</th><th>RISCONTRO</th>
</tr></thead><tbody>{rows}</tbody></table>
<div class="firme">
<div>Responsabile HACCP<br>{operatore_html}</div>
<div>Data<br>______/______/__________</div>
<div>Firma<br>&nbsp;</div>
</div>
<div style="margin-top:24px;text-align:center;font-size:8pt;color:#999;border-top:1px solid #ddd;padding-top:10px">
<p>Procedura di ritiro/richiamo &mdash; Reg. (CE) 178/2002, artt. 18-19 | Documento da conservare nel piano di autocontrollo HACCP</p>
</div>
</body></html>""")
