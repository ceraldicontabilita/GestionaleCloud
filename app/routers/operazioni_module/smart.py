"""
Operazioni Module - Riconciliazione Smart (banca veloce, analisi, associazioni).
"""
from fastapi import HTTPException
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from app.database import Database
from app.utils.parsing import safe_float
from .common import RiconciliaManuale, ConfermaBatchRequest, logger, QUERY_FATTURA_NON_PAGATA, set_fattura_pagata


async def banca_veloce(
    limit: int = 50,
    solo_non_riconciliati: bool = True
) -> Dict[str, Any]:
    """Endpoint veloce per tab Banca - movimenti + assegni + fatture da pagare."""
    db = Database.get_db()
    
    query = {}
    if solo_non_riconciliati:
        query["riconciliato"] = {"$ne": True}
    
    movimenti = await db.estratto_conto_movimenti.find(
        query,
        {"_id": 0}
    ).sort("data", -1).limit(limit).to_list(limit)
    
    assegni = await db.assegni.find(
        {"stato": {"$nin": ["incassato", "annullato"]}, "confermato": {"$ne": True}},
        {"_id": 0}
    ).sort("data_emissione", -1).limit(50).to_list(50)
    
    fatture_da_pagare = await db.invoices.find(
        {**QUERY_FATTURA_NON_PAGATA, "metodo_pagamento": {"$nin": [None, "", "contanti"]}},
        {"_id": 0, "id": 1, "invoice_number": 1, "invoice_date": 1, "supplier_name": 1, "total_amount": 1}
    ).sort("invoice_date", -1).limit(50).to_list(50)
    
    tot_non_ric = await db.estratto_conto_movimenti.count_documents({"riconciliato": {"$ne": True}})
    tot_ric = await db.estratto_conto_movimenti.count_documents({"riconciliato": True})
    
    return {
        "movimenti": movimenti,
        "assegni": assegni,
        "fatture_da_pagare": fatture_da_pagare,
        "stats": {
            "totale": len(movimenti),
            "non_riconciliati": tot_non_ric,
            "riconciliati": tot_ric,
            "assegni_pendenti": len(assegni),
            "fatture_da_pagare": len(fatture_da_pagare)
        }
    }


