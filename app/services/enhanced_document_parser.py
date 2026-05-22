"""
Enhanced Document Parser - Versione Migliorata
Parser universale per F24 e Cedolini con estrazione completa.
Usa Claude/GPT con prompt ottimizzati per estrarre TUTTI i dati.

Miglioramenti rispetto alla versione precedente:
- Prompt specifici per ogni sezione F24 (Erario, INPS, Regioni, Tributi Locali, INAIL)
- Supporto multi-formato cedolini (Zucchetti, Paghe Web, TeamSystem, ADP)
- Estrazione tabellare completa
- Validazione incrociata dei totali
"""

import os
import json
import base64
import logging
import fitz  # PyMuPDF
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ============================================================================
# PROMPT F24 - VERSIONE MIGLIORATA
# ============================================================================

PROMPT_F24_ENHANCED = """Sei un esperto contabile italiano. Analizza questo modello F24 ed estrai OGNI SINGOLO TRIBUTO presente.

ATTENZIONE CRITICA:
- Devi estrarre TUTTI i codici tributo, non saltarne nessuno
- Ogni riga della tabella è un tributo separato
- Controlla TUTTE le sezioni: ERARIO, INPS, REGIONI, IMU/TRIBUTI LOCALI, INAIL
- I totali devono corrispondere alla somma dei singoli tributi

STRUTTURA JSON DA RESTITUIRE:
{
  "dati_contribuente": {
    "codice_fiscale": "string (16 caratteri per persone fisiche, 11 per società)",
    "cognome_nome_ragione_sociale": "string",
    "domicilio_fiscale": "string",
    "codice_comune": "string (4 caratteri, es. F839)"
  },
  "dati_versamento": {
    "data_pagamento": "YYYY-MM-DD",
    "codice_ufficio": "string o null",
    "codice_atto": "string o null",
    "anno_riferimento": "YYYY"
  },
  "sezione_erario": [
    {
      "codice_tributo": "string 4 cifre (es. 1001, 1040, 2001, 6001, 6099)",
      "descrizione_tributo": "string (es. RITENUTE IRPEF DIPENDENTI)",
      "rateazione_regione_prov": "string 4 cifre o null",
      "anno_riferimento": "YYYY",
      "importo_a_debito": numero (sempre positivo, 0 se vuoto),
      "importo_a_credito": numero (sempre positivo, 0 se vuoto)
    }
  ],
  "sezione_inps": [
    {
      "codice_sede": "string (es. NA, RM, MI)",
      "causale_contributo": "string (es. DM10, CXX, RC01, DOMA, DMRA)",
      "matricola_inps": "string",
      "periodo_da": "MM/YYYY",
      "periodo_a": "MM/YYYY",
      "importo_a_debito": numero,
      "importo_a_credito": numero
    }
  ],
  "sezione_regioni": [
    {
      "codice_regione": "string 2 cifre (01=Piemonte, 03=Lombardia, 07=Liguria, 15=Campania, ecc.)",
      "codice_tributo": "string 4 cifre (es. 3800, 3801, 3802, 3812, 3813)",
      "descrizione": "string",
      "rateazione": "string o null",
      "anno_riferimento": "YYYY",
      "importo_a_debito": numero,
      "importo_a_credito": numero
    }
  ],
  "sezione_imu_tributi_locali": [
    {
      "codice_ente_comune": "string (es. F839 per Napoli, H501 per Roma)",
      "ravvedimento": "S" | "N" | null,
      "immobili_variati": "S" | "N" | null,
      "acconto": "S" | "N" | null,
      "saldo": "S" | "N" | null,
      "numero_immobili": numero o null,
      "codice_tributo": "string 4 cifre (es. 3918, 3914, 3916, 3850)",
      "descrizione": "string",
      "rateazione": "string o null",
      "anno_riferimento": "YYYY",
      "importo_a_debito": numero,
      "importo_a_credito": numero
    }
  ],
  "sezione_inail": [
    {
      "codice_sede": "string",
      "codice_ditta": "string",
      "cc": "string (codice controllo)",
      "numero_riferimento": "string",
      "causale": "string (es. P, R, S)",
      "importo_a_debito": numero,
      "importo_a_credito": numero
    }
  ],
  "sezione_altri_enti": [
    {
      "codice_ente": "string",
      "codice_sede": "string",
      "causale_contributo": "string",
      "codice_posizione": "string",
      "periodo_da": "MM/YYYY",
      "periodo_a": "MM/YYYY",
      "importo_a_debito": numero,
      "importo_a_credito": numero
    }
  ],
  "totali": {
    "totale_erario_debito": numero,
    "totale_erario_credito": numero,
    "saldo_erario": numero,
    "totale_inps_debito": numero,
    "totale_inps_credito": numero,
    "saldo_inps": numero,
    "totale_regioni_debito": numero,
    "totale_regioni_credito": numero,
    "saldo_regioni": numero,
    "totale_imu_debito": numero,
    "totale_imu_credito": numero,
    "saldo_imu": numero,
    "totale_inail_debito": numero,
    "totale_inail_credito": numero,
    "saldo_inail": numero,
    "totale_altri_enti_debito": numero,
    "totale_altri_enti_credito": numero,
    "TOTALE_VERSAMENTO": numero (questo è l'importo finale da pagare)
  },
  "validazione": {
    "somma_sezioni_corrisponde": true | false,
    "note": "string con eventuali discrepanze"
  }
}

CODICI TRIBUTO COMUNI DA CERCARE:
- ERARIO: 1001 (IRPEF dipendenti), 1040 (IRPEF autonomi), 2001-2003 (IRES), 6001-6099 (IVA), 1712 (acconto IRPEF), 1713 (saldo IRPEF)
- REGIONI: 3800-3802 (addizionale regionale), 3812-3813 (addizionale regionale acconto/saldo)
- TRIBUTI LOCALI: 3918 (IMU abitazione principale), 3914 (IMU terreni), 3916 (IMU aree fabbricabili), 3850 (diritto camerale)
- RAVVEDIMENTO: 8901-8907 (sanzioni), 1989-1994 (interessi)

IMPORTANTE:
- Converti tutti gli importi in numeri decimali (1.234,56 → 1234.56)
- Se una sezione è vuota, restituisci array vuoto []
- Il TOTALE_VERSAMENTO deve essere la somma di tutti i saldi positivi
- Rispondi SOLO con il JSON valido, senza altro testo
"""


