"""
Parser F24 con Gemini AI
Usa Gemini per estrarre dati da PDF F24 con OCR integrato.
Più robusto del parsing basato su coordinate.
"""
import os
import json
import asyncio
import logging
from typing import Dict, Any
from pathlib import Path
from dotenv import load_dotenv

# Carica .env dal percorso corretto
env_path = Path(__file__).resolve().parent.parent.parent / "backend" / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
    # Carica .env
    load_dotenv()

logger = logging.getLogger(__name__)

# Prompt per Gemini
PROMPT_ESTRAZIONE_F24 = """Analizza questo PDF F24 italiano ed estrai TUTTI i dati in formato JSON strutturato.

IMPORTANTE: Estrai OGNI singolo tributo presente nel documento, non saltare nulla.

Struttura JSON richiesta:
{
    "dati_generali": {
        "codice_fiscale": "string (11 o 16 caratteri)",
        "ragione_sociale": "string",
        "data_versamento": "YYYY-MM-DD",
        "tipo_f24": "F24 / F24 Semplificato / F24 Ordinario"
    },
    "sezione_erario": [
        {
            "codice_tributo": "4 cifre (es. 1001, 6001, 2003)",
            "rateazione": "4 cifre o vuoto",
            "anno": "YYYY",
            "importo_debito": numero,
            "importo_credito": numero
        }
    ],
    "sezione_inps": [
        {
            "codice_sede": "string",
            "causale": "string (es. DM10, CXX, RC01)",
            "matricola": "string",
            "periodo_da": "MM/YYYY",
            "periodo_a": "MM/YYYY",
            "importo_debito": numero,
            "importo_credito": numero
        }
    ],
    "sezione_regioni": [
        {
            "codice_regione": "2 cifre (01-21)",
            "codice_tributo": "4 cifre (es. 3800, 3812, 3813, 8907, 1993)",
            "rateazione": "4 cifre o vuoto",
            "anno": "YYYY",
            "importo_debito": numero,
            "importo_credito": numero
        }
    ],
    "sezione_tributi_locali": [
        {
            "codice_ente": "string (es. NA, RM) o codice comune (es. F839)",
            "codice_tributo": "4 cifre (es. 3850, 3918, 3847)",
            "rateazione": "4 cifre o vuoto",
            "anno": "YYYY",
            "numero_immobili": numero o null,
            "importo_debito": numero,
            "importo_credito": numero
        }
    ],
    "sezione_inail": [
        {
            "codice_sede": "string",
            "codice_ditta": "string",
            "cc": "string",
            "numero_riferimento": "string",
            "causale": "string",
            "importo_debito": numero,
            "importo_credito": numero
        }
    ],
    "totali": {
        "totale_debito": numero,
        "totale_credito": numero,
        "saldo_finale": numero
    }
}

REGOLE IMPORTANTI:
1. I codici IRAP (3800, 3812, 3813, 8907, 1993) vanno in sezione_regioni
2. I codici Camera di Commercio (3850, 3851, 3852) vanno in sezione_tributi_locali
3. I codici IMU (3912-3930) vanno in sezione_tributi_locali
4. I codici IVA (6001-6099, 6201-6312) vanno in sezione_erario
5. I codici IRES (2001-2003) vanno in sezione_erario
6. I codici IRPEF ritenute (1001, 1002, 1012, 1040) vanno in sezione_erario
7. Gli importi sono in formato italiano (virgola per decimali), converti in numeri float

Rispondi SOLO con il JSON, senza markdown o altro testo."""


