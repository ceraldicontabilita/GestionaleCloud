"""Il collegamento verbale -> fattura del noleggiatore: un solo sistema.

Il verbale porta **due** campi, ``fattura_id`` (la chiave) e ``fattura_numero``
(solo per mostrarlo), piu' la provenienza ``fattura_collegamento``. I sei campi
paralleli che si erano accumulati (``fattura_associata_*``, ``numero_fattura``)
non si scrivono piu': si **leggono** ancora (`fattura_id_del_verbale`,
`fattura_numero_del_verbale`) finche' la sistemazione una tantum
(`verbali_ricostruzione`) non li ha riportati sui campi canonici. Data, fornitore
e importo della fattura non si copiano sul verbale: si leggono dalla fattura.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

# Copie legacy del collegamento: mai scritte, lette solo come ripiego.
CAMPI_LEGACY_COLLEGAMENTO = (
    "fattura_associata_id",
    "fattura_associata_numero",
    "fattura_associata_data",
    "fattura_associata_fornitore",
    "fattura_associata_importo",
)


def fattura_id_del_verbale(verbale: Dict[str, Any]) -> Optional[str]:
    """Id della fattura collegata; il ripiego legacy vale solo se manca il canonico."""
    valore = verbale.get("fattura_id") or verbale.get("fattura_associata_id")
    return str(valore) if valore not in (None, "") else None


def fattura_numero_del_verbale(verbale: Dict[str, Any]) -> Optional[str]:
    valore = (
        verbale.get("fattura_numero")
        or verbale.get("fattura_associata_numero")
        or verbale.get("numero_fattura")
    )
    return str(valore) if valore not in (None, "") else None


def campi_collegamento(
    fattura_id: Any, fattura_numero: Any, *, regola: str, ora: Optional[str] = None,
) -> Dict[str, Any]:
    """I soli campi che un collegamento scrive sul verbale."""
    return {
        "fattura_id": str(fattura_id),
        "fattura_numero": str(fattura_numero) if fattura_numero not in (None, "") else None,
        "fattura_collegamento": {
            "regola": regola,
            "at": ora or datetime.now(timezone.utc).isoformat(),
        },
    }


def campi_da_fattura(fattura: Dict[str, Any], *, regola: str) -> Dict[str, Any]:
    """Collegamento a partire dal documento fattura (chiavi inglesi canoniche)."""
    return campi_collegamento(
        fattura.get("id") or fattura.get("_id"),
        fattura.get("invoice_number") or fattura.get("numero_fattura"),
        regola=regola,
    )


async def collega_verbale(
    db, filtro: Dict[str, Any], fattura_id: Any, fattura_numero: Any, *, regola: str,
) -> None:
    """Scrive il collegamento sul verbale, non tocca la fattura."""
    await db["verbali_noleggio"].update_one(
        filtro,
        {"$set": {
            **campi_collegamento(fattura_id, fattura_numero, regola=regola),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
