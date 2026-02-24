"""
Servizio ricerca IBAN per fornitori.
Estrae IBAN da fatture XML, API pubbliche e altri fonti.
"""
import re
import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone


from .constants import Collections

logger = logging.getLogger(__name__)

# Regex per IBAN italiano
IBAN_PATTERN = re.compile(r'IT\d{2}[A-Z]?\d{5}\d{5}[A-Z0-9]{12}', re.IGNORECASE)

# Metodi di pagamento che richiedono IBAN
METODI_BANCARI = [
    "bonifico", "banca", "sepa", "rid", "sdd", 
    "assegno", "riba", "mav", "rav", "f24", "carta", "misto"
]


async def estrai_iban_da_fatture(db, piva: str) -> Optional[str]:
    """
    Cerca IBAN nelle fatture XML per una P.IVA.
    
    Args:
        db: Database MongoDB
        piva: Partita IVA del fornitore
        
    Returns:
        IBAN trovato o None
    """
    # Cerca prima nel campo pagamento.iban
    fattura_con_iban = await db["invoices"].find_one(
        {
            "$or": [{"cedente_piva": piva}, {"supplier_vat": piva}],
            "pagamento.iban": {"$exists": True, "$ne": "", "$ne": None}
        },
        {"pagamento.iban": 1}
    )
    
    if fattura_con_iban:
        iban_candidato = fattura_con_iban.get("pagamento", {}).get("iban", "")
        if iban_candidato:
            iban_clean = iban_candidato.upper().strip()
            if IBAN_PATTERN.match(iban_clean) and len(iban_clean) == 27:
                return iban_clean
    
    # Cerca in campi alternativi
    fatture = await db["invoices"].find(
        {"$or": [{"cedente_piva": piva}, {"supplier_vat": piva}]},
        {"pagamento": 1, "dati_pagamento": 1, "payment_data": 1, "_id": 0}
    ).limit(10).to_list(10)
    
    for fattura in fatture:
        for campo in ["pagamento", "dati_pagamento", "payment_data"]:
            dati = fattura.get(campo, {})
            if isinstance(dati, dict):
                for v in dati.values():
                    if v and isinstance(v, str) and "IT" in v.upper():
                        match = IBAN_PATTERN.search(v.upper())
                        if match:
                            iban_candidato = match.group(0)
                            if len(iban_candidato) == 27:
                                return iban_candidato
    
    return None


async def ricerca_iban_web(db, fornitori: List[Dict]) -> Dict[str, Any]:
    """
    Cerca IBAN per una lista di fornitori usando tutte le fonti disponibili.
    
    Args:
        db: Database MongoDB
        fornitori: Lista di fornitori senza IBAN
        
    Returns:
        Risultato ricerca con statistiche
    """
    import httpx
    
    risultato = {
        "totale_fornitori": len(fornitori),
        "iban_trovati": 0,
        "iban_da_fatture": 0,
        "iban_da_api": 0,
        "non_trovati": 0,
        "errori": 0,
        "dettaglio_trovati": [],
        "dettaglio_non_trovati": []
    }
    
    if not fornitori:
        return risultato
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        for fornitore in fornitori:
            piva = fornitore.get("partita_iva", "")
            nome = fornitore.get("ragione_sociale") or fornitore.get("denominazione") or ""
            fornitore_id = fornitore.get("id")
            
            # Salta P.IVA non italiane (non 11 cifre)
            piva_clean = re.sub(r'[^0-9]', '', str(piva))
            if len(piva_clean) != 11:
                risultato["non_trovati"] += 1
                continue
            
            iban_trovato = None
            fonte = None
            
            try:
                # Fonte 1: Fatture XML
                iban_trovato = await estrai_iban_da_fatture(db, piva)
                if iban_trovato:
                    fonte = "fatture_xml"
                    risultato["iban_da_fatture"] += 1
                
                # Fonte 2: OpenCorporates API (per validare il fornitore)
                if not iban_trovato:
                    try:
                        oc_url = f"https://api.opencorporates.com/v0.4/companies/search?q={piva}&jurisdiction_code=it"
                        oc_resp = await client.get(oc_url)
                        if oc_resp.status_code == 200:
                            oc_data = oc_resp.json()
                            companies = oc_data.get("results", {}).get("companies", [])
                            if companies:
                                comp = companies[0].get("company", {})
                                if comp.get("name") and not nome:
                                    await db[Collections.SUPPLIERS].update_one(
                                        {"id": fornitore_id},
                                        {"$set": {"ragione_sociale": comp["name"].title()}}
                                    )
                    except Exception as e:
                        logger.debug(f"OpenCorporates error for {piva}: {e}")
                
                # Aggiorna fornitore se trovato IBAN
                if iban_trovato:
                    await db[Collections.SUPPLIERS].update_one(
                        {"id": fornitore_id},
                        {"$set": {
                            "iban": iban_trovato,
                            "iban_fonte": fonte,
                            "iban_data_ricerca": datetime.now(timezone.utc).isoformat(),
                            "updated_at": datetime.now(timezone.utc).isoformat()
                        }}
                    )
                    
                    risultato["iban_trovati"] += 1
                    risultato["dettaglio_trovati"].append({
                        "partita_iva": piva,
                        "nome": nome,
                        "iban": iban_trovato,
                        "fonte": fonte
                    })
                    logger.info(f"IBAN trovato per {nome}: {iban_trovato[:10]}... (fonte: {fonte})")
                else:
                    risultato["non_trovati"] += 1
                    if len(risultato["dettaglio_non_trovati"]) < 50:
                        risultato["dettaglio_non_trovati"].append({
                            "partita_iva": piva,
                            "nome": nome,
                            "motivo": "Non presente nelle fatture importate"
                        })
                
                await asyncio.sleep(0.1)
                
            except Exception as e:
                risultato["errori"] += 1
                logger.warning(f"Errore ricerca IBAN {piva}: {e}")
    
    return risultato


async def trova_fornitori_senza_iban(db, limit: int = 500) -> List[Dict]:
    """
    Trova fornitori con metodo bancario ma senza IBAN.
    """
    return await db[Collections.SUPPLIERS].find({
        "metodo_pagamento": {"$in": METODI_BANCARI},
        "$or": [
            {"iban": None},
            {"iban": ""},
            {"iban": {"$exists": False}}
        ],
        "partita_iva": {"$exists": True, "$ne": "", "$ne": None}
    }, {"_id": 0, "id": 1, "partita_iva": 1, "ragione_sociale": 1, "denominazione": 1}).to_list(limit)
