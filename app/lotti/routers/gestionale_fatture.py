"""Ponte unidirezionale GestionaleCloud -> Lotti per le fatture ricevute.

GestionaleCloud resta proprietario del documento contabile. Lotti conserva solo
la copia operativa necessaria a lotti, tracciabilita, prezzi e magazzino, insieme
all'identificativo e all'hash della fonte. Il registro ricevute rende ogni giro
idempotente e blocca automaticamente una sorgente cambiata dopo l'importazione.
"""

from __future__ import annotations

import hashlib
import os
import asyncio
import weakref
from functools import wraps
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote
from xml.sax.saxutils import escape

import httpx
from fastapi import APIRouter, Depends, Query

from app.lotti.auth import require_admin
from app.lotti.db import database as db
from app.lotti.servizi.identita_fatture import query_identita_fattura


router = APIRouter(prefix="/gestionale-fatture", tags=["GestionaleCloud Fatture"])
RECEIPTS = "gestionale_fatture_ricevute"
_STATI_NON_IMPORTABILI = {"senza_contenuto", "senza_identita_fornitore"}
_LUCCHETTI_INGRESSO = weakref.WeakKeyDictionary()


def _ingresso_serializzato(funzione):
    """Evento e sync condividono il tratto verifica/import nel singolo worker.

    Il document store Lotti supporta una sola istanza. Questo lucchetto non
    sostituisce una transazione o una garanzia fra processi distinti.
    """
    @wraps(funzione)
    async def esegui(*args, **kwargs):
        loop = asyncio.get_running_loop()
        lock = _LUCCHETTI_INGRESSO.setdefault(loop, asyncio.Lock())
        async with lock:
            return await funzione(*args, **kwargs)
    return esegui


def set_database(database):
    global db
    db = database


def _base_url() -> str:
    return (os.environ.get("GESTIONALECLOUD_API_URL") or "").strip().rstrip("/")


def _secret() -> str:
    return (os.environ.get("LOTTI_INTEGRATION_KEY") or "").strip()


def configurato() -> bool:
    # Nel monolite GestionaleCloud la fonte ERP è nello stesso processo: non
    # servono URL o segreti per fare una chiamata HTTP verso se stessi.
    return True


def _usa_ponte_http() -> bool:
    """Compatibilità per installazioni che tengono ancora Lotti separato."""
    return bool(_base_url() and _secret())


def _invoice_query(item: dict[str, Any]) -> dict[str, Any]:
    """La stessa fattura come la conosce Lotti, con **tutte** le identita'.

    Prima, se il gestionale aveva la P.IVA, si cercava solo `numero + piva`.
    Misurato il 22/09/2026: due fatture (Fiorentino 1/163, Vandemoortele
    8528000340) erano gia' in Lotti dall'import di gennaio con una P.IVA
    troncata o diversa («03473», il codice fiscale al posto della partita
    IVA), la chiave non combaciava e il ponte le ha create una seconda volta.
    Ora basta che combaci una delle due identita': numero + P.IVA, oppure
    numero + fornitore + data. Un `$or` su chiavi assenti non passa mai da
    solo, perche' ogni ramo esige il numero.
    """
    number = str(item.get("invoice_number") or "").strip()
    vat = str(item.get("supplier_vat") or "").strip()
    date = str(item.get("invoice_date") or "").strip()
    if len(date) >= 10 and date[4:5] == "-":
        date = f"{date[8:10]}/{date[5:7]}/{date[:4]}"
    query = query_identita_fattura(
        numero=number,
        piva=vat,
        fornitore=item.get("supplier_name"),
        data=date,
        source_id=item.get("source_id"),
    )
    if query is None:
        raise ValueError("Fattura senza identità completa")
    return query


