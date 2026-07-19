"""
Router Anagrafica Fornitori da XML
Completa i dati anagrafici mancanti di un fornitore leggendo il blocco
CedentePrestatore delle sue fatture XML (FatturaPA).
Estratto dall'ex router schede_tecniche (dominio HACCP rimosso): questa
funzione e' puramente contabile/anagrafica e resta nel gestionale.
"""
import re
import logging
import defusedxml.ElementTree as ET  # sicurezza: blocca XXE/entity expansion su XML esterni
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Union

from fastapi import APIRouter, HTTPException

from app.database import Database

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Anagrafica Fornitori"])

XML_DIR = Path("/tmp/uploads/pec_xml")


async def _find_xml_for_fornitore(db, fornitore) -> List[Union[Path, str]]:
    """Trova le sorgenti XML per un fornitore tramite le fatture passive.

    Ritorna una lista mista di Path (file su disco, se ancora presenti) e
    stringhe (testo XML letto da invoices.xml_raw). I file su /tmp non
    sopravvivono a riavvii/deploy del backend: per una ricostruzione
    storica (richiesta utente 14/07/2026: "esegui script per far
    ricostruire una tantum i dati dalle fatture") xml_raw persistito su
    Mongo è la fonte affidabile — il file su disco resta il fallback più
    veloce quando l'upload è recente e il processo non è stato riavviato.
    """
    piva = (fornitore.get("partita_iva") or fornitore.get("piva") or "").strip()
    nome = (fornitore.get("nome") or fornitore.get("ragione_sociale") or fornitore.get("denominazione") or "").strip()

    # Cerca le fatture del fornitore nella collezione canonica `invoices`
    # (§5.4: fatture_passive consolidata). Campi canonici supplier_vat/supplier_name.
    or_clauses = []
    if piva:
        or_clauses.append({"supplier_vat": piva})
    if nome:
        or_clauses.append({"supplier_name": {"$regex": re.escape(nome[:25]), "$options": "i"}})

    if not or_clauses:
        return []

    fatture = await db["invoices"].find(
        {"$or": or_clauses} if len(or_clauses) > 1 else or_clauses[0],
        {"_id": 0, "xml_filename": 1, "xml_raw": 1}
    ).limit(20).to_list(20)

    sources: List[Union[Path, str]] = []
    for f in fatture:
        fname = f.get("xml_filename")
        trovato_su_disco = False
        if fname:
            # I file sono salvati come `{hash}_{xml_filename}` in pec_xml
            matches = list(XML_DIR.glob(f"*{fname}"))
            if matches:
                sources.extend(matches)
                trovato_su_disco = True
        if not trovato_su_disco and f.get("xml_raw"):
            sources.append(f["xml_raw"])

    # Fallback: cerca per P.IVA nel nome del file XML (es. "IT04104640612" per piva "04104640612")
    if not sources and piva:
        sources = list(XML_DIR.glob(f"*{piva}*"))

    # dict.fromkeys non funziona su testo lungo ripetuto raramente uguale:
    # va bene comunque, la deduplica reale serve solo per i Path.
    visti = set()
    dedotte = []
    for s in sources:
        chiave = str(s) if isinstance(s, Path) else id(s)
        if chiave in visti:
            continue
        visti.add(chiave)
        dedotte.append(s)
    return dedotte[:50]


def _extract_cedente_from_xml(xml_source: Union[Path, str]) -> dict:
    """
    Estrae i dati del CedentePrestatore (fornitore) da una fattura XML
    FatturaPA: `xml_source` può essere un Path su disco o il testo XML
    (da invoices.xml_raw).
    Ritorna un dizionario con: ragione_sociale, partita_iva, codice_fiscale,
    indirizzo, cap, comune, provincia, telefono, email
    """
    try:
        if isinstance(xml_source, Path):
            root = ET.parse(xml_source).getroot()
        else:
            root = ET.fromstring(xml_source)

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
        fonte = xml_source if isinstance(xml_source, Path) else "xml_raw"
        logger.warning(f"Errore estrazione cedente da {fonte}: {e}")
        return {}


