"""
Helper centralizzati per l'ingestion dei Corrispettivi.

FUNZIONI CHIAVE:
- ingest_corrispettivo_parsed: punto unico di insert/update dei corrispettivi con
  1) anti-duplicato rigoroso (corrispettivo_key OR data+totale tolleranza 0.01€
     OR matricola_rt+data)
  2) propagazione automatica a prima_nota_cassa (contanti) e prima_nota_banca (POS)
  3) pulizia dei vecchi movimenti Prima Nota legati al record prima di rigenerare

- rebuild_prima_nota_from_corrispettivi: rigenera da zero tutti i movimenti Prima Nota
  partendo dai corrispettivi esistenti (utile per riparare dati storici).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional
import logging
import uuid

logger = logging.getLogger(__name__)


def _to_float(v: Any) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _build_corrispettivo_doc(parsed: Dict[str, Any], filename: str, source: str) -> Dict[str, Any]:
    data = parsed.get("data", "") or ""
    anno = int(data[:4]) if data and len(data) >= 4 and data[:4].isdigit() else datetime.now().year
    mese = int(data[5:7]) if data and len(data) >= 7 and data[5:7].isdigit() else datetime.now().month
    return {
        "corrispettivo_key": parsed.get("corrispettivo_key", ""),
        "data": data,
        "matricola_rt": parsed.get("matricola_rt", ""),
        "numero_documento": parsed.get("numero_documento", ""),
        "partita_iva": parsed.get("partita_iva", ""),
        "totale": _to_float(parsed.get("totale", 0)),
        "pagato_contanti": _to_float(parsed.get("pagato_contanti", 0)),
        "pagato_elettronico": _to_float(parsed.get("pagato_elettronico", 0)),
        "totale_imponibile": _to_float(parsed.get("totale_imponibile", 0)),
        "totale_iva": _to_float(parsed.get("totale_iva", 0)),
        "pagato_non_riscosso": _to_float(parsed.get("pagato_non_riscosso", 0)),
        "totale_ammontare_annulli": _to_float(parsed.get("totale_ammontare_annulli", 0)),
        "numero_documenti": int(_to_float(parsed.get("numero_documenti", 0))),
        "riepilogo_iva": parsed.get("riepilogo_iva", []) or [],
        "status": "imported",
        "source": source,
        "filename": filename,
        "anno": anno,
        "mese": mese,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


async def _find_existing_corrispettivo(db, corr_doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Anti-duplicato a più livelli.
    Esclude soft-deleted / archiviati.
    """
    not_deleted = {"entity_status": {"$ne": "deleted"}, "status": {"$nin": ["deleted", "archived"]}}

    key = (corr_doc.get("corrispettivo_key") or "").strip()
    data = corr_doc.get("data", "")
    matricola = (corr_doc.get("matricola_rt") or "").strip()
    totale = _to_float(corr_doc.get("totale", 0))

    # Livello 1: chiave naturale XML
    if key:
        existing = await db["corrispettivi"].find_one({"corrispettivo_key": key, **not_deleted})
        if existing:
            return existing

    # Livello 2: stessa data + stessa matricola (stesso registratore)
    if data and matricola:
        existing = await db["corrispettivi"].find_one({
            "data": data,
            "matricola_rt": matricola,
            **not_deleted,
        })
        if existing:
            return existing

    # Livello 3: stessa data + totale ±0.01 (stesso incasso giornaliero da provvisorio/manuale)
    if data and totale > 0:
        existing = await db["corrispettivi"].find_one({
            "data": data,
            "totale": {"$gte": totale - 0.01, "$lte": totale + 0.01},
            **not_deleted,
        })
        if existing:
            return existing

    return None


async def _delete_prima_nota_for_corrispettivo(db, corrispettivo_id: str, data: str) -> None:
    """Elimina i movimenti Prima Nota precedenti legati a questo corrispettivo,
    per evitare duplicati quando si rigenera la propagazione."""
    # Per id esatto
    if corrispettivo_id:
        await db["prima_nota_cassa"].delete_many({"corrispettivo_id": corrispettivo_id})
        await db["prima_nota_banca"].delete_many({"corrispettivo_id": corrispettivo_id})

    # Per source+data (corrispettivi storici senza corrispettivo_id)
    if data:
        await db["prima_nota_cassa"].delete_many({
            "data": data,
            "$or": [
                {"source": {"$in": [
                    "corrispettivo_import", "corrispettivo_pos",
                    "xml_import", "sincronizzazione", "corrispettivi_sync",
                    "zip_upload", "manual_entry", "manual", "corrispettivo_manuale",
                ]}, "categoria": "Corrispettivi"},
                {"categoria": "Corrispettivi", "corrispettivo_id": {"$in": [None, ""]}},
            ],
        })
        await db["prima_nota_banca"].delete_many({
            "data": data,
            "source": {"$in": ["corrispettivo_pos", "corrispettivi_sync"]},
        })


