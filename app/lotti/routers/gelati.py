"""
Router Gelateria: gestione gelati invenduti (da riutilizzare) e memoria delle
produzioni di gelato. Collezioni MongoDB condivise (DB Gestionale):
  - gelati_invenduti
  - gelati_produzioni
Il calcolo ricette è lato frontend (ricette base Ceraldi/Galatea); qui si
persistono invenduti e produzioni.
"""
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.lotti.db import database as db
from app.lotti.servizi.lotti_service import crea_lotto

router = APIRouter(prefix="/gelati", tags=["gelati"])

CATEGORIE = {"crema", "frutta", "cioccolato"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class InvendutoIn(BaseModel):
    gusto: str
    categoria: str = "crema"  # crema | frutta | cioccolato
    quantita_g: float
    data: Optional[str] = None  # YYYY-MM-DD (data del calo dal banco)
    # esito del prodotto rientrato in laboratorio:
    #   "rientrato"     = appena tornato dal banco, ancora da decidere
    #   "riutilizzato"  = recuperato nel rinfuso di un gelato nuovo
    #   "dismesso"      = buttato perché non più vendibile
    esito: Optional[str] = "rientrato"


ESITI = {"rientrato", "riutilizzato", "dismesso"}


class RecuperoRef(BaseModel):
    gusto: str
    quantita_g: float


class ProduzioneIn(BaseModel):
    ricetta: str
    peso_g: float  # peso TOTALE finito (nuovo prodotto + eventuale recuperato)
    modalita: Optional[str] = None  # "totale" | "completamento"
    data: Optional[str] = None
    note: Optional[str] = None
    recuperi: Optional[List[RecuperoRef]] = None  # gelato rientrato incorporato nel rinfuso



# ── Gusti per il menu a tendina degli invenduti ────────────────────────────────
# Il pasticcere ha le mani sporche: si sceglie con un tocco, non si scrive.
# Seed = gusti che l'app conosce già (basi di produzione + frutta del calcolo
# ricette + cioccolato). I gusti nuovi digitati una volta entrano per sempre
# nella tendina perché GET /gusti unisce il seed allo storico degli invenduti.
GUSTI_SEED = [
    # da basi/produzioni
    ("Fiordilatte", "crema"), ("Crema", "crema"), ("Ricotta", "crema"),
    ("Nocciola", "crema"), ("Pistacchio", "crema"), ("Superbiscotto", "crema"),
    ("Cioccolato", "cioccolato"), ("Fondente", "cioccolato"), ("Gianduia", "cioccolato"),
    # frutta (stessa lista del calcolo acqua-frutta)
    ("Anguria", "frutta"), ("Fragola", "frutta"), ("Melone", "frutta"),
    ("Pesca", "frutta"), ("Arancia", "frutta"), ("Albicocca", "frutta"),
    ("Lampone", "frutta"), ("Frutti di bosco", "frutta"), ("Ananas", "frutta"),
    ("Mandarino", "frutta"), ("Pera", "frutta"), ("Mela verde", "frutta"),
    ("Kiwi", "frutta"), ("Limone", "frutta"), ("Banana", "frutta"),
]


@router.get("/gusti")
async def lista_gusti():
    """Gusti per la tendina invenduti: seed dell'app + tutti i gusti già
    registrati negli invenduti (un gusto scritto una volta resta per sempre)."""
    visti = {}
    for nome, cat in GUSTI_SEED:
        visti[nome.lower()] = {"nome": nome, "categoria": cat}
    docs = await db.gelati_invenduti.find({}, {"_id": 0, "gusto": 1, "categoria": 1}).to_list(2000)
    for d in docs:
        nome = (d.get("gusto") or "").strip()
        if nome and nome.lower() not in visti:
            visti[nome.lower()] = {"nome": nome, "categoria": d.get("categoria") or "crema"}
    gusti = sorted(visti.values(), key=lambda x: x["nome"].lower())
    return {"gusti": gusti, "totale": len(gusti)}


# ── Gelati invenduti ──────────────────────────────────────────────────────
@router.get("/invenduti")
async def lista_invenduti():
    docs = (
        await db.gelati_invenduti.find({}, {"_id": 0}).sort("data", -1).to_list(1000)
    )
    return {"invenduti": docs, "totale": len(docs)}


@router.post("/invenduti")
async def aggiungi_invenduto(body: InvendutoIn):
    if not body.gusto.strip() or body.quantita_g <= 0:
        raise HTTPException(status_code=400, detail="Gusto e quantità obbligatori")
    cat = (body.categoria or "crema").lower()
    if cat not in CATEGORIE:
        cat = "crema"
    esito = (body.esito or "rientrato").lower()
    if esito not in ESITI:
        esito = "rientrato"
    doc = {
        "id": str(uuid.uuid4()),
        "gusto": body.gusto.strip(),
        "categoria": cat,
        "quantita_g": float(body.quantita_g),
        "riutilizzato_g": 0.0,  # quanto di questo rientro è già finito nel rinfuso
        "esito": esito,
        "data": body.data or _now()[:10],
        "created_at": _now(),
    }
    await db.gelati_invenduti.insert_one(doc)
    doc.pop("_id", None)
    return {"success": True, "invenduto": doc}


@router.post("/invenduti/{inv_id}/esito")
async def set_esito_invenduto(inv_id: str, esito: str = Query(...)):
    """Aggiorna l'esito di un gelato rientrato in laboratorio:
    riutilizzato (tutto recuperato nel rinfuso) o dismesso (non vendibile)."""
    esito = (esito or "").lower()
    if esito not in ESITI:
        raise HTTPException(status_code=400, detail="esito non valido (rientrato | riutilizzato | dismesso)")
    doc = await db.gelati_invenduti.find_one({"id": inv_id}, {"_id": 0, "quantita_g": 1})
    if not doc:
        raise HTTPException(status_code=404, detail="Invenduto non trovato")
    qg = float(doc.get("quantita_g") or 0)
    set_doc = {"esito": esito, "esito_data": _now()[:10]}
    if esito == "riutilizzato":
        set_doc["riutilizzato_g"] = qg  # tutto recuperato
    elif esito == "rientrato":
        set_doc["riutilizzato_g"] = 0.0  # torna disponibile
    await db.gelati_invenduti.update_one({"id": inv_id}, {"$set": set_doc})
    return {"success": True, "esito": esito}


@router.get("/invenduti-disponibili")
async def invenduti_disponibili():
    """Gusti realmente disponibili in laboratorio da recuperare nel rinfuso:
    per ogni gusto, i grammi residui (rientrato − già riutilizzato), esclusi i dismessi."""
    docs = await db.gelati_invenduti.find({}, {"_id": 0}).to_list(5000)
    per_gusto: dict = {}
    for d in docs:
        if (d.get("esito") or "rientrato") == "dismesso":
            continue
        residua = float(d.get("quantita_g") or 0) - float(d.get("riutilizzato_g") or 0)
        if residua <= 0:
            continue
        g = (d.get("gusto") or "—").strip()
        row = per_gusto.setdefault(g, {"gusto": g, "categoria": d.get("categoria") or "crema", "disponibile_g": 0.0})
        row["disponibile_g"] += residua
    righe = sorted((r for r in per_gusto.values() if r["disponibile_g"] > 0), key=lambda x: x["gusto"].lower())
    return {"disponibili": righe, "totale_g": round(sum(r["disponibile_g"] for r in righe), 1)}


async def _consuma_invenduto(gusto: str, da_recuperare: float, produzione_ref: Optional[str] = None) -> dict:
    """Consuma N g di un gusto dagli invenduti FIFO per data (scala il residuo,
    segna riutilizzato a saturazione). Ritorna consumato + fonti (per la tracciabilità
    del lotto: da quali rientri arriva il gelato recuperato)."""
    gusto = (gusto or "").strip()
    da_recuperare = float(da_recuperare or 0)
    if not gusto or da_recuperare <= 0:
        return {"consumato": 0.0, "fonti": []}
    candidati = await db.gelati_invenduti.find(
        {"gusto": gusto, "esito": {"$ne": "dismesso"}}, {"_id": 0}
    ).sort("data", 1).to_list(2000)
    consumato = 0.0
    fonti = []
    for d in candidati:
        if consumato >= da_recuperare:
            break
        residua = float(d.get("quantita_g") or 0) - float(d.get("riutilizzato_g") or 0)
        if residua <= 0:
            continue
        prendi = min(residua, da_recuperare - consumato)
        nuovo_riut = float(d.get("riutilizzato_g") or 0) + prendi
        set_doc = {"riutilizzato_g": nuovo_riut}
        if nuovo_riut >= float(d.get("quantita_g") or 0) - 0.001:
            set_doc["esito"] = "riutilizzato"
            set_doc["esito_data"] = _now()[:10]
        if produzione_ref:
            set_doc["riutilizzato_in"] = produzione_ref
        await db.gelati_invenduti.update_one({"id": d["id"]}, {"$set": set_doc})
        consumato += prendi
        fonti.append({"invenduto_id": d["id"], "data": d.get("data"), "quantita_g": round(prendi, 1)})
    return {"consumato": round(consumato, 1), "fonti": fonti}


class RecuperoIn(BaseModel):
    gusto: str
    quantita_g: float
    produzione_ref: Optional[str] = None  # nome ricetta/lotto in cui è stato recuperato


@router.post("/recupera")
async def recupera_invenduto(body: RecuperoIn):
    """Recupera N grammi di un gusto dagli invenduti (FIFO). Es: 700 g di cioccolato
    presi dai 1000 in giacenza → restano 300."""
    res = await _consuma_invenduto(body.gusto, body.quantita_g, body.produzione_ref)
    richiesto = round(float(body.quantita_g or 0), 1)
    return {
        "success": True,
        "gusto": (body.gusto or "").strip(),
        "richiesto_g": richiesto,
        "consumato_g": res["consumato"],
        "non_coperto_g": round(max(0.0, richiesto - res["consumato"]), 1),
        "fonti": res["fonti"],
    }


@router.get("/report")
async def report_invenduti(
    periodo: str = "mese",  # settimana | mese | anno
    da: Optional[str] = None,
    a: Optional[str] = None,
):
    """Riepilogo invenduti per gusto su un periodo: quanto è rientrato (invenduto),
    quanto è stato riutilizzato nel rinfuso e quanto dismesso. Interrogabile per
    settimana/mese/anno o con intervallo esplicito da/a (YYYY-MM-DD)."""
    oggi = datetime.now(timezone.utc).date()
    if da and a:
        d_da, d_a = da, a
    else:
        if periodo == "settimana":
            start = oggi - timedelta(days=oggi.weekday())  # lunedì
        elif periodo == "anno":
            start = oggi.replace(month=1, day=1)
        else:
            periodo = "mese"
            start = oggi.replace(day=1)
        d_da, d_a = start.isoformat(), oggi.isoformat()

    docs = await db.gelati_invenduti.find(
        {"data": {"$gte": d_da, "$lte": d_a}}, {"_id": 0}
    ).to_list(5000)

    per_gusto: dict = {}
    for d in docs:
        g = (d.get("gusto") or "—").strip()
        esito = (d.get("esito") or "rientrato").lower()
        qg = float(d.get("quantita_g") or 0)
        riut = float(d.get("riutilizzato_g") or 0)
        row = per_gusto.setdefault(g, {
            "gusto": g, "categoria": d.get("categoria") or "crema",
            "invenduto_g": 0.0, "riutilizzato_g": 0.0, "dismesso_g": 0.0,
            "in_attesa_g": 0.0, "n": 0,
        })
        row["invenduto_g"] += qg  # tutto ciò che è rientrato dal banco
        row["riutilizzato_g"] += riut  # grammi davvero finiti nel rinfuso (anche parziali)
        row["n"] += 1
        if esito == "dismesso":
            row["dismesso_g"] += (qg - riut)  # il residuo non recuperato è stato buttato
        else:
            row["in_attesa_g"] += (qg - riut)  # residuo ancora recuperabile

    righe = sorted(per_gusto.values(), key=lambda x: x["gusto"].lower())
    totali = {
        k: round(sum(r[k] for r in righe), 1)
        for k in ("invenduto_g", "riutilizzato_g", "dismesso_g", "in_attesa_g")
    }
    return {"periodo": periodo, "da": d_da, "a": d_a, "righe": righe, "totali": totali, "n_gusti": len(righe)}


@router.delete("/invenduti/{inv_id}")
async def elimina_invenduto(inv_id: str):
    res = await db.gelati_invenduti.delete_one({"id": inv_id})
    return {"success": res.deleted_count > 0}


# ── Produzioni gelato (memoria di ciò che è stato prodotto/aggiunto) ────────
@router.get("/produzioni")
async def lista_produzioni():
    docs = (
        await db.gelati_produzioni.find({}, {"_id": 0}).sort("data", -1).to_list(1000)
    )
    peso_tot = sum(d.get("peso_g", 0) for d in docs)
    return {"produzioni": docs, "totale": len(docs), "peso_totale_g": peso_tot}


@router.post("/produzioni")
async def aggiungi_produzione(body: ProduzioneIn):
    if not body.ricetta.strip() or body.peso_g <= 0:
        raise HTTPException(status_code=400, detail="Ricetta e peso obbligatori")
    ricetta_nome = body.ricetta.strip()
    peso_totale = float(body.peso_g)  # gelato finito = nuovo prodotto + recuperato

    # ── Recupero: consuma il gelato rientrato dagli invenduti (FIFO) ──
    recuperi_dett = []
    recuperato_tot = 0.0
    for rc in (body.recuperi or []):
        res = await _consuma_invenduto(rc.gusto, rc.quantita_g, produzione_ref=ricetta_nome)
        if res["consumato"] > 0:
            recuperi_dett.append({"gusto": (rc.gusto or "").strip(), "quantita_g": res["consumato"], "fonti": res["fonti"]})
            recuperato_tot += res["consumato"]
    peso_nuovo = round(max(0.0, peso_totale - recuperato_tot), 1)

    note_finali = (body.note or "")
    if recuperato_tot > 0:
        parti = ", ".join(f"{int(round(r['quantita_g']))} g {r['gusto']}" for r in recuperi_dett)
        note_finali = (note_finali + f" Composizione: {int(round(peso_nuovo))} g nuovi + {int(round(recuperato_tot))} g recuperati ({parti}).").strip()

    doc = {
        "id": str(uuid.uuid4()),
        "ricetta": ricetta_nome,
        "peso_g": peso_totale,
        "peso_nuovo_g": peso_nuovo,
        "peso_recuperato_g": round(recuperato_tot, 1),
        "recuperi": recuperi_dett,
        "modalita": body.modalita or "totale",
        "note": note_finali,
        "data": body.data or _now()[:10],
        "created_at": _now(),
    }
    # ── Sistema lotti UNICO: ogni produzione gelato è un lotto tracciabile ──
    from app.lotti.routers.utils import _calcola_scadenza
    lotto_id = str(uuid.uuid4())
    numero_lotto = f"GEL-{doc['data'].replace('-', '')}-{doc['id'][:4].upper()}"
    try:
        scad = _calcola_scadenza([ricetta_nome, "latte"], doc["data"],
                                 metodo_conservazione="abbattitore_negativo")
        data_scadenza = scad[1] or scad[0]
    except Exception:
        data_scadenza = None
    # Tracciabilità: il lotto del gelato finito registra il componente RECUPERATO
    # (col rientro d'origine) accanto alla produzione NUOVA.
    lotti_scalati = []
    for r in recuperi_dett:
        date_fonti = sorted({f.get("data") for f in r["fonti"] if f.get("data")})
        lotti_scalati.append({
            "ingrediente": f"Gelato {r['gusto']} recuperato",
            "fornitore": "Recupero interno (rientro dal banco)",
            "quantita_g": r["quantita_g"],
            "lotto_id": "",
            "fattura_ref": f"rientro {', '.join(date_fonti)}" if date_fonti else "rientro",
            "data_fattura": date_fonti[0] if date_fonti else None,
        })
    lotto = {
        "id": lotto_id,
        "numero_lotto": numero_lotto,
        "prodotto": f"Gelato {ricetta_nome}",
        "tipo": "gelato",
        "source": "gelati",
        "ricetta": ricetta_nome,
        "quantita_g": peso_totale,
        "peso_nuovo_g": peso_nuovo,
        "peso_recuperato_g": round(recuperato_tot, 1),
        "data_produzione": doc["data"],
        "data_scadenza": data_scadenza,
        "esaurito": False,
        "note": note_finali,
        "created_at": doc["created_at"],
    }
    if lotti_scalati:
        lotto["lotti_fornitori"] = {"lotti_scalati": lotti_scalati}
        lotto["composizione_recupero"] = recuperi_dett
    await crea_lotto(lotto, origine="gelato")
    doc["lotto_id"] = lotto_id
    doc["numero_lotto"] = numero_lotto
    await db.gelati_produzioni.insert_one(doc)
    doc.pop("_id", None)
    return {
        "success": True, "produzione": doc, "numero_lotto": numero_lotto,
        "peso_nuovo_g": peso_nuovo, "peso_recuperato_g": round(recuperato_tot, 1),
    }


@router.delete("/produzioni/{prod_id}")
async def elimina_produzione(prod_id: str):
    prod = await db.gelati_produzioni.find_one({"id": prod_id}, {"_id": 0})
    res = await db.gelati_produzioni.delete_one({"id": prod_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Produzione non trovata")
    if prod and prod.get("lotto_id"):
        # campo GEMELLO stato: senza, i filtri che guardano solo "stato" (es.
        # cosa-usare-oggi, dashboard) vedevano ancora il lotto gelato come
        # "aperto" anche dopo l'eliminazione. Azzero anche le quantità.
        await db.lotti.update_one(
            {"id": prod["lotto_id"]},
            {"$set": {"esaurito": True, "stato": "esaurito",
                      "esaurito_motivo": "produzione gelato eliminata",
                      "quantita": 0, "quantita_g": 0}},
        )
    return {"success": True}