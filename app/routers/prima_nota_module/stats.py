"""
Prima Nota Module - Statistiche e Export.
Statistiche aggregate, export Excel, anni disponibili, saldo iniziale manuale.
"""
from fastapi import HTTPException, Query, Body
from fastapi.responses import StreamingResponse
from typing import Dict, Any, Optional, Literal
from datetime import datetime, timezone
import io
import uuid

from app.database import Database
from app.services import conti_pos
from app.services.prima_nota_sumup_projection import (
    giorno_corrente_negozio,
    leggi_proiezioni_sumup_cassa,
)
from .common import (
    COLLECTION_PRIMA_NOTA_CASSA, COLLECTION_PRIMA_NOTA_BANCA,
    COLLECTION_SALDI_INIZIALI,
    CATEGORIE_ESCLUSE, aggrega_saldo_prima_nota, filtro_saldo_prima_nota,
    saldi_finanziari, get_saldo_iniziale_manuale, calcola_saldo_anni_precedenti,
)


async def get_saldi_finanziari(anno: Optional[int] = Query(None)) -> Dict[str, Any]:
    """Schede finanziarie separate, mai fuse in un unico numero.

    Un conto reale per ogni luogo dove il denaro sta davvero (Banca BPM,
    Mastercard SumUp) e un credito per ogni gestore che deve ancora versare.
    I crediti POS non concorrono alle disponibilita' liquide: sono incassi
    gia' avvenuti ma non ancora accreditati.
    """
    return await saldi_finanziari(Database.get_db(), anno)


async def get_saldi_iniziali(anno: int = Query(...)) -> Dict[str, Any]:
    """Saldi iniziali (riporto) inseriti a mano per l'anno: cassa e banca."""
    db = Database.get_db()
    docs = await db[COLLECTION_SALDI_INIZIALI].find(
        {"anno": int(anno)}, {"_id": 0}
    ).to_list(10)
    per_tipo = {d["tipo"]: d for d in docs}
    return {
        "anno": anno,
        "cassa": per_tipo.get("cassa"),
        "banca": per_tipo.get("banca"),
    }


