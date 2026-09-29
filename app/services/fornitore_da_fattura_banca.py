"""«A chi appartiene?» letto dalla fattura, senza che il titolare lo insegni.

Un addebito che il motore per causale non sa attribuire (es. l'SDD «AMAZON
PAYMENTS EUROPE» da 51,72 €) ha quasi sempre la sua fattura già in archivio:
stesso importo al centesimo, emessa poco prima, dal fornitore che la causale
nomina. Identità (nome del fornitore in causale) più importo al centesimo più
finestra di date: mai il solo importo. Se le fatture compatibili sono di più
fornitori il caso resta al titolare, che lo insegna dalla pagina Regole banca.

Scrive solo sul movimento (fornitore, categoria «Fatture», motivo): non crea
regole imparate (un pattern «AMAZON» varrebbe per due anagrafiche diverse) e
non lega la fattura, che resta compito dei motori di riconciliazione.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.constants.fattura_attiva import FILTRO_FATTURA_ATTIVA
from app.services.regole_riconoscimento_banca import _PAROLE_GENERICHE_BANCARIE

logger = logging.getLogger(__name__)

GIORNI_PRIMA_ADDEBITO = 60
GIORNI_DOPO_ADDEBITO = 3

_PAROLE_SOCIETARIE = {
    "SRL", "SPA", "SAS", "SNC", "SARL", "SEDE", "SECONDARIA", "SUCCURSALE",
    "ITALIA", "ITALIANA", "GROUP", "SOCIETA", "SERVICE", "SERVICES",
    "PAYMENTS", "EUROPE", "BUSINESS", "COMPANY",
}
_ESCLUSE = _PAROLE_GENERICHE_BANCARIE | _PAROLE_SOCIETARIE


def _parole_distintive(testo: Any) -> set:
    parole = re.findall(r"[A-ZÀ-Ù0-9]+", str(testo or "").upper())
    return {p for p in parole if len(p) >= 5 and p not in _ESCLUSE}


def _cent(valore: Any) -> Optional[int]:
    try:
        return round(abs(float(valore)) * 100)
    except (TypeError, ValueError):
        return None


def _e_uscita(mov: Dict[str, Any]) -> bool:
    """CSV e banca diretta: importo positivo e verso in `tipo`; vecchio
    archivio: importo con segno e `tipo` assente."""
    tipo = str(mov.get("tipo") or "").lower()
    if tipo:
        return tipo == "uscita"
    try:
        return float(mov.get("importo") or 0) < 0
    except (TypeError, ValueError):
        return False


def _giorno(valore: Any) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(valore)[:10])
    except (TypeError, ValueError):
        return None


def _nome_fattura(f: Dict[str, Any]) -> str:
    return f.get("supplier_name") or f.get("cedente_denominazione") or f.get("fornitore") or ""


def _chiave_fornitore(f: Dict[str, Any]) -> str:
    return str(
        f.get("supplier_id") or f.get("fornitore_id")
        or f.get("supplier_vat") or f.get("cedente_piva") or _nome_fattura(f)
    )


def scegli_fornitore(
    movimento: Dict[str, Any], fatture: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """La fattura che dice a chi appartiene il movimento, o None se non è
    certa (nessuna compatibile, oppure fornitori diversi)."""
    causale = movimento.get("descrizione_originale") or movimento.get("descrizione") or ""
    importo = _cent(movimento.get("importo"))
    data = _giorno(movimento.get("data"))
    parole_causale = _parole_distintive(causale)
    if importo is None or importo == 0 or data is None or not parole_causale:
        return None

    compatibili = []
    for f in fatture:
        if _cent(f.get("total_amount") or f.get("importo_totale")) != importo:
            continue
        emessa = _giorno(f.get("invoice_date") or f.get("data_fattura"))
        if emessa is None:
            continue
        if not (data - timedelta(days=GIORNI_PRIMA_ADDEBITO)
                <= emessa <= data + timedelta(days=GIORNI_DOPO_ADDEBITO)):
            continue
        if not (_parole_distintive(_nome_fattura(f)) & parole_causale):
            continue
        compatibili.append(f)

    fornitori = {_chiave_fornitore(f) for f in compatibili}
    if len(fornitori) != 1:
        return None
    return max(compatibili, key=lambda f: str(f.get("invoice_date") or ""))


def _campi_movimento(fattura: Dict[str, Any]) -> Dict[str, Any]:
    numero = fattura.get("invoice_number") or fattura.get("numero_fattura") or "?"
    data = str(fattura.get("invoice_date") or "")[:10]
    gg = "/".join(reversed(data.split("-"))) if data.count("-") == 2 else data
    return {
        "categoria": "Fatture",
        "categoria_auto": True,
        "categoria_auto_motivo": (
            f"fornitore letto dalla fattura {numero} del {gg}: importo al "
            "centesimo e nome in causale"
        ),
        "categoria_auto_at": datetime.now(timezone.utc).isoformat(),
        "fornitore_id": str(fattura.get("supplier_id") or fattura.get("fornitore_id") or "") or None,
        "fornitore": _nome_fattura(fattura) or None,
        "fornitore_da_fattura_id": fattura.get("id"),
    }


_PROIEZIONE_FATTURE = {
    "_id": 0, "id": 1, "invoice_number": 1, "numero_fattura": 1, "invoice_date": 1,
    "data_fattura": 1, "total_amount": 1, "importo_totale": 1, "supplier_id": 1,
    "fornitore_id": 1, "supplier_name": 1, "cedente_denominazione": 1, "fornitore": 1,
    "supplier_vat": 1, "cedente_piva": 1,
}


async def assegna_fornitori_da_fatture(
    db, movimenti: List[Dict[str, Any]], *, dry_run: bool = False,
) -> Dict[str, Any]:
    """Per ogni movimento in uscita senza categoria né fornitore, cerca la
    fattura che lo spiega e scrive fornitore e categoria. Un prefetch unico
    delle fatture attive con gli importi in gioco."""
    da_esaminare = [m for m in movimenti if _e_uscita(m)
                    and not m.get("categoria") and not m.get("fornitore_id")]
    importi = {c for c in (_cent(m.get("importo")) for m in da_esaminare) if c}
    if not importi:
        return {"esaminati": 0, "assegnati": 0, "movimenti": []}

    fatture = await db["invoices"].find(
        dict(FILTRO_FATTURA_ATTIVA), _PROIEZIONE_FATTURE,
    ).to_list(50000)
    per_importo: Dict[int, List[Dict[str, Any]]] = {}
    for f in fatture:
        c = _cent(f.get("total_amount") or f.get("importo_totale"))
        if c in importi:
            per_importo.setdefault(c, []).append(f)

    assegnati = []
    for mov in da_esaminare:
        fattura = scegli_fornitore(mov, per_importo.get(_cent(mov.get("importo")), []))
        if fattura is None:
            continue
        campi = _campi_movimento(fattura)
        assegnati.append({"movimento_id": mov.get("id"), **campi})
        if not dry_run:
            await db["estratto_conto_movimenti"].update_one(
                {"id": mov["id"]}, {"$set": campi},
            )
    return {"esaminati": len(da_esaminare), "assegnati": len(assegnati), "movimenti": assegnati}


async def assegna_alla_fattura_arrivata(db, fattura: Dict[str, Any]) -> Dict[str, Any]:
    """All'arrivo della fattura: i movimenti ancora senza fornitore con il suo
    importo al centesimo (query stretta, mai un ripasso d'archivio)."""
    importo = _cent(fattura.get("total_amount") or fattura.get("importo_totale"))
    if not importo:
        return {"esaminati": 0, "assegnati": 0, "movimenti": []}
    valore = importo / 100
    movimenti = await db["estratto_conto_movimenti"].find(
        {
            "$and": [
                {"$or": [{"categoria": None}, {"categoria": ""}, {"categoria": {"$exists": False}}]},
                {"$or": [
                    {"tipo": "uscita", "importo": {"$gte": valore - 0.004, "$lte": valore + 0.004}},
                    {"$or": [{"tipo": None}, {"tipo": ""}, {"tipo": {"$exists": False}}],
                     "importo": {"$gte": -valore - 0.004, "$lte": -valore + 0.004}},
                ]},
            ],
            "fornitore_id": {"$exists": False},
        },
        {"_id": 0, "id": 1, "data": 1, "importo": 1, "tipo": 1, "categoria": 1,
         "fornitore_id": 1, "descrizione": 1, "descrizione_originale": 1},
    ).limit(50).to_list(50)
    return await assegna_fornitori_da_fatture(db, movimenti)