async def parse_f24_with_gemini(pdf_path: str) -> Dict[str, Any]:
    """
    Parsa un PDF F24 usando Gemini AI.
    
    Args:
        pdf_path: Percorso al file PDF
        
    Returns:
        Dict con i dati estratti dal F24
    """
    from emergentintegrations.llm.chat import LlmChat, UserMessage, FileContentWithMimeType
    
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        raise ValueError("EMERGENT_LLM_KEY non configurata")
    
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"File non trovato: {pdf_path}")
    
    try:
        # Inizializza chat con Claude (supportato dalla chiave Emergent)
        # Claude Sonnet 4.5 supporta analisi di PDF
        chat = LlmChat(
            api_key=api_key,
            session_id=f"f24_parse_{os.path.basename(pdf_path)}",
            system_message="Sei un esperto di documenti fiscali italiani. Estrai dati da PDF F24 con precisione."
        ).with_model("anthropic", "claude-sonnet-4-20250514")
        
        # Prepara il file PDF
        pdf_file = FileContentWithMimeType(
            file_path=pdf_path,
            mime_type="application/pdf"
        )
        
        # Invia richiesta a Gemini
        user_message = UserMessage(
            text=PROMPT_ESTRAZIONE_F24,
            file_contents=[pdf_file]
        )
        
        response = await chat.send_message(user_message)
        
        # Pulisci la risposta (rimuovi eventuale markdown)
        response_text = response.strip()
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        if response_text.startswith("```"):
            response_text = response_text[3:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]
        response_text = response_text.strip()
        
        # Parse JSON
        try:
            result = json.loads(response_text)
        except json.JSONDecodeError as e:
            logger.error(f"Errore parsing JSON da Gemini: {e}")
            logger.error(f"Risposta: {response_text[:500]}")
            return {"error": f"Errore parsing risposta Gemini: {e}"}
        
        # Aggiungi descrizioni ai codici tributo
        result = _add_descrizioni(result)
        
        # Calcola totali se non presenti
        if "totali" not in result or not result["totali"]:
            result["totali"] = _calcola_totali(result)
        
        return result
        
    except Exception as e:
        logger.error(f"Errore Gemini parse F24: {e}")
        return {"error": str(e)}


def _add_descrizioni(result: Dict[str, Any]) -> Dict[str, Any]:
    """Aggiunge descrizioni ai codici tributo."""
    from app.services.parser_f24 import (
        get_descrizione_tributo, 
        get_descrizione_tributo_regioni,
        get_descrizione_tributo_locale,
        get_descrizione_causale_inps
    )
    
    # Sezione Erario
    for item in result.get("sezione_erario", []):
        if "descrizione" not in item:
            item["descrizione"] = get_descrizione_tributo(item.get("codice_tributo", ""))
    
    # Sezione Regioni
    for item in result.get("sezione_regioni", []):
        if "descrizione" not in item:
            item["descrizione"] = get_descrizione_tributo_regioni(item.get("codice_tributo", ""))
    
    # Sezione Tributi Locali
    for item in result.get("sezione_tributi_locali", []):
        if "descrizione" not in item:
            item["descrizione"] = get_descrizione_tributo_locale(item.get("codice_tributo", ""))
    
    # Sezione INPS
    for item in result.get("sezione_inps", []):
        if "descrizione" not in item:
            item["descrizione"] = get_descrizione_causale_inps(item.get("causale", ""))
    
    # Sezione INAIL
    for item in result.get("sezione_inail", []):
        if "descrizione" not in item:
            item["descrizione"] = f"Premio INAIL - {item.get('causale', '')}"
    
    return result


def _calcola_totali(result: Dict[str, Any]) -> Dict[str, float]:
    """Calcola totali da tutte le sezioni."""
    totale_debito = 0.0
    totale_credito = 0.0
    
    for sezione in ["sezione_erario", "sezione_inps", "sezione_regioni", 
                    "sezione_tributi_locali", "sezione_inail"]:
        for item in result.get(sezione, []):
            totale_debito += float(item.get("importo_debito", 0) or 0)
            totale_credito += float(item.get("importo_credito", 0) or 0)
    
    return {
        "totale_debito": round(totale_debito, 2),
        "totale_credito": round(totale_credito, 2),
        "saldo_finale": round(totale_debito - totale_credito, 2)
    }


# Wrapper sincrono per compatibilità
def parse_f24_gemini_sync(pdf_path: str) -> Dict[str, Any]:
    """Versione sincrona del parser Gemini."""
    return asyncio.run(parse_f24_with_gemini(pdf_path))