async def set_saldo_iniziale(data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Imposta (upsert) il saldo iniziale manuale di cassa o banca per un anno.

    Richiesta utente 16/07/2026: il riporto dell'anno (es. saldo al 2 gennaio
    2026, che viene dal 2025) deve essere modificabile a mano. Quando è
    impostato, sostituisce il riporto calcolato dai movimenti degli anni
    precedenti in TUTTI i punti che usano la funzione unica di saldo
    (pagina Prima Nota, bilancio, finanziaria, stats).
    """
    tipo = data.get("tipo")
    anno = data.get("anno")
    importo = data.get("importo")
    if tipo not in ("cassa", "banca"):
        raise HTTPException(status_code=400, detail="tipo deve essere 'cassa' o 'banca'")
    if not anno:
        raise HTTPException(status_code=400, detail="anno obbligatorio")
    try:
        importo = float(importo)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="importo non valido")

    db = Database.get_db()
    now = datetime.now(timezone.utc).isoformat()
    esistente = await db[COLLECTION_SALDI_INIZIALI].find_one({"tipo": tipo, "anno": int(anno)})
    if esistente:
        await db[COLLECTION_SALDI_INIZIALI].update_one(
            {"id": esistente["id"]},
            {"$set": {"importo": importo, "note": data.get("note"), "updated_at": now}},
        )
        saldo_id = esistente["id"]
    else:
        saldo_id = str(uuid.uuid4())
        await db[COLLECTION_SALDI_INIZIALI].insert_one({
            "id": saldo_id,
            "tipo": tipo,
            "anno": int(anno),
            "importo": importo,
            "note": data.get("note"),
            "created_at": now,
            "updated_at": now,
        })
    return {"id": saldo_id, "tipo": tipo, "anno": int(anno), "importo": importo}


async def delete_saldo_iniziale(tipo: str, anno: int) -> Dict[str, Any]:
    """Rimuove il saldo iniziale manuale: si torna al riporto calcolato."""
    if tipo not in ("cassa", "banca"):
        raise HTTPException(status_code=400, detail="tipo deve essere 'cassa' o 'banca'")
    db = Database.get_db()
    esito = await db[COLLECTION_SALDI_INIZIALI].delete_one({"tipo": tipo, "anno": int(anno)})
    if esito.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Saldo iniziale non trovato")
    return {"eliminato": True, "tipo": tipo, "anno": anno}


async def get_anni_disponibili() -> Dict[str, Any]:
    """Restituisce gli anni per cui esistono movimenti in prima nota."""
    db = Database.get_db()
    
    anni = set()
    current_year = datetime.now().year
    anni.add(current_year)
    
    pipeline = [
        {"$project": {"anno": {"$substr": ["$data", 0, 4]}}},
        {"$group": {"_id": "$anno"}}
    ]
    
    cassa_anni = await db[COLLECTION_PRIMA_NOTA_CASSA].aggregate(pipeline).to_list(100)
    for doc in cassa_anni:
        try:
            anni.add(int(doc["_id"]))
        except (ValueError, TypeError):
            pass
    
    banca_anni = await db[COLLECTION_PRIMA_NOTA_BANCA].aggregate(pipeline).to_list(100)
    for doc in banca_anni:
        try:
            anni.add(int(doc["_id"]))
        except (ValueError, TypeError):
            pass
    
    return {"anni": sorted(list(anni), reverse=True)}


async def get_prima_nota_stats(
    data_da: Optional[str] = Query(None),
    data_a: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """Statistiche aggregate prima nota cassa e banca."""
    db = Database.get_db()
    
    # Stesse esclusioni di tutte le altre query di riepilogo (§6.4): prima
    # qui i movimenti eliminati (soft-delete) e i duplicati POS venivano
    # ancora sommati, e le stats non tornavano con la Prima Nota.
    cassa_match = filtro_saldo_prima_nota(COLLECTION_PRIMA_NOTA_CASSA)
    banca_match = filtro_saldo_prima_nota(COLLECTION_PRIMA_NOTA_BANCA)
    banca_match["$or"] = [
        {"conto_contabile": conti_pos.CONTO_BPM},
        {"conto_contabile": {"$in": [None, ""]}},
        {"conto_contabile": {"$exists": False}},
    ]
    sumup_match = filtro_saldo_prima_nota(
        COLLECTION_PRIMA_NOTA_BANCA,
        conto_contabile=conti_pos.CONTO_SUMUP_MASTERCARD,
    )
    if data_da:
        cassa_match["data"] = {"$gte": data_da}
        banca_match["data"] = {"$gte": data_da}
        sumup_match["data"] = {"$gte": data_da}
    if data_a:
        cassa_match.setdefault("data", {})["$lte"] = data_a
        banca_match.setdefault("data", {})["$lte"] = data_a
        sumup_match.setdefault("data", {})["$lte"] = data_a

    cassa_pipeline = [
        {"$match": cassa_match},
        {"$group": {
            "_id": None,
            "entrate": {"$sum": {"$cond": [{"$eq": ["$tipo", "entrata"]}, "$importo", 0]}},
            "uscite": {"$sum": {"$cond": [{"$eq": ["$tipo", "uscita"]}, "$importo", 0]}},
            "count": {"$sum": 1}
        }}
    ]
    cassa_stats = await db[COLLECTION_PRIMA_NOTA_CASSA].aggregate(cassa_pipeline).to_list(1)
    
    banca_pipeline = [
        {"$match": banca_match},
        {"$group": {
            "_id": None,
            "entrate": {"$sum": {"$cond": [{"$eq": ["$tipo", "entrata"]}, "$importo", 0]}},
            "uscite": {"$sum": {"$cond": [{"$eq": ["$tipo", "uscita"]}, "$importo", 0]}},
            "count": {"$sum": 1}
        }}
    ]
    banca_stats = await db[COLLECTION_PRIMA_NOTA_BANCA].aggregate(banca_pipeline).to_list(1)

    sumup_pipeline = [
        {"$match": sumup_match},
        {"$group": {
            "_id": None,
            "entrate": {"$sum": {"$cond": [{"$eq": ["$tipo", "entrata"]}, "$importo", 0]}},
            "uscite": {"$sum": {"$cond": [{"$eq": ["$tipo", "uscita"]}, "$importo", 0]}},
            "count": {"$sum": 1},
        }},
    ]
    sumup_stats = await db[COLLECTION_PRIMA_NOTA_BANCA].aggregate(sumup_pipeline).to_list(1)
    
    cassa = cassa_stats[0] if cassa_stats else {"entrate": 0, "uscite": 0, "count": 0}
    banca = banca_stats[0] if banca_stats else {"entrate": 0, "uscite": 0, "count": 0}
    sumup = sumup_stats[0] if sumup_stats else {"entrate": 0, "uscite": 0, "count": 0}

    # Per l'intero esercizio la Dashboard deve mostrare lo stesso saldo della
    # Prima Nota, incluso il riporto al 01/01. Per un intervallo parziale
    # mostra invece soltanto i movimenti del periodo.
    riporto_cassa = 0.0
    riporto_banca = 0.0
    anno_intero = None
    if (
        data_da and data_a
        and data_da.endswith("-01-01")
        and data_a.endswith("-12-31")
        and data_da[:4] == data_a[:4]
    ):
        anno_intero = int(data_da[:4])
        cassa_manuale = await get_saldo_iniziale_manuale(
            db, COLLECTION_PRIMA_NOTA_CASSA, anno_intero,
        )
        banca_manuale = await get_saldo_iniziale_manuale(
            db, COLLECTION_PRIMA_NOTA_BANCA, anno_intero,
        )
        riporto_cassa = float(cassa_manuale or 0)
        riporto_banca = float(banca_manuale or 0)
        if cassa_manuale is None:
            riporto_cassa = float(await calcola_saldo_anni_precedenti(
                db, COLLECTION_PRIMA_NOTA_CASSA, anno_intero,
            ))
        if banca_manuale is None:
            riporto_banca = float(await calcola_saldo_anni_precedenti(
                db, COLLECTION_PRIMA_NOTA_BANCA, anno_intero,
            ))

    oggi = giorno_corrente_negozio()
    proiezione_sumup = {
        "data": oggi,
        "stato": "fuori_filtro",
        "applicabile": False,
        "delta": 0.0,
    }
    dal = data_da or "0001-01-01"
    al = data_a or oggi
    proiezioni_sumup = await leggi_proiezioni_sumup_cassa(db, dal, al)
    if proiezioni_sumup:
        for proiezione in proiezioni_sumup:
            if not proiezione.get("applicabile"):
                continue
            delta = round(float(proiezione.get("delta") or 0), 2)
            cassa["uscite"] = round(float(cassa.get("uscite") or 0) + delta, 2)
            if proiezione.get("numero_righe_persistite") == 0:
                cassa["count"] = int(cassa.get("count") or 0) + 1
        proiezione_sumup = {
            "stato": "periodo_sumup_archiviato",
            "applicabile": True,
            "giornate": proiezioni_sumup,
            "delta": round(sum(float(p.get("delta") or 0) for p in proiezioni_sumup if p.get("applicabile")), 2),
        }

    # La Dashboard espone il saldo dei movimenti dell'intervallo richiesto.
    # Non trascina automaticamente anni storici incompleti: un saldo di conto
    # richiede un riporto certificato e resta consultabile in Prima Nota.
    saldo_cassa = riporto_cassa + cassa.get("entrate", 0) - cassa.get("uscite", 0)
    saldo_banca = riporto_banca + banca.get("entrate", 0) - banca.get("uscite", 0)
    saldo_sumup = sumup.get("entrate", 0) - sumup.get("uscite", 0)
    return {
        "cassa": {
            "saldo": round(saldo_cassa, 2),
            "riporto": round(riporto_cassa, 2),
            "entrate": cassa.get("entrate", 0),
            "uscite": cassa.get("uscite", 0),
            "movimenti": cassa.get("count", 0)
        },
        "banca": {
            "saldo": round(saldo_banca, 2),
            "riporto": round(riporto_banca, 2),
            "entrate": banca.get("entrate", 0),
            "uscite": banca.get("uscite", 0),
            "movimenti": banca.get("count", 0)
        },
        "sumup": {
            "saldo": round(saldo_sumup, 2),
            "riporto": 0.0,
            "entrate": sumup.get("entrate", 0),
            "uscite": sumup.get("uscite", 0),
            "movimenti": sumup.get("count", 0)
        },
        "totale": {
            "saldo": round(saldo_cassa + saldo_banca + saldo_sumup, 2),
            "entrate": cassa.get("entrate", 0) + banca.get("entrate", 0) + sumup.get("entrate", 0),
            "uscite": cassa.get("uscite", 0) + banca.get("uscite", 0) + sumup.get("uscite", 0)
        },
        "criterio": "saldo_esercizio_con_riporto" if (riporto_cassa or riporto_banca) else "movimenti_del_periodo_senza_riporti_storici",
        "saldo_conto_certificato": bool(riporto_cassa or riporto_banca),
        "sumup_cassa_live": proiezione_sumup,
    }


async def get_saldo_finale(
    anno: int = Query(..., description="Anno per cui calcolare il saldo finale"),
    tipo: str = Query("cassa", description="Tipo: cassa o banca")
) -> Dict[str, Any]:
    """Calcola il saldo finale dell'anno specificato."""
    db = Database.get_db()
    
    collection = COLLECTION_PRIMA_NOTA_CASSA if tipo == "cassa" else COLLECTION_PRIMA_NOTA_BANCA

    # §6.4: stessa funzione/engine di cassa.py e banca.py (filtri, esclusioni e segno
    # uniformi: niente deleted/archived né categorie escluse; niente to_list illimitato).
    query = filtro_saldo_prima_nota(
        collection,
        data={"$gte": f"{anno}-01-01", "$lte": f"{anno}-12-31"},
    )
    # anno passato ad aggrega: il saldo FINALE include il riporto iniziale
    # (manuale o cumulato) — prima veniva ignorato (anno=None).
    saldi = await aggrega_saldo_prima_nota(db, collection, query, anno=anno)
    movimenti_count = await db[collection].count_documents(query)

    return {
        "anno": anno,
        "tipo": tipo,
        "saldo": saldi["saldo"],
        "movimenti_count": movimenti_count
    }


