"""Associazione prudente tra movimenti bancari e stipendi.

Una riga viene riconciliata soltanto quando la descrizione bancaria contiene
l'identita' completa del dipendente e l'importo e' positivo e non supera il
residuo della busta. Sono ammessi piu' acconti; la riga si chiude soltanto
quando la loro somma raggiunge il netto. Non esistono fallback per ordine del
database, solo cognome o semplice vicinanza dell'importo.

Competenza del bonifico (LOGICA_FUNZIONAMENTO.md §7, audit 03/09/2026 PR 13):
senza periodo esplicito in causale, un bonifico eseguito PRIMA del giorno 25
paga il cedolino del mese precedente (il saldo di gennaio arriva il 20
febbraio); dal 25 in poi paga il mese corrente. La vecchia finestra
[20/M, 15/M+1] agganciava il saldo di gennaio pagato il 20/02 alla busta di
febbraio: ``riallinea_competenza_bonifici_stipendi`` sposta (o stacca) i
bonifici gia' registrati sul mese sbagliato.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.database import Collections
from app.db_collections import COLL_ENTITY_RELATIONS
from app.routers.bonifici_module.classification import (
    classifica_destinazione_dipendente,
)
from app.services.bonifici_pdf_ingest import arricchisci_nomi_salari_da_cedolini
from app.services.identity_matching import nome_presente_nel_testo, nome_tokens
from app.services.accounting_relation_writers import record_salary_reconciliation
from app.services.entity_relations import relation_key, revoke_entity_relation
from app.services.scritture_contabili import FILTRO_MOVIMENTO_ATTIVO

logger = logging.getLogger(__name__)

# Giorno del mese da cui un bonifico senza periodo in causale si riferisce al
# mese corrente invece che al precedente (LOGICA_FUNZIONAMENTO.md §7).
GIORNO_CAMBIO_COMPETENZA = 25
MOTIVO_RIALLINEO_COMPETENZA = "riallineo_competenza_bonifici_stipendi_2026-09-03"

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


def competenza_bonifico_stipendio(data_movimento: Any) -> Optional[Tuple[int, int]]:
    """``(mese, anno)`` del cedolino pagato da un bonifico senza periodo in causale.

    Prima del giorno 25 il bonifico e' il saldo/acconto del mese PRECEDENTE
    (20/02/2026 -> 01/2026); dal 25 in poi e' del mese corrente (30/03/2026
    -> 03/2026). ``None`` se la data non e' leggibile.
    """
    try:
        data = datetime.fromisoformat(str(data_movimento or "")[:10])
    except (TypeError, ValueError):
        return None
    if data.day < GIORNO_CAMBIO_COMPETENZA:
        return (12, data.year - 1) if data.month == 1 else (data.month - 1, data.year)
    return data.month, data.year


def periodo_atteso_bonifico(descrizione: str, data_movimento: Any) -> Optional[Tuple[int, int]]:
    """Periodo dichiarato in causale, altrimenti quello dedotto dalla data."""
    return estrai_periodo_causale(descrizione) or competenza_bonifico_stipendio(data_movimento)


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


def _movimento_ids_stipendio(riga: Dict[str, Any]) -> List[str]:
    """Riferimenti bancari espliciti, deduplicati e nell'ordine sorgente."""
    result: List[str] = []
    values = riga.get("movimenti_bancari_ids") or []
    if not isinstance(values, list):
        values = [values]
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    for field in (
        "estratto_conto_id", "movimento_estratto_conto_id",
        "movimento_bancario_id", "bank_movement_id",
    ):
        text = str(riga.get(field) or "").strip()
        if text and text not in result:
            result.append(text)
    return result


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
    allow_partial: bool = True,
) -> List[Dict[str, Any]]:
    """Nome completo + importo entro il residuo + periodo di competenza.

    Il periodo e' quello scritto in causale; altrimenti lo decide la data del
    bonifico con la regola del giorno 25 (``competenza_bonifico_stipendio``).
    """
    nome_favore = estrai_nome_favore(descrizione)
    periodo = periodo_atteso_bonifico(descrizione, data_movimento)
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
        # Un saldo deve coprire l'intero residuo. Acconto e multiplo sono
        # ammessi soltanto quando l'operatore li ha scelti esplicitamente.
        if not allow_partial and abs(importo - residuo) > 0.009:
            continue
        nome_riga = _nome_riga_stipendio(riga)
        nome_ok = (
            _tokens(nome_favore or "") == _tokens(nome_riga)
            if nome_favore
            else nome_presente_nel_testo(nome_riga, descrizione)
        )
        if not nome_ok or len(_tokens(nome_riga)) < 2:
            continue
        # Senza periodo (ne' in causale ne' da una data leggibile) non si
        # sceglie una busta "a caso": nessun candidato.
        if periodo is None:
            continue
        try:
            periodo_riga = (int(riga.get("mese") or 0), int(riga.get("anno") or 0))
        except (TypeError, ValueError):
            continue
        if periodo_riga != periodo:
            continue
        candidati.append(riga)
    return candidati


