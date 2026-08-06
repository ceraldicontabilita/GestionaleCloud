"""Stato di riconciliazione della giornata POS, circuito per circuito.

Una giornata attraversa due fasi indipendenti:

1. **fiscale** — l'elettronico dichiarato dall'XML RT deve coincidere con la
   somma dei circuiti (Nexi + SumUp + eventuali altri);
2. **bancaria** — ogni credito POS deve essere confermato da un accredito
   reale, al netto delle commissioni.

Il principio che regge tutto: un dato mancante non e' zero. Se l'XML non e'
ancora arrivato, la differenza non e' "tutto non battuto": e' "attende XML".
Confondere le due cose produrrebbe allarmi falsi ogni mattina, e allarmi
falsi ripetuti sono il modo piu' rapido per rendere inutile un controllo.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from app.services.scritture_contabili import normalizza_gestore_pos

TOLLERANZA = 0.01

# Ordine di gravita': il primo stato applicabile e' quello mostrato.
ATTENDE_XML = "attende_xml"
ATTENDE_DATI = "attende_dati_circuito"
NON_QUADRATO = "xml_pos_non_quadrato"
ATTESA_ACCREDITO = "in_attesa_di_accredito"
ACCREDITO_PARZIALE = "accredito_parziale"
COMMISSIONI_DA_VERIFICARE = "commissioni_da_verificare"
RICONCILIATO = "riconciliato"

ETICHETTE = {
    ATTENDE_XML: "Attende XML",
    ATTENDE_DATI: "Attende dati circuito",
    NON_QUADRATO: "XML-POS non quadrato",
    ATTESA_ACCREDITO: "In attesa di accredito",
    ACCREDITO_PARZIALE: "Accredito parziale",
    COMMISSIONI_DA_VERIFICARE: "Commissioni da verificare",
    RICONCILIATO: "Riconciliato",
}

# Stati che rappresentano lavoro ancora aperto: sono quelli contati nei
# badge, e devono calare da soli man mano che la riconciliazione avanza.
STATI_APERTI = (
    ATTENDE_XML, ATTENDE_DATI, NON_QUADRATO,
    ATTESA_ACCREDITO, ACCREDITO_PARZIALE, COMMISSIONI_DA_VERIFICARE,
)


def _arrotonda(valore: Any) -> float:
    try:
        return round(float(valore or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def stato_giornata(
    *,
    elettronico_xml: Optional[float],
    circuiti: Dict[str, Optional[float]],
    crediti: Optional[Iterable[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Calcola stato e differenze di una giornata.

    ``circuiti`` mappa il circuito al suo venduto, con ``None`` quando il dato
    non e' ancora arrivato: e' la differenza fra "SumUp ha incassato zero" e
    "SumUp non ha ancora risposto", che non vanno mai confuse.

    ``crediti`` sono le righe di trasferimento POS del giorno, da cui si legge
    quanto e' stato realmente accreditato.
    """
    presenti = {c: _arrotonda(v) for c, v in (circuiti or {}).items()
                if v is not None}
    mancanti = sorted(c for c, v in (circuiti or {}).items() if v is None)
    pos_complessivo = round(sum(presenti.values()), 2)

    esito: Dict[str, Any] = {
        "elettronico_xml": None if elettronico_xml is None
                           else _arrotonda(elettronico_xml),
        "circuiti": presenti,
        "circuiti_mancanti": mancanti,
        "pos_complessivo": pos_complessivo if presenti else None,
        "differenza_fiscale": None,
        "accredito_atteso": 0.0,
        "accreditato": 0.0,
        "commissioni": 0.0,
        "differenza_residua": 0.0,
    }

    # Si confronta solo quando TUTTI i circuiti hanno risposto: con SumUp
    # ancora muto, 500 contro 600 sembrerebbe un ammanco di 100 che non
    # esiste. Meglio nessuna differenza che una differenza falsa.
    if elettronico_xml is not None and presenti and not mancanti:
        # Positiva = incassato col POS ma non battuto sul registratore.
        esito["differenza_fiscale"] = round(pos_complessivo
                                            - _arrotonda(elettronico_xml), 2)

    righe = [r for r in (crediti or []) if isinstance(r, dict)]
    esito["accredito_atteso"] = round(
        sum(_arrotonda(r.get("importo")) for r in righe), 2)
    esito["accreditato"] = round(
        sum(_arrotonda(r.get("accreditato_ec")) for r in righe), 2)
    esito["commissioni"] = round(
        sum(_arrotonda(r.get("commissioni")) for r in righe), 2)
    esito["differenza_residua"] = round(
        esito["accredito_atteso"] - esito["accreditato"]
        - esito["commissioni"], 2)

    esito["stato"] = _classifica(esito, righe)
    esito["stato_etichetta"] = ETICHETTE[esito["stato"]]
    esito["aperto"] = esito["stato"] in STATI_APERTI
    return esito


def _classifica(esito: Dict[str, Any], righe: List[Dict[str, Any]]) -> str:
    # Fase 1: fiscale. Finche' non e' completa non ha senso guardare la banca,
    # perche' non si sa nemmeno quale sia l'importo corretto da attendere.
    if esito["elettronico_xml"] is None:
        return ATTENDE_XML
    if esito["circuiti_mancanti"]:
        return ATTENDE_DATI
    if abs(esito["differenza_fiscale"] or 0) > TOLLERANZA:
        return NON_QUADRATO

    # Fase 2: bancaria.
    if any(r.get("stato_riconciliazione") == COMMISSIONI_DA_VERIFICARE
           for r in righe):
        return COMMISSIONI_DA_VERIFICARE
    if not righe or esito["accredito_atteso"] <= TOLLERANZA:
        return RICONCILIATO
    if esito["accreditato"] <= TOLLERANZA:
        return ATTESA_ACCREDITO
    if abs(esito["differenza_residua"]) > TOLLERANZA:
        return ACCREDITO_PARZIALE
    return RICONCILIATO


def riepiloga(giornate: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Contatori per stato. Calano da soli quando la riconciliazione avanza."""
    conteggi = {stato: 0 for stato in ETICHETTE}
    for giornata in giornate:
        stato = (giornata or {}).get("stato")
        if stato in conteggi:
            conteggi[stato] += 1
    return {
        "per_stato": conteggi,
        "etichette": dict(ETICHETTE),
        "aperti": sum(conteggi[s] for s in STATI_APERTI),
        "riconciliati": conteggi[RICONCILIATO],
        "totale": sum(conteggi.values()),
    }


def circuiti_attesi(chiusure: Iterable[Dict[str, Any]],
                    circuiti_configurati: Iterable[str]) -> Dict[str, Optional[float]]:
    """Venduto per circuito, con ``None`` per quelli che non hanno risposto.

    Un circuito configurato ma senza righe non vale zero: vale "sconosciuto".
    Un circuito con una chiusura a zero, invece, vale davvero zero — e' la
    dichiarazione esplicita che quel terminale non ha incassato.
    """
    per_circuito: Dict[str, Optional[float]] = {
        normalizza_gestore_pos(c): None for c in circuiti_configurati
    }
    for riga in chiusure or []:
        if not isinstance(riga, dict):
            continue
        circuito = normalizza_gestore_pos(riga.get("gestore"))
        importo = riga.get("importo")
        if importo is None:
            importo = riga.get("totale")
        per_circuito[circuito] = round(
            (per_circuito.get(circuito) or 0.0) + _arrotonda(importo), 2)
    return per_circuito
