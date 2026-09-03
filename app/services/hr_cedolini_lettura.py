"""Lettura di SOLA LETTURA dei cedolini dell'app HR (``public.app_cedolini``).

Riusa il punto unico di connessione di ``hr_cedolini_deposito`` (``dsn_hr`` +
``connetti_hr``): stessa DSN, stessa tabella, nessuna scrittura. Serve al
controllo incrociato F24 ↔ ritenute dei cedolini (avviso bonario, PR 11):
per un tributo da sostituto d'imposta (1001, 1012, 1040, 3802, 3847/3848,
DM10) la somma delle ritenute/contributi del mese deve coincidere con la
riga F24 del periodo.

Cosa contengono davvero i 1291 cedolini HR (verificato il 03/09/2026 sui
dati reali): ``lordo``, ``netto``, ``competenze``, ``trattenute`` (totale),
``retribuzione`` (paga base/contingenza), ``acconti``; NON esistono campi
``irpef``/``contributi_inps``/``addizionale_*`` ne' un elenco ``voci``.
Il riepilogo qui sotto quindi usa i campi per natura quando esistono e,
quando mancano, espone solo il totale ``trattenute`` marcandolo
``attendibile: False`` — mai un numero spacciato per la ritenuta IRPEF.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from app.services import hr_cedolini_deposito as deposito

logger = logging.getLogger(__name__)

# Campi (in ordine di preferenza) che un cedolino HR potrebbe esporre per
# ciascuna natura di trattenuta. I nomi seguono quelli usati dai parser
# dell'app HR; nessuno di questi risulta oggi popolato nell'archivio reale.
CAMPI_PER_NATURA: Dict[str, tuple] = {
    "irpef": ("irpef", "ritenute_irpef", "ritenuta_irpef", "irpef_netta", "irpef_trattenuta"),
    "addizionale_regionale": ("addizionale_regionale", "add_regionale", "addizionale_regionale_irpef"),
    "addizionale_comunale": ("addizionale_comunale", "add_comunale", "addizionale_comunale_irpef"),
    "inps": ("contributi_inps", "inps", "inps_dipendente", "contributi_previdenziali", "contributi_sociali"),
}

# Codici busta (elenco ``voci``, se un giorno verra' estratto) per natura.
CODICI_VOCI_PER_NATURA: Dict[str, tuple] = {
    "irpef": ("IRPEF", "RITENUTE IRPEF", "IMPOSTA NETTA"),
    "addizionale_regionale": ("ADD. REGIONALE", "ADDIZIONALE REGIONALE", "ADD.REG"),
    "addizionale_comunale": ("ADD. COMUNALE", "ADDIZIONALE COMUNALE", "ADD.COM"),
    "inps": ("INPS", "CONTRIBUTI INPS", "CONTR. INPS", "FAP"),
}

_SQL_CEDOLINI_PERIODO = (
    "SELECT (doc - 'pdf_data') AS doc FROM " + deposito.TABELLA_CEDOLINI +
    " WHERE doc->>'anno' ~ '^[0-9]+$' AND (doc->>'anno')::int = $1"
    "   AND doc->>'mese' ~ '^[0-9]+$' AND (doc->>'mese')::int = $2"
)


def _numero(valore: Any) -> Optional[float]:
    if valore in (None, "", False):
        return None
    if isinstance(valore, str) and "," in valore:
        valore = valore.replace(".", "").replace(",", ".")
    try:
        return float(valore)
    except (TypeError, ValueError):
        return None


def _doc(riga: Any) -> Dict[str, Any]:
    doc = riga["doc"] if isinstance(riga, dict) else riga[0]
    if isinstance(doc, str):
        doc = json.loads(doc)
    return dict(doc or {})


async def cedolini_hr_periodo(anno: int, mese: int) -> Dict[str, Any]:
    """Cedolini HR del mese (senza PDF). Non solleva mai: un errore di rete
    o l'assenza della DSN sono esiti espliciti, non eccezioni."""
    dsn = deposito.dsn_hr()
    if not dsn:
        return {"configurato": False, "cedolini": [], "errore": "hr_non_configurato"}
    try:
        con = await deposito.connetti_hr(dsn)
    except Exception as exc:  # noqa: BLE001 - la lettura HR non deve mai bloccare il controllo
        logger.warning("[HR lettura] connessione non riuscita: %s", exc)
        return {"configurato": True, "cedolini": [], "errore": f"connessione_hr: {exc}"}
    try:
        righe = await con.fetch(_SQL_CEDOLINI_PERIODO, int(anno), int(mese))
        return {"configurato": True, "cedolini": [_doc(r) for r in righe], "errore": None}
    except Exception as exc:  # noqa: BLE001
        logger.warning("[HR lettura] query cedolini %s/%s non riuscita: %s", mese, anno, exc)
        return {"configurato": True, "cedolini": [], "errore": f"lettura_hr: {exc}"}
    finally:
        try:
            await con.close()
        except Exception:  # noqa: BLE001
            pass


