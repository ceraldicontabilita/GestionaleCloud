"""
Document AI Extractor Service
Estrae dati strutturati da documenti italiani (F24, buste paga, estratti conto)
usando OCR + LLM.

Flusso:
1. PDF → PyMuPDF (estrae testo se disponibile)
2. Se PDF è immagine → pytesseract (OCR)
3. Testo → LLM (GPT/Claude) → JSON strutturato
"""

import os
import re
import json
import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import io
import base64
from datetime import datetime, timezone
from typing import Dict, Any
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Configurazione
EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")

# Soglia minima di caratteri per considerare il PDF come "testo"
MIN_TEXT_LENGTH = 100


# ============================================================
# PROMPT TEMPLATES PER TIPO DOCUMENTO
# ============================================================

PROMPTS = {
    "f24": """Sei un esperto di documenti fiscali italiani. Estrai i dati dal seguente Modello F24.

TESTO DEL DOCUMENTO:
{text}

Rispondi SOLO con un JSON valido con questa struttura:
{{
    "tipo_documento": "F24",
    "codice_fiscale": "...",
    "denominazione": "...",
    "data_versamento": "YYYY-MM-DD",
    "totale_versamento": 0.00,
    "sezione_erario": [
        {{"codice_tributo": "...", "anno_riferimento": "YYYY", "importo_debito": 0.00}}
    ],
    "sezione_inps": [
        {{"codice_sede": "...", "causale": "...", "matricola": "...", "periodo_da": "MM/YYYY", "periodo_a": "MM/YYYY", "importo_debito": 0.00}}
    ],
    "sezione_regioni": [
        {{"codice_regione": "...", "codice_tributo": "...", "anno_riferimento": "YYYY", "importo_debito": 0.00}}
    ],
    "sezione_imu": [
        {{"codice_ente": "...", "codice_tributo": "...", "anno_riferimento": "YYYY", "importo_debito": 0.00}}
    ]
}}

Se un campo non è presente, usa null. Se una sezione è vuota, usa array vuoto [].
NON aggiungere spiegazioni, SOLO il JSON.""",

    "busta_paga": """Sei un esperto di buste paga italiane. Estrai i dati dal seguente cedolino/busta paga.

TESTO DEL DOCUMENTO:
{text}

Rispondi SOLO con un JSON valido con questa struttura:
{{
    "tipo_documento": "BUSTA_PAGA",
    "dipendente": {{
        "nome_cognome": "...",
        "codice_fiscale": "...",
        "matricola": "..."
    }},
    "azienda": {{
        "denominazione": "...",
        "codice_fiscale": "...",
        "indirizzo": "..."
    }},
    "periodo": {{
        "mese": "...",
        "anno": "YYYY"
    }},
    "retribuzione": {{
        "lordo": 0.00,
        "netto": 0.00,
        "trattenute_inps": 0.00,
        "trattenute_irpef": 0.00,
        "addizionale_regionale": 0.00,
        "addizionale_comunale": 0.00
    }},
    "ore_lavorate": 0,
    "giorni_lavorati": 0,
    "ferie_residue": 0,
    "tfr_maturato": 0.00
}}

Se un campo non è presente, usa null.
NON aggiungere spiegazioni, SOLO il JSON.""",

    "estratto_conto": """Sei un esperto di estratti conto bancari italiani. Estrai i dati dal seguente estratto conto.

TESTO DEL DOCUMENTO:
{text}

Rispondi SOLO con un JSON valido con questa struttura:
{{
    "tipo_documento": "ESTRATTO_CONTO",
    "banca": "...",
    "intestatario": "...",
    "iban": "...",
    "periodo": {{
        "da": "YYYY-MM-DD",
        "a": "YYYY-MM-DD"
    }},
    "saldo_iniziale": 0.00,
    "saldo_finale": 0.00,
    "totale_entrate": 0.00,
    "totale_uscite": 0.00,
    "movimenti": [
        {{
            "data": "YYYY-MM-DD",
            "data_valuta": "YYYY-MM-DD",
            "descrizione": "...",
            "importo": 0.00,
            "tipo": "entrata|uscita"
        }}
    ]
}}

IMPORTANTE: Estrai TUTTI i movimenti visibili nel documento.
Se un campo non è presente, usa null.
NON aggiungere spiegazioni, SOLO il JSON.""",

    "fattura": """Sei un esperto di fatture italiane. Estrai i dati dalla seguente fattura.

TESTO DEL DOCUMENTO:
{text}

Rispondi SOLO con un JSON valido con questa struttura:
{{
    "tipo_documento": "FATTURA",
    "numero_fattura": "...",
    "data_fattura": "YYYY-MM-DD",
    "fornitore": {{
        "denominazione": "...",
        "partita_iva": "...",
        "codice_fiscale": "...",
        "indirizzo": "..."
    }},
    "cliente": {{
        "denominazione": "...",
        "partita_iva": "...",
        "codice_fiscale": "...",
        "indirizzo": "..."
    }},
    "imponibile": 0.00,
    "iva": 0.00,
    "totale": 0.00,
    "aliquota_iva": 0,
    "metodo_pagamento": "...",
    "scadenza_pagamento": "YYYY-MM-DD",
    "descrizione_righe": ["..."]
}}

Se un campo non è presente, usa null.
NON aggiungere spiegazioni, SOLO il JSON.""",

    "generico": """Analizza il seguente documento e estrai tutte le informazioni rilevanti.

TESTO DEL DOCUMENTO:
{text}

Rispondi SOLO con un JSON valido con questa struttura:
{{
    "tipo_documento": "...",
    "data_documento": "YYYY-MM-DD",
    "mittente": "...",
    "destinatario": "...",
    "oggetto": "...",
    "importi": [0.00],
    "date_rilevanti": ["YYYY-MM-DD"],
    "codici_fiscali": ["..."],
    "partite_iva": ["..."],
    "numeri_riferimento": ["..."],
    "contenuto_principale": "..."
}}

Se un campo non è presente, usa null o array vuoto.
NON aggiungere spiegazioni, SOLO il JSON.""",

    "bonifico": """Sei un esperto di documenti bancari italiani. Estrai i dati dalla seguente ricevuta di bonifico.

TESTO DEL DOCUMENTO:
{text}

Rispondi SOLO con un JSON valido con questa struttura:
{{
    "tipo_documento": "BONIFICO",
    "data_operazione": "YYYY-MM-DD",
    "data_valuta": "YYYY-MM-DD",
    "importo": 0.00,
    "valuta": "EUR",
    "ordinante": {{
        "denominazione": "...",
        "iban": "...",
        "banca": "..."
    }},
    "beneficiario": {{
        "denominazione": "...",
        "iban": "...",
        "banca": "..."
    }},
    "causale": "...",
    "cro_trn": "...",
    "tipo_bonifico": "SEPA|estero|istantaneo",
    "commissioni": 0.00
}}

Se un campo non è presente, usa null.
NON aggiungere spiegazioni, SOLO il JSON.""",

    "verbale": """Sei un esperto di verbali e multe stradali italiane. Estrai i dati dal seguente verbale/multa.

TESTO DEL DOCUMENTO:
{text}

Rispondi SOLO con un JSON valido con questa struttura:
{{
    "tipo_documento": "VERBALE",
    "numero_verbale": "...",
    "data_verbale": "YYYY-MM-DD",
    "data_violazione": "YYYY-MM-DD",
    "ora_violazione": "HH:MM",
    "luogo_violazione": "...",
    "targa_veicolo": "...",
    "tipo_veicolo": "...",
    "proprietario": {{
        "nome_cognome": "...",
        "codice_fiscale": "...",
        "indirizzo": "..."
    }},
    "violazione": {{
        "articolo": "...",
        "descrizione": "...",
        "punti_patente": 0
    }},
    "importo_ridotto": 0.00,
    "importo_pieno": 0.00,
    "scadenza_pagamento": "YYYY-MM-DD",
    "ente_accertatore": "...",
    "societa_noleggio": "..."
}}

Se un campo non è presente, usa null.
NON aggiungere spiegazioni, SOLO il JSON.""",

    "cartella_esattoriale": """Sei un esperto di cartelle esattoriali e atti dell'Agenzia delle Entrate-Riscossione. Estrai i dati dal seguente documento.

TESTO DEL DOCUMENTO:
{text}

Rispondi SOLO con un JSON valido con questa struttura:
{{
    "tipo_documento": "CARTELLA_ESATTORIALE",
    "numero_cartella": "...",
    "data_notifica": "YYYY-MM-DD",
    "contribuente": {{
        "denominazione": "...",
        "codice_fiscale": "...",
        "indirizzo": "..."
    }},
    "ente_creditore": "...",
    "debiti": [
        {{
            "descrizione": "...",
            "anno_riferimento": "YYYY",
            "importo_originario": 0.00,
            "interessi": 0.00,
            "sanzioni": 0.00,
            "aggio": 0.00,
            "totale_debito": 0.00
        }}
    ],
    "totale_cartella": 0.00,
    "scadenza_pagamento": "YYYY-MM-DD",
    "rate_disponibili": true,
    "numero_rate_max": 0,
    "riferimento_rottamazione": "..."
}}

Se un campo non è presente, usa null. Se una sezione è vuota, usa array vuoto [].
NON aggiungere spiegazioni, SOLO il JSON.""",

    "delibera_inps": """Sei un esperto di documenti INPS italiani. Estrai i dati dalla seguente delibera o comunicazione INPS.

TESTO DEL DOCUMENTO:
{text}

Rispondi SOLO con un JSON valido con questa struttura:
{{
    "tipo_documento": "DELIBERA_INPS",
    "numero_protocollo": "...",
    "data_documento": "YYYY-MM-DD",
    "tipo_comunicazione": "delibera|autorizzazione|diniego|richiesta",
    "oggetto": "...",
    "azienda": {{
        "denominazione": "...",
        "codice_fiscale": "...",
        "matricola_inps": "..."
    }},
    "sede_inps": "...",
    "importo_totale": 0.00,
    "periodo_riferimento": {{
        "da": "YYYY-MM-DD",
        "a": "YYYY-MM-DD"
    }},
    "numero_lavoratori": 0,
    "ore_autorizzate": 0,
    "causale": "...",
    "esito": "approvato|respinto|sospeso"
}}

Se un campo non è presente, usa null.
NON aggiungere spiegazioni, SOLO il JSON."""
}


