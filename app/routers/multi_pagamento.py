"""
Multi-Pagamento Fatture — Ceraldi ERP
=======================================
Gestisce pagamenti multipli per una singola fattura:
- Una fattura può essere pagata con N metodi (contanti + assegno + bonifico)
- Un assegno può coprire N fatture dello stesso fornitore
- Lo stato fattura è calcolato: somma pagamenti vs totale

Stato fattura:
- non_pagata: nessun pagamento registrato
- parzialmente_pagata: somma pagamenti < totale
- pagata: somma pagamenti >= totale
- eccedenza: somma pagamenti > totale (acconto o errore)
"""
import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, HTTPException, Query, Body
from pymongo.errors import DuplicateKeyError
from app.database import Database
from app.utils.error_handler import handle_errors

logger = logging.getLogger(__name__)
router = APIRouter()


def chiave_idempotenza_pagamento(
    fattura_id: str, importo: float, data_pag: str, metodo: str,
    assegno_numero: str = "", esplicita: Optional[str] = None,
) -> str:
    """Chiave stabile di un pagamento. Se il client fornisce una chiave esplicita
    la si usa; altrimenti si deriva dai dati naturali (fattura+importo+data+metodo
    +assegno). Serve a rendere `registra_pagamento` IDEMPOTENTE: due submit uguali
    non creano due movimenti Prima Nota. Vedi P0.9."""
    if esplicita:
        return str(esplicita)
    base = f"{fattura_id}|{round(float(importo or 0), 2)}|{data_pag}|{metodo}|{assegno_numero}"
    return "pag_" + hashlib.sha256(base.encode("utf-8")).hexdigest()[:24]


async def _ricalcola_stato_fattura(db, fattura_id: str) -> Dict[str, Any]:
    """Ricalcola lo stato di pagamento di una fattura dalla somma dei pagamenti."""
    fattura = await db["invoices"].find_one({"id": fattura_id}, {"_id": 0, "total_amount": 1})
    if not fattura:
        return {"stato": "non_trovata"}
    
    totale = float(fattura.get("total_amount", 0))
    
    pagamenti = await db["pagamenti"].find(
        {"fattura_id": fattura_id},
        {"_id": 0, "importo": 1}
    ).to_list(100)
    
    somma_pagamenti = sum(float(p.get("importo", 0)) for p in pagamenti)
    residuo = round(totale - somma_pagamenti, 2)
    
    if somma_pagamenti <= 0:
        stato = "non_pagata"
    elif residuo > 0.05:
        stato = "parzialmente_pagata"
    elif residuo < -0.05:
        stato = "eccedenza"
    else:
        stato = "pagata"
    
    await db["invoices"].update_one(
        {"id": fattura_id},
        {"$set": {
            "stato_pagamento": stato,
            "totale_pagato": round(somma_pagamenti, 2),
            "residuo_da_pagare": max(0, residuo),
            "num_pagamenti": len(pagamenti),
        }}
    )
    
    return {"stato": stato, "totale": totale, "pagato": somma_pagamenti, "residuo": residuo, "num_pagamenti": len(pagamenti)}


@router.get("/fattura/{fattura_id}")
@handle_errors
async def get_pagamenti_fattura(fattura_id: str) -> Dict[str, Any]:
    """Lista tutti i pagamenti di una fattura (multi-pagamento)."""
    db = Database.get_db()
    
    fattura = await db["invoices"].find_one(
        {"id": fattura_id},
        {"_id": 0, "id": 1, "invoice_number": 1, "supplier_name": 1, "total_amount": 1, "stato_pagamento": 1}
    )
    if not fattura:
        raise HTTPException(status_code=404, detail="Fattura non trovata")
    
    pagamenti = await db["pagamenti"].find(
        {"fattura_id": fattura_id},
        {"_id": 0}
    ).sort("data", -1).to_list(100)
    
    totale_fattura = float(fattura.get("total_amount", 0))
    totale_pagato = sum(float(p.get("importo", 0)) for p in pagamenti)
    
    return {
        "fattura": fattura,
        "pagamenti": pagamenti,
        "totale_fattura": totale_fattura,
        "totale_pagato": round(totale_pagato, 2),
        "residuo": round(totale_fattura - totale_pagato, 2),
        "stato": fattura.get("stato_pagamento", "non_pagata"),
        "completamente_pagata": totale_pagato >= totale_fattura - 0.05,
    }