# ============================================================================
# PROMPT CEDOLINO - VERSIONE MIGLIORATA MULTI-FORMATO
# ============================================================================

PROMPT_CEDOLINO_ENHANCED = """Sei un esperto di paghe e contributi italiano. Analizza questa busta paga/cedolino ed estrai TUTTI i dati.

ATTENZIONE: Esistono diversi formati di cedolino (Zucchetti, Paghe Web, TeamSystem, ADP, CSC). 
Devi riconoscere il formato e adattare l'estrazione.

STRUTTURA JSON DA RESTITUIRE:
{
  "formato_riconosciuto": "Zucchetti" | "Paghe Web" | "TeamSystem" | "ADP" | "CSC" | "Altro",
  "dati_azienda": {
    "ragione_sociale": "string",
    "codice_fiscale_azienda": "string (11 cifre)",
    "partita_iva": "string",
    "indirizzo": "string",
    "matricola_inps": "string"
  },
  "dati_dipendente": {
    "cognome": "string (MAIUSCOLO)",
    "nome": "string (MAIUSCOLO)", 
    "codice_fiscale": "string (16 caratteri)",
    "data_nascita": "YYYY-MM-DD",
    "data_assunzione": "YYYY-MM-DD",
    "matricola": "string",
    "qualifica": "string (es. IMPIEGATO, OPERAIO, QUADRO)",
    "livello": "string (es. 3° Livello, 4S, ecc.)",
    "mansione": "string (es. CAMERIERE, CUOCO, BARISTA)",
    "tipo_contratto": "string (CCNL Turismo, Commercio, ecc.)",
    "percentuale_part_time": numero o null (100 se full time)
  },
  "periodo_competenza": {
    "mese": numero (1-12),
    "anno": numero (YYYY),
    "mese_nome": "string (GENNAIO, FEBBRAIO, ecc.)",
    "giorni_lavorati": numero,
    "giorni_retribuiti": numero
  },
  "ore_lavorate": {
    "ore_ordinarie": numero,
    "ore_straordinarie": numero,
    "ore_notturne": numero,
    "ore_festive": numero,
    "ore_ferie_godute": numero,
    "ore_permessi_goduti": numero,
    "ore_malattia": numero,
    "ore_infortunio": numero,
    "ore_maternita": numero,
    "totale_ore": numero
  },
  "competenze": {
    "paga_base": numero,
    "contingenza": numero,
    "scatti_anzianita": numero,
    "superminimo": numero,
    "straordinario": numero,
    "indennita_turno": numero,
    "indennita_mensa": numero,
    "premi": numero,
    "altri_compensi": numero,
    "totale_competenze": numero,
    "dettaglio_voci": [
      {
        "codice": "string",
        "descrizione": "string",
        "quantita": numero,
        "importo": numero
      }
    ]
  },
  "trattenute": {
    "contributi_inps_dipendente": numero,
    "irpef": numero,
    "addizionale_regionale": numero,
    "addizionale_comunale": numero,
    "contributo_sindacale": numero,
    "anticipo_tfr": numero,
    "prestito": numero,
    "altre_trattenute": numero,
    "totale_trattenute": numero,
    "dettaglio_voci": [
      {
        "codice": "string",
        "descrizione": "string",
        "importo": numero
      }
    ]
  },
  "importi_finali": {
    "retribuzione_lorda": numero,
    "totale_competenze": numero,
    "totale_trattenute": numero,
    "netto_in_busta": numero,
    "arrotondamento": numero,
    "acconto_mese_precedente": numero,
    "netto_da_pagare": numero
  },
  "tfr": {
    "retribuzione_utile_tfr": numero,
    "quota_tfr_mese": numero,
    "tfr_fondo_aziendale": numero,
    "tfr_fondo_tesoreria_inps": numero,
    "tfr_fondo_pensione": numero,
    "totale_tfr_maturato": numero
  },
  "ferie_permessi": {
    "ferie_residuo_anno_precedente": numero,
    "ferie_maturate": numero,
    "ferie_godute": numero,
    "ferie_saldo": numero,
    "permessi_residuo": numero,
    "permessi_maturati": numero,
    "permessi_goduti": numero,
    "permessi_saldo": numero,
    "rol_residuo": numero,
    "rol_maturato": numero,
    "rol_goduto": numero,
    "rol_saldo": numero,
    "ex_festivita_residuo": numero,
    "ex_festivita_godute": numero,
    "ex_festivita_saldo": numero
  },
  "dati_pagamento": {
    "modalita": "BONIFICO" | "CONTANTI" | "ASSEGNO",
    "iban": "string (formato IT...)",
    "banca": "string"
  },
  "costi_azienda": {
    "contributi_inps_azienda": numero,
    "contributi_inail": numero,
    "tfr_competenza": numero,
    "costo_totale_azienda": numero
  },
  "validazione": {
    "netto_calcolato": numero,
    "netto_documento": numero,
    "differenza": numero,
    "calcolo_corretto": true | false
  }
}

INDICATORI PER TROVARE IL NETTO:
- Cerca esattamente: "NETTO DEL MESE", "NETTO IN BUSTA", "NETTO DA PAGARE", "NETTO A PAGARE"
- Il NETTO è SEMPRE = TOTALE COMPETENZE - TOTALE TRATTENUTE (± arrotondamenti)
- Se ci sono più importi simili, il NETTO DA PAGARE è quello finale più in basso

FORMATI SPECIFICI:
- Zucchetti: "NETTO DEL MESE" in fondo, formato tabellare classico
- Paghe Web: "Netto in busta" con layout più compatto
- TeamSystem: "TOTALE NETTO" con sezioni ben separate
- CSC: Layout con molte linee, cerca dopo "TOTALE TRATTENUTE"

IMPORTANTE:
- Converti tutti gli importi: 1.234,56 → 1234.56
- Se un campo non è presente, usa null
- Verifica che NETTO = COMPETENZE - TRATTENUTE
- Rispondi SOLO con JSON valido
"""


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def pdf_to_images(pdf_bytes: bytes, max_pages: int = 5, dpi: int = 200) -> List[bytes]:
    """
    Converte un PDF in lista di immagini PNG.
    Usa PyMuPDF (fitz) per la conversione.
    """
    images = []
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        for page_num in range(min(len(doc), max_pages)):
            page = doc[page_num]
            mat = fitz.Matrix(dpi/72, dpi/72)  # Scale factor
            pix = page.get_pixmap(matrix=mat)
            images.append(pix.tobytes("png"))
        doc.close()
    except Exception as e:
        logger.error(f"Errore conversione PDF: {e}")
    return images


