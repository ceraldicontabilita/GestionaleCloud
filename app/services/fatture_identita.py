"""Identita' documentale delle fatture: normalizzazione, storni non ammessi, dedup.

Trovato il 17/09/2026 sui dati reali: le 767 fatture 2026 importate dall'archivio
legacy (``source: xml_import``, create il 14/09 05:27) tenevano l'XML in
``fattura_allegata`` e i dati in campi propri (``numero``, ``data_documento``,
``importo_totale``, ``fornitore`` = ragione sociale) senza ``invoice_key``,
``supplier_vat`` ne' ``content_hash``. Per il gestionale erano quindi fatture
"senza identita'": l'ingest Drive delle stesse fatture non le vedeva
(controlla ``invoice_key``) e ne creava una seconda copia — 485 doppioni, di
cui 9 registrati DUE volte nel libro giornale — e la pulizia periodica dei
duplicati (``pulisci_duplicati_invoices``) non poteva raggrupparle (senza
P.IVA in chiaro) ne' provarle uguali (senza hash).

Questo modulo NON introduce un secondo sistema: ricava l'identita' canonica
dall'XML con lo stesso parser dell'import (``parse_fattura_xml``), la stessa
chiave (``generate_invoice_key``) e la stessa impronta (``sha256`` dell'XML,
identica a quella dell'ingest Drive: verificato su 4/4 coppie in produzione),
poi lascia lavorare i meccanismi gia' esistenti: dedup periodica per hash,
storno del motore unico di registrazione.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

COLL = "invoices"
_STATO_KEY = "bonifica_identita_fatture_stato"
_PAUSA = 0.1
_lock = asyncio.Lock()
_task: Optional[asyncio.Task] = None

_CAMPI_XML = ("xml_raw", "fattura_allegata", "document_original_ref", "xml_content")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _testo_xml(doc: Dict[str, Any]) -> Optional[str]:
    """Primo campo che contiene davvero una FatturaElettronica."""
    for campo in _CAMPI_XML:
        valore = doc.get(campo)
        if isinstance(valore, str) and "FatturaElettronica" in valore and "<" in valore:
            return valore
    return None


def _vuoto(valore: Any) -> bool:
    if valore is None:
        return True
    if isinstance(valore, str) and not valore.strip():
        return True
    if isinstance(valore, (int, float)) and float(valore) == 0.0:
        return True
    if isinstance(valore, (list, dict)) and not valore:
        return True
    return False


def _senza_identita(doc: Dict[str, Any]) -> bool:
    return _vuoto(doc.get("invoice_key")) or _vuoto(doc.get("content_hash")) \
        or _vuoto(doc.get("supplier_vat"))


_CAMPI_IMPRONTA = (
    "invoice_number", "invoice_date", "supplier_vat", "supplier_name", "customer_vat",
    "total_amount", "imponibile", "iva", "tipo_documento", "linee", "riepilogo_iva",
    "dati_pagamento", "dati_ddt",
)


_PREFISSO_IMPRONTA = "c2:"


def _testo_canonico(valore: Any) -> Any:
    """Stringhe con i soli caratteri ASCII (via ogni carattere non ASCII,
    compresi accenti, simboli e i «�» di una decodifica sbagliata: «Carità»
    e «Carit�» diventano entrambi «Carit») e gli spazi compressi; liste e
    dizionari ricorsivamente. Numeri e None invariati. Niente NFKD: «à» →
    «a» non combacerebbe con «�» → «»."""
    if isinstance(valore, str):
        piatto = valore.encode("ascii", "ignore").decode("ascii")
        return " ".join(piatto.split())
    if isinstance(valore, dict):
        return {str(k): _testo_canonico(v) for k, v in valore.items()}
    if isinstance(valore, (list, tuple)):
        return [_testo_canonico(v) for v in valore]
    return valore


def ha_impronta_corrente(doc: Dict[str, Any]) -> bool:
    """Vero se ``content_hash_canonico`` e' stato calcolato con la versione
    attuale dell'impronta (prefisso ``c2:``); le versioni precedenti vanno
    ricalcolate dal backfill."""
    return str(doc.get("content_hash_canonico") or "").startswith(_PREFISSO_IMPRONTA)


def impronta_contenuto_fattura(xml: str) -> Optional[str]:
    """Impronta del CONTENUTO della fattura (campi e righe letti dall'XML con
    il parser dell'import), indipendente da BOM, a capo, spazi, codifica e
    caratteri non ASCII del file. 17/09/2026: 42 coppie legacy↔Drive della
    stessa fattura restavano bloccate come «collisione di identita' da
    verificare» per un byte di BOM o, verificato in produzione, per «Carità»
    decodificato come «Carit�» in una copia (windows-1252 letto male). Non e'
    un confronto per numero e importo: entrano tutte le righe, i riepiloghi
    IVA, il tipo documento, le date e i pagamenti. Prefisso ``c2:`` (versione
    dell'impronta) per non confondersi con gli sha256 dei file. ``None`` se
    l'XML non e' leggibile."""
    if not isinstance(xml, str) or "FatturaElettronica" not in xml:
        return None
    from app.parsers.fattura_elettronica_parser import parse_fattura_xml

    try:
        parsed = parse_fattura_xml(xml.lstrip("\ufeff"))
    except Exception:  # noqa: BLE001 - XML rotto = nessuna impronta
        return None
    if not isinstance(parsed, dict) or parsed.get("error") or not parsed.get("invoice_number"):
        return None
    base = {campo: _testo_canonico(parsed.get(campo)) for campo in _CAMPI_IMPRONTA if campo in parsed}
    testo = json.dumps(base, sort_keys=True, ensure_ascii=True, default=str,
                       separators=(",", ":"))
    return _PREFISSO_IMPRONTA + hashlib.sha256(testo.encode("utf-8")).hexdigest()


def patch_identita_da_xml(doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Campi canonici mancanti ricavati dall'XML del documento (nessuna
    sovrascrittura di valori gia' presenti, tranne ``total_amount`` a zero).
    ``None`` se il documento non ha un XML leggibile o ha gia' l'identita'."""
    if not _senza_identita(doc):
        return None
    xml = _testo_xml(doc)
    if not xml:
        return None
    from app.parsers.fattura_elettronica_parser import parse_fattura_xml
    from app.routers.invoices.fatture_upload import generate_invoice_key

    parsed = parse_fattura_xml(xml)
    if parsed.get("error") or not parsed.get("invoice_number") or not parsed.get("supplier_vat"):
        return None
    patch: Dict[str, Any] = {}

    def metti(campo: str, valore: Any) -> None:
        if valore in (None, "", [], {}):
            return
        if _vuoto(doc.get(campo)):
            patch[campo] = valore

    metti("supplier_vat", parsed.get("supplier_vat"))
    metti("supplier_name", parsed.get("supplier_name"))
    metti("invoice_number", parsed.get("invoice_number"))
    metti("invoice_date", parsed.get("invoice_date"))
    metti("total_amount", float(parsed.get("total_amount") or 0))
    metti("imponibile", float(parsed.get("imponibile") or 0))
    metti("iva", float(parsed.get("iva") or 0))
    metti("tipo_documento", parsed.get("tipo_documento"))
    metti("tipo_documento_desc", parsed.get("tipo_documento_desc"))
    metti("fornitore", parsed.get("fornitore"))
    metti("linee", parsed.get("linee"))
    metti("riepilogo_iva", parsed.get("riepilogo_iva"))
    metti("cedente_piva", parsed.get("supplier_vat"))
    metti("cedente_denominazione", parsed.get("supplier_name"))
    metti("numero_fattura", parsed.get("invoice_number"))
    metti("data_fattura", parsed.get("invoice_date"))
    data = str(parsed.get("invoice_date") or "")
    if data[:4].isdigit():
        metti("anno", int(data[:4]))
    metti("xml_raw", xml)
    metti("content_hash", hashlib.sha256(xml.encode("utf-8")).hexdigest())
    if not ha_impronta_corrente(doc):
        patch["content_hash_canonico"] = impronta_contenuto_fattura(xml)
    chiave = generate_invoice_key(
        doc.get("invoice_number") or parsed.get("invoice_number", ""),
        doc.get("supplier_vat") or parsed.get("supplier_vat", ""),
        doc.get("invoice_date") or parsed.get("invoice_date", ""),
    )
    if _vuoto(doc.get("invoice_key")):
        patch["invoice_key"] = chiave
    if not patch:
        return None
    patch["identita_normalizzata_da"] = "xml_documento"
    patch["identita_normalizzata_at"] = _now()
    return patch


async def normalizza_fatture_senza_identita(db, *, dry_run: bool = False,
                                            pausa: float = _PAUSA) -> Dict[str, Any]:
    """Da' l'identita' canonica alle fatture attive che ne sono prive ma hanno
    l'XML. Idempotente: al secondo giro non trova piu' nulla."""
    # Prima passata SENZA payload (XML/PDF restano su Supabase): serve solo a
    # scegliere i candidati. Il documento completo si legge per id, uno alla
    # volta, soltanto per chi non ha identita' — mai l'intera collezione con
    # gli XML (in produzione 1.400 fatture = decine di MB e timeout a catena).
    from app.document_repository import metadata_projection

    leggeri = await db[COLL].find(
        {"status": {"$nin": ["deleted", "archived"]}}, metadata_projection(COLL)).to_list(None)
    candidati = [d for d in leggeri if _senza_identita(d)]
    normalizzate, senza_xml, errori = 0, 0, []
    for leggero in candidati:
        try:
            doc = await db[COLL].find_one({"id": leggero.get("id")}, {"_id": 0}) if leggero.get("id") else None
            if doc is None:
                senza_xml += 1
                continue
            patch = patch_identita_da_xml(doc)
        except Exception as exc:  # noqa: BLE001 - un XML rotto non ferma il giro
            errori.append(f"{doc.get('id')}: {exc}")
            continue
        if not patch:
            senza_xml += 1
            continue
        if dry_run:
            normalizzate += 1
            continue
        try:
            await db[COLL].update_one({"id": doc.get("id")}, {"$set": patch})
        except Exception as exc:  # noqa: BLE001 - un timeout Supabase non ferma il giro
            errori.append(f"{doc.get('id')}: scrittura fallita: {exc}")
            continue
        normalizzate += 1
        if pausa:
            await asyncio.sleep(pausa)
    return {"dry_run": dry_run, "candidate": len(candidati), "normalizzate": normalizzate,
            "senza_xml": senza_xml, "errori": errori[:20]}


async def normalizza_impronte_canoniche(db, *, dry_run: bool = False, massimo: int = 300,
                                        pausa: float = _PAUSA) -> Dict[str, Any]:
    """Da' l'impronta del contenuto (``content_hash_canonico``) alle fatture
    attive con XML che ne sono prive, al massimo ``massimo`` per giro (il
    documento completo si legge per id). Idempotente: al giro successivo
    restano solo quelle senza XML leggibile."""
    from app.document_repository import metadata_projection

    leggeri = await db[COLL].find(
        {"status": {"$nin": ["deleted", "archived"]}}, metadata_projection(COLL)).to_list(None)
    candidati = [d for d in leggeri
                 if not ha_impronta_corrente(d) and d.get("id")
                 and not d.get("senza_xml_leggibile")]
    # Prima le fatture coinvolte in una collisione di identita' (e le loro
    # controparti): sono quelle che l'impronta sblocca subito, invece di
    # aspettare che il backfill a lotti le raggiunga per caso.
    in_collisione = {str(d["id"]) for d in leggeri if d.get("identity_collision_with_ids")
                     or d.get("stato_import") == "collisione_identita_da_verificare"}
    for d in leggeri:
        in_collisione.update(str(i) for i in (d.get("identity_collision_with_ids") or []) if i)
    candidati.sort(key=lambda d: (str(d["id"]) not in in_collisione, str(d.get("created_at") or "")))
    calcolate, senza_xml, errori = 0, 0, []
    for leggero in candidati[:massimo]:
        try:
            doc = await db[COLL].find_one({"id": leggero["id"]}, {"_id": 0})
            xml = _testo_xml(doc or {})
            impronta = impronta_contenuto_fattura(xml) if xml else None
        except Exception as exc:  # noqa: BLE001
            errori.append(f"{leggero['id']}: {exc}")
            continue
        if dry_run:
            calcolate += int(bool(impronta))
            senza_xml += int(not impronta)
            continue
        try:
            if impronta:
                await db[COLL].update_one({"id": leggero["id"]}, {"$set": {"content_hash_canonico": impronta}})
                calcolate += 1
            else:
                # non ritentare a ogni giro un documento senza XML leggibile
                await db[COLL].update_one({"id": leggero["id"]}, {"$set": {"senza_xml_leggibile": True}})
                senza_xml += 1
        except Exception as exc:  # noqa: BLE001 - un timeout non ferma il giro
            errori.append(f"{leggero['id']}: scrittura fallita: {exc}")
            continue
        if pausa:
            await asyncio.sleep(pausa)
    return {"dry_run": dry_run, "candidate": len(candidati), "calcolate": calcolate,
            "senza_xml": senza_xml, "restanti": max(0, len(candidati) - massimo),
            "errori": errori[:20]}


async def storna_registrazioni_non_ammesse(db, *, dry_run: bool = False,
                                           pausa: float = _PAUSA) -> Dict[str, Any]:
    """Toglie dal libro giornale (con storno, mai cancellando) le fatture che
    non dovevano entrarci: archivio storico degli anni passati e doppioni
    gia' archiviati con ``duplicate_of``."""
    from app.services.registrazione_contabile import storna_registrazione_fattura

    docs = await db[COLL].find(
        {"registrata_contabilita": True},
        {"_id": 0, "id": 1, "status": 1, "stato_import": 1, "duplicate_of": 1,
         "invoice_number": 1, "invoice_date": 1}).to_list(None)
    da_stornare = []
    for d in docs:
        if d.get("duplicate_of"):
            da_stornare.append((d, f"duplicato della fattura {d['duplicate_of']}"))
        elif d.get("status") in {"archiviata", "archived", "deleted"} \
                or d.get("stato_import") == "archivio_storico":
            da_stornare.append((d, "fattura di archivio storico, fuori dal flusso contabile attivo"))
    stornate, esiti, errori = 0, [], []
    for d, motivo in da_stornare:
        if dry_run:
            continue
        try:
            r = await storna_registrazione_fattura(db, d.get("id"), motivo)
            esiti.append(r.get("stato"))
            if r.get("stato") == "stornato":
                stornate += 1
        except Exception as exc:  # noqa: BLE001
            errori.append(f"{d.get('id')}: {exc}")
        if pausa:
            await asyncio.sleep(pausa)
    return {"dry_run": dry_run, "da_stornare": len(da_stornare), "stornate": stornate,
            "esiti": {s: esiti.count(s) for s in set(esiti)}, "errori": errori[:20]}


async def bonifica_identita_fatture(db, *, dry_run: bool = False) -> Dict[str, Any]:
    """Giro completo, nell'ordine che serve: identita' → dedup provata per
    hash (archivia il doppione e ne storna la scrittura) → storno delle
    registrazioni non ammesse residue."""
    from app.routers.fatture_module.crud import pulisci_duplicati_invoices

    esito: Dict[str, Any] = {"dry_run": dry_run, "avviato_at": _now()}
    esito["identita"] = await normalizza_fatture_senza_identita(db, dry_run=dry_run)
    esito["impronte"] = await normalizza_impronte_canoniche(db, dry_run=dry_run)
    if dry_run:
        esito["dedup"] = {"dry_run": True, "nota": "la dedup per hash gira solo in modalita' reale"}
    else:
        esito["dedup"] = await pulisci_duplicati_invoices()
    esito["storni"] = await storna_registrazioni_non_ammesse(db, dry_run=dry_run)
    esito["terminato_at"] = _now()
    return esito


# --- esecuzione in background con stato persistito (stesso schema del pregresso)

def bonifica_in_corso() -> bool:
    return _task is not None and not _task.done()


async def _scrivi_stato(db, **campi: Any) -> None:
    await db["sistema_stato"].update_one(
        {"chiave": _STATO_KEY}, {"$set": {"chiave": _STATO_KEY, **campi}}, upsert=True)


async def _esegui(db) -> None:
    async with _lock:
        await _scrivi_stato(db, stato="in_corso", avviato_at=_now(), terminato_at=None,
                            risultato=None, errore=None)
        try:
            risultato = await bonifica_identita_fatture(db, dry_run=False)
            await _scrivi_stato(db, stato="completato", terminato_at=_now(), risultato=risultato)
            logger.info("[BONIFICA-IDENTITA-FATTURE] %s", risultato)
        except Exception as exc:  # noqa: BLE001
            logger.exception("[BONIFICA-IDENTITA-FATTURE] fallita")
            await _scrivi_stato(db, stato="errore", terminato_at=_now(), errore=str(exc))


def avvia_bonifica_in_background(db) -> bool:
    global _task
    if bonifica_in_corso():
        return False
    _task = asyncio.get_running_loop().create_task(_esegui(db))
    return True


async def stato_bonifica(db) -> Dict[str, Any]:
    doc = await db["sistema_stato"].find_one({"chiave": _STATO_KEY}, {"_id": 0}) or {}
    doc.pop("chiave", None)
    doc.setdefault("stato", "mai_eseguita")
    doc["in_corso"] = bonifica_in_corso()
    return doc
