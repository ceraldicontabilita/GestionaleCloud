"""Divide un Libro Unico multi-dipendente nei singoli cedolini e li registra.

Il consulente manda un unico PDF con tutti i dipendenti del mese: pagine di
presenze e pagine di elementi retributivi, una coppia per persona, riconosciute
dal codice fiscale che si ripete. Questo modulo raggruppa le pagine per CF,
ricostruisce un mini-PDF per ciascun dipendente e lo passa al parser gia'
verificato (`busta_paga_multi_template`), lo stesso usato per l'archivio
storico: stessi campi, stesso comportamento su netto e livello.

Le buste da amministratore (Ceraldi Valerio/Vincenzo/Antonietta) hanno solo la
pagina presenze, senza elementi retributivi: qui vengono segnalate e saltate,
non e' questo il documento da cui prendere il loro netto (arrivano gia'
riconciliate dalla cartella Drive "Cedolini Paga/Elaborate").
"""
import hashlib
from typing import Any, Dict

import fitz  # PyMuPDF


async def dividi_e_registra(db, pdf_bytes: bytes, filename: str = "") -> Dict[str, Any]:
    """Legge il Libro Unico e scrive ogni busta con lo scrittore unico dei cedolini.

    Prima questo modulo scriveva solo in HR: i cedolini di luglio 2026 non sono
    mai arrivati nel registro dell'ERP ne' in Prima Nota salari. Ora passa da
    `processa_tutti_cedolini_pdf` (lo stesso di posta, Drive e Documenti >
    Import): una busta col netto verificato va in contabilita' e nel deposito
    HR, una senza netto verificato solo in HR, una gia' in archivio e' un
    esito. `db` resta nella firma per i chiamanti HR: si scrive sull'ERP.
    """
    import base64

    from app.database import Database
    from app.services.cedolini_manager import processa_tutti_cedolini_pdf

    esito = await processa_tutti_cedolini_pdf(
        Database.get_db(), base64.b64encode(pdf_bytes).decode("ascii"), filename or "libro_unico.pdf",
        source_path=filename or "", source_file_hash=hashlib.sha256(pdf_bytes).hexdigest(),
        fonte="caricato",
    )

    def _competenza(busta: Dict[str, Any]) -> str:
        return f"{busta.get('anno')}-{int(busta['mese']):02d}" if busta.get("anno") and busta.get("mese") else "-"

    inseriti, saltati = [], []
    for busta in esito.get("dettaglio") or []:
        if busta["esito"] == "gia_presente":
            saltati.append({"dipendente": busta["dipendente"], "competenza": _competenza(busta)})
            continue
        tipo = str(busta.get("tipo_cedolino") or "mensile").strip().lower()
        inseriti.append({
            "dipendente": busta["dipendente"], "competenza": _competenza(busta),
            "tipo_cedolino": "ordinario" if tipo in ("", "mensile") else tipo,
            "netto": busta.get("netto"),
        })
    senza_paga = [{"errore": e} for e in esito.get("errori") or []]
    senza_anagrafica: list = []

    documento = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        pagine_totali = len(documento)
    finally:
        documento.close()
    cf_documento = {b.get("codice_fiscale") for b in esito.get("dettaglio") or [] if b.get("codice_fiscale")}

    return {
        "pagine_totali": pagine_totali,
        "dipendenti_nel_documento": len(cf_documento),
        "inseriti": inseriti, "gia_presenti": saltati,
        "senza_pagina_retributiva": senza_paga,
        "senza_anagrafica": senza_anagrafica,
    }