def _xml_from_projection(item: dict[str, Any]) -> str:
    """Crea un XML minimo quando GestionaleCloud conserva righe ma non il raw.

    Non inventa dati: usa esclusivamente i campi della proiezione e lascia vuoti
    quelli assenti. Serve a far passare le righe nella stessa pipeline HACCP.
    """
    def text(*keys: str, default: Any = "") -> str:
        for key in keys:
            value = item.get(key)
            if value not in (None, ""):
                return escape(str(value).strip())
        return escape(str(default).strip())

    vat = str(item.get("supplier_vat") or "").strip()
    if vat.upper().startswith("IT"):
        vat = vat[2:]
    invoice_date = str(item.get("invoice_date") or "").strip()
    if len(invoice_date) >= 10 and invoice_date[2:3] in {"/", "-"}:
        invoice_date = f"{invoice_date[6:10]}-{invoice_date[3:5]}-{invoice_date[:2]}"
    lines = item.get("lines") if isinstance(item.get("lines"), list) else []
    details = []
    for index, line in enumerate(lines, 1):
        if not isinstance(line, dict):
            continue
        def line_text(*keys: str, default: Any = "") -> str:
            for key in keys:
                value = line.get(key)
                if value not in (None, ""):
                    return escape(str(value).strip())
            return escape(str(default).strip())
        description = line_text("descrizione", "description", "nome", "name")
        if not description:
            continue
        details.append(
            "<DettaglioLinee>"
            f"<NumeroLinea>{index}</NumeroLinea>"
            f"<Descrizione>{description}</Descrizione>"
            f"<Quantita>{line_text('quantita', 'quantity', 'qta', default='1')}</Quantita>"
            f"<UnitaMisura>{line_text('unita_misura', 'unit', 'um', default='PZ')}</UnitaMisura>"
            f"<PrezzoUnitario>{line_text('prezzo_unitario', 'unit_price', 'prezzo', default='0')}</PrezzoUnitario>"
            f"<PrezzoTotale>{line_text('prezzo_totale', 'line_total', 'totale', default='0')}</PrezzoTotale>"
            "</DettaglioLinee>"
        )
    if not details:
        return ""
    return (
        "<?xml version='1.0' encoding='UTF-8'?>"
        "<FatturaElettronica>"
        "<FatturaElettronicaHeader><CedentePrestatore><DatiAnagrafici>"
        f"<IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>{escape(vat)}</IdCodice></IdFiscaleIVA>"
        f"<Anagrafica><Denominazione>{text('supplier_name')}</Denominazione></Anagrafica>"
        "</DatiAnagrafici></CedentePrestatore></FatturaElettronicaHeader>"
        "<FatturaElettronicaBody><DatiGenerali><DatiGeneraliDocumento>"
        f"<TipoDocumento>{text('document_type', default='TD01')}</TipoDocumento>"
        f"<Numero>{text('invoice_number')}</Numero><Data>{escape(invoice_date)}</Data>"
        f"<ImportoTotaleDocumento>{text('total_amount', default='0')}</ImportoTotaleDocumento>"
        "</DatiGeneraliDocumento></DatiGenerali><DatiBeniServizi>"
        + "".join(details)
        + "</DatiBeniServizi></FatturaElettronicaBody></FatturaElettronica>"
    )


