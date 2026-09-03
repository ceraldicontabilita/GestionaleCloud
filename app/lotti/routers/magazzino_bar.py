"""
magazzino_bar.py
----------------
Gestione giacenze magazzino bar:
  - Prodotti con stock corrente (collection magazzino_bar_prodotti)
  - Movimenti carico/scarico (collection magazzino_bar_movimenti)

Endpoints:
  GET  /magazzino-bar/prodotti            — lista prodotti + giacenza
  POST /magazzino-bar/prodotti            — aggiunge nuovo prodotto
  POST /magazzino-bar/carico              — carica giacenza (fattura)
  POST /magazzino-bar/scarico             — scarica giacenza (operatore)
  GET  /magazzino-bar/movimenti           — storico movimenti
  GET  /magazzino-bar/movimenti/oggi      — movimenti di oggi
"""

from pymongo import ReturnDocument
import uuid
import logging
_LOG_INIT = logging.getLogger("uvicorn.error")
from datetime import datetime, timezone, date, timedelta
from fastapi import APIRouter, HTTPException, Query, Body, Depends
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional, List
from app.lotti.db import database as db
from app.lotti.auth import require_admin

router = APIRouter(prefix="/magazzino-bar", tags=["magazzino_bar"])


# ── Prodotti di default (seed al primo avvio) ────────────────────────────────
# ── Prodotti di default: estratti in magazzino_bar_seed.py ───────────────────
from app.lotti.routers.magazzino_bar_seed import PRODOTTI_DEFAULT


async def seed_magazzino_bar():
    count = await db.magazzino_bar_prodotti.count_documents({})
    if count > 0:
        return
    docs = [{"id": str(uuid.uuid4()), **p} for p in PRODOTTI_DEFAULT]
    await db.magazzino_bar_prodotti.insert_many(docs)


# ── Modelli ──────────────────────────────────────────────────────────────────
class NuovoProdotto(BaseModel):
    nome: str
    categoria: str
    fornitore: Optional[str] = ""
    unita: Optional[str] = "pz"          # unità del pezzo singolo (bottiglia, lattina, pz)
    unita_collo: Optional[str] = "cassa"  # come arriva in fattura (cassa, cartone, collo)
    pezzi_per_collo: Optional[int] = 1    # quanti pezzi singoli in una cassa/cartone


class MovimentoCarico(BaseModel):
    prodotto_id: str
    quantita: float                       # interpretata secondo 'unita_movimento'
    unita_movimento: Optional[str] = "collo"  # 'collo' (casse) o 'pezzo' (singoli)
    nota: Optional[str] = ""  # es. "Fattura n. 1234"
    operatore_nome: Optional[str] = ""


class MovimentoScarico(BaseModel):
    prodotto_id: str
    quantita: float                       # di norma in pezzi singoli
    unita_movimento: Optional[str] = "pezzo"  # 'pezzo' (default) o 'collo'
    operatore_nome: str  # nome dal PIN (obbligatorio)
    nota: Optional[str] = ""


# ── GET prodotti ──────────────────────────────────────────────────────────────
@router.get("/prodotti")
async def lista_prodotti(
    categoria: Optional[str] = None, fornitore: Optional[str] = None, q: Optional[str] = None
):
    filtro = {}
    if categoria:
        filtro["categoria"] = categoria
    if fornitore:
        filtro["fornitore"] = fornitore
    if q:
        filtro["nome"] = {"$regex": q, "$options": "i"}

    docs = (
        await db.magazzino_bar_prodotti.find(filtro, {"_id": 0}).sort("categoria", 1).to_list(500)
    )
    return docs


# ── POST nuovo prodotto ───────────────────────────────────────────────────────
@router.post("/prodotti")
async def crea_prodotto(payload: NuovoProdotto):
    nome = payload.nome.strip()
    ppc = _pezzi_da_nome(nome) or (int(payload.pezzi_per_collo) if payload.pezzi_per_collo else 1) or 1
    doc = {
        "id": str(uuid.uuid4()),
        "nome": nome,
        "categoria": await _risolvi_cat(payload.categoria.strip()),
        "fornitore": payload.fornitore or "",
        "unita": payload.unita or "pz",
        "stock": 0,
        "pezzi_per_collo": ppc,
        "unita_collo": _unita_collo_da_nome(nome) if ppc > 1 else (payload.unita_collo or "cassa"),
    }
    await db.magazzino_bar_prodotti.insert_one(doc)
    doc.pop("_id", None)
    return doc


async def applica_movimento_stock(prod: dict, delta_pezzi: float, tipo: str,
                                  operatore_nome: str, nota: str = "",
                                  extra: dict | None = None):
    """UNICA via che modifica lo stock bar: aggiorna magazzino_bar_prodotti e
    registra il movimento. Usata da carico, scarico, scarico unificato e
    carico-da-fattura: una sola logica, un solo posto da correggere."""
    # Aggiornamento ATOMICO: $inc somma il delta lato Mongo, immune da scarichi
    # concorrenti (leggi-poi-scrivi perdeva una vendita se due scarichi partivano
    # insieme). find_one_and_update torna il documento col valore reale aggiornato.
    aggiornato = await db.magazzino_bar_prodotti.find_one_and_update(
        {"id": prod["id"]},
        {"$inc": {"stock": round(delta_pezzi, 3)}},
        return_document=ReturnDocument.AFTER,
    )
    nuovo = round(float((aggiornato or {}).get("stock", float(prod.get("stock", 0)) + delta_pezzi)), 3)
    mov = {
        "id": str(uuid.uuid4()),
        "prodotto_id": prod["id"],
        "prodotto_nome": prod["nome"],
        "tipo": tipo,
        "quantita": round(abs(delta_pezzi), 3),
        "unita": prod.get("unita", "pz"),
        "stock_dopo": nuovo,
        "operatore_nome": operatore_nome or "sistema",
        "nota": nota or "",
        "data": datetime.now(timezone.utc).isoformat(),
        **(extra or {}),
    }
    await db.magazzino_bar_movimenti.insert_one(dict(mov))
    mov.pop("_id", None)
    from app.lotti.eventi import publish
    await publish("STOCK_MOVIMENTATO", {
        "prodotto": prod.get("nome", ""), "tipo": tipo,
        "quantita": delta_pezzi, "stock_dopo": prod.get("stock"),
    })
    return nuovo, mov


