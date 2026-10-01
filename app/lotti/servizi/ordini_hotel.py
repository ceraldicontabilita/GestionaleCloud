"""Ordini mattutini degli hotel: carrello, produzione e tracciabilita.

L'ordine conserva una fotografia immutabile di prodotto, prezzo e allergeni.
Per i prodotti interni salva il riferimento alla ricetta; per Vandemoortele
salva soltanto fatture trovate con identita esatta. Un lotto reale viene
associato dopo la produzione o la scelta del lotto fornitore: non viene mai
inventato a partire dal solo nome commerciale.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable, Mapping

from pymongo.errors import DuplicateKeyError

from app.lotti.allergeni import normalizza_allergeni
from app.lotti.db import database as db


STATI_ORDINE = ("ricevuto", "confermato", "in_preparazione", "pronto", "consegnato", "annullato")
STATI_PAGAMENTO = ("da_incassare", "incassato")
_FORNITORE_VDM = re.compile(r"vand(?:e)?moo?rte?le|vandermortel", re.IGNORECASE)


def _norm(valore: Any) -> str:
    testo = unicodedata.normalize("NFKD", str(valore or ""))
    testo = "".join(c for c in testo if not unicodedata.combining(c))
    return " ".join(re.findall(r"[A-Z0-9]+", testo.upper()))


def _digest_vdm(descrizione: Any) -> str:
    return hashlib.sha256(_norm(descrizione).encode("utf-8")).hexdigest()[:24]


def _money(valore: Any) -> Decimal:
    return Decimal(str(valore or "0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _senza_mongo(documento: Mapping[str, Any] | None) -> dict[str, Any]:
    return {k: v for k, v in (documento or {}).items() if k != "_id"}


async def _fatture_vandemoortele_per_chiavi(chiavi: Iterable[str]) -> dict[str, list[dict[str, Any]]]:
    attese = {c.split(":", 1)[1] for c in chiavi if c.startswith("vandemoortele:")}
    esito: dict[str, list[dict[str, Any]]] = {x: [] for x in attese}
    if not attese:
        return esito
    fatture = await db.fatture.find(
        {"$or": [
            {"fornitore": {"$regex": "vandemoortele|vandermoortel|vandermortel", "$options": "i"}},
            {"fornitore_ragione_sociale": {"$regex": "vandemoortele|vandermoortel|vandermortel", "$options": "i"}},
        ]},
        {"_id": 0, "id": 1, "numero_fattura": 1, "data_fattura": 1,
         "fornitore": 1, "fornitore_ragione_sociale": 1, "prodotti": 1},
    ).to_list(500)
    for fattura in fatture:
        for riga in fattura.get("prodotti") or []:
            descrizione = riga.get("descrizione") or riga.get("description") or riga.get("nome")
            digest = _digest_vdm(descrizione)
            if digest not in attese:
                continue
            riferimento = {
                "fattura_id": str(fattura.get("id") or ""),
                "numero_fattura": str(fattura.get("numero_fattura") or ""),
                "data_fattura": str(fattura.get("data_fattura") or ""),
                "fornitore": str(fattura.get("fornitore") or fattura.get("fornitore_ragione_sociale") or "Vandemoortele"),
                "descrizione_riga": str(descrizione or ""),
                "codice_articolo": str(riga.get("codice_articolo") or riga.get("codice") or ""),
            }
            if riferimento not in esito[digest]:
                esito[digest].append(riferimento)
    return esito


async def _arricchisci_riga(catalogo: Mapping[str, Any], quantita: int,
                            fatture_vdm: Mapping[str, list[dict[str, Any]]]) -> dict[str, Any]:
    chiave = str(catalogo.get("chiave") or "")
    origine = str(catalogo.get("origine") or "")
    allergeni = normalizza_allergeni(catalogo.get("allergeni") or [])
    riga = {
        "chiave": chiave,
        "origine": origine,
        "nome": str(catalogo.get("nome") or ""),
        "descrizione": str(catalogo.get("descrizione") or ""),
        "immagine": catalogo.get("immagine") or None,
        "categoria": str(catalogo.get("categoria") or ""),
        "quantita": quantita,
        "prezzo_unitario": float(_money(catalogo.get("prezzo"))),
        "totale": float(_money(catalogo.get("prezzo")) * quantita),
        "allergeni": allergeni,
        "lotti_associati": [],
    }
    if chiave.startswith("interno:"):
        prodotto_id = chiave.split(":", 1)[1]
        prodotto = await db.prodotti_vendita.find_one({"id": prodotto_id}, {"_id": 0})
        ricetta_id = str((prodotto or {}).get("ricetta_id") or "")
        ricetta = await db.ricette.find_one({"id": ricetta_id}, {"_id": 0}) if ricetta_id else None
        riga.update({
            "prodotto_vendita_id": prodotto_id,
            "ricetta_id": ricetta_id or None,
            "reparto": str((ricetta or {}).get("reparto") or ""),
            "allergeni": normalizza_allergeni([*allergeni, *((ricetta or {}).get("allergeni") or [])]),
            "tracciabilita_tipo": "lotto_produzione",
            "tracciabilita_stato": "produzione_da_registrare" if ricetta_id else "ricetta_da_verificare",
        })
    else:
        digest = chiave.split(":", 1)[1] if ":" in chiave else ""
        prove = list(fatture_vdm.get(digest) or [])
        riga.update({
            "fatture_origine": prove,
            "tracciabilita_tipo": "lotto_fornitore",
            "tracciabilita_stato": "lotto_fornitore_da_associare",
            "prova_acquisto": "fattura_vandemoortele" if prove else "da_verificare",
        })
    return riga


async def crea_ordine(*, struttura_id: str, struttura_nome: str, data_consegna: str,
                       catalogo: Mapping[str, Mapping[str, Any]], righe: list[dict[str, Any]],
                       nota: str = "", idempotenza: str = "") -> dict[str, Any]:
    if idempotenza:
        esistente = await db.ordini_hotel.find_one(
            {"struttura_id": struttura_id, "idempotenza": idempotenza}, {"_id": 0})
        if esistente:
            return esistente
    chiavi = [str(x.get("chiave") or "") for x in righe]
    fatture_vdm = await _fatture_vandemoortele_per_chiavi(chiavi)
    dettagli = []
    for richiesta in righe:
        chiave = str(richiesta.get("chiave") or "")
        prodotto = catalogo.get(chiave)
        if not prodotto:
            raise ValueError(f"Prodotto non disponibile per questa struttura: {chiave}")
        quantita = int(richiesta.get("quantita") or 0)
        if quantita < 1 or quantita > 200:
            raise ValueError("Quantita prodotto non valida (1-200)")
        dettagli.append(await _arricchisci_riga(prodotto, quantita, fatture_vdm))
    if not dettagli:
        raise ValueError("Il carrello e vuoto")
    ora = datetime.now(timezone.utc).isoformat()
    documento = {
        "_id": f"ordine_hotel:{struttura_id}:{idempotenza}" if idempotenza else f"ordine_hotel:{uuid.uuid4().hex}",
        "id": "OH-" + uuid.uuid4().hex[:12].upper(),
        "idempotenza": idempotenza or uuid.uuid4().hex,
        "struttura_id": struttura_id,
        "struttura_nome": struttura_nome,
        "data_consegna": data_consegna,
        "nota": nota.strip()[:500],
        "righe": dettagli,
        "totale": float(sum((_money(x["totale"]) for x in dettagli), Decimal("0"))),
        "stato": "ricevuto",
        "pagamento": "da_incassare",
        "origine": "convenzioni_hotel",
        "creato_il": ora,
        "aggiornato_il": ora,
        "audit": [{"quando": ora, "azione": "ordine_ricevuto", "da": "albergatore"}],
    }
    try:
        await db.ordini_hotel.insert_one(documento.copy())
    except DuplicateKeyError:
        esistente = await db.ordini_hotel.find_one(
            {"struttura_id": struttura_id, "idempotenza": idempotenza}, {"_id": 0})
        if esistente:
            return esistente
        raise
    return _senza_mongo(documento)


async def lista_ordini(query: Mapping[str, Any] | None = None, limite: int = 300) -> list[dict[str, Any]]:
    return await db.ordini_hotel.find(dict(query or {}), {"_id": 0}).sort("creato_il", -1).to_list(limite)


async def aggiorna_ordine(ordine_id: str, *, stato: str | None = None,
                          pagamento: str | None = None, da: str = "titolare") -> dict[str, Any] | None:
    if stato is not None and stato not in STATI_ORDINE:
        raise ValueError("Stato ordine non valido")
    if pagamento is not None and pagamento not in STATI_PAGAMENTO:
        raise ValueError("Stato pagamento non valido")
    campi: dict[str, Any] = {"aggiornato_il": datetime.now(timezone.utc).isoformat()}
    if stato is not None:
        campi["stato"] = stato
    if pagamento is not None:
        campi["pagamento"] = pagamento
    audit = {"quando": campi["aggiornato_il"], "azione": "ordine_aggiornato", "da": da,
             "stato": stato, "pagamento": pagamento}
    await db.ordini_hotel.update_one({"id": ordine_id}, {"$set": campi, "$push": {"audit": audit}})
    return _senza_mongo(await db.ordini_hotel.find_one({"id": ordine_id}, {"_id": 0})) or None


async def associa_lotto(ordine_id: str, chiave: str, lotto_id: str, *, da: str) -> dict[str, Any]:
    ordine = await db.ordini_hotel.find_one({"id": ordine_id}, {"_id": 0})
    if not ordine:
        raise ValueError("Ordine hotel non trovato")
    righe = list(ordine.get("righe") or [])
    riga = next((x for x in righe if x.get("chiave") == chiave), None)
    if not riga:
        raise ValueError("Prodotto non presente nell'ordine")
    filtro = {"$or": [{"id": lotto_id}, {"numero_lotto": lotto_id}, {"numero": lotto_id}]}
    tipo = riga.get("tracciabilita_tipo")
    if tipo == "lotto_produzione":
        lotto = await db.lotti.find_one(filtro, {"_id": 0})
    elif tipo == "lotto_fornitore":
        lotto = await db.lotti_fornitori.find_one(filtro, {"_id": 0})
    else:
        raise ValueError("Tipo di tracciabilita del prodotto da verificare")
    if not lotto:
        origine = "di produzione" if tipo == "lotto_produzione" else "fornitore"
        raise ValueError(f"Lotto reale {origine} non trovato")
    riferimento = {
        "id": str(lotto.get("id") or ""),
        "numero_lotto": str(lotto.get("numero_lotto") or lotto.get("numero") or ""),
        "prodotto": str(lotto.get("prodotto") or lotto.get("nome_prodotto") or lotto.get("nome") or ""),
    }
    if riferimento not in riga.setdefault("lotti_associati", []):
        riga["lotti_associati"].append(riferimento)
    riga["tracciabilita_stato"] = "lotto_associato"
    ora = datetime.now(timezone.utc).isoformat()
    await db.ordini_hotel.update_one(
        {"id": ordine_id},
        {"$set": {"righe": righe, "aggiornato_il": ora},
         "$push": {"audit": {"quando": ora, "azione": "lotto_associato", "da": da,
                              "chiave": chiave, "lotto_id": lotto_id}}},
    )
    aggiornato = await db.ordini_hotel.find_one({"id": ordine_id}, {"_id": 0})
    return _senza_mongo(aggiornato)