def detect_document_type(text: str) -> str:
    """
    Rileva automaticamente il tipo di documento dal testo.
    """
    text_lower = text.lower()
    
    # F24 (alta priorità)
    if any(kw in text_lower for kw in ["modello f24", "delega irrevocabile", "codice tributo", "sezione erario"]):
        return "f24"
    
    # Verbale/Multa (alta priorità)
    if any(kw in text_lower for kw in ["verbale n", "verbale di contestazione", "violazione", "codice della strada", 
                                        "multa", "contravvenzione", "infrazione", "sanzione amministrativa"]):
        return "verbale"
    
    # Cartella esattoriale (alta priorità)
    if any(kw in text_lower for kw in ["cartella di pagamento", "agenzia delle entrate-riscossione", "ader", 
                                        "cartella esattoriale", "intimazione di pagamento", "rottamazione"]):
        return "cartella_esattoriale"
    
    # Delibera INPS
    if any(kw in text_lower for kw in ["delibera inps", "sede inps", "cassa integrazione", "fonsi", 
                                        "autorizzazione inps", "ammortizzatori sociali"]):
        return "delibera_inps"
    
    # Bonifico (controlla PRIMA di estratto conto)
    if any(kw in text_lower for kw in ["ricevuta bonifico", "bonifico sepa", "disposizione di bonifico",
                                        "ricevuta per ordinante", "cro:", "trn:", "bonifico effettuato"]):
        return "bonifico"
    
    # Busta paga
    if any(kw in text_lower for kw in ["busta paga", "cedolino", "retribuzione lorda", "retribuzione netta", 
                                        "trattenute", "prospetto paga"]):
        return "busta_paga"
    
    # Estratto conto
    if any(kw in text_lower for kw in ["estratto conto", "saldo iniziale", "saldo finale", "movimenti", "data valuta"]):
        return "estratto_conto"
    
    # Fattura
    if any(kw in text_lower for kw in ["fattura n", "fattura numero", "imponibile", "totale fattura", "iva"]):
        return "fattura"
    
    return "generico"
    if any(kw in text_lower for kw in ["fattura n", "fattura numero", "imponibile", "totale fattura", "iva"]):
        return "fattura"
    
    return "generico"


