"""
Operazioni Module - Riconciliazione Smart (banca veloce, analisi, associazioni).
"""
from fastapi import HTTPException
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from app.database import Database
from app.utils.parsing import safe_float
from .common import RiconciliaManuale, ConfermaBatchRequest, logger, QUERY_FATTURA_NON_PAGATA, set_fattura_pagata

# Le operazioni della carta Nexi (tipo="carta_credito") vivono nella STESSA
# collezione estratto_conto_movimenti (stesso schema del download automatico
# via email) ma non sono movimenti bancari da riconciliare uno per uno: la
# banca vede solo l'addebito mensile, le singole spese carta si riconciliano
# con lo statement Nexi (app/services/nexi_carta.py), non con una fattura.
# Senza questa esclusione le operazioni carta inquinavano la coda "da
# riconciliare" del tab Banca (bug 18/07/2026, segnalato dall'utente subito
# dopo il primo import di uno statement Nexi reale).
ESCLUDI_CARTA_CREDITO = {"tipo": {"$ne": "carta_credito"}}


async def banca_veloce(
    limit: int = 50,
    solo_non_riconciliati: bool = True,
    anno: Optional[int] = None
) -> Dict[str, Any]:
    """Endpoint veloce per tab Banca - movimenti + assegni + fatture da pagare."""
    db = Database.get_db()

    query = {**ESCLUDI_CARTA_CREDITO}
    if solo_non_riconciliati:
        query["riconciliato"] = {"$ne": True}
    if anno:
        query["data"] = {"$regex": f"^{anno}"}

    movimenti = await db.estratto_conto_movimenti.find(
        query,
        {"_id": 0}
    ).sort("data", -1).limit(limit).to_list(limit)

    assegni_query = {"stato": {"$nin": ["incassato", "annullato"]}, "confermato": {"$ne": True}}
    if anno:
        assegni_query["data_emissione"] = {"$regex": f"^{anno}"}
    assegni = await db.assegni.find(
        assegni_query,
        {"_id": 0}
    ).sort("data_emissione", -1).limit(50).to_list(50)

    fatture_query = {**QUERY_FATTURA_NON_PAGATA, "metodo_pagamento": {"$nin": [None, "", "contanti"]}}
    if anno:
        fatture_query["invoice_date"] = {"$regex": f"^{anno}"}
    fatture_da_pagare = await db.invoices.find(
        fatture_query,
        {"_id": 0, "id": 1, "invoice_number": 1, "invoice_date": 1, "supplier_name": 1, "total_amount": 1}
    ).sort("invoice_date", -1).limit(50).to_list(50)

    conta_movimenti_query = {**ESCLUDI_CARTA_CREDITO, **({"data": {"$regex": f"^{anno}"}} if anno else {})}
    tot_non_ric = await db.estratto_conto_movimenti.count_documents({**conta_movimenti_query, "riconciliato": {"$ne": True}})
    tot_ric = await db.estratto_conto_movimenti.count_documents({**conta_movimenti_query, "riconciliato": True})
    
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
    """Esegue i motori canonici; i casi ambigui restano aperti."""
    db = Database.get_db()

    errori = []
    try:
        from app.services.riconciliazione_bancaria import riconcilia_movimenti_banca
        banca = await riconcilia_movimenti_banca()
    except Exception as exc:
        logger.exception("Errore motore canonico banca")
        banca = {"totale_riconciliati": 0, "movimenti_analizzati": 0}
        errori.append({"motore": "banca", "error": str(exc)})

    try:
        from app.routers.paypal_statements import _auto_riconcilia
        paypal = await _auto_riconcilia(db, applica=True)
    except Exception as exc:
        logger.exception("Errore riconciliazione PayPal-banca")
        paypal = {"riconciliati": 0, "ambigui": 0}
        errori.append({"motore": "paypal", "error": str(exc)})

    try:
        from app.services.reconciliation_orchestrator import (
            riconcilia_documenti_e_pagamenti,
        )
        documenti = await riconcilia_documenti_e_pagamenti(db)
    except Exception as exc:
        logger.exception("Errore orchestratore documenti/pagamenti")
        documenti = {}
        errori.append({"motore": "documenti_pagamenti", "error": str(exc)})

    riconciliati_canonici = int(banca.get("totale_riconciliati") or 0) + int(
        paypal.get("riconciliati") or 0
    )
    riconciliati_documenti = (
        int((documenti.get("assegni_intenti") or {}).get("collegati") or 0)
        + int((documenti.get("assegni_auto") or {}).get("fatture_aggiornate") or 0)
        + int((documenti.get("bonifici_pdf") or {}).get("associati") or 0)
        + int((documenti.get("salari") or {}).get("bonifici_associati") or 0)
        + int((documenti.get("f24") or {}).get("movimenti_associati") or 0)
    )
    return {
        "success": not errori,
        "riconciliati": riconciliati_canonici + riconciliati_documenti,
        "analizzati": int(banca.get("movimenti_analizzati") or 0),
        "banca": banca,
        "paypal": paypal,
        "documenti_pagamenti": documenti,
        "errori": errori[:10],
    }


