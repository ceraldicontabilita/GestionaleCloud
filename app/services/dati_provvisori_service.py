"""
Dati Provvisori — Ceraldi ERP
===============================
Sistema di staging: il gestionale propone abbinamenti fattura↔banca,
l'utente conferma prima dell'inserimento definitivo in Prima Nota.
"""
import logging
import re
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

COLLECTION = "dati_provvisori"


async def genera_proposte_pagamento(db, anno: int = 2026) -> Dict[str, Any]:
    """
    Cerca fatture bonifico non pagate e propone abbinamenti con movimenti bancari.
    Strategia match:
    1. Importo esatto + nome fornitore nella descrizione
    2. Importo esatto + P.IVA nella descrizione  
    3. Importo esatto + data vicina (±30gg dalla fattura)
    """
    stats = {"fatture_analizzate": 0, "proposte_create": 0, "gia_proposte": 0, "no_match": 0}
    
    # Fatture bonifico non pagate
    fatture = await db["invoices"].find(
        {
            "payment_method": {"$in": ["bonifico", "sepa", "rid", "domiciliazione", ""]},
            "$or": [{"stato_pagamento": {"$ne": "pagata"}}, {"stato_pagamento": None}],
            "total_amount": {"$gt": 0},
            "invoice_date": {"$regex": f"^{anno}"}
        },
        {"_id": 0}
    ).to_list(500)
    
    stats["fatture_analizzate"] = len(fatture)
    
    # Proposte già esistenti (dedup)
    existing_refs = set()
    async for p in db[COLLECTION].find({"tipo": "pagamento_fattura"}, {"_id": 0, "fattura_id": 1}):
        existing_refs.add(p.get("fattura_id"))
    
    # Movimenti banca uscita dell'anno
    movimenti = await db["estratto_conto_movimenti"].find(
        {"tipo": "uscita", "data_contabile": {"$regex": f"/{anno}$"}},
        {"_id": 0}
    ).to_list(10000)
    
    # Index movimenti per importo (per match veloce)
    mov_by_importo = {}
    for m in movimenti:
        imp = float(m.get("importo", 0))
        if imp not in mov_by_importo:
            mov_by_importo[imp] = []
        mov_by_importo[imp].append(m)
    
    movimenti_usati = set()
    
    for fatt in fatture:
        if fatt["id"] in existing_refs:
            stats["gia_proposte"] += 1
            continue
        
        importo = float(fatt.get("total_amount", 0))
        nome = (fatt.get("supplier_name") or "").upper()
        piva = fatt.get("supplier_vat", "")
        data_fatt = fatt.get("invoice_date", "")
        
        # Cerca match per importo esatto
        candidati = mov_by_importo.get(importo, [])
        
        best_match = None
        best_score = 0
        
        for mov in candidati:
            if mov.get("id") in movimenti_usati:
                continue
            
            desc = (mov.get("descrizione") or "").upper()
            score = 0
            
            # Score per nome fornitore
            nome_parts = nome.split()[:2]
            for part in nome_parts:
                if len(part) > 3 and part in desc:
                    score += 30
            
            # Score per P.IVA
            if piva and piva in desc:
                score += 50
            
            # Score per keyword VS.DISP/BONIFICO
            if "VS.DISP" in desc or "BONIFICO" in desc:
                score += 10
            
            # Score per data vicina
            if data_fatt:
                try:
                    data_mov = mov.get("data_contabile", "")
                    if "/" in data_mov:
                        parts = data_mov.split("/")
                        mov_date = datetime(int(parts[2]), int(parts[1]), int(parts[0]))
                    elif "-" in data_mov:
                        mov_date = datetime.strptime(data_mov[:10], "%Y-%m-%d")
                    else:
                        mov_date = None
                    
                    if mov_date:
                        fatt_date = datetime.strptime(data_fatt[:10], "%Y-%m-%d")
                        diff_days = abs((mov_date - fatt_date).days)
                        if diff_days <= 7:
                            score += 20
                        elif diff_days <= 30:
                            score += 10
                        elif diff_days > 90:
                            score -= 20
                except Exception:
                    pass
            
            if score > best_score:
                best_score = score
                best_match = mov
        
        if best_match and best_score >= 10:
            # Crea proposta
            proposta = {
                "id": str(uuid.uuid4()),
                "tipo": "pagamento_fattura",
                "stato": "da_confermare",
                "confidence": min(best_score, 100),
                
                # Fattura
                "fattura_id": fatt["id"],
                "fattura_numero": fatt.get("invoice_number", ""),
                "fattura_data": data_fatt,
                "fattura_fornitore": fatt.get("supplier_name", ""),
                "fattura_piva": piva,
                "fattura_importo": importo,
                "fattura_metodo": fatt.get("payment_method", ""),
                
                # Movimento banca
                "movimento_id": best_match.get("id"),
                "movimento_data": best_match.get("data_contabile", ""),
                "movimento_importo": float(best_match.get("importo", 0)),
                "movimento_descrizione": (best_match.get("descrizione") or "")[:200],
                
                "destinazione": "prima_nota_banca",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            
            await db[COLLECTION].insert_one(proposta)
            movimenti_usati.add(best_match.get("id"))
            stats["proposte_create"] += 1
        else:
            stats["no_match"] += 1
    
    logger.info(f"[PROVVISORI] Proposte generate: {stats}")
    return stats


async def conferma_proposta(db, proposta_id: str) -> Dict[str, Any]:
    """
    Conferma una proposta: registra il pagamento in Prima Nota e aggiorna la fattura.
    """
    proposta = await db[COLLECTION].find_one({"id": proposta_id})
    if not proposta:
        return {"success": False, "error": "Proposta non trovata"}
    
    if proposta.get("stato") == "confermata":
        return {"success": True, "message": "Già confermata"}
    
    fatt_id = proposta.get("fattura_id")
    importo = proposta.get("fattura_importo", 0)
    fornitore = proposta.get("fattura_fornitore", "")
    numero = proposta.get("fattura_numero", "")
    data_mov = proposta.get("movimento_data", "")
    
    # Converti data DD/MM/YYYY → YYYY-MM-DD
    data_iso = data_mov
    if "/" in data_mov:
        parts = data_mov.split("/")
        if len(parts) == 3:
            data_iso = f"{parts[2]}-{parts[1]}-{parts[0]}"
    
    # Registra in Prima Nota Banca
    pn_id = str(uuid.uuid4())
    movimento = {
        "id": pn_id,
        "data": data_iso,
        "tipo": "uscita",
        "categoria": "Fatture",
        "descrizione": f"Fatt. {numero} - {fornitore[:30]}",
        "importo": importo,
        "riferimento": f"FATT-{fatt_id}",
        "fattura_id": fatt_id,
        "movimento_banca_id": proposta.get("movimento_id"),
        "source": "conferma_provvisori",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    
    await db["prima_nota_banca"].insert_one(movimento)
    
    # Aggiorna fattura
    await db["invoices"].update_one(
        {"id": fatt_id},
        {"$set": {
            "stato_pagamento": "pagata",
            "prima_nota_id": pn_id,
            "prima_nota_tipo": "banca",
            "data_pagamento": data_iso,
        }}
    )
    
    # Aggiorna proposta
    await db[COLLECTION].update_one(
        {"id": proposta_id},
        {"$set": {
            "stato": "confermata",
            "confermata_at": datetime.now(timezone.utc).isoformat(),
            "prima_nota_id": pn_id,
        }}
    )
    
    return {"success": True, "message": f"Pagamento confermato: {fornitore} €{importo}"}


async def conferma_tutte(db) -> Dict[str, Any]:
    """Conferma TUTTE le proposte in sospeso."""
    proposte = await db[COLLECTION].find(
        {"tipo": "pagamento_fattura", "stato": "da_confermare"},
        {"_id": 0, "id": 1}
    ).to_list(500)
    
    confermati = 0
    errori = 0
    for p in proposte:
        result = await conferma_proposta(db, p["id"])
        if result.get("success"):
            confermati += 1
        else:
            errori += 1
    
    return {"confermati": confermati, "errori": errori}


async def rifiuta_proposta(db, proposta_id: str) -> Dict[str, Any]:
    """Rifiuta una proposta (match errato)."""
    result = await db[COLLECTION].update_one(
        {"id": proposta_id},
        {"$set": {"stato": "rifiutata", "rifiutata_at": datetime.now(timezone.utc).isoformat()}}
    )
    return {"success": result.modified_count > 0}
