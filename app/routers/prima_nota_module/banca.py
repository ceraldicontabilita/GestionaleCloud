"""
Prima Nota Module - Operazioni Prima Nota Banca.
CRUD e operazioni per movimenti bancari.
"""
from fastapi import HTTPException, Query, Body
from typing import Dict, Any, Optional
from datetime import datetime, timezone
import uuid

from app.database import Database, Collections
from .common import (
    COLLECTION_PRIMA_NOTA_BANCA, TIPO_MOVIMENTO, CATEGORIE_ESCLUSE, ESCLUSIONI_PRIMA_NOTA,
    calcola_saldo_anni_precedenti, aggrega_saldo_prima_nota
)


POS_SOURCES = {"trasferimento_pos", "corrispettivo_pos", "corrispettivi_sync"}
# 'corrispettivo_pos' e 'corrispettivi_sync' sono lo stesso tipo di riga
# (quota POS del corrispettivo XML in banca) per due percorsi di scrittura
# diversi — già trattati come equivalenti altrove nel codice (es.
# app/routers/invoices/corrispettivi_helpers.py li raggruppa nello stesso
# "$in"). 'corrispettivi_sync' è la fonte ATTUALMENTE attiva
# (app/routers/invoices/corrispettivi.py) e non è esclusa dalla vista
# Prima Nota Banca (common.py::SOURCES_ESCLUSE) — quindi va arricchita
# come le altre, altrimenti resta senza nessun badge (review Codex,
# 3° giro su PR #66). Oggi nessun flusso la marca riconciliata (nessun
# accreditato_ec / movimento_estratto_conto_id viene mai scritto per
# questa source): mostrerà sempre "Da verificare" finché non esiste una
# vera riconciliazione per questo percorso — corretto, non un difetto:
# riflette lo stato reale dei dati.


# Alias noti (4 giri di review Codex su PR #66) con cui i vari flussi di
# riconciliazione scrivono l'ID di un movimento reale di estratto conto sul
# movimento di Prima Nota: ogni flusso ha inventato il proprio nome campo,
# mai unificati. Presente uno qualunque di questi = prova reale (nessuno
# di questi flussi lo scrive mai in modo speculativo, solo a match confermato):
#   estratto_conto_id           — manutenzione.py (retro-collegamento)
#   movimento_bancario_id       — pagamento.py (riconciliazione manuale),
#                                  assegni.py sull'invoice
#   movimento_estratto_conto_id — email_monitor_service.py (POS Nexi legacy),
#                                  assegni.py sul movimento
#   movimento_banca_id          — dati_provvisori_service.py (conferma proposta)
CAMPI_EVIDENZA_MOVIMENTO = (
    "estratto_conto_id", "movimento_bancario_id",
    "movimento_estratto_conto_id", "movimento_banca_id",
)


def _evidenza_movimento(m: Dict[str, Any]):
    for campo in CAMPI_EVIDENZA_MOVIMENTO:
        val = m.get(campo)
        if val:
            return val
    return None


