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
