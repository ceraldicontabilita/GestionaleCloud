"""
Alias: parse_estratto_conto_csv
Wrappa parse_estratto_conto_pdf da estratto_conto_bpm.
Il router upload-csv riceve il file come bytes — viene passato come pdf_bytes.
"""
import hashlib
from typing import Dict, Any
from app.parsers.estratto_conto_bpm import parse_estratto_conto_pdf


def parse_estratto_conto_csv(csv_str: str) -> Dict[str, Any]:
    """
    Nota: il nome 'csv' è legacy. BPM esporta PDF, non CSV.
    Questo wrapper non viene usato direttamente — il router chiama
    parse_estratto_conto_pdf con pdf_bytes.
    Manteniamo per compatibilità import.
    """
    return {"errore": "Usa upload-pdf, non upload-csv"}


def parse_estratto_conto_pdf_bytes(pdf_bytes: bytes) -> Dict[str, Any]:
    """Helper diretto con chiavi per deduplicazione movimenti."""
    result = parse_estratto_conto_pdf(pdf_bytes=pdf_bytes)

    # Aggiungi chiave dedup a ogni movimento
    for i, mov in enumerate(result.get("movimenti", [])):
        chiave_raw = f"{mov['data_operazione']}|{mov['descrizione'][:30]}|{mov['importo']}"
        mov["chiave"] = hashlib.md5(chiave_raw.encode()).hexdigest()
        mov["riconciliato"] = False

    result["totale_entrate"] = round(sum(m["avere"] for m in result.get("movimenti", [])), 2)
    result["totale_uscite"] = round(sum(m["dare"] for m in result.get("movimenti", [])), 2)
    result["saldo_netto"] = round(result["totale_entrate"] - result["totale_uscite"], 2)
    return result
