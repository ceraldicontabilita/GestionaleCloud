"""Proiezione semantica delle prove bancarie in Prima Nota Banca.

L'estratto conto e' prova immutabile. Quando la causale identifica in modo
univoco la natura dell'operazione (finanziamento socio, retribuzione/TFR o
addebito PayPal), questa prova viene proiettata nel registro contabile tramite
il writer unico. Non viene mai usata la sola uguaglianza dell'importo.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional

from app.database import Collections
from app.routers.bonifici_module.classification import (
    classifica_destinazione_dipendente,
)
from app.services.finanziamenti_soci import classifica_finanziamento_ec
from app.services.scritture_contabili import scrivi_movimento_se_assente
from app.services.bank_reconciliation_rules import classify_bank_movement


SOURCE = "proiezione_semantica_ec"
_PAYPAL = re.compile(r"\bPAYPAL\b", re.IGNORECASE)
_ADDEBITO_DIRETTO = re.compile(
    r"\b(?:SDD|ADDEBITO\s+DIRETTO|49RJ2252ASLM4)\b", re.IGNORECASE
)


def _testo(doc: Dict[str, Any]) -> str:
    return " ".join(
        str(doc.get(campo) or "")
        for campo in (
            "descrizione_originale", "descrizione", "causale",
            "beneficiario", "ordinante",
        )
        if doc.get(campo)
    ).strip()


def _id_ec(doc: Dict[str, Any]) -> str:
    return str(
        doc.get("id")
        or doc.get("movement_id")
        or doc.get("transaction_id")
        or doc.get("_id")
        or ""
    )


def _data_iso(doc: Dict[str, Any]) -> str:
    valore = str(
        doc.get("data_contabile")
        or doc.get("data")
        or doc.get("date")
        or doc.get("data_valuta")
        or ""
    ).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", valore[:10]):
        return valore[:10]
    match = re.search(r"\b(\d{2})[/-](\d{2})[/-](\d{4})\b", valore)
    if match:
        return f"{match.group(3)}-{match.group(2)}-{match.group(1)}"
    return ""


def _verso(doc: Dict[str, Any]) -> Optional[str]:
    valore = str(doc.get("tipo") or doc.get("type") or "").strip().lower()
    if valore in {"entrata", "credito", "credit", "dare"}:
        return "entrata"
    if valore in {"uscita", "debito", "debit", "avere"}:
        return "uscita"
    try:
        return "entrata" if float(doc.get("importo") or 0) > 0 else "uscita"
    except (TypeError, ValueError):
        return None


def _importo(doc: Dict[str, Any]) -> float:
    try:
        return round(abs(float(doc.get("importo") or doc.get("amount") or 0)), 2)
    except (TypeError, ValueError):
        return 0.0


def _classifica_paypal(doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    testo = _testo(doc)
    if _verso(doc) != "uscita" or not (_PAYPAL.search(testo) and _ADDEBITO_DIRETTO.search(testo)):
        return None
    return {
        "tipo": "uscita",
        "categoria": "Pagamento PayPal",
        "tipo_classificazione_contabile": "paypal_sdd",
        "gestore_pagamento": "paypal",
    }


def _classifica_dipendente(
    doc: Dict[str, Any], dipendenti: Iterable[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    if _verso(doc) != "uscita":
        return None
    risultato = classifica_destinazione_dipendente(doc, dipendenti)
    if not (risultato.get("destinazione_dipendente") and risultato.get("identita_univoca")):
        return None
    tipo = risultato.get("tipo_retribuzione") or "stipendio"
    return {
        "tipo": "uscita",
        "categoria": "TFR" if tipo == "tfr" else "Stipendi",
        "tipo_classificazione_contabile": tipo,
        "dipendente_id": risultato.get("dipendente_id"),
        "dipendente_nome": risultato.get("dipendente_nome_rilevato"),
        "dipendente_codice_fiscale": risultato.get("dipendente_codice_fiscale"),
        "motivo_classificazione": risultato.get("motivo_destinazione"),
    }


def classifica_movimento_ec(
    doc: Dict[str, Any], dipendenti: Iterable[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Classifica solo identita' esplicite; nessun match per importo."""
    finanziamento = classifica_finanziamento_ec(doc)
    if finanziamento:
        return {
            "tipo": finanziamento["tipo_banca"],
            "categoria": "Finanziamento soci",
            "tipo_classificazione_contabile": f"finanziamento_socio_{finanziamento['tipo']}",
            "socio_id": finanziamento["socio_id"],
            "socio_nome": finanziamento["socio_nome"],
            "tipo_finanziamento": finanziamento["tipo"],
        }
    causale = classify_bank_movement(doc)
    if (
        causale
        and causale.get("tipo") == "commissione_bancaria"
        and _verso(doc) == "uscita"
    ):
        # Commissioni e competenze sono costi bancari deterministici che non
        # richiedono una fattura esterna. Possono quindi entrare nel registro
        # con la riga EC come prova esatta; POS, SDD, F24 e versamenti restano
        # invece solo classificati finche' manca il collegamento reciproco.
        return {
            "tipo": "uscita",
            "categoria": "Commissioni bancarie",
            "tipo_classificazione_contabile": (
                f"commissione_bancaria:{causale['rule_id']}"
            ),
            "regola_bancaria": causale["rule_id"],
            "regola_versione": causale["rule_version"],
            "campi_estratti": causale.get("campi_estratti") or {},
        }
    dipendente = _classifica_dipendente(doc, dipendenti)
    if dipendente:
        return dipendente
    return _classifica_paypal(doc)


