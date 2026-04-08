"""
Cedolini — Upload PDF buste paga, parse, salva, riconcilia.
Collection: cedolini
Prefix: /api/cedolini

Logica aggiornamento dipendente (import misto mesi/anni):
  1. Upsert cedolini su (codice_fiscale, mese, anno) — sempre
  2. paga_base / ultimo_netto / iban_cedolino → solo se cedolino è il più recente in assoluto
  3. Progressivi INPS/IRPEF/INAIL → struttura per anno, aggiorna col valore MAX (crescono nel tempo)
  4. TFR → struttura per anno, aggiorna solo se questo mese è il più recente per quell'anno
  5. Ferie/permessi saldo → solo se cedolino è il più recente in assoluto
"""
from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import datetime
from typing import Optional
import logging

from app.database import get_database
from app.parsers.cedolino_zucchetti import parse_cedolino_pdf

router = APIRouter()
logger = logging.getLogger(__name__)
COLL = "cedolini"


def _oid(doc):
    if doc and "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc


def _competenza(mese: int, anno: int) -> int:
    """Restituisce un intero comparabile: anno*100 + mese (es. 202409)."""
    return anno * 100 + mese


async def aggiorna_dipendente_da_cedolino(
    db: AsyncIOMotorDatabase,
    ced: dict,
) -> None:
    """
    Aggiorna la scheda dipendente in modo sicuro per import misto.
    Chiamare DOPO l'upsert del cedolino in collection 'cedolini'.
    """
    cf   = ced.get("codice_fiscale", "")
    mese = ced.get("mese", 0)
    anno = ced.get("anno", 0)
    if not cf or not mese or not anno:
        return

    comp_nuovo = _competenza(mese, anno)
    anno_str   = str(anno)

    # ── Trova il cedolino più recente già salvato per questo dipendente ──────
    piu_recente = await db[COLL].find_one(
        {"codice_fiscale": cf},
        sort=[("anno", -1), ("mese", -1)],
    )
    comp_esistente = (
        _competenza(piu_recente["mese"], piu_recente["anno"])
        if piu_recente else 0
    )
    is_piu_recente = comp_nuovo >= comp_esistente

    # ── Trova il cedolino più recente per l'ANNO corrente ────────────────────
    piu_recente_anno = await db[COLL].find_one(
        {"codice_fiscale": cf, "anno": anno},
        sort=[("mese", -1)],
    )
    comp_anno_esistente = (
        _competenza(piu_recente_anno["mese"], piu_recente_anno["anno"])
        if piu_recente_anno else 0
    )
    is_piu_recente_anno = comp_nuovo >= comp_anno_esistente

    # ── Costruisci $set e $max ───────────────────────────────────────────────
    set_fields: dict = {"updated_at": datetime.utcnow()}
    max_fields: dict = {}

    # 1) Campi "più recente in assoluto"
    if is_piu_recente:
        set_fields["ultimo_cedolino"] = f"{mese:02d}/{anno}"
        if ced.get("netto"):
            set_fields["ultimo_netto"] = ced["netto"]
        if ced.get("iban"):
            set_fields["iban_cedolino"] = ced["iban"]
        if ced.get("paga_base"):
            set_fields["paga_base"] = ced["paga_base"]
        if ced.get("livello"):
            set_fields["livello"] = ced["livello"]
        if ced.get("mansione"):
            set_fields["mansione"] = ced["mansione"]
        # Ferie e permessi (saldo cumulativo — valido solo sul più recente)
        if ced.get("ferie_saldo_gg") not in (None, 0.0):
            set_fields["ferie_saldo_gg"] = ced["ferie_saldo_gg"]
        if ced.get("permessi_saldo_ore") not in (None, 0.0):
            set_fields["permessi_saldo_ore"] = ced["permessi_saldo_ore"]

    # 2) Progressivi annuali — struttura: progressivi.<anno>.imp_inps ecc.
    #    Usiamo $max perché i progressivi crescono durante l'anno.
    #    Tra cedolini dello stesso anno, vince il valore più alto.
    prog_map = {
        "imp_inps_anno":   f"progressivi.{anno_str}.imp_inps",
        "imp_irpef_anno":  f"progressivi.{anno_str}.imp_irpef",
        "irpef_pagata_anno": f"progressivi.{anno_str}.irpef_pagata",
        "imp_inail_anno":  f"progressivi.{anno_str}.imp_inail",
    }
    for ced_key, mongo_key in prog_map.items():
        val = ced.get(ced_key)
        if val:
            max_fields[mongo_key] = val

    # 3) TFR per anno — aggiorna solo se è il mese più recente di quell'anno
    if is_piu_recente_anno:
        if ced.get("tfr_fondo_31_12"):
            set_fields[f"tfr.{anno_str}.fondo_31_12"] = ced["tfr_fondo_31_12"]
        if ced.get("tfr_quota_anno"):
            set_fields[f"tfr.{anno_str}.quota_anno"] = ced["tfr_quota_anno"]
        if ced.get("tfr_rivalutazione"):
            set_fields[f"tfr.{anno_str}.rivalutazione"] = ced["tfr_rivalutazione"]

    # ── Applica aggiornamento ────────────────────────────────────────────────
    update_op: dict = {}
    if set_fields:
        update_op["$set"] = set_fields
    if max_fields:
        update_op["$max"] = max_fields

    if not update_op:
        return

    await db["dipendenti"].update_one(
        {"codice_fiscale": cf},
        {
            **update_op,
            "$setOnInsert": {
                "nome":           ced.get("nome", ""),
                "cognome":        ced.get("cognome", ""),
                "codice_fiscale": cf,
                "stato":          "attivo",
                "created_at":     datetime.utcnow(),
            },
        },
        upsert=True,
    )

    logger.debug(
        "Dipendente %s aggiornato — più_recente=%s più_recente_anno=%s",
        cf, is_piu_recente, is_piu_recente_anno,
    )


