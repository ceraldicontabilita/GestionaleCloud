"""Termini di recupero dei tributi non trovati: entro quando l'ente puo' ancora chiederli.

01/10/2026, richiesta del titolare. La lettura dei termini sta in una sola
fonte, la vista ``verifica.tabulato_tributi_termini`` (scadenza di legge,
slittamento Covid, data entro cui Agenzia, INPS o Comune possono ancora
chiedere il versamento mancante). Lo schema ``verifica`` non e' leggibile dal
ruolo applicativo: l'unico ingresso e' ``public.gc_termini_recupero()``
(segreto runtime, come le altre ``gc_*``), chiamata da
``SupabaseRuntimeDatabase.termini_recupero``.

Qui non si calcola nessun termine: si legge la riga, si porta l'importo in
centesimi interi (mai ``float``), si contano i giorni rimasti sul fuso
``Europe/Rome`` e si ordina. Un tributo il cui termine non e' determinabile
resta «da verificare»: non si dice mai «ancora recuperabile» senza una data.

Il termine e' **indicativo**: un atto gia' notificato, una sospensione o la
denuncia di un lavoratore possono allungarlo. Va confermato con il
commercialista (la pagina lo dice sempre, `AVVISO`).
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Optional
from zoneinfo import ZoneInfo

AVVISO = "Termini indicativi, da confermare con il commercialista."

# Tributi per i quali ha senso chiedersi «fino a quando l'ente puo' chiederlo»:
# il versamento non c'e', oppure c'e' il modello F24 ma non la quietanza.
STATI_APERTI = ("MANCANTE", "F24_SENZA_QUIETANZA")
SOGLIA_URGENZA_GIORNI = 120

ANCORA_RECUPERABILE = "ANCORA_RECUPERABILE"
TERMINE_SCADUTO = "TERMINE_SCADUTO"
DA_VERIFICARE = "DA_VERIFICARE"

ETICHETTE_STATO = {
    "MANCANTE": "Versamento non trovato",
    "F24_SENZA_QUIETANZA": "F24 senza quietanza",
    "NON_SCADUTO": "Non ancora scaduto",
    "PAGATO": "Pagato",
    "PAGATO_SOLO_QUIETANZA": "Pagato, solo quietanza",
}
ETICHETTE_SITUAZIONE = {
    ANCORA_RECUPERABILE: "Ancora recuperabile dall'ente",
    TERMINE_SCADUTO: "Termine scaduto (salvo atti gia' notificati)",
    DA_VERIFICARE: "Termine non determinabile",
}
ORDINE_SITUAZIONE = {ANCORA_RECUPERABILE: 0, TERMINE_SCADUTO: 1, DA_VERIFICARE: 2}


def oggi_roma() -> date:
    return datetime.now(ZoneInfo("Europe/Rome")).date()


def _data(valore: Any) -> Optional[date]:
    if not valore:
        return None
    try:
        return date.fromisoformat(str(valore)[:10])
    except ValueError:
        return None


def _cents(valore: Any) -> Optional[int]:
    """Importo in centesimi interi: ``None`` resta ``None``, mai zero."""
    if valore in (None, ""):
        return None
    try:
        return int((Decimal(str(valore)) * 100).to_integral_value())
    except (InvalidOperation, ValueError):
        return None


def normalizza(riga: Dict[str, Any], oggi: date) -> Dict[str, Any]:
    """Riga della vista -> riga della pagina, con giorni rimasti e urgenza."""
    stato = str(riga.get("stato") or "")
    termine = _data(riga.get("recuperabile_entro"))
    giorni = (termine - oggi).days if termine else None
    if stato not in STATI_APERTI:
        situazione = None
    elif termine is None:
        situazione = DA_VERIFICARE
    elif giorni is not None and giorni < 0:
        situazione = TERMINE_SCADUTO
    else:
        situazione = ANCORA_RECUPERABILE
    return {
        "chiave": "|".join(str(riga.get(k) or "") for k in ("codice", "periodo", "scadenza")),
        "codice": riga.get("codice"),
        "tributo": riga.get("tributo"),
        "tipo": riga.get("tipo"),
        "periodo": riga.get("periodo"),
        "scadenza": riga.get("scadenza"),
        "stato": stato,
        "stato_label": ETICHETTE_STATO.get(stato, stato),
        "esito": riga.get("esito"),
        "pagato_cents": _cents(riga.get("pagato")),
        "date_pagamento": riga.get("date_pagamento"),
        "protocolli": riga.get("protocolli"),
        "ha_f24": bool(riga.get("ha_f24")),
        "termine_ordinario": riga.get("termine_ordinario"),
        "slittamento_covid": riga.get("slittamento_covid"),
        "recuperabile_entro": termine.isoformat() if termine else None,
        "giorni_rimasti": giorni if situazione == ANCORA_RECUPERABILE else None,
        "situazione": situazione,
        "situazione_label": ETICHETTE_SITUAZIONE.get(situazione) if situazione else None,
        "urgente": situazione == ANCORA_RECUPERABILE and giorni is not None and giorni < SOGLIA_URGENZA_GIORNI,
    }


def _chiave_ordine(voce: Dict[str, Any]):
    """Prima «ancora recuperabile» dalla data piu' vicina; poi le scadute, la
    piu' recente per prima; in fondo quelle senza termine."""
    gruppo = ORDINE_SITUAZIONE.get(voce["situazione"], 3)
    termine = _data(voce["recuperabile_entro"])
    if gruppo == 0 and termine:
        posizione = termine.toordinal()
    elif gruppo == 1 and termine:
        posizione = -termine.toordinal()
    else:
        posizione = 0
    return (gruppo, posizione, voce["codice"] or "", voce["scadenza"] or "", voce["periodo"] or "")


