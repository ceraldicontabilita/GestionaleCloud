"""
Router per la gestione dei Lotti.
"""

from fastapi import APIRouter, Depends, HTTPException, Query

# 25/07/2026 — Enzo: «il dipendente deve solo produrre e vedere le ricette,
# tutto il resto lo guardo e lo uso io: metti tutto sotto PIN». Cancellare un
# lotto è la cosa più definitiva che si possa fare alla tracciabilità.
from app.lotti.auth import require_admin
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict
from datetime import datetime, timezone, timedelta
import uuid
import logging
_LOG_INIT = logging.getLogger("uvicorn.error")
import re

router = APIRouter(prefix="/lotti", tags=["Lotti"])

from app.lotti.db import database as db
from app.lotti.servizi.lotti_service import crea_lotto

# ==================== MODELLI ====================


class LottoCreate(BaseModel):
    prodotto: str
    ingredienti_dettaglio: List[str] = []
    data_produzione: str
    data_scadenza: str
    numero_lotto: str
    etichetta: str = ""
    quantita: float = 1
    unita_misura: str = "pz"


class Lotto(LottoCreate):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    scadenza_abbattuto: str = ""
    mesi_abbattuto: int = 0
    ingrediente_critico: str = ""
    conservazione_note: str = ""
    allergeni: List[str] = []
    allergeni_dettaglio: Dict = {}
    allergeni_testo: str = ""
    progressivo: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ==================== ENDPOINTS ====================


def _normalizza_lotto(it: dict) -> dict:
    """Normalizza un lotto fra i due schemi DB (usato da piu endpoint)."""
    n = dict(it)
    if not n.get("prodotto") and n.get("prodotto_nome"):
        n["prodotto"] = n["prodotto_nome"]
    if not n.get("numero_lotto") and n.get("lotto_id"):
        n["numero_lotto"] = n["lotto_id"]
    if not n.get("id") and n.get("lotto_id"):
        n["id"] = n["lotto_id"]
    n.setdefault("stato", "attivo")
    n.setdefault("consumato", False)
    n.setdefault("data_consumo", None)
    from app.lotti.servizi.lotto_arricchimento_service import arricchisci_lotto
    return arricchisci_lotto(n)


@router.get("")
async def get_lotti(
    search: Optional[str] = Query(None),
    data_da: Optional[str] = Query(None),
    data_a: Optional[str] = Query(None),
    limit: int = Query(1000),
):
    """Lista lotti con ricerca e filtri data — normalizza entrambi gli schemi DB"""
    query: dict = {}
    if search:
        query["$or"] = [
            {"prodotto": {"$regex": search, "$options": "i"}},
            {"prodotto_nome": {"$regex": search, "$options": "i"}},
            {"numero_lotto": {"$regex": search, "$options": "i"}},
            {"lotto_id": {"$regex": search, "$options": "i"}},
        ]

    items = await db.lotti.find(query, {"_id": 0}).sort("created_at", -1).to_list(limit)

    # Filtro data robusto: confronto su date reali (il campo data_produzione è stringa DD/MM/YYYY,
    # il confronto stringa $gte/$lte non rispetta l'ordine cronologico).
    if data_da or data_a:
        def _parse(s):
            if not s:
                return None
            s = str(s).strip()
            for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
                try:
                    return datetime.strptime(s[:10], fmt).date()
                except Exception:
                    continue
            return None
        d_da = _parse(data_da)
        d_a = _parse(data_a)
        filtrati = []
        for it in items:
            dp = _parse(it.get("data_produzione"))
            if dp is None:
                continue
            if d_da and dp < d_da:
                continue
            if d_a and dp > d_a:
                continue
            filtrati.append(it)
        items = filtrati

    return [_normalizza_lotto(it) for it in items]