def extract_text_from_pdf(pdf_data: bytes) -> str:
    """
    Estrae testo da PDF usando PyMuPDF.
    Se il PDF è un'immagine, usa OCR.
    """
    text = ""
    
    try:
        # Apri il PDF con PyMuPDF
        doc = fitz.open(stream=pdf_data, filetype="pdf")
        
        for page_num, page in enumerate(doc):
            # Prima prova estrazione testo nativo
            page_text = page.get_text()
            
            if page_text and len(page_text.strip()) > MIN_TEXT_LENGTH:
                text += f"\n--- Pagina {page_num + 1} ---\n"
                text += page_text
            else:
                # PDF è immagine, usa OCR
                logger.info(f"Pagina {page_num + 1}: testo insufficiente, uso OCR")
                
                # Converti pagina in immagine
                mat = fitz.Matrix(2.0, 2.0)  # 2x zoom per migliore OCR
                pix = page.get_pixmap(matrix=mat)
                img_data = pix.tobytes("png")
                
                # OCR con pytesseract
                image = Image.open(io.BytesIO(img_data))
                ocr_text = pytesseract.image_to_string(image, lang='ita+eng')
                
                if ocr_text.strip():
                    text += f"\n--- Pagina {page_num + 1} (OCR) ---\n"
                    text += ocr_text
        
        doc.close()
        
    except Exception as e:
        logger.error(f"Errore estrazione PDF: {e}")
        raise
    
    return text.strip()