def _importo_da_voci(cedolino: Dict[str, Any], natura: str) -> Optional[float]:
    voci = cedolino.get("voci")
    if not isinstance(voci, list):
        return None
    etichette = CODICI_VOCI_PER_NATURA.get(natura, ())
    totale = None
    for voce in voci:
        if not isinstance(voce, dict):
            continue
        testo = " ".join(
            str(voce.get(k) or "") for k in ("codice", "descrizione", "voce", "causale")
        ).upper()
        if not any(et in testo for et in etichette):
            continue
        importo = _numero(voce.get("trattenuta") or voce.get("importo") or voce.get("ritenuta"))
        if importo is None:
            continue
        totale = (totale or 0.0) + abs(importo)
    return totale


def riepilogo_ritenute(
    cedolini: List[Dict[str, Any]], natura: str, importo_atteso: Optional[float] = None,
) -> Dict[str, Any]:
    """Somma per natura (irpef / addizionali / inps) sui cedolini del periodo.

    Se nessun cedolino espone la natura richiesta, il riepilogo NON e'
    attendibile: espone il solo totale ``trattenute`` (che include anche i
    contributi a carico del dipendente) come dato di contesto.
    """
    campi = CAMPI_PER_NATURA.get(natura, ())
    totale = 0.0
    con_campo = 0
    campo_usato: Optional[str] = None
    trattenute_totali = 0.0
    dipendenti: List[Dict[str, Any]] = []
    for ced in cedolini:
        tratt = _numero(ced.get("trattenute"))
        if tratt is not None:
            trattenute_totali += tratt
        valore = None
        for campo in campi:
            valore = _numero(ced.get(campo))
            if valore is not None:
                campo_usato = campo_usato or campo
                break
        if valore is None:
            valore = _importo_da_voci(ced, natura)
            if valore is not None:
                campo_usato = campo_usato or "voci"
        if valore is not None:
            con_campo += 1
            totale += abs(valore)
        dipendenti.append({
            "nome": ced.get("nome_dipendente") or ced.get("dipendente_nome"),
            "codice_fiscale": ced.get("codice_fiscale"),
            "tipo_cedolino": ced.get("tipo_cedolino"),
            "valore": round(abs(valore), 2) if valore is not None else None,
            "trattenute": round(tratt, 2) if tratt is not None else None,
        })

    attendibile = bool(cedolini) and con_campo == len(cedolini)
    if not cedolini:
        motivo = "nessun_cedolino_hr_nel_periodo"
    elif con_campo == 0:
        motivo = "voci_non_estratte_nei_cedolini_hr"
    elif con_campo < len(cedolini):
        motivo = "natura_assente_su_alcuni_cedolini"
    else:
        motivo = None
    totale_arr = round(totale, 2) if con_campo else None
    differenza = (
        round(float(importo_atteso) - totale_arr, 2)
        if importo_atteso is not None and totale_arr is not None else None
    )
    return {
        "natura": natura,
        "n_cedolini": len(cedolini),
        "n_cedolini_con_valore": con_campo,
        "campo_usato": campo_usato,
        "totale": totale_arr,
        "differenza_vs_avviso": differenza,
        "attendibile": attendibile,
        "motivo": motivo,
        "trattenute_totali": round(trattenute_totali, 2),
        "dipendenti": dipendenti,
    }