@router.post("/upload-pdf")
async def upload_cedolini_pdf(
    file: UploadFile = File(...),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Upload PDF cedolini multi-dipendente, parsa e salva."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Solo PDF")

    content = await file.read()
    cedolini = parse_cedolino_pdf(pdf_bytes=content)

    if not cedolini:
        raise HTTPException(400, "Nessun cedolino trovato nel PDF")

    risultati = []
    for ced in cedolini:
        cf   = ced.get("codice_fiscale", "")
        mese = ced.get("mese")
        anno = ced.get("anno")

        if not cf or not mese or not anno:
            risultati.append({
                "stato": "incompleto",
                "codice_fiscale": cf,
                "mese": mese,
                "anno": anno,
            })
            continue

        ced["filename"]    = file.filename
        ced["imported_at"] = datetime.utcnow()
        ced["riconciliato"] = False

        # 1) Upsert cedolino — sempre
        result = await db[COLL].update_one(
            {"codice_fiscale": cf, "mese": mese, "anno": anno},
            {"$set": ced, "$setOnInsert": {"created_at": datetime.utcnow()}},
            upsert=True,
        )

        # 2) Aggiorna dipendente con logica competenza
        await aggiorna_dipendente_da_cedolino(db, ced)

        risultati.append({
            "stato":           "importato" if result.upserted_id else "aggiornato",
            "codice_fiscale":  cf,
            "dipendente":      f"{ced.get('cognome', '')} {ced.get('nome', '')}",
            "mese":            mese,
            "anno":            anno,
            "netto":           ced.get("netto"),
        })

    return {
        "ok":         True,
        "cedolini":   risultati,
        "n_importati": sum(1 for r in risultati if r["stato"] in ("importato", "aggiornato")),
    }


@router.get("")
async def lista_cedolini(
    anno: Optional[int] = None,
    mese: Optional[int] = None,
    skip: int = 0,
    limit: int = 50,
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    filtro = {}
    if anno:
        filtro["anno"] = anno
    if mese:
        filtro["mese"] = mese
    cursor = db[COLL].find(filtro).sort(
        [("anno", -1), ("mese", -1), ("cognome", 1)]
    ).skip(skip).limit(limit)
    items  = [_oid(doc) async for doc in cursor]
    totale = await db[COLL].count_documents(filtro)
    return {"items": items, "totale": totale}


@router.post("/riconcilia")
async def riconcilia_cedolini(db: AsyncIOMotorDatabase = Depends(get_database)):
    """Riconcilia cedolini con movimenti estratto conto."""
    non_ric = await db[COLL].find(
        {"riconciliato": False, "netto": {"$gt": 0}}
    ).to_list(500)

    riconciliati = 0
    for ced in non_ric:
        netto = ced["netto"]
        mov   = await db["estratto_conto_movimenti"].find_one({
            "categoria":    "stipendio",
            "riconciliato": False,
            "importo":      {"$gte": -(netto + 2), "$lte": -(netto - 2)},
        })
        if mov:
            await db[COLL].update_one(
                {"_id": ced["_id"]},
                {"$set": {"riconciliato": True, "movimento_id": str(mov["_id"])}},
            )
            await db["estratto_conto_movimenti"].update_one(
                {"_id": mov["_id"]},
                {"$set": {"riconciliato": True, "cedolino_cf": ced.get("codice_fiscale")}},
            )
            riconciliati += 1

    return {
        "ok":                     True,
        "riconciliati":           riconciliati,
        "totale_non_riconciliati": len(non_ric) - riconciliati,
    }
