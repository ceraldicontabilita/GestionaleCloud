"""Contabili di filiale BPM: la ricevuta di sportello come prova del movimento.

La «Contabile di filiale» e' il foglio che la banca stampa allo sportello
(«Vogliate prendere nota che abbiamo eseguito, sul Vostro conto corrente…»).
Quasi sempre e' un **versamento di contanti** (causale 780 CONTANTI, con
distinta e conta delle banconote), a volte un'altra operazione di sportello
(66C SPESE LIBR.AS., il libretto assegni).

Non crea niente: il movimento lo scrive l'estratto conto, il versamento lo
riconosce `versamenti_contanti`. Qui la ricevuta si **attacca** alla riga
dell'estratto che documenta, come prova distinta:

- stesso verso e importo al centesimo;
- data contabile dal giorno dell'operazione a 3 giorni dopo;
- per un versamento, la riga deve essere un versamento per
  `versamenti_contanti.classifica`; per le altre operazioni deve condividere
  una parola della causale («SPESE»). Mai il solo importo.

Una riga sola → collegata. Nessuna → `in_attesa_estratto` (il giro bancario
riprova quando l'estratto arriva). Piu' d'una → `da_verificare` coi candidati.
"""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

TIPO = "contabile_filiale"
COLL = "contabili_filiale"
GIORNI_CONTABILIZZAZIONE = 3

_OPERAZIONE = re.compile(
    r"\b(\d{2,3}[A-Z]?)\s+([A-Z][A-Z0-9 .'/\-]*?)\s+(?:EUR\s+)?"
    r"(\d{1,3}(?:\.\d{3})*,\d{2})([+-])\s+(\d{2}/\d{2}/\d{4})"
)
_DATA = re.compile(r"\b(\d{2})/(\d{2})/(\d{4})\b")
_DISTINTA = re.compile(r"DISTINTA\s+N\.?\s*(\d+)", re.I)


def riconosci(testo: str) -> bool:
    """Il foglio di sportello BPM: la formula d'apertura e la parola CONTABILE."""
    compatto = re.sub(r"\s+", " ", str(testo or "")).upper()
    return ("VOGLIATE PRENDERE NOTA CHE ABBIAMO ESEGUITO" in compatto
            and "CONTABILE" in compatto
            and "DIPENDENZA" in compatto)


def _iso(giorno: str) -> Optional[str]:
    trovato = _DATA.search(giorno or "")
    if not trovato:
        return None
    gg, mm, aaaa = trovato.groups()
    return f"{aaaa}-{mm}-{gg}"


def _importo(testo: str) -> Decimal:
    try:
        return Decimal(testo.replace(".", "").replace(",", "."))
    except InvalidOperation:
        return Decimal("0")


def leggi(testo: str) -> Dict[str, Any]:
    """Operazioni, totale con segno, data e distinta; ``{}`` se non si legge."""
    compatto = re.sub(r"\s+", " ", str(testo or "")).upper()
    operazioni = []
    for codice, descrizione, importo, segno, valuta in _OPERAZIONE.findall(compatto):
        valore = _importo(importo)
        operazioni.append({
            "codice": codice, "descrizione": descrizione.strip(),
            "importo": str(valore if segno == "+" else -valore), "valuta": _iso(valuta),
        })
    if not operazioni:
        return {}
    totale = sum((Decimal(o["importo"]) for o in operazioni), Decimal("0"))
    date = [f"{a}-{m}-{g}" for g, m, a in _DATA.findall(compatto)]
    distinta = _DISTINTA.search(compatto)
    versamento = totale > 0 and any(
        o["codice"] == "780" or "CONTANT" in o["descrizione"] for o in operazioni)
    return {
        "operazioni": operazioni,
        "importo": str(totale),
        "verso": "entrata" if totale > 0 else "uscita",
        "data_operazione": min(date) if date else operazioni[0]["valuta"],
        "distinta": distinta.group(1) if distinta else None,
        "operazione": "versamento_contanti" if versamento else "operazione_sportello",
    }


def _importo_movimento(movimento: Dict[str, Any]) -> Decimal:
    for campo in ("importo", "amount"):
        if movimento.get(campo) not in (None, ""):
            try:
                return Decimal(str(movimento[campo])).quantize(Decimal("0.01"))
            except InvalidOperation:
                return Decimal("0")
    return Decimal("0")


