"""
Document Data Saver Service
Salva i dati estratti dai documenti nelle collection appropriate del gestionale.

Mapping tipo_documento -> collection:
- F24 -> f24_models
- BUSTA_PAGA -> cedolini / anagrafica_dipendenti
- ESTRATTO_CONTO -> estratto_conto_movimenti
- BONIFICO -> bonifici_stipendi / archivio_bonifici
- VERBALE -> verbali_noleggio
- CARTELLA_ESATTORIALE -> adr_definizione_agevolata
- DELIBERA_INPS -> delibere_fonsi
- FATTURA -> invoices
"""

from datetime import datetime, timezone
from typing import Dict, Any, Optional
import logging
import re

logger = logging.getLogger(__name__)


def parse_date(date_str: str) -> Optional[str]:
    """Converte vari formati data in ISO format."""
    if not date_str:
        return None
    
    # Già in formato ISO
    if re.match(r'\d{4}-\d{2}-\d{2}', str(date_str)):
        return str(date_str)[:10]
    
    # Formato DD/MM/YYYY
    match = re.match(r'(\d{1,2})/(\d{1,2})/(\d{4})', str(date_str))
    if match:
        return f"{match.group(3)}-{match.group(2).zfill(2)}-{match.group(1).zfill(2)}"
    
    return str(date_str)


def parse_amount(amount) -> float:
    """Converte importo in float."""
    if amount is None:
        return 0.0
    if isinstance(amount, (int, float)):
        return float(amount)
    # Rimuovi simboli valuta e converti
    clean = str(amount).replace('€', '').replace('.', '').replace(',', '.').strip()
    try:
        return float(clean)
    except:
        return 0.0


async def save_f24_to_gestionale(db, data: Dict[str, Any], source_info: Dict[str, Any] = None) -> Dict[str, Any]:
    """Salva F24 nella collection f24_models."""
    try:
        doc = {
            "codice_fiscale": data.get("codice_fiscale"),
            "denominazione": data.get("denominazione"),
            "data_versamento": parse_date(data.get("data_versamento")),
            "totale_versamento": parse_amount(data.get("totale_versamento")),
            "sezione_erario": data.get("sezione_erario", []),
            "sezione_inps": data.get("sezione_inps", []),
            "sezione_regioni": data.get("sezione_regioni", []),
            "sezione_imu": data.get("sezione_imu", []),
            "source": "document_ai",
            "source_info": source_info or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
            "processed": True
        }
        
        # Evita duplicati (stesso CF + data + totale)
        existing = await db["f24_unificato"].find_one({
            "codice_fiscale": doc["codice_fiscale"],
            "data_versamento": doc["data_versamento"],
            "totale_versamento": doc["totale_versamento"]
        })
        
        if existing:
            return {"status": "duplicate", "message": "F24 già presente", "id": str(existing.get("_id"))}
        
        result = await db["f24_unificato"].insert_one(doc)
        return {"status": "saved", "collection": "f24_models", "id": str(result.inserted_id)}
        
    except Exception as e:
        logger.error(f"Errore salvataggio F24: {e}")
        return {"status": "error", "message": str(e)}


