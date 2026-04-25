from fastapi import APIRouter, HTTPException, Body
from fastapi.responses import FileResponse
from datetime import datetime, timezone
from typing import Dict, Any
import os
import re

from app.database import Database
from app.services.paypal_api_sync import sync_paypal_period
from app.services.paypal_riconciliazione import match_fornitore, normalize_string

router = APIRouter(tags=["PayPal API"])


@router.post("/sync")
async def sync_period(body: Dict[str, Any] = Body(...)):
    try:
        start = datetime.fromisoformat(body["start_date"]).replace(tzinfo=timezone.utc)
        end = datetime.fromisoformat(body["end_date"]).replace(tzinfo=timezone.utc)
    except (KeyError, ValueError) as e:
        raise HTTPException(400, f"Formato data non valido: {e}")

    db = Database.get_db()
    result = await sync_paypal_period(db, start, end)
    return result


@router.post("/sync/month")
async def sync_current_month():
    from calendar import monthrange
    now = datetime.now(timezone.utc)
    last_day = monthrange(now.year, now.month)[1]
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = now.replace(day=last_day, hour=23, minute=59, second=59)

    db = Database.get_db()
    return await sync_paypal_period(db, start, end)


@router.get("/status")
async def status():
    db = Database.get_db()
    total = await db["paypal_transactions"].count_documents({})
    enriched = await db["paypal_transactions"].count_documents({"source": "paypal_api"})
    pagopa = await db["paypal_transactions"].count_documents({"is_pagopa": True})

    last = await db["paypal_transactions"].find_one(
        {"source": "paypal_api"},
        sort=[("enriched_at", -1)],
        projection={"_id": 0, "enriched_at": 1},
    )
    return {
        "total_transazioni": total,
        "arricchite_da_api": enriched,
        "identificate_pagopa": pagopa,
        "ultimo_sync": last.get("enriched_at") if last else None,
    }


@router.post("/riconcilia")
async def riconcilia_da_collection(body: Dict[str, Any] = Body(default={})):
    """
    FASE 2: riconciliazione unificata che processa in sequenza:
    1. Multe PagoPA → verbali_noleggio
    2. Fatture commerciali → invoices (match by paypal_account_id)
    3. Allineamento paypal_transactions ↔ estratto_conto_movimenti
    """
    from app.services.paypal_riconciliazione import (
        riconcilia_pagamenti_paypal,
        riconcilia_multe_pagopa,
        collega_a_estratto_conto,
    )

    db = Database.get_db()
    q: Dict[str, Any] = {"importo": {"$lt": 0}}
    if body.get("start_date"):
        q["initiation_date"] = {"$gte": body["start_date"]}
    if body.get("end_date"):
        q.setdefault("initiation_date", {})["$lte"] = body["end_date"] + "T23:59:59Z"

    txs = await db["paypal_transactions"].find(q, {"_id": 0}).to_list(5000)
    multe = [t for t in txs if t.get("is_pagopa")]
    fatture = [t for t in txs if not t.get("is_pagopa")]

    r_multe = await riconcilia_multe_pagopa(db, multe)
    r_fatt = await riconcilia_pagamenti_paypal(db, [
        {
            "data": (t.get("initiation_date") or "")[:10],
            "beneficiario": t.get("paypal_account_id", "") or t.get("transaction_subject", ""),
            "paypal_account_id": t.get("paypal_account_id"),
            "importo": t.get("importo", 0),
            "codice_transazione": t.get("transaction_id"),
        }
        for t in fatture
    ])
    r_banca = await collega_a_estratto_conto(db)
    return {"multe_pagopa": r_multe, "fatture": r_fatt, "banca": r_banca}


@router.get("/ricevuta-pdf/{transaction_id}")
async def scarica_ricevuta_pdf(transaction_id: str):
    from app.services.paypal_pdf_fetcher import (
        fetch_ricevuta_pagopa,
        genera_pdf_transazione_paypal,
    )
    db = Database.get_db()
    tx = await db["paypal_transactions"].find_one({"transaction_id": transaction_id})
    if not tx:
        raise HTTPException(404, "Transazione non trovata")
    pdf_path = tx.get("pdf_ricevuta_path") or tx.get("pdf_generato_path")
    if not pdf_path or not os.path.exists(pdf_path):
        if tx.get("is_pagopa"):
            r = await fetch_ricevuta_pagopa(
                db, transaction_id,
                abs(tx.get("importo", 0)),
                tx.get("initiation_date", ""),
            )
            pdf_path = r["pdf_path"] if r else None
        if not pdf_path:
            pdf_path = await genera_pdf_transazione_paypal(db, transaction_id)
    if not pdf_path or not os.path.exists(pdf_path):
        raise HTTPException(404, "PDF non disponibile")
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=f"ricevuta_paypal_{transaction_id}.pdf",
    )