# ── POST carico (fattura → aumenta stock) ────────────────────────────────────
@router.post("/carico")
async def carico(payload: MovimentoCarico):
    prod = await db.magazzino_bar_prodotti.find_one({"id": payload.prodotto_id})
    if not prod:
        raise HTTPException(404, "Prodotto non trovato")

    pezzi_collo = float(prod.get("pezzi_per_collo", 1) or 1)
    # Se il carico è in colli (casse/cartoni) converto in pezzi singoli.
    if payload.unita_movimento == "collo":
        pezzi_aggiunti = payload.quantita * pezzi_collo
        dettaglio_nota = f"{payload.quantita:g} {prod.get('unita_collo','cassa')} × {pezzi_collo:g} = {pezzi_aggiunti:g} {prod.get('unita','pz')}"
    else:
        pezzi_aggiunti = payload.quantita
        dettaglio_nota = f"{pezzi_aggiunti:g} {prod.get('unita','pz')}"

    nota_finale = payload.nota or ""
    if dettaglio_nota:
        nota_finale = f"{nota_finale} ({dettaglio_nota})".strip()

    nuovo_stock, mov = await applica_movimento_stock(
        prod, pezzi_aggiunti, "carico", payload.operatore_nome,
        nota=nota_finale,
        extra={"quantita_colli": payload.quantita if payload.unita_movimento == "collo" else None},
    )
    try:
        from app.lotti.utils.activity_log import registra_attivita
        await registra_attivita(
            payload.operatore_nome, "magazzino",
            f"{payload.operatore_nome or 'Sistema'} ha caricato {round(pezzi_aggiunti, 3):g} {prod.get('unita','pz')} di {prod['nome']}",
            extra={"prodotto": prod["nome"], "quantita": round(pezzi_aggiunti, 3)},
        )
    except Exception:
        _LOG_INIT.debug("[magazzino_bar] errore non bloccante ignorato")
    return {"ok": True, "stock_nuovo": nuovo_stock, "pezzi_aggiunti": round(pezzi_aggiunti, 3), "movimento": mov}


# ── Richieste rifornimento frigo (bar → magazzino) ───────────────────────────
class RichiestaRifornimento(BaseModel):
    prodotto_id: str
    quantita: float = 1
    unita_movimento: str = "collo"   # collo (cartone) | pezzo
    operatore_nome: str = ""
    nota: str = ""


