"""Collega le scadenze del Calendario fiscale ai codici tributo del Piano tributi.

Il calendario dice *quando* si scade, il Piano tributi dice *quali codici* devono
arrivare e *se sono arrivati* (quietanza, banca). Qui non c'e' un secondo motore:
si legge la griglia del Piano (`piano_tributi.griglia`) e si attacca a ogni
scadenza che ha una voce corrispondente. Sola lettura: non cambia mai `completato`
(la conferma del titolare resta sua); dice solo se la conferma e' sostenuta da un F24.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from app.services import piano_tributi

logger = logging.getLogger(__name__)

# id della scadenza del calendario -> [(voce del Piano, periodo della casella)]
_MENSILI = (
    (re.compile(r"^ritenute_\d{4}_(\d{2})$"), "ritenute_1001"),
    (re.compile(r"^inps_\d{4}_(\d{2})$"), "inps_dm10"),
    (re.compile(r"^iva_liq_\d{4}_(\d{2})$"), "iva_mensile"),
)
# Voci annuali: periodo None = l'unica casella della voce, qualunque scadenza abbia configurato il titolare.
_ANNUALI = {
    "ires_saldo": [("ires_saldo", None), ("ires_acconto_1", None)],
    "irap_saldo": [("irap_saldo", None), ("irap_acconto_1", None)],
    "ires_acconto2": [("ires_acconto_2", None)],
    "irap_acconto2": [("irap_acconto_2", None)],
}
# Solo «nessun F24 in archivio»: un modello presente ma non pagato ha il suo stato («Scaduto, non pagato»).
_STATI_SENZA_F24 = {piano_tributi.MANCA_F24}


def voci_della_scadenza(scadenza_id: str) -> List[Tuple[str, Optional[str]]]:
    """Voce del Piano e periodo per una scadenza del calendario, o [] se non c'e' un codice da attendere."""
    for regola, voce in _MENSILI:
        m = regola.match(scadenza_id or "")
        if m:
            return [(voce, m.group(1))]
    for prefisso, voci in _ANNUALI.items():
        if (scadenza_id or "").startswith(prefisso + "_"):
            return list(voci)
    return []


def _codici_del_periodo(voce: Dict[str, Any], periodo: Optional[str]) -> List[str]:
    """IVA mensile: del Piano resta solo il codice del mese della casella (6002 per febbraio)."""
    codici = list(voce.get("codici") or [])
    if voce.get("id") == "iva_mensile" and periodo:
        solo = [c for c in codici if c == f"60{periodo}"]
        return solo or codici
    return codici


def _sintesi(casella: Dict[str, Any], voce: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "voce_id": voce["id"],
        "etichetta": voce["etichetta"],
        "codici": _codici_del_periodo(voce, casella.get("periodo")),
        "obbligatorio": bool(voce.get("obbligatorio", True)),
        "stato": casella["stato"],
        "etichetta_stato": casella["etichetta_stato"],
        "giorni_scaduto": casella.get("giorni_scaduto"),
        "importo": casella.get("importo"),
        "versamenti": [
            {"f24_id": m.get("f24_id"), "data_versamento": m.get("data_versamento"),
             "stato": m.get("stato")}
            for m in casella.get("modelli") or []
        ],
    }


def collega_scadenze(scadenze: List[Dict[str, Any]], griglia: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Aggiunge a ogni scadenza con codici attesi il riscontro del Piano (funzione pura)."""
    indice: Dict[Tuple[str, Optional[str]], Tuple[Dict[str, Any], Dict[str, Any]]] = {}
    for riga in griglia.get("voci") or []:
        voce = riga["voce"]
        for casella in riga["caselle"]:
            indice[(voce["id"], casella["periodo"])] = (voce, casella)
        if len(riga["caselle"]) == 1:
            indice[(voce["id"], None)] = (voce, riga["caselle"][0])

    for scadenza in scadenze:
        trovate = []
        for voce_id, periodo in voci_della_scadenza(str(scadenza.get("id") or "")):
            coppia = indice.get((voce_id, periodo))
            if coppia:
                trovate.append(_sintesi(coppia[1], coppia[0]))
        if not trovate:
            continue
        scadenza["codici_attesi"] = sorted({c for t in trovate for c in t["codici"]})
        scadenza["piano_voci"] = trovate
        # La conferma a mano e' incoerente solo se una voce obbligatoria e' scaduta senza F24.
        scadenza["conferma_senza_f24"] = bool(
            scadenza.get("completato")
            and scadenza.get("provenienza_stato") == "conferma_manuale"
            and any(t["obbligatorio"] and t["stato"] in _STATI_SENZA_F24 for t in trovate)
        )
    return scadenze


async def collega_al_piano(db, anno: int, scadenze: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Un guasto del Piano non rompe il calendario: le scadenze restano com'erano."""
    try:
        griglia = await piano_tributi.griglia(db, anno, scrivi=False)
    except Exception as exc:
        logger.warning("Calendario: Piano tributi non leggibile per %s: %s %s", anno, type(exc).__name__, exc)
        return scadenze
    return collega_scadenze(scadenze, griglia)
