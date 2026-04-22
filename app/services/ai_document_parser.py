"""
Parser AI Universale per Documenti
Usa emergentintegrations con OpenAI GPT (vision) per estrarre dati strutturati da PDF.
Supporta: Fatture, F24, Buste Paga

Converte PDF in immagini e le invia a OpenAI per l'analisi usando emergentintegrations.
"""
import os
import json
import base64
import logging
import tempfile
import io
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Prompts specifici per ogni tipo di documento
PROMPT_FATTURA = """Analizza questa fattura e estrai TUTTI i dati in formato JSON strutturato.

Estrai:
{
  "tipo_documento": "fattura" | "nota_credito" | "nota_debito",
  "numero_fattura": "string",
  "data_fattura": "YYYY-MM-DD",
  "fornitore": {
    "denominazione": "string",
    "partita_iva": "string (solo numeri, 11 cifre)",
    "codice_fiscale": "string",
    "indirizzo": "string",
    "cap": "string",
    "citta": "string",
    "provincia": "string"
  },
  "cliente": {
    "denominazione": "string",
    "partita_iva": "string",
    "codice_fiscale": "string"
  },
  "righe": [
    {
      "descrizione": "string (descrizione prodotto/servizio)",
      "quantita": numero,
      "unita_misura": "string",
      "prezzo_unitario": numero,
      "prezzo_totale": numero,
      "aliquota_iva": numero (es: 22, 10, 4, 0),
      "codice_articolo": "string se presente"
    }
  ],
  "totali": {
    "imponibile": numero,
    "iva": numero,
    "totale_fattura": numero
  },
  "pagamento": {
    "modalita": "string (bonifico, contanti, etc)",
    "scadenza": "YYYY-MM-DD",
    "iban": "string se presente"
  },
  "note": "string (eventuali note o causali)"
}

IMPORTANTE:
- Estrai TUTTE le righe prodotto/servizio presenti
- I numeri devono essere in formato decimale (es: 1234.56, non 1.234,56)
- Le date in formato YYYY-MM-DD
- Se un campo non è presente, usa null
- Rispondi SOLO con il JSON, senza altro testo"""

PROMPT_F24 = """Analizza questo documento F24/quietanza F24 e estrai TUTTI i dati in formato JSON strutturato.

Estrai:
{
  "tipo_documento": "f24" | "quietanza_f24",
  "data_pagamento": "YYYY-MM-DD",
  "codice_fiscale": "string (11 cifre per società, 16 caratteri per persone)",
  "ragione_sociale": "string",
  "protocollo_telematico": "string se presente",
  "banca": {
    "nome": "string",
    "abi": "string",
    "cab": "string"
  },
  "sezione_erario": [
    {
      "codice_tributo": "string (4 cifre)",
      "rateazione": "string",
      "periodo_riferimento": "MM/YYYY o YYYY",
      "importo_debito": numero,
      "importo_credito": numero,
      "descrizione": "string (es: Ritenute lavoro dipendente)"
    }
  ],
  "sezione_inps": [
    {
      "codice_sede": "string",
      "causale": "string (DM10, CXX, etc)",
      "matricola": "string",
      "periodo_riferimento": "MM/YYYY",
      "importo_debito": numero,
      "importo_credito": numero
    }
  ],
  "sezione_regioni": [
    {
      "codice_regione": "string",
      "codice_tributo": "string",
      "periodo_riferimento": "string",
      "importo_debito": numero,
      "importo_credito": numero
    }
  ],
  "sezione_imu": [
    {
      "codice_comune": "string",
      "codice_tributo": "string",
      "anno_riferimento": "YYYY",
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

IMPORTANTE:
- Estrai TUTTI i tributi presenti in ogni sezione
- I codici tributo sono di 4 cifre (es: 1001, 3802, 6001)
- I numeri devono essere in formato decimale
- Se un campo non è presente, usa null o array vuoto []
- Rispondi SOLO con il JSON, senza altro testo"""

