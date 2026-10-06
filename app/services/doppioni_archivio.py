"""Doppioni d'archivio: lo stesso documento entrato più volte, spostato fra i «da eliminare».

Decisione del titolare (26/09/2026): «i doppioni devono essere eliminati:
spostali in una cartella da eliminare», per cedolini, F24, quietanze e
bonifici. La «cartella» di un archivio è la sua collezione
``<collezione>_quarantena`` (lo stesso schema di
``estratto_conto_movimenti_quarantena``): la copia ci va intera, con
``duplicato_di`` e il motivo, e sparisce dall'archivio vivo. Da lì si recupera
o si elimina per davvero; qui nulla si cancella senza lasciarne copia.

Un doppione è **lo stesso contenuto**, mai lo stesso nome o lo stesso importo
da soli:

- cedolino: dipendente, anno, mese, tipo, netto, lordo e trattenute al
  centesimo (la stessa busta dal file singolo, dal Libro Unico, da una
  «Variante 1»). Arretrati e conguagli hanno tipo o importi diversi e restano;
- quietanza F24: il protocollo telematico dell'Agenzia, altrimenti
  contribuente, data, saldo e codici tributo;
- bonifico: il CRO/TRN della banca con l'importo, altrimenti data, importo,
  beneficiario e causale;
- F24: il modello già in quarantena da ``f24_doppioni`` (stesso contenuto
  fiscale) passa nella sua cartella.

Resta la copia che porta pagamenti, abbinamenti o collegamenti; a parità la
prima arrivata. Chi puntava a una copia (``cedolino_id`` in Prima Nota
salari, ``quietanza_id`` negli F24) viene ricollegato a quella che resta prima
dello spostamento. La Prima Nota salari la bonifica il suo motore
(``bonifica_prima_nota_salari_doppioni``), che sposta anche i bonifici
agganciati; qui le righe che ha marcato passano nella cartella.
"""
from __future__ import annotations

import asyncio
import logging
import re
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)

SUFFISSO = "_quarantena"
MOTIVO = "doppione"


def _ora() -> str:
    return datetime.now(timezone.utc).isoformat()


def centesimi(valore: Any) -> Optional[int]:
    if valore is None or valore == "":
        return None
    try:
        return int((Decimal(str(valore)) * 100).quantize(Decimal("1")))
    except (InvalidOperation, ValueError):
        return None


def _testo(valore: Any) -> str:
    return re.sub(r"\s+", " ", str(valore or "")).strip().upper()


# ── identità ────────────────────────────────────────────────────────────────

def identita_cedolino(doc: Dict[str, Any]) -> Optional[Tuple]:
    netto = centesimi(doc.get("netto_mese", doc.get("netto")))
    cf = _testo(doc.get("codice_fiscale"))
    if not cf or netto is None or not doc.get("anno") or not doc.get("mese"):
        return None
    tipo = _testo(doc.get("tipo_cedolino") or "mensile").lower()
    return (cf, int(doc["anno"]), int(doc["mese"]), tipo, netto,
            centesimi(doc.get("lordo")), centesimi(doc.get("totale_trattenute")))


def identita_quietanza(doc: Dict[str, Any]) -> Optional[Tuple]:
    """Stesso protocollo **e** stesso saldo: dallo stesso PDF escono deleghe
    diverse col protocollo uguale (il ravvedimento pagato lo stesso giorno,
    2.946,31 e 22,47 EUR il 04/11/2022), e sono due pagamenti."""
    protocollo = _testo(doc.get("protocollo_telematico"))
    saldo = centesimi(doc.get("saldo"))
    if protocollo:
        return ("protocollo", protocollo, saldo)
    cf = _testo(doc.get("codice_fiscale"))
    data = str(doc.get("data_pagamento") or "")[:10]
    codici = tuple(sorted(str(c) for c in doc.get("codici_tributo") or []))
    if not (cf and data and saldo is not None and codici):
        return None
    return ("contenuto", cf, data, saldo, codici)


