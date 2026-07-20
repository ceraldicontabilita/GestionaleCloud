"""Associazione prudente tra movimenti bancari e stipendi.

Una riga viene riconciliata soltanto quando la descrizione bancaria contiene
il nome completo del dipendente e l'importo coincide al centesimo con la
busta ancora da pagare. Non esistono fallback per mese, ordine del database o
semplice vicinanza dell'importo.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.services.bonifici_pdf_ingest import (
    arricchisci_nomi_salari_da_cedolini,
    nome_presente_nel_testo,
    nome_tokens,
)

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


def _candidati_univoci(
    descrizione: str,
    importo: float,
    righe: List[Dict[str, Any]],
    data_movimento: str = "",
) -> List[Dict[str, Any]]:
    """Nome completo + importo entro il residuo + periodo, se presente."""
    nome_favore = estrai_nome_favore(descrizione)
    periodo = estrai_periodo_causale(descrizione)
    candidati: List[Dict[str, Any]] = []
    for riga in righe:
        if riga.get("riconciliato") is True:
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

    movimenti = await db["estratto_conto_movimenti"].find(
        {
            "riconciliato": {"$ne": True},
            "$or": [
                {"descrizione": {"$regex": "FAVORE|STIPEND|EMOLUMENT|SALARI|COMPETENZ", "$options": "i"}},
                {"descrizione_originale": {"$regex": "FAVORE|STIPEND|EMOLUMENT|SALARI|COMPETENZ", "$options": "i"}},
            ],
        },
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
        candidati = _candidati_univoci(
            descrizione,
            abs(importo_grezzo),
            righe,
            data_movimento=movimento.get("data") or "",
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
                        "nome_completo_in_causale",
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
