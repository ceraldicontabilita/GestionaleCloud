"""
Parser PDF per Piani di Ammortamento Mutui
==========================================

Estrae le rate dai PDF BPM (Banca Popolare di Milano)
e le importa nell'archivio del runtime.
"""

import re
import pdfplumber
from typing import List, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
import tempfile
import os
import logging

from app.database import Database
from app.routers.mutui import _admin_mutui
from app.utils.upload_validation import verifica_pdf_reale

# Legge e importa piani di ammortamento (dati finanziari): solo admin, come il router Mutui.
router = APIRouter(tags=["Mutui Parser PDF"], dependencies=[Depends(_admin_mutui)])
logger = logging.getLogger(__name__)


def parse_mutuo_pdf(pdf_path: str) -> Dict:
    """
    Parsa un PDF di piano ammortamento BPM e estrae tutti i dati.

    Returns:
        Dict con dati mutuo e lista rate
    """
    mutuo_data = {
        "intestatario": None,
        "tipo_finanziamento": None,
        "importo_accordato": 0.0,
        "numero_delibera": None,
        "rate_residue_dichiarate": 0,
        "rate": []
    }

    all_text = ""

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                all_text += text + "\n"

    # Estrai intestatario
    match = re.search(r'Rag\.Soc\./Intestatario:\s*(.+?)(?:\n|Tipo)', all_text)
    if match:
        mutuo_data["intestatario"] = match.group(1).strip()

    # Estrai tipo finanziamento
    match = re.search(r'Tipo finanziamento:\s*(.+?)\s*Importo accordato', all_text)
    if match:
        mutuo_data["tipo_finanziamento"] = match.group(1).strip()

    # Estrai importo accordato
    match = re.search(r'Importo accordato:\s*([\d.,]+)\s*EUR', all_text)
    if match:
        importo_str = match.group(1).replace('.', '').replace(',', '.')
        mutuo_data["importo_accordato"] = float(importo_str)

    # Estrai numero delibera
    match = re.search(r'Numero delibera:\s*(\d+)', all_text)
    if match:
        mutuo_data["numero_delibera"] = match.group(1)

    # Estrai rate residue
    match = re.search(r'Rate residue:\s*(\d+)', all_text)
    if match:
        mutuo_data["rate_residue_dichiarate"] = int(match.group(1))

    # Pattern per le rate:
    # Numero rata | Scadenza | Importo | Quota capitale | Quota interessi | Stato
    # Esempio: "1 17/03/2021 4.908,98 EUR 4.558,42 EUR 347,81 EUR Pagata"
    rate_pattern = re.compile(
        r'(\d+)\s+'  # Numero rata
        r'(\d{2}/\d{2}/\d{4})\s+'  # Data scadenza
        r'([\d.,]+)\s*EUR\s+'  # Importo totale
        r'([\d.,]+)\s*EUR\s+'  # Quota capitale
        r'([\d.,]+)\s*EUR\s+'  # Quota interessi
        r'(Pagata|Da pagare|Scaduta)',  # Stato
        re.IGNORECASE
    )

    for match in rate_pattern.finditer(all_text):
        numero_rata = int(match.group(1))
        data_scadenza = match.group(2)
        importo_totale = float(match.group(3).replace('.', '').replace(',', '.'))
        quota_capitale = float(match.group(4).replace('.', '').replace(',', '.'))
        quota_interessi = float(match.group(5).replace('.', '').replace(',', '.'))
        stato = match.group(6).capitalize()

        rata = {
            "numero_rata": numero_rata,
            "data_scadenza": data_scadenza,
            "importo_totale": importo_totale,
            "quota_capitale": quota_capitale,
            "quota_interessi": quota_interessi,
            "stato": stato,
            "riconciliata": False,
            "movimento_bancario_id": None,
            "data_pagamento_effettivo": None,
            "note_riconciliazione": None
        }
        mutuo_data["rate"].append(rata)

    # Ordina rate per numero
    mutuo_data["rate"].sort(key=lambda x: x["numero_rata"])

    # Calcola statistiche
    rate_pagate = sum(1 for r in mutuo_data["rate"] if r["stato"] == "Pagata")
    rate_da_pagare = sum(1 for r in mutuo_data["rate"] if r["stato"] == "Da pagare")

    totale_pagato_capitale = sum(r["quota_capitale"] for r in mutuo_data["rate"] if r["stato"] == "Pagata")
    totale_pagato_interessi = sum(r["quota_interessi"] for r in mutuo_data["rate"] if r["stato"] == "Pagata")
    totale_pagato = sum(r["importo_totale"] for r in mutuo_data["rate"] if r["stato"] == "Pagata")

    debito_residuo_capitale = sum(r["quota_capitale"] for r in mutuo_data["rate"] if r["stato"] != "Pagata")
    debito_residuo_interessi = sum(r["quota_interessi"] for r in mutuo_data["rate"] if r["stato"] != "Pagata")
    debito_residuo_totale = sum(r["importo_totale"] for r in mutuo_data["rate"] if r["stato"] != "Pagata")

    # Trova prossima rata da pagare
    prossima_rata = None
    for rata in mutuo_data["rate"]:
        if rata["stato"] == "Da pagare":
            prossima_rata = rata
            break

    mutuo_data["statistiche"] = {
        "totale_rate": len(mutuo_data["rate"]),
        "rate_pagate": rate_pagate,
        "rate_da_pagare": rate_da_pagare,
        "totale_pagato_capitale": round(totale_pagato_capitale, 2),
        "totale_pagato_interessi": round(totale_pagato_interessi, 2),
        "totale_pagato": round(totale_pagato, 2),
        "debito_residuo_capitale": round(debito_residuo_capitale, 2),
        "debito_residuo_interessi": round(debito_residuo_interessi, 2),
        "debito_residuo_totale": round(debito_residuo_totale, 2),
        "prossima_rata": prossima_rata
    }

    return mutuo_data