async def save_busta_paga_to_gestionale(db, data: Dict[str, Any], source_info: Dict[str, Any] = None) -> Dict[str, Any]:
    """Salva busta paga nella collection cedolini e aggiorna anagrafica dipendente."""
    try:
        dipendente = data.get("dipendente", {})
        azienda = data.get("azienda", {})
        periodo = data.get("periodo", {})
        retribuzione = data.get("retribuzione", {})
        
        # Documento cedolino
        doc = {
            "dipendente_cf": dipendente.get("codice_fiscale"),
            "dipendente_nome": dipendente.get("nome_cognome"),
            "dipendente_matricola": dipendente.get("matricola"),
            "azienda_cf": azienda.get("codice_fiscale"),
            "azienda_denominazione": azienda.get("denominazione"),
            "mese": periodo.get("mese"),
            "anno": periodo.get("anno"),
            "lordo": parse_amount(retribuzione.get("lordo")),
            "netto": parse_amount(retribuzione.get("netto")),
            "trattenute_inps": parse_amount(retribuzione.get("trattenute_inps")),
            "trattenute_irpef": parse_amount(retribuzione.get("trattenute_irpef")),
            "addizionale_regionale": parse_amount(retribuzione.get("addizionale_regionale")),
            "addizionale_comunale": parse_amount(retribuzione.get("addizionale_comunale")),
            "ore_lavorate": data.get("ore_lavorate"),
            "giorni_lavorati": data.get("giorni_lavorati"),
            "tfr_maturato": parse_amount(data.get("tfr_maturato")),
            "source": "document_ai",
            "source_info": source_info or {},
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        # Evita duplicati
        existing = await db["cedolini"].find_one({
            "dipendente_cf": doc["dipendente_cf"],
            "mese": doc["mese"],
            "anno": doc["anno"]
        })
        
        if existing:
            return {"status": "duplicate", "message": "Cedolino già presente", "id": str(existing.get("_id"))}
        
        result = await db["cedolini"].insert_one(doc)
        
        # Aggiorna/crea anagrafica dipendente
        if dipendente.get("codice_fiscale"):
            await db["dipendenti"].update_one(
                {"codice_fiscale": dipendente.get("codice_fiscale")},
                {
                    "$set": {
                        "nome_cognome": dipendente.get("nome_cognome"),
                        "matricola": dipendente.get("matricola"),
                        "last_cedolino": f"{periodo.get('mese')}/{periodo.get('anno')}",
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    },
                    "$setOnInsert": {
                        "created_at": datetime.now(timezone.utc).isoformat()
                    }
                },
                upsert=True
            )
        
        return {"status": "saved", "collection": "cedolini", "id": str(result.inserted_id)}
        
    except Exception as e:
        logger.error(f"Errore salvataggio busta paga: {e}")
        return {"status": "error", "message": str(e)}


async def save_bonifico_to_gestionale(db, data: Dict[str, Any], source_info: Dict[str, Any] = None) -> Dict[str, Any]:
    """Salva bonifico nella collection archivio_bonifici."""
    try:
        ordinante = data.get("ordinante", {})
        beneficiario = data.get("beneficiario", {})
        
        doc = {
            "data_operazione": parse_date(data.get("data_operazione")),
            "data_valuta": parse_date(data.get("data_valuta")),
            "importo": parse_amount(data.get("importo")),
            "valuta": data.get("valuta", "EUR"),
            "ordinante_denominazione": ordinante.get("denominazione"),
            "ordinante_iban": ordinante.get("iban"),
            "ordinante_banca": ordinante.get("banca"),
            "beneficiario_denominazione": beneficiario.get("denominazione"),
            "beneficiario_iban": beneficiario.get("iban"),
            "beneficiario_banca": beneficiario.get("banca"),
            "causale": data.get("causale"),
            "cro_trn": data.get("cro_trn"),
            "tipo_bonifico": data.get("tipo_bonifico"),
            "commissioni": parse_amount(data.get("commissioni")),
            "source": "document_ai",
            "source_info": source_info or {},
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        # Evita duplicati (CRO/TRN unico)
        if doc.get("cro_trn"):
            existing = await db["archivio_bonifici"].find_one({"cro_trn": doc["cro_trn"]})
            if existing:
                return {"status": "duplicate", "message": "Bonifico già presente (CRO/TRN)", "id": str(existing.get("_id"))}
        
        result = await db["archivio_bonifici"].insert_one(doc)
        return {"status": "saved", "collection": "archivio_bonifici", "id": str(result.inserted_id)}
        
    except Exception as e:
        logger.error(f"Errore salvataggio bonifico: {e}")
        return {"status": "error", "message": str(e)}


async def save_estratto_conto_to_gestionale(db, data: Dict[str, Any], source_info: Dict[str, Any] = None) -> Dict[str, Any]:
    """Salva movimenti estratto conto nella collection estratto_conto_movimenti."""
    try:
        movimenti_salvati = 0
        movimenti_duplicati = 0
        
        base_info = {
            "banca": data.get("banca"),
            "intestatario": data.get("intestatario"),
            "iban": data.get("iban"),
            "source": "document_ai",
            "source_info": source_info or {},
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        for mov in data.get("movimenti", []):
            importo = parse_amount(mov.get("importo"))
            tipo = "entrata" if importo > 0 else "uscita"
            
            doc = {
                **base_info,
                "data": parse_date(mov.get("data")),
                "data_valuta": parse_date(mov.get("data_valuta")),
                "descrizione": mov.get("descrizione"),
                "importo": abs(importo),
                "tipo": tipo,
                "descrizione_originale": mov.get("descrizione"),
                "riconciliato": False
            }
            
            # Genera ID univoco per evitare duplicati
            doc_id = f"EC-{doc['data']}-{doc['importo']:.2f}-{hash(doc['descrizione'] or '')}"
            doc["id"] = doc_id
            
            existing = await db["estratto_conto_movimenti"].find_one({"id": doc_id})
            if existing:
                movimenti_duplicati += 1
                continue
            
            await db["estratto_conto_movimenti"].insert_one(doc)
            movimenti_salvati += 1
        
        return {
            "status": "saved", 
            "collection": "estratto_conto_movimenti",
            "movimenti_salvati": movimenti_salvati,
            "movimenti_duplicati": movimenti_duplicati
        }
        
    except Exception as e:
        logger.error(f"Errore salvataggio estratto conto: {e}")
        return {"status": "error", "message": str(e)}


async def save_verbale_to_gestionale(db, data: Dict[str, Any], source_info: Dict[str, Any] = None) -> Dict[str, Any]:
    """Salva verbale nella collection verbali_noleggio."""
    try:
        proprietario = data.get("proprietario", {})
        violazione = data.get("violazione", {})
        
        doc = {
            "numero_verbale": data.get("numero_verbale"),
            "data_verbale": parse_date(data.get("data_verbale")),
            "data_violazione": parse_date(data.get("data_violazione")),
            "ora_violazione": data.get("ora_violazione"),
            "luogo_violazione": data.get("luogo_violazione"),
            "targa": data.get("targa_veicolo"),
            "tipo_veicolo": data.get("tipo_veicolo"),
            "proprietario_nome": proprietario.get("nome_cognome"),
            "proprietario_cf": proprietario.get("codice_fiscale"),
            "proprietario_indirizzo": proprietario.get("indirizzo"),
            "articolo_violato": violazione.get("articolo"),
            "descrizione_violazione": violazione.get("descrizione"),
            "punti_patente": violazione.get("punti_patente"),
            "importo_ridotto": parse_amount(data.get("importo_ridotto")),
            "importo_pieno": parse_amount(data.get("importo_pieno")),
            "scadenza_pagamento": parse_date(data.get("scadenza_pagamento")),
            "ente_accertatore": data.get("ente_accertatore"),
            "societa_noleggio": data.get("societa_noleggio"),
            "stato": "in_attesa_conferma",
            "source": "document_ai",
            "source_info": source_info or {},
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        # Evita duplicati
        if doc.get("numero_verbale"):
            existing = await db["verbali_noleggio"].find_one({"numero_verbale": doc["numero_verbale"]})
            if existing:
                return {"status": "duplicate", "message": "Verbale già presente", "id": str(existing.get("_id"))}
        
        result = await db["verbali_noleggio"].insert_one(doc)
        return {"status": "saved", "collection": "verbali_noleggio", "id": str(result.inserted_id)}
        
    except Exception as e:
        logger.error(f"Errore salvataggio verbale: {e}")
        return {"status": "error", "message": str(e)}


async def save_cartella_esattoriale_to_gestionale(db, data: Dict[str, Any], source_info: Dict[str, Any] = None) -> Dict[str, Any]:
    """Salva cartella esattoriale nella collection adr_definizione_agevolata."""
    try:
        contribuente = data.get("contribuente", {})
        
        doc = {
            "numero_cartella": data.get("numero_cartella"),
            "data_notifica": parse_date(data.get("data_notifica")),
            "contribuente_denominazione": contribuente.get("denominazione"),
            "contribuente_cf": contribuente.get("codice_fiscale"),
            "contribuente_indirizzo": contribuente.get("indirizzo"),
            "ente_creditore": data.get("ente_creditore"),
            "debiti": data.get("debiti", []),
            "totale_cartella": parse_amount(data.get("totale_cartella")),
            "scadenza_pagamento": parse_date(data.get("scadenza_pagamento")),
            "rate_disponibili": data.get("rate_disponibili"),
            "numero_rate_max": data.get("numero_rate_max"),
            "riferimento_rottamazione": data.get("riferimento_rottamazione"),
            "stato": "da_gestire",
            "source": "document_ai",
            "source_info": source_info or {},
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        # Evita duplicati
        if doc.get("numero_cartella"):
            existing = await db["adr_definizione_agevolata"].find_one({"numero_cartella": doc["numero_cartella"]})
            if existing:
                return {"status": "duplicate", "message": "Cartella già presente", "id": str(existing.get("_id"))}
        
        result = await db["adr_definizione_agevolata"].insert_one(doc)
        return {"status": "saved", "collection": "adr_definizione_agevolata", "id": str(result.inserted_id)}
        
    except Exception as e:
        logger.error(f"Errore salvataggio cartella esattoriale: {e}")
        return {"status": "error", "message": str(e)}


async def save_delibera_inps_to_gestionale(db, data: Dict[str, Any], source_info: Dict[str, Any] = None) -> Dict[str, Any]:
    """Salva delibera INPS nella collection delibere_fonsi."""
    try:
        azienda = data.get("azienda", {})
        periodo = data.get("periodo_riferimento", {})
        
        doc = {
            "numero_protocollo": data.get("numero_protocollo"),
            "data_documento": parse_date(data.get("data_documento")),
            "tipo_comunicazione": data.get("tipo_comunicazione"),
            "oggetto": data.get("oggetto"),
            "azienda_denominazione": azienda.get("denominazione"),
            "azienda_cf": azienda.get("codice_fiscale"),
            "matricola_inps": azienda.get("matricola_inps"),
            "sede_inps": data.get("sede_inps"),
            "importo_totale": parse_amount(data.get("importo_totale")),
            "periodo_da": parse_date(periodo.get("da")),
            "periodo_a": parse_date(periodo.get("a")),
            "numero_lavoratori": data.get("numero_lavoratori"),
            "ore_autorizzate": data.get("ore_autorizzate"),
            "causale": data.get("causale"),
            "esito": data.get("esito"),
            "source": "document_ai",
            "source_info": source_info or {},
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        # Evita duplicati
        if doc.get("numero_protocollo"):
            existing = await db["delibere_fonsi"].find_one({"numero_protocollo": doc["numero_protocollo"]})
            if existing:
                return {"status": "duplicate", "message": "Delibera già presente", "id": str(existing.get("_id"))}
        
        result = await db["delibere_fonsi"].insert_one(doc)
        return {"status": "saved", "collection": "delibere_fonsi", "id": str(result.inserted_id)}
        
    except Exception as e:
        logger.error(f"Errore salvataggio delibera INPS: {e}")
        return {"status": "error", "message": str(e)}


async def save_fattura_to_gestionale(db, data: Dict[str, Any], source_info: Dict[str, Any] = None) -> Dict[str, Any]:
    """Salva fattura nella collection invoices."""
    try:
        fornitore = data.get("fornitore", {})
        cliente = data.get("cliente", {})
        
        doc = {
            "numero_fattura": data.get("numero_fattura"),
            "data_fattura": parse_date(data.get("data_fattura")),
            "fornitore_denominazione": fornitore.get("denominazione"),
            "fornitore_piva": fornitore.get("partita_iva"),
            "fornitore_cf": fornitore.get("codice_fiscale"),
            "cliente_denominazione": cliente.get("denominazione"),
            "cliente_piva": cliente.get("partita_iva"),
            "cliente_cf": cliente.get("codice_fiscale"),
            "imponibile": parse_amount(data.get("imponibile")),
            "iva": parse_amount(data.get("iva")),
            "totale": parse_amount(data.get("totale")),
            "aliquota_iva": data.get("aliquota_iva"),
            "metodo_pagamento": data.get("metodo_pagamento"),
            "scadenza_pagamento": parse_date(data.get("scadenza_pagamento")),
            "descrizione_righe": data.get("descrizione_righe", []),
            "stato": "in_attesa_conferma",
            "source": "document_ai",
            "source_info": source_info or {},
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        # Evita duplicati
        existing = await db["invoices"].find_one({
            "numero_fattura": doc["numero_fattura"],
            "fornitore_piva": doc["fornitore_piva"],
            "data_fattura": doc["data_fattura"]
        })
        
        if existing:
            return {"status": "duplicate", "message": "Fattura già presente", "id": str(existing.get("_id"))}
        
        result = await db["invoices"].insert_one(doc)
        return {"status": "saved", "collection": "invoices", "id": str(result.inserted_id)}
        
    except Exception as e:
        logger.error(f"Errore salvataggio fattura: {e}")
        return {"status": "error", "message": str(e)}


# Mapping tipo documento -> funzione di salvataggio
SAVE_FUNCTIONS = {
    "F24": save_f24_to_gestionale,
    "BUSTA_PAGA": save_busta_paga_to_gestionale,
    "BONIFICO": save_bonifico_to_gestionale,
    "ESTRATTO_CONTO": save_estratto_conto_to_gestionale,
    "VERBALE": save_verbale_to_gestionale,
    "CARTELLA_ESATTORIALE": save_cartella_esattoriale_to_gestionale,
    "DELIBERA_INPS": save_delibera_inps_to_gestionale,
    "FATTURA": save_fattura_to_gestionale
}


async def save_extracted_data_to_gestionale(
    db, 
    extracted_data: Dict[str, Any],
    source_info: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Salva i dati estratti nella collection appropriata del gestionale.
    
    Args:
        db: Database MongoDB
        extracted_data: Dati estratti dal documento (output di extract_structured_data)
        source_info: Informazioni sulla fonte (filename, email_id, etc.)
    
    Returns:
        Risultato del salvataggio
    """
    if not extracted_data.get("success"):
        return {"status": "error", "message": "Dati non validi per il salvataggio"}
    
    data = extracted_data.get("data", {})
    tipo_documento = data.get("tipo_documento", "").upper()
    
    save_func = SAVE_FUNCTIONS.get(tipo_documento)
    
    if not save_func:
        logger.warning(f"Tipo documento non supportato per salvataggio: {tipo_documento}")
        return {
            "status": "unsupported",
            "message": f"Tipo documento '{tipo_documento}' non supportato per salvataggio automatico",
            "tipo_documento": tipo_documento
        }
    
    return await save_func(db, data, source_info)