def identita_bonifico(doc: Dict[str, Any]) -> Optional[Tuple]:
    cro = _testo(doc.get("cro_trn"))
    importo = centesimi(doc.get("importo"))
    if cro and importo is not None:
        # Il CRO con l'importo: una distinta con un CRO solo e piu' importi resta intera.
        return ("cro", cro, importo)
    data = str(doc.get("data") or "")[:10]
    beneficiario = doc.get("beneficiario")
    nome = _testo(beneficiario.get("nome") if isinstance(beneficiario, dict) else beneficiario)
    if not (data and importo is not None and nome):
        return None
    return ("contenuto", data, importo, nome, _testo(doc.get("causale")))


# ── quale copia resta ───────────────────────────────────────────────────────

def _punteggio_cedolino(doc: Dict[str, Any]) -> Tuple:
    pagato = bool(doc.get("pagato") or (doc.get("importo_pagato") or 0) > 0 or doc.get("pagamenti")
                  or doc.get("riconciliato") or doc.get("riconciliato_auto"))
    return (0 if pagato else 1, 0 if (doc.get("drive_file_id") or doc.get("pdf_disponibile")) else 1,
            0 if doc.get("voci") else 1, str(doc.get("created_at") or ""))


def _punteggio_quietanza(doc: Dict[str, Any]) -> Tuple:
    associata = bool(doc.get("f24_associati")) or str(doc.get("stato_associazione") or "").lower() not in (
        "", "non_associata", "da_associare")
    return (0 if associata else 1, 0 if doc.get("drive_file_id") else 1, str(doc.get("created_at") or ""))


def _punteggio_bonifico(doc: Dict[str, Any]) -> Tuple:
    legato = bool(doc.get("riconciliato") or doc.get("associato") or doc.get("movimento_id")
                  or doc.get("fattura_id") or doc.get("cedolino_id") or doc.get("hr_deposito"))
    beneficiario = doc.get("beneficiario")
    nome = _testo(beneficiario.get("nome") if isinstance(beneficiario, dict) else beneficiario)
    # «RICEVUTA PER ORDINANTE» e' l'intestazione della ricevuta letta come beneficiario.
    letto_bene = bool(nome) and "RICEVUTA PER ORDINANTE" not in nome
    return (0 if legato else 1, 0 if letto_bene else 1, 0 if doc.get("parser_completo") else 1,
            str(doc.get("created_at") or ""))


def gruppi_doppioni(docs: Iterable[Dict[str, Any]], identita: Callable, punteggio: Callable
                    ) -> List[Tuple[Dict[str, Any], List[Dict[str, Any]]]]:
    """(copia che resta, copie da spostare) per ogni contenuto presente più volte."""
    per_chiave: Dict[Tuple, List[Dict[str, Any]]] = defaultdict(list)
    for doc in docs:
        chiave = identita(doc)
        if chiave is not None and doc.get("id"):
            per_chiave[chiave].append(doc)
    gruppi = []
    for copie in per_chiave.values():
        if len(copie) > 1:
            ordinate = sorted(copie, key=punteggio)
            gruppi.append((ordinate[0], ordinate[1:]))
    return gruppi


# ── spostamento ─────────────────────────────────────────────────────────────

async def sposta_nella_cartella(db, collezione: str, copia: Dict[str, Any], originale_id: Optional[str],
                                *, motivo: str = MOTIVO, actor: str = "sistema") -> None:
    """La copia intera va in ``<collezione>_quarantena`` e lascia l'archivio vivo (per id)."""
    await db[collezione + SUFFISSO].update_one(
        {"id": copia["id"]},
        {"$set": {**copia, "duplicato_di": originale_id, "motivo_quarantena": motivo,
                  "quarantena_at": _ora(), "quarantena_da": actor}},
        upsert=True,
    )
    await db[collezione].delete_one({"id": copia["id"]})


async def _ricollega(db, collezione: str, campo: str, da: str, a: str) -> int:
    righe = await db[collezione].find({campo: da}, {"_id": 0, "id": 1}).to_list(None)
    for riga in righe:
        await db[collezione].update_one({"id": riga["id"]}, {"$set": {campo: a}})
    return len(righe)