async def _arricchisci_riconciliazione(db, movimenti: list) -> None:
    """Aggiunge a ogni movimento fattura/POS/PayPal un campo
    'riconciliazione' con evidenza di un vero match con l'estratto conto
    (o, per PayPal, con una transazione reale). Senza questo, in Prima
    Nota Banca una fattura registrata (es. manualmente, o auto-confermata
    da metodo fornitore) è indistinguibile da una davvero riconciliata —
    segnalato dall'utente sul caso Leasys, ANCORA presente in banca il
    07/07 nonostante non risultasse pagata — e un trasferimento POS
    cassa→banca è indistinguibile da un vero accredito verificato —
    segnalato dall'utente sul caso "coerenza di trascrizione vs coerenza
    con l'estratto conto".

    REGOLA (2° giro di review Codex): il flag booleano 'riconciliato', da
    solo, NON è prova di nulla — app/routers/fatture_module/pagamento.py::
    aggiorna_metodi_pagamento_da_fornitori marca fattura.riconciliato=True
    SOLO perché il fornitore ha metodo di pagamento 'banca' in anagrafica,
    senza nessun riscontro con un movimento reale (probabile causa esatta
    del caso Leasys). Serve sempre un ID di collegamento a un movimento
    reale (vedi CAMPI_EVIDENZA_MOVIMENTO), non il flag da solo — ma la
    presenza dell'ID stesso (senza richiedere ANCHE 'riconciliato' booleano
    insieme) è già prova sufficiente: nessun flusso conosciuto scrive
    questi ID in modo speculativo (4° giro di review: dati_provvisori_service.py
    conferma la proposta con movimento_banca_id ma senza mai impostare
    'riconciliato' sul movimento — richiederlo insieme causava falsi "Da
    verificare" su collegamenti già reali).

    fattura_id su un movimento può essere l'id reale, l'invoice_key
    (fallback storico in registra_pagamento_fattura), oppure assente con
    solo `riferimento: "FATT-<id>"` (righe legacy, stessa convenzione già
    usata per la riparazione in manutenzione.py) — la query cerca tutte e
    tre le forme.

    Una sola query batch su tutte le fatture coinvolte: niente N+1
    (pattern già segnalato come problema altrove nell'audit statico).
    """
    for m in movimenti:
        if not m.get("fattura_id") and str(m.get("riferimento") or "").startswith("FATT-"):
            m["_fattura_id_derivato"] = m["riferimento"][len("FATT-"):]

    fattura_ids = list({
        m.get("fattura_id") or m.get("_fattura_id_derivato")
        for m in movimenti if m.get("fattura_id") or m.get("_fattura_id_derivato")
    })
    fatture_by_key: Dict[str, Any] = {}
    if fattura_ids:
        fatture = await db[Collections.INVOICES].find(
            {"$or": [{"id": {"$in": fattura_ids}}, {"invoice_key": {"$in": fattura_ids}}]},
            {"_id": 0, "id": 1, "invoice_key": 1, "riconciliato_con_ec": 1,
             "movimento_bancario_id": 1, "riconciliato_automaticamente": 1, "match_score": 1},
        ).to_list(len(fattura_ids))
        for f in fatture:
            for chiave in (f.get("id"), f.get("invoice_key")):
                if chiave:
                    fatture_by_key[chiave] = f

    for m in movimenti:
        fid = m.pop("_fattura_id_derivato", None) or m.get("fattura_id")
        source = m.get("source")
        is_pos = source in POS_SOURCES
        is_paypal = source == "riconciliazione_paypal"
        is_versamento = m.get("categoria") == "Versamento Banca" or source in {
            "versamento_cassa_in_attesa", "riconciliazione_ec_versamento",
        }
        if not fid and not is_pos and not is_paypal and not is_versamento:
            continue

        if is_versamento:
            m["riconciliazione"] = {
                "tipo": "versamento_contanti",
                "verificata": bool(_evidenza_movimento(m)),
                "automatica": bool(m.get("estratto_conto_id")),
                "match_score": None,
                "accreditato_ec": None,
            }
            continue

        if is_paypal:
            m["riconciliazione"] = {
                "tipo": "paypal",
                "verificata": bool(m.get("riconciliato") and m.get("paypal_transaction_id")),
                "automatica": False, "match_score": None, "accreditato_ec": None,
            }
            continue

        if is_pos:
            accreditato = round(float(m.get("accreditato_ec") or 0), 2)
            atteso = round(float(m.get("importo") or 0), 2)
            differenza = round(accreditato - atteso, 2)
            evidenza = bool(accreditato or _evidenza_movimento(m))
            # Un accredito trovato non basta a dichiarare il trasferimento
            # riconciliato: deve quadrare con il POS del giorno al centesimo.
            # Questo ricalcolo rende corretti anche i record storici che erano
            # stati marcati verdi pur avendo importi diversi.
            quadrato = evidenza and abs(differenza) <= 0.01
            m["riconciliazione"] = {
                "tipo": "pos_trasferimento",
                "verificata": quadrato,
                "automatica": False, "match_score": None,
                "accreditato_ec": accreditato if evidenza else None,
                "importo_atteso": atteso,
                "differenza_ec": differenza if evidenza else None,
                "accredito_trovato": evidenza,
            }
            continue

        fattura = fatture_by_key.get(fid)
        evidenza_fattura = bool(fattura and (fattura.get("riconciliato_con_ec") or fattura.get("movimento_bancario_id")))
        verificata = evidenza_fattura or bool(_evidenza_movimento(m))
        m["riconciliazione"] = {
            "tipo": "fattura",
            "verificata": verificata,
            "automatica": bool(fattura and fattura.get("riconciliato_automaticamente")) if evidenza_fattura else False,
            "match_score": fattura.get("match_score") if evidenza_fattura else None,
            "accreditato_ec": None,
        }