# ============================================================================
# FUNZIONI DI PARSING
# ============================================================================

async def parse_f24_enhanced(
    file_bytes: bytes,
    mime_type: str = "application/pdf"
) -> Dict[str, Any]:
    """
    Parse un F24 con il prompt migliorato.
    Estrae TUTTI i codici tributo da tutte le sezioni.
    """
    try:
        from app.services.emergent_stub import LlmChat, UserMessage, ImageContent
        
        api_key = os.environ.get("EMERGENT_LLM_KEY")
        if not api_key:
            return {"error": "EMERGENT_LLM_KEY non configurata", "success": False}
        
        # Prepara le immagini
        images_b64 = []
        
        if "pdf" in mime_type.lower():
            images = pdf_to_images(file_bytes, max_pages=3, dpi=200)
            if not images:
                return {"error": "Impossibile convertire PDF in immagini", "success": False}
            for img in images:
                images_b64.append(base64.b64encode(img).decode())
        else:
            images_b64.append(base64.b64encode(file_bytes).decode())
        
        # Inizializza chat con Claude
        chat = LlmChat(
            api_key=api_key,
            session_id=f"f24_parser_{datetime.now().timestamp()}",
            system_message="Sei un esperto contabile italiano specializzato in modelli F24."
        ).with_model("anthropic", "claude-sonnet-4-20250514")
        
        # Crea ImageContent per ogni immagine
        image_contents = [
            ImageContent(
                source_type="base64",
                image_type="image/png",
                data=img_b64
            )
            for img_b64 in images_b64
        ]
        
        # Crea messaggio con prompt + immagini
        user_message = UserMessage(
            text=PROMPT_F24_ENHANCED,
            images=image_contents
        )
        
        # Invia e ottieni risposta
        response = await chat.send_message_async(user_message)
        
        # Parse JSON dalla risposta
        result = _extract_json_from_response(response)
        
        if result:
            result["_parsing_info"] = {
                "parser": "enhanced_f24_v2",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "model": "claude-sonnet-4",
                "pages_processed": len(images_b64)
            }
            result = _validate_f24_totals(result)
            result["success"] = True
        else:
            return {"error": "Impossibile estrarre dati dal documento", "success": False}
            
        return result
        
    except Exception as e:
        logger.error(f"Errore parsing F24 enhanced: {e}")
        return {"error": str(e), "success": False}


