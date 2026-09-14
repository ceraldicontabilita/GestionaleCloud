"""Stato del rapporto di lavoro: UN solo concetto, con data e motivo.

Titolare 14/09/2026 (pagina Anagrafica HR): «tre stati diversi per lo stesso
concetto» (attivo / inattivo / cessato), la cessazione senza data ne' motivo,
l'icona che cambiava stato senza chiedere nulla. Da qui in poi:

* ``stato`` vale solo ``attivo`` o ``cessato``; ``attivo`` (bool) e
  ``in_carico`` seguono sempre lo stato (mai piu' ``stato=inattivo`` con
  ``attivo=true`` come e' successo a Moscato il 14/09);
* un cessato ha ``data_fine_rapporto`` (gg/mm/aaaa nella UI), ``motivo_cessazione``
  fra quelli di ``MOTIVI_CESSAZIONE`` e ``riferimento_cessazione`` (numero del
  modulo dimissioni / protocollo UNILAV);
* ``data_cessazione`` e ``data_dimissione`` restano scritti per i lettori
  storici (TFR, cedolini, portale), ma la fonte e' ``data_fine_rapporto``.

Le funzioni qui sono usate dal router HR, dal ponte verso Lotti
(``app/routers/lotti_integration.py``) e dal modulo dimissioni del gestionale.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

MOTIVI_CESSAZIONE = (
    "dimissioni", "licenziamento", "fine_contratto", "risoluzione_consensuale", "altro",
)
ETICHETTE_MOTIVO = {
    "dimissioni": "Dimissioni", "licenziamento": "Licenziamento",
    "fine_contratto": "Fine contratto", "risoluzione_consensuale": "Risoluzione consensuale",
    "altro": "Altro",
}
STATI_NON_IN_FORZA = {"cessato", "dimesso", "archiviato", "inattivo", "disattivo"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def data_iso(valore: Any) -> Optional[str]:
    """``YYYY-MM-DD`` da ISO/gg-mm-aaaa; None se non e' una data."""
    testo = str(valore or "").strip()
    if not testo:
        return None
    if len(testo) >= 10 and testo[4] == "-" and testo[7] == "-":
        try:
            datetime.strptime(testo[:10], "%Y-%m-%d")
            return testo[:10]
        except ValueError:
            return None
    for sep in ("/", "-", "."):
        parti = testo[:10].split(sep)
        if len(parti) == 3 and len(parti[2]) == 4:
            try:
                return datetime(int(parti[2]), int(parti[1]), int(parti[0])).strftime("%Y-%m-%d")
            except ValueError:
                return None
    return None


def data_fine_rapporto(dip: Dict[str, Any]) -> Optional[str]:
    for campo in ("data_fine_rapporto", "data_cessazione", "data_dimissione", "data_cessazione_prevista"):
        d = data_iso(dip.get(campo))
        if d:
            return d
    return None


def e_in_forza(dip: Dict[str, Any]) -> bool:
    """Rapporto in corso: non fuso, non cessato, ``attivo`` non false."""
    if not dip or "merged_into" in dip:
        return False
    if dip.get("attivo") is False or dip.get("in_carico") is False:
        return False
    return str(dip.get("stato") or "attivo").strip().lower() not in STATI_NON_IN_FORZA


def stato_normalizzato(dip: Dict[str, Any]) -> str:
    return "attivo" if e_in_forza(dip) else "cessato"


def riepilogo_stato(dip: Dict[str, Any]) -> Dict[str, Any]:
    """Campi di stato esposti alla UI e a Lotti, sempre coerenti fra loro."""
    stato = stato_normalizzato(dip)
    motivo = str(dip.get("motivo_cessazione") or "").strip().lower() if stato == "cessato" else ""
    if motivo and motivo not in MOTIVI_CESSAZIONE:
        motivo = "altro" if not motivo.startswith("dimission") else "dimissioni"
    return {
        "stato": stato,
        "attivo": stato == "attivo",
        "data_fine_rapporto": data_fine_rapporto(dip) if stato == "cessato" else None,
        "motivo_cessazione": motivo or None,
        "motivo_cessazione_etichetta": ETICHETTE_MOTIVO.get(motivo) if motivo else None,
        "riferimento_cessazione": (dip.get("riferimento_cessazione") or (dip.get("dimissioni") or {}).get("codice_modulo") or None)
        if stato == "cessato" else None,
        "motivo_cessazione_originale": dip.get("motivo_cessazione") if stato == "cessato" else None,
    }


def campi_cessazione(data_fine: Any, motivo: str = "altro", riferimento: str = "",
                     note: str = "", fonte: str = "manuale") -> Dict[str, Any]:
    """``$set`` per cessare un rapporto. Solleva ValueError su data non valida."""
    d = data_iso(data_fine)
    if not d:
        raise ValueError("data di fine rapporto non valida (usa gg/mm/aaaa)")
    m = str(motivo or "altro").strip().lower()
    if m not in MOTIVI_CESSAZIONE:
        m = "altro"
    return {
        "stato": "cessato", "attivo": False, "in_carico": False,
        "data_fine_rapporto": d, "data_cessazione": d, "data_dimissione": d,
        "motivo_cessazione": m,
        "riferimento_cessazione": str(riferimento or "").strip(),
        "note_cessazione": str(note or "").strip(),
        "cessazione_fonte": fonte, "cessato_il": _now_iso(),
    }


def campi_riattivazione() -> Dict[str, Dict[str, Any]]:
    """Aggiornamento Mongo per rimettere in forza un cessato (storia conservata
    da chi chiama in ``cessazioni_precedenti``)."""
    return {
        "$set": {"stato": "attivo", "attivo": True, "in_carico": True, "riattivato_il": _now_iso()},
        "$unset": {"data_fine_rapporto": "", "data_cessazione": "", "data_dimissione": "",
                   "motivo_cessazione": "", "riferimento_cessazione": "", "note_cessazione": "",
                   "cessazione_fonte": "", "cessato_il": "", "data_cessazione_prevista": ""},
    }