async def proietta_movimenti_bancari_semantici(
    db, *, anno: Optional[int] = None, movimento_ids=None,
) -> Dict[str, Any]:
    """Scrive in Banca le sole prove con classificazione univoca e auditabile."""
    dipendenti = await db[Collections.EMPLOYEES].find(
        {}, {
            "_id": 0, "id": 1, "nome": 1, "cognome": 1,
            "nome_completo": 1, "codice_fiscale": 1, "cf": 1, "iban": 1,
        },
    ).to_list(5000)

    query: Dict[str, Any] = {}
    if movimento_ids:
        ids = [str(item) for item in movimento_ids if item]
        query = {"$or": [
            {"id": {"$in": ids}},
            {"movement_id": {"$in": ids}},
            {"transaction_id": {"$in": ids}},
        ]}

    stats = {
        "esaminati": 0, "proiettati": 0, "gia_presenti": 0,
        "finanziamenti_soci": 0, "stipendi": 0, "tfr": 0,
        "paypal_sdd": 0, "non_classificati": 0,
        "causali_deterministiche": 0,
        "commissioni_bancarie": 0,
    }
    cursore = db[Collections.BANK_STATEMENTS].find(query)
    async for movimento_ec in cursore:
        data = _data_iso(movimento_ec)
        if anno and not data.startswith(f"{anno}-"):
            continue
        stats["esaminati"] += 1
        ec_id = _id_ec(movimento_ec)
        importo = _importo(movimento_ec)
        causale_classification = classify_bank_movement(movimento_ec)
        if causale_classification and ec_id:
            source_query = (
                {"_id": movimento_ec["_id"]}
                if movimento_ec.get("_id") is not None
                else {"id": ec_id}
            )
            await db[Collections.BANK_STATEMENTS].update_one(
                source_query,
                {"$set": {
                    "decisione_classificazione": "automatica",
                    "classificazione_rule_id": causale_classification["rule_id"],
                    "classificazione_rule_version": causale_classification["rule_version"],
                    "classificazione_evidenze": causale_classification["evidenze"],
                    "classificazione_campi_estratti": causale_classification["campi_estratti"],
                    "classificazione_tipo": causale_classification["tipo"],
                    "classificazione_categoria": causale_classification["categoria"],
                    "classificato_at": datetime.now(timezone.utc).isoformat(),
                }},
            )
            stats["causali_deterministiche"] += 1
        classificazione = classifica_movimento_ec(movimento_ec, dipendenti)
        if not classificazione or not ec_id or not data or importo <= 0:
            stats["non_classificati"] += 1
            continue

        tipo_classificazione = classificazione["tipo_classificazione_contabile"]
        documento = {
            "data": data,
            "anno": int(data[:4]),
            "mese": int(data[5:7]),
            "tipo": classificazione["tipo"],
            "importo": importo,
            "categoria": classificazione["categoria"],
            "descrizione": _testo(movimento_ec),
            "source": SOURCE,
            "natura": "movimento_bancario_reale",
            "estratto_conto_id": ec_id,
            "movimento_estratto_conto_id": ec_id,
            "movimento_bancario_id": ec_id,
            "classificazione_automatica": True,
            "tipo_classificazione_contabile": tipo_classificazione,
            "classificato_at": datetime.now(timezone.utc).isoformat(),
            **{k: v for k, v in classificazione.items() if k not in {"tipo", "categoria"} and v},
        }
        prima_nota_id, gia_esistente = await scrivi_movimento_se_assente(
            db,
            "banca",
            {"$or": [
                {"estratto_conto_id": ec_id},
                {"movimento_estratto_conto_id": ec_id},
                {"movimento_bancario_id": ec_id},
                {"movimento_banca_id": ec_id},
            ]},
            documento,
        )
        query_sorgente = (
            {"_id": movimento_ec["_id"]}
            if movimento_ec.get("_id") is not None
            else {"id": ec_id}
        )
        await db[Collections.BANK_STATEMENTS].update_one(
            query_sorgente,
            {"$set": {
                "classificato_contabilmente": True,
                "tipo_classificazione_contabile": tipo_classificazione,
                "prima_nota_banca_id": prima_nota_id,
                "proiezione_contabile_at": datetime.now(timezone.utc).isoformat(),
                **{k: v for k, v in classificazione.items() if k in {
                    "socio_id", "socio_nome", "dipendente_id", "dipendente_nome",
                    "gestore_pagamento",
                } and v},
            }},
        )
        if gia_esistente:
            stats["gia_presenti"] += 1
        else:
            stats["proiettati"] += 1
        if tipo_classificazione.startswith("finanziamento_socio_"):
            stats["finanziamenti_soci"] += 1
        elif tipo_classificazione.startswith("commissione_bancaria:"):
            stats["commissioni_bancarie"] += 1
        elif tipo_classificazione in {"stipendio", "tfr", "paypal_sdd"}:
            chiave_statistica = {
                "stipendio": "stipendi",
                "tfr": "tfr",
                "paypal_sdd": "paypal_sdd",
            }[tipo_classificazione]
            stats[chiave_statistica] += 1
    return stats