def _facet(voci: Iterable[Dict[str, Any]], campo: str, etichette: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    conteggi: Dict[str, int] = {}
    for v in voci:
        valore = v.get(campo)
        if valore:
            conteggi[valore] = conteggi.get(valore, 0) + 1
    return [{"id": k, "label": (etichette or {}).get(k, k), "n": n} for k, n in sorted(conteggi.items())]


def riepilogo(
    righe: Iterable[Dict[str, Any]],
    *,
    oggi: Optional[date] = None,
    stato: Optional[str] = None,
    situazione: Optional[str] = None,
    codice: Optional[str] = None,
    cerca: Optional[str] = None,
) -> Dict[str, Any]:
    """Elenco filtrato e ordinato, con i conteggi sull'insieme intero.

    ``stato`` assente = solo i tributi con il versamento mancante
    (``STATI_APERTI``); ``TUTTI`` toglie il filtro.
    """
    oggi = oggi or oggi_roma()
    tutte = [normalizza(r, oggi) for r in righe]
    aperte = [v for v in tutte if v["stato"] in STATI_APERTI]

    if not stato:
        scelte = aperte
    elif stato == "TUTTI":
        scelte = list(tutte)
    else:
        scelte = [v for v in tutte if v["stato"] == stato]
    if situazione:
        scelte = [v for v in scelte if v["situazione"] == situazione]
    if codice:
        scelte = [v for v in scelte if v["codice"] == codice]
    testo = (cerca or "").strip().casefold()
    if testo:
        scelte = [v for v in scelte if testo in " ".join(
            str(v.get(k) or "") for k in ("codice", "tributo", "periodo", "esito")).casefold()]
    scelte.sort(key=_chiave_ordine)

    ancora = [v for v in aperte if v["situazione"] == ANCORA_RECUPERABILE]
    primo = min(ancora, key=lambda v: v["recuperabile_entro"], default=None)
    return {
        "oggi": oggi.isoformat(),
        "avviso": AVVISO,
        "soglia_urgenza_giorni": SOGLIA_URGENZA_GIORNI,
        "voci": scelte,
        "totale": len(scelte),
        "conteggi": {
            "righe": len(tutte),
            "aperte": len(aperte),
            "ancora_recuperabili": len(ancora),
            "urgenti": sum(1 for v in ancora if v["urgente"]),
            "scadute": sum(1 for v in aperte if v["situazione"] == TERMINE_SCADUTO),
            "da_verificare": sum(1 for v in aperte if v["situazione"] == DA_VERIFICARE),
        },
        "primo_termine": ({
            "recuperabile_entro": primo["recuperabile_entro"],
            "giorni_rimasti": primo["giorni_rimasti"],
            "codice": primo["codice"],
            "periodo": primo["periodo"],
        } if primo else None),
        "facets": {
            "stati": _facet(tutte, "stato", ETICHETTE_STATO),
            "situazioni": _facet(aperte, "situazione", ETICHETTE_SITUAZIONE),
            "codici": _facet(aperte, "codice"),
        },
    }
