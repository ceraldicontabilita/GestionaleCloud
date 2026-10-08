"""Bonifica dei doppioni di Prima Nota derivati dai corrispettivi (PR 5).

Audit del commercialista 03/09/2026 (memoria/AUDIT_COMMERCIALISTA_2026-09-03.md
§2): 77 giornate con corrispettivo registrato due volte in Prima Nota Cassa
(+217.025,64 €), 58 uscite POS doppie in Cassa (+108.275,48 €), 56 crediti
POS doppi in Prima Nota Banca (+105.428,88 €). Stesso ``corrispettivo_id``,
stessa matricola, stesso ``source``, ``created_at`` diversi: due processi con
cache diverse hanno scritto entrambi la stessa giornata.

Regole:

- ``analizza(db)`` e' un dry-run puro: raggruppa le righe ATTIVE per la
  chiave deterministica della scrittura (``chiave_idempotenza_corrispettivo``:
  collezione + corrispettivo + tipo entrata/uscita + gestore), tiene la piu'
  VECCHIA per ``created_at`` e propone le altre;
- ``applica(db)`` MARCA soltanto (``entity_status="deleted"``, ``status=
  "deleted"``, ``duplicate_of``, ``deleted_reason``, ``deleted_at``): nessuna
  cancellazione fisica, mai. Assegna ``idempotency_key`` alla riga tenuta,
  a quelle marcate e alle righe singole ancora senza chiave, cosi' l'indice
  unico di Postgres (supabase/migrations/20260903_idempotency_key.sql) puo'
  essere creato e protegge anche lo storico;
- se il corrispettivo puntava alla copia marcata (``prima_nota_cassa_id`` /
  ``prima_nota_banca_id``), il riferimento viene riportato sulla riga tenuta.

Le letture di Prima Nota (``routers/prima_nota_module``, bilancio, dashboard)
filtrano ``status`` in ("deleted", "archived"); il motore contabile filtra
anche ``entity_status``: per questo si marcano ENTRAMBI i campi.
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

from app.services import conti_pos
from app.services.scritture_contabili import (
    FILTRO_MOVIMENTO_ATTIVO,
    _batch_scritture_registro,
    chiave_idempotenza_corrispettivo,
    normalizza_gestore_pos,
)

logger = logging.getLogger(__name__)

MOTIVO_BONIFICA = "bonifica_doppioni_2026-09-03"
COLLEZIONI = ("prima_nota_cassa", "prima_nota_banca")
REGISTRI_LOGICI = ("cassa_entrate", "cassa_uscite_pos", "banca_crediti_pos")
_REGISTRO_PER_TIPO = {
    "cassa_entrata": "cassa_entrate",
    "cassa_uscita": "cassa_uscite_pos",
    "banca_credito": "banca_crediti_pos",
}


def _gestore_riga(riga: Dict[str, Any]) -> str:
    """Gestore del circuito, letto dal campo o dedotto dalla categoria storica.

    Le righe scritte prima del 07/08/2026 non hanno ``gestore`` e la loro
    categoria e' quella indistinta ("POS Verso Banca"): appartengono tutte a
    NUMIA, come stabilisce ``filtro_gestore_pos``.
    """
    gestore = str(riga.get("gestore") or "").strip()
    if gestore:
        return normalizza_gestore_pos(gestore)
    categoria = str(riga.get("categoria") or riga.get("category") or "")
    for circuito, sigla in conti_pos.SIGLE.items():
        if categoria == conti_pos.categoria_uscita_pos(circuito) or sigla in categoria.upper().split():
            return circuito
    return normalizza_gestore_pos(None)


def classifica_riga(collection: str, riga: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """``(registro_logico, idempotency_key)`` della riga, o ``(None, None)``.

    Solo le tre scritture derivate da un corrispettivo hanno un'identita'
    deterministica; tutto il resto (versamenti, fatture, stipendi...) non
    viene toccato dalla bonifica.
    """
    corr_id = str(riga.get("corrispettivo_id") or "").strip()
    if not corr_id:
        return None, None
    tipo = str(riga.get("tipo") or riga.get("type") or "").strip().lower()
    categoria = str(riga.get("categoria") or riga.get("category") or "").strip()
    source = str(riga.get("source") or "").strip().lower()
    if collection == "prima_nota_cassa" and tipo == "entrata" and categoria == "Corrispettivi":
        return "cassa_entrate", chiave_idempotenza_corrispettivo(corr_id, "cassa_entrata")
    if collection == "prima_nota_cassa" and tipo == "uscita" and categoria in conti_pos.CATEGORIE_USCITA_POS:
        return "cassa_uscite_pos", chiave_idempotenza_corrispettivo(
            corr_id, "cassa_uscita", _gestore_riga(riga))
    if collection == "prima_nota_banca" and tipo == "entrata" and (
        categoria == "Corrispettivi POS" or source == "trasferimento_pos"
    ):
        return "banca_crediti_pos", chiave_idempotenza_corrispettivo(
            corr_id, "banca_credito", _gestore_riga(riga))
    return None, None


def _ordine(riga: Dict[str, Any]) -> Tuple[str, str]:
    """La riga piu' vecchia e' quella originale; senza data va in coda."""
    return (str(riga.get("created_at") or "9999"), str(riga.get("id") or riga.get("_id") or ""))


def _importo(riga: Dict[str, Any]) -> float:
    try:
        return round(float(riga.get("importo") or riga.get("amount") or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def _sintesi(riga: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": riga.get("id"),
        "_id": riga.get("_id"),
        "created_at": riga.get("created_at"),
        "importo": _importo(riga),
        "source": riga.get("source"),
        "idempotency_key": riga.get("idempotency_key"),
    }


def _selettore(riga: Dict[str, Any]) -> Dict[str, Any]:
    if riga.get("_id") is not None:
        return {"_id": riga["_id"]}
    return {"id": riga.get("id")}


async def _righe_attive(db, collection: str) -> List[Dict[str, Any]]:
    cursor = db[collection].find(dict(FILTRO_MOVIMENTO_ATTIVO))
    if hasattr(cursor, "to_list"):
        return await cursor.to_list(None)
    return [riga async for riga in cursor]


async def analizza(db) -> Dict[str, Any]:
    """Dry-run: cosa verrebbe marcato, per registro, con importi e coppie."""
    registri = {
        nome: {"gruppi": 0, "righe_da_marcare": 0, "importo_doppio": 0.0,
               "righe_attive": 0, "righe_senza_chiave": 0}
        for nome in REGISTRI_LOGICI
    }
    coppie: List[Dict[str, Any]] = []
    non_classificate = 0
    singole_senza_chiave: List[Dict[str, Any]] = []

    for collection in COLLEZIONI:
        gruppi: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        registro_di: Dict[str, str] = {}
        for riga in await _righe_attive(db, collection):
            registro, chiave = classifica_riga(collection, riga)
            if not chiave or not registro:
                if riga.get("corrispettivo_id"):
                    non_classificate += 1
                continue
            gruppi[chiave].append(riga)
            registro_di[chiave] = registro
            registri[registro]["righe_attive"] += 1
            if riga.get("idempotency_key") != chiave:
                registri[registro]["righe_senza_chiave"] += 1

        for chiave, righe in gruppi.items():
            registro = registro_di[chiave]
            righe.sort(key=_ordine)
            tenuta, marcate = righe[0], righe[1:]
            if not marcate:
                if tenuta.get("idempotency_key") != chiave:
                    singole_senza_chiave.append({
                        "collection": collection, "chiave": chiave,
                        "registro": registro, "riga": tenuta,
                    })
                continue
            registri[registro]["gruppi"] += 1
            registri[registro]["righe_da_marcare"] += len(marcate)
            registri[registro]["importo_doppio"] = round(
                registri[registro]["importo_doppio"] + sum(_importo(r) for r in marcate), 2)
            coppie.append({
                "collection": collection,
                "registro": registro,
                "chiave": chiave,
                "corrispettivo_id": tenuta.get("corrispettivo_id"),
                "data": tenuta.get("data") or tenuta.get("date"),
                "gestore": tenuta.get("gestore"),
                "tenuta": _sintesi(tenuta),
                "marcate": [_sintesi(r) for r in marcate],
                # servono ad ``applica``; non entrano nella risposta HTTP
                "_tenuta": tenuta,
                "_marcate": marcate,
            })

    coppie.sort(key=lambda c: (c["collection"], str(c["data"]), c["chiave"]))
    return {
        "dry_run": True,
        "motivo": MOTIVO_BONIFICA,
        "registri": registri,
        "totale_gruppi": sum(r["gruppi"] for r in registri.values()),
        "totale_righe_da_marcare": sum(r["righe_da_marcare"] for r in registri.values()),
        "totale_importo_doppio": round(sum(r["importo_doppio"] for r in registri.values()), 2),
        "righe_singole_senza_chiave": len(singole_senza_chiave),
        "righe_con_corrispettivo_non_classificate": non_classificate,
        "coppie": coppie,
        "_singole_senza_chiave": singole_senza_chiave,
    }


def _pubblica(analisi: Dict[str, Any]) -> Dict[str, Any]:
    """Toglie i documenti completi, tenuti solo per ``applica``."""
    esito = {k: v for k, v in analisi.items() if not k.startswith("_")}
    esito["coppie"] = [
        {k: v for k, v in coppia.items() if not k.startswith("_")}
        for coppia in analisi.get("coppie", [])
    ]
    return esito


async def _riallinea_corrispettivo(
    db, coppia: Dict[str, Any], id_tenuta: Optional[str], ids_marcate: set,
) -> int:
    """Se il corrispettivo puntava a una copia marcata, torna sulla tenuta."""
    corr_id = coppia.get("corrispettivo_id")
    if not corr_id or not id_tenuta:
        return 0
    campo = {"cassa_entrate": "prima_nota_cassa_id",
             "banca_crediti_pos": "prima_nota_banca_id"}.get(coppia["registro"])
    if not campo:
        return 0
    corr = await db["corrispettivi"].find_one({"id": corr_id})
    if not corr:
        return 0
    aggiornamenti: Dict[str, Any] = {}
    if corr.get(campo) in ids_marcate:
        aggiornamenti[campo] = id_tenuta
    if corr.get("prima_nota_id") in ids_marcate:
        aggiornamenti["prima_nota_id"] = id_tenuta
    if not aggiornamenti:
        return 0
    await db["corrispettivi"].update_one({"id": corr_id}, {"$set": aggiornamenti})
    return 1


async def applica(db, actor: Optional[str] = None) -> Dict[str, Any]:
    """Marca le copie piu' recenti e assegna le chiavi. Mai cancellazioni."""
    analisi = await analizza(db)
    adesso = datetime.now(timezone.utc).isoformat()
    marcate_per_registro = {nome: 0 for nome in REGISTRI_LOGICI}
    chiavi_assegnate = 0
    corrispettivi_riallineati = 0

    async with _batch_scritture_registro(db):
        for coppia in analisi["coppie"]:
            tenuta = coppia["_tenuta"]
            chiave = coppia["chiave"]
            id_tenuta = tenuta.get("id") or tenuta.get("_id")
            ids_marcate = set()
            # Prima le copie: diventano inattive e la chiave, condivisa con la
            # riga tenuta, non viola l'indice parziale (solo righe attive).
            for riga in coppia["_marcate"]:
                await db[coppia["collection"]].update_one(_selettore(riga), {"$set": {
                    "entity_status": "deleted",
                    "status": "deleted",
                    "deleted": True,
                    "duplicate_of": id_tenuta,
                    "deleted_reason": MOTIVO_BONIFICA,
                    "deleted_at": adesso,
                    "idempotency_key": chiave,
                    "updated_at": adesso,
                }})
                marcate_per_registro[coppia["registro"]] += 1
                ids_marcate.update({riga.get("id"), riga.get("_id")})
            if tenuta.get("idempotency_key") != chiave:
                await db[coppia["collection"]].update_one(
                    _selettore(tenuta), {"$set": {"idempotency_key": chiave, "updated_at": adesso}},
                )
                chiavi_assegnate += 1
            corrispettivi_riallineati += await _riallinea_corrispettivo(
                db, coppia, id_tenuta, ids_marcate)

        for voce in analisi["_singole_senza_chiave"]:
            await db[voce["collection"]].update_one(
                _selettore(voce["riga"]),
                {"$set": {"idempotency_key": voce["chiave"], "updated_at": adesso}},
            )
            chiavi_assegnate += 1

    esito = _pubblica(analisi)
    esito.update({
        "dry_run": False,
        "eseguita_at": adesso,
        "righe_marcate": marcate_per_registro,
        "totale_righe_marcate": sum(marcate_per_registro.values()),
        "chiavi_assegnate": chiavi_assegnate,
        "corrispettivi_riallineati": corrispettivi_riallineati,
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
        logger.exception("Audit della bonifica doppioni non scritto")
    logger.warning(
        "[bonifica doppioni] marcate %s righe (%s), chiavi assegnate %s, corrispettivi riallineati %s",
        esito["totale_righe_marcate"], marcate_per_registro, chiavi_assegnate,
        corrispettivi_riallineati,
    )
    return esito


async def esegui(db, dry_run: bool = True, actor: Optional[str] = None) -> Dict[str, Any]:
    """Punto unico per endpoint e CLI."""
    if dry_run:
        return _pubblica(await analizza(db))
    return await applica(db, actor=actor)


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
        description="Bonifica dei doppioni di Prima Nota derivati dai corrispettivi.",
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