@router.post("/richieste")
async def crea_richiesta(payload: RichiestaRifornimento):
    """Il bar chiede un rifornimento (es. 1 cartone di Prosecco). La richiesta
    appare in automatico sulla lavagna del tablet Magazzino."""
    prod = await db.magazzino_bar_prodotti.find_one({"id": payload.prodotto_id}, {"_id": 0})
    if not prod:
        raise HTTPException(404, "Prodotto non trovato")
    doc = {
        "id": str(uuid.uuid4()),
        "prodotto_id": payload.prodotto_id,
        "prodotto_nome": prod["nome"],
        "quantita": float(payload.quantita or 1),
        "unita_movimento": payload.unita_movimento if payload.unita_movimento in ("collo", "pezzo") else "collo",
        "stato": "aperta",          # aperta -> evasa | annullata
        "richiesto_da": payload.operatore_nome.strip(),
        "nota": payload.nota or "",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.magazzino_bar_richieste.insert_one(dict(doc))
    return {"ok": True, "richiesta": doc}


@router.get("/richieste")
async def lista_richieste(stato: str = Query("aperta"), limit: int = Query(100, ge=1, le=500)):
    q = {} if stato == "tutte" else {"stato": stato}
    items = await db.magazzino_bar_richieste.find(q, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return {"totale": len(items), "richieste": items}


@router.put("/richieste/{rid}/ok")
async def evadi_richiesta(rid: str, operatore_nome: str = Query("")):
    """L'operatore del magazzino tocca OK = il cartone è stato preso:
    la richiesta si chiude e LO STOCK SI SCALA AUTOMATICAMENTE (movimento di
    scarico registrato). Se poi lo stock scende sotto soglia, i riordini
    automatici creano la bozza per rimpiazzare."""
    ric = await db.magazzino_bar_richieste.find_one({"id": rid}, {"_id": 0})
    if not ric:
        raise HTTPException(404, "Richiesta non trovata")
    # CLAIM ATOMICO: un doppio tap "OK" sul tablet arrivava due volte qui e
    # scaricava lo stesso cartone due volte (il check stato+update separati non
    # erano atomici). Solo il primo tap prende in carico la richiesta.
    claim = await db.magazzino_bar_richieste.update_one(
        {"id": rid, "stato": "aperta"}, {"$set": {"stato": "in_evasione"}})
    if claim.modified_count == 0:
        return {"ok": True, "gia_evasa": True, "stato": ric.get("stato")}
    avviso = None
    try:
        esito = await _evadi_scarico(ric, operatore_nome)
        stock_dopo = esito["stock_dopo"]
        avviso = esito["avviso"]
    except Exception:
        # errore inatteso: la richiesta torna aperta, ritentabile
        await db.magazzino_bar_richieste.update_one(
            {"id": rid, "stato": "in_evasione"}, {"$set": {"stato": "aperta"}})
        raise
    await db.magazzino_bar_richieste.update_one({"id": rid}, {"$set": {
        "stato": "evasa", "prelevato_da": operatore_nome or "magazzino",
        "evasa_il": datetime.now(timezone.utc).isoformat(), "stock_dopo": stock_dopo,
    }})
    return {"ok": True, "stock_dopo": stock_dopo, "avviso": avviso}


async def _evadi_scarico(ric: dict, operatore_nome: str) -> dict:
    """Scarico effettivo di una richiesta lavagna presa in carico (claim già
    fatto dal chiamante). Ritorna {stock_dopo, avviso}."""
    avviso = None
    try:
        esito = await scarico(MovimentoScarico(
            prodotto_id=ric["prodotto_id"],
            quantita=float(ric.get("quantita", 1)),
            unita_movimento=ric.get("unita_movimento", "collo"),
            operatore_nome=operatore_nome or "magazzino",
            nota=f"rifornimento frigo bar (richiesta di {ric.get('richiesto_da') or 'bar'})",
        ))
        stock_dopo = esito.get("stock_nuovo")
    except HTTPException:
        # Il cartone è stato preso fisicamente anche se lo stock a sistema non basta:
        # scarico quello che c'è (stock a 0) e segnalo lo scostamento inventariale.
        prod = await db.magazzino_bar_prodotti.find_one({"id": ric["prodotto_id"]})
        disponibile = float(prod.get("stock", 0)) if prod else 0
        if prod:
            await db.magazzino_bar_prodotti.update_one({"id": ric["prodotto_id"]}, {"$set": {"stock": 0}})
            await db.magazzino_bar_movimenti.insert_one({
                "id": str(uuid.uuid4()), "prodotto_id": ric["prodotto_id"],
                "prodotto_nome": ric["prodotto_nome"], "tipo": "scarico",
                "quantita": disponibile, "unita": prod.get("unita", "pz"),
                "stock_dopo": 0, "operatore_nome": operatore_nome or "magazzino",
                "nota": "rifornimento frigo bar — stock a sistema insufficiente, azzerato (verifica inventario)",
                "data": datetime.now(timezone.utc).isoformat(),
            })
        stock_dopo = 0
        avviso = "Stock a sistema insufficiente: azzerato. Verifica l'inventario."
        # CHIUSURA DEL CERCHIO (fix 02/07/2026): il prodotto è ESAURITO proprio
        # mentre il bar lo chiede — prima la richiesta si chiudeva 'evasa' e
        # nessuno lo riordinava (perso se soglia_minima=0). Ora entra da solo
        # nel circuito riordino (bozza per fornitore, dedup incrociata).
        try:
            from app.lotti.routers.ordini_fornitori import aggiungi_a_bozza_riordino
            pezzi_per_collo = float((prod or {}).get("pezzi_per_collo") or 1) or 1
            qta_pezzi = float(ric.get("quantita", 1) or 1)
            if (ric.get("unita_movimento") or "collo") == "collo":
                qta_pezzi *= pezzi_per_collo
            esito_riordino = await aggiungi_a_bozza_riordino(
                nome=ric.get("prodotto_nome", ""),
                prodotto_id=ric.get("prodotto_id", ""),
                quantita=max(qta_pezzi - disponibile, 1),
                unita=(prod or {}).get("unita", "pz"),
                richiesto_da=ric.get("richiesto_da") or operatore_nome or "lavagna",
                nota=f"esaurito in consegna lavagna (richiesti {ric.get('quantita')} "
                     f"{ric.get('unita_movimento', 'collo')}, disponibili {disponibile:g})",
            )
            if not esito_riordino.get("gia_in_ordine"):
                avviso += " Prodotto messo in bozza di riordino."
        except Exception:
            _LOG_INIT.warning("[lavagna] riordino automatico da esaurito fallito (non bloccante)")
    return {"stock_dopo": stock_dopo, "avviso": avviso}


@router.delete("/richieste/{rid}")
async def annulla_richiesta(rid: str):
    res = await db.magazzino_bar_richieste.update_one(
        {"id": rid, "stato": "aperta"}, {"$set": {"stato": "annullata"}})
    if res.matched_count == 0:
        raise HTTPException(404, "Richiesta aperta non trovata")
    return {"ok": True}


# ── POST scarico (operatore prende → diminuisce stock) ────────────────────────
@router.post("/scarico")
async def scarico(payload: MovimentoScarico):
    prod = await db.magazzino_bar_prodotti.find_one({"id": payload.prodotto_id})
    if not prod:
        raise HTTPException(404, "Prodotto non trovato")

    pezzi_collo = float(prod.get("pezzi_per_collo", 1) or 1)
    # Lo scarico è di norma in pezzi; se in colli, converto in pezzi.
    if payload.unita_movimento == "collo":
        pezzi_tolti = payload.quantita * pezzi_collo
    else:
        pezzi_tolti = payload.quantita

    stock_attuale = float(prod.get("stock", 0))
    if pezzi_tolti > stock_attuale:
        raise HTTPException(
            400,
            f"Quantità richiesta ({pezzi_tolti:g} {prod.get('unita','pz')}) superiore allo stock disponibile ({stock_attuale:g})",
        )

    nuovo_stock, mov = await applica_movimento_stock(
        prod, -pezzi_tolti, "scarico", payload.operatore_nome, nota=payload.nota or "")
    try:
        from app.lotti.utils.activity_log import registra_attivita
        await registra_attivita(
            payload.operatore_nome, "magazzino",
            f"{payload.operatore_nome or 'Operatore'} ha prelevato {round(pezzi_tolti, 3):g} {prod.get('unita','pz')} di {prod['nome']}",
            extra={"prodotto": prod["nome"], "quantita": round(pezzi_tolti, 3)},
        )
    except Exception:
        _LOG_INIT.debug("[magazzino_bar] errore non bloccante ignorato")
    mov.pop("_id", None)
    return {"ok": True, "stock_nuovo": nuovo_stock, "movimento": mov}


@router.get("/piu-usati")
async def piu_usati(limit: int = 12):
    """Prodotti più scaricati di recente, per accesso rapido nel tablet.
    Conta gli scarichi degli ultimi 60 giorni e ordina per frequenza.
    Se non c'è storico sufficiente, completa con i prodotti a stock più alto."""
    from datetime import timedelta
    from collections import defaultdict

    limite = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
    conteggi = defaultdict(lambda: {"n": 0, "qta": 0.0})
    async for m in db.magazzino_bar_movimenti.find(
        {"tipo": "scarico", "data": {"$gte": limite}}, {"_id": 0, "prodotto_id": 1, "quantita": 1}
    ):
        pid = m.get("prodotto_id")
        if pid:
            conteggi[pid]["n"] += 1
            conteggi[pid]["qta"] += float(m.get("quantita", 0) or 0)

    # Ordina per numero di scarichi (frequenza d'uso)
    ordinati = sorted(conteggi.items(), key=lambda kv: kv[1]["n"], reverse=True)
    ids_top = [pid for pid, _ in ordinati[:limit]]

    prodotti_top = []
    for pid in ids_top:
        p = await db.magazzino_bar_prodotti.find_one({"id": pid}, {"_id": 0})
        if p:
            p["scarichi_recenti"] = conteggi[pid]["n"]
            prodotti_top.append(p)

    # Completa fino a limit con prodotti a stock disponibile non già inclusi
    if len(prodotti_top) < limit:
        gia = {p["id"] for p in prodotti_top}
        async for p in db.magazzino_bar_prodotti.find(
            {"stock": {"$gt": 0}}, {"_id": 0}
        ).sort("stock", -1).limit(limit * 2):
            if p["id"] not in gia:
                p["scarichi_recenti"] = 0
                prodotti_top.append(p)
            if len(prodotti_top) >= limit:
                break

    return prodotti_top


# ── GET movimenti ─────────────────────────────────────────────────────────────
@router.get("/movimenti")
async def movimenti(
    prodotto_id: Optional[str] = None, tipo: Optional[str] = None, limit: int = Query(100, le=500)
):
    filtro = {}
    if prodotto_id:
        filtro["prodotto_id"] = prodotto_id
    if tipo:
        filtro["tipo"] = tipo
    docs = (
        await db.magazzino_bar_movimenti.find(filtro, {"_id": 0})
        .sort("data", -1)
        .limit(limit)
        .to_list(limit)
    )
    return docs


# ── GET movimenti di oggi ─────────────────────────────────────────────────────
@router.get("/movimenti/oggi")
async def movimenti_oggi():
    oggi = datetime.now(timezone.utc).date().isoformat()
    docs = (
        await db.magazzino_bar_movimenti.find({"data": {"$gte": oggi}}, {"_id": 0})
        .sort("data", -1)
        .to_list(200)
    )
    return docs


# ── GET categorie & fornitori disponibili ─────────────────────────────────────
@router.get("/filtri")
async def filtri():
    categorie = await db.magazzino_bar_prodotti.distinct("categoria")
    fornitori = await db.magazzino_bar_prodotti.distinct("fornitore")
    return {"categorie": sorted(categorie), "fornitori": sorted(f for f in fornitori if f)}


# ── Modello soglia ─────────────────────────────────────────────────────────────
class SogliaUpdate(BaseModel):
    soglia_minima: float
    # None = non toccare il valore esistente (i client che editano solo la
    # soglia, es. card Ordini, non devono azzerare la quantità di riordino)
    quantita_riordino: Optional[float] = None


# ── PATCH soglia minima + quantità riordino prodotto ──────────────────────────
class RettificaInventario(BaseModel):
    stock_contato: float           # quanti pezzi ho CONTATO davvero
    operatore_nome: str = ""
    nota: str = ""


@router.post("/prodotti/{prodotto_id}/rettifica")
async def rettifica_inventario(prodotto_id: str, payload: RettificaInventario):
    """Inventario: imposto la giacenza al valore CONTATO a mano. La differenza
    col valore precedente viene registrata come movimento di rettifica, sempre
    attraverso applica_movimento_stock (un'unica via per lo stock)."""
    prod = await db.magazzino_bar_prodotti.find_one({"id": prodotto_id})
    if not prod:
        raise HTTPException(404, "Prodotto non trovato")
    attuale = float(prod.get("stock", 0) or 0)
    contato = round(float(payload.stock_contato), 3)
    delta = round(contato - attuale, 3)
    if delta == 0:
        return {"ok": True, "stock_nuovo": attuale, "delta": 0, "invariato": True}
    nota = (payload.nota or "").strip() or f"Inventario: contati {contato:g} (erano {attuale:g})"
    nuovo_stock, mov = await applica_movimento_stock(
        prod, delta, "rettifica", payload.operatore_nome, nota=nota,
        extra={"stock_precedente": attuale, "stock_contato": contato},
    )
    return {"ok": True, "stock_nuovo": nuovo_stock, "delta": delta, "movimento": mov}


@router.patch("/prodotti/{prodotto_id}/soglia")
async def aggiorna_soglia(prodotto_id: str, payload: SogliaUpdate):
    res = await db.magazzino_bar_prodotti.update_one(
        {"id": prodotto_id},
        {
            "$set": {
                "soglia_minima": round(payload.soglia_minima, 3),
                **({"quantita_riordino": round(payload.quantita_riordino, 3)}
                   if payload.quantita_riordino is not None else {}),
            }
        },
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Prodotto non trovato")
    prod = await db.magazzino_bar_prodotti.find_one({"id": prodotto_id}, {"_id": 0})
    return prod


# ── Pulizia non-merce dalle giacenze (servizi entrati da fatture XML) ─────────
from app.lotti.routers.classificatore_alimenti import e_merce_alimentare as _e_merce

@router.get("/pulizia-non-merce")
async def trova_non_merce(_admin=Depends(require_admin)):
    """Elenca le voci di magazzino che NON sono merce (servizi, rinnovi, canoni...)
    finite in giacenza da righe di fatture XML. Solo elenco: non cancella nulla."""
    prodotti = await db.magazzino_bar_prodotti.find({}, {"_id": 0}).to_list(2000)
    sospetti = [p for p in prodotti if not _e_merce(p.get("nome", ""), p.get("categoria", ""))]
    return {"totale": len(prodotti), "non_merce": len(sospetti),
            "voci": [{"id": p.get("id"), "nome": p.get("nome"),
                      "categoria": p.get("categoria"), "stock": p.get("stock")} for p in sospetti]}

class RimuoviNonMerceReq(BaseModel):
    ids: List[str]  # gli id confermati dall'utente dopo aver visto l'elenco

@router.post("/pulizia-non-merce")
async def rimuovi_non_merce(payload: RimuoviNonMerceReq, _admin=Depends(require_admin)):
    """Rimuove SOLO gli id esplicitamente confermati dall'utente (non cancella alla
    cieca). Le fatture restano intatte: si pulisce solo la vista giacenze."""
    if not payload.ids:
        raise HTTPException(400, "Nessun id da rimuovere")
    res = await db.magazzino_bar_prodotti.delete_many({"id": {"$in": payload.ids}})
    return {"ok": True, "rimossi": res.deleted_count}


# ── POST soglie in massa per categoria ────────────────────────────────────────
class SoglieMassaItem(BaseModel):
    categoria: str
    soglia_minima: float
    quantita_riordino: float = 0.0

class SoglieMassaReq(BaseModel):
    regole: List[SoglieMassaItem]
    solo_mancanti: bool = True  # True: non sovrascrive le soglie gia' impostate a mano

@router.post("/soglie-massa")
async def soglie_massa(payload: SoglieMassaReq):
    """Imposta la soglia di riordino per intere categorie in un colpo.
    Con solo_mancanti=True rispetta le soglie gia' messe a mano (non le tocca)."""
    aggiornati = 0
    for r in payload.regole:
        filtro = {"categoria": r.categoria}
        if payload.solo_mancanti:
            filtro["$or"] = [{"soglia_minima": {"$exists": False}},
                             {"soglia_minima": None}, {"soglia_minima": 0}]
        res = await db.magazzino_bar_prodotti.update_many(
            filtro,
            {"$set": {"soglia_minima": round(r.soglia_minima, 3),
                      "quantita_riordino": round(r.quantita_riordino, 3)}},
        )
        aggiornati += res.modified_count
    return {"ok": True, "prodotti_aggiornati": aggiornati}

def _norm_nome(s):
    import re
    return re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip()


@router.get("/soglie-suggerite")
async def soglie_suggerite():
    """Propone una soglia di riordino per ogni prodotto bar, calcolata dallo
    storico acquisti reale (fatture): soglia = quantita media di un acquisto
    tipico, arrotondata. Nessun valore inventato. L'utente la accetta o modifica."""
    import math
    from collections import defaultdict
    prodotti = await db.magazzino_bar_prodotti.find({}, {"_id": 0, "id": 1, "nome": 1, "soglia_minima": 1, "categoria": 1}).to_list(2000)
    # storico acquisti dalle fatture, indicizzato per nome normalizzato
    acquisti = defaultdict(list)
    async for f in db.fatture.find({}, {"_id": 0, "prodotti": 1}):
        for p in (f.get("prodotti") or []):
            nome = _norm_nome(p.get("descrizione"))
            try:
                q = float(str(p.get("quantita") or 0).replace(",", "."))
            except Exception:
                q = 0
            if nome and q > 0:
                acquisti[nome].append(q)
    out = []
    for prod in prodotti:
        chiave = _norm_nome(prod.get("nome"))
        # match esatto o per contenimento (il nome magazzino e quello fattura possono differire)
        storico = acquisti.get(chiave, [])
        if not storico:
            for k, v in acquisti.items():
                if chiave and (chiave in k or k in chiave) and len(chiave) > 4:
                    storico = v
                    break
        if not storico:
            continue
        media = sum(storico) / len(storico)
        suggerita = max(1, math.ceil(media))
        out.append({
            "id": prod.get("id"), "nome": prod.get("nome"), "categoria": prod.get("categoria"),
            "soglia_attuale": prod.get("soglia_minima", 0) or 0,
            "soglia_suggerita": suggerita, "acquisti_storici": len(storico),
        })
    out.sort(key=lambda x: -x["acquisti_storici"])
    return {"totale": len(out), "suggerimenti": out}


class ApplicaSuggeriteReq(BaseModel):
    ids: List[str] = []          # se vuoto: applica a tutti i suggeriti
    solo_mancanti: bool = True   # non sovrascrive le soglie gia' impostate

@router.post("/soglie-suggerite/applica")
async def applica_soglie_suggerite(payload: ApplicaSuggeriteReq = Body(...)):
    """Applica le soglie suggerite (dallo storico). Con solo_mancanti rispetta
    quelle gia' messe a mano. Calcola di nuovo i suggerimenti per sicurezza."""
    sugg = (await soglie_suggerite())["suggerimenti"]
    if payload.ids:
        sugg = [s for s in sugg if s["id"] in payload.ids]
    n = 0
    for s in sugg:
        if payload.solo_mancanti and (s["soglia_attuale"] or 0) > 0:
            continue
        await db.magazzino_bar_prodotti.update_one(
            {"id": s["id"]},
            {"$set": {"soglia_minima": s["soglia_suggerita"],
                      "quantita_riordino": s["soglia_suggerita"]}},
        )
        n += 1
    return {"ok": True, "applicate": n}


@router.get("/categorie-soglie")
async def categorie_soglie():
    """Riepilogo per categoria: quanti prodotti, quanti senza soglia, soglia media.
    Serve alla UI per proporre le soglie in massa."""
    pipeline = [
        {"$group": {
            "_id": "$categoria",
            "totale": {"$sum": 1},
            "senza_soglia": {"$sum": {"$cond": [{"$gt": [{"$ifNull": ["$soglia_minima", 0]}, 0]}, 0, 1]}},
        }},
        {"$sort": {"totale": -1}},
    ]
    cats = await db.magazzino_bar_prodotti.aggregate(pipeline).to_list(100)
    return {"categorie": [{"categoria": c["_id"] or "(senza categoria)",
                           "totale": c["totale"], "senza_soglia": c["senza_soglia"]} for c in cats]}


# ── PATCH configurazione collo (pezzi per cassa/cartone) ──────────────────────
class ColloUpdate(BaseModel):
    pezzi_per_collo: float
    unita_collo: Optional[str] = "cassa"
    unita: Optional[str] = None  # opzionale: aggiorna anche l'unità del pezzo singolo


@router.patch("/prodotti/{prodotto_id}/collo")
async def aggiorna_collo(prodotto_id: str, payload: ColloUpdate):
    """Configura quanti pezzi singoli contiene un collo (es. Coca: 24, acqua: 6, prosecco: 6).
    Indispensabile perché il carico in casse venga convertito correttamente in pezzi."""
    campi = {
        "pezzi_per_collo": round(payload.pezzi_per_collo, 3),
        "unita_collo": payload.unita_collo or "cassa",
    }
    if payload.unita:
        campi["unita"] = payload.unita
    res = await db.magazzino_bar_prodotti.update_one({"id": prodotto_id}, {"$set": campi})
    if res.matched_count == 0:
        raise HTTPException(404, "Prodotto non trovato")
    prod = await db.magazzino_bar_prodotti.find_one({"id": prodotto_id}, {"_id": 0})
    return prod


# ── Configurazione colli in blocco (una sola volta) ───────────────────────────
class RigaCollo(BaseModel):
    prodotto_id: str
    pezzi_per_collo: float
    unita_collo: Optional[str] = "cassa"
    unita: Optional[str] = None


class ColliBulkPayload(BaseModel):
    righe: List[RigaCollo]


@router.post("/colli-bulk")
async def configura_colli_bulk(payload: ColliBulkPayload):
    """Configura in un'unica operazione i pezzi-per-collo di tutti i prodotti.
    Pensato per la schermata di setup iniziale: prosecco=6, Coca=24, acqua=6, ecc."""
    from pymongo import UpdateOne

    ops = []
    for r in payload.righe:
        campi = {
            "pezzi_per_collo": round(r.pezzi_per_collo, 3),
            "unita_collo": r.unita_collo or "cassa",
        }
        if r.unita:
            campi["unita"] = r.unita
        ops.append(UpdateOne({"id": r.prodotto_id}, {"$set": campi}))

    if not ops:
        return {"ok": True, "aggiornati": 0}

    res = await db.magazzino_bar_prodotti.bulk_write(ops, ordered=False)
    return {"ok": True, "aggiornati": res.modified_count + res.upserted_count}


# ── LINEA MAGAZZINO (inventario fisico) ───────────────────────────────────────
# Modello a due giacenze:
#   - stock        = giacenza in magazzino (in pezzi). Lo scarico tocca SOLO questa.
#   - scorta_frigo = scorta fissa nei cassetti/frigo (default 20 pezzi). Concorre al
#                    totale ma non viene mai scalata dallo scarico.
#   - totale       = stock + scorta_frigo (mostrato all'operatore)
SCORTA_FRIGO_DEFAULT = 20


class RigaLinea(BaseModel):
    prodotto_id: str
    quantita: float                       # quanto contato in magazzino
    in_colli: Optional[bool] = False      # True = quantita in casse; False = pezzi


class LineaPayload(BaseModel):
    righe: List[RigaLinea]
    operatore_nome: Optional[str] = ""
    scorta_frigo: Optional[float] = None  # se None usa il valore per prodotto o il default


@router.get("/linea")
async def get_linea():
    """Tutti i prodotti con la giacenza attuale per l'inventario fisico.
    Ritorna magazzino (stock), scorta frigo e totale = stock + frigo."""
    docs = await db.magazzino_bar_prodotti.find({}, {"_id": 0}).sort("categoria", 1).to_list(1000)
    righe = []
    for p in docs:
        stock = float(p.get("stock", 0) or 0)
        frigo = float(p.get("scorta_frigo", SCORTA_FRIGO_DEFAULT) or 0)
        righe.append({
            **p,
            "scorta_frigo": frigo,
            "totale": round(stock + frigo, 3),
        })
    return righe


@router.post("/linea")
async def salva_linea(payload: LineaPayload):
    """Allinea il magazzino all'inventario fisico.
    Per ogni prodotto imposta la giacenza di magazzino contata (in pezzi o colli)
    e assegna la scorta frigo (default 20). Registra un movimento di rettifica."""
    aggiornati = 0
    dettagli = []
    for r in payload.righe:
        prod = await db.magazzino_bar_prodotti.find_one({"id": r.prodotto_id})
        if not prod:
            continue
        pezzi_collo = float(prod.get("pezzi_per_collo", 1) or 1)
        nuovo_stock = r.quantita * pezzi_collo if r.in_colli else r.quantita
        nuovo_stock = round(nuovo_stock, 3)

        frigo = payload.scorta_frigo
        if frigo is None:
            frigo = float(prod.get("scorta_frigo", SCORTA_FRIGO_DEFAULT) or SCORTA_FRIGO_DEFAULT)
        frigo = round(float(frigo), 3)

        stock_precedente = float(prod.get("stock", 0) or 0)
        await db.magazzino_bar_prodotti.update_one(
            {"id": r.prodotto_id},
            {"$set": {"stock": nuovo_stock, "scorta_frigo": frigo}},
        )

        # Movimento di rettifica inventario (differenza rispetto al precedente)
        delta = round(nuovo_stock - stock_precedente, 3)
        if delta != 0:
            await db.magazzino_bar_movimenti.insert_one({
                "id": str(uuid.uuid4()),
                "prodotto_id": r.prodotto_id,
                "prodotto_nome": prod["nome"],
                "tipo": "rettifica_linea",
                "quantita": abs(delta),
                "segno": "+" if delta > 0 else "-",
                "unita": prod.get("unita", "pz"),
                "stock_dopo": nuovo_stock,
                "operatore_nome": payload.operatore_nome or "linea",
                "nota": f"Inventario: magazzino {stock_precedente:g} → {nuovo_stock:g}, frigo {frigo:g}",
                "data": datetime.now(timezone.utc).isoformat(),
            })
        aggiornati += 1
        dettagli.append({
            "prodotto_id": r.prodotto_id,
            "nome": prod["nome"],
            "stock_magazzino": nuovo_stock,
            "scorta_frigo": frigo,
            "totale": round(nuovo_stock + frigo, 3),
        })
    return {"ok": True, "prodotti_allineati": aggiornati, "dettagli": dettagli}


# ── GET soglie suggerite da fatture (media quantità acquistata) ────────────────
@router.get("/soglie-suggest")
async def soglie_suggest():
    """
    Per ogni prodotto bar, cerca nei lotti_fornitori una corrispondenza per nome
    e calcola la media delle quantità acquistate come soglia suggerita.
    """
    prodotti = await db.magazzino_bar_prodotti.find({}, {"_id": 0}).to_list(500)
    lotti = await db.lotti_fornitori.find(
        {}, {"_id": 0, "prodotto_nome": 1, "quantita_acquistata": 1}
    ).to_list(3000)

    suggerimenti = []
    for prod in prodotti:
        nome_bar = prod["nome"].lower()
        parole = [w for w in nome_bar.split() if len(w) > 3]
        matching = []
        for lotto in lotti:
            lot_nome = (lotto.get("prodotto_nome") or "").lower()
            # Match se almeno 1 parola significativa coincide O nome del bar è substring
            if nome_bar in lot_nome or any(p in lot_nome for p in parole):
                qty = float(lotto.get("quantita_acquistata") or 0)
                if qty > 0:
                    matching.append(qty)

        if matching:
            avg = sum(matching) / len(matching)
            # 30% della media come soglia minima (arrotondato a .5)
            suggerita = max(0.5, round(avg * 0.30 * 2) / 2)
        else:
            suggerita = float(prod.get("soglia_minima") or 1.0)

        suggerimenti.append(
            {
                "prodotto_id": prod["id"],
                "nome": prod["nome"],
                "categoria": prod.get("categoria", ""),
                "stock_attuale": float(prod.get("stock", 0)),
                "soglia_corrente": float(prod.get("soglia_minima") or 0),
                "soglia_suggerita": suggerita,
                "n_fatture_match": len(matching),
            }
        )

    suggerimenti.sort(key=lambda x: x["n_fatture_match"], reverse=True)
    return suggerimenti


# ── POST riordina prodotti sotto soglia ────────────────────────────────────────
@router.post("/riordina")
async def riordina_sotto_soglia(operatore_nome: str = "Amministratore"):
    """Riordino manuale dei prodotti bar sotto soglia: delega al MOTORE UNICO
    (bozze per fornitore, dedup incrociata, source riordino_auto). Prima
    creava un ordine parallelo con stato legacy 'inviato' che nessun flusso
    (dedup, riconciliazione, ricezione, pendenti) leggeva: mai chiuso e
    prodotti duplicati nelle bozze del giorno dopo."""
    from app.lotti.routers.ordini_fornitori import esegui_riordino_automatico
    esito = await esegui_riordino_automatico(dry_run=False)
    return {
        "ok": True,
        "message": "Riordino eseguito col motore unico",
        "bozze_create": esito.get("bozze_create", esito.get("bozze_che_verrebbero_create", [])),
        "n_prodotti": esito.get("prodotti_riordinati", 0),
    }


# ── POST imposta soglie su tutti i prodotti (richiesta Enzo 02/07/2026) ──────
@router.post("/soglie-imposta-tutte")
async def soglie_imposta_tutte(soglia: float = Query(1, ge=0),
                               quantita: float = Query(1, ge=0),
                               solo_mancanti: bool = Query(False)):
    """Imposta soglia_minima e quantita_riordino su TUTTI i prodotti bar
    ("per semplicità metti ovunque soglia 1 e quantità 1"). Con
    solo_mancanti=true tocca solo i prodotti senza soglia."""
    filtro = {}
    if solo_mancanti:
        filtro = {"$or": [{"soglia_minima": {"$exists": False}},
                           {"soglia_minima": None}, {"soglia_minima": 0}]}
    res = await db.magazzino_bar_prodotti.update_many(
        filtro, {"$set": {"soglia_minima": float(soglia),
                           "quantita_riordino": float(quantita)}})
    return {"ok": True, "aggiornati": res.modified_count,
            "soglia": soglia, "quantita": quantita}


# ── GET report giacenze HTML (stampabile come PDF) ─────────────────────────────
@router.get("/report-giacenze", response_class=HTMLResponse)
async def report_giacenze():
    """Report settimanale giacenze: Magazzino Bar + Materie Prime (lotti attivi)."""
    oggi = date.today()
    lunedi = oggi - timedelta(days=oggi.weekday())
    domenica = lunedi + timedelta(days=6)
    periodo = f"{lunedi.strftime('%d/%m/%Y')} — {domenica.strftime('%d/%m/%Y')}"

    bar = await db.magazzino_bar_prodotti.find({}, {"_id": 0}).sort("categoria", 1).to_list(500)
    lotti = (
        await db.lotti_fornitori.find(
            {"esaurito": {"$ne": True}, "quantita_disponibile": {"$gt": 0}},
            {
                "_id": 0,
                "prodotto_nome": 1,
                "fornitore": 1,
                "quantita_disponibile": 1,
                "unita_misura": 1,
                "data_scadenza": 1,
                "giorni_alla_scadenza": 1,
            },
        )
        .sort("giorni_alla_scadenza", 1)
        .to_list(1000)
    )

    def stato_badge(stock, soglia):
        if stock == 0:
            return '<span style="color:#dc2626;font-weight:800">ESAURITO</span>'
        if soglia and soglia > 0 and stock < soglia:
            return '<span style="color:#d97706;font-weight:800">SOTTO SOGLIA</span>'
        return '<span style="color:#16a34a;font-weight:700">OK</span>'

    def scadenza_style(giorni):
        if giorni is None:
            return ""
        if giorni < 7:
            return "color:#dc2626;font-weight:800"
        if giorni < 30:
            return "color:#d97706;font-weight:700"
        return "color:#374151"

    # ── Sezione Bar ──────────────────────────────────────────────────────────
    bar_rows = ""
    for p in bar:
        stock = float(p.get("stock", 0))
        soglia = float(p.get("soglia_minima") or 0)
        bg = "#fef2f2" if stock == 0 else ("#fffbeb" if (soglia > 0 and stock < soglia) else "#fff")
        bar_rows += f"""
        <tr style="background:{bg}">
          <td>{p['nome']}</td>
          <td>{p.get('categoria','')}</td>
          <td style="text-align:right;font-weight:800">{stock}</td>
          <td>{p.get('unita','pz')}</td>
          <td style="text-align:right">{soglia if soglia > 0 else '—'}</td>
          <td style="text-align:center">{stato_badge(stock, soglia)}</td>
        </tr>"""

    n_esauriti = sum(1 for p in bar if float(p.get("stock", 0)) == 0)
    n_sotto = sum(
        1
        for p in bar
        if float(p.get("stock", 0)) > 0
        and float(p.get("soglia_minima") or 0) > 0
        and float(p.get("stock", 0)) < float(p.get("soglia_minima") or 0)
    )

    # ── Sezione Materie Prime ────────────────────────────────────────────────
    mp_rows = ""
    for l in lotti:
        g = l.get("giorni_alla_scadenza")
        style_sc = scadenza_style(g)
        mp_rows += f"""
        <tr>
          <td>{l.get('prodotto_nome','—')}</td>
          <td>{l.get('fornitore','—')}</td>
          <td style="text-align:right;font-weight:700">{l.get('quantita_disponibile',0)}</td>
          <td>{l.get('unita_misura','—')}</td>
          <td style="{style_sc}">{l.get('data_scadenza','—')}</td>
          <td style="{style_sc};text-align:right">{g if g is not None else '—'}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<title>Report Giacenze — {periodo}</title>
<style>
  @page {{ size: A4; margin: 15mm 12mm; }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: Arial, sans-serif; font-size: 9pt; color: #1e293b; }}
  .no-print {{ background:#1e40af; color:#fff; padding:14px 20px; display:flex; justify-content:space-between; align-items:center; }}
  .no-print button {{ background:#fff; color:#1e40af; border:none; padding:10px 22px; border-radius:8px; font-weight:800; font-size:13px; cursor:pointer; }}
  @media print {{ .no-print {{ display:none; }} }}
  h1 {{ font-size:14pt; font-weight:800; margin:14px 0 4px; }}
  h2 {{ font-size:11pt; font-weight:800; color:#1e40af; margin:16px 0 8px; border-bottom:2px solid #dbeafe; padding-bottom:4px; }}
  .meta {{ font-size:8pt; color:#64748b; margin-bottom:12px; }}
  .stats {{ display:flex; gap:12px; margin-bottom:12px; }}
  .stat {{ background:#f8fafc; border:1px solid #e2e8f0; border-radius:6px; padding:6px 12px; font-size:8pt; }}
  .stat strong {{ font-size:12pt; font-weight:800; display:block; }}
  table {{ width:100%; border-collapse:collapse; margin-bottom:16px; font-size:8pt; }}
  th {{ background:#1e40af; color:#fff; padding:5px 7px; text-align:left; font-size:7.5pt; }}
  td {{ padding:4px 7px; border-bottom:1px solid #f1f5f9; vertical-align:middle; }}
  tr:hover {{ background:#f8fafc; }}
</style>
</head>
<body>
<div class="no-print">
  <div>
    <strong>Report Giacenze Settimanale</strong>
    <span style="font-size:12px;margin-left:12px;opacity:0.8">Ceraldi Group — {periodo}</span>
  </div>
  <button onclick="window.print()">Stampa / Salva PDF</button>
</div>

<h1>Report Giacenze Settimanale</h1>
<div class="meta">Periodo: {periodo} &nbsp;·&nbsp; Generato: {datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M")} UTC</div>

<div class="stats">
  <div class="stat"><strong>{len(bar)}</strong>prodotti bar</div>
  <div class="stat"><strong style="color:#dc2626">{n_esauriti}</strong>esauriti</div>
  <div class="stat"><strong style="color:#d97706">{n_sotto}</strong>sotto soglia</div>
  <div class="stat"><strong>{len(lotti)}</strong>lotti materie prime attivi</div>
</div>

<h2>Magazzino Bar</h2>
<table>
  <thead><tr>
    <th>Prodotto</th><th>Categoria</th><th style="text-align:right">Stock</th>
    <th>Unità</th><th style="text-align:right">Soglia Min</th><th style="text-align:center">Stato</th>
  </tr></thead>
  <tbody>{bar_rows}</tbody>
</table>

<h2>Materie Prime — Lotti Attivi ({len(lotti)})</h2>
<table>
  <thead><tr>
    <th>Prodotto</th><th>Fornitore</th><th style="text-align:right">Qty Disponibile</th>
    <th>Unità</th><th>Scadenza</th><th style="text-align:right">Giorni</th>
  </tr></thead>
  <tbody>{mp_rows}</tbody>
</table>
</body>
</html>"""
    return HTMLResponse(content=html)


# ── POST sincronizza prodotti default (aggiunge quelli mancanti) ──────────────
@router.post("/sync-prodotti-default")
async def sync_prodotti_default():
    """
    Aggiunge al DB i prodotti presenti in PRODOTTI_DEFAULT ma non ancora salvati.
    Non modifica quelli già esistenti. Usare dopo aggiornamenti al seed.
    """
    esistenti_nomi = set(
        doc["nome"]
        for doc in await db.magazzino_bar_prodotti.find({}, {"_id": 0, "nome": 1}).to_list(1000)
    )
    nuovi = []
    for p in PRODOTTI_DEFAULT:
        if p["nome"] not in esistenti_nomi:
            nuovi.append({"id": str(uuid.uuid4()), **p})

    if nuovi:
        await db.magazzino_bar_prodotti.insert_many(nuovi)

    return {
        "ok": True,
        "aggiunti": len(nuovi),
        "gia_presenti": len(esistenti_nomi),
        "totale": len(esistenti_nomi) + len(nuovi),
        "nomi_aggiunti": [n["nome"] for n in nuovi],
    }


# ── ACCORPAMENTO CATEGORIE (permanente) ───────────────────────────────────────
async def _risolvi_cat(cat):
    """Applica le regole di accorpamento: categoria 'da' -> 'a'. Segue la catena (max 5)."""
    c = (cat or "").strip()
    if not c:
        return c
    try:
        for _ in range(5):
            rule = await db.magazzino_bar_cat_merge.find_one({"da": c}, {"_id": 0, "a": 1})
            if not rule or not rule.get("a") or rule["a"] == c:
                break
            c = rule["a"]
    except Exception:
        _LOG_INIT.debug("[magazzino_bar] errore non bloccante ignorato")
    return c


@router.get("/categorie")
async def categorie_con_conteggio():
    """Categorie del magazzino bar con numero prodotti + regole di accorpamento attive."""
    pipeline = [{"$group": {"_id": "$categoria", "n": {"$sum": 1}}}, {"$sort": {"_id": 1}}]
    rows = await db.magazzino_bar_prodotti.aggregate(pipeline).to_list(300)
    cats = [{"categoria": (r["_id"] or "(senza)"), "prodotti": r["n"]} for r in rows]
    merges = await db.magazzino_bar_cat_merge.find({}, {"_id": 0}).to_list(300)
    return {"categorie": cats, "accorpamenti": merges}


class AccorpaCat(BaseModel):
    da: str
    a: str


@router.post("/accorpa-categoria")
async def accorpa_categoria(payload: AccorpaCat, _admin=Depends(require_admin)):
    """Accorpa la categoria 'da' nella 'a': sposta i prodotti e salva la regola permanente."""
    da = (payload.da or "").strip()
    a = (payload.a or "").strip()
    if not da or not a:
        return {"ok": False, "error": "categorie mancanti"}
    if da == a:
        return {"ok": False, "error": "categoria di origine e destinazione uguali"}
    res = await db.magazzino_bar_prodotti.update_many({"categoria": da}, {"$set": {"categoria": a}})
    # regola permanente (idempotente)
    await db.magazzino_bar_cat_merge.update_one({"da": da}, {"$set": {"da": da, "a": a}}, upsert=True)
    # eventuali regole che puntavano a 'da' ora puntano ad 'a'
    await db.magazzino_bar_cat_merge.update_many({"a": da}, {"$set": {"a": a}})
    # non lasciare una regola a->a
    await db.magazzino_bar_cat_merge.delete_many({"$expr": {"$eq": ["$da", "$a"]}})
    return {"ok": True, "spostati": res.modified_count, "da": da, "a": a}


@router.delete("/accorpa-categoria/{da}")
async def annulla_accorpamento(da: str):
    res = await db.magazzino_bar_cat_merge.delete_one({"da": da})
    return {"ok": True, "rimosse": res.deleted_count}

# ── Pezzi per collo derivati AUTOMATICAMENTE dal nome (dato presente in fattura XML) ──
import re as _re
_PEZZI_PAT = _re.compile(
    r"(\d+)\s*(?:pz|pezzi|bott(?:iglie)?|bt|cps?|capsule|cialde)\b", _re.IGNORECASE
)

def _pezzi_da_nome(nome: str):
    """Estrae il numero di pezzi per collo dal nome prodotto.
    Es: 'Acqua 50cl (cassa 24pz)' -> 24 ; 'Prosecco (cartone 6bt)' -> 6 ;
    'Cialde Kimbo Box 150pz' -> 150. Ritorna None se non c'e' un collo."""
    if not nome:
        return None
    matches = _PEZZI_PAT.findall(nome)
    if not matches:
        return None
    n = int(matches[-1])
    return n if n > 1 else None

def _unita_collo_da_nome(nome: str):
    n = (nome or "").lower()
    if "cassa" in n:
        return "cassa"
    if "cartone" in n or "cartoni" in n:
        return "cartone"
    if "rotolo" in n:
        return "rotolo"
    if "box" in n:
        return "box"
    if "cf" in n or "conf" in n:
        return "confezione"
    return "collo"


@router.post("/auto-configura-colli")
async def auto_configura_colli():
    """Imposta pezzi_per_collo per TUTTI i prodotti leggendo il dato dal nome (presente in fattura XML).
    Nessuna configurazione manuale: 'cassa 24pz' -> 24, 'cartone 6bt' -> 6, ecc."""
    prods = await db.magazzino_bar_prodotti.find(
        {}, {"_id": 0, "id": 1, "nome": 1, "pezzi_per_collo": 1}
    ).to_list(2000)
    aggiornati = 0
    dettaglio = []
    for p in prods:
        n = _pezzi_da_nome(p.get("nome", ""))
        if not n:
            continue
        if int(float(p.get("pezzi_per_collo") or 1)) == n:
            continue
        await db.magazzino_bar_prodotti.update_one(
            {"id": p["id"]},
            {"$set": {"pezzi_per_collo": n, "unita_collo": _unita_collo_da_nome(p.get("nome", ""))}},
        )
        aggiornati += 1
        dettaglio.append({"nome": p.get("nome", ""), "pezzi_per_collo": n})
    return {"ok": True, "aggiornati": aggiornati, "totale": len(prods), "dettaglio": dettaglio}

