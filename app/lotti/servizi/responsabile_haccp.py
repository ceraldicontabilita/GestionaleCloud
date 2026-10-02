"""Il responsabile HACCP e la firma della sessione amministratore.

Decisione del titolare (02/10/2026): il responsabile di tutti i frigoriferi e
congelatori e' l'amministratore, che entra nel gestionale col PIN
amministratore e firma le rilevazioni con quella sessione, senza un secondo
PIN.

Due regole, in un posto solo:

1. **Responsabile predefinito.** Un apparecchio senza responsabile assegnato
   e' del titolare. Il nome non sta nel codice: e' `responsabile_haccp` delle
   Impostazioni azienda (`app/lotti/azienda.py`, variabile `AZIENDA_RESP_HACCP`
   come default). Se nessuno l'ha scritto, l'apparecchio resta senza
   responsabile e il turno lo dice: un nome mancante non si inventa.
2. **Firma della sessione amministratore.** Una sessione nata dal Gestionale
   (`via = sessione_erp`, ruolo amministratore) firma: `firma_verificata`,
   `firma_via = sessione_admin`, nome del titolare dal token se porta la sua
   identita' HR, altrimenti dalle Impostazioni. Il token anonimo `erp:...`
   non e' una persona e un nome generico («Amministratore») non e' un nome:
   senza un nome vero la firma non e' verificata.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from app.lotti import azienda as _azienda

# Valore di `operatore_id` che dice «il titolare», qualunque sia il suo nome.
ID_TITOLARE = "titolare"

FIRMA_VIA_SESSIONE_ADMIN = "sessione_admin"

# Segnaposto che le sessioni mettono al posto di un nome: non firmano.
_NOMI_GENERICI = frozenset({"operatore", "amministratore", "admin", "titolare"})


def _nome_vero(valore: Any) -> str:
    nome = str(valore or "").strip()
    return "" if nome.lower() in _NOMI_GENERICI else nome


async def nome_responsabile_haccp() -> str:
    """Il nome scritto nelle Impostazioni azienda; vuoto se nessuno l'ha scritto."""
    azienda = await _azienda.get_azienda()
    return str(azienda.get("responsabile_haccp") or "").strip()


async def responsabile_predefinito() -> Dict[str, Any]:
    """Chi risponde di un apparecchio senza assegnazione: il titolare."""
    return {
        "operatore_id": ID_TITOLARE,
        "operatore_nome": await nome_responsabile_haccp(),
        "responsabile_predefinito": True,
    }


def responsabile_apparecchio(apparecchio: Dict[str, Any], predefinito: Dict[str, Any]) -> Dict[str, Any]:
    """Responsabile della casella: l'assegnato in HR, altrimenti il titolare.

    `predefinito` e' `responsabile_predefinito()`, letto una volta per giro.
    Un apparecchio assegnato esplicitamente al titolare (`ID_TITOLARE`) prende
    il nome corrente delle Impostazioni, non quello copiato all'assegnazione.
    """
    operatore_id = str(apparecchio.get("operatore_id") or "")
    if operatore_id and operatore_id != ID_TITOLARE:
        return {
            "operatore_id": operatore_id,
            "operatore_nome": str(apparecchio.get("operatore_nome") or ""),
            "responsabile_predefinito": False,
        }
    return {
        "operatore_id": ID_TITOLARE,
        "operatore_nome": predefinito.get("operatore_nome") or "",
        "responsabile_predefinito": operatore_id != ID_TITOLARE,
    }


def e_sessione_admin(attore: Optional[Dict[str, Any]]) -> bool:
    return bool(
        attore
        and attore.get("ruolo") == "amministratore"
        and attore.get("via") == "sessione_erp"
    )


async def firma_sessione_admin(attore: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Firma del titolare dalla sessione del Gestionale, o None se non c'e' un nome vero."""
    identificativo = str(attore.get("id") or "")
    identita_hr = bool(identificativo) and not identificativo.startswith("erp:")
    nome_token = _nome_vero(attore.get("nome"))
    nome = nome_token if (identita_hr and nome_token) else (await nome_responsabile_haccp() or nome_token)
    if not nome:
        return None
    return {
        "operatore": nome,
        "dipendente_id": identificativo if identita_hr else "",
        "firma_verificata": True,
        "firma_via": FIRMA_VIA_SESSIONE_ADMIN,
    }
