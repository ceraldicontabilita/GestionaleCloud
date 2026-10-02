"""Ruoli di Lotti: chi può fare cosa, in un posto solo.

Decisione del titolare (26/09/2026). Oltre all'operatore esistono:

- **responsabile HACCP** (``haccp``): registri, anomalie, dichiarazione di
  conformità, frigoriferi e congelatori; può anche smaltire un lotto;
- **caporeparto** (``caporeparto``): ricette e produzione del **proprio**
  reparto, smaltimento lotti.

Il titolare (``amministratore``) entra dal Gestionale oppure col proprio PIN
personale associato alla scheda HR e può tutto.

Il ruolo sta sulla **scheda HR** (``lotti_ruolo``, ``lotti_reparti``):
l'anagrafica HR comanda e Lotti ne tiene solo la proiezione in
``tablet_operatori``. Il backend non si fida del ruolo scritto nel token: a
ogni operazione riservata rilegge la scheda HR, così un ruolo tolto vale
subito e non allo scadere del token. Un ruolo sconosciuto o assente vale
operatore; un operatore non in carico non passa (fallisce chiuso).
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

AMMINISTRATORE = "amministratore"
OPERATORE = "operatore"
HACCP = "haccp"
CAPOREPARTO = "caporeparto"

RUOLI_LOTTI = (OPERATORE, HACCP, CAPOREPARTO)

ETICHETTE_RUOLO = {
    OPERATORE: "Operatore",
    HACCP: "Responsabile HACCP",
    CAPOREPARTO: "Caporeparto",
    AMMINISTRATORE: "Titolare",
}

# Stessi valori che ``_categorizza_reparto`` assegna alle ricette.
REPARTI = ("pasticceria", "rosticceria", "bar", "altro")

# permesso -> ruoli (oltre al titolare) che lo hanno
PERMESSI: Dict[str, frozenset] = {
    "haccp_registri": frozenset({HACCP}),
    "haccp_conformita": frozenset({HACCP}),
    "haccp_anomalie": frozenset({HACCP}),
    "frigoriferi": frozenset({HACCP}),
    "smaltimento": frozenset({HACCP, CAPOREPARTO}),
    "ricette": frozenset({CAPOREPARTO}),
    "produzione": frozenset({CAPOREPARTO}),
}

# Permessi che valgono solo sul reparto della persona (il titolare li ha su tutti).
PERMESSI_PER_REPARTO = frozenset({"ricette", "produzione"})

ETICHETTE_PERMESSO = {
    "haccp_registri": "correggere i registri HACCP",
    "haccp_conformita": "dichiarare la conformità",
    "haccp_anomalie": "gestire le anomalie",
    "frigoriferi": "gestire frigoriferi e congelatori",
    "smaltimento": "smaltire i lotti",
    "ricette": "modificare le ricette",
    "produzione": "annullare una produzione",
}


def normalizza_ruolo(valore: Any) -> str:
    ruolo = str(valore or "").strip().lower()
    return ruolo if ruolo in RUOLI_LOTTI else OPERATORE


def normalizza_reparti(valori: Optional[Iterable[Any]]) -> List[str]:
    if isinstance(valori, str):
        valori = [valori]
    visti: List[str] = []
    for v in valori or []:
        r = str(v or "").strip().lower()
        if r in REPARTI and r not in visti:
            visti.append(r)
    return visti


def permessi_di(ruolo: str) -> List[str]:
    if ruolo == AMMINISTRATORE:
        return sorted(PERMESSI)
    return sorted(p for p, ruoli in PERMESSI.items() if ruolo in ruoli)


def ha_permesso(ruolo: str, permesso: str) -> bool:
    if permesso not in PERMESSI:
        raise KeyError(f"Permesso sconosciuto: {permesso}")
    return ruolo == AMMINISTRATORE or ruolo in PERMESSI[permesso]


def reparto_ammesso(ruolo: str, reparti: Iterable[str], reparto: Any) -> bool:
    """Il titolare lavora su ogni reparto; gli altri solo sui propri. Una
    ricetta senza reparto non è di nessun caporeparto."""
    if ruolo == AMMINISTRATORE:
        return True
    r = str(reparto or "").strip().lower()
    return bool(r) and r in set(reparti or [])


def profilo_ruolo(ruolo: str, reparti: Iterable[str]) -> Dict[str, Any]:
    """Quello che il tablet riceve al login per mostrare solo ciò che si può fare."""
    return {
        "ruolo": ruolo,
        "ruolo_etichetta": ETICHETTE_RUOLO.get(ruolo, ruolo),
        "reparti": list(reparti or []),
        "permessi": permessi_di(ruolo),
    }