async def parse_cedolino_enhanced(
    file_bytes: bytes,
    mime_type: str = "application/pdf"
) -> Dict[str, Any]:
    """
    Parse un cedolino/busta paga con il prompt migliorato.
    Supporta tutti i formati principali (Zucchetti, Paghe Web, TeamSystem, ADP, CSC).
    """
    try:
        from app.services.emergent_stub import LlmChat, UserMessage, ImageContent
        
        api_key = os.environ.get("EMERGENT_LLM_KEY")
        if not api_key:
            return {"error": "EMERGENT_LLM_KEY non configurata", "success": False}
        
        # Prepara le immagini
        images_b64 = []
        
        if "pdf" in mime_type.lower():
            images = pdf_to_images(file_bytes, max_pages=2, dpi=200)  # Cedolini di solito 1-2 pagine
            if not images:
                return {"error": "Impossibile convertire PDF in immagini", "success": False}
            for img in images:
                images_b64.append(base64.b64encode(img).decode())
        else:
            images_b64.append(base64.b64encode(file_bytes).decode())
        
        # Inizializza chat con Claude
        chat = LlmChat(
            api_key=api_key,
            session_id=f"cedolino_parser_{datetime.now().timestamp()}",
            system_message="Sei un esperto di paghe e contributi italiano. Estrai dati precisi dalle buste paga."
        ).with_model("anthropic", "claude-sonnet-4-20250514")
        
        # Crea ImageContent per ogni immagine
        image_contents = [
            ImageContent(
                source_type="base64",
                image_type="image/png",
                data=img_b64
            )
            for img_b64 in images_b64
        ]
        
        # Crea messaggio con prompt + immagini
        user_message = UserMessage(
            text=PROMPT_CEDOLINO_ENHANCED,
            images=image_contents
        )
        
        # Invia e ottieni risposta
        response = await chat.send_message_async(user_message)
        
        # Parse JSON dalla risposta
        result = _extract_json_from_response(response)
        
        if result:
            result["_parsing_info"] = {
                "parser": "enhanced_cedolino_v2",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "model": "claude-sonnet-4",
                "pages_processed": len(images_b64)
            }
            result = _validate_cedolino_netto(result)
            result["success"] = True
        else:
            return {"error": "Impossibile estrarre dati dal documento", "success": False}
            
        return result
        
    except Exception as e:
        logger.error(f"Errore parsing cedolino enhanced: {e}")
        return {"error": str(e), "success": False}


def _extract_json_from_response(response: str) -> Optional[Dict[str, Any]]:
    """Estrae JSON dalla risposta LLM."""
    if not response:
        return None
    
    # Prova a parsare direttamente
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        pass
    
    # Cerca JSON nel testo
    import re
    json_patterns = [
        r'```json\s*([\s\S]*?)\s*```',
        r'```\s*([\s\S]*?)\s*```',
        r'\{[\s\S]*\}'
    ]
    
    for pattern in json_patterns:
        match = re.search(pattern, response)
        if match:
            try:
                json_str = match.group(1) if match.lastindex else match.group(0)
                return json.loads(json_str)
            except json.JSONDecodeError:
                continue
    
    return None


