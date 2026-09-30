"""
Enhanced Document Parser - lettura AI dei cedolini
(la parte F24 e' stata tolta: i modelli hanno un solo lettore, `parser_f24`).

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

async def parse_cedolino_enhanced(
    file_bytes: bytes,
    mime_type: str = "application/pdf"
) -> Dict[str, Any]:
    """
    Parse un cedolino/busta paga con il prompt migliorato.
    Supporta tutti i formati principali (Zucchetti, Paghe Web, TeamSystem, ADP, CSC).
    """
    try:
        from app.services.anthropic_llm_client import (
            LlmChat, UserMessage, ImageContent, document_model_name,
        )
        
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            return {"error": "ANTHROPIC_API_KEY non configurata", "success": False}
        
        # Prepara le immagini
        images_b64 = []
        
        if "pdf" in mime_type.lower():
            images = pdf_to_images(file_bytes, max_pages=4, dpi=200)
            if not images:
                return {"error": "Impossibile convertire PDF in immagini", "success": False}
            for img in images:
                images_b64.append(base64.b64encode(img).decode())
        else:
            images_b64.append(base64.b64encode(file_bytes).decode())
        
        # Inizializza chat con Claude
        model_name = document_model_name()
        chat = LlmChat(
            api_key=api_key,
            session_id=f"cedolino_parser_{datetime.now().timestamp()}",
            system_prompt="Sei un esperto di paghe e contributi italiano. Estrai dati precisi dalle buste paga."
        ).with_model("anthropic", model_name)
        
        # Crea ImageContent per ogni immagine
        image_contents = [
            ImageContent(image_data=img_b64, mime_type="image/png")
            for img_b64 in images_b64
        ]
        
        # Crea messaggio con prompt + immagini
        user_message = UserMessage(
            content=PROMPT_CEDOLINO_ENHANCED,
            images=image_contents
        )

        # Invia e ottieni risposta
        response = await chat.send_message(user_message)
        
        # Parse JSON dalla risposta
        result = _extract_json_from_response(response)
        
        if result:
            result["_parsing_info"] = {
                "parser": "enhanced_cedolino_v2",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "model": model_name,
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