# ── Riallineamento della competenza dei bonifici gia' registrati (PR 13) ────

def _chiave_dipendente(riga: Dict[str, Any]) -> Tuple[str, ...]:
    """Identita' del dipendente della riga: id anagrafico, altrimenti il nome."""
    dipendente_id = str(riga.get("dipendente_id") or "").strip()
    if dipendente_id:
        return ("id", dipendente_id)
    return ("nome",) + tuple(sorted(_tokens(_nome_riga_stipendio(riga))))


def _periodo_riga(riga: Dict[str, Any]) -> Optional[Tuple[int, int]]:
    try:
        periodo = (int(riga.get("mese") or 0), int(riga.get("anno") or 0))
    except (TypeError, ValueError):
        return None
    return periodo if 1 <= periodo[0] <= 12 and periodo[1] >= 2000 else None


def _importo_movimento(movimento: Dict[str, Any]) -> float:
    try:
        return round(abs(float(movimento.get("importo") or 0)), 2)
    except (TypeError, ValueError):
        return 0.0


def campi_riga_da_movimenti_stipendio(
    riga: Dict[str, Any], movimenti: List[Dict[str, Any]], now: str,
) -> Dict[str, Any]:
    """Stato di pagamento della riga ricalcolato dai movimenti collegati.

    Stessa forma scritta da ``associa_bonifici_stipendi``; una riga senza
    movimenti torna allo stato iniziale dell'import (bonifico 0, saldo
    negativo pari al netto, nessuno stato bonifico).
    """
    busta = _importo_atteso(riga)
    ordinati = sorted(movimenti, key=lambda m: (str(m.get("data") or ""), str(m.get("id") or "")))
    pagato = round(sum(_importo_movimento(m) for m in ordinati), 2)
    if not ordinati:
        return {
            "movimenti_bancari_ids": [],
            "importo_bonifico": 0,
            "saldo": round(-busta, 2),
            "riconciliato": False,
            "stato_bonifico": None,
            "pagato_con": None,
            "data_pagamento": None,
            "updated_at": now,
        }
    saldo = round(busta - pagato, 2)
    completata = abs(saldo) <= 0.009
    return {
        "movimenti_bancari_ids": [str(m.get("id")) for m in ordinati],
        "importo_bonifico": pagato,
        "saldo": 0.0 if completata else saldo,
        "riconciliato": completata,
        "stato_bonifico": "riconciliato" if completata else "parzialmente_riconciliato",
        "pagato_con": "bonifico",
        "data_pagamento": str(ordinati[-1].get("data") or "")[:10],
        "updated_at": now,
    }