@router.get("/account-ids-non-mappati")
async def account_ids_non_mappati():
    """
    Ritorna lista di paypal_account_id presenti in paypal_transactions
    ma NON ancora mappati a un fornitore. Per ciascun account_id aggrega:
    - n. transazioni, importo totale, ultima data, lista transaction_subject/invoice_id
    - fornitori candidati (per importo vicino + nome simile)
    """
    from app.services.paypal_riconciliazione import normalize_string, match_fornitore  # noqa: F811

    db = Database.get_db()

    # Aggrega i paypal_account_id dalle transazioni
    pipeline = [
        {"$match": {"paypal_account_id": {"$exists": True, "$nin": [None, ""]}}},
        {"$group": {
            "_id": "$paypal_account_id",
            "n_tx": {"$sum": 1},
            "importo_totale": {"$sum": "$importo"},
            "ultima_data": {"$max": "$initiation_date"},
            "subjects": {"$addToSet": "$transaction_subject"},
            "invoice_ids": {"$addToSet": "$invoice_id_fornitore"},
            "is_pagopa": {"$max": "$is_pagopa"},
            "nome_controparte": {"$first": "$nome_controparte"},
            "email_controparte": {"$first": "$email_controparte"},
        }},
        {"$sort": {"ultima_data": -1}},
    ]
    aggregates = await db["paypal_transactions"].aggregate(pipeline).to_list(500)

    # Fornitori già mappati
    mapped_ids = set()
    async for f in db["fornitori"].find(
        {"paypal_account_id": {"$ne": None}},
        {"_id": 0, "paypal_account_id": 1}
    ):
        if f.get("paypal_account_id"):
            mapped_ids.add(f["paypal_account_id"])

    # Per le transazioni PagoPA il fornitore è un ente, non serve mapping
    risultati = []
    for agg in aggregates:
        account_id = agg["_id"]
        if account_id in mapped_ids:
            continue
        if agg.get("is_pagopa"):
            continue

        importo_medio = abs(agg["importo_totale"] / max(agg["n_tx"], 1))
        subjects = [s for s in agg.get("subjects") or [] if s]
        invoice_ids = [i for i in agg.get("invoice_ids") or [] if i]
        nome_controparte = (agg.get("nome_controparte") or "").strip()

        query_text = " ".join(subjects[:3])
        candidati = []
        suggested_forn_id = None  # pre-selezione UI se match certo

        # STRATEGIA 1 (match certo): cerca fornitore con ragione_sociale che matcha nome_controparte
        if nome_controparte:
            # Prima parola significativa (es. "Gruppo Adam s.r.l." → "Gruppo Adam" o "Gruppo")
            words = [w for w in nome_controparte.split() if len(w) >= 3
                     and w.lower() not in ("spa", "srl", "s.r.l.", "s.p.a.", "s.r.l", "s.p.a",
                                            "sas", "snc", "ltd", "gmbh", "ag", "sa", "ab")]
            search_word = words[0] if words else nome_controparte.split()[0]

            cursor_forn = db["fornitori"].find(
                {"$or": [
                    {"nome": {"$regex": re.escape(search_word), "$options": "i"}},
                    {"ragione_sociale": {"$regex": re.escape(search_word), "$options": "i"}},
                ]},
                {"_id": 0, "id": 1, "nome": 1, "ragione_sociale": 1, "piva": 1}
            )
            async for forn in cursor_forn:
                forn_nome = forn.get("ragione_sociale") or forn.get("nome") or ""
                # Normalizza entrambi per match
                norm_cp = normalize_string(nome_controparte)
                norm_fn = normalize_string(forn_nome)
                # Exact match (uguali dopo normalize) oppure uno contiene l'altro
                if norm_cp == norm_fn:
                    match_type = "exact"
                    score = 1.0
                elif norm_cp in norm_fn or norm_fn in norm_cp:
                    match_type = "partial"
                    score = 0.85
                else:
                    # Fuzzy score su nome
                    score = match_fornitore(nome_controparte, forn_nome)
                    match_type = "fuzzy" if score >= 0.6 else None
                if match_type:
                    candidato = {
                        "fornitore_id": forn.get("id"),
                        "nome": forn_nome,
                        "piva": forn.get("piva") or "",
                        "n_fatture_simili": 0,
                        "score": round(score, 2),
                        "source": f"nome_paypal_{match_type}",
                    }
                    candidati.append(candidato)
                    # Primo match esatto → lo suggeriamo per pre-selezione
                    if match_type == "exact" and not suggested_forn_id:
                        suggested_forn_id = forn.get("id")

        # STRATEGIA 2: fornitori con fatture di importo simile (fallback)
        min_imp = importo_medio * 0.6
        max_imp = importo_medio * 1.4
        pipeline_forn = [
            {"$match": {"total_amount": {"$gte": min_imp, "$lte": max_imp}}},
            {"$group": {
                "_id": "$supplier_vat",
                "supplier_name": {"$first": "$supplier_name"},
                "fornitore_denominazione": {"$first": "$fornitore_denominazione"},
                "n_fatture": {"$sum": 1},
            }},
            {"$limit": 30},
        ]
        try:
            forn_cursor = await db["invoices"].aggregate(pipeline_forn).to_list(30)
        except Exception:
            forn_cursor = []

        seen_piva = {c["piva"] for c in candidati if c.get("piva")}
        seen_ids = {c["fornitore_id"] for c in candidati}
        for fc in forn_cursor:
            piva = fc.get("_id")
            if not piva or piva in seen_piva:
                continue
            seen_piva.add(piva)
            nome = fc.get("supplier_name") or fc.get("fornitore_denominazione") or ""
            score = match_fornitore(query_text or account_id, nome) if query_text else 0.0
            # Boost se il nome matcha nome_controparte
            if nome_controparte and nome:
                cp_score = match_fornitore(nome_controparte, nome)
                if cp_score > score:
                    score = cp_score
            forn = await db["fornitori"].find_one(
                {"$or": [{"piva": piva}, {"partita_iva": piva}, {"codice_fiscale": piva}]},
                {"_id": 0, "id": 1, "nome": 1, "ragione_sociale": 1, "piva": 1}
            )
            if forn and forn.get("id") not in seen_ids:
                seen_ids.add(forn.get("id"))
                candidati.append({
                    "fornitore_id": forn.get("id"),
                    "nome": forn.get("ragione_sociale") or forn.get("nome") or nome,
                    "piva": forn.get("piva") or piva,
                    "n_fatture_simili": fc.get("n_fatture", 0),
                    "score": round(score, 2),
                    "source": "importo_simile",
                })
        # Ordina per score desc poi per n_fatture desc
        candidati.sort(key=lambda c: (c["score"], c["n_fatture_simili"]), reverse=True)

        risultati.append({
            "paypal_account_id": account_id,
            "nome_controparte": nome_controparte or None,
            "email_controparte": agg.get("email_controparte") or None,
            "n_tx": agg["n_tx"],
            "importo_totale": round(abs(agg["importo_totale"]), 2),
            "importo_medio": round(importo_medio, 2),
            "ultima_data": agg["ultima_data"],
            "subjects": subjects[:5],
            "invoice_ids": invoice_ids[:5],
            "candidati": candidati[:8],
            "suggested_fornitore_id": suggested_forn_id,
        })

    return {
        "totale_non_mappati": len(risultati),
        "items": risultati,
    }


