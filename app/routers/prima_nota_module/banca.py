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


async def _arricchisci_riconciliazione(db, movimenti: list) -> None:
    """Aggiunge a ogni movimento fattura o trasferimento POS un campo
    'riconciliazione' con evidenza di un vero match con l'estratto conto.
    Senza questo, in Prima Nota Banca una fattura registrata (es.
    manualmente, o auto-confermata da metodo fornitore) è indistinguibile
    da una davvero riconciliata con l'estratto conto — segnalato
    dall'utente sul caso Leasys — e un trasferimento POS cassa→banca
    (source 'trasferimento_pos') è indistinguibile da un vero accredito
    bancario verificato — segnalato dall'utente sul caso "coerenza di
    trascrizione vs coerenza con l'estratto conto".

    L'evidenza vive in punti diversi a seconda del flusso che l'ha
    scritta (review Codex su PR #66):
    - riconciliazione_bancaria.py::_applica_pagamento_banca (flusso
      automatico) scrive SOLO sulla fattura: riconciliato_con_ec/
      riconciliato_automaticamente/match_score;
    - fatture_module/pagamento.py::riconcilia_fattura_con_estratto_conto
      (riconciliazione manuale) scrive fattura.riconciliato (non
      riconciliato_con_ec) e, se esiste, prima_nota_banca.riconciliato;
    - prima_nota_module/manutenzione.py (retro-collegamento) scrive SOLO
      sul movimento: prima_nota_banca.riconciliato + estratto_conto_id;
    - scritture_contabili.py::riconcilia_accredito_pos_ec (accrediti POS)
      scrive SOLO sul movimento 'trasferimento_pos': riconciliato +
      accreditato_ec.
    Quindi la verifica è un OR fra fattura e movimento, non solo fattura.

    fattura_id su un movimento può essere l'id reale o l'invoice_key
    (fallback storico in registra_pagamento_fattura): la query cerca
    entrambi.

    Una sola query batch su tutte le fatture coinvolte: niente N+1
    (pattern già segnalato come problema altrove nell'audit statico).
    """
    fattura_ids = list({m["fattura_id"] for m in movimenti if m.get("fattura_id")})
    fatture_by_key: Dict[str, Any] = {}
    if fattura_ids:
        fatture = await db[Collections.INVOICES].find(
            {"$or": [{"id": {"$in": fattura_ids}}, {"invoice_key": {"$in": fattura_ids}}]},
            {"_id": 0, "id": 1, "invoice_key": 1, "riconciliato": 1,
             "riconciliato_con_ec": 1, "riconciliato_automaticamente": 1, "match_score": 1},
        ).to_list(len(fattura_ids))
        for f in fatture:
            for chiave in (f.get("id"), f.get("invoice_key")):
                if chiave:
                    fatture_by_key[chiave] = f

    for m in movimenti:
        fid = m.get("fattura_id")
        is_pos_trasferimento = m.get("source") == "trasferimento_pos"
        if not fid and not is_pos_trasferimento:
            continue
        fattura = fatture_by_key.get(fid) if fid else None
        verificata_fattura = bool(fattura and (fattura.get("riconciliato_con_ec") or fattura.get("riconciliato")))
        verificata = verificata_fattura or bool(m.get("riconciliato"))
        m["riconciliazione"] = {
            "tipo": "pos_trasferimento" if is_pos_trasferimento else "fattura",
            "verificata": verificata,
            "automatica": bool(fattura and fattura.get("riconciliato_automaticamente")) if verificata_fattura else False,
            "match_score": fattura.get("match_score") if verificata_fattura else None,
            "accreditato_ec": round(float(m.get("accreditato_ec") or 0), 2) if is_pos_trasferimento and m.get("accreditato_ec") else None,
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