async def riallinea_competenza_bonifici_stipendi(
    db,
    *,
    dry_run: bool = True,
    anno: Optional[int] = None,
    actor: Optional[str] = None,
) -> Dict[str, Any]:
    """Porta ogni bonifico gia' collegato sulla busta del periodo giusto.

    Per ogni riferimento bancario di ``prima_nota_salari`` ricalcola il
    periodo atteso (causale, altrimenti regola del giorno 25). Se la riga
    e' di un altro periodo:

    - ``spostamenti``: esiste UNA sola riga dello stesso dipendente per il
      periodo atteso con residuo capiente -> il bonifico passa a quella
      (importi, saldo, stato, ``movimenti_bancari_ids``, ``stipendio_id``
      sul movimento, relazione ``allocates_salary_payment`` revocata e
      ricreata);
    - ``senza_destinazione``: la riga del periodo atteso non esiste (es.
      gennaio 2026 assente in prima nota) -> il bonifico viene STACCATO
      dalla riga sbagliata e il movimento torna da riconciliare: quando la
      riga giusta verra' creata, l'associazione ordinaria lo aggancera' da
      sola. Non si inventa un cedolino;
    - ``ambigui``: piu' righe candidate (mensile + tredicesima dello stesso
      mese) -> nessuna scelta automatica, resta com'e'.

    Idempotente: una seconda esecuzione non trova piu' nulla da fare.
    ``dry_run=True`` non scrive niente.
    """
    filtro: Dict[str, Any] = dict(FILTRO_MOVIMENTO_ATTIVO)
    if anno:
        filtro["anno"] = int(anno)
    righe = await db["prima_nota_salari"].find(filtro, {"_id": 0}).to_list(20000)
    if anno:
        # Le destinazioni possono stare nell'anno precedente (bonifico di
        # gennaio -> dicembre): servono anche quelle righe.
        righe_prec = await db["prima_nota_salari"].find(
            {"anno": int(anno) - 1, **FILTRO_MOVIMENTO_ATTIVO}, {"_id": 0}
        ).to_list(20000)
        righe = righe + [r for r in righe_prec if r.get("id") not in {x.get("id") for x in righe}]
    per_id = {str(r.get("id")): r for r in righe if r.get("id")}
    per_dipendente_periodo: Dict[Tuple[Any, ...], List[Dict[str, Any]]] = {}
    for riga in righe:
        periodo = _periodo_riga(riga)
        if periodo:
            per_dipendente_periodo.setdefault((_chiave_dipendente(riga), periodo), []).append(riga)

    # Stato simulato: id riga -> lista movimenti attualmente collegati.
    movimenti_cache: Dict[str, Optional[Dict[str, Any]]] = {}

    async def _movimento(movimento_id: str) -> Optional[Dict[str, Any]]:
        if movimento_id not in movimenti_cache:
            movimenti_cache[movimento_id] = await db["estratto_conto_movimenti"].find_one(
                {"id": movimento_id}, {"_id": 0}
            )
        return movimenti_cache[movimento_id]

    collegati: Dict[str, List[Dict[str, Any]]] = {}
    esito: Dict[str, Any] = {
        "dry_run": dry_run,
        "motivo": MOTIVO_RIALLINEO_COMPETENZA,
        "regola": f"causale esplicita, altrimenti giorno < {GIORNO_CAMBIO_COMPETENZA} = mese precedente",
        "righe_esaminate": len(righe),
        "movimenti_esaminati": 0,
        "coerenti": 0,
        "riferimenti_non_verificati": 0,
        "spostamenti": [],
        "senza_destinazione": [],
        "ambigui": [],
    }
    righe_toccate: set = set()
    movimenti_da_staccare: List[Tuple[Dict[str, Any], Dict[str, Any], Tuple[int, int]]] = []

    for riga in sorted(righe, key=lambda r: (int(r.get("anno") or 0), int(r.get("mese") or 0), str(r.get("id")))):
        riga_id = str(riga.get("id") or "")
        ids = _movimento_ids_stipendio(riga)
        if not riga_id or not ids:
            continue
        for movimento_id in ids:
            movimento = await _movimento(movimento_id)
            esito["movimenti_esaminati"] += 1
            if not movimento:
                esito["riferimenti_non_verificati"] += 1
                continue
            collegati.setdefault(riga_id, []).append(movimento)

    for riga_id, movimenti in list(collegati.items()):
        riga = per_id[riga_id]
        periodo_riga = _periodo_riga(riga)
        for movimento in list(movimenti):
            descrizione = movimento.get("descrizione_originale") or movimento.get("descrizione") or ""
            atteso = periodo_atteso_bonifico(descrizione, movimento.get("data"))
            if atteso is None or periodo_riga is None or atteso == periodo_riga:
                esito["coerenti"] += 1
                continue
            importo = _importo_movimento(movimento)
            sintesi = {
                "movimento_id": movimento.get("id"),
                "data": str(movimento.get("data") or "")[:10],
                "importo": importo,
                "dipendente": _nome_riga_stipendio(riga),
                "da": {"id": riga_id, "mese": periodo_riga[0], "anno": periodo_riga[1]},
                "periodo_atteso": {"mese": atteso[0], "anno": atteso[1]},
            }
            candidate = [
                r for r in per_dipendente_periodo.get((_chiave_dipendente(riga), atteso), [])
                if str(r.get("id")) != riga_id
            ]
            capienti = []
            for candidata in candidate:
                cid = str(candidata.get("id"))
                pagato = round(sum(_importo_movimento(m) for m in collegati.get(cid, [])), 2)
                residuo = round(_importo_atteso(candidata) - pagato, 2)
                if importo - residuo <= 0.009 and residuo > 0:
                    capienti.append(candidata)
            if len(capienti) > 1:
                esito["ambigui"].append({**sintesi, "candidate": [str(c.get("id")) for c in capienti]})
                continue
            if not capienti:
                esito["senza_destinazione"].append(sintesi)
                movimenti.remove(movimento)
                movimenti_da_staccare.append((riga, movimento, atteso))
                righe_toccate.add(riga_id)
                continue
            destinazione = capienti[0]
            dest_id = str(destinazione.get("id"))
            movimenti.remove(movimento)
            collegati.setdefault(dest_id, []).append(movimento)
            righe_toccate.update({riga_id, dest_id})
            esito["spostamenti"].append({
                **sintesi,
                "a": {"id": dest_id, "mese": atteso[0], "anno": atteso[1]},
            })

    esito["totale_da_riallineare"] = len(esito["spostamenti"]) + len(esito["senza_destinazione"])
    if dry_run:
        return esito

    now = datetime.now(timezone.utc).isoformat()
    relazioni_revocate = relazioni_create = 0
    for riga_id in sorted(righe_toccate):
        riga = per_id[riga_id]
        await db["prima_nota_salari"].update_one(
            {"id": riga_id},
            {"$set": {
                **campi_riga_da_movimenti_stipendio(riga, collegati.get(riga_id, []), now),
                "riallineo_competenza": MOTIVO_RIALLINEO_COMPETENZA,
            }},
        )
        riga.update(campi_riga_da_movimenti_stipendio(riga, collegati.get(riga_id, []), now))

    for spostamento in esito["spostamenti"]:
        movimento = movimenti_cache[spostamento["movimento_id"]]
        origine, destinazione = per_id[spostamento["da"]["id"]], per_id[spostamento["a"]["id"]]
        await db["estratto_conto_movimenti"].update_one(
            {"id": movimento["id"]},
            {"$set": {
                "stipendio_id": destinazione["id"],
                "dipendente": _nome_riga_stipendio(destinazione),
                "riallineo_competenza": MOTIVO_RIALLINEO_COMPETENZA,
                "riallineo_competenza_at": now,
                "updated_at": now,
            }},
        )
        if await revoke_entity_relation(
            db, source_type="bank_movement", source_id=str(movimento["id"]),
            relation_type="allocates_salary_payment", target_type="salary_entry",
            target_id=str(origine["id"]), actor=actor or "riallineo_competenza",
        ):
            relazioni_revocate += 1
        try:
            await record_salary_reconciliation(
                db, salary_entry=destinazione, movement=movimento,
                amount=spostamento["importo"], employee_name=_nome_riga_stipendio(destinazione),
            )
            relazioni_create += 1
        except Exception:
            logger.exception(
                "Errore relazione stipendio %s / movimento %s nel riallineo",
                destinazione.get("id"), movimento.get("id"),
            )

    for riga, movimento, atteso in movimenti_da_staccare:
        await db["estratto_conto_movimenti"].update_one(
            {"id": movimento["id"]},
            {"$set": {
                "riconciliato": False,
                "stipendio_id": None,
                "tipo_riconciliazione": None,
                "categoria": "Stipendi",
                "riallineo_competenza": MOTIVO_RIALLINEO_COMPETENZA,
                "riallineo_competenza_at": now,
                "riallineo_periodo_atteso": f"{atteso[0]:02d}/{atteso[1]}",
                "updated_at": now,
            }},
        )
        if await revoke_entity_relation(
            db, source_type="bank_movement", source_id=str(movimento["id"]),
            relation_type="allocates_salary_payment", target_type="salary_entry",
            target_id=str(riga["id"]), actor=actor or "riallineo_competenza",
        ):
            relazioni_revocate += 1

    esito.update({
        "eseguita_at": now,
        "righe_aggiornate": len(righe_toccate),
        "spostamenti_applicati": len(esito["spostamenti"]),
        "movimenti_staccati": len(movimenti_da_staccare),
        "relazioni_revocate": relazioni_revocate,
        "relazioni_create": relazioni_create,
    })
    if righe_toccate:
        try:
            await db["prima_nota_migrazioni_audit"].insert_one({
                "id": str(uuid.uuid4()),
                "migrazione": MOTIVO_RIALLINEO_COMPETENZA,
                "actor": actor or "sistema",
                "created_at": now,
                "risultato": {k: v for k, v in esito.items() if k not in ("spostamenti", "senza_destinazione", "ambigui")},
                "spostamenti": esito["spostamenti"],
                "senza_destinazione": esito["senza_destinazione"],
            })
        except Exception:  # pragma: no cover - l'audit non deve bloccare il riallineo
            logger.exception("Audit del riallineo competenza stipendi non scritto")
        logger.warning(
            "[riallineo competenza stipendi] spostati %s, staccati %s, righe aggiornate %s",
            len(esito["spostamenti"]), len(movimenti_da_staccare), len(righe_toccate),
        )
    return esito