async def list_prima_nota_banca(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=10000),
    anno: Optional[int] = Query(None, description="Anno (es. 2024, 2025)"),
    data_da: Optional[str] = Query(None),
    data_a: Optional[str] = Query(None),
    tipo: Optional[str] = Query(None),
    categoria: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """Lista movimenti prima nota banca con saldo separato per anno."""
    db = Database.get_db()

    query = {
        "status": {"$nin": ["deleted", "archived"]},
        **ESCLUSIONI_PRIMA_NOTA,
    }

    if anno:
        # §6.4: query anno allineata a cassa.py (copre anche i doc con anno == "")
        query["$or"] = [
            {"anno": anno},
            {"anno": {"$in": [None, ""]}, "data": {"$gte": f"{anno}-01-01", "$lte": f"{anno}-12-31"}},
            {"anno": {"$exists": False}, "data": {"$gte": f"{anno}-01-01", "$lte": f"{anno}-12-31"}}
        ]
    
    if data_da:
        query.setdefault("data", {})["$gte"] = data_da
    if data_a:
        query.setdefault("data", {})["$lte"] = data_a
    if tipo:
        query["tipo"] = tipo
    if categoria:
        query["categoria"] = categoria
    
    movimenti = await db[COLLECTION_PRIMA_NOTA_BANCA].find(query, {"_id": 0}).sort("data", -1).skip(skip).limit(limit).to_list(limit)
    await _arricchisci_riconciliazione(db, movimenti)

    # §6.4: saldo tramite la funzione UNICA (segno/riporto/saldo finale uniformi)
    saldi = await aggrega_saldo_prima_nota(db, COLLECTION_PRIMA_NOTA_BANCA, query, anno)

    return {
        "movimenti": movimenti,
        "saldo": saldi["saldo"],
        "saldo_anno": saldi["saldo_anno"],
        "saldo_precedente": saldi["saldo_precedente"],
        "saldo_iniziale_manuale": saldi.get("saldo_iniziale_manuale", False),
        "totale_entrate": saldi["totale_entrate"],
        "totale_uscite": saldi["totale_uscite"],
        "count": len(movimenti),
        "anno": anno
    }