async def _tratta(db, collezione: str, identita: Callable, punteggio: Callable, *, dry_run: bool,
                  actor: str, riferimenti: Tuple[Tuple[str, str], ...] = (),
                  proiezione: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
    docs = await db[collezione].find({}, proiezione or {"_id": 0, "pdf_data": 0}).to_list(None)
    gruppi = gruppi_doppioni(docs, identita, punteggio)
    esito: Dict[str, Any] = {"collezione": collezione, "gruppi": len(gruppi),
                             "copie": sum(len(c) for _, c in gruppi), "ricollegati": 0,
                             "esempi": [{"resta": r.get("id"), "copie": [c.get("id") for c in cc]}
                                        for r, cc in gruppi[:20]]}
    if dry_run:
        return esito
    for resta, copie in gruppi:
        for copia in copie:
            for coll_rif, campo in riferimenti:
                esito["ricollegati"] += await _ricollega(db, coll_rif, campo, copia["id"], resta["id"])
            completa = await db[collezione].find_one({"id": copia["id"]}, {"_id": 0}) or copia
            await sposta_nella_cartella(db, collezione, completa, resta["id"], actor=actor)
    logger.info("[doppioni] %s: %s copie spostate in %s%s (%s riferimenti ricollegati)",
                collezione, esito["copie"], collezione, SUFFISSO, esito["ricollegati"])
    return esito


async def _f24_gia_in_quarantena(db, *, dry_run: bool, actor: str) -> Dict[str, Any]:
    from app.services.f24_doppioni import COLL, MOTIVO_DOPPIONE, STATO_QUARANTENA

    copie = await db[COLL].find({"status": STATO_QUARANTENA, "motivo_quarantena": MOTIVO_DOPPIONE},
                                {"_id": 0}).to_list(None)
    if not dry_run:
        for copia in copie:
            await sposta_nella_cartella(db, COLL, copia, copia.get("doppione_di"), actor=actor)
    return {"collezione": COLL, "copie": len(copie)}


async def _prima_nota_salari(db, *, dry_run: bool, actor: str) -> Dict[str, Any]:
    from app.services.bonifica_prima_nota_salari_doppioni import COLLECTION, esegui

    bonifica = await esegui(db, dry_run=dry_run, actor=actor)
    spostate = 0
    if not dry_run:
        marcate = await db[COLLECTION].find(
            {"duplicate_of": {"$exists": True}, "entity_status": "deleted"}, {"_id": 0},
        ).to_list(None)
        for riga in marcate:
            if riga.get("duplicate_of"):
                await sposta_nella_cartella(db, COLLECTION, riga, riga["duplicate_of"], actor=actor)
                spostate += 1
    return {"collezione": COLLECTION, "bonifica": {k: v for k, v in bonifica.items()
                                                  if not isinstance(v, list)}, "spostate": spostate}


async def _rileggi_ricevute_sumup(db, *, dry_run: bool) -> Dict[str, Any]:
    """Ricevute SumUp lette col beneficiario sbagliato (IBAN SumUp, nome dal file): si rileggono per id."""
    import base64

    from app.routers.bonifici_module.pdf_parser import extract_transfers_from_text, read_pdf_bytes

    righe = await db["bonifici_transfers"].find({}, {"_id": 0, "id": 1, "beneficiario": 1}).to_list(None)
    ids = [r["id"] for r in righe
           if str((r.get("beneficiario") or {}).get("iban") or "").upper().startswith("IE")
           and "SUMU" in str((r.get("beneficiario") or {}).get("iban") or "").upper()]
    corrette = 0
    for rid in ids:
        completa = await db["bonifici_transfers"].find_one({"id": rid}, {"_id": 0})
        dati = (completa or {}).get("pdf_data")
        if not dati:
            continue
        try:
            testo = await asyncio.to_thread(read_pdf_bytes, base64.b64decode(dati))
            letto = extract_transfers_from_text(testo, filename=completa.get("source_file") or "")[0]
        except Exception as exc:
            logger.warning("[doppioni] ricevuta SumUp %s illeggibile: %s %s", rid, type(exc).__name__, exc)
            continue
        if str((letto.get("beneficiario") or {}).get("iban") or "").upper().startswith("IE"):
            continue
        corrette += 1
        if not dry_run:
            data = letto.get("data")
            await db["bonifici_transfers"].update_one({"id": rid}, {"$set": {
                "beneficiario": letto["beneficiario"], "ordinante": letto["ordinante"],
                "causale": letto["causale"], "cro_trn": letto["cro_trn"],
                **({"data": data.isoformat()} if hasattr(data, "isoformat") else {}),
                "updated_at": _ora(),
            }})
    return {"collezione": "bonifici_transfers", "ricevute_sumup_da_rileggere": len(ids), "corrette": corrette}


async def _stampe_fattura_tra_bonifici(db, *, dry_run: bool, actor: str) -> Dict[str, Any]:
    """Stampe PDF di fatture entrate come bonifici (importo = imponibile): in quarantena per id.

    Chi controllare lo sceglie l'assenza di un riferimento di banca; la decisione e' del contenuto del PDF.
    """
    import base64

    from app.routers.bonifici_module.pdf_parser import read_pdf_bytes
    from app.services.bonifici_pdf_ingest import e_stampa_fattura

    # Il contenuto decide; per non rileggere ogni PDF si guardano i transfer senza
    # riferimento di banca (CRO/TRN/rif. interno): una ricevuta vera ne porta uno.
    candidati = [
        r for r in await db["bonifici_transfers"].find(
            {}, {"_id": 0, "id": 1, "cro_trn": 1, "rif_interno": 1,
                 "salario_associato": 1, "fattura_associata": 1, "hr_deposito": 1}).to_list(None)
        if not r.get("cro_trn") and not r.get("rif_interno")
        and not r.get("salario_associato") and not r.get("fattura_associata")
        and (r.get("hr_deposito") or {}).get("esito") not in {"depositato", "arricchito"}
    ]
    trovati: List[str] = []
    for cand in candidati:
        completa = await db["bonifici_transfers"].find_one({"id": cand["id"]}, {"_id": 0})
        dati = (completa or {}).get("pdf_data")
        if not dati:
            continue
        try:
            testo = await asyncio.to_thread(read_pdf_bytes, base64.b64decode(dati))
        except Exception as exc:
            logger.warning("[doppioni] stampa fattura %s illeggibile: %s %s", cand["id"], type(exc).__name__, exc)
            continue
        if not e_stampa_fattura(testo):
            continue
        trovati.append(cand["id"])
        if not dry_run:
            from app.services.bonifici_pdf_ingest import togli_code_hr_e_inbox

            await togli_code_hr_e_inbox(db, cand["id"])
            await sposta_nella_cartella(
                db, "bonifici_transfers", completa, None,
                motivo="stampa PDF di una fattura, non un bonifico", actor=actor)
    return {"collezione": "bonifici_transfers", "stampe_fattura": len(trovati), "ids": trovati[:20]}


async def ripulisci(db, *, dry_run: bool = True, actor: str = "sistema") -> Dict[str, Any]:
    """Cedolini, Prima Nota salari, quietanze F24, bonifici e F24: un giro solo."""
    return {
        "dry_run": dry_run,
        "cedolini": await _tratta(db, "cedolini", identita_cedolino, _punteggio_cedolino,
                                  dry_run=dry_run, actor=actor,
                                  riferimenti=(("prima_nota_salari", "cedolino_id"),)),
        "prima_nota_salari": await _prima_nota_salari(db, dry_run=dry_run, actor=actor),
        "quietanze_f24": await _tratta(db, "quietanze_f24", identita_quietanza, _punteggio_quietanza,
                                       dry_run=dry_run, actor=actor,
                                       riferimenti=(("f24_unificato", "quietanza_id"),)),
        "bonifici_sumup_riletti": await _rileggi_ricevute_sumup(db, dry_run=dry_run),
        "bonifici_transfers": await _tratta(db, "bonifici_transfers", identita_bonifico,
                                            _punteggio_bonifico, dry_run=dry_run, actor=actor),
        "bonifici_stampe_fattura": await _stampe_fattura_tra_bonifici(db, dry_run=dry_run, actor=actor),
        "f24_unificato": await _f24_gia_in_quarantena(db, dry_run=dry_run, actor=actor),
    }