def _parole(testo: str) -> set:
    return {p for p in re.findall(r"[A-Z]{4,}", str(testo or "").upper())}


def _compatibile(contabile: Dict[str, Any], movimento: Dict[str, Any]) -> bool:
    from app.services.versamenti_contanti import classifica

    if _importo_movimento(movimento) != Decimal(contabile["importo"]).quantize(Decimal("0.01")):
        return False
    if contabile["operazione"] == "versamento_contanti":
        return classifica(movimento) == "versamento"
    causale = " ".join(o["descrizione"] for o in contabile["operazioni"])
    descrizione = movimento.get("descrizione_originale") or movimento.get("descrizione") or ""
    return bool(_parole(causale) & _parole(descrizione))


async def collega(db, contabile: Dict[str, Any]) -> Dict[str, Any]:
    """Cerca la riga dell'estratto che la contabile documenta e la collega."""
    giorno = contabile.get("data_operazione")
    if not giorno:
        esito = {"stato": "da_verificare", "motivo": "data non letta", "candidati": []}
    else:
        fine = (datetime.fromisoformat(giorno) + timedelta(days=GIORNI_CONTABILIZZAZIONE)).date().isoformat()
        movimenti = await db["estratto_conto_movimenti"].find(
            {"data": {"$gte": giorno, "$lte": fine + "~"}},
            {"_id": 0, "id": 1, "data": 1, "importo": 1, "amount": 1, "descrizione": 1,
             "descrizione_originale": 1, "contabile_filiale_id": 1},
        ).to_list(None)
        candidati = [m for m in movimenti if _compatibile(contabile, m)
                     and m.get("contabile_filiale_id") in (None, "", contabile["id"])]
        if len(candidati) == 1:
            movimento = candidati[0]
            await db["estratto_conto_movimenti"].update_one(
                {"id": movimento["id"]},
                {"$set": {"contabile_filiale_id": contabile["id"],
                          "contabile_filiale_drive_file_id": contabile.get("drive_file_id")}},
            )
            esito = {"stato": "collegata", "movimento_id": movimento["id"], "candidati": []}
        elif not candidati:
            esito = {"stato": "in_attesa_estratto", "candidati": []}
        else:
            esito = {"stato": "da_verificare", "motivo": "piu' righe compatibili",
                     "candidati": [m["id"] for m in candidati]}
    await db[COLL].update_one(
        {"id": contabile["id"]},
        {"$set": {**esito, "controllata_il": datetime.now(timezone.utc).isoformat()}},
    )
    return esito


async def registra(db, filename: str, content: bytes, testo: str, *,
                   drive_file_id: Optional[str] = None) -> Dict[str, Any]:
    """Archivia la contabile (una volta per impronta) e prova a collegarla."""
    impronta = hashlib.sha256(content).hexdigest()
    esistente = await db[COLL].find_one({"id": impronta}, {"_id": 0})
    if esistente:
        return {"success": True, "duplicate": True, **esistente}
    lettura = leggi(testo)
    if not lettura:
        return {"success": False, "message": "Contabile di filiale senza operazioni leggibili"}
    contabile = {
        "id": impronta, "sha256": impronta, "filename": filename,
        "drive_file_id": drive_file_id, **lettura,
        "creata_il": datetime.now(timezone.utc).isoformat(),
    }
    await db[COLL].insert_one(dict(contabile))
    esito = await collega(db, contabile)
    return {"success": True, "duplicate": False, **contabile, **esito}


async def ricollega_in_attesa(db) -> Dict[str, int]:
    """Il secondo pezzo arrivato dopo: riprova le contabili senza movimento."""
    aperte = await db[COLL].find(
        {"stato": {"$in": ["in_attesa_estratto", "da_verificare"]}}, {"_id": 0}).to_list(None)
    conteggi = {"riprovate": 0, "collegate": 0}
    for contabile in aperte:
        conteggi["riprovate"] += 1
        esito = await collega(db, contabile)
        if esito["stato"] == "collegata":
            conteggi["collegate"] += 1
    return conteggi

