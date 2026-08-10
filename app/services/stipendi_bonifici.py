"""Associazione prudente tra movimenti bancari e stipendi.

Una riga viene riconciliata soltanto quando la descrizione bancaria contiene
l'identita' completa del dipendente e l'importo e' positivo e non supera il
residuo della busta. Sono ammessi piu' acconti; la riga si chiude soltanto
quando la loro somma raggiunge il netto. Non esistono fallback per ordine del
database, solo cognome o semplice vicinanza dell'importo.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.database import Collections
from app.routers.bonifici_module.classification import (
    classifica_destinazione_dipendente,
)
from app.services.bonifici_pdf_ingest import arricchisci_nomi_salari_da_cedolini
from app.services.identity_matching import nome_presente_nel_testo, nome_tokens
from app.services.accounting_relation_writers import record_salary_reconciliation

logger = logging.getLogger(__name__)

_FAVORE_RE = re.compile(
    r"FAVORE\s+([A-Za-zÀ-ÿ'\. ]+?)(?:\s+NOTPROVIDE\b.*)?\s*(?:-|$)",
    re.I,
)
_PERIODO_NUM_RE = re.compile(r"\b(0?[1-9]|1[0-4])[/\-](20\d{2})\b")
_MESI = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4,
    "maggio": 5, "giugno": 6, "luglio": 7, "agosto": 8,
    "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
    "tredicesima": 13, "quattordicesima": 14,
}


def _tokens(nome: str) -> frozenset[str]:
    return nome_tokens(nome)


def estrai_nome_favore(descrizione: str) -> Optional[str]:
    """Estrae il beneficiario; esclude sempre le righe di commissione."""
    if not descrizione or "COMM" in descrizione.upper()[:30]:
        return None
    match = _FAVORE_RE.search(descrizione)
    return match.group(1).strip() if match else None


def estrai_periodo_causale(descrizione: str) -> Optional[Tuple[int, int]]:
    """Restituisce (mese, anno) solo quando la causale lo dichiara."""
    testo = (descrizione or "").casefold()
    match = _PERIODO_NUM_RE.search(testo)
    if match:
        return int(match.group(1)), int(match.group(2))
    for nome, mese in _MESI.items():
        match = re.search(rf"\b{nome}\b(?:\s+|[/\-])(20\d{{2}})\b", testo)
        if match:
            return mese, int(match.group(1))
    return None


def _nome_riga_stipendio(riga: Dict[str, Any]) -> str:
    nome = (
        riga.get("dipendente_nome")
        or riga.get("dipendente")
        or riga.get("nome_dipendente")
        or ""
    ).strip()
    if nome:
        return nome
    match = re.search(
        r"Stipendio\s+(.+?)\s*[-–]?\s*\d{2}/\d{4}",
        riga.get("descrizione") or "",
    )
    return match.group(1).strip() if match else ""


def _importo_atteso(riga: Dict[str, Any]) -> float:
    return round(float(riga.get("importo_busta") or riga.get("importo") or 0), 2)


def _importo_residuo(riga: Dict[str, Any]) -> float:
    atteso = _importo_atteso(riga)
    pagato = round(abs(float(riga.get("importo_bonifico") or 0)), 2)
    return round(max(0.0, atteso - pagato), 2)


def _anagrafica_fallback_da_salari(righe: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Compatibilita' per record storici: l'anagrafica resta la fonte primaria."""
    result: List[Dict[str, Any]] = []
    identita = set()
    for riga in righe:
        nome = _nome_riga_stipendio(riga)
        chiave = tuple(sorted(_tokens(nome)))
        if len(chiave) < 2 or chiave in identita:
            continue
        identita.add(chiave)
        result.append({
            "id": riga.get("dipendente_id") or f"salario:{'|'.join(chiave)}",
            "nome_completo": nome,
            "codice_fiscale": riga.get("codice_fiscale"),
            "iban": riga.get("iban"),
        })
    return result


