"""Catene di controllo POS, indipendenti fra loro.

Regola fondativa (utente 07/08/2026): **l'XML RT non riparte i pagamenti
elettronici.** E' la fonte fiscale del corrispettivo e non sa quanta parte sia
passata da Numia e quanta da SumUp. La formula ``elettronico XML = Nexi +
SumUp`` e' vietata: il POS si ricostruisce solo dai terminali reali.

Le fonti sono quattro e restano separate:

1. **XML RT** — quanto e' stato trasmesso fiscalmente;
2. **chiusura di cassa** — quanto la cassa ha registrato operativamente;
3. **POS reali** — chiusure dei terminali, API ufficiali, statement dei
   provider. Mai l'XML come ripiego;
4. **fonti finanziarie** — accrediti Numia su BPM, payout SumUp sulla
   Mastercard, con commissioni e rimborsi distinti.

Da qui tre controlli che NON si compensano a vicenda:

- **fiscale**: chiusura cassa contro XML RT. Segnala e basta: nessuna delle
  due fonti viene mai corretta in automatico;
- **cassa**: contante atteso = chiusura cassa meno i POS reali. Se un
  terminale non ha risposto il contante e' *non determinabile*, non si stima
  con l'XML;
- **accrediti**: per circuito, il credito contro quanto e' stato versato.

Una giornata non e' "quadrata" perche' due numeri coincidono: ogni catena ha
uno stato suo.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from app.services.scritture_contabili import normalizza_gestore_pos

TOLLERANZA = 0.01

# --- Stati della catena fiscale (cassa contro XML) --------------------------
FISCALE_ATTENDE_XML = "attende_xml"
FISCALE_ATTENDE_CASSA = "attende_chiusura_cassa"
FISCALE_DIFFORME = "cassa_xml_difforme"
FISCALE_OK = "cassa_xml_allineati"

# --- Stati della catena di cassa (contante) ---------------------------------
CASSA_ATTENDE_POS = "attende_pos_reale"
CASSA_PROVVISORIO = "contante_provvisorio"
CASSA_OK = "contante_determinato"

# --- Stati della catena di accredito, per circuito --------------------------
ACCREDITO_ATTESA = "in_attesa_di_accredito"
ACCREDITO_PARZIALE = "accredito_parziale"
COMMISSIONI_DA_VERIFICARE = "commissioni_da_verificare"
ACCREDITO_OK = "accreditato"

ETICHETTE = {
    FISCALE_ATTENDE_XML: "Attende XML RT",
    FISCALE_ATTENDE_CASSA: "Attende chiusura di cassa",
    FISCALE_DIFFORME: "Cassa e XML difformi",
    FISCALE_OK: "Cassa e XML allineati",
    CASSA_ATTENDE_POS: "Attende POS reale",
    CASSA_PROVVISORIO: "Contante provvisorio",
    CASSA_OK: "Contante determinato",
    ACCREDITO_ATTESA: "In attesa di accredito",
    ACCREDITO_PARZIALE: "Accredito parziale",
    COMMISSIONI_DA_VERIFICARE: "Commissioni da verificare",
    ACCREDITO_OK: "Accreditato",
}

# Stati che rappresentano lavoro ancora aperto: sono quelli contati nei badge.
STATI_APERTI = (
    FISCALE_ATTENDE_XML, FISCALE_ATTENDE_CASSA, FISCALE_DIFFORME,
    CASSA_ATTENDE_POS, CASSA_PROVVISORIO,
    ACCREDITO_ATTESA, ACCREDITO_PARZIALE, COMMISSIONI_DA_VERIFICARE,
)


def _num(valore: Any) -> Optional[float]:
    if valore is None:
        return None
    try:
        return round(float(valore), 2)
    except (TypeError, ValueError):
        return None


def catena_fiscale(*, totale_xml: Optional[float],
                   chiusura_cassa: Optional[float]) -> Dict[str, Any]:
    """Chiusura di cassa contro XML RT. Segnala, non corregge.

    Le due fonti sono indipendenti e possono legittimamente differire. Il
    compito del controllo e' rendere visibile la differenza, mai appianarla.
    """
    xml, cassa = _num(totale_xml), _num(chiusura_cassa)
    esito: Dict[str, Any] = {
        "totale_xml": xml, "chiusura_cassa": cassa, "differenza": None,
    }
    if xml is None:
        esito["stato"] = FISCALE_ATTENDE_XML
    elif cassa is None:
        esito["stato"] = FISCALE_ATTENDE_CASSA
    else:
        esito["differenza"] = round(cassa - xml, 2)
        esito["stato"] = (FISCALE_OK if abs(esito["differenza"]) <= TOLLERANZA
                          else FISCALE_DIFFORME)
    esito["stato_etichetta"] = ETICHETTE[esito["stato"]]
    return esito


def catena_pos_reale(circuiti: Dict[str, Optional[float]]) -> Dict[str, Any]:
    """Somma dei terminali reali. Nessun confronto con l'XML.

    ``circuiti`` mappa il circuito al venduto, con ``None`` quando il dato non
    e' ancora arrivato: e' la differenza fra "SumUp ha incassato zero" e
    "SumUp non ha ancora risposto", che non vanno mai confuse.
    """
    presenti = {c: _num(v) for c, v in (circuiti or {}).items() if v is not None}
    mancanti = sorted(c for c, v in (circuiti or {}).items() if v is None)
    return {
        "per_circuito": presenti,
        "circuiti_mancanti": mancanti,
        # Con un terminale muto il totale e' parziale: dirlo esplicitamente
        # evita che venga usato come se fosse completo.
        "totale_pos_reale": round(sum(presenti.values()), 2) if presenti else None,
        "completo": bool(presenti) and not mancanti,
    }


def catena_cassa(*, chiusura_cassa: Optional[float],
                 pos: Dict[str, Any]) -> Dict[str, Any]:
    """Contante atteso = chiusura di cassa meno i POS reali.

    Se manca anche un solo terminale il contante NON si calcola con l'XML:
    resta provvisorio. Stimarlo con un dato fiscale significherebbe dichiarare
    una giacenza di cassa che nessuno ha verificato.
    """
    cassa = _num(chiusura_cassa)
    esito: Dict[str, Any] = {
        "chiusura_cassa": cassa,
        "pos_dedotto": pos.get("totale_pos_reale"),
        "contante_atteso": None,
        "determinabile": False,
    }
    if cassa is None or not pos.get("per_circuito"):
        esito["stato"] = CASSA_ATTENDE_POS
    elif not pos.get("completo"):
        # Calcolabile, ma su terminali incompleti: e' un valore di lavoro.
        esito["contante_atteso"] = round(cassa - (pos["totale_pos_reale"] or 0), 2)
        esito["stato"] = CASSA_PROVVISORIO
    else:
        esito["contante_atteso"] = round(cassa - pos["totale_pos_reale"], 2)
        esito["determinabile"] = True
        esito["stato"] = CASSA_OK
    esito["stato_etichetta"] = ETICHETTE[esito["stato"]]
    return esito


def catena_accredito(circuito: str, *, venduto: Optional[float],
                     accreditato: float = 0.0, commissioni: float = 0.0,
                     rimborsi: float = 0.0, chargeback: float = 0.0,
                     anomalia_commissioni: bool = False) -> Dict[str, Any]:
    """Quanto il circuito ha versato contro quanto deve.

    Numia accredita il LORDO su BPM (le sue commissioni arrivano dopo, con
    fattura, e seguono un ciclo separato); SumUp accredita il NETTO sulla
    Mastercard, quindi la trattenuta rientra qui nel conto.
    """
    atteso = _num(venduto)
    esito: Dict[str, Any] = {
        "circuito": normalizza_gestore_pos(circuito),
        "venduto": atteso,
        "accreditato": _num(accreditato) or 0.0,
        "commissioni": _num(commissioni) or 0.0,
        "rimborsi": _num(rimborsi) or 0.0,
        "chargeback": _num(chargeback) or 0.0,
        "residuo": None,
    }
    if atteso is None:
        esito["stato"] = ACCREDITO_ATTESA
    else:
        esito["residuo"] = round(
            atteso - esito["rimborsi"] - esito["chargeback"]
            - esito["accreditato"] - esito["commissioni"], 2)
        if anomalia_commissioni:
            esito["stato"] = COMMISSIONI_DA_VERIFICARE
        elif esito["accreditato"] <= TOLLERANZA and atteso > TOLLERANZA:
            esito["stato"] = ACCREDITO_ATTESA
        elif abs(esito["residuo"]) > TOLLERANZA:
            esito["stato"] = ACCREDITO_PARZIALE
        else:
            esito["stato"] = ACCREDITO_OK
    esito["stato_etichetta"] = ETICHETTE[esito["stato"]]
    return esito


def stato_giornata(*, totale_xml: Optional[float] = None,
                   chiusura_cassa: Optional[float] = None,
                   circuiti: Optional[Dict[str, Optional[float]]] = None,
                   accrediti: Optional[Dict[str, Dict[str, Any]]] = None,
                   ) -> Dict[str, Any]:
    """Le tre catene di una giornata, senza compensarle fra loro."""
    pos = catena_pos_reale(circuiti or {})
    fiscale = catena_fiscale(totale_xml=totale_xml, chiusura_cassa=chiusura_cassa)
    cassa = catena_cassa(chiusura_cassa=chiusura_cassa, pos=pos)

    per_circuito = []
    for circuito, venduto in sorted((circuiti or {}).items()):
        dati = (accrediti or {}).get(circuito) or {}
        per_circuito.append(catena_accredito(circuito, venduto=venduto, **dati))

    aperte = [c["stato"] for c in [fiscale, cassa] + per_circuito
              if c["stato"] in STATI_APERTI]
    return {
        "fiscale": fiscale,
        "pos_reale": pos,
        "cassa": cassa,
        "accrediti": per_circuito,
        "catene_aperte": len(aperte),
        # Chiusa solo quando OGNI catena e' a posto: non basta che due numeri
        # coincidano da qualche parte.
        "completata": not aperte,
    }


def riepiloga(giornate: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Contatori per stato, catena per catena. Calano man mano che si chiude."""
    conteggi = {stato: 0 for stato in ETICHETTE}
    aperte = complete = 0
    for giornata in giornate:
        if not giornata:
            continue
        catene = [giornata.get("fiscale"), giornata.get("cassa")]
        catene += list(giornata.get("accrediti") or [])
        for catena in catene:
            stato = (catena or {}).get("stato")
            if stato in conteggi:
                conteggi[stato] += 1
        if giornata.get("completata"):
            complete += 1
        else:
            aperte += 1
    return {
        "per_stato": conteggi,
        "etichette": dict(ETICHETTE),
        "giornate_aperte": aperte,
        "giornate_complete": complete,
    }


def circuiti_attesi(chiusure: Iterable[Dict[str, Any]],
                    circuiti_configurati: Iterable[str]) -> Dict[str, Optional[float]]:
    """Venduto per circuito, con ``None`` per quelli che non hanno risposto.

    Un circuito configurato ma senza righe non vale zero: vale "sconosciuto".
    Una chiusura a zero, invece, vale davvero zero — e' la dichiarazione
    esplicita che quel terminale non ha incassato.
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
            (per_circuito.get(circuito) or 0.0) + (_num(importo) or 0.0), 2)
    return per_circuito
