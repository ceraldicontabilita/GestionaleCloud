"""Estrattore documentale AI per HR — re-export del motore unico dell'ERP.

Questo modulo era una copia di `app.services.document_ai_extractor` divergente
in tre punti, tutti difetti: chiamava `LlmChat(system_message=...)` e
`UserMessage(text=...)` con nomi di parametro inesistenti (TypeError), tagliava
il testo a 15.000 caratteri (il limite gia' alzato a 150.000 sull'ERP perche'
troncava gli estratti conto e i PDF multipagina) e passava da uno stub con un
modello ritirato cablato nel codice.

Un solo motore per funzione: il codice vive in `app/services/`, qui resta solo
il percorso di import usato dal ramo HR.
"""
from app.services.document_ai_extractor import (  # noqa: F401
    ANTHROPIC_API_KEY,
    MIN_TEXT_LENGTH,
    PROMPTS,
    detect_document_type,
    extract_structured_data,
    extract_text_from_image,
    extract_text_from_pdf,
    process_document,
    process_document_from_base64,
)

__all__ = [
    "ANTHROPIC_API_KEY",
    "MIN_TEXT_LENGTH",
    "PROMPTS",
    "detect_document_type",
    "extract_structured_data",
    "extract_text_from_image",
    "extract_text_from_pdf",
    "process_document",
    "process_document_from_base64",
]