@router.post("/parse-pdf", summary="Parsa PDF piano ammortamento")
async def parse_mutuo_pdf_endpoint(file: UploadFile = File(...)):
    """
    Carica un PDF di piano ammortamento e lo parsa per estrarre le rate.
    NON salva nel database, restituisce solo i dati estratti per review.
    """
    try:
        # Verifica estensione
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Il file deve essere un PDF")

        content = await file.read()
        verifica_pdf_reale(content, file.filename)

        # Salva temporaneamente
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        try:
            # Parsa il PDF
            result = parse_mutuo_pdf(tmp_path)

            return {
                "success": True,
                "message": f"PDF parsato con successo. Trovate {len(result['rate'])} rate.",
                "data": result
            }

        finally:
            # Pulisci file temporaneo
            os.unlink(tmp_path)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Errore parsing PDF (%s): %s", type(e).__name__, e)
        raise HTTPException(status_code=500, detail=f"Errore parsing PDF: {str(e)}") from e


@router.post("/import-pdf", summary="Importa il piano di ammortamento da PDF")
async def import_mutuo_from_pdf(
    file: UploadFile = File(...),
    nome_mutuo: Optional[str] = None,
    aggiorna_esistente: bool = False
):
    """Importa il piano di ammortamento con l'import documentale unico
    (``services/mutui_document_import.importa_documento_mutuo``, lo stesso di
    Documenti > Import): deduplica SHA-256 e scrittura in
    ``mutui_piani_documentali``, la collezione che leggono la pagina Mutui e
    la proiezione bancaria. Prima scriveva in ``mutui``, che nessuno legge
    (audit 27/09/2026). ``nome_mutuo`` e ``aggiorna_esistente`` restano per
    compatibilita': una nuova versione del piano e' un nuovo documento
    (altro SHA-256) e vale la piu' recente."""
    from app.services.mutui_document_import import importa_documento_mutuo

    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Il file deve essere un PDF")
    content = await file.read()
    verifica_pdf_reale(content, file.filename)
    try:
        esito = await importa_documento_mutuo(Database.get_db(), content, file.filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "message": "Piano di ammortamento importato", "data": esito}


@router.post("/parse-multiple", summary="Parsa multipli PDF")
async def parse_multiple_pdfs(files: List[UploadFile] = File(...)):
    """
    Parsa multipli PDF di piani ammortamento in un'unica chiamata.
    Restituisce i dati estratti senza salvare nel database.
    """
    results = []

    for file in files:
        try:
            if not file.filename.lower().endswith('.pdf'):
                results.append({
                    "filename": file.filename,
                    "success": False,
                    "error": "Non è un file PDF"
                })
                continue

            content = await file.read()
            try:
                verifica_pdf_reale(content, file.filename)
            except HTTPException as e:
                results.append({"filename": file.filename, "success": False, "error": e.detail})
                continue

            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
                tmp.write(content)
                tmp_path = tmp.name

            try:
                parsed = parse_mutuo_pdf(tmp_path)
                results.append({
                    "filename": file.filename,
                    "success": True,
                    "data": parsed
                })
            finally:
                os.unlink(tmp_path)

        except Exception as e:
            logger.warning("Parsing PDF mutuo non riuscito (%s): %s", type(e).__name__, e)
            results.append({
                "filename": file.filename,
                "success": False,
                "error": str(e)
            })

    return {
        "success": True,
        "total_files": len(files),
        "parsed_successfully": sum(1 for r in results if r["success"]),
        "results": results
    }
