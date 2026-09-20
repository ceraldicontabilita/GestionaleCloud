"""Ponte unidirezionale GestionaleCloud -> Lotti per le fatture ricevute.

GestionaleCloud resta proprietario del documento contabile. Lotti conserva solo
la copia operativa necessaria a lotti, tracciabilita, prezzi e magazzino, insieme
all'identificativo e all'hash della fonte. Il registro ricevute rende ogni giro
idempotente e blocca automaticamente una sorgente cambiata dopo l'importazione.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote
from xml.sax.saxutils import escape

import httpx
from fastapi import APIRouter, Depends, Query

from app.lotti.auth import require_admin
from app.lotti.db import database as db


router = APIRouter(prefix="/gestionale-fatture", tags=["GestionaleCloud Fatture"])
RECEIPTS = "gestionale_fatture_ricevute"


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
    number = str(item.get("invoice_number") or "").strip()
    vat = str(item.get("supplier_vat") or "").strip()
    if vat:
        return {"numero_fattura": number, "piva": vat}
    date = str(item.get("invoice_date") or "").strip()
    if len(date) >= 10 and date[4:5] == "-":
        date = f"{date[8:10]}/{date[5:7]}/{date[:4]}"
    return {
        "numero_fattura": number,
        "fornitore": str(item.get("supplier_name") or "").strip(),
        "data_fattura": date,
    }


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


async def _source_id_gia_presi() -> dict[str, str]:
    """`source_id` -> `source_hash` delle fatture gia' prese in carico.

    Solo gli stati terminali: un `conflitto_hash` deve essere riesaminato ogni
    giro, non saltato."""
    righe = await getattr(db, RECEIPTS).find(
        {"stato": {"$in": ["importata", "collegata_esistente"]}},
        {"_id": 0, "source_id": 1, "source_hash": 1},
    ).to_list(100000)
    return {
        str(r.get("source_id") or ""): str(r.get("source_hash") or "")
        for r in righe if r.get("source_id")
    }


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
        gia_presi = await _source_id_gia_presi()
        da_prendere = []
        for item in items:
            sid = str(item.get("source_id") or "").strip()
            sh = str(item.get("source_hash") or "").strip()
            if sid and sh and gia_presi.get(sid) == sh:
                result["gia_ricevute"] += 1
                continue
            da_prendere.append(item)
        result["arretrato"] = max(0, len(da_prendere) - massimo)
        items = da_prendere[:massimo]

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
            if receipt:
                if receipt.get("source_hash") == source_hash and receipt.get("stato") in {
                    "importata", "collegata_esistente"
                }:
                    result["gia_ricevute"] += 1
                    continue
                result["conflitti"].append({
                    "source_id": source_id,
                    "numero": item.get("invoice_number"),
                    "motivo": "La fattura sorgente e cambiata dopo la prima ricezione",
                })
                if not anteprima:
                    await getattr(db, RECEIPTS).update_one(
                        {"source_id": source_id},
                        {"$set": {"stato": "conflitto_hash", "nuovo_source_hash": source_hash,
                                  "ultimo_controllo": now}},
                    )
                continue

            existing = await db.fatture.find_one(
                _invoice_query(item),
                {"_id": 0, "id": 1, "prodotti": 1, "xml_raw": 1,
                 "haccp_pipeline_version": 1},
            )
            if existing and (
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
                continue
            result["importabili"] += 1
            if anteprima:
                continue

            try:
                if client is not None:
                    detail = await _get_json(
                        client,
                        f"/api/integrations/lotti/invoices/{quote(source_id, safe='')}",
                    )
                else:
                    detail = await _dettaglio_locale(source_id)
                if detail.get("source_hash") != source_hash:
                    result["conflitti"].append({
                        "source_id": source_id,
                        "numero": item.get("invoice_number"),
                        "motivo": "Hash elenco e dettaglio non coincidono",
                    })
                    continue
                xml_raw = str(detail.get("xml_raw") or "") or _xml_from_projection(detail)
                if not xml_raw:
                    result["senza_xml"] += 1
                    continue
                from app.lotti.routers.fatture import _UF, importa_fattura_xml

                imported = await importa_fattura_xml([
                    _UF(f"gestionale-{source_id}.xml", xml_raw.encode("utf-8"))
                ])
                invoice = await db.fatture.find_one(
                    _invoice_query(item), {"_id": 0, "id": 1}
                )
                if not invoice:
                    raise RuntimeError("Import completato senza fattura operativa")
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
    except Exception as exc:
        result["ok"] = False
        result["errori"].append(f"Lettura fonte GestionaleCloud: {_descrivi(exc)}")
    finally:
        if client is not None:
            await client.aclose()

    result["ok"] = not result["errori"] and not result["conflitti"]
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
