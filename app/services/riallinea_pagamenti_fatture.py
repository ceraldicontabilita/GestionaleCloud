"""Riallineamento fattura ↔ banca ↔ Prima Nota con il motore canonico (PR 2).

Audit del commercialista 03/09/2026 (memoria/AUDIT_COMMERCIALISTA_2026-09-03.md
§1): 25 righe di Prima Nota Banca "Fatture" scritte dal motore storico di
``riconciliazione_bancaria.py`` (``source = ric_auto_identita_unica``) con
stati divergenti — 18/25 con estratto conto NON riconciliato, 12/25 senza
scadenza ne' partita aperta, Enel 2.787,08 "riconciliata" in Prima Nota ma
partita aperta, Fastweb pagata 7 giorni PRIMA della fattura.

Questa bonifica NON scrive stati per conto suo: per ogni riga di Prima Nota
Banca con ``fattura_id`` ricalcola tutto con l'unico motore
(``bank_payment_allocations.persist_bank_invoice_allocations``), che aggiorna
fattura, scadenze, partita, EC, Prima Nota e relazione con lo stesso
``operation_id`` e con identita' ``bank:<movimento>:<fattura>`` (nessun
doppione: le righe esistenti vengono completate, mai affiancate).

Esiti per riga:

- ``coerente``: i cinque oggetti e la relazione sono gia' allineati → nulla;
- ``riallineabile``: fattura ed EC esistono, il movimento non precede la
  fattura, la quota quadra al centesimo → ``applica`` la passa al motore;
- ``proposta``: incoerenza non risolvibile in automatico (fattura non in
  archivio — §0.1 —, EC assente, pagamento antecedente alla fattura, quota
  che non quadra, EC gia' riconciliato con un'altra fattura, rifiuto del
  motore) → ``applica`` la mette in ``operazioni_da_confermare`` (idempotente
  per movimento, con ``match_type = riallineamento_pagamento_fattura``).

``analizza`` e' un dry-run puro; ``applica`` e' idempotente: al secondo giro
le righe riallineate risultano coerenti e le proposte esistono gia'
(``scritture = 0``).
"""
from __future__ import annotations

import logging
import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from app.services.bank_payment_allocations import (
    evidenza_scadenza_id,
    persist_bank_invoice_allocations,
    validate_bank_invoice_allocations,
)
from app.services.entity_relations import relation_key
from app.services.payment_allocation_validator import to_cents
from app.services.scritture_contabili import FILTRO_MOVIMENTO_ATTIVO, _batch_scritture_registro

logger = logging.getLogger(__name__)

MOTIVO_BONIFICA = "riallinea_pagamenti_fatture_2026-09-03"
MATCH_TYPE_PROPOSTA = "riallineamento_pagamento_fattura"
ACTOR_MOTORE = "automatic_riallineamento_pagamenti_fatture"

ESITO_COERENTE = "coerente"
ESITO_RIALLINEABILE = "riallineabile"
ESITO_PROPOSTA = "proposta"


def _id_ec(riga: Dict[str, Any]) -> str:
    return str(
        riga.get("estratto_conto_id") or riga.get("movimento_bancario_id")
        or riga.get("movimento_estratto_conto_id") or ""
    ).strip()


def _data_fattura(fattura: Dict[str, Any]) -> str:
    return str(
        fattura.get("invoice_date") or fattura.get("data_fattura")
        or fattura.get("data") or ""
    )[:10]


async def _lista(cursor, n: int = 1000) -> List[Dict[str, Any]]:
    if hasattr(cursor, "to_list"):
        return await cursor.to_list(n)
    return [doc async for doc in cursor]


async def _righe_fattura(db) -> List[Dict[str, Any]]:
    righe = await _lista(db["prima_nota_banca"].find({
        "fattura_id": {"$nin": [None, ""]},
        **FILTRO_MOVIMENTO_ATTIVO,
    }), 20000)
    righe.sort(key=lambda r: (str(r.get("data") or ""), str(r.get("id") or "")))
    return righe