async def riconcilia_manuale(request: RiconciliaManuale) -> Dict[str, Any]:
    """Riconciliazione manuale movimento con entità."""
    db = Database.get_db()

    movimento = await db.estratto_conto_movimenti.find_one({"id": request.movimento_id})
    if not movimento:
        raise HTTPException(status_code=404, detail="Movimento non trovato")
    # Guard anti-doppio-match (P1-2, LOGICA §6): mai sovrascrivere una
    # riconciliazione già fatta — rifiuta con 409.
    if movimento.get("riconciliato"):
        raise HTTPException(status_code=409, detail="Movimento già riconciliato")

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
            pn = await registra_pagamento_fattura(
                fattura, "banca", movimento_bancario=movimento,
                source="riconciliazione_manuale",
            )
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
    
    query = {"riconciliato": {"$ne": True}, "ignorato": {"$ne": True}}

    if importo:
        tolleranza = importo * 0.05
        query["importo"] = {"$gte": importo - tolleranza, "$lte": importo + tolleranza}

    if dipendente:
        query["$or"] = [
            {"nome_dipendente": {"$regex": dipendente, "$options": "i"}},
            {"dipendente": {"$regex": dipendente, "$options": "i"}}
        ]
    
    stipendi = await db.prima_nota_salari.find(query, {"_id": 0}).sort("data", -1).limit(limit).to_list(limit)

    # Leggibilità (segnalazione utente 18/07/2026: "€0,00, non capisco se
    # sono bonifici o cedolini"): queste righe sono ATTESE DI PAGAMENTO
    # generate dai cedolini. importo = netto busta; se il netto non è stato
    # letto dal PDF lo si dice chiaramente; i bonifici già trovati in
    # estratto conto sono riportati. Le righe senza dipendente né importo
    # non potranno mai essere associate: escluse dalla lista.
    visibili = []
    for s in stipendi:
        nome = (s.get("dipendente") or s.get("dipendente_nome") or "").strip()
        busta = float(s.get("importo_busta") or s.get("importo") or 0)
        bonifici = float(s.get("importo_bonifico") or 0)
        if not nome and busta <= 0:
            continue  # riga inservibile (né nome né importo)
        s["importo"] = busta
        dettagli = []
        dettagli.append(f"busta € {busta:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                        if busta > 0 else "netto busta non letto dal PDF")
        if bonifici > 0:
            dettagli.append(f"bonifici trovati € {bonifici:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        s["descrizione"] = (f"Stipendio {nome} - {s.get('mese', 0):02d}/{s.get('anno', '')}"
                            f" · {' · '.join(dettagli)}")
        visibili.append(s)

    return {"stipendi": visibili, "totale": len(visibili)}


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

    f24_list = await db["f24_unificato"].find(query, {"_id": 0}).sort("data_scadenza", -1).limit(limit).to_list(limit)

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
        result = await db["f24_unificato"].update_one(
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