async def _create_prima_nota_movements(db, corr_doc: Dict[str, Any]) -> Dict[str, Optional[str]]:
    """
    Crea i movimenti Prima Nota:
    - prima_nota_cassa (DARE) per la quota contanti
    - prima_nota_banca (DARE - entrata da conciliare) per la quota POS/elettronica
    """
    data = corr_doc.get("data", "")
    totale = _to_float(corr_doc.get("totale", 0))
    contanti = _to_float(corr_doc.get("pagato_contanti", 0))
    elettronico = _to_float(corr_doc.get("pagato_elettronico", 0))
    non_riscosso = _to_float(corr_doc.get("pagato_non_riscosso", 0))
    iva = _to_float(corr_doc.get("totale_iva", 0))
    imponibile = _to_float(corr_doc.get("totale_imponibile", 0))

    # Se i dettagli pagamento non ci sono, considera tutto contanti
    if contanti == 0 and elettronico == 0 and totale > 0:
        contanti = totale

    anno = int(data[:4]) if data and len(data) >= 4 and data[:4].isdigit() else datetime.now().year
    mese = int(data[5:7]) if data and len(data) >= 7 and data[5:7].isdigit() else datetime.now().month

    now = datetime.now(timezone.utc).isoformat()
    cassa_id = None
    banca_id = None

    if contanti > 0:
        cassa_id = str(uuid.uuid4())
        mov_cassa = {
            "id": cassa_id,
            "corrispettivo_id": corr_doc.get("id"),
            "data": data,
            "date": data,
            "tipo": "entrata",
            "type": "entrata",
            "importo": round(contanti, 2),
            "amount": round(contanti, 2),
            "descrizione": f"Corrispettivo contanti {data}",
            "description": f"Corrispettivo contanti {data}",
            "categoria": "Corrispettivi",
            "category": "Corrispettivi",
            "source": "corrispettivo_import",
            "anno": anno,
            "mese": mese,
            "imponibile": round(imponibile, 2),
            "iva": round(iva, 2),
            "contanti": round(contanti, 2),
            "elettronico": round(elettronico, 2),
            "non_riscosso": round(non_riscosso, 2),
            "dettaglio": {
                "contanti": round(contanti, 2),
                "elettronico": round(elettronico, 2),
                "totale_iva": round(iva, 2),
                "matricola_rt": corr_doc.get("matricola_rt", ""),
                "numero_documenti": corr_doc.get("numero_documenti", 0),
            },
            "created_at": now,
        }
        await db["prima_nota_cassa"].insert_one(mov_cassa.copy())

    if elettronico > 0:
        banca_id = str(uuid.uuid4())
        mov_banca = {
            "id": banca_id,
            "corrispettivo_id": corr_doc.get("id"),
            "data": data,
            "date": data,
            "tipo": "entrata",
            "type": "entrata",
            "importo": round(elettronico, 2),
            "amount": round(elettronico, 2),
            "descrizione": f"POS corrispettivo {data}",
            "description": f"POS corrispettivo {data}",
            "categoria": "Corrispettivi POS",
            "category": "Corrispettivi POS",
            "source": "corrispettivo_pos",
            "anno": anno,
            "mese": mese,
            "riconciliato": False,
            "created_at": now,
        }
        await db["prima_nota_banca"].insert_one(mov_banca.copy())

    return {"prima_nota_cassa_id": cassa_id, "prima_nota_banca_id": banca_id}


