"""Lotto automatico dei prodotti Acquaviva (ordini degli hotel, poi colazione del mattino).

Il lotto non si associa a mano: nome del prodotto, giorno e numero della fattura
Acquaviva in uso si uniscono in un numero di lotto, che si salva in
`lotti_fornitori` e si vede in Lotti. La fattura in uso e' la **piu' vecchia
ancora da usare** (FIFO): la scorre il titolare con «Successiva» quando la merce
di quella fattura e' finita (le quantita' delle fatture, in cartoni, non si
confrontano con i pezzi serviti: non si inventano). Finche' nessuno l'ha scelta
vale l'ultima fattura arrivata fino a quel giorno, e la pagina lo dice.
Mai per somiglianza di nome: un prodotto e' Acquaviva solo se il titolare lo ha
segnato (`menu_prodotti_fornitore`).
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from datetime import date, datetime, timezone
from typing import Any

from app.lotti.db import database as db

FORNITORE_RE = "acquaviva|vande?moo?rte?le|vandermortel"
COLL_PRODOTTI = "menu_prodotti_fornitore"
COLL_IN_USO = "acquaviva_fattura_in_uso"
ID_IN_USO = "corrente"


def data_iso(valore: Any) -> str:
    """'30/12/2025' o '2025-12-02' -> 'AAAA-MM-GG'; illeggibile -> ''."""
    testo = str(valore or "").strip()[:10]
    for formato in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(testo, formato).date().isoformat()
        except ValueError:
            continue
    return ""


def slug_prodotto(nome: Any) -> str:
    testo = unicodedata.normalize("NFKD", str(nome or ""))
    testo = "".join(c for c in testo if not unicodedata.combining(c))
    return "-".join(re.findall(r"[A-Z0-9]+", testo.upper()))[:40].strip("-") or "PRODOTTO"


def numero_lotto(nome: Any, giorno: Any, numero_fattura: Any) -> str:
    """NOME-PRODOTTO-AAAAMMGG-NUMEROFATTURA, sempre lo stesso per lo stesso trio."""
    giorno_iso = data_iso(giorno) or str(giorno or "")
    return f"{slug_prodotto(nome)}-{giorno_iso.replace('-', '')}-{str(numero_fattura or '').strip()}"


async def fatture_acquaviva() -> list[dict[str, Any]]:
    """Fatture Acquaviva/Vandemoortele dalla piu' vecchia, una per (numero, data)."""
    regex = {"$regex": FORNITORE_RE, "$options": "i"}
    elenco = await db.fatture.find(
        {"$and": [{"$or": [{"fornitore": regex}, {"fornitore_ragione_sociale": regex}]},
                  {"deleted": {"$ne": True}}]},
        {"_id": 0, "id": 1, "numero_fattura": 1, "data_fattura": 1, "fornitore": 1,
         "fornitore_ragione_sociale": 1},
    ).to_list(2000)
    viste: dict[tuple[str, str], dict[str, Any]] = {}
    for f in elenco:
        numero = str(f.get("numero_fattura") or "").strip()
        giorno = data_iso(f.get("data_fattura"))
        if not numero or not giorno:
            continue
        viste.setdefault((giorno, numero), {
            "fattura_id": str(f.get("id") or ""), "numero_fattura": numero, "data_fattura": giorno,
            "fornitore": str(f.get("fornitore") or f.get("fornitore_ragione_sociale") or "Acquaviva"),
        })
    return [viste[k] for k in sorted(viste)]


async def _scelta_salvata() -> dict[str, Any] | None:
    return await db[COLL_IN_USO].find_one({"id": ID_IN_USO}, {"_id": 0})


def _indice(fatture: list[dict[str, Any]], scelta: dict[str, Any] | None) -> int | None:
    if not scelta:
        return None
    for i, f in enumerate(fatture):
        if f["numero_fattura"] == scelta.get("numero_fattura") and f["data_fattura"] == scelta.get("data_fattura"):
            return i
    return None


async def stato_fattura_in_uso(giorno: Any = None) -> dict[str, Any]:
    """Fattura in uso con precedente e successiva; `automatica` = nessuna scelta del titolare."""
    fatture = await fatture_acquaviva()
    if not fatture:
        return {"in_uso": None, "precedente": None, "successiva": None, "automatica": True, "totale": 0}
    i = _indice(fatture, await _scelta_salvata())
    automatica = i is None
    if automatica:
        limite = data_iso(giorno) or date.today().isoformat()
        fino_al_giorno = [k for k, f in enumerate(fatture) if f["data_fattura"] <= limite]
        i = fino_al_giorno[-1] if fino_al_giorno else len(fatture) - 1
    return {
        "in_uso": fatture[i],
        "precedente": fatture[i - 1] if i > 0 else None,
        "successiva": fatture[i + 1] if i + 1 < len(fatture) else None,
        "automatica": automatica,
        "totale": len(fatture),
    }