PROMPT_BUSTA_PAGA = """Analizza questa busta paga/cedolino e estrai TUTTI i dati in formato JSON strutturato.

Estrai:
{
  "tipo_documento": "busta_paga",
  "periodo": {
    "mese": numero (1-12),
    "anno": numero (YYYY),
    "descrizione": "string (es: Dicembre 2024, Tredicesima 2024)"
  },
  "dipendente": {
    "nome": "string",
    "cognome": "string",
    "codice_fiscale": "string",
    "matricola": "string se presente",
    "qualifica": "string",
    "livello": "string"
  },
  "azienda": {
    "denominazione": "string",
    "partita_iva": "string",
    "codice_fiscale": "string"
  },
  "retribuzione": {
    "paga_base": numero,
    "contingenza": numero,
    "scatti_anzianita": numero,
    "superminimo": numero,
    "altri_elementi": numero,
    "ore_ordinarie": numero,
    "ore_straordinario": numero,
    "straordinario_importo": numero,
    "festivita": numero,
    "indennita_varie": numero,
    "lordo_totale": numero
  },
  "trattenute": {
    "inps_dipendente": numero,
    "irpef": numero,
    "addizionale_regionale": numero,
    "addizionale_comunale": numero,
    "altre_trattenute": numero,
    "totale_trattenute": numero
  },
  "netto": {
    "netto_mese": numero,
    "arrotondamento": numero,
    "netto_pagato": numero
  },
  "progressivi": {
    "ferie_maturate": numero (ore o giorni),
    "ferie_godute": numero,
    "ferie_residue": numero,
    "permessi_maturati": numero (ore),
    "permessi_goduti": numero,
    "permessi_residui": numero,
    "rol_maturati": numero (ore),
    "rol_goduti": numero,
    "rol_residui": numero,
    "ex_festivita_maturate": numero,
    "ex_festivita_godute": numero,
    "ex_festivita_residue": numero
  },
  "tfr": {
    "quota_mese": numero,
    "fondo_accantonato": numero,
    "rivalutazione": numero
  },
  "contributi_azienda": {
    "inps_azienda": numero,
    "inail": numero,
    "totale": numero
  }
}

IMPORTANTE:
- Estrai TUTTI i valori presenti nella busta paga
- Presta particolare attenzione a ferie, permessi, ROL e TFR
- I numeri devono essere in formato decimale
- Se un campo non è presente, usa 0 o null
- Rispondi SOLO con il JSON, senza altro testo"""


def pdf_to_images(pdf_bytes: bytes, max_pages: int = 5, dpi: int = 150) -> List[bytes]:
    """
    Converte un PDF in lista di immagini PNG.
    Usa PyMuPDF (fitz) per la conversione.
    
    Args:
        pdf_bytes: Contenuto PDF in bytes
        max_pages: Numero massimo di pagine da convertire
        dpi: Risoluzione immagini
        
    Returns:
        Lista di immagini PNG in bytes
    """
    import fitz  # PyMuPDF
    
    images = []
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        
        for page_num in range(min(len(doc), max_pages)):
            page = doc[page_num]
            # Scala per DPI desiderato (default fitz è 72 DPI)
            zoom = dpi / 72
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat)
            
            # Converti in PNG bytes
            img_bytes = pix.tobytes("png")
            images.append(img_bytes)
        
        doc.close()
        
    except Exception as e:
        logger.error(f"Errore conversione PDF in immagini: {e}")
    
    return images