def extract_text_from_image(image_data: bytes) -> str:
    """
    Estrae testo da immagine usando OCR.
    """
    try:
        image = Image.open(io.BytesIO(image_data))
        text = pytesseract.image_to_string(image, lang='ita+eng')
        return text.strip()
    except Exception as e:
        logger.error(f"Errore OCR immagine: {e}")
        raise


async def extract_structured_data(
    text: str,
    document_type: str = None,
    model: str = "claude-sonnet-4-5-20250929"
) -> Dict[str, Any]:
    """
    Usa LLM per estrarre dati strutturati dal testo.
    
    Args:
        text: Testo del documento
        document_type: Tipo documento (f24, busta_paga, estratto_conto, fattura, generico)
        model: Modello LLM da usare
    
    Returns:
        Dati strutturati in formato dict
    """
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    
    if not EMERGENT_LLM_KEY:
        raise ValueError("EMERGENT_LLM_KEY non configurata")
    
    # Auto-detect tipo documento se non specificato
    if not document_type:
        document_type = detect_document_type(text)
    
    # Seleziona il prompt appropriato
    prompt_template = PROMPTS.get(document_type, PROMPTS["generico"])
    prompt = prompt_template.format(text=text[:15000])  # Limita a 15k caratteri
    
    try:
        # Inizializza chat LLM
        # Determina provider dal nome del modello
        if model.startswith("claude"):
            provider = "anthropic"
        elif model.startswith("gemini"):
            provider = "gemini"
        else:
            provider = "openai"
        
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"doc_extract_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            system_message="Sei un assistente specializzato nell'estrazione di dati da documenti italiani. Rispondi SEMPRE e SOLO con JSON valido."
        ).with_model(provider, model)
        
        # Invia messaggio
        user_message = UserMessage(text=prompt)
        response = await chat.send_message(user_message)
        
        # Pulisci la risposta (rimuovi markdown code blocks se presenti)
        response_clean = response.strip()
        if response_clean.startswith("```"):
            # Rimuovi ```json e ```
            lines = response_clean.split("\n")
            response_clean = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
        
        # Parse JSON
        try:
            data = json.loads(response_clean)
        except json.JSONDecodeError:
            # Prova a trovare JSON nella risposta
            json_match = re.search(r'\{.*\}', response_clean, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
            else:
                data = {"raw_response": response, "parse_error": True}
        
        return {
            "success": True,
            "document_type": document_type,
            "data": data,
            "model_used": model,
            "text_length": len(text),
            "extracted_at": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Errore estrazione LLM: {e}")
        return {
            "success": False,
            "error": str(e),
            "document_type": document_type,
            "text_preview": text[:500] if text else None
        }


async def process_document(
    file_data: bytes,
    filename: str,
    document_type: str = None,
    model: str = "claude-sonnet-4-5-20250929"
) -> Dict[str, Any]:
    """
    Processa un documento completo: estrae testo e poi dati strutturati.
    
    Args:
        file_data: Contenuto del file in bytes
        filename: Nome del file
        document_type: Tipo documento (opzionale, auto-detect)
        model: Modello LLM
    
    Returns:
        Risultato con testo estratto e dati strutturati
    """
    result = {
        "filename": filename,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ocr_used": False,
        "text": None,
        "structured_data": None
    }
    
    try:
        # Determina tipo file
        ext = filename.lower().split(".")[-1] if "." in filename else ""
        
        if ext == "pdf":
            text = extract_text_from_pdf(file_data)
            result["ocr_used"] = "OCR" in text
        elif ext in ["png", "jpg", "jpeg", "tiff", "bmp"]:
            text = extract_text_from_image(file_data)
            result["ocr_used"] = True
        else:
            return {**result, "error": f"Formato file non supportato: {ext}"}
        
        result["text"] = text
        result["text_length"] = len(text)
        
        if not text or len(text) < 50:
            return {**result, "error": "Nessun testo estratto dal documento"}
        
        # Estrai dati strutturati con LLM
        structured = await extract_structured_data(text, document_type, model)
        result["structured_data"] = structured
        
        return result
        
    except Exception as e:
        logger.error(f"Errore processamento documento {filename}: {e}")
        return {**result, "error": str(e)}


async def process_document_from_base64(
    base64_data: str,
    filename: str,
    document_type: str = None,
    model: str = "claude-sonnet-4-5-20250929"
) -> Dict[str, Any]:
    """
    Processa un documento da base64.
    """
    try:
        file_data = base64.b64decode(base64_data)
        return await process_document(file_data, filename, document_type, model)
    except Exception as e:
        return {"error": f"Errore decodifica base64: {e}", "filename": filename}
