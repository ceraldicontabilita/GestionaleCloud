"""
SERVIZIO ARRICCHIMENTO LOTTO — calcolo centralizzato di semaforo scadenza
e valore economico (Tranche 0, HACCP features 04/07/2026).

Prima d'ora questi due dati non esistevano da nessuna parte:
  - il "semaforo" scadenza era solo un badge testuale lato frontend
    (LottiList.jsx: SCADUTO / "Scade tra Ngg"), a 2 soli livelli;
  - nessun campo di valore economico esisteva sul lotto (il modello Lotto
    non ha prezzo/costo — solo `produzioni`/`lotti_produzione` scrivono
    `costo_totale`/`costo_pezzo` in fase di produzione).

Un solo punto di calcolo qui, usato sia dalle liste (`GET /lotti`) sia
dalle future viste "Cosa usare oggi"/dashard economica, così le soglie
sono coerenti ovunque.

Soglie semaforo allineate a `SOGLIA_SCADENZA_LOTTO_GG = 2` già usata in
supervisor_operativo.py per l'alert "lotti in scadenza": sotto quella
soglia scatta quantomeno il giallo.
"""
import re
from datetime import date
from typing import Optional

from app.lotti.routers.date_utils import it_to_iso, parse_iso


def _giorni_alla_scadenza(data_scadenza: str) -> Optional[int]:
    if not data_scadenza:
        return None
    s = str(data_scadenza).strip()
    iso = s if re.match(r"^\d{4}-\d{2}-\d{2}", s) else it_to_iso(s)
    d = parse_iso(iso)
    if d is None:
        return None
    return (d - date.today()).days


def calcola_stato_scadenza(data_scadenza: str) -> dict:
    """Semaforo a 4 livelli + grigio per data mancante/illeggibile.
    Ritorna {colore, label, giorni_alla_scadenza}."""
    giorni = _giorni_alla_scadenza(data_scadenza)
    if giorni is None:
        return {"colore": "grigio", "label": "Scadenza sconosciuta", "giorni_alla_scadenza": None}
    if giorni < 0:
        return {"colore": "rosso", "label": f"Scaduto da {-giorni}gg", "giorni_alla_scadenza": giorni}
    if giorni <= 1:
        label = "Scade oggi" if giorni == 0 else "Scade domani"
        return {"colore": "arancione", "label": label, "giorni_alla_scadenza": giorni}
    if giorni <= 3:
        return {"colore": "giallo", "label": f"Scade tra {giorni}gg", "giorni_alla_scadenza": giorni}
    return {"colore": "verde", "label": f"Scade tra {giorni}gg", "giorni_alla_scadenza": giorni}


def calcola_valore_economico(lotto: dict) -> Optional[float]:
    """Valore economico residuo del lotto = costo di produzione unitario ×
    quantità residua (decisione Enzo 04/07/2026: costo di produzione, non
    prezzo di vendita — rappresenta il valore perso in caso di spreco).
    Ritorna None se il lotto non ha un costo_pezzo noto (es. lotti manuali/
    pesce, creati prima che il costo fosse tracciato): non si inventa un
    valore assente."""
    costo_pezzo = lotto.get("costo_pezzo")
    if costo_pezzo is None:
        return None
    try:
        costo_pezzo = float(costo_pezzo)
    except (TypeError, ValueError):
        return None
    quantita = lotto.get("quantita")
    try:
        quantita = float(quantita) if quantita is not None else 0.0
    except (TypeError, ValueError):
        quantita = 0.0
    return round(costo_pezzo * quantita, 2)


def arricchisci_lotto(lotto: dict) -> dict:
    """Aggiunge stato_scadenza + valore_economico a un documento lotto già
    normalizzato. Additivo: non tocca nessun campo esistente."""
    lotto["stato_scadenza"] = calcola_stato_scadenza(lotto.get("data_scadenza"))
    lotto["valore_economico"] = calcola_valore_economico(lotto)
    return lotto