async def _valuta_riga(db, riga: Dict[str, Any]) -> Dict[str, Any]:
    """Stato dei cinque oggetti + esito, senza scrivere nulla."""
    fattura_id = str(riga.get("fattura_id") or "")
    ec_id = _id_ec(riga)
    fattura = await db["invoices"].find_one({"id": fattura_id}) if fattura_id else None
    ec = await db["estratto_conto_movimenti"].find_one({"id": ec_id}, {"_id": 0}) if ec_id else None
    scadenze = await _lista(db["scadenziario_fornitori"].find({"fattura_id": fattura_id}), 100)
    partita = await db["partite_aperte"].find_one(
        {"documento_id": fattura_id, "tipo": "fattura_fornitore"}, {"_id": 0},
    )
    allocation_id = f"bank:{ec_id}:{fattura_id}"
    allocazione = await db["bank_payment_allocations"].find_one(
        {"allocation_id": allocation_id, "status": {"$ne": "reversed"}}, {"_id": 0},
    )
    relazione = await db["entity_relations"].find_one({
        "relation_key": relation_key(
            "bank_movement", ec_id or "-", "allocates_invoice_payment", "invoice", fattura_id or "-",
        ),
        "status": "confirmed",
    }, {"_id": 0}) if ec_id and fattura_id else None

    quota_cents = to_cents(riga.get("importo"))
    stato = {
        "prima_nota_id": riga.get("id"),
        "prima_nota_source": riga.get("source"),
        "fattura_id": fattura_id,
        "estratto_conto_id": ec_id,
        "importo": quota_cents / 100,
        "data_movimento": str(riga.get("data") or "")[:10],
        "fattura_presente": fattura is not None,
        "estratto_conto_presente": ec is not None,
        "prima_nota_riconciliata": bool(riga.get("riconciliato")),
        "ec_riconciliato": bool(ec and ec.get("riconciliato")),
        "ec_fattura_id": (ec or {}).get("fattura_id"),
        "fattura_pagata": bool(fattura and (fattura.get("pagato") or fattura.get("paid"))),
        "scadenze": len(scadenze),
        "scadenze_pagate": sum(1 for s in scadenze if s.get("pagato")),
        "scadenze_con_evidenza": sum(
            1 for s in scadenze
            if any(
                str((e or {}).get("evidenza_id")) == evidenza_scadenza_id(ec_id, fattura_id)
                for e in (s.get("evidenze_pagamento") or [])
            )
        ),
        "partita_stato": (partita or {}).get("stato"),
        "allocazione_presente": allocazione is not None,
        "relazione_presente": relazione is not None,
        "fornitore": (fattura or {}).get("supplier_name") or (fattura or {}).get("cedente_denominazione")
        or (scadenze[0].get("fornitore_nome") if scadenze else None),
        "numero_fattura": (fattura or {}).get("invoice_number") or (fattura or {}).get("numero_fattura")
        or (scadenze[0].get("numero_fattura") if scadenze else None),
        "data_fattura": _data_fattura(fattura) if fattura else (
            str(scadenze[0].get("data_fattura") or "")[:10] if scadenze else None
        ),
    }

    motivi: List[str] = []
    if fattura is None:
        motivi.append("fattura_assente")
    if ec is None:
        motivi.append("estratto_conto_assente")
    if ec is not None:
        ec_cents = abs(to_cents(ec.get("importo")))
        if ec_cents != quota_cents:
            motivi.append("quota_non_quadrata")
        ec_fatture = {str(v) for v in (ec.get("fattura_ids") or []) if v}
        if ec.get("fattura_id"):
            ec_fatture.add(str(ec.get("fattura_id")))
        if ec.get("riconciliato") and ec_fatture and fattura_id not in ec_fatture:
            motivi.append("ec_riconciliato_con_altra_fattura")
    data_fattura = stato["data_fattura"]
    if data_fattura and stato["data_movimento"] and stato["data_movimento"] < data_fattura:
        motivi.append("pagamento_antecedente_fattura")

    coerente = (
        not motivi
        and stato["allocazione_presente"]
        and stato["relazione_presente"]
        and stato["ec_riconciliato"]
        and stato["prima_nota_riconciliata"]
        and stato["fattura_pagata"]
        and (stato["scadenze"] == 0 or stato["scadenze_con_evidenza"] > 0)
        and (stato["partita_stato"] in (None, "chiusa", "parziale"))
    )
    if motivi:
        esito = ESITO_PROPOSTA
    elif coerente:
        esito = ESITO_COERENTE
    else:
        esito = ESITO_RIALLINEABILE
    return {**stato, "esito": esito, "motivi": motivi, "_riga": riga, "_fattura": fattura, "_ec": ec}