@router.get("/cerca-universale")
async def cerca_universale(q: str = Query(...), limit: int = Query(100)):
    """Ricerca tracciabilità per QUALSIASI estremo: numero lotto, prodotto,
    fornitore, lotto fornitore, date, operatore e DENTRO i lotti fornitori
    scalati (controlli ASL: da un lotto fornitore ai prodotti finiti che lo
    contengono). Restituisce {query, totale, risultati} con match_in."""
    rx = {"$regex": re.escape(q), "$options": "i"}
    query = {"$or": [
        {"prodotto": rx},
        {"prodotto_nome": rx},
        {"numero_lotto": rx},
        {"lotto_id": rx},
        {"fornitore": rx},
        {"lotto_fornitore": rx},
        {"data_produzione": rx},
        {"data_scadenza": rx},
        {"operatore_nome": rx},
        {"lotti_fornitori.lotti_scalati.fornitore": rx},
        {"lotti_fornitori.lotti_scalati.lotto_id_fornitore": rx},
        {"lotti_fornitori.lotti_scalati.fattura_ref": rx},
        {"lotti_fornitori.lotti_scalati.prodotto": rx},
        {"lotti_fornitori.lotti_scalati.ingrediente": rx},
    ]}
    items = await db.lotti.find(query, {"_id": 0}).sort("created_at", -1).to_list(limit)
    ql = q.lower()
    risultati = []
    for it in items:
        n = _normalizza_lotto(it)
        # match_in: in quali campi compare la query (atteso dal frontend)
        campi = {
            "numero lotto": n.get("numero_lotto"),
            "prodotto": n.get("prodotto"),
            "fornitore": n.get("fornitore"),
            "lotto fornitore": n.get("lotto_fornitore"),
            "data": n.get("data_produzione"),
        }
        n["match_in"] = [k for k, v in campi.items() if v and ql in str(v).lower()]
        # match dentro i lotti fornitori scalati (tracciabilità ASL)
        scal = (it.get("lotti_fornitori") or {}).get("lotti_scalati") or []
        for s in scal:
            if ql in (s.get("fornitore") or "").lower():
                n["match_in"].append(f"fornitore: {s.get('fornitore')}")
            if ql in str(s.get("lotto_id_fornitore") or "").lower():
                n["match_in"].append(f"lotto fornitore: {s.get('lotto_id_fornitore')}")
            if ql in str(s.get("fattura_ref") or "").lower():
                n["match_in"].append(f"fattura: {s.get('fattura_ref')}")
            if ql in (s.get("prodotto") or s.get("ingrediente") or "").lower():
                n["match_in"].append(f"ingrediente: {s.get('prodotto') or s.get('ingrediente')}")
        risultati.append(n)
    return {"query": q, "totale": len(risultati), "risultati": risultati}


class AbbattimentoPesce(BaseModel):
    prodotto: str
    fornitore: str = ""
    lotto_fornitore: str = ""
    quantita_kg: float = 0
    operatore: str = ""
    inizio: str = ""
    note: str = ""


