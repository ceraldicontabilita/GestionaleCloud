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
from app.services.scritture_contabili import scrivi_movimento

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
    
    # Proposte già esistenti (dedup). Un movimento EC non può alimentare
    # contemporaneamente più proposte attive/confermate. Le proposte rifiutate
    # non lo consumano e possono quindi lasciare il movimento disponibile.
    existing_refs = set()
    existing_movement_refs = set()
    async for p in db[COLLECTION].find(
        {"tipo": "pagamento_fattura", "stato": {"$in": ["da_confermare", "in_conferma", "confermata"]}},
        {"_id": 0, "fattura_id": 1, "movimento_id": 1},
    ):
        if p.get("fattura_id"):
            existing_refs.add(p.get("fattura_id"))
        if p.get("movimento_id"):
            existing_movement_refs.add(str(p.get("movimento_id")))
    
    # Solo movimenti bancari reali ancora liberi. Una riga EC già riconciliata
    # è prova già consumata e non può essere proposta di nuovo.
    movimenti = await db["estratto_conto_movimenti"].find(
        {
            "tipo": "uscita",
            "data_contabile": {"$regex": f"/{anno}$"},
            "riconciliato": {"$ne": True},
        },
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
            movimento_id = mov.get("id")
            if not movimento_id:
                continue
            if movimento_id in movimenti_usati or str(movimento_id) in existing_movement_refs:
                continue
            if mov.get("riconciliato") is True:
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
    """Conferma UNA proposta usando come prova il movimento EC reale.

    La proposta è solo un suggerimento. La conferma viene serializzata per
    evitare doppi click e il movimento di estratto conto viene "prenotato"
    prima della scrittura, così non può saldare due fatture concorrenti.
    """
    proposta = await db[COLLECTION].find_one({"id": proposta_id})
    if not proposta:
        return {"success": False, "error": "Proposta non trovata"}
    if proposta.get("stato") == "confermata":
        return {
            "success": True,
            "message": "Già confermata",
            "idempotent_replay": True,
            "prima_nota_id": proposta.get("prima_nota_id"),
        }
    if proposta.get("stato") != "da_confermare":
        return {"success": False, "error": f"Proposta non confermabile: {proposta.get('stato') or 'stato sconosciuto'}"}

    now = datetime.now(timezone.utc).isoformat()
    claim = await db[COLLECTION].update_one(
        {"id": proposta_id, "stato": "da_confermare"},
        {"$set": {"stato": "in_conferma", "conferma_claimed_at": now}},
    )
    if getattr(claim, "modified_count", 0) == 0:
        aggiornata = await db[COLLECTION].find_one({"id": proposta_id}) or {}
        if aggiornata.get("stato") == "confermata":
            return {
                "success": True, "message": "Già confermata",
                "idempotent_replay": True,
                "prima_nota_id": aggiornata.get("prima_nota_id"),
            }
        return {"success": False, "error": "Proposta già in elaborazione o non più confermabile"}

    movimento_id = str(proposta.get("movimento_id") or "").strip()
    if not movimento_id:
        await db[COLLECTION].update_one(
            {"id": proposta_id, "stato": "in_conferma"},
            {"$set": {"stato": "da_confermare", "errore_conferma": "Movimento EC mancante"}},
        )
        return {"success": False, "error": "Movimento di estratto conto mancante: nessuna prova bancaria"}

    # Prenota atomicamente il movimento EC. La query impedisce che una prova
    # già riconciliata o prenotata da un'altra proposta venga riutilizzata.
    ec_claim = await db["estratto_conto_movimenti"].update_one(
        {
            "id": movimento_id,
            "riconciliato": {"$ne": True},
            "riconciliazione_claim": {"$in": [None, proposta_id]},
        },
        {"$set": {
            "riconciliazione_claim": proposta_id,
            "riconciliazione_claimed_at": now,
        }},
    )
    if getattr(ec_claim, "modified_count", 0) == 0:
        await db[COLLECTION].update_one(
            {"id": proposta_id, "stato": "in_conferma"},
            {"$set": {"stato": "da_confermare", "errore_conferma": "Movimento EC già usato o non disponibile"}},
        )
        return {"success": False, "error": "Movimento bancario già riconciliato o impegnato da un'altra proposta"}

    fatt_id = proposta.get("fattura_id")
    importo = float(proposta.get("fattura_importo") or 0)
    fornitore = proposta.get("fattura_fornitore", "")
    numero = proposta.get("fattura_numero", "")
    data_mov = proposta.get("movimento_data", "")
    data_iso = data_mov
    if "/" in data_mov:
        parts = data_mov.split("/")
        if len(parts) == 3:
            data_iso = f"{parts[2]}-{parts[1]}-{parts[0]}"

    try:
        from app.routers.prima_nota_module.sync import costruisci_campi_movimento_fattura
        fattura_doc = await db["invoices"].find_one(
            {"id": fatt_id},
            {"_id": 0, "tipo_documento": 1, "supplier_vat": 1, "cedente_piva": 1},
        ) or {}
        fattura_per_helper = {
            "tipo_documento": fattura_doc.get("tipo_documento"),
            "invoice_number": numero,
            "supplier_name": fornitore,
            "supplier_vat": fattura_doc.get("supplier_vat"),
            "cedente_piva": fattura_doc.get("cedente_piva"),
        }

        pn_id = str(uuid.uuid4())
        movimento = {
            "id": pn_id,
            "data": data_iso,
            **costruisci_campi_movimento_fattura(fattura_per_helper, importo),
            "riferimento": f"FATT-{fatt_id}",
            "fattura_id": fatt_id,
            # Campo canonico usato dal writer per l'hash idempotente; il legacy
            # resta per compatibilità con le letture storiche.
            "movimento_bancario_id": movimento_id,
            "movimento_banca_id": movimento_id,
            "estratto_conto_id": movimento_id,
            "riconciliato": True,
            "source": "conferma_provvisori",
            "created_at": now,
        }
        pn_id = await scrivi_movimento(db, "banca", movimento)

        await db["estratto_conto_movimenti"].update_one(
            {"id": movimento_id, "riconciliazione_claim": proposta_id},
            {"$set": {
                "riconciliato": True,
                "fattura_id": fatt_id,
                "prima_nota_id": pn_id,
                "riconciliato_il": now,
                "riconciliazione_fonte": "conferma_provvisori",
                "riconciliazione_claim": None,
            }},
        )
        await db["invoices"].update_one(
            {"id": fatt_id},
            {"$set": {
                "status": "paid",
                "payment_status": "paid",
                "pagato": True,
                "stato_pagamento": "pagata",
                "importo_pagato": importo,
                "importo_residuo": 0.0,
                "riconciliato": True,
                "prima_nota_id": pn_id,
                "prima_nota_tipo": "banca",
                "movimento_bancario_id": movimento_id,
                "data_pagamento": data_iso,
            }},
        )
        await db[COLLECTION].update_one(
            {"id": proposta_id, "stato": "in_conferma"},
            {"$set": {
                "stato": "confermata",
                "confermata_at": now,
                "prima_nota_id": pn_id,
                "movimento_id": movimento_id,
                "errore_conferma": None,
            }},
        )
        return {
            "success": True,
            "message": f"Pagamento confermato: {fornitore} €{importo}",
            "prima_nota_id": pn_id,
            "movimento_id": movimento_id,
        }
    except Exception:
        # Se la scrittura fallisce, rilascia le prenotazioni: nessun movimento
        # deve restare falsamente riconciliato per un errore applicativo.
        await db["estratto_conto_movimenti"].update_one(
            {"id": movimento_id, "riconciliazione_claim": proposta_id, "riconciliato": {"$ne": True}},
            {"$set": {"riconciliazione_claim": None}},
        )
        await db[COLLECTION].update_one(
            {"id": proposta_id, "stato": "in_conferma"},
            {"$set": {"stato": "da_confermare", "errore_conferma": "Errore durante la conferma"}},
        )
        raise


async def conferma_tutte(db) -> Dict[str, Any]:
    """Disabilitata: le proposte probabilistiche richiedono conferma singola."""
    return {
        "success": False,
        "error": "Conferma massiva disabilitata: verificare e confermare ogni proposta singolarmente",
        "confermati": 0,
    }


async def rifiuta_proposta(db, proposta_id: str) -> Dict[str, Any]:
    """Rifiuta una proposta (match errato)."""
    result = await db[COLLECTION].update_one(
        {"id": proposta_id},
        {"$set": {"stato": "rifiutata", "rifiutata_at": datetime.now(timezone.utc).isoformat()}}
    )
    return {"success": result.modified_count > 0}
