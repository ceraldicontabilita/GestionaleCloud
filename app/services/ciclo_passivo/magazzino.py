"""
Modulo Magazzino per il Ciclo Passivo.
Gestisce carico magazzino, lotti HACCP, movimenti.
"""
import uuid
import hashlib
import logging
from datetime import datetime, timezone
from typing import Dict, List

from .constants import (
    LOTTI_COLLECTION,
    MOVIMENTI_MAG_COLLECTION
)
from .helpers import estrai_codice_lotto, estrai_scadenza

logger = logging.getLogger(__name__)


def genera_id_lotto_interno(fornitore_nome: str, data_fattura: str, numero_linea: str) -> str:
    """
    Genera un ID univoco per il lotto interno.
    Formato: LI-YYYYMMDD-FORN-NNN
    """
    data_clean = data_fattura.replace("-", "")[:8] if data_fattura else datetime.now().strftime("%Y%m%d")
    forn_hash = hashlib.md5(fornitore_nome.encode()).hexdigest()[:4].upper()
    return f"LI-{data_clean}-{forn_hash}-{numero_linea.zfill(3)}"


async def processa_carico_magazzino(
    db, 
    fattura_id: str, 
    fornitore: Dict, 
    linee: List[Dict], 
    data_fattura: str, 
    numero_documento: str = ""
) -> Dict:
    """
    Processa il carico magazzino dalla fattura.
    Crea lotti HACCP e aggiorna le giacenze.
    
    Returns:
        {
            "lotti_creati": int,
            "lotti": [...],
            "errori": [...]
        }
    """
    risultato = {
        "lotti_creati": 0,
        "lotti": [],
        "errori": [],
        "giacenze_aggiornate": 0
    }
    
    fornitore_nome = fornitore.get("ragione_sociale") or fornitore.get("denominazione") or ""
    fornitore_id = fornitore.get("id") or fornitore.get("partita_iva")
    
    for idx, linea in enumerate(linee, 1):
        try:
            descrizione = linea.get("descrizione") or linea.get("Descrizione", "")
            if not descrizione:
                continue
            
            # Quantità e prezzo
            quantita = float(linea.get("quantita") or linea.get("Quantita") or 1)
            unita = linea.get("unita_misura") or linea.get("UnitaMisura") or "PZ"
            prezzo_unitario = float(linea.get("prezzo_unitario") or linea.get("PrezzoUnitario") or 0)
            prezzo_totale = float(linea.get("prezzo_totale") or linea.get("PrezzoTotale") or 0)
            
            # Estrai codice lotto e scadenza dalla descrizione
            codice_lotto = estrai_codice_lotto(descrizione)
            data_scadenza = estrai_scadenza(descrizione)
            
            # Genera ID lotto interno se non presente
            if not codice_lotto:
                codice_lotto = genera_id_lotto_interno(fornitore_nome, data_fattura, str(idx))
            
            # Crea lotto HACCP
            lotto = {
                "id": str(uuid.uuid4()),
                "codice_lotto": codice_lotto,
                "codice_interno": genera_id_lotto_interno(fornitore_nome, data_fattura, str(idx)),
                "prodotto": descrizione[:200],
                "descrizione_completa": descrizione,
                "fornitore_id": fornitore_id,
                "fornitore_nome": fornitore_nome,
                "fattura_id": fattura_id,
                "numero_documento": numero_documento,
                "data_carico": data_fattura,
                "data_scadenza": data_scadenza,
                "quantita_iniziale": quantita,
                "quantita_residua": quantita,
                "unita_misura": unita,
                "prezzo_unitario": prezzo_unitario,
                "prezzo_totale": prezzo_totale,
                "stato": "disponibile",
                "etichetta_stampata": False,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            
            # Controlla se lotto già esistente
            esistente = await db[LOTTI_COLLECTION].find_one({
                "codice_lotto": codice_lotto,
                "fattura_id": fattura_id
            })
            
            if not esistente:
                await db[LOTTI_COLLECTION].insert_one(lotto.copy())
                risultato["lotti_creati"] += 1
                risultato["lotti"].append({
                    "id": lotto["id"],
                    "codice": codice_lotto,
                    "prodotto": lotto["prodotto"][:50],
                    "quantita": quantita
                })
                
                # Crea movimento magazzino
                movimento = {
                    "id": str(uuid.uuid4()),
                    "lotto_id": lotto["id"],
                    "tipo": "carico",
                    "quantita": quantita,
                    "data": data_fattura,
                    "fattura_id": fattura_id,
                    "note": f"Carico da fattura {numero_documento}",
                    "created_at": datetime.now(timezone.utc).isoformat()
                }
                await db[MOVIMENTI_MAG_COLLECTION].insert_one(movimento.copy())
                
        except Exception as e:
            risultato["errori"].append({
                "linea": idx,
                "descrizione": descrizione[:50] if descrizione else "N/A",
                "errore": str(e)
            })
            logger.warning(f"Errore carico magazzino linea {idx}: {e}")
    
    return risultato