async def _get_json(client: httpx.AsyncClient, path: str, **params) -> dict[str, Any]:
    response = await client.get(
        f"{_base_url()}{path}",
        params=params or None,
        headers={"X-Lotti-Key": _secret()},
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("Risposta GestionaleCloud non valida")
    return payload


# Guardia contro un ciclo infinito se la fonte sbaglia a dire `total`. Non e'
# il tetto di lavorazione: quello si applica alle sole fatture ANCORA DA
# PRENDERE, dopo il confronto col registro delle ricevute.
_TETTO_ELENCO = 20000


async def _elenco(client: httpx.AsyncClient, anno: int | None) -> tuple[list[dict], int]:
    """Elenco COMPLETO della fonte per l'anno. Tagliarlo qui significherebbe
    tagliarlo per data (l'elenco arriva ordinato), cioe' perdere per sempre le
    fatture piu' recenti."""
    items: list[dict] = []
    skip = 0
    total = 0
    while len(items) < _TETTO_ELENCO:
        params: dict[str, Any] = {"skip": skip, "limit": 500}
        if anno:
            params["anno"] = anno
        page = await _get_json(client, "/api/integrations/lotti/invoices", **params)
        data = page.get("data") if isinstance(page.get("data"), list) else []
        total = int(page.get("total") or len(data))
        items.extend(x for x in data if isinstance(x, dict))
        skip += len(data)
        if not data or skip >= total:
            break
    return items, total


async def _elenco_locale(anno: int | None) -> tuple[list[dict], int]:
    """Legge la proiezione canonica direttamente dal GestionaleCloud locale.

    Restituisce TUTTE le fatture dell'anno, non le prime N: il taglio per
    numero si applica piu' avanti alle sole fatture ancora da prendere."""
    from app.routers.lotti_integration import _documents, _projection, _year

    items = [_projection(doc, include_xml=False) for doc in await _documents()]
    if anno is not None:
        items = [item for item in items if _year(item.get("invoice_date", "")) == anno]
    items.sort(key=lambda item: (item.get("invoice_date", ""), item.get("source_id", "")))
    return items, len(items)


async def _dettaglio_locale(source_id: str) -> dict[str, Any]:
    from app.routers.lotti_integration import _documento_per_source_id, _projection

    document = await _documento_per_source_id(source_id)
    if document is not None:
        return _projection(document, include_xml=True)
    raise ValueError("Fattura sorgente non trovata nel GestionaleCloud")


async def _leggi_dettaglio(client, source_id: str) -> dict[str, Any]:
    if client is not None:
        return await _get_json(client, f"/api/integrations/lotti/invoices/{quote(source_id, safe='')}")
    return await _dettaglio_locale(source_id)


def _sha_xml(testo: Any) -> str:
    testo = str(testo or "")
    return hashlib.sha256(testo.encode("utf-8")).hexdigest() if testo else ""


async def fatture_da_prendere_fornitore(piva: str, nome: str) -> list[str]:
    """`source_id` delle fatture di UN fornitore non ancora in Lotti.

    Serve quando lo si include: entrano le sole fatture ancora da prendere
    (le altre le riconosce `_source_id_gia_presi`, e l'import e' comunque
    idempotente). Il fornitore si riconosce per P.IVA; senza P.IVA per nome."""
    from app.services.magazzino_fornitore import chiave_nome, normalizza_piva

    p, n = normalizza_piva(piva), chiave_nome(nome)
    if not p and not n:
        return []
    items, _ = await _elenco_locale(None)
    gia_presi = await _source_id_gia_presi()
    trovati: list[str] = []
    for item in items:
        vat = normalizza_piva(item.get("supplier_vat"))
        if p:
            if vat != p:
                continue
        elif chiave_nome(item.get("supplier_name")) != n:
            continue
        sid = str(item.get("source_id") or "").strip()
        sh = str(item.get("source_hash") or "").strip()
        if not sid or (sh and gia_presi.get(sid) == sh):
            continue
        trovati.append(sid)
    return trovati


def _descrivi(exc: BaseException) -> str:
    """Messaggio dell'eccezione, o il suo TIPO se il messaggio e' vuoto.

    `str(exc)` e' vuoto per molte eccezioni reali (i timeout di httpx, per
    dirne una). Il registro di produzione al 20/09/2026 conteneva quattro giri
    andati storti con scritto soltanto «Lettura fonte GestionaleCloud: » —
    un guasto muto, che CLAUDE.md vieta proprio perche' il log deve dire
    QUALE cosa non ha funzionato, non limitarsi a dire «errore»."""
    testo = str(exc).strip()
    tipo = type(exc).__name__
    return f"{tipo}: {testo[:180]}" if testo else tipo


async def _fatture_presenti() -> set[str]:
    return {
        str(f["id"])
        for f in await db.fatture.find({}, {"_id": 0, "id": 1, "haccp_import_completo": 1,
                                           "haccp_import_ambiguo": 1}).to_list(100000)
        if f.get("id") and f.get("haccp_import_completo") is not False and not f.get("haccp_import_ambiguo")
    }


async def _source_id_gia_presi(presenti: set[str] | None = None) -> dict[str, str]:
    """`source_id` -> `source_hash` delle fatture gia' prese E ANCORA PRESENTI.

    Solo gli stati terminali: un `conflitto_hash` deve essere riesaminato ogni
    giro, non saltato.

    Il registro da solo non basta. Se le fatture operative di Lotti vengono
    svuotate (ripopolamento da zero, ripristino, cancellazione a mano) il
    registro resta pieno e il ponte salta TUTTO: il magazzino non si rialimenta
    piu' e nessuno capisce perche'. Una riga vale quindi solo se la fattura
    che dice di aver preso esiste ancora davvero in `db.fatture`; altrimenti
    torna fra quelle da prendere, e l'import e' idempotente, quindi
    rialimentare non duplica.

    Una lettura sola dei soli identificativi, non una per fattura."""
    righe = await getattr(db, RECEIPTS).find(
        {"stato": {"$in": ["importata", "collegata_esistente"]}},
        {"_id": 0, "source_id": 1, "source_hash": 1, "fattura_id": 1},
    ).to_list(100000)
    if presenti is None:
        presenti = await _fatture_presenti()
    presi: dict[str, str] = {}
    for r in righe:
        sid = str(r.get("source_id") or "")
        if not sid:
            continue
        fattura_id = str(r.get("fattura_id") or "")
        if not fattura_id or fattura_id not in presenti:
            continue  # il registro dice presa, ma in Lotti non c'e' piu'
        presi[sid] = str(r.get("source_hash") or "")
    return presi


async def _verifica_xml_ricevuto(item, receipt, *, client=None, dettaglio=None,
                               anteprima=False):
    """Una sola regola XML per l'ingresso evento e per il giro periodico."""
    source_id = str(item.get("source_id") or "")
    source_hash = str(item.get("source_hash") or "")
    chiavi = [_invoice_query(item)]
    if receipt and receipt.get("fattura_id"):
        chiavi.append({"id": receipt["fattura_id"]})
    existing = await db.fatture.find_one(
        {"$or": chiavi}, {"_id": 0, "id": 1, "haccp_xml_sha256": 1,
                           "xml_raw": 1, "haccp_import_completo": 1, "haccp_import_ambiguo": 1},
    )
    if not existing:
        return None
    if existing.get("haccp_import_ambiguo"):
        return {"stato": "errore", "fattura_id": existing.get("id"),
                "motivo": "Carico stock con esito incerto: verificare fattura e movimenti "
                          "prima di autorizzare un nuovo tentativo"}
    if receipt and receipt.get("source_hash") == source_hash:
        return None
    sha_lotti = existing.get("haccp_xml_sha256") or _sha_xml(existing.get("xml_raw"))
    if not receipt and not sha_lotti:
        return None  # copia legacy senza impronta da confrontare
    if dettaglio is None:
        dettaglio = await _leggi_dettaglio(client, source_id)
    xml_fonte = str(dettaglio.get("xml_raw") or "") or _xml_from_projection(dettaglio)
    sha_fonte = _sha_xml(xml_fonte)
    now = datetime.now(timezone.utc).isoformat()
    if sha_lotti and sha_lotti == sha_fonte:
        if existing.get("haccp_import_completo") is False or not receipt:
            return None  # il documento parziale va ripreso dal motore
        if not anteprima:
            await getattr(db, RECEIPTS).update_one(
                {"source_id": source_id},
                {"$set": {"source_hash": source_hash, "stato": "collegata_esistente",
                          "fattura_id": existing.get("id"), "ultimo_controllo": now},
                 "$unset": {"nuovo_source_hash": "", "conflitto_verificato": ""}},
            )
            await db.fatture.update_one({"id": existing["id"]},
                                       {"$set": {"gestionale_source_hash": source_hash}})
        return {"stato": "riallineata", "fattura_id": existing.get("id")}
    motivo = ("L'XML della fattura e' cambiato dopo la prima ricezione" if sha_lotti and sha_fonte
              else "Impossibile verificare l'XML della fattura gia' ricevuta")
    if not anteprima:
        await getattr(db, RECEIPTS).update_one(
            {"source_id": source_id},
            {"$set": {"source_id": source_id, "stato": "conflitto_hash",
                      "nuovo_source_hash": source_hash, "conflitto_verificato": True,
                      "fattura_id": existing.get("id"), "ultimo_controllo": now}},
            upsert=True,
        )
    return {"stato": "conflitto_hash", "fattura_id": existing.get("id"), "motivo": motivo}


@_ingresso_serializzato
async def esegui_sync_gestionale(
    *, anno: int | None = None, massimo: int = 1000, anteprima: bool = False
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ok": True,
        "configurato": True,
        "anteprima": anteprima,
        "anno": anno,
        "totale_fonte": 0,
        "esaminate": 0,
        "importabili": 0,
        "importate": 0,
        "collegate_esistenti": 0,
        "gia_ricevute": 0,
        "arretrato": 0,
        "senza_xml": 0,
        # fornitori che il titolare ha escluso da Lotti: saltati, non errori
        "escluse_fornitore": 0,
        # impronta cambiata solo nei metadati del gestionale, XML identico
        "riallineate": 0,
        # conflitti gia' segnalati per la stessa impronta: restano da vedere,
        # ma non si rileggono a ogni giro (occuperebbero il tetto per sempre)
        "conflitti_noti": 0,
        "non_importabili_noti": 0,
        "senza_identita_fornitore": 0,
        "conflitti": [],
        "errori": [],
    }
    now = datetime.now(timezone.utc).isoformat()
    client = None
    try:
        if _usa_ponte_http():
            timeout = httpx.Timeout(120.0, connect=20.0)
            client = httpx.AsyncClient(timeout=timeout, follow_redirects=True)
            items, total = await _elenco(client, anno)
        else:
            items, total = await _elenco_locale(anno)
        result["totale_fonte"] = total

        # Il tetto `massimo` limita il LAVORO di un giro, non la finestra di
        # fatture che il ponte e' disposto a vedere. Prima si applicava
        # all'elenco intero, che arriva ordinato per data crescente: con 1.444
        # fatture in archivio e un tetto di 1.000, le 444 dal 30/06/2026 in poi
        # non sarebbero MAI entrate in Lotti, e il buco cresceva ogni giorno —
        # senza un errore, senza un alert, solo merce che non arriva.
        # Ora si scartano prima quelle gia' prese, poi si taglia: ogni giro
        # lavora fatture NUOVE, e `arretrato` dice quante restano per il giro
        # dopo, cosi' il ritardo e' un numero che si legge.
        presenti = await _fatture_presenti()
        gia_presi = await _source_id_gia_presi(presenti)
        noti = {
            str(r.get("source_id") or ""): str(r.get("nuovo_source_hash") or "")
            for r in await getattr(db, RECEIPTS).find(
                # solo quelli confermati dalla regola attuale (XML diverso con
                # la fattura in Lotti): i vecchi si riesaminano una volta
                {"stato": "conflitto_hash", "conflitto_verificato": True},
                {"_id": 0, "source_id": 1, "nuovo_source_hash": 1, "fattura_id": 1}
            ).to_list(100000)
            if str(r.get("fattura_id") or "") in presenti
        }
        non_importabili_noti = {
            str(r.get("source_id") or ""): str(r.get("source_hash") or "")
            for r in await getattr(db, RECEIPTS).find(
                {"stato": {"$in": sorted(_STATI_NON_IMPORTABILI)}},
                {"_id": 0, "source_id": 1, "source_hash": 1},
            ).to_list(100000)
        }
        da_prendere = []
        for item in items:
            sid = str(item.get("source_id") or "").strip()
            sh = str(item.get("source_hash") or "").strip()
            if sid and sh and gia_presi.get(sid) == sh:
                result["gia_ricevute"] += 1
                continue
            if sid and sh and noti.get(sid) == sh:
                result["conflitti_noti"] += 1
                continue
            if sid and sh and non_importabili_noti.get(sid) == sh:
                result["non_importabili_noti"] += 1
                continue
            da_prendere.append(item)
        # Un fornitore escluso non entra mai in Lotti: lo si toglie PRIMA del
        # tetto, altrimenti ogni giro rileggeva le stesse fatture escluse,
        # le contava come errore («senza fattura operativa») e non finiva mai.
        # La decisione canonica sta nell'anagrafica ERP (per P.IVA); dove
        # non ha mai deciso vale quella gia' presa in Lotti (per nome).
        from app.services.magazzino_fornitore import carica_decisioni

        decisioni = await carica_decisioni(db_lotti=db)
        da_lavorare = []
        for item in da_prendere:
            if decisioni.escluso(item.get("supplier_vat"), item.get("supplier_name")):
                result["escluse_fornitore"] += 1
                continue
            da_lavorare.append(item)
        result["arretrato"] = max(0, len(da_lavorare) - massimo)
        items = da_lavorare[:massimo]

        for item in items:
            result["esaminate"] += 1
            source_id = str(item.get("source_id") or "").strip()
            source_hash = str(item.get("source_hash") or "").strip()
            if not source_id or not source_hash:
                result["errori"].append("Fattura senza source_id/source_hash")
                continue

            receipt = await getattr(db, RECEIPTS).find_one(
                {"source_id": source_id}, {"_id": 0}
            )
            # Il gestionale arricchisce le fatture (categorie, centri di costo,
            # stato di pagamento) e l'impronta cambia anche se l'XML no.
            # Trattarlo come conflitto bloccava per sempre la fattura, anche
            # quando in Lotti non c'era: 163 fatture alimentari da giugno 2026
            # mai arrivate. Conflitto vero = la fattura e' in Lotti con un XML
            # diverso; se manca si importa, se l'XML e' lo stesso si riallinea.
            try:
                controllo = await _verifica_xml_ricevuto(item, receipt, client=client,
                                                        anteprima=anteprima)
            except Exception as exc:
                result["errori"].append(f"{item.get('invoice_number') or source_id}: {_descrivi(exc)}")
                continue
            if controllo:
                if controllo["stato"] == "riallineata":
                    result["riallineate"] += 1
                elif controllo["stato"] == "errore":
                    result["errori"].append(controllo["motivo"])
                else:
                    result["conflitti"].append({"source_id": source_id,
                                                "numero": item.get("invoice_number"),
                                                "motivo": controllo["motivo"]})
                continue

            existing = await db.fatture.find_one(
                _invoice_query(item),
                {"_id": 0, "id": 1, "prodotti": 1, "xml_raw": 1,
                 "haccp_pipeline_version": 1, "haccp_import_completo": 1},
            )
            if existing and existing.get("haccp_import_completo") is not False and (
                existing.get("prodotti") or existing.get("xml_raw")
                or existing.get("haccp_pipeline_version")
            ):
                result["collegate_esistenti"] += 1
                if not anteprima:
                    relation = {
                        "gestionale_source_id": source_id,
                        "gestionale_source_hash": source_hash,
                        "gestionale_source": item.get("source") or "gestionalecloud",
                        "gestionale_collegata_il": now,
                    }
                    await db.fatture.update_one(_invoice_query(item), {"$set": relation})
                    await getattr(db, RECEIPTS).update_one(
                        {"source_id": source_id},
                        {"$set": {**relation, "source_id": source_id, "source_hash": source_hash,
                                  "stato": "collegata_esistente", "fattura_id": existing.get("id"),
                                  "numero_fattura": item.get("invoice_number"),
                                  "data_fattura": item.get("invoice_date")}},
                        upsert=True,
                    )
                continue

            if not item.get("has_xml") and not item.get("lines"):
                result["senza_xml"] += 1
                if not anteprima:
                    await getattr(db, RECEIPTS).update_one(
                        {"source_id": source_id},
                        {"$set": {
                            "source_id": source_id,
                            "source_hash": source_hash,
                            "stato": "senza_contenuto",
                            "numero_fattura": item.get("invoice_number"),
                            "data_fattura": item.get("invoice_date"),
                            "ultimo_controllo": now,
                        }},
                        upsert=True,
                    )
                continue
            result["importabili"] += 1
            if anteprima:
                continue

            try:
                detail = await _leggi_dettaglio(client, source_id)
                xml_fattura = str(detail.get("xml_raw") or "")
                nome_fornitore = str(
                    detail.get("supplier_name") or item.get("supplier_name") or ""
                ).strip()
                piva_fornitore = str(
                    detail.get("supplier_vat") or item.get("supplier_vat") or ""
                ).strip()
                # Alcuni documenti fiscali generici (per esempio un avviso
                # PagoPA caricato via email) vivono nell'archivio `invoices`
                # con righe e content_hash, ma non sono FatturaElettronica e
                # non hanno un cedente. Non si deve inventare un fornitore ne'
                # ritentarli come errore ogni 15 minuti: restano nel Gestionale
                # e Lotti registra soltanto che non sono importabili.
                if not xml_fattura and not (nome_fornitore or piva_fornitore):
                    result["importabili"] -= 1
                    result["senza_identita_fornitore"] += 1
                    await getattr(db, RECEIPTS).update_one(
                        {"source_id": source_id},
                        {"$set": {
                            "source_id": source_id,
                            "source_hash": source_hash,
                            "stato": "senza_identita_fornitore",
                            "numero_fattura": item.get("invoice_number"),
                            "data_fattura": item.get("invoice_date"),
                            "ultimo_controllo": now,
                        }},
                        upsert=True,
                    )
                    continue
                xml_raw = xml_fattura or _xml_from_projection(detail)
                if not xml_raw:
                    result["senza_xml"] += 1
                    continue
                from app.lotti.routers.fatture import _UF, importa_fattura_xml

                imported = await importa_fattura_xml(
                    [_UF(f"gestionale-{source_id}.xml", xml_raw.encode("utf-8"))],
                    collega_ricette=False,
                )
                if imported.get("errori"):
                    raise RuntimeError("Import operativo incompleto: " + "; ".join(imported["errori"]))
                ids = [i for i in (imported.get("fatture_ids") or []) if i]
                if not ids and imported.get("fatture_saltate_escluse"):
                    result["escluse_fornitore"] += 1
                    continue
                invoice = (
                    await db.fatture.find_one({"id": ids[0]}, {"_id": 0, "id": 1}) if ids
                    else await db.fatture.find_one(_invoice_query(item), {"_id": 0, "id": 1})
                )
                if not invoice:
                    raise RuntimeError(
                        "Import completato senza fattura operativa: "
                        f"{'; '.join(imported.get('errori') or []) or 'nessun esito dal motore'}"
                    )
                relation = {
                    "gestionale_source_id": source_id,
                    "gestionale_source_hash": source_hash,
                    "gestionale_source": item.get("source") or "gestionalecloud",
                    "gestionale_collegata_il": now,
                }
                await db.fatture.update_one({"id": invoice["id"]}, {"$set": relation})
                await getattr(db, RECEIPTS).update_one(
                    {"source_id": source_id},
                    {"$set": {**relation, "source_id": source_id, "source_hash": source_hash,
                              "stato": "importata", "fattura_id": invoice.get("id"),
                              "numero_fattura": item.get("invoice_number"),
                              "data_fattura": item.get("invoice_date"),
                              "esito_import": {
                                  "fatture_processate": imported.get("fatture_processate", 0),
                                  "duplicati": imported.get("fatture_duplicate_saltate", 0),
                              }}},
                    upsert=True,
                )
                result["importate"] += 1
            except Exception as exc:
                result["errori"].append(
                    f"{item.get('invoice_number') or source_id}: {_descrivi(exc)}"
                )

        # Un giro puo' importare decine di fatture. Il collegamento canonico
        # attraversa l'intero ricettario e deve quindi girare una volta sola,
        # dopo che tutti i nuovi prodotti/mapping sono disponibili.
        if result["importate"] and not anteprima:
            try:
                from app.lotti.routers.ricette import collega_ingredienti_canonico

                collegamenti = await collega_ingredienti_canonico()
                result["ingredienti_ricette_collegati"] = collegamenti.get(
                    "ingredienti_collegati", 0
                )
            except Exception as exc:
                result["errori"].append(
                    f"Collegamento ingredienti ricette: {_descrivi(exc)}"
                )
    except Exception as exc:
        result["ok"] = False
        result["errori"].append(f"Lettura fonte GestionaleCloud: {_descrivi(exc)}")
    finally:
        if client is not None:
            await client.aclose()

    result["ok"] = not result["errori"] and not result["conflitti"]
    result["completo"] = result["ok"] and result["arretrato"] == 0
    if not anteprima:
        await db.sistema_stato.update_one(
            {"chiave": "gestionale_fatture_sync"},
            {"$set": {"chiave": "gestionale_fatture_sync", "ultimo_sync": now,
                      "ultimo_esito": result}},
            upsert=True,
        )
    return result


@router.get("/stato")
async def stato_gestionale_fatture():
    stato = await db.sistema_stato.find_one(
        {"chiave": "gestionale_fatture_sync"}, {"_id": 0}
    )
    ricevute = await getattr(db, RECEIPTS).count_documents({})
    return {
        "configurato": configurato(),
        "fonte": "GestionaleCloud",
        "modalita": "http" if _usa_ponte_http() else "interna",
        "database_separati": _usa_ponte_http(),
        "direzione": "GestionaleCloud -> Lotti",
        "ricevute_registrate": ricevute,
        "ultimo_sync": (stato or {}).get("ultimo_sync"),
        "ultimo_esito": (stato or {}).get("ultimo_esito"),
    }


@router.post("/sync")
async def sync_gestionale_fatture(
    anno: int | None = Query(None, ge=2000, le=2100),
    limit: int = Query(1000, ge=1, le=5000),
    anteprima: bool = Query(True),
    _admin=Depends(require_admin),
):
    return await esegui_sync_gestionale(anno=anno, massimo=limit, anteprima=anteprima)


@_ingresso_serializzato
async def alimenta_lotti_da_fattura(source_id: str) -> dict[str, Any]:
    """Porta UNA fattura del gestionale dentro Lotti, subito.

    E' l'aggancio automatico fra l'ingresso dei documenti e il magazzino: una
    fattura XML che entra da Drive deve alimentare Lotti senza aspettare il
    giro dei 15 minuti, e se e' gia' entrata deve rialimentarlo comunque
    (l'import e' idempotente per fornitore + numero + data, quindi non
    duplica).

    Costa una lettura per id piu' l'import di quel solo documento: non e' un
    ripasso dell'archivio, e puo' girare per ogni fattura senza moltiplicare
    il lavoro sul lotto di 25 file del giro Drive.
    """
    esito: dict[str, Any] = {"source_id": source_id, "stato": "saltata"}
    if not source_id:
        esito["motivo"] = "source_id mancante"
        return esito
    try:
        dettaglio = await _dettaglio_locale(source_id)
    except Exception as exc:  # fattura non piu' attiva o non trovata
        esito["motivo"] = _descrivi(exc)
        return esito

    from app.services.magazzino_fornitore import carica_decisioni

    if (await carica_decisioni(db_lotti=db)).escluso(
            dettaglio.get("supplier_vat"), dettaglio.get("supplier_name")):
        esito["motivo"] = "fornitore fuori dal magazzino"
        return esito

    xml_raw = str(dettaglio.get("xml_raw") or "") or _xml_from_projection(dettaglio)
    if not xml_raw:
        esito["motivo"] = "nessun XML ne' righe strutturate"
        return esito

    receipt = await getattr(db, RECEIPTS).find_one({"source_id": source_id}, {"_id": 0})
    controllo = await _verifica_xml_ricevuto(dettaglio, receipt, dettaglio=dettaglio)
    if controllo:
        if controllo["stato"] in {"conflitto_hash", "errore"}:
            esito.update(controllo)
        else:
            esito.update({"stato": "alimentata", "fattura_id": controllo["fattura_id"],
                          "prodotti": 0, "lotti": 0})
        return esito

    from app.lotti.routers.fatture import _UF, importa_fattura_xml

    importata = await importa_fattura_xml([
        _UF(f"gestionale-{source_id}.xml", xml_raw.encode("utf-8"))
    ])
    if importata.get("errori"):
        esito.update({"stato": "errore", "motivo": "Import operativo incompleto: "
                      + "; ".join(importata["errori"])})
        return esito
    now = datetime.now(timezone.utc).isoformat()
    relazione = {
        "gestionale_source_id": source_id,
        "gestionale_source_hash": dettaglio.get("source_hash", ""),
        "gestionale_source": "gestionalecloud",
        "gestionale_collegata_il": now,
    }
    if importata.get("fatture_saltate_escluse") and not importata.get("fatture_ids"):
        esito["motivo"] = "fornitore escluso da Lotti"
        return esito
    ids = [i for i in (importata.get("fatture_ids") or []) if i]
    fattura = (
        await db.fatture.find_one({"id": ids[0]}, {"_id": 0, "id": 1}) if ids
        else await db.fatture.find_one(_invoice_query(dettaglio), {"_id": 0, "id": 1})
    )
    if not fattura:
        # L'importatore puo' restituire errori senza sollevare: dichiararlo
        # importato creava una ricevuta senza fattura che il giro successivo
        # saltava per sempre, lasciando il magazzino privo della merce.
        esito.update({
            "stato": "errore",
            "motivo": "Import completato senza fattura operativa: "
                      + ("; ".join(importata.get("errori") or []) or "nessun esito dal motore"),
        })
        return esito
    await db.fatture.update_one({"id": fattura["id"]}, {"$set": relazione})
    await getattr(db, RECEIPTS).update_one(
        {"source_id": source_id},
        {"$set": {**relazione, "source_id": source_id,
                  "source_hash": dettaglio.get("source_hash", ""),
                  "stato": "importata",
                  "fattura_id": (fattura or {}).get("id"),
                  "numero_fattura": dettaglio.get("invoice_number"),
                  "data_fattura": dettaglio.get("invoice_date"),
                  "esito_import": {
                      "fatture_processate": importata.get("fatture_processate", 0),
                      "duplicati": importata.get("fatture_duplicate_saltate", 0),
                  }}},
        upsert=True,
    )
    esito.update({
        "stato": "alimentata",
        "fattura_id": (fattura or {}).get("id"),
        "prodotti": importata.get("prodotti_trovati", 0),
        "lotti": importata.get("nuove_materie", 0),
    })
    return esito
