"""Lettura delle schede temperature: quali apparecchi, e nessuna scrittura.

Fino al 26/09/2026 frigoriferi e congelatori erano sempre 12, scritti nel
codice: un apparecchio numero 13 non compariva mai, uno eliminato restava in
colonna, e aprire la pagina di un anno creava (con ``insert_one`` dentro un
GET) dodici schede vuote per ciascuna, che la lista attrezzature a sua volta
ricopiava come apparecchi censiti.

Qui, per frigoriferi e congelatori insieme:

- gli apparecchi di un anno sono quelli **attivi** in ``attrezzature_config``
  più quelli che in quell'anno hanno almeno una rilevazione (un apparecchio
  dismesso a luglio resta nel registro di quell'anno, perché lì c'è la sua
  storia);
- le schede dell'anno si leggono con **una** query; a un apparecchio senza
  scheda corrisponde una scheda vuota **non salvata**. La scheda nasce solo
  alla prima registrazione.
"""
from __future__ import annotations

from typing import Callable, Iterable

from app.lotti.db import database as db

CONFIG = {
    "frigo": {"collezione": "temperature_positive", "campo": "frigorifero_numero"},
    "congelatore": {"collezione": "temperature_negative", "campo": "congelatore_numero"},
}


def ha_rilevazioni(scheda: dict) -> bool:
    for giorni in (scheda.get("temperature") or {}).values():
        if isinstance(giorni, dict) and giorni:
            return True
    return False


async def apparecchi_attivi(tipo: str) -> list[dict]:
    """Apparecchi censiti e attivi, per numero (fuori servizio compresi: la
    casella resta, marcata; solo un apparecchio eliminato sparisce)."""
    return (
        await db.attrezzature_config.find({"tipo": tipo, "attivo": {"$ne": False}}, {"_id": 0})
        .sort("numero", 1)
        .to_list(None)
    )


async def schede_anno(tipo: str, anno: int, nuova: Callable[[int, int], dict]) -> list[dict]:
    """Le schede dell'anno per gli apparecchi di quell'anno, in una query sola."""
    cfg = CONFIG[tipo]
    campo = cfg["campo"]
    esistenti = await db[cfg["collezione"]].find({"anno": anno}, {"_id": 0}).to_list(None)
    per_numero = {int(s[campo]): s for s in esistenti if s.get(campo) is not None}
    attivi = {int(a["numero"]): a for a in await apparecchi_attivi(tipo) if a.get("numero") is not None}
    numeri = set(attivi) | {n for n, s in per_numero.items() if ha_rilevazioni(s)}
    schede = []
    for n in sorted(numeri):
        scheda = per_numero.get(n) or nuova(anno, n)
        scheda = dict(scheda)
        scheda["attivo"] = n in attivi
        if n in attivi and attivi[n].get("fuori_servizio"):
            scheda["fuori_servizio"] = True
        schede.append(scheda)
    return schede


def numeri(schede: Iterable[dict], tipo: str) -> list[int]:
    return [int(s[CONFIG[tipo]["campo"]]) for s in schede]