async def analizza_movimenti_smart(
    limit: int = 100,
    solo_non_riconciliati: bool = True
) -> Dict[str, Any]:
    """Analizza movimenti estratto conto con suggerimenti riconciliazione."""
    from app.services.riconciliazione_smart import analizza_estratto_conto_batch
    
    try:
        risultati = await analizza_estratto_conto_batch(limit, solo_non_riconciliati)
        return risultati
    except Exception as e:
        logger.error(f"Errore analisi smart: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def analizza_singolo_movimento(movimento_id: str) -> Dict[str, Any]:
    """Analizza un singolo movimento.

    Bug: importava `analizza_singolo_movimento` da riconciliazione_smart.py,
    funzione mai esistita in quel modulo (solo `analizza_movimento`,
    `analizza_movimento_con_cache`, `analizza_estratto_conto_batch`) — ogni
    chiamata a questo endpoint dava sempre ImportError/500. Corretto: carica
    il movimento e usa `analizza_movimento`, che si aspetta il dict."""
    from app.services.riconciliazione_smart import analizza_movimento

    db = Database.get_db()
    movimento = await db.estratto_conto_movimenti.find_one({"id": movimento_id}, {"_id": 0})
    if not movimento:
        raise HTTPException(status_code=404, detail="Movimento non trovato")

    try:
        return await analizza_movimento(movimento)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def riconcilia_automatico(
    tipo: Optional[str] = None,
    limit: int = 100
) -> Dict[str, Any]:
    """Riconciliazione automatica dei movimenti."""
    db = Database.get_db()
    
    query = {"riconciliato": {"$ne": True}}
    if tipo:
        query["tipo_suggerito"] = tipo
    
    movimenti = await db.estratto_conto_movimenti.find(query, {"_id": 0}).limit(limit).to_list(limit)
    
    riconciliati = 0
    errori = []
    
    for mov in movimenti:
        try:
            importo = abs(safe_float(mov.get("importo", 0)))
            descrizione = (mov.get("descrizione") or mov.get("descrizione_originale") or "").upper()

            match_found = False

            # Match fatture per importo esatto
            fattura = await db.invoices.find_one({
                **QUERY_FATTURA_NON_PAGATA,
                "$or": [
                    {"total_amount": {"$gte": importo * 0.99, "$lte": importo * 1.01}},
                    {"importo_totale": {"$gte": importo * 0.99, "$lte": importo * 1.01}}
                ]
            }, {"_id": 0, "id": 1, "supplier_name": 1})

            if fattura:
                await db.estratto_conto_movimenti.update_one(
                    {"id": mov["id"]},
                    {"$set": {
                        "riconciliato": True,
                        "fattura_id": fattura["id"],
                        "tipo_riconciliazione": "auto_importo",
                        "data_riconciliazione": datetime.now(timezone.utc).isoformat()
                    }}
                )
                pagato_fields = set_fattura_pagata({"movimento_bancario_id": mov["id"]})

                # Crea (idempotente) il movimento in Prima Nota Banca e propaga
                # FATTURA_PAGATA — senza questo la fattura risulta pagata da
                # questo motore "smart" ma non compare mai in Prima Nota Banca
                # né chiude la partita aperta collegata (stesso gap già chiuso
                # nel motore canonico da _applica_pagamento_banca() in
                # riconciliazione_bancaria.py, vedi memoria/moduli/RICONCILIAZIONE.md).
                try:
                    from app.routers.prima_nota_module.sync import registra_pagamento_fattura
                    pn = await registra_pagamento_fattura(fattura, "banca")
                    if pn.get("banca"):
                        pagato_fields["prima_nota_id"] = pn["banca"]
                        pagato_fields["prima_nota_tipo"] = "banca"
                        pagato_fields["prima_nota_banca_id"] = pn["banca"]
                except Exception:
                    logger.exception(f"Errore registrazione prima nota banca per fattura {fattura['id']}")

                await db.invoices.update_one(
                    {"id": fattura["id"]},
                    {"$set": pagato_fields}
                )

                try:
                    from app.services.event_bus import propagate_event, EventTypes
                    await propagate_event(EventTypes.FATTURA_PAGATA, {
                        "fattura_id": fattura["id"],
                        "importo": importo,
                        "metodo_pagamento": "banca",
                        "data_pagamento": pagato_fields["data_pagamento"],
                    }, db, source_module="riconciliazione_smart_auto")
                except Exception:
                    logger.exception(f"Errore propagazione FATTURA_PAGATA per {fattura['id']}")

                riconciliati += 1
                match_found = True
            
            if not match_found and "I24" in descrizione:
                # Match F24
                f24 = await db.f24_commercialista.find_one({
                    "importo_totale": {"$gte": importo * 0.99, "$lte": importo * 1.01}
                }, {"_id": 0, "id": 1})
                
                if f24:
                    await db.estratto_conto_movimenti.update_one(
                        {"id": mov["id"]},
                        {"$set": {
                            "riconciliato": True,
                            "f24_id": f24["id"],
                            "tipo_riconciliazione": "auto_f24",
                            "data_riconciliazione": datetime.now(timezone.utc).isoformat()
                        }}
                    )
                    riconciliati += 1
                    
        except Exception as e:
            errori.append({"movimento_id": mov.get("id"), "error": str(e)})
    
    return {
        "success": True,
        "riconciliati": riconciliati,
        "analizzati": len(movimenti),
        "errori": errori[:10]
    }


async def riconcilia_manuale(request: RiconciliaManuale) -> Dict[str, Any]:
    """Riconciliazione manuale movimento con entità."""
    db = Database.get_db()

    movimento = await db.estratto_conto_movimenti.find_one({"id": request.movimento_id})
    if not movimento:
        raise HTTPException(status_code=404, detail="Movimento non trovato")

    entita_id = request.associazioni[0].get("id") if request.associazioni else None
    # "fattura_sdd" è il sotto-tipo prodotto dall'analizzatore per gli SDD con
    # match su combinazione fatture: va saldato come una fattura normale,
    # altrimenti il movimento risulta riconciliato ma la fattura resta "da
    # pagare" ovunque nel resto del gestionale.
    tipo_operazione = "fattura" if request.tipo == "fattura_sdd" else request.tipo

    update_fields = {
        "riconciliato": True,
        "tipo_riconciliazione": "manuale",
        "data_riconciliazione": datetime.now(timezone.utc).isoformat(),
        "note_riconciliazione": request.note
    }

    if tipo_operazione == "fattura" and entita_id:
        fattura = await db.invoices.find_one({"id": entita_id})
        if not fattura:
            raise HTTPException(status_code=404, detail="Fattura non trovata")

        update_fields["fattura_id"] = entita_id
        pagato_fields = set_fattura_pagata({"movimento_bancario_id": request.movimento_id})

        # Crea (idempotente) il movimento in Prima Nota Banca — senza questo
        # la fattura risulta pagata ma non compare mai in Prima Nota Banca,
        # stesso gap già chiuso nel motore canonico da _applica_pagamento_banca()
        # in riconciliazione_bancaria.py.
        try:
            from app.routers.prima_nota_module.sync import registra_pagamento_fattura
            pn = await registra_pagamento_fattura(fattura, "banca")
            if pn.get("banca"):
                pagato_fields["prima_nota_id"] = pn["banca"]
                pagato_fields["prima_nota_tipo"] = "banca"
                pagato_fields["prima_nota_banca_id"] = pn["banca"]
        except Exception:
            logger.exception(f"Errore registrazione prima nota banca per fattura {entita_id}")

        await db.invoices.update_one(
            {"id": entita_id},
            {"$set": pagato_fields}
        )

        # Propaga il pagamento: senza questo evento la partita aperta
        # collegata (scadenziario) resta "aperta" per sempre, perché la
        # conferma manuale non passa dal matching automatico che emette
        # MATCH_CONFERMATO — vedi commento in on_fattura_pagata_risolvi.
        try:
            from app.services.event_bus import propagate_event, EventTypes
            await propagate_event(EventTypes.FATTURA_PAGATA, {
                "fattura_id": entita_id,
                "importo": movimento.get("importo"),
                "metodo_pagamento": fattura.get("metodo_pagamento"),
                "data_pagamento": update_fields["data_riconciliazione"],
            }, db, source_module="riconciliazione_smart_manuale")
        except Exception:
            logger.exception(f"Errore propagazione FATTURA_PAGATA per {entita_id}")

    elif tipo_operazione == "stipendio" and entita_id:
        update_fields["stipendio_id"] = entita_id

    elif tipo_operazione == "f24" and entita_id:
        update_fields["f24_id"] = entita_id

    await db.estratto_conto_movimenti.update_one(
        {"id": request.movimento_id},
        {"$set": update_fields}
    )

    return {"success": True, "movimento_id": request.movimento_id, "tipo": tipo_operazione}


async def cerca_fatture_per_associazione(
    importo: Optional[float] = None,
    fornitore: Optional[str] = None,
    data: Optional[str] = None,
    limit: int = 20
) -> Dict[str, Any]:
    """Cerca fatture per associazione manuale."""
    db = Database.get_db()
    
    query = dict(QUERY_FATTURA_NON_PAGATA)

    if importo:
        tolleranza = importo * 0.05
        query["$or"] = [
            {"total_amount": {"$gte": importo - tolleranza, "$lte": importo + tolleranza}},
            {"importo_totale": {"$gte": importo - tolleranza, "$lte": importo + tolleranza}}
        ]
    
    if fornitore:
        query["$or"] = query.get("$or", []) + [
            {"supplier_name": {"$regex": fornitore, "$options": "i"}},
            {"cedente_denominazione": {"$regex": fornitore, "$options": "i"}}
        ]
    
    fatture = await db.invoices.find(query, {"_id": 0}).sort("invoice_date", -1).limit(limit).to_list(limit)
    
    return {"fatture": fatture, "totale": len(fatture)}


async def cerca_stipendi_per_associazione(
    importo: Optional[float] = None,
    dipendente: Optional[str] = None,
    limit: int = 20
) -> Dict[str, Any]:
    """Cerca stipendi per associazione manuale."""
    db = Database.get_db()
    
    query = {"riconciliato": {"$ne": True}}
    
    if importo:
        tolleranza = importo * 0.05
        query["importo"] = {"$gte": importo - tolleranza, "$lte": importo + tolleranza}
    
    if dipendente:
        query["$or"] = [
            {"nome_dipendente": {"$regex": dipendente, "$options": "i"}},
            {"dipendente": {"$regex": dipendente, "$options": "i"}}
        ]
    
    stipendi = await db.prima_nota_salari.find(query, {"_id": 0}).sort("data", -1).limit(limit).to_list(limit)
    
    return {"stipendi": stipendi, "totale": len(stipendi)}


async def cerca_f24_per_associazione(
    importo: Optional[float] = None,
    data: Optional[str] = None,
    limit: int = 20
) -> Dict[str, Any]:
    """Cerca F24 per associazione manuale."""
    db = Database.get_db()

    query = {"riconciliato": {"$ne": True}}

    if importo:
        tolleranza = importo * 0.05
        query["importo_totale"] = {"$gte": importo - tolleranza, "$lte": importo + tolleranza}

    if data:
        query["data_scadenza"] = {"$regex": f"^{data[:7]}"}

    f24_list = await db.f24_commercialista.find(query, {"_id": 0}).sort("data_scadenza", -1).limit(limit).to_list(limit)

    return {"f24": f24_list, "totale": len(f24_list)}


async def conferma_f24_batch(request: ConfermaBatchRequest) -> Dict[str, Any]:
    """Conferma manuale di uno o più F24 pendenti con metodo di pagamento.

    Sostituisce la vecchia chiamata a /api/riconciliazione-intelligente/
    conferma-multipla, che si aspettava un payload di fatture e falliva
    SEMPRE con 400 sui F24 inviati da RiconciliazioneUnificata.jsx.
    Scrive sulla stessa collection letta da cerca_f24_per_associazione,
    così l'F24 confermato sparisce dalla lista dei pendenti.
    """
    db = Database.get_db()

    confermati = 0
    errori = []
    now = datetime.now(timezone.utc).isoformat()

    for op in request.operazioni:
        f24_id = op.get("operazione_id") or op.get("f24_id")
        if not f24_id:
            errori.append({"operazione": op, "errore": "operazione_id mancante"})
            continue
        result = await db.f24_commercialista.update_one(
            {"id": f24_id},
            {"$set": {
                "riconciliato": True,
                "status": "pagato",
                "pagato_manualmente": True,
                "metodo_pagamento": op.get("metodo_pagamento") or "banca",
                "tipo_riconciliazione": "manuale",
                "data_riconciliazione": now,
                "updated_at": now,
            }}
        )
        if result.matched_count == 0:
            errori.append({"operazione": op, "errore": f"F24 {f24_id} non trovato"})
        else:
            confermati += 1

    return {
        "success": len(errori) == 0,
        "confermati": confermati,
        "errori": errori,
    }