async def export_prima_nota_excel(
    tipo: Literal["cassa", "banca", "entrambi"] = Query("entrambi"),
    data_da: Optional[str] = Query(None),
    data_a: Optional[str] = Query(None)
) -> StreamingResponse:
    """Export Prima Nota in Excel."""
    try:
        import pandas as pd
    except ImportError:
        raise HTTPException(status_code=500, detail="pandas non installato")
    
    db = Database.get_db()
    query = {}
    if data_da:
        query["data"] = {"$gte": data_da}
    if data_a:
        query.setdefault("data", {})["$lte"] = data_a
    
    output = io.BytesIO()
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        if tipo in ["cassa", "entrambi"]:
            cassa = await db[COLLECTION_PRIMA_NOTA_CASSA].find(query, {"_id": 0}).sort("data", -1).to_list(10000)
            if cassa:
                df_cassa = pd.DataFrame(cassa)
                cols = ["data", "tipo", "importo", "descrizione", "categoria", "riferimento"]
                df_cassa = df_cassa[[c for c in cols if c in df_cassa.columns]]
                df_cassa.to_excel(writer, sheet_name="Prima Nota Cassa", index=False)
        
        if tipo in ["banca", "entrambi"]:
            banca = await db[COLLECTION_PRIMA_NOTA_BANCA].find(query, {"_id": 0}).sort("data", -1).to_list(10000)
            if banca:
                df_banca = pd.DataFrame(banca)
                cols = ["data", "tipo", "importo", "descrizione", "categoria", "riferimento", "assegno_collegato"]
                df_banca = df_banca[[c for c in cols if c in df_banca.columns]]
                df_banca.to_excel(writer, sheet_name="Prima Nota Banca", index=False)

        # openpyxl requires at least one sheet; without any movements for the
        # period no sheet would be written and the writer crashes on save.
        if not writer.sheets:
            pd.DataFrame(columns=["data", "tipo", "importo", "descrizione"]).to_excel(
                writer, sheet_name="Prima Nota", index=False
            )

    output.seek(0)
    filename = f"prima_nota_{datetime.now().strftime('%Y%m%d')}.xlsx"
    
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