@router.post("/mappa-fornitore")
async def mappa_fornitore(body: Dict[str, Any] = Body(...)):
    """Associa un paypal_account_id a un fornitore esistente."""
    paypal_account_id = (body.get("paypal_account_id") or "").strip()
    fornitore_id = (body.get("fornitore_id") or "").strip()
    if not paypal_account_id or not fornitore_id:
        raise HTTPException(400, "paypal_account_id e fornitore_id richiesti")

    db = Database.get_db()
    forn = await db["fornitori"].find_one({"id": fornitore_id}, {"_id": 0, "id": 1, "nome": 1, "ragione_sociale": 1})
    if not forn:
        raise HTTPException(404, "Fornitore non trovato")

    # Verifica che l'account_id non sia già mappato a un altro fornitore
    already = await db["fornitori"].find_one(
        {"paypal_account_id": paypal_account_id, "id": {"$ne": fornitore_id}},
        {"_id": 0, "id": 1, "nome": 1, "ragione_sociale": 1}
    )
    if already:
        raise HTTPException(409, f"Account già mappato a: {already.get('ragione_sociale') or already.get('nome')}")

    res = await db["fornitori"].update_one(
        {"id": fornitore_id},
        {"$set": {"paypal_account_id": paypal_account_id, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    return {
        "success": True,
        "modified": res.modified_count,
        "fornitore": forn.get("ragione_sociale") or forn.get("nome"),
        "paypal_account_id": paypal_account_id,
    }


@router.post("/smappa-fornitore")
async def smappa_fornitore(body: Dict[str, Any] = Body(...)):
    """Rimuove mapping paypal_account_id da un fornitore (per correzioni)."""
    fornitore_id = (body.get("fornitore_id") or "").strip()
    if not fornitore_id:
        raise HTTPException(400, "fornitore_id richiesto")
    db = Database.get_db()
    res = await db["fornitori"].update_one(
        {"id": fornitore_id},
        {"$unset": {"paypal_account_id": ""},
         "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    return {"success": True, "modified": res.modified_count}


@router.post("/crea-fornitore-e-mappa")
async def crea_fornitore_e_mappa(body: Dict[str, Any] = Body(...)):
    """Crea un nuovo fornitore E lo mappa al paypal_account_id in un'unica operazione.

    Body:
        {
            "paypal_account_id": "6QL6S5MMB8NA2",  # OBBLIGATORIO
            "ragione_sociale":   "MongoDB Limited",  # OBBLIGATORIO
            "piva":              "IE9952657T",       # opzionale
            "nazione":           "IE",               # default "IT"
            "metodo_pagamento":  "paypal",           # default "paypal" (è ovvio)
            "esclude_magazzino": True,               # default True
            "email":             "billing@mongodb.com",  # opzionale
            "note":              "Servizi cloud DB"
        }

    Comportamento:
    - Verifica che il paypal_account_id non sia già mappato altrove (409)
    - Verifica che la P.IVA non sia duplicata (409)
    - Crea il fornitore con uuid + valori default sensati per fornitori PayPal
      (esclude_magazzino=True perché tipicamente sono SaaS/servizi, non prodotti)
    - Imposta automaticamente paypal_account_id sul nuovo record
    """
    import uuid

    paypal_account_id = (body.get("paypal_account_id") or "").strip()
    ragione_sociale = (body.get("ragione_sociale") or "").strip()
    if not paypal_account_id:
        raise HTTPException(400, "paypal_account_id richiesto")
    if not ragione_sociale:
        raise HTTPException(400, "ragione_sociale richiesta")

    db = Database.get_db()

    # Anti-duplicazione 1: paypal_account_id già mappato?
    already_mapped = await db["fornitori"].find_one(
        {"paypal_account_id": paypal_account_id},
        {"_id": 0, "id": 1, "nome": 1, "ragione_sociale": 1}
    )
    if already_mapped:
        raise HTTPException(
            409,
            f"Account PayPal già mappato a fornitore: "
            f"{already_mapped.get('ragione_sociale') or already_mapped.get('nome')}"
        )

    # Anti-duplicazione 2: P.IVA già esistente?
    piva = (body.get("piva") or "").strip().upper()
    if piva:
        existing_by_piva = await db["fornitori"].find_one(
            {"piva": piva},
            {"_id": 0, "id": 1, "nome": 1, "ragione_sociale": 1}
        )
        if existing_by_piva:
            raise HTTPException(
                409,
                f"P.IVA già presente per: "
                f"{existing_by_piva.get('ragione_sociale') or existing_by_piva.get('nome')}. "
                f"Usa /mappa-fornitore con fornitore_id={existing_by_piva.get('id')}"
            )

    now_iso = datetime.now(timezone.utc).isoformat()
    fornitore_id = str(uuid.uuid4())

    fornitore = {
        "id": fornitore_id,
        "nome": ragione_sociale,
        "ragione_sociale": ragione_sociale,
        "piva": piva,
        "codice_fiscale": (body.get("codice_fiscale") or "").upper().strip(),
        "email": (body.get("email") or "").strip(),
        "telefono": (body.get("telefono") or "").strip(),
        "indirizzo": (body.get("indirizzo") or "").strip(),
        "cap": (body.get("cap") or "").strip(),
        "comune": (body.get("comune") or "").strip(),
        "provincia": (body.get("provincia") or "").strip(),
        "nazione": (body.get("nazione") or "IT").upper().strip(),
        "iban": "",  # PayPal non usa IBAN
        "iban_lista": [],
        "metodo_pagamento": body.get("metodo_pagamento") or "paypal",
        "giorni_pagamento": int(body.get("giorni_pagamento") or 0),
        "esclude_magazzino": bool(body.get("esclude_magazzino", True)),
        "escludi_da_tracciabilita": bool(body.get("escludi_da_tracciabilita", False)),
        "paypal_account_id": paypal_account_id,
        "note": (body.get("note") or "").strip() or "Creato da mapping PayPal",
        "source": "paypal_mapping",
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    await db["fornitori"].insert_one(fornitore.copy())
    fornitore.pop("_id", None)

    # Conta transazioni che ora avranno il fornitore mappato
    n_tx = await db["paypal_transactions"].count_documents(
        {"paypal_account_id": paypal_account_id}
    )

    return {
        "success": True,
        "fornitore_id": fornitore_id,
        "ragione_sociale": ragione_sociale,
        "paypal_account_id": paypal_account_id,
        "n_transazioni_collegabili": n_tx,
        "fornitore": fornitore,
    }
