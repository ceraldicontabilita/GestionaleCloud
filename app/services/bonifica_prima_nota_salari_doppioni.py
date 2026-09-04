"""Bonifica dei doppioni di ``prima_nota_salari`` (PR 14, audit 03/09/2026 §5).

Due canali indipendenti scrivono la stessa busta con chiavi diverse (vedi
``app/services/prima_nota_salari_chiave.py``): l'import da Excel/indice
cedolini Drive (``POST /import-salari-verificati``) non porta il codice
fiscale sulla riga, il sync dal registro cedolini interno
(``services/salari_sync.py``) confronta la chiave solo contro righe che
hanno gia' un CF proprio. Risultato reale verificato 04/09/2026 (vedi
``memoria/AUDIT_COMMERCIALISTA_2026-09-03.md`` §5): 2 buste duplicate di
maggio 2026 (Ceraldi Valerio e Ceraldi Vincenzo, stesso netto 2.000,00
scritto due volte — una dal canale busta, una dal canale cedolino) e 3 righe
di dicembre 2025 (Murolo, Parisi, Pocci) con un bonifico gia' agganciato
(``movimenti_bancari_ids``) ma mai riallineato (``importo_bonifico=0``, saldo
negativo pieno) dopo la migrazione ``recover_salary_relations_20260821_v1``.

Regole (mai un'associazione ambigua, mai una cancellazione fisica):

- due righe sono un DOPPIONE certo solo se hanno la STESSA identita' logica
  (``chiave_logica_riga``: CF risolto, anno, mese, tipo cedolino canonico) E
  lo STESSO importo atteso (entro un centesimo). Due righe con la stessa
  identita' ma importo diverso (es. Parisi 05/2026: 1.231,00 e 1.129,00) NON
  sono toccate qui: sono un'anomalia da capire, non un doppione da
  cancellare — restano nel report in ``ambigue_importo_diverso``, da
  verificare col confronto HR di ``salari_sync_hr.py`` (PR 15);
- tra le righe duplicate resta quella piu' completa (CF proprio,
  ``dipendente_id``, ``cedolino_id``/``hr_cedolino_id``, un riferimento
  bancario gia' collegato — ``punteggio_completezza``), a parita' la piu'
  recente; le altre sono marcate ``entity_status="deleted"`` +
  ``status="deleted"`` + ``duplicate_of``, MAI cancellate;
- se una riga marcata aveva ``movimenti_bancari_ids``, i riferimenti
  (movimento bancario + ``entity_relations``) migrano sulla riga tenuta e i
  suoi importi vengono ricalcolati dai movimenti risultanti;
- il backfill dei campi di pagamento (``importo_bonifico``/``saldo``/
  ``riconciliato``) di una riga con ``movimenti_bancari_ids`` non vuoto ma
  incoerenti riusa lo stesso motore di
  ``stipendi_bonifici.campi_riga_da_movimenti_stipendio``, non lo reinventa.
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

from app.services.entity_relations import relation_key, revoke_entity_relation
from app.services.accounting_relation_writers import record_salary_reconciliation
from app.services.prima_nota_salari_chiave import (
    ChiaveSalario,
    IndiceDipendenti,
    carica_indice_dipendenti,
    chiave_logica_riga,
    importo_atteso_riga,
    nome_riga_salario,
    punteggio_completezza,
    riga_piu_autorevole,
)
from app.services.scritture_contabili import FILTRO_MOVIMENTO_ATTIVO
from app.services.stipendi_bonifici import campi_riga_da_movimenti_stipendio

logger = logging.getLogger(__name__)

MOTIVO_BONIFICA = "bonifica_prima_nota_salari_doppioni_2026-09-04"
COLLECTION = "prima_nota_salari"


def _movimento_ids(riga: Dict[str, Any]) -> List[str]:
    valori = riga.get("movimenti_bancari_ids") or []
    if not isinstance(valori, list):
        valori = [valori]
    result: List[str] = []
    for valore in valori:
        testo = str(valore or "").strip()
        if testo and testo not in result:
            result.append(testo)
    return result


def _sintesi(riga: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": riga.get("id"),
        "dipendente": nome_riga_salario(riga),
        "codice_fiscale": riga.get("codice_fiscale"),
        "tipo": riga.get("tipo"),
        "source": riga.get("source"),
        "importo_busta": importo_atteso_riga(riga),
        "importo_bonifico": riga.get("importo_bonifico"),
        "movimenti_bancari_ids": _movimento_ids(riga),
        "created_at": riga.get("created_at"),
        "cedolino_id": riga.get("cedolino_id"),
    }


async def _righe_attive(db) -> List[Dict[str, Any]]:
    cursor = db[COLLECTION].find(dict(FILTRO_MOVIMENTO_ATTIVO))
    if hasattr(cursor, "to_list"):
        return await cursor.to_list(None)
    return [riga async for riga in cursor]


async def analizza(db) -> Dict[str, Any]:
    """Dry-run puro: raggruppa le righe attive per identita' logica.

    Non scrive nulla. Ritorna i gruppi di doppioni certi (stesso importo),
    le righe con la stessa identita' ma importo diverso (mai toccate qui) e
    le righe con un riferimento bancario da riallineare.
    """
    indice = await carica_indice_dipendenti(db)
    righe = await _righe_attive(db)

    per_chiave: Dict[ChiaveSalario, List[Dict[str, Any]]] = defaultdict(list)
    senza_identita: List[Dict[str, Any]] = []
    for riga in righe:
        chiave = chiave_logica_riga(riga, indice)
        if chiave is None:
            senza_identita.append(_sintesi(riga))
            continue
        per_chiave[chiave].append(riga)

    gruppi_doppioni: List[Dict[str, Any]] = []
    ambigue_importo_diverso: List[Dict[str, Any]] = []
    for chiave, righe_chiave in per_chiave.items():
        if len(righe_chiave) < 2:
            continue
        per_importo: Dict[float, List[Dict[str, Any]]] = defaultdict(list)
        for riga in righe_chiave:
            per_importo[importo_atteso_riga(riga)].append(riga)
        if len(per_importo) > 1:
            ambigue_importo_diverso.append({
                "codice_fiscale": chiave[0], "anno": chiave[1], "mese": chiave[2],
                "tipo_cedolino": chiave[3],
                "righe": [_sintesi(r) for r in righe_chiave],
            })
        for importo, righe_importo in per_importo.items():
            if len(righe_importo) < 2:
                continue
            tenuta = riga_piu_autorevole(righe_importo)
            marcate = [r for r in righe_importo if r.get("id") != tenuta.get("id")]
            if not marcate:
                continue
            gruppi_doppioni.append({
                "codice_fiscale": chiave[0], "anno": chiave[1], "mese": chiave[2],
                "tipo_cedolino": chiave[3], "importo_busta": importo,
                "tenuta": _sintesi(tenuta), "marcate": [_sintesi(r) for r in marcate],
                # riusati solo da ``applica``
                "_tenuta": tenuta, "_marcate": marcate,
            })

    # Righe con un bonifico gia' agganciato ma bonifico/saldo/riconciliato
    # mai riallineati (migrazione 21/08/2026: 23 ``entity_relations``
    # ricreate senza toccare questi tre campi sulla riga salario). Lo stato
    # atteso e' quello calcolato da ``campi_riga_da_movimenti_stipendio``
    # sui movimenti risultanti: se diverso da quello salvato, la riga va
    # riallineata.
    da_riallineare: List[Dict[str, Any]] = []
    for riga in righe:
        ids = _movimento_ids(riga)
        if not ids:
            continue
        movimenti = []
        for movimento_id in ids:
            movimento = await db["estratto_conto_movimenti"].find_one(
                {"id": movimento_id}, {"_id": 0}
            )
            if movimento:
                movimenti.append(movimento)
        campi_attesi = campi_riga_da_movimenti_stipendio(riga, movimenti, "")
        # ``updated_at``/``data_pagamento`` non decidono la discrepanza.
        divergente = any(
            riga.get(campo) != valore
            for campo, valore in campi_attesi.items()
            if campo not in ("updated_at", "data_pagamento")
        )
        if divergente:
            da_riallineare.append({**_sintesi(riga), "_riga": riga})

    gruppi_doppioni.sort(key=lambda g: (g["anno"], g["mese"], g["codice_fiscale"]))
    ambigue_importo_diverso.sort(key=lambda g: (g["anno"], g["mese"], g["codice_fiscale"]))

    return {
        "dry_run": True,
        "motivo": MOTIVO_BONIFICA,
        "righe_attive": len(righe),
        "righe_senza_identita_risolta": len(senza_identita),
        "totale_gruppi_doppioni": len(gruppi_doppioni),
        "totale_righe_da_marcare": sum(len(g["marcate"]) for g in gruppi_doppioni),
        "totale_righe_ambigue_importo_diverso": sum(
            len(g["righe"]) for g in ambigue_importo_diverso
        ),
        "totale_righe_da_riallineare_pagamento": len(da_riallineare),
        "gruppi_doppioni": gruppi_doppioni,
        "ambigue_importo_diverso": ambigue_importo_diverso,
        "da_riallineare_pagamento": da_riallineare,
        "righe_senza_identita": senza_identita,
    }


def _pubblica(analisi: Dict[str, Any]) -> Dict[str, Any]:
    esito = {k: v for k, v in analisi.items() if not k.startswith("_")}
    esito["gruppi_doppioni"] = [
        {k: v for k, v in gruppo.items() if not k.startswith("_")}
        for gruppo in analisi.get("gruppi_doppioni", [])
    ]
    esito["da_riallineare_pagamento"] = [
        {k: v for k, v in riga.items() if not k.startswith("_")}
        for riga in analisi.get("da_riallineare_pagamento", [])
    ]
    return esito


async def _migra_riferimenti_bancari(
    db, *, tenuta: Dict[str, Any], marcate: List[Dict[str, Any]],
    actor: Optional[str], now: str,
) -> Tuple[Dict[str, Any], int, int]:
    """Sposta i riferimenti bancari delle righe marcate sulla riga tenuta e
    ricalcola bonifico/saldo/riconciliato dai movimenti risultanti."""
    ids_tenuta = _movimento_ids(tenuta)
    ids_da_migrare = [mid for r in marcate for mid in _movimento_ids(r) if mid not in ids_tenuta]
    relazioni_revocate = relazioni_create = 0
    if not ids_da_migrare:
        return tenuta, relazioni_revocate, relazioni_create

    tutti_ids = ids_tenuta + ids_da_migrare
    movimenti: List[Dict[str, Any]] = []
    for movimento_id in tutti_ids:
        movimento = await db["estratto_conto_movimenti"].find_one(
            {"id": movimento_id}, {"_id": 0}
        )
        if movimento:
            movimenti.append(movimento)

    campi = campi_riga_da_movimenti_stipendio(tenuta, movimenti, now)
    await db[COLLECTION].update_one({"id": tenuta["id"]}, {"$set": campi})
    tenuta = {**tenuta, **campi}

    for riga_marcata in marcate:
        for movimento_id in _movimento_ids(riga_marcata):
            if movimento_id not in ids_da_migrare:
                continue
            await db["estratto_conto_movimenti"].update_one(
                {"id": movimento_id},
                {"$set": {
                    "stipendio_id": tenuta["id"],
                    "dipendente": nome_riga_salario(tenuta),
                    "riallineo_doppioni": MOTIVO_BONIFICA,
                    "updated_at": now,
                }},
            )
            if await revoke_entity_relation(
                db, source_type="bank_movement", source_id=str(movimento_id),
                relation_type="allocates_salary_payment", target_type="salary_entry",
                target_id=str(riga_marcata["id"]), actor=actor or MOTIVO_BONIFICA,
            ):
                relazioni_revocate += 1
            movimento = next((m for m in movimenti if str(m.get("id")) == movimento_id), None)
            if movimento:
                try:
                    await record_salary_reconciliation(
                        db, salary_entry=tenuta, movement=movimento,
                        amount=round(abs(float(movimento.get("importo") or 0)), 2),
                        employee_name=nome_riga_salario(tenuta),
                    )
                    relazioni_create += 1
                except Exception:
                    logger.exception(
                        "Errore relazione stipendio %s / movimento %s nella bonifica doppioni",
                        tenuta.get("id"), movimento_id,
                    )
    return tenuta, relazioni_revocate, relazioni_create


async def applica(db, actor: Optional[str] = None) -> Dict[str, Any]:
    """Marca i doppioni certi, migra i riferimenti bancari, riallinea i
    pagamenti orfani. Mai una cancellazione fisica."""
    analisi = await analizza(db)
    adesso = datetime.now(timezone.utc).isoformat()
    righe_marcate = 0
    relazioni_revocate_tot = relazioni_create_tot = 0

    for gruppo in analisi["gruppi_doppioni"]:
        tenuta = gruppo["_tenuta"]
        marcate = gruppo["_marcate"]
        tenuta, revocate, create = await _migra_riferimenti_bancari(
            db, tenuta=tenuta, marcate=marcate, actor=actor, now=adesso,
        )
        relazioni_revocate_tot += revocate
        relazioni_create_tot += create
        for riga in marcate:
            await db[COLLECTION].update_one(
                {"id": riga["id"]},
                {"$set": {
                    "entity_status": "deleted",
                    "status": "deleted",
                    "duplicate_of": tenuta["id"],
                    "deleted_reason": MOTIVO_BONIFICA,
                    "deleted_at": adesso,
                    "updated_at": adesso,
                }},
            )
            righe_marcate += 1

    righe_riallineate = 0
    for voce in analisi["da_riallineare_pagamento"]:
        riga = voce["_riga"]
        # Se la riga e' stata appena marcata duplicata, il riallineo di
        # riferimenti l'ha gia' gestita: non toccarla due volte.
        if riga.get("id") in {r["id"] for g in analisi["gruppi_doppioni"] for r in g["_marcate"]}:
            continue
        movimenti = []
        for movimento_id in _movimento_ids(riga):
            movimento = await db["estratto_conto_movimenti"].find_one(
                {"id": movimento_id}, {"_id": 0}
            )
            if movimento:
                movimenti.append(movimento)
        campi = campi_riga_da_movimenti_stipendio(riga, movimenti, adesso)
        if any(riga.get(k) != v for k, v in campi.items()):
            await db[COLLECTION].update_one({"id": riga["id"]}, {"$set": campi})
            righe_riallineate += 1

    esito = _pubblica(analisi)
    esito.update({
        "dry_run": False,
        "eseguita_at": adesso,
        "righe_marcate": righe_marcate,
        "righe_pagamento_riallineate": righe_riallineate,
        "relazioni_revocate": relazioni_revocate_tot,
        "relazioni_create": relazioni_create_tot,
    })
    try:
        await db["prima_nota_migrazioni_audit"].insert_one({
            "id": str(uuid.uuid4()),
            "migrazione": MOTIVO_BONIFICA,
            "actor": actor or "sistema",
            "created_at": adesso,
            "risultato": {
                k: v for k, v in esito.items()
                if k not in ("gruppi_doppioni", "ambigue_importo_diverso", "da_riallineare_pagamento", "righe_senza_identita")
            },
            "gruppi_doppioni": [
                {"tenuta": g["tenuta"]["id"], "marcate": [m["id"] for m in g["marcate"]]}
                for g in esito["gruppi_doppioni"]
            ],
        })
    except Exception:  # pragma: no cover - l'audit non deve bloccare la bonifica
        logger.exception("Audit della bonifica doppioni salari non scritto")
    logger.warning(
        "[bonifica doppioni salari] marcate %s righe, pagamenti riallineati %s, "
        "relazioni revocate %s, create %s",
        righe_marcate, righe_riallineate, relazioni_revocate_tot, relazioni_create_tot,
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
        description="Bonifica dei doppioni di prima_nota_salari (PR 14).",
    )
    parser.add_argument("--applica", action="store_true",
                        help="marca davvero i doppioni (default: solo analisi)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    risultato = asyncio.run(_main_async(dry_run=not args.applica))
    print(json.dumps(risultato, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