async def sposta_fattura_in_uso(azione: str, *, da: str = "titolare") -> dict[str, Any]:
    """«successiva» (la merce della fattura in uso e' finita) o «precedente» (correzione)."""
    if azione not in ("successiva", "precedente"):
        raise ValueError("Azione non valida")
    stato = await stato_fattura_in_uso()
    nuova = stato.get(azione)
    if not nuova:
        raise ValueError("Non ci sono altre fatture in quella direzione")
    await db[COLL_IN_USO].update_one(
        {"id": ID_IN_USO},
        {"$set": {"id": ID_IN_USO, "numero_fattura": nuova["numero_fattura"],
                  "data_fattura": nuova["data_fattura"], "aggiornato_il": datetime.now(timezone.utc).isoformat(),
                  "da": da}},
        upsert=True,
    )
    return await stato_fattura_in_uso()


async def prodotti_acquaviva() -> set[str]:
    docs = await db[COLL_PRODOTTI].find({"fornitore": "acquaviva"}, {"_id": 0, "prodotto_id": 1}).to_list(5000)
    return {str(d.get("prodotto_id")) for d in docs}


async def imposta_prodotto_acquaviva(prodotto_id: int, attivo: bool, *, da: str = "titolare") -> None:
    chiave = f"menu:{int(prodotto_id)}"
    await db[COLL_PRODOTTI].update_one(
        {"id": chiave},
        {"$set": {"id": chiave, "prodotto_id": str(int(prodotto_id)),
                  "fornitore": "acquaviva" if attivo else "", "aggiornato_il": datetime.now(timezone.utc).isoformat(),
                  "da": da}},
        upsert=True,
    )


async def nome_fattura_prodotto(prodotto_id: Any, ripiego: str = "") -> str:
    """Nome del prodotto come sta nelle fatture Acquaviva: e' il nome del LOTTO (uso interno).

    Ai clienti il Menu mostra il nome semplice; il nome di fattura sta solo qui, accanto al segno
    «Fornitore: Acquaviva». Senza nome di fattura vale il nome del Menu."""
    doc = await db[COLL_PRODOTTI].find_one({"id": f"menu:{prodotto_id}"}, {"_id": 0, "nome_fattura": 1})
    return str((doc or {}).get("nome_fattura") or "").strip() or str(ripiego or "")


async def imposta_nome_fattura(prodotto_id: int, nome: str, *, da: str = "titolare") -> None:
    chiave = f"menu:{int(prodotto_id)}"
    await db[COLL_PRODOTTI].update_one(
        {"id": chiave},
        {"$set": {"id": chiave, "prodotto_id": str(int(prodotto_id)), "nome_fattura": str(nome or "").strip(),
                  "aggiornato_il": datetime.now(timezone.utc).isoformat(), "da": da}},
        upsert=True,
    )


async def e_prodotto_acquaviva(prodotto_id: Any) -> bool:
    doc = await db[COLL_PRODOTTI].find_one({"id": f"menu:{prodotto_id}"}, {"_id": 0, "fornitore": 1})
    return bool(doc and doc.get("fornitore") == "acquaviva")


async def lotto_per_prodotto(nome: str, giorno: Any) -> dict[str, Any] | None:
    """Crea (o ritrova) il lotto di quel prodotto per quel giorno con la fattura in uso.

    Idempotente: lo stesso prodotto nello stesso giorno con la stessa fattura e' un lotto solo.
    Ritorna None se non c'e' nessuna fattura Acquaviva: il lotto non si inventa.
    """
    stato = await stato_fattura_in_uso(giorno)
    fattura = stato["in_uso"]
    if not fattura:
        return None
    numero = numero_lotto(nome, giorno, fattura["numero_fattura"])
    lotto = await db.lotti_fornitori.find_one({"numero_lotto": numero}, {"_id": 0})
    if not lotto:
        lotto = {
            "id": str(uuid.uuid4()),
            "fornitore": fattura["fornitore"],
            "prodotto_nome": nome,
            "prodotto_nome_norm": str(nome).lower(),
            "numero_lotto": numero,
            "lotto_id_fornitore": numero,
            "fattura_ref": fattura["numero_fattura"],
            "data_fattura": date.fromisoformat(fattura["data_fattura"]).strftime("%d/%m/%Y"),
            "data_giorno": data_iso(giorno),
            "origine": "automatico_acquaviva",
            "fattura_scelta_automatica": stato["automatica"],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.lotti_fornitori.insert_one(dict(lotto))
    return {"lotto": lotto, "fattura": fattura, "automatica": stato["automatica"]}