async def create_prima_nota_banca(data: Dict[str, Any] = Body(...)) -> Dict[str, str]:
    """Crea movimento prima nota banca."""
    db = Database.get_db()
    
    required = ["data", "tipo", "importo", "descrizione"]
    for field in required:
        if field not in data:
            raise HTTPException(status_code=400, detail=f"Campo obbligatorio mancante: {field}")
    
    if data["tipo"] not in TIPO_MOVIMENTO:
        raise HTTPException(status_code=400, detail="Tipo deve essere 'entrata' o 'uscita'")
    
    movimento = {
        "id": str(uuid.uuid4()),
        "data": data["data"],
        "tipo": data["tipo"],
        "importo": float(data["importo"]),
        "descrizione": data["descrizione"],
        "categoria": data.get("categoria", "Altro"),
        "riferimento": data.get("riferimento"),
        "fornitore_piva": data.get("fornitore_piva"),
        "fattura_id": data.get("fattura_id"),
        "iban": data.get("iban"),
        "conto_bancario": data.get("conto_bancario"),
        "note": data.get("note"),
        "source": data.get("source"),
        "pos_details": data.get("pos_details"),
        "numero_assegno": data.get("numero_assegno") or data.get("assegno_numero"),
        "assegno_numero": data.get("numero_assegno") or data.get("assegno_numero"),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db[COLLECTION_PRIMA_NOTA_BANCA].insert_one(movimento.copy())

    # Stesso bug/fix di cassa.py::create_prima_nota_cassa (15/07/2026): un'uscita
    # banca collegata a una fattura deve marcarla pagata, altrimenti resta
    # candidabile per un secondo pagamento reale via riconciliazione bancaria
    # o "Paga in Cassa" — doppio conteggio della stessa spesa.
    if data["tipo"] == "uscita" and data.get("fattura_id"):
        await db[Collections.INVOICES].update_one(
            {"id": data["fattura_id"]},
            {"$set": {
                "pagato": True,
                "stato_pagamento": "pagata",
                "data_pagamento": data["data"],
                "metodo_pagamento": "banca",
                "prima_nota_banca_id": movimento["id"],
            }}
        )

    return {"message": "Movimento banca creato", "id": movimento["id"]}


async def update_prima_nota_banca(
    movimento_id: str,
    data: Dict[str, Any] = Body(...)
) -> Dict[str, str]:
    """Modifica movimento prima nota banca."""
    db = Database.get_db()
    
    update_data = {"updated_at": datetime.now(timezone.utc).isoformat()}
    
    for field in ["data", "tipo", "importo", "descrizione", "categoria", "riferimento", "note", "fornitore", "ragione_sociale"]:
        if field in data:
            update_data[field] = float(data[field]) if field == "importo" else data[field]

    if "numero_assegno" in data or "assegno_numero" in data:
        numero_assegno = (data.get("numero_assegno") or data.get("assegno_numero") or "").strip()
        update_data["numero_assegno"] = numero_assegno or None
        update_data["assegno_numero"] = numero_assegno or None
    
    result = await db[COLLECTION_PRIMA_NOTA_BANCA].update_one(
        {"id": movimento_id},
        {"$set": update_data}
    )

    if result.matched_count == 0:
        # La vista Banca è un mix di prima_nota_banca + estratto_conto_movimenti:
        # i movimenti dell'estratto conto vanno aggiornati nella loro collection
        result_ec = await db["estratto_conto_movimenti"].update_one(
            {"id": movimento_id},
            {"$set": update_data}
        )
        if result_ec.matched_count == 0:
            raise HTTPException(status_code=404, detail="Movimento non trovato")

    return {"message": "Movimento aggiornato", "id": movimento_id}


async def delete_movimento_banca(
    movimento_id: str,
    force: bool = Query(False, description="Forza eliminazione")
) -> Dict[str, Any]:
    """Elimina un singolo movimento banca con validazione."""
    from app.services.business_rules import BusinessRules, EntityStatus
    
    db = Database.get_db()
    
    mov = await db[COLLECTION_PRIMA_NOTA_BANCA].find_one({"id": movimento_id})
    if not mov:
        # Movimento dell'estratto conto mostrato nella vista Banca: la riga
        # originale è il documento bancario, IMMUTABILE — non si elimina mai
        # (audit 16/07/2026, prima qui c'era una delete_one). Viene solo
        # esclusa dalla vista Banca, recuperabile in qualunque momento.
        mov_ec = await db["estratto_conto_movimenti"].find_one({"id": movimento_id})
        if not mov_ec:
            raise HTTPException(status_code=404, detail="Movimento non trovato")
        await db["estratto_conto_movimenti"].update_one(
            {"id": movimento_id},
            {"$set": {
                "escluso_da_vista_banca": True,
                "escluso_at": datetime.now(timezone.utc).isoformat(),
            }},
        )
        return {"success": True,
                "message": "Movimento estratto conto escluso dalla vista (l'originale resta nell'estratto conto)"}

    validation = BusinessRules.can_delete_movement(mov)

    if not validation.is_valid:
        raise HTTPException(
            status_code=400,
            detail={"message": "Eliminazione non consentita", "errors": validation.errors}
        )

    if validation.warnings and not force:
        return {
            "status": "warning",
            "warnings": validation.warnings,
            "require_force": True
        }

    await db[COLLECTION_PRIMA_NOTA_BANCA].update_one(
        {"id": movimento_id},
        {"$set": {
            "entity_status": EntityStatus.DELETED.value,
            "status": "deleted",
            "deleted_at": datetime.now(timezone.utc).isoformat()
        }}
    )

    # Se il movimento saldava una fattura, la fattura torna "da pagare"
    # (niente prima_nota_id orfano / stato pagata fantasma)
    if mov.get("fattura_id"):
        await db["invoices"].update_one(
            {"id": mov["fattura_id"], "prima_nota_id": movimento_id},
            {"$set": {"stato_pagamento": "", "pagato": False, "paid": False},
             "$unset": {"prima_nota_id": "", "prima_nota_tipo": "",
                        "prima_nota_banca_id": "", "data_pagamento": ""}}
        )

    return {"success": True, "message": "Movimento eliminato (archiviato)"}


async def delete_all_prima_nota_banca() -> Dict[str, Any]:
    """Elimina TUTTI i movimenti dalla prima nota banca."""
    db = Database.get_db()
    result = await db[COLLECTION_PRIMA_NOTA_BANCA].delete_many({})
    return {"message": f"Eliminati {result.deleted_count} movimenti dalla banca"}


async def delete_banca_by_source(source: str) -> Dict[str, Any]:
    """Elimina movimenti banca per source."""
    db = Database.get_db()
    result = await db[COLLECTION_PRIMA_NOTA_BANCA].delete_many({"source": source})
    return {"message": f"Eliminati {result.deleted_count} movimenti con source={source}"}


async def get_fattura_allegata_banca(movimento_id: str) -> Dict[str, Any]:
    """Recupera la fattura allegata a un movimento banca."""
    db = Database.get_db()
    
    mov = await db[COLLECTION_PRIMA_NOTA_BANCA].find_one({"id": movimento_id}, {"_id": 0})
    if not mov:
        raise HTTPException(status_code=404, detail="Movimento non trovato")
    
    fattura_id = mov.get("fattura_id")
    if not fattura_id:
        return {"movimento_id": movimento_id, "fattura": None, "message": "Nessuna fattura collegata"}
    
    fattura = await db["invoices"].find_one(
        {"$or": [{"id": fattura_id}, {"invoice_key": fattura_id}]},
        {"_id": 0}
    )
    
    return {
        "movimento_id": movimento_id,
        "fattura": fattura,
        "message": "Fattura trovata" if fattura else "Fattura non trovata nel DB"
    }
