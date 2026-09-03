"""
azienda.py — Sorgente unica dei dati aziendali (Ceraldi Group S.r.l.).

Tutti i PDF e le stampe HTML (listino, ordini, report HACCP, manuale, schede,
etichette lotto) leggono da qui: niente piu' dati ripetuti e divergenti sparsi
nei singoli router.

I valori di default arrivano dalle env (con fallback ai dati reali) e possono
essere sovrascritti dalle Impostazioni, persistiti su Mongo nella collection
'impostazioni' (documento _id='azienda'). Il campo piu' usato e'
codice_destinatario (SDI): cambia quando cambia il gestore dell'interscambio di
fatturazione, e aggiornarlo qui aggiorna automaticamente tutti i PDF.
"""

import os
import html as _html

from fastapi import APIRouter, Body

from app.lotti.db import database as db

_DOC_ID = "azienda"

# Default reali — sovrascrivibili da env e poi dalle Impostazioni.
DEFAULT_AZIENDA = {
    "ragione_sociale": os.environ.get("AZIENDA_NOME", "Ceraldi Group S.r.l."),
    "indirizzo": os.environ.get("AZIENDA_INDIRIZZO", "Piazza Carità 14, 80134 Napoli (NA)"),
    "partita_iva": os.environ.get("AZIENDA_PIVA", "04523831214"),
    "codice_fiscale": os.environ.get("AZIENDA_CF", "04523831214"),
    "codice_destinatario": os.environ.get("AZIENDA_CODICE_DESTINATARIO", "USAL8PV"),
    "email": os.environ.get("AZIENDA_EMAIL", ""),
    "telefono": os.environ.get("AZIENDA_TEL", ""),
    "attivita": os.environ.get("AZIENDA_ATTIVITA", "Pasticceria e Rosticceria"),
    "responsabile_haccp": os.environ.get("AZIENDA_RESP_HACCP", ""),
    "studio_consulenza": os.environ.get("AZIENDA_STUDIO", ""),
}

# Campi che le Impostazioni possono modificare e salvare.
CAMPI_MODIFICABILI = [
    "ragione_sociale",
    "indirizzo",
    "partita_iva",
    "codice_fiscale",
    "codice_destinatario",
    "email",
    "telefono",
    "attivita",
    "responsabile_haccp",
    "studio_consulenza",
]


async def get_azienda() -> dict:
    """Dati azienda = default + eventuali override salvati nelle Impostazioni."""
    dati = dict(DEFAULT_AZIENDA)
    try:
        doc = await db.impostazioni.find_one({"_id": _DOC_ID})
    except Exception:
        doc = None  # se Mongo non risponde si usano i default
    if doc:
        for chiave in CAMPI_MODIFICABILI:
            valore = doc.get(chiave)
            if valore is not None and str(valore).strip() != "":
                dati[chiave] = str(valore).strip()
    return dati


async def set_azienda(campi: dict) -> dict:
    """Salva gli override (solo i campi ammessi) e ritorna i dati aggiornati."""
    update = {
        chiave: str(valore).strip()
        for chiave, valore in (campi or {}).items()
        if chiave in CAMPI_MODIFICABILI and valore is not None
    }
    if update:
        await db.impostazioni.update_one({"_id": _DOC_ID}, {"$set": update}, upsert=True)
    return await get_azienda()


def riga_dettaglio(a: dict) -> str:
    """Riga unica: 'Indirizzo · P.IVA … · Cod. Dest. … · tel · email'."""
    a = a or {}
    parti = [
        a.get("indirizzo", ""),
        (f"P.IVA {a['partita_iva']}" if a.get("partita_iva") else ""),
        (f"Cod. Dest. {a['codice_destinatario']}" if a.get("codice_destinatario") else ""),
        a.get("telefono", ""),
        a.get("email", ""),
    ]
    return " · ".join(p for p in parti if p)


def intestazione_html(a: dict) -> str:
    """Blocco intestazione per le stampe HTML (report HACCP, manuale, schede)."""
    a = a or {}
    nome = _html.escape(a.get("ragione_sociale", ""))
    dettaglio = _html.escape(riga_dettaglio(a))
    return (
        '<div style="text-align:center;margin-bottom:10px">'
        f'<div style="font-size:15px;font-weight:800;color:#2a3329">{nome}</div>'
        f'<div style="font-size:10px;color:#64748b">{dettaglio}</div>'
        "</div>"
    )


router = APIRouter(prefix="/azienda", tags=["azienda"])


@router.get("")
async def leggi_azienda():
    """Dati azienda correnti usati in tutti i PDF/stampe.
    Include 'salvata'=True se l'utente ha personalizzato i dati (doc override su Mongo),
    usato dalla Configurazione guidata per auto-verificare il passo 'Dati azienda'."""
    dati = await get_azienda()
    try:
        doc = await db.impostazioni.find_one({"_id": _DOC_ID})
    except Exception:
        doc = None
    dati["salvata"] = bool(doc)
    return dati


@router.put("")
async def aggiorna_azienda(payload: dict = Body(...)):
    """Aggiorna i dati azienda (incl. il codice destinatario SDI)."""
    return await set_azienda(payload)