async def _popola_dati_fornitore(db, fornitore: dict) -> dict:
    """Logica condivisa tra l'endpoint singolo e quello bulk: legge le
    fatture XML del fornitore, estrae il CedentePrestatore, aggiorna SOLO i
    campi mancanti (non sovrascrive mai dati già presenti)."""
    xml_sources = await _find_xml_for_fornitore(db, fornitore)
    if not xml_sources:
        return {"success": False, "message": "Nessun file XML trovato per questo fornitore", "dati": {}}

    dati_estratti: dict = {}
    for source in xml_sources:
        cedente = _extract_cedente_from_xml(source)
        # Prendi il primo valore non vuoto trovato per ogni campo
        for k, v in cedente.items():
            if k not in dati_estratti and v:
                dati_estratti[k] = v

    if not dati_estratti:
        return {"success": False, "message": "Nessun dato anagrafico trovato negli XML", "dati": {}}

    aggiornamenti = {}
    for campo, valore in dati_estratti.items():
        if not fornitore.get(campo) and valore:
            aggiornamenti[campo] = valore

    if aggiornamenti:
        aggiornamenti["updated_at"] = datetime.now(timezone.utc).isoformat()
        fornitore_id = fornitore.get("id") or fornitore.get("partita_iva")
        await db["fornitori"].update_one(
            {"$or": [{"id": fornitore_id}, {"partita_iva": fornitore_id}]},
            {"$set": aggiornamenti}
        )

    return {
        "success": True,
        "dati_estratti": dati_estratti,
        "campi_aggiornati": list(aggiornamenti.keys()),
        "xml_letti": len(xml_sources),
        "message": f"Aggiornati {len(aggiornamenti)} campi da {len(xml_sources)} fatture XML"
    }


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

    return await _popola_dati_fornitore(db, fornitore)


# Campi anagrafici che, se mancanti, rendono un fornitore candidato al
# popolamento bulk da XML — stessi campi segnalati dall'utente 14/07/2026
# ("mancano iban email località nei dati") più telefono/indirizzo/cap, già
# usati dalla card "Dati incompleti" della pagina Fornitori.
_CAMPI_DA_COMPLETARE = ["comune", "email", "telefono", "indirizzo", "cap", "provincia"]


@router.post("/popola-tutti")
async def popola_tutti_fornitori_da_xml(limite: int = 500):
    """
    Ricostruzione UNA TANTUM (richiesta utente 14/07/2026: "esegui script
    per far ricostruire una tantum i dati dalle fatture"): passa in
    rassegna i fornitori con almeno un campo anagrafico mancante e prova a
    completarli leggendo le fatture XML già in archivio (file su disco o,
    quando mancano — es. dopo un riavvio — il testo persistito in
    invoices.xml_raw). Idempotente e non distruttivo: stessa regola
    dell'endpoint singolo, aggiorna solo i campi vuoti, non tocca mai un
    valore già presente. Va rilanciato ogni volta che arrivano nuove XML
    per fornitori ancora incompleti (non è un job schedulato).
    """
    db = Database.get_db()

    fornitori = await db["fornitori"].find(
        {"$or": [{c: {"$in": [None, ""]}} for c in _CAMPI_DA_COMPLETARE]},
        {"_id": 0}
    ).to_list(limite)

    risultati = {"analizzati": len(fornitori), "aggiornati": 0, "senza_xml": 0, "senza_dati": 0, "dettaglio": []}

    for fornitore in fornitori:
        esito = await _popola_dati_fornitore(db, fornitore)
        if esito["success"] and esito.get("campi_aggiornati"):
            risultati["aggiornati"] += 1
            risultati["dettaglio"].append({
                "fornitore_id": fornitore.get("id") or fornitore.get("partita_iva"),
                "ragione_sociale": fornitore.get("ragione_sociale") or fornitore.get("nome"),
                "campi_aggiornati": esito["campi_aggiornati"],
            })
        elif not esito["success"] and "Nessun file XML" in esito.get("message", ""):
            risultati["senza_xml"] += 1
        else:
            risultati["senza_dati"] += 1

    risultati["message"] = (
        f"{risultati['aggiornati']}/{risultati['analizzati']} fornitori completati; "
        f"{risultati['senza_xml']} senza fatture XML trovate, "
        f"{risultati['senza_dati']} con XML letti ma senza nuovi dati."
    )
    return risultati
