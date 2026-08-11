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

from app.services.payment_allocation_validator import to_cents

logger = logging.getLogger(__name__)


async def _check_coerenza_pos(db, corr_doc: Dict[str, Any]) -> None:
    """
    Confronta l'elettronico dichiarato dal corrispettivo con l'accredito
    Nexi in banca, segnalando eventuali differenze. Fail-safe: un errore qui
    non deve mai bloccare l'import del corrispettivo (già scritto in Prima
    Nota prima di questa chiamata).
    """
    try:
        from app.handlers.corrispettivi import handler_check_coerenza_pos
        await handler_check_coerenza_pos({
            "data": corr_doc.get("data", ""),
            "totale_elettronico": corr_doc.get("pagato_elettronico", 0),
        }, db)
    except Exception:
        logger.exception(f"[Corrispettivi] Errore check coerenza POS per {corr_doc.get('data')}")


def _to_float(v: Any) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _build_corrispettivo_doc(parsed: Dict[str, Any], filename: str, source: str) -> Dict[str, Any]:
    data = parsed.get("data", "") or ""
    anno = int(data[:4]) if data and len(data) >= 4 and data[:4].isdigit() else datetime.now().year
    mese = int(data[5:7]) if data and len(data) >= 7 and data[5:7].isdigit() else datetime.now().month
    righe_iva = []
    for row in parsed.get("riepilogo_iva", []) or []:
        imponibile_cents = to_cents(row.get("ammontare", row.get("imponibile", 0)))
        iva_cents = to_cents(row.get("imposta", 0))
        righe_iva.append({
            **row,
            "imponibile_cents": imponibile_cents,
            "iva_cents": iva_cents,
            "totale_cents": imponibile_cents + iva_cents,
        })

    totale_cents = to_cents(parsed.get("totale", 0))
    contanti_cents = to_cents(parsed.get("pagato_contanti", 0))
    elettronico_cents = to_cents(parsed.get("pagato_elettronico", 0))
    imponibile_cents = to_cents(parsed.get("totale_imponibile", 0))
    iva_cents = to_cents(parsed.get("totale_iva", 0))
    iva_printed = bool(righe_iva) and all(
        bool(row.get("imposta_presente")) for row in parsed.get("riepilogo_iva", []) or []
    )
    if iva_printed:
        quadratura_iva = "VERIFICATA" if imponibile_cents + iva_cents == totale_cents else "ERRORE"
    else:
        quadratura_iva = "NON_VERIFICABILE"
    return {
        "corrispettivo_key": parsed.get("corrispettivo_key", ""),
        "data": data,
        "matricola_rt": parsed.get("matricola_rt", ""),
        "numero_documento": parsed.get("numero_documento", ""),
        "partita_iva": parsed.get("partita_iva", ""),
        "totale": totale_cents / 100,
        "totale_cents": totale_cents,
        "pagato_contanti": contanti_cents / 100,
        "pagato_contanti_cents": contanti_cents,
        "pagato_elettronico": elettronico_cents / 100,
        "pagato_elettronico_cents": elettronico_cents,
        "totale_imponibile": imponibile_cents / 100,
        "totale_imponibile_cents": imponibile_cents,
        "totale_iva": iva_cents / 100,
        "totale_iva_cents": iva_cents,
        "quadratura_iva_status": quadratura_iva,
        "iva_source": "XML_STAMPATO" if iva_printed else "NON_DISPONIBILE",
        "pagato_non_riscosso": _to_float(parsed.get("pagato_non_riscosso", 0)),
        "totale_ammontare_annulli": _to_float(parsed.get("totale_ammontare_annulli", 0)),
        "numero_documenti": int(_to_float(parsed.get("numero_documenti", 0))),
        "riepilogo_iva": righe_iva,
        "status": "imported",
        "source": source,
        "filename": filename,
        "sha256": parsed.get("sha256") or parsed.get("document_hash"),
        "parser_version": parsed.get("parser_version") or "corrispettivi_xml_v2_cents",
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
                # Bug A (segnalato dall'utente 14/07/2026): la quick-form
                # "💳 POS" di Prima Nota (PrimaNota.jsx::handleSavePos) crea
                # un'uscita provvisoria categoria "POS"/source "manual_pos"
                # con commento "Sarà sovrascritto quando arriva XML" — ma
                # nessuna delle due clausole sopra la intercetta (categoria
                # diversa da "Corrispettivi"), quindi restava un'uscita
                # cassa fantasma per sempre, mai riconciliata con
                # Coerenza POS (che legge solo prima_nota_banca) e mai
                # sostituita dal vero movimento "POS Verso Banca" creato
                # dall'import XML: le due finivano per sommarsi, gonfiando
                # le uscite cassa. Ora viene ripulita quando arriva il
                # corrispettivo reale per la stessa data, come promesso.
                {"source": "manual_pos", "categoria": "POS"},
            ],
        })
        await db["prima_nota_banca"].delete_many({
            "data": data,
            "source": {"$in": ["corrispettivo_pos", "corrispettivi_sync"]},
        })


