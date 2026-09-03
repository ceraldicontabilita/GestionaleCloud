"""Bonifica dei doppioni di Prima Nota Banca degli assegni (PR 3).

Audit del commercialista 03/09/2026 (memoria/AUDIT_COMMERCIALISTA_2026-09-03.md
§1): quattro assegni (0208770633 318,66 / 0208770634 1.403,01 / 0208770636
2.496,33 / 0208770637 636,00 = 4.853,99 EUR) registrati DUE volte in Prima
Nota Banca per lo stesso ``estratto_conto_id``: stessa fonte
``assegno_estratto_conto``, ``created_at`` 29/08 14:07 e 14:33. Due processi
con cache diverse hanno superato entrambi la guardia in memoria di
``assegni_estratto_conto._garantisci_prima_nota``.

Stesso contratto della bonifica dei corrispettivi
(``app/services/bonifica_prima_nota_doppioni.py``), registro logico
``banca_assegni``:

- ``analizza(db)`` e' un dry-run puro: raggruppa le righe ATTIVE per la
  chiave deterministica ``chiave_idempotenza_assegno`` (``assegno:<ec_id>:
  banca_uscita``), tiene la piu' VECCHIA per ``created_at`` e propone le altre;
- ``applica(db)`` MARCA soltanto (``entity_status``/``status`` = ``deleted``,
  ``duplicate_of``, ``deleted_reason``, ``deleted_at``): nessuna cancellazione
  fisica, mai. Assegna ``idempotency_key`` alla riga tenuta, alle marcate e
  alle righe singole ancora senza chiave;
- i riferimenti che puntavano alla copia marcata (``assegni.prima_nota_banca_id``,
  ``estratto_conto_movimenti.prima_nota_banca_id``, ``invoices.prima_nota_id``
  / ``prima_nota_banca_id``) tornano sulla riga tenuta.

E' esposta dallo STESSO endpoint admin della bonifica corrispettivi
(``POST /api/admin/bonifica-prima-nota-doppioni?dry_run=``), che unisce i due
esiti con ``integra_nel_report``; niente secondo endpoint.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.services.assegni_estratto_conto import chiave_idempotenza_assegno
from app.services.bonifica_prima_nota_doppioni import (
    _importo,
    _ordine,
    _pubblica,
    _righe_attive,
    _selettore,
    _sintesi,
)
from app.services.scritture_contabili import _batch_scritture_registro

logger = logging.getLogger(__name__)

MOTIVO_BONIFICA = "bonifica_doppioni_assegni_2026-09-03"
COLLECTION = "prima_nota_banca"
REGISTRO = "banca_assegni"


def _estratto_conto_id(riga: Dict[str, Any]) -> str:
    return str(
        riga.get("estratto_conto_id") or riga.get("movimento_estratto_conto_id") or ""
    ).strip()


def classifica_riga(riga: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """``(registro_logico, idempotency_key)`` della riga, o ``(None, None)``.

    Solo le uscite banca prodotte dal riscontro di un assegno in estratto
    conto hanno questa identita': servono il movimento di estratto conto e
    la natura "assegno" (``assegno_id``, fonte ``assegno_estratto_conto`` o
    categoria ``Assegni``). Il resto della Prima Nota non viene toccato.
    """
    ec_id = _estratto_conto_id(riga)
    if not ec_id:
        return None, None
    source = str(riga.get("source") or "").strip().lower()
    categoria = str(riga.get("categoria") or riga.get("category") or "").strip()
    e_assegno = bool(riga.get("assegno_id")) or source == "assegno_estratto_conto" or categoria == "Assegni"
    if not e_assegno:
        return None, None
    return REGISTRO, chiave_idempotenza_assegno(ec_id)


async def analizza(db) -> Dict[str, Any]:
    """Dry-run: cosa verrebbe marcato, con importi e coppie."""
    registro = {"gruppi": 0, "righe_da_marcare": 0, "importo_doppio": 0.0,
                "righe_attive": 0, "righe_senza_chiave": 0}
    gruppi: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for riga in await _righe_attive(db, COLLECTION):
        registro_logico, chiave = classifica_riga(riga)
        if not chiave or not registro_logico:
            continue
        gruppi[chiave].append(riga)
        registro["righe_attive"] += 1
        if riga.get("idempotency_key") != chiave:
            registro["righe_senza_chiave"] += 1

    coppie: List[Dict[str, Any]] = []
    singole_senza_chiave: List[Dict[str, Any]] = []
    for chiave, righe in gruppi.items():
        righe.sort(key=_ordine)
        tenuta, marcate = righe[0], righe[1:]
        if not marcate:
            if tenuta.get("idempotency_key") != chiave:
                singole_senza_chiave.append({
                    "collection": COLLECTION, "chiave": chiave,
                    "registro": REGISTRO, "riga": tenuta,
                })
            continue
        registro["gruppi"] += 1
        registro["righe_da_marcare"] += len(marcate)
        registro["importo_doppio"] = round(
            registro["importo_doppio"] + sum(_importo(r) for r in marcate), 2)
        coppie.append({
            "collection": COLLECTION,
            "registro": REGISTRO,
            "chiave": chiave,
            "estratto_conto_id": _estratto_conto_id(tenuta),
            "assegno_id": tenuta.get("assegno_id"),
            "assegno_numero": tenuta.get("assegno_numero") or tenuta.get("numero_assegno"),
            "data": tenuta.get("data") or tenuta.get("date"),
            "tenuta": _sintesi(tenuta),
            "marcate": [_sintesi(r) for r in marcate],
            "_tenuta": tenuta,
            "_marcate": marcate,
        })

    coppie.sort(key=lambda c: (str(c["data"]), c["chiave"]))
    return {
        "dry_run": True,
        "motivo": MOTIVO_BONIFICA,
        "registri": {REGISTRO: registro},
        "totale_gruppi": registro["gruppi"],
        "totale_righe_da_marcare": registro["righe_da_marcare"],
        "totale_importo_doppio": registro["importo_doppio"],
        "righe_singole_senza_chiave": len(singole_senza_chiave),
        "coppie": coppie,
        "_singole_senza_chiave": singole_senza_chiave,
    }


async def _riallinea_riferimenti(
    db, coppia: Dict[str, Any], id_tenuta: Optional[str], ids_marcate: set,
) -> int:
    """Assegno, movimento EC e fattura non devono puntare alla copia marcata."""
    if not id_tenuta:
        return 0
    riallineati = 0
    tenuta = coppia["_tenuta"]
    ec_id = _estratto_conto_id(tenuta)
    assegno_id = tenuta.get("assegno_id")
    fattura_ids = [
        str(v) for v in (
            tenuta.get("fattura_id"), tenuta.get("invoice_id"),
            *(tenuta.get("fattura_ids") or []),
        ) if v
    ]

    async def _sposta(collection: str, selettore: Dict[str, Any], campi: Tuple[str, ...]) -> None:
        nonlocal riallineati
        doc = await db[collection].find_one(selettore)
        if not doc:
            return
        aggiornamenti = {
            campo: id_tenuta for campo in campi if doc.get(campo) in ids_marcate
        }
        if aggiornamenti:
            await db[collection].update_one(selettore, {"$set": aggiornamenti})
            riallineati += 1

    if assegno_id:
        await _sposta("assegni", {"id": assegno_id}, ("prima_nota_banca_id",))
    if ec_id:
        await _sposta("estratto_conto_movimenti", {"id": ec_id}, ("prima_nota_banca_id",))
    for fattura_id in dict.fromkeys(fattura_ids):
        await _sposta("invoices", {"id": fattura_id}, ("prima_nota_id", "prima_nota_banca_id"))
    return riallineati


async def applica(db, actor: Optional[str] = None) -> Dict[str, Any]:
    """Marca le copie piu' recenti e assegna le chiavi. Mai cancellazioni."""
    analisi = await analizza(db)
    adesso = datetime.now(timezone.utc).isoformat()
    marcate = 0
    chiavi_assegnate = 0
    riferimenti_riallineati = 0

    async with _batch_scritture_registro(db):
        for coppia in analisi["coppie"]:
            tenuta = coppia["_tenuta"]
            chiave = coppia["chiave"]
            id_tenuta = tenuta.get("id") or tenuta.get("_id")
            ids_marcate = set()
            for riga in coppia["_marcate"]:
                await db[COLLECTION].update_one(_selettore(riga), {"$set": {
                    "entity_status": "deleted",
                    "status": "deleted",
                    "deleted": True,
                    "duplicate_of": id_tenuta,
                    "deleted_reason": MOTIVO_BONIFICA,
                    "deleted_at": adesso,
                    "idempotency_key": chiave,
                    "updated_at": adesso,
                }})
                marcate += 1
                ids_marcate.update({riga.get("id"), riga.get("_id")})
            if tenuta.get("idempotency_key") != chiave:
                await db[COLLECTION].update_one(
                    _selettore(tenuta), {"$set": {"idempotency_key": chiave, "updated_at": adesso}},
                )
                chiavi_assegnate += 1
            riferimenti_riallineati += await _riallinea_riferimenti(
                db, coppia, id_tenuta, ids_marcate)

        for voce in analisi["_singole_senza_chiave"]:
            await db[COLLECTION].update_one(
                _selettore(voce["riga"]),
                {"$set": {"idempotency_key": voce["chiave"], "updated_at": adesso}},
            )
            chiavi_assegnate += 1

    esito = _pubblica(analisi)
    esito.update({
        "dry_run": False,
        "eseguita_at": adesso,
        "righe_marcate": {REGISTRO: marcate},
        "totale_righe_marcate": marcate,
        "chiavi_assegnate": chiavi_assegnate,
        "riferimenti_riallineati": riferimenti_riallineati,
    })
    try:
        await db["prima_nota_migrazioni_audit"].insert_one({
            "id": str(uuid.uuid4()),
            "migrazione": MOTIVO_BONIFICA,
            "actor": actor or "sistema",
            "created_at": adesso,
            "risultato": {k: v for k, v in esito.items() if k != "coppie"},
            "coppie": [
                {"collection": c["collection"], "chiave": c["chiave"],
                 "tenuta": c["tenuta"]["id"], "marcate": [m["id"] for m in c["marcate"]]}
                for c in esito["coppie"]
            ],
        })
    except Exception:  # pragma: no cover - l'audit non deve bloccare la bonifica
        logger.exception("Audit della bonifica doppioni assegni non scritto")
    logger.warning(
        "[bonifica doppioni assegni] marcate %s righe, chiavi assegnate %s, riferimenti riallineati %s",
        marcate, chiavi_assegnate, riferimenti_riallineati,
    )
    return esito