async def parse_document_with_ai(
    file_path: str = None,
    file_bytes: bytes = None,
    document_type: str = "auto",
    mime_type: str = "application/pdf"
) -> Dict[str, Any]:
    """
    Analizza un documento usando AI (emergentintegrations con OpenAI) e restituisce dati strutturati.
    
    Args:
        file_path: Percorso al file PDF/immagine
        file_bytes: Contenuto del file in bytes
        document_type: "fattura", "f24", "busta_paga" o "auto" per rilevamento automatico
        mime_type: Tipo MIME del file
        
    Returns:
        Dict con i dati estratti strutturati
    """
    from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
    
    # Usa EMERGENT_LLM_KEY per emergentintegrations
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    logger.info(f"Using EMERGENT_LLM_KEY: {api_key[:20] if api_key else 'NOT SET'}...")
    
    if not api_key:
        return {"error": "EMERGENT_LLM_KEY non configurata", "success": False}
    
    try:
        # Leggi il file se abbiamo solo il path
        if file_path and not file_bytes:
            with open(file_path, "rb") as f:
                file_bytes = f.read()
        
        if not file_bytes:
            return {"error": "Nessun contenuto file fornito", "success": False}
        
        # Prepara le immagini
        images_b64 = []
        
        if "pdf" in mime_type.lower():
            # Converti PDF in immagini
            images = pdf_to_images(file_bytes, max_pages=3, dpi=150)
            if not images:
                return {"error": "Impossibile convertire PDF in immagini", "success": False}
            
            for img in images:
                images_b64.append(base64.b64encode(img).decode())
        else:
            # È già un'immagine
            images_b64.append(base64.b64encode(file_bytes).decode())
        
        # Seleziona il prompt appropriato
        if document_type == "auto":
            prompt = """Identifica il tipo di questo documento italiano. Rispondi SOLO con una di queste opzioni esatte:
fattura
f24
busta_paga
altro

Rispondi con UNA SOLA PAROLA senza punteggiatura."""
        elif document_type == "fattura":
            prompt = PROMPT_FATTURA
        elif document_type == "f24":
            prompt = PROMPT_F24
        elif document_type == "busta_paga":
            prompt = PROMPT_BUSTA_PAGA
        else:
            prompt = PROMPT_FATTURA  # Default
        
        # Inizializza chat con emergentintegrations - usa Claude con vision
        # (L'Emergent LLM Key ha accesso solo a modelli Claude)
        chat = LlmChat(
            api_key=api_key,
            session_id=f"doc_parser_{datetime.now().timestamp()}",
            system_message="Sei un esperto parser di documenti contabili italiani. Estrai dati precisi e strutturati in formato JSON."
        ).with_model("anthropic", "claude-sonnet-4-20250514")  # Claude supporta vision
        
        # Crea ImageContent per ogni immagine
        image_contents = [ImageContent(image_base64=img_b64) for img_b64 in images_b64]
        
        # Invia messaggio con immagini - usa file_contents come da playbook
        user_message = UserMessage(
            text=prompt,
            file_contents=image_contents
        )
        
        response = await chat.send_message(user_message)
        response_text = response.strip() if isinstance(response, str) else str(response)
        
        # Se era auto-detection, fai una seconda chiamata con il prompt specifico
        if document_type == "auto":
            detected_type = response_text.lower().strip()
            logger.info(f"Tipo documento rilevato: {detected_type}")
            
            if detected_type in ["fattura", "f24", "busta_paga"]:
                # Richiama con il prompt specifico
                result = await parse_document_with_ai(
                    file_bytes=file_bytes,
                    document_type=detected_type,
                    mime_type=mime_type
                )
                result["detected_type"] = detected_type
                return result
            else:
                return {
                    "error": f"Tipo documento non supportato: {detected_type}",
                    "detected_type": detected_type,
                    "success": False
                }
        
        # Parse JSON dalla risposta
        try:
            # Rimuovi eventuali markdown code blocks
            json_str = response_text
            if json_str.startswith("```json"):
                json_str = json_str[7:]
            if json_str.startswith("```"):
                json_str = json_str[3:]
            if json_str.endswith("```"):
                json_str = json_str[:-3]
            
            parsed_data = json.loads(json_str.strip())
            parsed_data["success"] = True
            parsed_data["parsed_at"] = datetime.now(timezone.utc).isoformat()
            parsed_data["parser"] = "ai_emergent_claude"
            parsed_data["pages_analyzed"] = len(images_b64)
            
            return parsed_data
            
        except json.JSONDecodeError as e:
            logger.error(f"Errore parsing JSON risposta AI: {e}")
            logger.debug(f"Risposta raw: {response_text[:500]}")
            return {
                "error": f"Errore parsing risposta AI: {str(e)}",
                "raw_response": response_text[:1000],
                "success": False
            }
            
    except Exception as e:
        logger.error(f"Errore parse_document_with_ai: {e}")
        import traceback
        return {
            "error": str(e),
            "traceback": traceback.format_exc()[:500],
            "success": False
        }


async def parse_fattura_ai(file_path: str = None, file_bytes: bytes = None) -> Dict[str, Any]:
    """Wrapper per parsing fatture."""
    return await parse_document_with_ai(
        file_path=file_path,
        file_bytes=file_bytes,
        document_type="fattura"
    )


async def parse_f24_ai(file_path: str = None, file_bytes: bytes = None) -> Dict[str, Any]:
    """Wrapper per parsing F24."""
    return await parse_document_with_ai(
        file_path=file_path,
        file_bytes=file_bytes,
        document_type="f24"
    )


async def parse_busta_paga_ai(file_path: str = None, file_bytes: bytes = None) -> Dict[str, Any]:
    """Wrapper per parsing buste paga."""
    return await parse_document_with_ai(
        file_path=file_path,
        file_bytes=file_bytes,
        document_type="busta_paga"
    )


