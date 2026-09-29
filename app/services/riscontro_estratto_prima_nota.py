"""Righe di Prima Nota Banca riscontrate sull'estratto conto ufficiale.

Titolare, 28/09/2026: stipendi, PayPal e assegni scritti in Prima Nota da un
movimento bancario si dicono **riconciliati** quando quel movimento sta
nell'estratto conto ufficiale della banca. La proiezione li scriveva sempre
con ``riconciliato: False``: 139 stipendi del 2026 con l'estratto in mano
risultavano ancora da riconciliare.

Se l'identificativo collegato non esiste piu' (il movimento e' stato
rigenerato da una nuova lettura dell'estratto) la riga si riscontra sul
movimento ufficiale dello STESSO giorno e dello stesso importo al centesimo,
purche' non sia gia' il riscontro di un'altra riga.

La prova e' una sola: il movimento collegato alla riga (``estratto_conto_id``
e sinonimi) esiste, non e' in quarantena, ha l'evidenza ufficiale (il PDF
della banca, non l'export CSV che resta ``in_attesa_estratto_ufficiale``) e
coincide con la riga per giorno e importo al centesimo. Il movimento non si
tocca: il suo ``riconciliato`` dice che e' agganciato al documento (busta,
fattura, assegno), e segnarlo qui toglierebbe il bonifico al motore degli
stipendi.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

#: Le sole categorie che il titolare ha chiesto di chiudere cosi'.
CATEGORIE = ("Stipendi", "Pagamento PayPal", "Assegni")

_CAMPI_LEGAME = ("estratto_conto_id", "movimento_bancario_id", "movimento_estratto_conto_id")


def _cents(valore: Any) -> int:
    try:
        return int(round(abs(float(valore or 0)) * 100))
    except (TypeError, ValueError):
        return -1


def evidenza_ufficiale(movimento: Dict[str, Any]) -> bool:
    """Il movimento viene dall'estratto della banca, non da un export."""
    if movimento.get("in_attesa_estratto_ufficiale") is True:
        return False
    if movimento.get("evidenza_bancaria_ufficiale") is True:
        return True
    # I movimenti storici senza metadato sono fonti ufficiali legacy
    # (``bank_evidence.filtro_solo_evidenza_ufficiale``).
    return "livello_evidenza" not in movimento or movimento.get("livello_evidenza") == "ufficiale"


def _escluso(movimento: Dict[str, Any]) -> bool:
    return (
        str(movimento.get("status") or "") in {"deleted", "archived"}
        or movimento.get("ignorata") is True
        or movimento.get("in_quarantena") is True
    )


async def _ufficiali_per_giorno(db, righe: List[Dict[str, Any]]) -> Dict[tuple, List[Dict[str, Any]]]:
    """Movimenti ufficiali attivi non ancora usati come riscontro, per (giorno, centesimi)."""
    giorni = sorted({str(r.get("data") or "")[:10] for r in righe if r.get("data")})
    if not giorni:
        return {}
    gia_usati = {
        str((r.get("riscontro_estratto") or {}).get("movimento_id"))
        for r in await db["prima_nota_banca"].find(
            {"riscontro_estratto.movimento_id": {"$exists": True}},
            {"_id": 0, "riscontro_estratto": 1}).to_list(50000)
    }
    docs = await db["estratto_conto_movimenti"].find(
        {"data": {"$gte": giorni[0], "$lte": giorni[-1] + "~"}},
        {"_id": 0, "id": 1, "data": 1, "importo": 1, "status": 1, "ignorata": 1,
         "in_quarantena": 1, "in_attesa_estratto_ufficiale": 1,
         "evidenza_bancaria_ufficiale": 1, "livello_evidenza": 1,
         "source_filename_ufficiale": 1, "source_filename": 1}).to_list(50000)
    richiesti = set(giorni)
    out: Dict[tuple, List[Dict[str, Any]]] = {}
    for m in sorted(docs, key=lambda x: str(x.get("id"))):
        giorno = str(m.get("data") or "")[:10]
        if (giorno not in richiesti or str(m.get("id")) in gia_usati
                or _escluso(m) or not evidenza_ufficiale(m)):
            continue
        out.setdefault((giorno, _cents(m.get("importo"))), []).append(m)
    return out


async def segna_righe_riscontrate(db) -> Dict[str, Any]:
    """Idempotente: una riga gia' riconciliata non si riscrive."""
    from app.services.scritture_contabili import FILTRO_MOVIMENTO_ATTIVO

    esito: Dict[str, Any] = {"esaminate": 0, "riconciliate": 0, "senza_estratto_ufficiale": 0,
                             "non_coincidenti": 0, "per_categoria": {}}
    righe: List[Dict[str, Any]] = await db["prima_nota_banca"].find(
        {"$and": [dict(FILTRO_MOVIMENTO_ATTIVO),
                  {"categoria": {"$in": list(CATEGORIE)}},
                  {"riconciliato": {"$ne": True}}]},
        {"_id": 0, "id": 1, "data": 1, "importo": 1, "categoria": 1, **{c: 1 for c in _CAMPI_LEGAME}},
    ).to_list(20000)
    legami = {r["id"]: next((str(r[c]) for c in _CAMPI_LEGAME if r.get(c)), None) for r in righe}
    ids = sorted({m for m in legami.values() if m})
    movimenti: Dict[str, Dict[str, Any]] = {}
    for i in range(0, len(ids), 500):
        for m in await db["estratto_conto_movimenti"].find(
                {"id": {"$in": ids[i:i + 500]}},
                {"_id": 0, "id": 1, "data": 1, "importo": 1, "status": 1, "ignorata": 1,
                 "in_quarantena": 1, "in_attesa_estratto_ufficiale": 1,
                 "evidenza_bancaria_ufficiale": 1, "livello_evidenza": 1,
                 "source_filename_ufficiale": 1, "source_filename": 1}).to_list(500):
            movimenti[str(m["id"])] = m

    orfane = [r for r in righe if not movimenti.get(legami.get(r["id"]) or "")]
    per_giorno = await _ufficiali_per_giorno(db, orfane) if orfane else {}

    ora = datetime.now(timezone.utc).isoformat()
    for riga in righe:
        movimento = movimenti.get(legami.get(riga["id"]) or "")
        if not movimento:
            chiave = (str(riga.get("data") or "")[:10], _cents(riga.get("importo")))
            libero = per_giorno.get(chiave) or []
            if not libero:
                continue
            movimento = libero.pop(0)
            esito["per_giorno_importo"] = esito.get("per_giorno_importo", 0) + 1
        esito["esaminate"] += 1
        if _escluso(movimento) or not evidenza_ufficiale(movimento):
            esito["senza_estratto_ufficiale"] += 1
            continue
        if (str(riga.get("data") or "")[:10] != str(movimento.get("data") or "")[:10]
                or _cents(riga.get("importo")) != _cents(movimento.get("importo"))):
            esito["non_coincidenti"] += 1
            continue
        await db["prima_nota_banca"].update_one({"id": riga["id"]}, {"$set": {
            "riconciliato": True,
            "stato_riconciliazione": "riconciliato",
            "in_attesa_estratto_ufficiale": False,
            "riscontro_estratto": {
                "movimento_id": movimento["id"],
                "file": movimento.get("source_filename_ufficiale") or movimento.get("source_filename"),
                "il": ora,
            },
        }})
        esito["riconciliate"] += 1
        categoria = riga.get("categoria")
        esito["per_categoria"][categoria] = esito["per_categoria"].get(categoria, 0) + 1
    return esito