async def esegui(db, dry_run: bool = True, actor: Optional[str] = None) -> Dict[str, Any]:
    """Punto unico per endpoint e CLI."""
    if dry_run:
        return _pubblica(await analizza(db))
    return await applica(db, actor=actor)


def integra_nel_report(esito_corrispettivi: Dict[str, Any], esito_assegni: Dict[str, Any]) -> Dict[str, Any]:
    """Un solo report per l'endpoint admin: registri, coppie e totali uniti."""
    esito = dict(esito_corrispettivi)
    esito["registri"] = {**esito_corrispettivi.get("registri", {}), **esito_assegni.get("registri", {})}
    esito["coppie"] = list(esito_corrispettivi.get("coppie", [])) + list(esito_assegni.get("coppie", []))
    esito["motivo_assegni"] = esito_assegni.get("motivo")
    for campo in ("totale_gruppi", "totale_righe_da_marcare", "righe_singole_senza_chiave"):
        esito[campo] = int(esito_corrispettivi.get(campo) or 0) + int(esito_assegni.get(campo) or 0)
    esito["totale_importo_doppio"] = round(
        float(esito_corrispettivi.get("totale_importo_doppio") or 0)
        + float(esito_assegni.get("totale_importo_doppio") or 0), 2)
    if not esito.get("dry_run", True):
        esito["righe_marcate"] = {
            **esito_corrispettivi.get("righe_marcate", {}), **esito_assegni.get("righe_marcate", {}),
        }
        for campo in ("totale_righe_marcate", "chiavi_assegnate"):
            esito[campo] = int(esito_corrispettivi.get(campo) or 0) + int(esito_assegni.get(campo) or 0)
        esito["riferimenti_riallineati"] = int(esito_assegni.get("riferimenti_riallineati") or 0)
    return esito


# ── CLI ──────────────────────────────────────────────────────────────────────

async def _main_async(dry_run: bool) -> Dict[str, Any]:
    from app.database import Database

    await Database.connect_db()
    try:
        return await esegui(Database.get_db(), dry_run=dry_run, actor="cli")
    finally:
        await Database.close_db()


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Bonifica dei doppioni di Prima Nota Banca degli assegni (stesso estratto_conto_id).",
    )
    parser.add_argument("--applica", action="store_true",
                        help="marca davvero le copie (default: solo analisi)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    risultato = asyncio.run(_main_async(dry_run=not args.applica))
    print(json.dumps(risultato, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
