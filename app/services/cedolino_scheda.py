"""Scheda di una busta paga per la vista ``/personale/cedolini/:id`` (MINI-08).

Sola lettura sul registro ``cedolini``. Un dato assente resta ``None``: la
pagina scrive «Dato non disponibile», mai zero. Il PDF non viaggia nella
scheda: si apre a parte dall'endpoint unico degli originali
(``/api/originale/cedolino/{id}``, DRV-04).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.services import cedolini_versioni as versioni
from app.services.originale_documento import url_originale

_ESCLUSI = {"_id": 0, "pdf_data": 0, "_raw_text": 0, "pdf_text": 0}
_MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
         "settembre", "ottobre", "novembre", "dicembre"]


def _numero(valore: Any) -> Optional[float]:
    """Un importo letto, o ``None``: mai un ``0`` di comodo."""
    if valore is None or valore == "":
        return None
    try:
        return float(valore)
    except (TypeError, ValueError):
        return None


def pdf_disponibile(doc: Dict[str, Any]) -> bool:
    stato = doc.get("_payload_stato") if isinstance(doc.get("_payload_stato"), dict) else {}
    return bool(doc.get("drive_file_id") or doc.get("pdf_disponibile") or stato.get("pdf_data") == "pieno")


def _periodo(doc: Dict[str, Any]) -> Optional[str]:
    mese, anno = versioni._intero(doc.get("mese")), versioni._intero(doc.get("anno"))
    if not (mese and anno and 1 <= mese <= 12):
        return None
    return f"{_MESI[mese - 1].capitalize()} {anno}"


def _versione_gruppo(riga: Dict[str, Any], corrente_id: Optional[str]) -> Dict[str, Any]:
    r = versioni._riassunto(riga)
    r["corrente"] = riga.get("id") == corrente_id
    r["status"] = riga.get("status")
    return r


async def scheda(db, cedolino_id: str) -> Optional[Dict[str, Any]]:
    doc = await db[versioni.COLL].find_one({"id": cedolino_id}, _ESCLUSI)
    if not doc:
        return None
    gruppo: List[Dict[str, Any]] = await versioni.righe_della_busta(db, doc)
    decisione = versioni.decidi(gruppo) if len(gruppo) > 1 else None
    chiave = versioni.chiave_busta(doc)
    netto = versioni.netto_di(doc)
    disponibile = pdf_disponibile(doc)
    if not disponibile:
        # Il marcatore `_payload_stato` non e' scritto su ogni riga (in archivio e'
        # assente): il PDF si prova per id, una lettura sola, come da regola 2.
        pieno = await db[versioni.COLL].find_one({"id": cedolino_id}, {"_id": 0, "pdf_data": 1})
        disponibile = bool((pieno or {}).get("pdf_data"))
    return {
        "id": doc.get("id"),
        "dipendente": doc.get("nome_dipendente") or doc.get("dipendente"),
        "anno": versioni._intero(doc.get("anno")),
        "mese": versioni._intero(doc.get("mese")),
        "periodo": _periodo(doc),
        "tipo": chiave[3] if chiave else (doc.get("tipo_cedolino") or None),
        "filename": doc.get("filename") or doc.get("pdf_filename"),
        "canale": doc.get("canale"),
        "status": doc.get("status"),
        "sostituito": str(doc.get("status") or "").lower() == versioni.STATUS_SOSTITUITO,
        "netto": float(netto) if netto is not None else None,
        "netto_fonte": doc.get("netto_fonte"),
        "stato_netto": doc.get("stato_netto"),
        "lordo": _numero(doc.get("lordo")),
        "totale_trattenute": _numero(doc.get("totale_trattenute")),
        "pagato": bool(doc.get("pagato")),
        "versione": {
            "variante": versioni.variante_di(doc),
            "stampa_di_controllo": versioni.stampa_di_controllo(doc),
            "rettificato": bool(doc.get("rettificato")),
            "n_versioni_totali": doc.get("n_versioni_totali"),
            "versioni_scartate": doc.get("versioni_scartate") or [],
            "storico_netto": doc.get("storico_netto") or [],
            "da_decidere": bool(doc.get("varianti_da_decidere")),
        },
        "versioni_gruppo": [_versione_gruppo(r, doc.get("id")) for r in gruppo],
        "decisione": ({"esito": decisione["esito"], "motivo": decisione.get("motivo") or "",
                       "vincitore": (decisione.get("vincitore") or {}).get("id")}
                      if decisione else None),
        "pdf_disponibile": disponibile,
        "pdf_url": url_originale("cedolino", doc.get("id")) if disponibile else None,
    }
