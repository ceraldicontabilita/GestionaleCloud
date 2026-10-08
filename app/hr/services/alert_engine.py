"""Motore alert — re-export del modulo unico.

La logica vive in `app/services/alert_engine.py`. Fino al 19/09/2026 qui c'era
una copia con un **catalogo diverso**, e questo e' il punto: `genera_alert`
non solleva su un codice fuori catalogo, scrive una riga di log e torna
`None`. Un alert emesso col codice sbagliato **sparisce in silenzio**.

I due cataloghi divergevano in entrambe le direzioni: 60 codici in comune, 15
solo sul lato ERP, 5 solo qui (`CED_CONTESTATA`, `DIP_DIMISSIONI_RICEVUTE`,
`DIP_CONTRATTO_IN_SCADENZA`, `DIP_PERIODO_PROVA_IN_SCADENZA`,
`MAG_SOTTO_SCORTA`). I cinque sono stati portati sul catalogo unico prima di
cancellare questa copia, quindi nessuna definizione e' andata persa.

Si vedeva anche da fuori: `app/services/dimissioni_adempimenti.py`, che e'
codice dell'ERP, importava `genera_alert` **da qui** — non per scelta di
architettura, ma perche' `DIP_DIMISSIONI_RICEVUTE` esisteva solo in questo
catalogo. Ora quell'import punta al modulo unico.

`tests/hr/test_alert_catalogo_unico.py` impedisce che il buco si riapra:
ogni codice citato in `app/` deve esistere nel catalogo.
"""
from app.services.alert_engine import (  # noqa: F401
    ALERT_CATALOG,
    COLL_ALERT_DEFINITIONS,
    COLL_ALERTS,
    conta_alert_per_modulo,
    genera_alert,
    ignora_alert,
    risolvi_alert,
    risolvi_alert_multi,
    seed_alert_definitions,
    verifica_alert_aperti,
)

__all__ = [
    "ALERT_CATALOG",
    "COLL_ALERTS",
    "COLL_ALERT_DEFINITIONS",
    "conta_alert_per_modulo",
    "genera_alert",
    "ignora_alert",
    "risolvi_alert",
    "risolvi_alert_multi",
    "seed_alert_definitions",
    "verifica_alert_aperti",
]
