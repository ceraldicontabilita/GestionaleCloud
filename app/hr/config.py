"""Configurazione del modulo HR (ex AppDipendenti) dentro GestionaleCloud.

Il modulo non ha piu' un segreto JWT proprio ne' un PIN amministratore
proprio: firma e verifica i token con lo stesso ``SECRET_KEY`` del gestionale
(``app.config.settings``) e l'accesso amministratore passa dal login unico
del gestionale (PIN + MFA). Qui restano solo le costanti specifiche del
portale dipendenti.
"""
import os

from app.config import settings as _gestionale


class Settings:
    """Vista HR sulla configurazione unica del gestionale."""

    ALGORITHM: str = _gestionale.ALGORITHM

    # Sessione del portale dipendenti (dispositivo condiviso in negozio): il
    # titolare ha chiesto esplicitamente che il PIN non venga richiesto a ogni
    # apertura. Default 7 giorni, come nell'app originale.
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
        os.environ.get("HR_PORTALE_TOKEN_EXPIRE_MINUTES", str(60 * 24 * 7))
    )

    @property
    def SECRET_KEY(self) -> str:  # noqa: N802 - nome storico usato dai chiamanti
        # Letto a ogni accesso: il gestionale puo' rigenerare una chiave
        # effimera in sviluppo e il modulo HR deve seguirla, mai divergere.
        return _gestionale.SECRET_KEY


settings = Settings()

ALGORITHM = settings.ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES

# Feature flag (usati da require_feature). Vuoto = nessuna feature gated attiva.
FEATURES: dict = {}
