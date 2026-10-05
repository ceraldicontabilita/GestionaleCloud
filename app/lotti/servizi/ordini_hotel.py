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
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Awaitable, Callable, Iterable, Mapping
from zoneinfo import ZoneInfo

from pymongo.errors import DuplicateKeyError

from app.lotti.allergeni import normalizza_allergeni
from app.lotti.db import database as db
from app.lotti.servizi.catalogo_acquaviva_hotel import (
    digest_identita,
    identita_riga,
)


STATI_ORDINE = ("ricevuto", "confermato", "in_preparazione", "pronto", "consegnato", "annullato")
STATI_PAGAMENTO = ("da_incassare", "incassato")
METODI_PAGAMENTO = ("in_loco", "borsellino")
ORA_LIMITE_ORDINE = 14
FASCE_RITIRO = tuple(f"{h:02d}:{m:02d}" for h in range(6, 12) for m in (0, 30))
_ROMA = ZoneInfo("Europe/Rome")


def limite_ordine(data_consegna: date) -> datetime:
    """Si ordina entro le 14:00 del giorno prima della consegna (ora di Roma)."""
    return datetime.combine(data_consegna - timedelta(days=1), time(ORA_LIMITE_ORDINE), tzinfo=_ROMA)


def prima_consegna_possibile(adesso: datetime | None = None) -> date:
    adesso = (adesso or datetime.now(_ROMA)).astimezone(_ROMA)
    giorno = adesso.date() + timedelta(days=1)
    return giorno if adesso < limite_ordine(giorno) else giorno + timedelta(days=1)


def verifica_termini(data_consegna: date, ora_ritiro: str, adesso: datetime | None = None) -> None:
    adesso = (adesso or datetime.now(_ROMA)).astimezone(_ROMA)
    if ora_ritiro not in FASCE_RITIRO:
        raise ValueError("Scegli un orario di ritiro dall'elenco")
    if adesso >= limite_ordine(data_consegna):
        primo = prima_consegna_possibile(adesso)
        raise ValueError(
            f"Per ricevere i prodotti il {data_consegna.strftime('%d/%m/%Y')} si ordina entro le "
            f"{ORA_LIMITE_ORDINE}:00 del giorno prima. Prima consegna possibile: {primo.strftime('%d/%m/%Y')}")
    if data_consegna > adesso.date() + timedelta(days=30):
        raise ValueError("La consegna deve essere entro i prossimi 30 giorni")
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
    catalogo = await db.acquaviva_prodotti.find(
        {"fonte": {"$in": ["acquaviva", "vandemoortele"]}, "attivo": {"$ne": False}},
        {
            "_id": 0,
            "id": 1,
            "nome": 1,
            "nome_display": 1,
            "nome_verificato": 1,
            "descrizione": 1,
            "descrizione_lunga": 1,
            "codice": 1,
            "codice_articolo": 1,
            "codice_aqv_2025": 1,
            "codice_aqv_2026": 1,
            "codici_alias": 1,
            "alias_fattura": 1,
        },
    ).to_list(5000)
    for fattura in fatture:
        for riga in fattura.get("prodotti") or []:
            descrizione = riga.get("descrizione") or riga.get("description") or riga.get("nome")
            identita, _prodotto = identita_riga(str(descrizione or ""), riga, catalogo)
            digest_canonico = digest_identita(identita)
            digest_storico = _digest_vdm(descrizione)
            digest_trovati = {digest_canonico, digest_storico} & attese
            if not digest_trovati:
                continue
            riferimento = {
                "fattura_id": str(fattura.get("id") or ""),
                "numero_fattura": str(fattura.get("numero_fattura") or ""),
                "data_fattura": str(fattura.get("data_fattura") or ""),
                "fornitore": str(fattura.get("fornitore") or fattura.get("fornitore_ragione_sociale") or "Vandemoortele"),
                "descrizione_riga": str(descrizione or ""),
                "codice_articolo": str(riga.get("codice_articolo") or riga.get("codice") or ""),
            }
            for digest in digest_trovati:
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
    elif chiave.startswith("menu:"):
        # Il listino hotel usa il Menu digitale canonico. Se il prodotto e'
        # pubblicato da una ricetta Lotti conserviamo il confine forte del
        # lotto di produzione; per gli altri prodotti non inventiamo la fonte.
        lotti_ref = str(catalogo.get("lotti_ref") or "")
        ricetta_id = lotti_ref.split(":", 1)[1] if lotti_ref.startswith("ricetta:") else ""
        ricetta = await db.ricette.find_one({"id": ricetta_id}, {"_id": 0}) if ricetta_id else None
        riga.update({
            "menu_prodotto_id": chiave.split(":", 1)[1],
            "ricetta_id": ricetta_id or None,
            "reparto": str((ricetta or {}).get("reparto") or ""),
            "allergeni": normalizza_allergeni([*allergeni, *((ricetta or {}).get("allergeni") or [])]),
            "tracciabilita_tipo": "lotto_produzione" if ricetta_id else "da_classificare",
            "tracciabilita_stato": "produzione_da_registrare" if ricetta_id else "origine_da_verificare",
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
                       nota: str = "", idempotenza: str = "", ora_ritiro: str = "",
                       pagamento_metodo: str = "in_loco",
                       addebita: Callable[[str, Decimal], Awaitable[None]] | None = None,
                       storna: Callable[[str, Decimal], Awaitable[None]] | None = None) -> dict[str, Any]:
    if pagamento_metodo not in METODI_PAGAMENTO:
        raise ValueError("Metodo di pagamento non valido")
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
    ordine_id = "OH-" + uuid.uuid4().hex[:12].upper()
    totale = sum((_money(x["totale"]) for x in dettagli), Decimal("0"))
    con_borsellino = pagamento_metodo == "borsellino"
    if con_borsellino:
        if addebita is None:
            raise ValueError("Pagamento dal borsellino non disponibile")
        await addebita(ordine_id, totale)
    documento = {
        "_id": f"ordine_hotel:{struttura_id}:{idempotenza}" if idempotenza else f"ordine_hotel:{uuid.uuid4().hex}",
        "id": ordine_id,
        "idempotenza": idempotenza or uuid.uuid4().hex,
        "struttura_id": struttura_id,
        "struttura_nome": struttura_nome,
        "data_consegna": data_consegna,
        "ora_ritiro": ora_ritiro,
        "pagamento_metodo": pagamento_metodo,
        "nota": nota.strip()[:500],
        "righe": dettagli,
        "totale": float(totale),
        "stato": "ricevuto",
        "pagamento": "incassato" if con_borsellino else "da_incassare",
        "origine": "convenzioni_hotel",
        "creato_il": ora,
        "aggiornato_il": ora,
        "audit": [{"quando": ora, "azione": "ordine_ricevuto", "da": "albergatore",
                   "pagamento_metodo": pagamento_metodo, "ora_ritiro": ora_ritiro}],
    }
    try:
        await db.ordini_hotel.insert_one(documento.copy())
    except DuplicateKeyError:
        if con_borsellino and storna:
            await storna(ordine_id, totale)
        esistente = await db.ordini_hotel.find_one(
            {"struttura_id": struttura_id, "idempotenza": idempotenza}, {"_id": 0})
        if esistente:
            return esistente
        raise
    except Exception:
        if con_borsellino and storna:
            await storna(ordine_id, totale)
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