async def analizza(db) -> Dict[str, Any]:
    """Dry-run: classifica ogni riga di Prima Nota Banca con fattura."""
    valutazioni = [await _valuta_riga(db, riga) for riga in await _righe_fattura(db)]
    esiti = Counter(v["esito"] for v in valutazioni)
    motivi = Counter(m for v in valutazioni for m in v["motivi"])
    proposte_gia_presenti = 0
    for v in valutazioni:
        if v["esito"] != ESITO_PROPOSTA or not v["estratto_conto_id"]:
            continue
        esistente = await db["operazioni_da_confermare"].find_one({
            "movimento_ec_id": v["estratto_conto_id"], "stato": "da_confermare",
        })
        if esistente:
            proposte_gia_presenti += 1
    return {
        "dry_run": True,
        "motivo": MOTIVO_BONIFICA,
        "righe_esaminate": len(valutazioni),
        "coerenti": esiti.get(ESITO_COERENTE, 0),
        "riallineabili": esiti.get(ESITO_RIALLINEABILE, 0),
        "proposte": esiti.get(ESITO_PROPOSTA, 0),
        "proposte_gia_presenti": proposte_gia_presenti,
        "motivi_proposte": dict(motivi),
        "righe": [
            {k: v for k, v in voce.items() if not k.startswith("_")}
            for voce in valutazioni
        ],
        "_valutazioni": valutazioni,
    }


def _pubblica(analisi: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in analisi.items() if not k.startswith("_")}


def _operazione_proposta(voce: Dict[str, Any], now: str) -> Dict[str, Any]:
    riga = voce["_riga"]
    ec = voce.get("_ec") or {}
    fattura = voce.get("_fattura") or {}
    descrizione = str(
        ec.get("descrizione_originale") or ec.get("descrizione")
        or riga.get("descrizione") or ""
    )
    motivo = (
        "Riallineamento pagamento fattura non applicabile in automatico: "
        + ", ".join(voce["motivi"])
        + ". La riga di Prima Nota Banca resta com'e' finche' un operatore non conferma."
    )
    return {
        "id": str(uuid.uuid4()),
        "tipo": "riconciliazione_dubbio",
        "movimento_ec_id": voce["estratto_conto_id"] or f"prima_nota:{riga.get('id')}",
        "data": voce["data_movimento"],
        "importo": voce["importo"],
        "descrizione": descrizione,
        "tipo_movimento": "uscita",
        "match_type": MATCH_TYPE_PROPOSTA,
        "confidence": "basso",
        "dettagli": {
            "fatture_candidate": [{
                "id": voce["fattura_id"],
                "numero": voce.get("numero_fattura"),
                "fornitore": voce.get("fornitore"),
                "importo": fattura.get("total_amount") or fattura.get("importo_totale") or voce["importo"],
                "data": voce.get("data_fattura"),
                "in_archivio": voce["fattura_presente"],
            }],
            "prima_nota_banca_id": riga.get("id"),
            "prima_nota_source": riga.get("source"),
            "motivi": voce["motivi"],
            "stato_oggetti": {
                k: voce[k] for k in (
                    "prima_nota_riconciliata", "ec_riconciliato", "fattura_pagata",
                    "scadenze", "scadenze_pagate", "partita_stato",
                    "allocazione_presente", "relazione_presente",
                )
            },
            "motivo_dubbio": motivo,
        },
        "stato": "da_confermare",
        "origine": MOTIVO_BONIFICA,
        "created_at": now,
    }