async def ingest_corrispettivo_parsed(
    db,
    parsed: Dict[str, Any],
    filename: str = "",
    source: str = "xml",
    *,
    update_if_exists: bool = False,
) -> Dict[str, Any]:
    """
    Punto d'ingresso unico per i corrispettivi importati.

    Ritorna:
    {
      "action": "created" | "updated" | "duplicate",
      "corrispettivo_id": str,
      "data": str,
      "totale": float,
      "prima_nota_cassa_id": Optional[str],
      "prima_nota_banca_id": Optional[str],
    }
    """
    corr_doc = _build_corrispettivo_doc(parsed, filename, source)
    data_str = corr_doc.get("data", "")
    totale = corr_doc.get("totale", 0.0)

    existing = await _find_existing_corrispettivo(db, corr_doc)

    # Se è un import XML e c'era un corrispettivo manuale provvisorio per
    # quella data, promuoviamo il record a "definitivo_xml" mantenendo traccia
    # storica del dato manuale (totale_manuale resta, data_inserimento_manuale
    # resta, ma totale/totale_xml vengono sovrascritti con i dati fiscali).
    # Vedi spiegazione flusso in POST /api/corrispettivi/manuale.
    was_manuale_provvisorio = bool(
        existing
        and source == "xml"
        and (
            existing.get("stato") in ("provvisorio", "manca_xml")
            or existing.get("source") in ("manuale_serale", "manuale", "manual_entry")
        )
    )
    if source == "xml":
        # L'import XML imposta sempre stato definitivo + totale_xml
        corr_doc["stato"] = "definitivo_xml"
        corr_doc["totale_xml"] = totale
        corr_doc["data_import_xml"] = datetime.now(timezone.utc).isoformat()
        # Se c'era il manuale, preserviamo totale_manuale e data_inserimento_manuale
        if was_manuale_provvisorio and existing:
            if existing.get("totale_manuale"):
                corr_doc["totale_manuale"] = existing.get("totale_manuale")
            if existing.get("data_inserimento_manuale"):
                corr_doc["data_inserimento_manuale"] = existing.get("data_inserimento_manuale")
            # Forziamo update_if_exists anche se il chiamante non l'ha chiesto:
            # promuovere provvisorio → definitivo è sempre sicuro
            update_if_exists = True

    if existing:
        if not update_if_exists:
            # Duplicato: non toccare Prima Nota
            return {
                "action": "duplicate",
                "corrispettivo_id": existing.get("id"),
                "data": data_str,
                "totale": totale,
                "prima_nota_cassa_id": None,
                "prima_nota_banca_id": None,
            }

        # Update: mantieni l'id originale
        corrispettivo_id = existing.get("id") or str(uuid.uuid4())
        corr_doc["id"] = corrispettivo_id
        corr_doc["created_at"] = existing.get("created_at") or datetime.now(timezone.utc).isoformat()

        await db["corrispettivi"].update_one(
            {"id": corrispettivo_id},
            {"$set": corr_doc}
        )

        # Rigenera i movimenti Prima Nota (elimina quelli vecchi e ricrea)
        await _delete_prima_nota_for_corrispettivo(db, corrispettivo_id, data_str)
        pn = await _create_prima_nota_movements(db, corr_doc)

        await db["corrispettivi"].update_one(
            {"id": corrispettivo_id},
            {"$set": {
                "prima_nota_id": pn.get("prima_nota_cassa_id") or pn.get("prima_nota_banca_id"),
                "prima_nota_cassa_id": pn.get("prima_nota_cassa_id"),
                "prima_nota_banca_id": pn.get("prima_nota_banca_id"),
            }}
        )

        return {
            "action": "updated",
            "corrispettivo_id": corrispettivo_id,
            "data": data_str,
            "totale": totale,
            **pn,
        }

    # NUOVO record
    corrispettivo_id = str(uuid.uuid4())
    corr_doc["id"] = corrispettivo_id
    corr_doc["created_at"] = datetime.now(timezone.utc).isoformat()
    await db["corrispettivi"].insert_one(corr_doc.copy())

    # Pulisci eventuali movimenti "manuali" per quella data prima di ricreare
    await _delete_prima_nota_for_corrispettivo(db, corrispettivo_id, data_str)
    pn = await _create_prima_nota_movements(db, corr_doc)

    await db["corrispettivi"].update_one(
        {"id": corrispettivo_id},
        {"$set": {
            "prima_nota_id": pn.get("prima_nota_cassa_id") or pn.get("prima_nota_banca_id"),
            "prima_nota_cassa_id": pn.get("prima_nota_cassa_id"),
            "prima_nota_banca_id": pn.get("prima_nota_banca_id"),
        }}
    )

    logger.info(f"[Corrispettivi] Nuovo importato data={data_str} totale={totale} "
                f"cassa={pn.get('prima_nota_cassa_id')} banca={pn.get('prima_nota_banca_id')}")

    return {
        "action": "created",
        "corrispettivo_id": corrispettivo_id,
        "data": data_str,
        "totale": totale,
        **pn,
    }