async def batch_parse_documents(
    file_paths: List[str],
    document_type: str = "auto"
) -> List[Dict[str, Any]]:
    """
    Parsing batch di documenti.
    
    Args:
        file_paths: Lista di percorsi file
        document_type: Tipo documento o "auto"
        
    Returns:
        Lista di risultati parsing
    """
    results = []
    for path in file_paths:
        try:
            result = await parse_document_with_ai(
                file_path=path,
                document_type=document_type
            )
            result["file_path"] = path
            result["file_name"] = os.path.basename(path)
            results.append(result)
        except Exception as e:
            results.append({
                "file_path": path,
                "file_name": os.path.basename(path),
                "error": str(e),
                "success": False
            })
    return results


def convert_ai_fattura_to_db_format(ai_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Converte i dati estratti dall'AI nel formato database esistente.
    """
    if not ai_data.get("success"):
        return ai_data
    
    return {
        "numero_fattura": ai_data.get("numero_fattura"),
        "data_fattura": ai_data.get("data_fattura"),
        "tipo_documento": ai_data.get("tipo_documento", "fattura"),
        "fornitore": ai_data.get("fornitore", {}).get("denominazione"),
        "fornitore_piva": ai_data.get("fornitore", {}).get("partita_iva"),
        "fornitore_cf": ai_data.get("fornitore", {}).get("codice_fiscale"),
        "fornitore_indirizzo": ai_data.get("fornitore", {}).get("indirizzo"),
        "cliente": ai_data.get("cliente", {}).get("denominazione"),
        "cliente_piva": ai_data.get("cliente", {}).get("partita_iva"),
        "imponibile": ai_data.get("totali", {}).get("imponibile", 0),
        "iva": ai_data.get("totali", {}).get("iva", 0),
        "totale": ai_data.get("totali", {}).get("totale_fattura", 0),
        "righe": ai_data.get("righe", []),
        "scadenza_pagamento": ai_data.get("pagamento", {}).get("scadenza"),
        "modalita_pagamento": ai_data.get("pagamento", {}).get("modalita"),
        "iban": ai_data.get("pagamento", {}).get("iban"),
        "note": ai_data.get("note"),
        "parsed_by": "ai_emergent_claude",
        "parsed_at": ai_data.get("parsed_at")
    }


def convert_ai_busta_paga_to_dipendente_update(ai_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Converte i dati estratti dalla busta paga in aggiornamento per scheda dipendente.
    """
    if not ai_data.get("success"):
        return ai_data
    
    progressivi = ai_data.get("progressivi", {})
    tfr = ai_data.get("tfr", {})
    periodo = ai_data.get("periodo", {})
    
    return {
        "ultimo_cedolino": {
            "mese": periodo.get("mese"),
            "anno": periodo.get("anno"),
            "netto": ai_data.get("netto", {}).get("netto_pagato", 0),
            "lordo": ai_data.get("retribuzione", {}).get("lordo_totale", 0)
        },
        "progressivi": {
            "ferie_maturate": progressivi.get("ferie_maturate", 0),
            "ferie_godute": progressivi.get("ferie_godute", 0),
            "ferie_residue": progressivi.get("ferie_residue", 0),
            "permessi_maturati": progressivi.get("permessi_maturati", 0),
            "permessi_goduti": progressivi.get("permessi_goduti", 0),
            "permessi_residui": progressivi.get("permessi_residui", 0),
            "rol_maturati": progressivi.get("rol_maturati", 0),
            "rol_goduti": progressivi.get("rol_goduti", 0),
            "rol_residui": progressivi.get("rol_residui", 0),
            "ex_festivita_maturate": progressivi.get("ex_festivita_maturate", 0),
            "ex_festivita_godute": progressivi.get("ex_festivita_godute", 0),
            "ex_festivita_residue": progressivi.get("ex_festivita_residue", 0)
        },
        "tfr": {
            "quota_mese": tfr.get("quota_mese", 0),
            "fondo_accantonato": tfr.get("fondo_accantonato", 0),
            "rivalutazione": tfr.get("rivalutazione", 0)
        },
        "retribuzione": {
            "paga_base": ai_data.get("retribuzione", {}).get("paga_base", 0),
            "contingenza": ai_data.get("retribuzione", {}).get("contingenza", 0),
            "superminimo": ai_data.get("retribuzione", {}).get("superminimo", 0)
        },
        "parsed_by": "ai_emergent_claude",
        "parsed_at": ai_data.get("parsed_at"),
        "anno_riferimento": periodo.get("anno"),
        "mese_riferimento": periodo.get("mese")
    }