async def applica(db, actor: Optional[str] = None) -> Dict[str, Any]:
    """Riallinea con il motore canonico; il resto diventa proposta. Idempotente."""
    from app.services.riconciliazione_bancaria import (
        _alert_match_ambiguo,
        _crea_operazione_da_confermare_idempotente,
    )

    analisi = await analizza(db)
    now = datetime.now(timezone.utc).isoformat()
    riallineate: List[Dict[str, Any]] = []
    rifiutate: List[Dict[str, Any]] = []
    proposte_create = 0
    proposte_gia_presenti = 0
    async with _batch_scritture_registro(db):
        for voce in analisi["_valutazioni"]:
            if voce["esito"] == ESITO_RIALLINEABILE:
                ec = voce["_ec"]
                try:
                    allocazioni = await validate_bank_invoice_allocations(
                        db, ec, [{"id": voce["fattura_id"], "quota_cents": to_cents(voce["importo"])}],
                    )
                    esito = await persist_bank_invoice_allocations(
                        db, ec, allocazioni, actor=ACTOR_MOTORE,
                    )
                except HTTPException as exc:
                    voce["motivi"].append(f"motore_canonico: {exc.detail}")
                    voce["esito"] = ESITO_PROPOSTA
                    rifiutate.append({"prima_nota_id": voce["prima_nota_id"], "motivo": exc.detail})
                else:
                    riallineate.append({
                        "prima_nota_id": voce["prima_nota_id"],
                        "fattura_id": voce["fattura_id"],
                        "estratto_conto_id": voce["estratto_conto_id"],
                        "operation_id": esito.get("operation_id"),
                    })
                    continue
            if voce["esito"] == ESITO_PROPOSTA:
                operazione = _operazione_proposta(voce, now)
                creata = await _crea_operazione_da_confermare_idempotente(db, operazione)
                if creata:
                    proposte_create += 1
                    if voce["estratto_conto_id"]:
                        await _alert_match_ambiguo(
                            db, voce["estratto_conto_id"], operazione["dettagli"]["motivo_dubbio"],
                        )
                else:
                    proposte_gia_presenti += 1

    esito_finale = _pubblica(analisi)
    esito_finale.update({
        "dry_run": False,
        "eseguita_at": now,
        "riallineate": len(riallineate),
        "riallineate_dettaglio": riallineate,
        "rifiutate_dal_motore": rifiutate,
        "proposte_create": proposte_create,
        "proposte_gia_presenti": proposte_gia_presenti,
        "scritture": len(riallineate) + proposte_create,
    })
    if riallineate or proposte_create:
        try:
            await db["prima_nota_migrazioni_audit"].insert_one({
                "id": str(uuid.uuid4()),
                "migrazione": MOTIVO_BONIFICA,
                "actor": actor or "sistema",
                "created_at": now,
                "risultato": {k: v for k, v in esito_finale.items() if k != "righe"},
            })
        except Exception:  # pragma: no cover - l'audit non deve bloccare la bonifica
            logger.exception("Audit del riallineamento pagamenti fatture non scritto")
    logger.warning(
        "[riallinea pagamenti fatture] riallineate %s, proposte create %s (gia' presenti %s), rifiutate %s",
        len(riallineate), proposte_create, proposte_gia_presenti, len(rifiutate),
    )
    return esito_finale


async def esegui(db, dry_run: bool = True, actor: Optional[str] = None) -> Dict[str, Any]:
    """Punto unico per endpoint e avvio."""
    if dry_run:
        return _pubblica(await analizza(db))
    return await applica(db, actor=actor)


async def analizza_avvio(db, actor: Optional[str] = None) -> Dict[str, Any]:
    """Voce di ``bonifiche_avvio`` (app/main.py): SOLO dry-run, registrato in
    ``migration_runs``. L'applicazione resta una scelta esplicita dell'admin
    (``POST /api/admin/riallinea-pagamenti-fatture?dry_run=false``)."""
    esito = _pubblica(await analizza(db))
    esito["applicata"] = False
    esito["actor"] = actor or "sistema"
    # il registro delle migrazioni conserva i conteggi, non 25 righe di dettaglio
    esito["righe"] = esito["righe"][:50]
    return esito