def _candidati_univoci(
    descrizione: str,
    importo: float,
    righe: List[Dict[str, Any]],
    data_movimento: str = "",
    dipendente_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Nome completo + importo entro il residuo + periodo, se presente."""
    nome_favore = estrai_nome_favore(descrizione)
    periodo = estrai_periodo_causale(descrizione)
    candidati: List[Dict[str, Any]] = []
    for riga in righe:
        if riga.get("riconciliato") is True:
            continue
        # Quando l'anagrafica ha identificato il dipendente per CF/IBAN/nome,
        # non permettere che un omonimo con un altro id diventi candidato.
        riga_dipendente_id = str(riga.get("dipendente_id") or "").strip()
        if dipendente_id and riga_dipendente_id and riga_dipendente_id != str(dipendente_id):
            continue
        residuo = _importo_residuo(riga)
        if residuo <= 0 or importo - residuo > 0.009:
            continue
        nome_riga = _nome_riga_stipendio(riga)
        nome_ok = (
            _tokens(nome_favore or "") == _tokens(nome_riga)
            if nome_favore
            else nome_presente_nel_testo(nome_riga, descrizione)
        )
        if not nome_ok or len(_tokens(nome_riga)) < 2:
            continue
        if periodo and (
            int(riga.get("mese") or 0), int(riga.get("anno") or 0)
        ) != periodo:
            continue
        if not periodo:
            # Senza periodo esplicito in causale, la data deve cadere nella
            # finestra paga dal 20 del mese al 15 del mese successivo.
            try:
                mese_riga = int(riga.get("mese") or 0)
                anno_riga = int(riga.get("anno") or 0)
                data_mov = datetime.fromisoformat(str(data_movimento)[:10])
                if not 1 <= mese_riga <= 12:
                    continue
                inizio = datetime(anno_riga, mese_riga, 20)
                fine = (
                    datetime(anno_riga + 1, 1, 15)
                    if mese_riga == 12
                    else datetime(anno_riga, mese_riga + 1, 15)
                )
                if not inizio <= data_mov <= fine:
                    continue
            except (TypeError, ValueError):
                continue
        candidati.append(riga)
    return candidati


async def associa_bonifici_stipendi(
    db, stipendio_id: Optional[str] = None, anno: Optional[int] = None
) -> Dict[str, Any]:
    """Riconcilia solo match bancari certi e univoci."""
    nomi_arricchiti = await arricchisci_nomi_salari_da_cedolini(db)
    filtro: Dict[str, Any] = {"riconciliato": {"$ne": True}}
    if stipendio_id:
        filtro["id"] = stipendio_id
    if anno:
        filtro["anno"] = int(anno)
    righe = await db["prima_nota_salari"].find(
        filtro, {"_id": 0}
    ).to_list(5000)

    dipendenti = await db[Collections.EMPLOYEES].find(
        {}, {
            "_id": 0,
            "id": 1,
            "nome": 1,
            "cognome": 1,
            "nome_completo": 1,
            "codice_fiscale": 1,
            "cf": 1,
            "iban": 1,
        },
    ).to_list(5000)
    # I salari storici possono precedere la migrazione dell'anagrafica. Sono
    # usati solo come fallback e non sostituiscono mai una identita' corrente.
    ids_anagrafica = {str(d.get("id") or "") for d in dipendenti if d.get("id")}
    nomi_anagrafica = {
        tuple(sorted(_tokens(
            d.get("nome_completo")
            or f"{d.get('nome', '')} {d.get('cognome', '')}".strip()
        )))
        for d in dipendenti
    }
    for fallback in _anagrafica_fallback_da_salari(righe):
        nome_fallback = tuple(sorted(_tokens(fallback.get("nome_completo") or "")))
        if (
            str(fallback.get("id") or "") not in ids_anagrafica
            and nome_fallback not in nomi_anagrafica
        ):
            dipendenti.append(fallback)

    filtro_movimenti: Dict[str, Any] = {
        "riconciliato": {"$ne": True},
        "$or": [
            {"tipo": "uscita"},
            {"importo": {"$lt": 0}},
        ],
    }
    if anno:
        filtro_movimenti["data"] = {"$regex": rf"^{int(anno)}-"}
    movimenti = await db["estratto_conto_movimenti"].find(
        filtro_movimenti,
        {"_id": 0},
    ).sort("data", 1).to_list(10000)

    now = datetime.now(timezone.utc).isoformat()
    associati = righe_completate = ambigui = 0
    dettaglio: List[Dict[str, Any]] = []

    for movimento in movimenti:
        importo_grezzo = float(movimento.get("importo") or 0)
        if not (movimento.get("tipo") == "uscita" or importo_grezzo < 0):
            continue
        descrizione = (
            movimento.get("descrizione_originale")
            or movimento.get("descrizione")
            or ""
        )
        if "COMM" in descrizione.upper()[:30]:
            continue
        destinazione = classifica_destinazione_dipendente(movimento, dipendenti)
        if not (
            destinazione.get("destinazione_dipendente")
            and destinazione.get("identita_univoca")
        ):
            continue
        candidati = _candidati_univoci(
            descrizione,
            abs(importo_grezzo),
            righe,
            data_movimento=movimento.get("data") or "",
            dipendente_id=destinazione.get("dipendente_id"),
        )
        if len(candidati) != 1:
            ambigui += int(len(candidati) > 1)
            continue

        riga = candidati[0]
        importo = round(abs(importo_grezzo), 2)
        atteso = _importo_atteso(riga)
        pagato_prima = round(abs(float(riga.get("importo_bonifico") or 0)), 2)
        pagato_totale = round(pagato_prima + importo, 2)
        saldo = round(atteso - pagato_totale, 2)
        completata = abs(saldo) <= 0.009
        await db["estratto_conto_movimenti"].update_one(
            {"id": movimento["id"]},
            {"$set": {
                "riconciliato": True,
                "tipo_riconciliazione": "stipendio_nome_importo_entro_residuo",
                "stipendio_id": riga["id"],
                "dipendente": _nome_riga_stipendio(riga),
                "dipendente_id": (
                    destinazione.get("dipendente_id") or riga.get("dipendente_id")
                ),
                "categoria": "Stipendi",
                "data_riconciliazione": now,
            }},
        )
        await db["prima_nota_salari"].update_one(
            {"id": riga["id"]},
            {
                "$set": {
                    "importo_bonifico": pagato_totale,
                    "saldo": 0.0 if completata else saldo,
                    "data_pagamento": (movimento.get("data") or "")[:10],
                    "pagato_con": "bonifico",
                    "riconciliato": completata,
                    "stato_bonifico": (
                        "riconciliato" if completata else "parzialmente_riconciliato"
                    ),
                    "riconciliazione_evidenze": [
                        destinazione.get("motivo_destinazione"),
                        "importo_entro_residuo",
                        "movimento_estratto_conto",
                    ],
                    "updated_at": now,
                },
                "$addToSet": {"movimenti_bancari_ids": movimento["id"]},
            },
        )
        riga["importo_bonifico"] = pagato_totale
        riga["saldo"] = 0.0 if completata else saldo
        riga["riconciliato"] = completata
        try:
            await record_salary_reconciliation(
                db,
                salary_entry=riga,
                movement=movimento,
                amount=importo,
                employee_name=_nome_riga_stipendio(riga),
            )
        except Exception:
            logger.exception(
                "Errore registrazione relazione stipendio %s / movimento %s",
                riga.get("id"),
                movimento.get("id"),
            )
        associati += 1
        righe_completate += int(completata)
        if len(dettaglio) < 40:
            dettaglio.append({
                "dipendente": _nome_riga_stipendio(riga),
                "data_bonifico": (movimento.get("data") or "")[:10],
                "importo": importo,
                "stipendio_id": riga["id"],
                "riga_completata": completata,
            })

    return {
        "bonifici_associati": associati,
        "righe_stipendio_completate": righe_completate,
        "righe_pendenti_esaminate": len(righe),
        "nomi_arricchiti_da_cedolini": nomi_arricchiti,
        "match_ambigui_ignorati": ambigui,
        "dettaglio": dettaglio,
    }


async def riconciliazione_salario_verificata(db, riga: Dict[str, Any]) -> bool:
    """Convalida anche le vecchie etichette usando il movimento bancario."""
    if riga.get("riconciliato") is not True:
        return False
    atteso = _importo_atteso(riga)
    importo_registrato = round(abs(float(riga.get("importo_bonifico") or 0)), 2)
    if atteso <= 0 or abs(atteso - importo_registrato) > 0.009:
        return False

    movimento_ids: List[str] = []
    for value in riga.get("movimenti_bancari_ids") or []:
        if value and value not in movimento_ids:
            movimento_ids.append(value)
    for key in (
        "estratto_conto_id", "movimento_estratto_conto_id",
        "movimento_bancario_id", "bank_movement_id",
    ):
        value = riga.get(key)
        if value and value not in movimento_ids:
            movimento_ids.append(value)
    if not movimento_ids:
        return False

    riga_verifica = dict(riga)
    riga_verifica["riconciliato"] = False
    riga_verifica["importo_bonifico"] = 0.0
    totale_verificato = 0.0
    for movimento_id in movimento_ids:
        movimento = await db["estratto_conto_movimenti"].find_one(
            {"id": movimento_id}, {"_id": 0}
        )
        if not movimento:
            continue
        importo = abs(float(movimento.get("importo") or 0))
        residuo = round(atteso - totale_verificato, 2)
        if importo <= 0 or importo - residuo > 0.009:
            continue
        descrizione = (
            movimento.get("descrizione_originale")
            or movimento.get("descrizione")
            or ""
        )
        candidati = _candidati_univoci(
            descrizione,
            importo,
            [riga_verifica],
            data_movimento=movimento.get("data") or "",
        )
        if len(candidati) == 1:
            totale_verificato = round(totale_verificato + importo, 2)
            riga_verifica["importo_bonifico"] = totale_verificato
    return abs(atteso - totale_verificato) <= 0.009