@router.post("/abbattimento-pesce")
async def registra_abbattimento_pesce(body: AbbattimentoPesce):
    """Registra l'abbattimento del pesce per consumo crudo/poco cotto nel
    sistema lotti UNICO (Reg. CE 853/2004: ≥24h a -20°C). Il lotto entra in
    tracciabilità, ricerca universale e richiami come ogni altro lotto."""
    if not body.prodotto.strip():
        raise HTTPException(400, "Prodotto obbligatorio")
    oggi = datetime.now().date().isoformat()
    lid = str(uuid.uuid4())
    numero = f"PES-{oggi.replace('-', '')}-{lid[:4].upper()}"
    from app.lotti.routers.utils import _calcola_scadenza
    try:
        scad = _calcola_scadenza(["pesce"], oggi, metodo_conservazione="abbattitore_negativo")
        data_scadenza = scad[1] or scad[0]
    except Exception:
        data_scadenza = None
    lotto = {
        "id": lid,
        "numero_lotto": numero,
        "prodotto": body.prodotto.strip(),
        "tipo": "abbattimento_pesce",
        "source": "pesce",
        "fornitore": body.fornitore.strip(),
        "lotto_fornitore": body.lotto_fornitore.strip(),
        "quantita_kg": float(body.quantita_kg or 0),
        "operatore_nome": body.operatore.strip(),
        "abbattimento": {
            "inizio": body.inizio or datetime.now(timezone.utc).isoformat(),
            "regola": "≥24h a -20°C (Reg. CE 853/2004, consumo crudo)",
        },
        "data_produzione": oggi,
        "data_scadenza": data_scadenza,
        "esaurito": False,
        "note": body.note,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    lotto = await crea_lotto(lotto, origine="manuale")
    return {"ok": True, "lotto": lotto}


class RicevimentoPesce(BaseModel):
    prodotto: str
    denominazione: str = ""
    metodo: str = "pescato"
    zona_fao: str = ""
    fornitore: str = ""
    lotto_fornitore: str = ""
    quantita_kg: float = 0
    temperatura_arrivo: str = ""
    stato_imballo: str = "integro"
    data_scadenza: str = ""
    allergeni: list = ["pesce"]
    operatore: str = ""
    note: str = ""


@router.post("/ricevimento-pesce")
async def registra_ricevimento_pesce(body: RicevimentoPesce):
    """Registra il RICEVIMENTO del pesce nel sistema lotti unico: lotto,
    fornitore, temperatura, stato imballo, scadenza, denominazione e zona
    (Reg. UE 1379/2013), allergeni. Tracciabile e richiamabile da subito."""
    if not body.prodotto.strip():
        raise HTTPException(400, "Prodotto obbligatorio")
    oggi = datetime.now().date().isoformat()
    lid = str(uuid.uuid4())
    numero = f"PESR-{oggi.replace('-', '')}-{lid[:4].upper()}"
    data_scadenza = (body.data_scadenza or "").strip() or None
    if not data_scadenza:
        from app.lotti.routers.utils import _calcola_scadenza
        try:
            scad = _calcola_scadenza(["pesce"], oggi, metodo_conservazione="frigo")
            data_scadenza = scad[0]
        except Exception:
            data_scadenza = None
    lotto = {
        "id": lid,
        "numero_lotto": numero,
        "prodotto": body.prodotto.strip(),
        "tipo": "pesce_ricevimento",
        "source": "pesce",
        "denominazione": body.denominazione.strip(),
        "metodo_produzione": body.metodo,
        "zona_fao": body.zona_fao.strip(),
        "fornitore": body.fornitore.strip(),
        "lotto_fornitore": body.lotto_fornitore.strip(),
        "quantita_kg": float(body.quantita_kg or 0),
        "temperatura_arrivo": body.temperatura_arrivo.strip(),
        "stato_imballo": body.stato_imballo,
        "allergeni": [a for a in (body.allergeni or []) if a],
        "operatore_nome": body.operatore.strip(),
        "data_produzione": oggi,
        "data_scadenza": data_scadenza,
        "esaurito": False,
        "note": body.note,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if body.stato_imballo != "integro":
        lotto["anomalia"] = "Imballo danneggiato al ricevimento"
    lotto = await crea_lotto(lotto, origine="manuale")
    return {"ok": True, "lotto": lotto}


@router.put("/abbattimento-pesce/{lotto_id}/concludi")
async def concludi_abbattimento(lotto_id: str, forza: bool = Query(False), note: str = Query("")):
    """Chiude l'abbattimento: valido solo dopo >=24h a -20°C (Reg. CE 853/2004).
    Prima delle 24h viene bloccato (forza=true solo per correzioni, con nota)."""
    lotto = await db.lotti.find_one({"id": lotto_id, "tipo": "abbattimento_pesce"}, {"_id": 0})
    if not lotto:
        raise HTTPException(404, "Lotto abbattimento non trovato")
    ab = lotto.get("abbattimento") or {}
    if ab.get("fine"):
        return {"ok": True, "gia_concluso": True, "fine": ab["fine"]}
    inizio = ab.get("inizio")
    ore = None
    try:
        t0 = datetime.fromisoformat(str(inizio).replace("Z", "+00:00"))
        if t0.tzinfo is None:
            t0 = t0.replace(tzinfo=timezone.utc)
        ore = (datetime.now(timezone.utc) - t0).total_seconds() / 3600
    except Exception:
        _LOG_INIT.debug("[lotti] errore non bloccante ignorato")
    if ore is not None and ore < 24 and not forza:
        raise HTTPException(400, f"Abbattimento non completo: {ore:.1f}h su 24. Riprova tra {24 - ore:.0f} ore (o usa forza=true con nota).")
    ab["fine"] = datetime.now(timezone.utc).isoformat()
    ab["ore_effettive"] = round(ore, 1) if ore is not None else None
    ab["esito"] = "conforme" if (ore is None or ore >= 24) else f"chiuso in anticipo: {note or 'senza nota'}"
    await db.lotti.update_one({"id": lotto_id}, {"$set": {"abbattimento": ab}})
    return {"ok": True, "abbattimento": ab}


@router.get("/pesce")
async def lotti_pesce(limit: int = Query(30, ge=1, le=200)):
    """Registro pesce: ricevimenti e abbattimenti recenti (sistema unico)."""
    items = await db.lotti.find(
        {"tipo": {"$in": ["abbattimento_pesce", "pesce_ricevimento"]}}, {"_id": 0}
    ).sort("created_at", -1).to_list(limit)
    return {"totale": len(items), "lotti": items}


@router.get("/cosa-usare-oggi")
async def cosa_usare_oggi(limit: int = Query(200, ge=1, le=2000)):
    """Lotti attivi ordinati per urgenza (semaforo scadenza) e, a parità di
    urgenza, per valore economico decrescente — così l'operatore vede prima
    cosa rischia di più (rosso/arancione) e, tra pari urgenza, cosa costa
    di più lasciare andare a male."""
    from app.lotti.routers.utils import FILTRO_LOTTO_APERTO
    items = await db.lotti.find(dict(FILTRO_LOTTO_APERTO), {"_id": 0}).to_list(5000)
    normalizzati = [_normalizza_lotto(it) for it in items]
    # esclude i lotti già a quantità zero (consumati parzialmente fino a esaurimento
    # ma non ancora marcati — coerente col filtro usato altrove, es. giacenza_prodotti_finiti)
    normalizzati = [n for n in normalizzati if (n.get("quantita") or 0) > 0]
    ordine_colore = {"rosso": 0, "arancione": 1, "giallo": 2, "verde": 3, "grigio": 4}
    normalizzati.sort(key=lambda n: (
        ordine_colore.get(n["stato_scadenza"]["colore"], 5),
        -(n.get("valore_economico") or 0),
    ))
    return {"totale": len(normalizzati), "lotti": normalizzati[:limit]}


@router.get("/{lotto_id}")
async def get_lotto(lotto_id: str):
    """Ottiene un lotto per ID"""
    item = await db.lotti.find_one({"id": lotto_id}, {"_id": 0})
    if not item:
        raise HTTPException(status_code=404, detail="Lotto non trovato")
    item = dict(item)
    if "stato" not in item or item["stato"] is None:
        item["stato"] = "attivo"
    if "consumato" not in item or item["consumato"] is None:
        item["consumato"] = False
    if "data_consumo" not in item:
        item["data_consumo"] = None
    from app.lotti.servizi.lotto_arricchimento_service import arricchisci_lotto
    return arricchisci_lotto(item)


@router.get("/{lotto_id}/movimenti")
async def get_movimenti_lotto(lotto_id: str):
    """Registro movimenti grezzo del lotto (creazione, spostamenti, ecc.).
    Base per la cronologia completa (Tranche 3) — qui esposto già ora per
    poter collaudare che ogni evento venga davvero registrato."""
    from app.lotti.servizi.movimenti_lotto_service import cronologia_lotto
    return {"lotto_id": lotto_id, "movimenti": await cronologia_lotto(lotto_id)}


@router.get("/{lotto_id}/scheda-completa")
async def get_scheda_completa_lotto(lotto_id: str):
    """Gemello digitale del lotto / cronologia completa (Tranche 1 + 3):
    dati arricchiti + cronologia movimenti (arricchita con le anomalie
    collegate) + ricetta collegata (se trovata per nome — il lotto non
    salva ancora ricetta_id, solo il nome prodotto) + abbattimento (se il
    lotto lo ha attraversato, es. pesce). I pulsanti azione (stampa, apri
    fattura/recall/registro HACCP) restano lato frontend, che già ha gli
    endpoint dedicati (stampa.py, lotti/recall/*, fatture/{id}/visualizza).

    NOTA onesta sui limiti di questa cronologia: le stampe etichetta non
    sono loggate (ogni apertura della finestra di stampa non è
    distinguibile da una stampa effettiva) e i richiami (`/lotti/recall/*`)
    sono ricerche on-demand, non eventi persistiti — non compaiono qui
    finché l'app non avrà un registro dei richiami eseguiti."""
    item = await db.lotti.find_one({"id": lotto_id}, {"_id": 0})
    if not item:
        raise HTTPException(status_code=404, detail="Lotto non trovato")
    from app.lotti.servizi.lotto_arricchimento_service import arricchisci_lotto
    from app.lotti.servizi.movimenti_lotto_service import cronologia_lotto
    lotto = arricchisci_lotto(dict(item))

    ricetta = None
    if lotto.get("prodotto"):
        ricetta = await db.ricette.find_one(
            {"nome": lotto["prodotto"]}, {"_id": 0, "id": 1, "nome": 1, "reparto": 1}
        )

    movimenti = await cronologia_lotto(lotto_id)
    anomalie_ids = {
        m["documento_collegato"]["id"] for m in movimenti
        if (m.get("documento_collegato") or {}).get("tipo") == "anomalia"
    }
    anomalie_per_id = {}
    if anomalie_ids:
        docs = await db.anomalie.find(
            {"id": {"$in": list(anomalie_ids)}},
            {"_id": 0, "id": 1, "attrezzatura": 1, "categoria": 1, "descrizione": 1, "stato": 1},
        ).to_list(len(anomalie_ids))
        anomalie_per_id = {d["id"]: d for d in docs}
    richiami_ids = {
        m["documento_collegato"]["id"] for m in movimenti
        if (m.get("documento_collegato") or {}).get("tipo") == "richiamo"
    }
    richiami_per_id = {}
    if richiami_ids:
        docs = await db.richiami_eseguiti.find(
            {"id": {"$in": list(richiami_ids)}},
            {"_id": 0, "id": 1, "ingrediente": 1, "stato": 1, "motivo": 1},
        ).to_list(len(richiami_ids))
        richiami_per_id = {d["id"]: d for d in docs}

    for m in movimenti:
        doc_coll = m.get("documento_collegato") or {}
        if doc_coll.get("tipo") == "anomalia" and doc_coll.get("id") in anomalie_per_id:
            m["anomalia_collegata"] = anomalie_per_id[doc_coll["id"]]
        if doc_coll.get("tipo") == "richiamo" and doc_coll.get("id") in richiami_per_id:
            m["richiamo_collegato"] = richiami_per_id[doc_coll["id"]]

    # Ingredienti usati (mancavano in scheda — audit onesto 04/07/2026):
    # ingredienti_dettaglio sono le righe complete "prodotto  allergeni -
    # fornitore n° fatt X - data"; in mancanza, la lista semplice.
    ingredienti = item.get("ingredienti_dettaglio") or item.get("ingredienti") or []
    ingredienti = [i if isinstance(i, str) else (i.get("nome") or str(i)) for i in ingredienti]

    # Link "Apri fattura": i lotti scalati citano il lotto fornitore, che a
    # sua volta ha fattura_ref (numero fattura) — qui si risolve fino all'ID
    # fattura così il frontend apre il visualizzatore con un tocco.
    scalati = (lotto.get("lotti_fornitori") or {}).get("lotti_scalati", [])
    ids_lf = [s.get("lotto_id") for s in scalati if s.get("lotto_id")]
    ref_per_lf = {}
    if ids_lf:
        async for lf in db.lotti_fornitori.find(
            {"id": {"$in": ids_lf}}, {"_id": 0, "id": 1, "fattura_ref": 1}
        ):
            if lf.get("fattura_ref"):
                ref_per_lf[lf["id"]] = lf["fattura_ref"]
    fattura_id_per_ref = {}
    if ref_per_lf:
        async for f in db.fatture.find(
            {"numero_fattura": {"$in": list(set(ref_per_lf.values()))}},
            {"_id": 0, "id": 1, "numero_fattura": 1},
        ):
            fattura_id_per_ref[f["numero_fattura"]] = f["id"]
    for s in scalati:
        ref = ref_per_lf.get(s.get("lotto_id"))
        if ref:
            s["fattura_ref"] = ref
            if ref in fattura_id_per_ref:
                s["fattura_id"] = fattura_id_per_ref[ref]

    return {
        "lotto": lotto,
        "movimenti": movimenti,
        "ricetta_collegata": ricetta,
        "ingredienti": ingredienti,
        "lotti_fornitori_scalati": scalati,
        "abbattimento": lotto.get("abbattimento"),
    }


@router.post("", response_model=Lotto)
async def create_lotto(item: LottoCreate):
    """Crea un nuovo lotto"""
    data = item.model_dump()
    data = await crea_lotto(data, origine="manuale")
    return data


@router.delete("/{lotto_id}")
async def delete_lotto(lotto_id: str, _admin=Depends(require_admin)):
    """Elimina un lotto (cerca per id o lotto_id per compatibilità schema vecchio)"""
    result = await db.lotti.delete_one({"$or": [{"id": lotto_id}, {"lotto_id": lotto_id}]})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Lotto non trovato")
    return {"success": True}


@router.post("/archivia-scaduti")
async def archivia_scaduti(giorni: int = Query(30, ge=0, le=3650)):
    """Marca 'esaurito' i lotti scaduti da più di N giorni (default 30).
    Escono da promemoria e FIFO ma restano in archivio per la tracciabilità:
    nessun dato viene cancellato."""
    from app.lotti.routers.digest import _to_iso
    limite = (datetime.now().date() - timedelta(days=giorni)).isoformat()
    items = await db.lotti.find(
        {"esaurito": {"$ne": True}}, {"data_scadenza": 1}
    ).to_list(20000)
    oids = [it["_id"] for it in items
            if (_to_iso(it.get("data_scadenza")) or "9999") < limite]
    if not oids:
        return {"ok": True, "archiviati": 0, "soglia_data": limite}
    upd = await db.lotti.update_many(
        {"_id": {"$in": oids}},
        {"$set": {"esaurito": True,
                  "stato": "esaurito",  # campo gemello: senza, i filtri sullo stato lo vedono ancora "aperto"
                  "esaurito_motivo": f"archiviato automaticamente: scaduto da oltre {giorni} giorni",
                  "esaurito_il": datetime.now(timezone.utc).isoformat()}},
    )
    return {"ok": True, "archiviati": upd.modified_count, "soglia_data": limite}


@router.post("/elimina-senza-tracciabilita")
async def elimina_senza_tracciabilita(conferma: bool = Query(False)):
    """Elimina definitivamente i lotti storici senza dettaglio ingredienti (produzioni
    passate create prima che il collegamento ingredienti fosse tracciato — dato non
    ricostruibile a posteriori). STESSA query del cruscotto /controllo-dati/overview
    (issue 'lotti_senza_tracciabilita'), per cancellare esattamente e solo quelli
    segnalati. Richiesto da Enzo 01/07/2026. Senza conferma=true fa solo un'anteprima
    (nessuna cancellazione)."""
    def _vuoto(path):
        return {"$or": [
            {path: {"$exists": False}}, {path: None}, {path: ""}, {path: []},
        ]}
    query = {"$and": [
        {"$or": [
            {"stato": {"$exists": False}},
            # vocabolario reale dei lotti terminati (prima "consumato/chiuso/
            # archiviato", valori che nessuno scrive → il filtro non escludeva
            # nulla): ora esclude davvero i lotti già smaltiti/esauriti.
            {"stato": {"$nin": ["smaltito", "esaurito"]}},
        ]},
        _vuoto("ingredienti_dettaglio"),
        _vuoto("ingredienti"),
    ]}
    trovati = await db.lotti.find(
        query, {"_id": 0, "id": 1, "numero_lotto": 1, "prodotto": 1, "prodotto_nome": 1, "stato": 1}
    ).to_list(1000)
    if not conferma:
        return {"ok": True, "anteprima": True, "trovati": len(trovati), "lotti": trovati,
                "nota": "Nessuna cancellazione eseguita. Richiama con ?conferma=true per eliminare davvero."}
    result = await db.lotti.delete_many(query)
    return {"ok": True, "eliminati": result.deleted_count, "lotti": trovati}
