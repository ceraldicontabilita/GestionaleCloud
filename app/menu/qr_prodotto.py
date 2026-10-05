"""QR del singolo prodotto: l'ID prodotto unico (PRD-000123) nell'indirizzo del Menu.

L'indirizzo pubblico del menu e' una sola fonte (`menu_qrcode_config.menu_url`, sempre
``https://<dominio>/menu/``); il QR si disegna nel browser (`qrcode.react`), qui si costruisce
solo l'indirizzo. Il prodotto si apre da ``/menu/carta/?p=<codice>``; ``canale`` apre la carta
del solo sala o delivery.
"""
import re
from typing import Optional
from urllib.parse import urlencode

CODICE_PRODOTTO_RE = re.compile(r"^PRD-\d{6,}$")
CANALI = ("sala", "delivery")


def codice_valido(codice: str) -> bool:
    return bool(CODICE_PRODOTTO_RE.match(str(codice or "")))


def url_prodotto(menu_url: Optional[str], codice: str, canale: Optional[str] = None) -> Optional[str]:
    """Indirizzo della scheda del prodotto, o ``None`` se il menu non ha ancora un indirizzo pubblico."""
    base = str(menu_url or "").strip()
    if not base or not codice_valido(codice):
        return None
    if canale not in (None, "") and canale not in CANALI:
        raise ValueError("Canale non valido")
    domanda = {"p": codice}
    if canale:
        domanda["canale"] = canale
    return f"{base.rstrip('/')}/carta/?{urlencode(domanda)}"
