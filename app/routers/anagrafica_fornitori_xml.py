"""
Router Anagrafica Fornitori da XML
Completa i dati anagrafici mancanti di un fornitore leggendo il blocco
CedentePrestatore delle sue fatture XML (FatturaPA).
Estratto dall'ex router schede_tecniche (dominio HACCP rimosso): questa
funzione e' puramente contabile/anagrafica e resta nel gestionale.
"""
import re
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from fastapi import APIRouter, HTTPException

from app.database import Database

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Anagrafica Fornitori"])

XML_DIR = Path("/tmp/uploads/pec_xml")


async def _find_xml_for_fornitore(db, fornitore) -> List[Path]:
    """Trova i file XML per un fornitore tramite le fatture passive."""
    piva = (fornitore.get("partita_iva") or fornitore.get("piva") or "").strip()
    nome = (fornitore.get("nome") or fornitore.get("ragione_sociale") or fornitore.get("denominazione") or "").strip()

    # Cerca fatture passive associate a questo fornitore (per P.IVA o nome)
    or_clauses = []
    if piva:
        or_clauses.append({"fornitore_piva": piva})
    if nome:
        or_clauses.append({"fornitore_denominazione": {"$regex": re.escape(nome[:25]), "$options": "i"}})

    if not or_clauses:
        return []

    fatture = await db["fatture_passive"].find(
        {"$or": or_clauses} if len(or_clauses) > 1 else or_clauses[0],
        {"_id": 0, "xml_filename": 1}
    ).limit(20).to_list(20)

    paths = []
    for f in fatture:
        fname = f.get("xml_filename")
        if fname:
            # I file sono salvati come `{hash}_{xml_filename}` in pec_xml
            matches = list(XML_DIR.glob(f"*{fname}"))
            paths.extend(matches)

    # Fallback: cerca per P.IVA nel nome del file XML (es. "IT04104640612" per piva "04104640612")
    if not paths and piva:
        paths = list(XML_DIR.glob(f"*{piva}*"))

    return list(dict.fromkeys(paths))[:50]


def _extract_cedente_from_xml(xml_path: Path) -> dict:
    """
    Estrae i dati del CedentePrestatore (fornitore) da un file XML FatturaPA.
    Ritorna un dizionario con: ragione_sociale, partita_iva, codice_fiscale,
    indirizzo, cap, comune, provincia, telefono, email
    """
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()

        # Trova il blocco CedentePrestatore
        cedente = None
        for el in root.iter():
            local = el.tag.split("}")[-1] if "}" in el.tag else el.tag
            if local == "CedentePrestatore":
                cedente = el
                break

        if cedente is None:
            return {}

        # Estrai tutti i campi testo del blocco
        dati: dict = {}
        for child in cedente.iter():
            local = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if child.text and child.text.strip():
                dati[local] = child.text.strip()

        result: dict = {}

        # Nome azienda
        if dati.get("Denominazione"):
            result["ragione_sociale"] = dati["Denominazione"]
            result["nome"] = dati["Denominazione"]
        elif dati.get("Nome") and dati.get("Cognome"):
            result["ragione_sociale"] = f"{dati['Cognome']} {dati['Nome']}"
            result["nome"] = result["ragione_sociale"]

        # P.IVA / CF
        if dati.get("IdCodice"):
            result["partita_iva"] = dati["IdCodice"]
        if dati.get("CodiceFiscale"):
            result["codice_fiscale"] = dati["CodiceFiscale"]

        # Indirizzo
        if dati.get("Indirizzo"):
            result["indirizzo"] = dati["Indirizzo"]
        if dati.get("CAP"):
            result["cap"] = dati["CAP"]
        if dati.get("Comune"):
            result["comune"] = dati["Comune"]
        if dati.get("Provincia"):
            result["provincia"] = dati["Provincia"]

        # Contatti
        if dati.get("Telefono"):
            result["telefono"] = dati["Telefono"]
        if dati.get("Email"):
            result["email"] = dati["Email"]

        return result

    except Exception as e:
        logger.warning(f"Errore estrazione cedente da {xml_path}: {e}")
        return {}


@router.post("/popola-fornitore/{fornitore_id}")
async def popola_fornitore_da_xml(fornitore_id: str):
    """
    Legge tutti i file XML delle fatture del fornitore ed estrae i dati anagrafici
    dal blocco CedentePrestatore (telefono, email, indirizzo, comune, provincia...).
    Aggiorna SOLO i campi mancanti (non sovrascrive dati esistenti).
    """
    db = Database.get_db()

    fornitore = await db["fornitori"].find_one(
        {"$or": [{"id": fornitore_id}, {"partita_iva": fornitore_id}]},
        {"_id": 0}
    )
    if not fornitore:
        raise HTTPException(status_code=404, detail="Fornitore non trovato")

    xml_paths = await _find_xml_for_fornitore(db, fornitore)
    if not xml_paths:
        return {"success": False, "message": "Nessun file XML trovato per questo fornitore", "dati": {}}

    dati_estratti: dict = {}
    for xml_path in xml_paths:
        cedente = _extract_cedente_from_xml(xml_path)
        # Prendi il primo valore non vuoto trovato per ogni campo
        for k, v in cedente.items():
            if k not in dati_estratti and v:
                dati_estratti[k] = v

    if not dati_estratti:
        return {"success": False, "message": "Nessun dato anagrafico trovato negli XML", "dati": {}}

    # Aggiorna solo i campi che mancano nel fornitore
    aggiornamenti = {}
    for campo, valore in dati_estratti.items():
        if not fornitore.get(campo) and valore:
            aggiornamenti[campo] = valore

    if aggiornamenti:
        aggiornamenti["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db["fornitori"].update_one(
            {"$or": [{"id": fornitore_id}, {"partita_iva": fornitore_id}]},
            {"$set": aggiornamenti}
        )

    return {
        "success": True,
        "dati_estratti": dati_estratti,
        "campi_aggiornati": list(aggiornamenti.keys()),
        "xml_letti": len(xml_paths),
        "message": f"Aggiornati {len(aggiornamenti)} campi da {len(xml_paths)} fatture XML"
    }
