"""Backfill dei conti CEE sulle righe di Prima Nota senza `conto_contabile` (PR 7).

Audit del commercialista 03/09/2026 (memoria/AUDIT_COMMERCIALISTA_2026-09-03.md
§2): 117 righe di Prima Nota Banca senza conto (Fatture 25, Stipendi 48,
Assegni 23, Pagamento PayPal 12, Commissioni 9) e tutte le righe di Cassa
(corrispettivi, uscite POS) senza conto: registrazioni che nessun bilancio
di verifica puo' collocare.

Regole:

- ``analizza(db)`` e' un dry-run puro: per ogni riga ATTIVA dei due registri
  calcola con ``mapping_piano_conti.completa_conti_prima_nota`` i SOLI campi
  mancanti (``conto_contabile`` di tesoreria, ``conto_contropartita`` per
  categoria, descrizioni) e riporta i conteggi per registro e categoria;
- ``applica(db)`` scrive quei campi con ``$set``: non tocca importi, date,
  categorie o stati; una riga la cui categoria non ha una contropartita
  nota riceve il conto di tesoreria e ``contropartita_da_classificare``,
  mai un conto inventato;
- idempotente: al secondo giro non c'e' nulla da aggiornare.
"""
from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.services.mapping_piano_conti import completa_conti_prima_nota
from app.services.scritture_contabili import (
    FILTRO_MOVIMENTO_ATTIVO,
    REGISTRI,
    _batch_scritture_registro,
)

logger = logging.getLogger(__name__)

MOTIVO_BONIFICA = "bonifica_conti_prima_nota_2026-09-03"


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
    """Dry-run: quante righe riceverebbero quali conti, per registro/categoria."""
    registri: Dict[str, Dict[str, Any]] = {}
    aggiornamenti: List[Dict[str, Any]] = []
    non_classificabili: List[Dict[str, Any]] = []
    for registro, collection in REGISTRI.items():
        conteggio = {
            "righe_attive": 0, "righe_da_aggiornare": 0,
            "senza_conto_contabile": 0, "senza_contropartita": 0,
            "contropartita_da_classificare": 0, "conti_non_validi": 0,
            "per_categoria": defaultdict(int),
        }
        for riga in await _righe_attive(db, collection):
            conteggio["righe_attive"] += 1
            try:
                campi = completa_conti_prima_nota(registro, riga)
            except ValueError as exc:
                conteggio["conti_non_validi"] += 1
                non_classificabili.append({
                    "collection": collection, "id": riga.get("id"),
                    "categoria": riga.get("categoria"), "motivo": str(exc),
                })
                continue
            if not campi:
                continue
            conteggio["righe_da_aggiornare"] += 1
            conteggio["per_categoria"][str(riga.get("categoria") or "")] += 1
            if "conto_contabile" in campi:
                conteggio["senza_conto_contabile"] += 1
            if "conto_contropartita" in campi:
                conteggio["senza_contropartita"] += 1
            if campi.get("contropartita_da_classificare"):
                conteggio["contropartita_da_classificare"] += 1
            aggiornamenti.append({
                "collection": collection, "id": riga.get("id"),
                "categoria": riga.get("categoria"), "campi": campi,
                "_riga": riga,
            })
        conteggio["per_categoria"] = dict(conteggio["per_categoria"])
        registri[registro] = conteggio
    return {
        "dry_run": True,
        "motivo": MOTIVO_BONIFICA,
        "registri": registri,
        "totale_righe_da_aggiornare": len(aggiornamenti),
        "totale_conti_non_validi": len(non_classificabili),
        "conti_non_validi": non_classificabili[:50],
        "esempi": [
            {k: v for k, v in voce.items() if not k.startswith("_")}
            for voce in aggiornamenti[:20]
        ],
        "_aggiornamenti": aggiornamenti,
    }


def _pubblica(analisi: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in analisi.items() if not k.startswith("_")}


async def applica(db, actor: Optional[str] = None) -> Dict[str, Any]:
    """Assegna i soli campi conto mancanti. Importi e stati restano intatti."""
    analisi = await analizza(db)
    adesso = datetime.now(timezone.utc).isoformat()
    aggiornate = 0
    async with _batch_scritture_registro(db):
        for voce in analisi["_aggiornamenti"]:
            await db[voce["collection"]].update_one(
                _selettore(voce["_riga"]),
                {"$set": {**voce["campi"], "conti_assegnati_da": MOTIVO_BONIFICA,
                          "updated_at": adesso}},
            )
            aggiornate += 1
    esito = _pubblica(analisi)
    esito.update({"dry_run": False, "eseguita_at": adesso, "righe_aggiornate": aggiornate})
    if aggiornate:
        try:
            await db["prima_nota_migrazioni_audit"].insert_one({
                "id": str(uuid.uuid4()),
                "migrazione": MOTIVO_BONIFICA,
                "actor": actor or "sistema",
                "created_at": adesso,
                "risultato": {k: v for k, v in esito.items() if k not in ("esempi",)},
            })
        except Exception:  # pragma: no cover - l'audit non deve bloccare la bonifica
            logger.exception("Audit della bonifica conti Prima Nota non scritto")
    logger.warning("[bonifica conti prima nota] righe aggiornate %s", aggiornate)
    return esito


async def esegui(db, dry_run: bool = True, actor: Optional[str] = None) -> Dict[str, Any]:
    """Punto unico per endpoint, CLI e avvio."""
    if dry_run:
        return _pubblica(await analizza(db))
    return await applica(db, actor=actor)


def integra_nel_report(report: Dict[str, Any], esito_conti: Dict[str, Any]) -> Dict[str, Any]:
    """Aggiunge la sezione conti al report unico della bonifica Prima Nota."""
    report = dict(report)
    report["conti_contabili"] = esito_conti
    report["righe_conti_da_aggiornare"] = int(esito_conti.get("totale_righe_da_aggiornare") or 0)
    if not esito_conti.get("dry_run", True):
        report["righe_conti_aggiornate"] = int(esito_conti.get("righe_aggiornate") or 0)
    return report