@router.post("/registra")
@handle_errors
async def registra_pagamento(data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """
    Registra un pagamento (anche parziale) per una fattura.
    
    Body:
    {
        "fattura_id": "uuid",
        "importo": 500.00,
        "metodo": "contanti|assegno|bonifico|carta|sepa",
        "data": "2026-04-11",
        "assegno_numero": "0208770770" (opzionale),
        "note": "Acconto" (opzionale)
    }
    """
    db = Database.get_db()
    
    fattura_id = data.get("fattura_id")
    importo = float(data.get("importo", 0))
    metodo = data.get("metodo", "contanti")
    data_pag = data.get("data", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    
    if importo <= 0:
        raise HTTPException(status_code=400, detail="Importo deve essere > 0")
    
    fattura = await db["invoices"].find_one({"id": fattura_id}, {"_id": 0})
    if not fattura:
        raise HTTPException(status_code=404, detail="Fattura non trovata")

    # Idempotenza: se lo stesso pagamento è già stato registrato (stesso submit),
    # NON crearne un altro né duplicare il movimento Prima Nota. Vedi P0.9.
    idem = chiave_idempotenza_pagamento(
        fattura_id, importo, data_pag, metodo,
        assegno_numero=data.get("assegno_numero", ""),
        esplicita=data.get("idempotency_key"),
    )
    esistente = await db["pagamenti"].find_one({"idempotency_key": idem}, {"_id": 0})
    if esistente:
        stato = await _ricalcola_stato_fattura(db, fattura_id)
        return {"success": True, "idempotente": True, "pagamento": esistente, "stato_fattura": stato}

    # Crea il pagamento
    pag_id = str(uuid.uuid4())
    pagamento = {
        "id": pag_id,
        "idempotency_key": idem,
        "fattura_id": fattura_id,
        "fattura_numero": fattura.get("invoice_number", ""),
        "fornitore": fattura.get("supplier_name", ""),
        "fornitore_piva": fattura.get("supplier_vat", ""),
        "importo": importo,
        "data": data_pag,
        "metodo": metodo,
        "assegno_id": data.get("assegno_id"),
        "assegno_numero": data.get("assegno_numero", ""),
        "note": data.get("note", ""),
        "prima_nota_id": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        await db["pagamenti"].insert_one(pagamento)
    except DuplicateKeyError:
        # Race: un submit concorrente identico ha già inserito il pagamento
        # (indice unique su idempotency_key). Rispondi idempotente, non 500.
        esistente = await db["pagamenti"].find_one({"idempotency_key": idem}, {"_id": 0})
        stato = await _ricalcola_stato_fattura(db, fattura_id)
        return {"success": True, "idempotente": True, "pagamento": esistente, "stato_fattura": stato}

    # Registra in Prima Nota
    pn_collection = "prima_nota_cassa" if metodo in ["contanti", "cassa", "carta"] else "prima_nota_banca"
    pn_tipo = "cassa" if metodo in ["contanti", "cassa", "carta"] else "banca"

    # Nota di credito (TD04/TD08) NON è un pagamento a fornitore in uscita:
    # stessa regola già applicata in prima_nota_module/sync.py (bug
    # segnalato dall'utente 14/07/2026, qui era hardcoded "uscita"/"Fatture").
    from app.routers.prima_nota_module.sync import costruisci_campi_movimento_fattura

    pn_id = str(uuid.uuid4())
    await db[pn_collection].insert_one({
        "id": pn_id,
        "data": data_pag,
        **costruisci_campi_movimento_fattura(fattura, importo, lunghezza_fornitore=25, suffisso=f"({metodo})"),
        "riferimento": f"PAG-{pag_id}",
        "fattura_id": fattura_id,
        "pagamento_id": pag_id,
        "source": "multi_pagamento",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    
    # Aggiorna il pagamento con il link prima nota
    await db["pagamenti"].update_one(
        {"id": pag_id},
        {"$set": {"prima_nota_id": pn_id, "prima_nota_tipo": pn_tipo}}
    )
    
    # Se assegno, collega anche alla collection assegni
    if metodo == "assegno" and data.get("assegno_numero"):
        await db["assegni"].update_one(
            {"numero": data["assegno_numero"]},
            {"$addToSet": {"fatture_associate": fattura_id},
             "$set": {"beneficiario": fattura.get("supplier_name",""), "beneficiario_piva": fattura.get("supplier_vat","")}}
        )
    
    # Ricalcola stato fattura
    stato = await _ricalcola_stato_fattura(db, fattura_id)
    
    return {
        "success": True,
        "pagamento_id": pag_id,
        "importo": importo,
        "metodo": metodo,
        "stato_fattura": stato,
    }


@router.post("/assegno-multi-fatture")
@handle_errors
async def assegno_copre_piu_fatture(data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """
    Un singolo assegno paga N fatture dello stesso fornitore.
    
    Body:
    {
        "assegno_numero": "0208770769",
        "fatture": [
            {"fattura_id": "uuid1", "importo": 1567.93},
            {"fattura_id": "uuid2", "importo": 997.97},
        ]
    }
    """
    db = Database.get_db()
    
    assegno_numero = data.get("assegno_numero", "")
    fatture_list = data.get("fatture", [])
    
    if not fatture_list:
        raise HTTPException(status_code=400, detail="Lista fatture vuota")
    
    # Trova assegno
    assegno = await db["assegni"].find_one({"numero": assegno_numero})
    assegno_id = assegno["id"] if assegno else None
    
    risultati = []
    for f in fatture_list:
        fatt_id = f.get("fattura_id")
        importo = float(f.get("importo", 0))
        
        # Chiamata diretta con dict: passare Body(**{...}) creava un FieldInfo
        # e ogni data.get() dentro registra_pagamento crashava (endpoint mai
        # funzionato — bug #2 audit memoria/endpoints/README.md).
        result = await registra_pagamento({
            "fattura_id": fatt_id,
            "importo": importo,
            "metodo": "assegno",
            "data": assegno.get("data_incasso", "") if assegno else "",
            "assegno_id": assegno_id,
            "assegno_numero": assegno_numero,
            "note": f"Assegno N.{assegno_numero} (multi-fattura)",
        })
        risultati.append(result)
    
    return {"success": True, "assegno": assegno_numero, "fatture_pagate": len(risultati), "dettagli": risultati}


@router.post("/fattura-multi-metodo")
@handle_errors
async def fattura_pagata_multi_metodo(data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """
    Una fattura pagata con N metodi diversi.
    
    Body:
    {
        "fattura_id": "uuid",
        "pagamenti": [
            {"importo": 200, "metodo": "contanti", "data": "2026-03-20"},
            {"importo": 619.05, "metodo": "assegno", "data": "2026-03-23", "assegno_numero": "0208770770"},
        ]
    }
    """
    db = Database.get_db()
    
    fattura_id = data.get("fattura_id")
    pagamenti_list = data.get("pagamenti", [])
    
    if not pagamenti_list:
        raise HTTPException(status_code=400, detail="Lista pagamenti vuota")
    
    risultati = []
    for p in pagamenti_list:
        # Dict diretto, non Body(**{...}): vedi commento in assegno_copre_piu_fatture.
        result = await registra_pagamento({
            "fattura_id": fattura_id,
            "importo": p.get("importo", 0),
            "metodo": p.get("metodo", "contanti"),
            "data": p.get("data", ""),
            "assegno_numero": p.get("assegno_numero", ""),
            "note": p.get("note", ""),
        })
        risultati.append(result)
    
    return {"success": True, "fattura_id": fattura_id, "pagamenti_registrati": len(risultati), "dettagli": risultati}


@router.get("/riepilogo-fornitore/{piva}")
@handle_errors
async def riepilogo_pagamenti_fornitore(piva: str) -> Dict[str, Any]:
    """Riepilogo pagamenti per fornitore: fatture, pagamenti, residui."""
    db = Database.get_db()
    
    fatture = await db["invoices"].find(
        {"supplier_vat": piva, "total_amount": {"$gt": 0}},
        {"_id": 0, "id": 1, "invoice_number": 1, "total_amount": 1, "stato_pagamento": 1, "totale_pagato": 1, "invoice_date": 1}
    ).sort("invoice_date", -1).to_list(500)
    
    pagamenti = await db["pagamenti"].find(
        {"fornitore_piva": piva},
        {"_id": 0}
    ).sort("data", -1).to_list(1000)
    
    tot_fatture = sum(float(f.get("total_amount", 0)) for f in fatture)
    tot_pagato = sum(float(p.get("importo", 0)) for p in pagamenti)
    
    return {
        "fornitore_piva": piva,
        "fatture": fatture,
        "pagamenti": pagamenti,
        "totale_fatturato": round(tot_fatture, 2),
        "totale_pagato": round(tot_pagato, 2),
        "residuo": round(tot_fatture - tot_pagato, 2),
        "num_fatture": len(fatture),
        "num_pagamenti": len(pagamenti),
    }


@router.delete("/{pagamento_id}")
@handle_errors
async def elimina_pagamento(pagamento_id: str) -> Dict[str, Any]:
    """Elimina un pagamento e ricalcola lo stato della fattura."""
    db = Database.get_db()
    
    pag = await db["pagamenti"].find_one({"id": pagamento_id})
    if not pag:
        raise HTTPException(status_code=404, detail="Pagamento non trovato")
    
    # Rimuovi dalla prima nota
    if pag.get("prima_nota_id"):
        for coll in ["prima_nota_cassa", "prima_nota_banca"]:
            await db[coll].delete_one({"id": pag["prima_nota_id"]})
    
    # Rimuovi pagamento
    await db["pagamenti"].delete_one({"id": pagamento_id})
    
    # Ricalcola stato fattura
    fattura_id = pag.get("fattura_id")
    if fattura_id:
        stato = await _ricalcola_stato_fattura(db, fattura_id)
        return {"success": True, "stato_fattura": stato}
    
    return {"success": True}
