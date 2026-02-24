"""
Funzioni di business logic per il modulo Noleggio Auto.
Elaborazione fatture, scansione veicoli, associazioni automatiche.
"""
import re
import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

from app.database import Database

from .constants import FORNITORI_NOLEGGIO, TARGA_PATTERN, COLLECTION
from .parsers import (
    estrai_codice_cliente,
    estrai_modello_marca,
    categorizza_spesa,
    is_nota_credito as check_nota_credito,
    is_fattura_bollo
)

logger = logging.getLogger(__name__)


async def processa_fattura_noleggio(fattura: dict) -> dict:
    """
    Processa una singola fattura per il modulo Noleggio Auto.
    Viene chiamata automaticamente durante l'import XML.
    
    Se trova un nuovo veicolo, lo crea.
    Se trova spese per un veicolo esistente, le associa.
    
    Returns: {"processed": bool, "veicolo_nuovo": bool, "targa": str, "categorie": [...]}
    """
    db = Database.get_db()
    
    supplier_vat = fattura.get("supplier_vat") or fattura.get("fornitore_partita_iva", "")
    
    # Verifica se è un fornitore di noleggio
    if supplier_vat not in FORNITORI_NOLEGGIO.values():
        return {"processed": False, "motivo": "Non è fornitore noleggio"}
    
    # Trova il nome del fornitore
    fornitore_nome = next((k for k, v in FORNITORI_NOLEGGIO.items() if v == supplier_vat), "")
    
    linee = fattura.get("linee", [])
    if not linee:
        return {"processed": False, "motivo": "Nessuna linea nella fattura"}
    
    # Estrai tutte le targhe dalla fattura
    targhe_trovate = set()
    for linea in linee:
        desc = linea.get("descrizione") or linea.get("Descrizione", "")
        match = re.search(TARGA_PATTERN, desc)
        if match:
            targhe_trovate.add(match.group(1))
    
    risultato = {
        "processed": True,
        "fornitore": fornitore_nome,
        "targhe": list(targhe_trovate),
        "veicoli_nuovi": [],
        "veicoli_aggiornati": [],
        "categorie_trovate": []
    }
    
    tipo_doc = fattura.get("tipo_documento", "").lower()
    is_nota_credito = "nota" in tipo_doc or tipo_doc == "td04"
    
    # Processa ogni targa trovata
    for targa in targhe_trovate:
        # Verifica se il veicolo esiste già
        veicolo_esistente = await db[COLLECTION].find_one({"targa": targa})
        
        if not veicolo_esistente:
            # Estrai informazioni per il nuovo veicolo
            marca = ""
            modello = ""
            for linea in linee:
                desc = linea.get("descrizione", "")
                if targa in desc:
                    marca, modello = estrai_modello_marca(desc, targa)
                    if marca or modello:
                        break
            
            # Crea nuovo veicolo
            codice_cliente = estrai_codice_cliente(fattura, fornitore_nome)
            nuovo_veicolo = {
                "id": str(uuid.uuid4()),
                "targa": targa,
                "marca": marca,
                "modello": modello,
                "fornitore_noleggio": fornitore_nome,
                "fornitore_piva": supplier_vat,
                "contratto": codice_cliente,
                "codice_cliente": codice_cliente,
                "driver": None,
                "driver_id": None,
                "data_inizio": fattura.get("invoice_date") or fattura.get("data_documento"),
                "data_fine": None,
                "note": f"Creato automaticamente da fattura {fattura.get('invoice_number') or fattura.get('numero_documento')}",
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            await db[COLLECTION].insert_one(nuovo_veicolo.copy())
            risultato["veicoli_nuovi"].append(targa)
        else:
            risultato["veicoli_aggiornati"].append(targa)
        
        # Analizza le categorie di spesa per questa targa
        for linea in linee:
            desc = linea.get("descrizione", "")
            if targa not in desc:
                continue
            
            prezzo = float(linea.get("prezzo_totale") or linea.get("PrezzoTotale") or 
                          linea.get("prezzo_unitario") or linea.get("PrezzoUnitario") or 0)
            categoria, importo, metadata = categorizza_spesa(desc, prezzo, is_nota_credito)
            
            if categoria not in risultato["categorie_trovate"]:
                risultato["categorie_trovate"].append(categoria)
    
    # Se nessuna targa trovata ma è fornitore noleggio, segnala per associazione manuale
    if not targhe_trovate:
        risultato["richiede_associazione_manuale"] = True
        risultato["motivo"] = "Fattura senza targa - richiede associazione manuale"
        
        # Analizza comunque le categorie
        for linea in linee:
            desc = linea.get("descrizione", "")
            prezzo = float(linea.get("prezzo_totale") or linea.get("prezzo_unitario") or 0)
            categoria, _, _ = categorizza_spesa(desc, prezzo, is_nota_credito)
            if categoria not in risultato["categorie_trovate"]:
                risultato["categorie_trovate"].append(categoria)
    
    return risultato


async def _trova_targa_per_fattura_bollo(
    db, 
    supplier_vat: str, 
    invoice_date: str
) -> Optional[str]:
    """
    Cerca la targa del veicolo attivo al momento della fattura bollo.
    Utilizzato quando la fattura non contiene la targa (es. LeasePlan).
    """
    # Usa la data della fattura per trovare il veicolo corretto
    data_fattura = invoice_date[:10] if invoice_date else datetime.now().strftime('%Y-%m-%d')
    
    # Cerca un veicolo attivo alla data della fattura
    veicoli_attivi = await db[COLLECTION].find({
        "fornitore_piva": supplier_vat,
        "$or": [
            {"data_fine": {"$exists": False}},
            {"data_fine": None},
            {"data_fine": ""},
            {"data_fine": {"$gte": data_fattura}}
        ]
    }).to_list(length=100)
    
    # Se ci sono più veicoli, scegli quello con data_inizio più vicina alla data fattura
    if len(veicoli_attivi) > 1:
        veicoli_attivi.sort(key=lambda x: x.get("data_inizio", ""), reverse=True)
        for v in veicoli_attivi:
            data_inizio = v.get("data_inizio", "")
            if data_inizio <= data_fattura:
                veicoli_attivi = [v]
                break
    
    if veicoli_attivi:
        return veicoli_attivi[0].get("targa")
    
    return None


async def _processa_linee_fattura(
    linee: List[dict],
    targhe_trovate: set,
    invoice_data: dict,
    is_nota_credito: bool,
    veicoli: dict
) -> Dict[str, Dict[str, Any]]:
    """
    Processa le linee di una fattura e le raggruppa per targa e categoria.
    Restituisce una struttura per l'aggregazione successiva.
    """
    linee_per_targa: Dict[str, Dict[str, Any]] = {}
    targhe_da_db = targhe_trovate.copy()
    
    # Extract from invoice_data for local use
    _ = (invoice_data["invoice_number"], invoice_data["invoice_date"], invoice_data["invoice_id"])  # Used in dicts below
    supplier = invoice_data["supplier"]
    supplier_vat = invoice_data["supplier_vat"]
    codice_cliente = invoice_data["codice_cliente"]
    
    for linea in linee:
        desc = linea.get("descrizione") or linea.get("Descrizione", "")
        
        # Trova la targa per questa linea
        match = re.search(TARGA_PATTERN, desc)
        if match:
            targa = match.group(1)
        elif targhe_da_db:
            targa = list(targhe_da_db)[0]
        else:
            continue
        
        # Inizializza veicolo nel risultato finale se non esiste
        if targa not in veicoli:
            marca, modello = estrai_modello_marca(desc, targa)
            veicoli[targa] = _crea_struttura_veicolo(
                targa, supplier, supplier_vat, codice_cliente, marca, modello
            )
        else:
            _aggiorna_info_veicolo(veicoli[targa], desc, targa, codice_cliente)
        
        # Inizializza struttura per questa targa in questa fattura
        if targa not in linee_per_targa:
            linee_per_targa[targa] = {}
        
        # Estrai importi
        prezzo_totale = float(linea.get("prezzo_totale") or linea.get("PrezzoTotale") or 
                              linea.get("prezzo_unitario") or linea.get("PrezzoUnitario") or 0)
        aliquota_iva = float(linea.get("aliquota_iva") or linea.get("AliquotaIVA") or 22)
        
        # Categorizza con metadata
        categoria, importo, metadata = categorizza_spesa(desc, prezzo_totale, is_nota_credito)
        iva = abs(importo) * aliquota_iva / 100
        if importo < 0:
            iva = -iva
        
        # Per i verbali, crea un record separato per ogni riga
        if categoria == "verbali":
            _aggiungi_verbale(veicoli[targa], invoice_data, desc, importo, iva, metadata)
            continue
        
        # Raggruppa per categoria (per le altre categorie)
        if categoria not in linee_per_targa[targa]:
            linee_per_targa[targa][categoria] = {
                "voci": [],
                "totale_imponibile": 0,
                "totale_iva": 0,
                "metadata": {}
            }
        
        linee_per_targa[targa][categoria]["voci"].append({
            "descrizione": desc,
            "importo": round(importo, 2)
        })
        linee_per_targa[targa][categoria]["totale_imponibile"] += importo
        linee_per_targa[targa][categoria]["totale_iva"] += iva
        
        for k, v in metadata.items():
            if k not in linee_per_targa[targa][categoria]["metadata"]:
                linee_per_targa[targa][categoria]["metadata"][k] = v
    
    return linee_per_targa


def _crea_struttura_veicolo(
    targa: str, 
    supplier: str, 
    supplier_vat: str, 
    codice_cliente: Optional[str],
    marca: str,
    modello: str
) -> Dict[str, Any]:
    """Crea la struttura iniziale per un veicolo."""
    return {
        "targa": targa,
        "fornitore_noleggio": supplier,
        "fornitore_piva": supplier_vat,
        "codice_cliente": codice_cliente,
        "modello": modello,
        "marca": marca,
        "driver": None,
        "driver_id": None,
        "contratto": codice_cliente,
        "data_inizio": None,
        "data_fine": None,
        "note": None,
        "canoni": [],
        "pedaggio": [],
        "verbali": [],
        "bollo": [],
        "costi_extra": [],
        "riparazioni": [],
        "totale_canoni": 0,
        "totale_pedaggio": 0,
        "totale_verbali": 0,
        "totale_bollo": 0,
        "totale_costi_extra": 0,
        "totale_riparazioni": 0,
        "totale_generale": 0
    }


def _aggiorna_info_veicolo(veicolo: dict, desc: str, targa: str, codice_cliente: Optional[str]):
    """Aggiorna le info del veicolo se mancanti."""
    if codice_cliente and not veicolo["codice_cliente"]:
        veicolo["codice_cliente"] = codice_cliente
        veicolo["contratto"] = codice_cliente
    
    if not veicolo["modello"]:
        marca, modello = estrai_modello_marca(desc, targa)
        if modello:
            veicolo["modello"] = modello
        if marca:
            veicolo["marca"] = marca


def _aggiungi_verbale(veicolo: dict, invoice_data: dict, desc: str, importo: float, iva: float, metadata: dict):
    """Aggiunge un verbale al veicolo."""
    imponibile = round(importo, 2)
    iva_calc = round(iva, 2)
    totale = round(imponibile + iva_calc, 2)
    
    record = {
        "data": invoice_data["invoice_date"],
        "numero_fattura": invoice_data["invoice_number"],
        "fattura_id": invoice_data["invoice_id"],
        "fornitore": invoice_data["supplier"],
        "descrizione": desc,
        "imponibile": imponibile,
        "iva": iva_calc,
        "totale": totale,
        "pagato": invoice_data.get("pagato", False),
        "numero_verbale": metadata.get("numero_verbale"),
        "data_verbale": metadata.get("data_verbale")
    }
    
    veicolo["verbali"].append(record)
    veicolo["totale_verbali"] += imponibile


async def scan_fatture_noleggio(anno: Optional[int] = None) -> Tuple[Dict[str, Any], List[dict]]:
    """
    Scansiona le fatture XML per estrarre dati veicoli noleggio.
    Raggruppa per targa e per numero fattura (non per singola linea).
    
    MODIFICA: Se anno non specificato, carica TUTTI gli anni.
    
    Returns: (veicoli_dict, fatture_senza_targa)
    """
    
    db = Database.get_db()
    
    veicoli: Dict[str, Any] = {}
    fatture_senza_targa: List[dict] = []
    
    # Query per P.IVA fornitori con proiezione per performance
    query: Dict[str, Any] = {
        "supplier_vat": {"$in": list(FORNITORI_NOLEGGIO.values())}
    }
    
    # Se anno specificato, filtra per quell'anno
    if anno is not None:
        query["invoice_date"] = {"$regex": f"^{anno}"}
    
    # Proiezione per ridurre il payload (escludi xml_content e altri campi pesanti)
    projection = {
        "_id": 1,
        "invoice_number": 1,
        "invoice_date": 1,
        "supplier_name": 1,
        "supplier_vat": 1,
        "tipo_documento": 1,
        "total_amount": 1,
        "pagato": 1,
        "prima_nota_banca_id": 1,
        "linee": 1,
        "causali": 1
    }
    
    cursor = db["invoices"].find(query, projection)
    
    async for invoice in cursor:
        invoice_number = invoice.get("invoice_number", "")
        invoice_date = invoice.get("invoice_date", "")
        supplier = invoice.get("supplier_name", "")
        supplier_vat = invoice.get("supplier_vat", "")
        invoice_id = str(invoice.get("_id", ""))
        
        is_nota_credito = check_nota_credito(invoice)
        codice_cliente = estrai_codice_cliente(invoice, supplier)
        
        linee = invoice.get("linee", [])
        targhe_trovate: set = set()
        
        # Prima passata: trova tutte le targhe nella fattura
        for linea in linee:
            desc = linea.get("descrizione") or linea.get("Descrizione", "")
            match = re.search(TARGA_PATTERN, desc)
            if match:
                targhe_trovate.add(match.group(1))
        
        # Se nessuna targa trovata, prova ad associare intelligentemente
        if not targhe_trovate:
            if is_fattura_bollo(linee) and supplier_vat:
                targa_attiva = await _trova_targa_per_fattura_bollo(db, supplier_vat, invoice_date)
                if targa_attiva:
                    targhe_trovate.add(targa_attiva)
                    logger.info(f"Associo fattura bollo {invoice_number} a targa {targa_attiva}")
            
            if not targhe_trovate:
                fatture_senza_targa.append({
                    "invoice_number": invoice_number,
                    "invoice_date": invoice_date,
                    "invoice_id": invoice_id,
                    "supplier": supplier,
                    "supplier_vat": supplier_vat,
                    "tipo_documento": invoice.get("tipo_documento", ""),
                    "codice_cliente": codice_cliente,
                    "total": invoice.get("total_amount", 0),
                    "pagato": invoice.get("pagato", False),
                    "prima_nota_banca_id": invoice.get("prima_nota_banca_id"),
                    "linee": linee
                })
                continue
        
        # Prepara dati fattura per processamento
        invoice_data = {
            "invoice_number": invoice_number,
            "invoice_date": invoice_date,
            "invoice_id": invoice_id,
            "supplier": supplier,
            "supplier_vat": supplier_vat,
            "codice_cliente": codice_cliente,
            "pagato": invoice.get("pagato", False)
        }
        
        # Processa linee (usa invoice_data internamente)
        linee_per_targa = await _processa_linee_fattura(
            linee, targhe_trovate, invoice_data, is_nota_credito, veicoli
        )
        
        # Aggiungi fatture raggruppate al veicolo (esclusi verbali)
        for targa, categorie in linee_per_targa.items():
            for categoria, dati in categorie.items():
                if categoria == "verbali":
                    continue
                    
                imponibile = round(dati["totale_imponibile"], 2)
                iva = round(dati["totale_iva"], 2)
                totale = round(imponibile + iva, 2)
                
                record = {
                    "data": invoice_date,
                    "numero_fattura": invoice_number,
                    "fattura_id": invoice_id,
                    "fornitore": supplier,
                    "voci": dati["voci"],
                    "imponibile": imponibile,
                    "iva": iva,
                    "totale": totale,
                    "pagato": invoice.get("pagato", False)
                }
                
                veicoli[targa][categoria].append(record)
                veicoli[targa][f"totale_{categoria}"] += imponibile
    
    # Calcola totali generali
    for targa in veicoli:
        veicoli[targa]["totale_generale"] = round(
            veicoli[targa]["totale_canoni"] +
            veicoli[targa]["totale_pedaggio"] +
            veicoli[targa]["totale_verbali"] +
            veicoli[targa]["totale_bollo"] +
            veicoli[targa]["totale_costi_extra"] +
            veicoli[targa]["totale_riparazioni"],
            2
        )
        
        for key in ["totale_canoni", "totale_pedaggio", "totale_verbali", 
                    "totale_bollo", "totale_costi_extra", "totale_riparazioni"]:
            veicoli[targa][key] = round(veicoli[targa][key], 2)
    
    return veicoli, fatture_senza_targa