async def rebuild_prima_nota_from_corrispettivi(
    db,
    anno: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Rigenera i movimenti prima_nota_cassa e prima_nota_banca per tutti i
    corrispettivi di un anno (o di tutti gli anni se None).

    1. Elimina tutti i movimenti Prima Nota con source=corrispettivo_*
    2. Per ogni corrispettivo, ricrea i movimenti
    """
    query: Dict[str, Any] = {"entity_status": {"$ne": "deleted"}}
    if anno:
        query["data"] = {"$regex": f"^{anno}"}

    # 1) purge Prima Nota corrispettivi
    purge_sources_cassa = [
        "corrispettivo_import", "corrispettivo_pos",
        "xml_import", "sincronizzazione", "corrispettivi_sync",
        "zip_upload", "manual_entry", "manual", "corrispettivo_manuale",
    ]
    purge_filter_cassa = {
        "categoria": "Corrispettivi",
        "source": {"$in": purge_sources_cassa},
    }
    purge_filter_banca = {"source": {"$in": ["corrispettivo_pos", "corrispettivi_sync"]}}
    if anno:
        purge_filter_cassa["data"] = {"$regex": f"^{anno}"}
        purge_filter_banca["data"] = {"$regex": f"^{anno}"}

    del_cassa = await db["prima_nota_cassa"].delete_many(purge_filter_cassa)
    del_banca = await db["prima_nota_banca"].delete_many(purge_filter_banca)

    # 2) ricrea
    created_cassa = 0
    created_banca = 0
    processed = 0
    skipped = 0
    corrispettivi = await db["corrispettivi"].find(query, {"_id": 0}).to_list(100000)
    for corr in corrispettivi:
        if not corr.get("data") or _to_float(corr.get("totale", 0)) <= 0:
            skipped += 1
            continue
        pn = await _create_prima_nota_movements(db, corr)
        await db["corrispettivi"].update_one(
            {"id": corr.get("id")},
            {"$set": {
                "prima_nota_id": pn.get("prima_nota_cassa_id") or pn.get("prima_nota_banca_id"),
                "prima_nota_cassa_id": pn.get("prima_nota_cassa_id"),
                "prima_nota_banca_id": pn.get("prima_nota_banca_id"),
            }}
        )
        if pn.get("prima_nota_cassa_id"):
            created_cassa += 1
        if pn.get("prima_nota_banca_id"):
            created_banca += 1
        processed += 1

    return {
        "anno": anno,
        "corrispettivi_processati": processed,
        "corrispettivi_saltati": skipped,
        "prima_nota_cassa_eliminati": del_cassa.deleted_count,
        "prima_nota_banca_eliminati": del_banca.deleted_count,
        "prima_nota_cassa_creati": created_cassa,
        "prima_nota_banca_creati": created_banca,
    }


async def cleanup_duplicate_corrispettivi(db, anno: Optional[int] = None) -> Dict[str, Any]:
    """
    Elimina i duplicati dalla collection 'corrispettivi' sulla base di (data, matricola_rt, totale).
    Per ogni gruppo tiene il record più vecchio (created_at o _id) e hard-delete degli altri.
    """
    match: Dict[str, Any] = {"entity_status": {"$ne": "deleted"}}
    if anno:
        match["data"] = {"$regex": f"^{anno}"}

    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": {
                "data": "$data",
                "matricola_rt": {"$ifNull": ["$matricola_rt", ""]},
                "totale": {"$round": [{"$ifNull": ["$totale", 0]}, 2]},
            },
            "count": {"$sum": 1},
            "docs": {"$push": {"id": "$id", "created_at": "$created_at", "_id": "$_id"}},
        }},
        {"$match": {"count": {"$gt": 1}}},
    ]
    dupes = await db["corrispettivi"].aggregate(pipeline).to_list(100000)

    deleted = 0
    groups = 0
    for g in dupes:
        docs = g["docs"]
        # Ordina per created_at (None in coda), mantiene il primo
        docs.sort(key=lambda d: (d.get("created_at") or "9999", str(d.get("_id"))))
        to_delete_ids = [d["id"] for d in docs[1:] if d.get("id")]
        if to_delete_ids:
            r = await db["corrispettivi"].delete_many({"id": {"$in": to_delete_ids}})
            deleted += r.deleted_count
            groups += 1

    return {"gruppi_duplicati": groups, "corrispettivi_eliminati": deleted, "anno": anno}