async def recupera_relazioni_stipendi_mancanti(
    db,
    *,
    anno: Optional[int] = None,
    stipendio_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Ricrea soltanto relazioni stipendio gia' dimostrate dalle sorgenti.

    La presenza dell'ID bancario sulla riga salario e' necessaria ma non
    sufficiente: il movimento deve esistere, essere un'uscita e superare le
    stesse verifiche di identita', periodo/data e residuo dell'associazione
    ordinaria. La funzione non modifica salari o movimenti ed e' idempotente.
    """
    filtro: Dict[str, Any] = dict(FILTRO_MOVIMENTO_ATTIVO)
    if anno:
        filtro["anno"] = int(anno)
    if stipendio_id:
        filtro["id"] = stipendio_id
    righe = await db["prima_nota_salari"].find(
        filtro, {"_id": 0}
    ).to_list(5000)

    result: Dict[str, Any] = {
        "righe_esaminate": len(righe),
        "riferimenti_bancari_esaminati": 0,
        "relazioni_recuperate": 0,
        "relazioni_gia_presenti": 0,
        "riferimenti_non_verificati": 0,
        "errori": 0,
    }
    for riga in righe:
        salary_id = str(riga.get("id") or "").strip()
        movement_ids = _movimento_ids_stipendio(riga)
        if not salary_id or not movement_ids:
            continue

        movimenti: List[Dict[str, Any]] = []
        for movement_id in movement_ids:
            result["riferimenti_bancari_esaminati"] += 1
            movimento = await db["estratto_conto_movimenti"].find_one(
                {"id": movement_id}, {"_id": 0}
            )
            if not movimento:
                result["riferimenti_non_verificati"] += 1
                continue
            try:
                importo_grezzo = float(movimento.get("importo") or 0)
            except (TypeError, ValueError):
                result["riferimenti_non_verificati"] += 1
                continue
            if importo_grezzo == 0 or not (
                movimento.get("tipo") == "uscita" or importo_grezzo < 0
            ):
                result["riferimenti_non_verificati"] += 1
                continue
            movimenti.append(movimento)

        riga_verifica = dict(riga)
        riga_verifica["riconciliato"] = False
        riga_verifica["importo_bonifico"] = 0.0
        for movimento in sorted(
            movimenti,
            key=lambda item: (
                str(item.get("data") or ""), str(item.get("id") or "")
            ),
        ):
            importo = round(abs(float(movimento.get("importo") or 0)), 2)
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
                dipendente_id=riga.get("dipendente_id"),
                allow_partial=True,
            )
            if len(candidati) != 1:
                result["riferimenti_non_verificati"] += 1
                continue

            movement_id = str(movimento.get("id") or "").strip()
            key = relation_key(
                "bank_movement", movement_id, "allocates_salary_payment",
                "salary_entry", salary_id,
            )
            try:
                existing = await db[COLL_ENTITY_RELATIONS].find_one({
                    "relation_key": key,
                    "status": {"$ne": "revoked"},
                })
                await record_salary_reconciliation(
                    db,
                    salary_entry=riga,
                    movement=movimento,
                    amount=importo,
                    employee_name=_nome_riga_stipendio(riga),
                )
                if existing:
                    result["relazioni_gia_presenti"] += 1
                else:
                    result["relazioni_recuperate"] += 1
            except Exception:
                result["errori"] += 1
                logger.exception(
                    "Errore recupero relazione stipendio %s / movimento %s",
                    salary_id,
                    movement_id,
                )
                continue

            pagato = round(
                float(riga_verifica.get("importo_bonifico") or 0) + importo, 2
            )
            riga_verifica["importo_bonifico"] = pagato
            riga_verifica["riconciliato"] = (
                abs(_importo_atteso(riga_verifica) - pagato) <= 0.009
            )
    return result


async def associa_bonifici_stipendi(
    db, stipendio_id: Optional[str] = None, anno: Optional[int] = None,
    allow_partial: bool = True,
) -> Dict[str, Any]:
    """Riconcilia solo match bancari certi e univoci."""
    nomi_arricchiti = await arricchisci_nomi_salari_da_cedolini(db)
    # Prima di associare altro, i bonifici gia' collegati devono stare sul
    # periodo giusto (regola del giorno 25): e' lo stesso motore, non un
    # comando di manutenzione a parte. Solo nelle esecuzioni batch.
    riallineo_competenza: Optional[Dict[str, Any]] = None
    if not stipendio_id:
        try:
            riallineo_competenza = await riallinea_competenza_bonifici_stipendi(
                db, dry_run=False, anno=anno, actor="associa_bonifici_stipendi",
            )
        except Exception:
            logger.exception("Riallineo competenza bonifici stipendi non completato")
            riallineo_competenza = {"errore": True}
    try:
        recupero_relazioni = await recupera_relazioni_stipendi_mancanti(
            db, anno=anno, stipendio_id=stipendio_id,
        )
    except Exception:
        logger.exception("Errore generale nel recupero relazioni stipendio")
        recupero_relazioni = {
            "righe_esaminate": 0,
            "riferimenti_bancari_esaminati": 0,
            "relazioni_recuperate": 0,
            "relazioni_gia_presenti": 0,
            "riferimenti_non_verificati": 0,
            "errori": 1,
        }
    filtro: Dict[str, Any] = {"riconciliato": {"$ne": True}, **FILTRO_MOVIMENTO_ATTIVO}
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
            allow_partial=allow_partial,
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
        "recupero_relazioni": recupero_relazioni,
        "riallineo_competenza": riallineo_competenza,
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

    movimento_ids = _movimento_ids_stipendio(riga)
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


# ── CLI ──────────────────────────────────────────────────────────────────────

async def _main_async(dry_run: bool, anno: Optional[int]) -> Dict[str, Any]:
    from app.database import Database

    await Database.connect_db()
    try:
        return await riallinea_competenza_bonifici_stipendi(
            Database.get_db(), dry_run=dry_run, anno=anno, actor="cli",
        )
    finally:
        await Database.close_db()


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Riallinea la competenza dei bonifici stipendio gia' collegati "
            "(regola del giorno 25). Default: solo analisi."
        ),
    )
    parser.add_argument("--applica", action="store_true", help="scrive davvero le modifiche")
    parser.add_argument("--anno", type=int, default=None, help="limita a un anno contabile")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    risultato = asyncio.run(_main_async(dry_run=not args.applica, anno=args.anno))
    print(json.dumps(risultato, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