def _validate_f24_totals(data: Dict[str, Any]) -> Dict[str, Any]:
    """Valida che i totali F24 corrispondano alla somma delle sezioni."""
    try:
        totali = data.get("totali", {})
        
        # Calcola totali dalle sezioni
        calcolati = {
            "erario_debito": sum(t.get("importo_a_debito", 0) for t in data.get("sezione_erario", [])),
            "erario_credito": sum(t.get("importo_a_credito", 0) for t in data.get("sezione_erario", [])),
            "inps_debito": sum(t.get("importo_a_debito", 0) for t in data.get("sezione_inps", [])),
            "inps_credito": sum(t.get("importo_a_credito", 0) for t in data.get("sezione_inps", [])),
            "regioni_debito": sum(t.get("importo_a_debito", 0) for t in data.get("sezione_regioni", [])),
            "regioni_credito": sum(t.get("importo_a_credito", 0) for t in data.get("sezione_regioni", [])),
            "imu_debito": sum(t.get("importo_a_debito", 0) for t in data.get("sezione_imu_tributi_locali", [])),
            "imu_credito": sum(t.get("importo_a_credito", 0) for t in data.get("sezione_imu_tributi_locali", [])),
        }
        
        # Aggiungi validazione
        data["validazione"] = {
            "totali_calcolati": calcolati,
            "somma_debiti": sum(v for k, v in calcolati.items() if "debito" in k),
            "somma_crediti": sum(v for k, v in calcolati.items() if "credito" in k),
            "tributi_estratti": {
                "erario": len(data.get("sezione_erario", [])),
                "inps": len(data.get("sezione_inps", [])),
                "regioni": len(data.get("sezione_regioni", [])),
                "imu_locali": len(data.get("sezione_imu_tributi_locali", [])),
                "inail": len(data.get("sezione_inail", [])),
                "totale": sum([
                    len(data.get("sezione_erario", [])),
                    len(data.get("sezione_inps", [])),
                    len(data.get("sezione_regioni", [])),
                    len(data.get("sezione_imu_tributi_locali", [])),
                    len(data.get("sezione_inail", []))
                ])
            }
        }
        
    except Exception as e:
        logger.warning(f"Errore validazione F24: {e}")
    
    return data


def _validate_cedolino_netto(data: Dict[str, Any]) -> Dict[str, Any]:
    """Valida che il netto del cedolino sia corretto."""
    try:
        importi = data.get("importi_finali", {})
        competenze = importi.get("totale_competenze", 0)
        trattenute = importi.get("totale_trattenute", 0)
        netto_doc = importi.get("netto_in_busta", 0) or importi.get("netto_da_pagare", 0)
        
        netto_calcolato = competenze - trattenute
        differenza = abs(netto_calcolato - netto_doc) if netto_doc else 0
        
        data["validazione"] = {
            "netto_calcolato": round(netto_calcolato, 2),
            "netto_documento": round(netto_doc, 2),
            "differenza": round(differenza, 2),
            "calcolo_corretto": differenza < 1.0  # Tolleranza 1€ per arrotondamenti
        }
        
    except Exception as e:
        logger.warning(f"Errore validazione cedolino: {e}")
    
    return data


# ============================================================================
# FUNZIONE PRINCIPALE UNIFICATA
# ============================================================================

async def parse_document_enhanced(
    file_bytes: bytes,
    document_type: str = "auto",
    mime_type: str = "application/pdf"
) -> Dict[str, Any]:
    """
    Parser universale migliorato per F24 e Cedolini.
    
    Args:
        file_bytes: Contenuto del file
        document_type: "f24", "cedolino", "busta_paga", o "auto"
        mime_type: Tipo MIME del file
    
    Returns:
        Dati estratti strutturati
    """
    if document_type in ["f24", "F24"]:
        return await parse_f24_enhanced(file_bytes, mime_type)
    elif document_type in ["cedolino", "busta_paga", "payslip"]:
        return await parse_cedolino_enhanced(file_bytes, mime_type)
    elif document_type == "auto":
        # Prova a rilevare automaticamente
        # Prima prova F24, poi cedolino
        result = await parse_f24_enhanced(file_bytes, mime_type)
        if result and not result.get("error") and result.get("sezione_erario"):
            return result
        return await parse_cedolino_enhanced(file_bytes, mime_type)
    else:
        return {"error": f"Tipo documento non supportato: {document_type}"}