async def _create_prima_nota_movements(db, corr_doc: Dict[str, Any]) -> Dict[str, Optional[str]]:
    """MIGRATO AL MOTORE UNICO (18/07/2026, decisione utente): la logica
    vive in app/services/scritture_contabili.registra_corrispettivo.
    MODELLO POS: uscita cassa = CHIUSURA MANUALE serale del terminale
    (fallback XML); la banca riceve il TRASFERIMENTO speculare (source
    trasferimento_pos, stesso trasferimento_id, uno per circuito), che
    l'accredito reale dell'estratto conto riconcilia senza duplicare.

    NB: fino al 18/07/2026 questa docstring diceva che "la banca NON riceve
    più righe sintetiche". Era il modello precedente ed è stato superato dalla
    regola canonica POS: escludere il trasferimento dai saldi banca è
    esattamente il bug del 16/07/2026 che faceva sparire ~204.000 € di
    incassi POS. Il trasferimento resta nel saldo contabile ed è marcato
    ``in_transito`` finché l'accredito non lo conferma."""
    from app.services.scritture_contabili import registra_corrispettivo
    return await registra_corrispettivo(db, corr_doc)




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

        await _check_coerenza_pos(db, corr_doc)

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

    # Follow-up dal fix di registra_corrispettivo (PR #67): _find_existing_
    # corrispettivo sopra fa più find_one separati (chiave XML, poi data+
    # matricola, poi data+totale) prima di questo insert — due upload dello
    # stesso corrispettivo lanciati quasi in contemporanea potevano superare
    # entrambi il controllo prima che uno dei due avesse scritto, creando
    # due documenti "corrispettivi" duplicati (anche se, grazie al fix già
    # in produzione, il movimento in Prima Nota Cassa non si duplicava).
    # Quando è disponibile la chiave naturale del file XML (il caso comune
    # e quello a rischio reale di doppio import automatico), l'insert
    # diventa un'unica operazione atomica lato MongoDB. I due controlli più
    # deboli (data+matricola, data+totale — usati per corrispettivi
    # manuali/provvisori senza chiave XML) restano non atomici: rischio
    # residuo noto, non coperto in questo fix mirato.
    chiave_xml = (corr_doc.get("corrispettivo_key") or "").strip()
    if chiave_xml:
        # Review Codex su PR #68: la query deve escludere i soft-delete
        # esattamente come fa _find_existing_corrispettivo sopra (livello 1),
        # altrimenti un corrispettivo eliminato (entity_status="deleted")
        # con la stessa chiave XML verrebbe considerato "già esistente" e
        # impedirebbe di ricrearlo ricaricando lo stesso file.
        precedente = await db["corrispettivi"].find_one_and_update(
            {
                "corrispettivo_key": chiave_xml,
                "entity_status": {"$ne": "deleted"},
                "status": {"$nin": ["deleted", "archived"]},
            },
            {"$setOnInsert": corr_doc.copy()},
            upsert=True,
        )
        if precedente:
            # Race persa: un'altra richiesta concorrente ha già creato il
            # documento per questa chiave tra il controllo sopra e questo
            # insert. Trattalo come duplicato, non toccare Prima Nota.
            return {
                "action": "duplicate",
                "corrispettivo_id": precedente.get("id"),
                "data": data_str,
                "totale": totale,
                "prima_nota_cassa_id": None,
                "prima_nota_banca_id": None,
            }
    else:
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

    await _check_coerenza_pos(db, corr_doc)

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

    # 1) purge Prima Nota corrispettivi.
    # Bug corretto 16/07/2026 (verifica live sui dati reali): il purge era
    # limitato a categoria "Corrispettivi" + una lista parziale di source,
    # quindi NON eliminava mai né le uscite POS (categoria "POS Verso Banca",
    # stesso source corrispettivo_import) né i residui delle pipeline
    # smantellate (source corrispettivo_xml → entrate duplicate e "Girofondi
    # POS"; corrispettivi_pos_sync → seconda uscita POS "POS"; manuale_da_xml).
    # In produzione: 1066 entrate Corrispettivi per 149 corrispettivi reali
    # (37 giorni con 26 copie) e 50 giorni con uscita POS doppia. Ora il
    # purge è per SOURCE su tutte le righe generate dai corrispettivi, di
    # qualunque categoria; i movimenti manuali/di altra origine (versamenti,
    # pagamenti fatture) non vengono toccati.
    purge_sources_cassa = [
        "corrispettivo_import", "corrispettivo_pos",
        "xml_import", "sincronizzazione", "corrispettivi_sync",
        "zip_upload", "manual_entry", "manual", "corrispettivo_manuale",
        "corrispettivo_xml", "corrispettivi_pos_sync", "manuale_da_xml",
    ]
    purge_filter_cassa = {"source": {"$in": purge_sources_cassa}}
    # La contropartita bancaria del motore unico usa source
    # "trasferimento_pos". Se non viene rimossa, il rebuild conserva le
    # vecchie quote POS invece di rigenerarle dai corrispettivi aggiornati.
    purge_filter_banca = {"source": {"$in": [
        "corrispettivo_pos", "corrispettivi_sync", "trasferimento_pos",
    ]}}
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
    duplicati_saltati = 0
    # Dedup difensivo per (data, matricola, totale): esiste un solo
    # registratore (regola utente §5) quindi un solo corrispettivo per
    # giorno/matricola — se in collection restano documenti duplicati
    # (reimport storici non ancora ripuliti da cleanup_duplicate_corrispettivi)
    # il rebuild NON deve creare due entrate per lo stesso giorno.
    visti = set()
    corrispettivi = await db["corrispettivi"].find(query, {"_id": 0}).to_list(100000)
    if len(corrispettivi) >= 100000:
        logger.warning("rebuild_prima_nota_from_corrispettivi: raggiunto il tetto di 100000 documenti, possibile troncamento")
    # Ordina per created_at (i più vecchi prima): a parità di giorno/matricola
    # sopravvive il documento originale, i reimport successivi vengono saltati.
    corrispettivi.sort(key=lambda c: c.get("created_at") or "9999")
    for corr in corrispettivi:
        # Stessa regola di fallback usata da _create_prima_nota_movements: un
        # corrispettivo storico può non avere il campo "totale" popolato e
        # riportare solo pagato_contanti/pagato_elettronico (es. record creati
        # dal vecchio data_propagation.py). Controllare solo "totale" qui
        # scartava questi record dalla ricostruzione DOPO che il movimento
        # Prima Nota corrispondente era già stato eliminato dal purge sopra
        # (stesso source "corrispettivo_import"), facendo sparire il
        # corrispettivo da Prima Nota invece di ricrearlo correttamente.
        totale_o_fallback = _to_float(
            corr.get("totale")
            or corr.get("totale_complessivo")
            or corr.get("importo")
            or corr.get("totale_giornaliero")
            or (_to_float(corr.get("pagato_contanti", 0)) + _to_float(corr.get("pagato_elettronico", 0)) or _to_float(corr.get("pagato_pos", 0)))
        )
        if not corr.get("data") or totale_o_fallback <= 0:
            skipped += 1
            continue
        chiave = (corr.get("data"), corr.get("matricola_rt") or "", round(totale_o_fallback, 2))
        if chiave in visti:
            duplicati_saltati += 1
            continue
        visti.add(chiave)
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
        "corrispettivi_duplicati_saltati": duplicati_saltati,
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
    if len(dupes) >= 100000:
        logger.warning("cleanup_duplicate_corrispettivi: raggiunto il tetto di 100000 gruppi duplicati, possibile troncamento")

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
