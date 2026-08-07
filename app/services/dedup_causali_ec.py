"""Duplicati di estratto conto nati da causali con prefisso diverso.

Il caso reale (07/08/2026): lo stesso addebito WORLDPAY compare come
``SDD CORE: M-...`` in un export e come ``ADDEBITO DIRETTO SDD - SDD CORE:
M-...`` nell'altro. Stessa data, stesso importo, stesso mandato — ma la
deduplica dell'import confrontava le descrizioni grezze, e le due forme
entravano entrambe.

L'import ora normalizza i prefissi (``normalizza_descrizione_ec``); questo
modulo ripara lo STORICO gia' doppio. Il punto delicato e' il conteggio:
tre addebiti da 1,79 nello stesso giorno possono essere TRE operazioni vere.
La verita' e' il singolo file: ogni estratto elenca le operazioni del giorno
per intero, quindi il numero reale di operazioni e' il MASSIMO di righe che
un solo file porta per quel gruppo. Le righe oltre quel numero sono la
seconda copia.

Niente cancellazioni (regola utente): il doppione viene marcato riconciliato
con ``tipo_riconciliazione = "duplicato_causale"`` e il riferimento alla riga
conservata — esce dalle code e dai saldi operativi, ma resta leggibile.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.routers.bank.estratto_conto import normalizza_descrizione_ec

COLLEZIONE = "estratto_conto_movimenti"
LIMITE_DOCUMENTI = 100000
TIPO_RICONCILIAZIONE = "duplicato_causale"


def _chiave(riga: Dict[str, Any]) -> tuple:
    return (
        str(riga.get("data") or "")[:10],
        round(abs(float(riga.get("importo") or 0)), 2),
        normalizza_descrizione_ec(
            riga.get("descrizione_originale") or riga.get("descrizione") or ""
        ),
    )


def _priorita_conservazione(riga: Dict[str, Any]) -> tuple:
    """Chi resta, a parita' di gruppo: prima chi porta gia' lavoro sopra."""
    return (
        0 if riga.get("riconciliato") else 1,          # riconciliata: mai toccarla
        0 if riga.get("importato_prima_nota") else 1,  # gia' in Prima Nota
        0 if riga.get("evidenza_bancaria_ufficiale") else 1,
        str(riga.get("created_at") or ""),             # poi la piu' vecchia
    )


def _gruppi_sospetti(righe: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    gruppi: Dict[tuple, List[Dict[str, Any]]] = defaultdict(list)
    for riga in righe:
        gruppi[_chiave(riga)].append(riga)

    sospetti = []
    for gruppo in gruppi.values():
        if len(gruppo) < 2:
            continue
        forme = {
            (r.get("descrizione_originale") or r.get("descrizione") or "").strip()
            for r in gruppo
        }
        # Con una forma sola la deduplica per occorrenza ha gia' fatto il suo
        # lavoro all'import: N righe identiche = N operazioni dichiarate dal
        # file. Qui interessano solo le forme miste (prefisso si'/no).
        if len(forme) < 2:
            continue
        sospetti.append(gruppo)
    return sospetti


def _piano_per_gruppo(gruppo: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Quante righe tenere e quali marcare, per un gruppo a forme miste."""
    per_file: Dict[str, int] = defaultdict(int)
    for riga in gruppo:
        per_file[str(riga.get("source_filename") or f"sconosciuto:{riga.get('id')}")] += 1
    reali = max(per_file.values())
    if len(gruppo) <= reali:
        return None

    ordinate = sorted(gruppo, key=_priorita_conservazione)
    return {"tenere": ordinate[:reali], "marcare": ordinate[reali:]}


async def analizza(db) -> Dict[str, Any]:
    """Fotografia in sola lettura: quanti doppioni e dove."""
    righe = await db[COLLEZIONE].find(
        {"riconciliato": {"$ne": True}},
        {"_id": 0, "id": 1, "data": 1, "importo": 1, "descrizione": 1,
         "descrizione_originale": 1, "source_filename": 1, "created_at": 1,
         "riconciliato": 1, "importato_prima_nota": 1,
         "evidenza_bancaria_ufficiale": 1},
    ).to_list(LIMITE_DOCUMENTI)

    gruppi = _gruppi_sospetti(righe)
    piani = [p for p in (_piano_per_gruppo(g) for g in gruppi) if p]
    esempi = [{
        "data": p["marcare"][0].get("data"),
        "importo": p["marcare"][0].get("importo"),
        "tenute": len(p["tenere"]),
        "doppioni": len(p["marcare"]),
        "descrizioni": sorted({
            (r.get("descrizione_originale") or r.get("descrizione") or "")[:70]
            for r in p["tenere"] + p["marcare"]
        }),
    } for p in piani[:30]]

    return {
        "gruppi_con_forme_miste": len(gruppi),
        "gruppi_con_doppioni": len(piani),
        "righe_da_marcare": sum(len(p["marcare"]) for p in piani),
        "esempi": esempi,
        "nota": ("Sola lettura: nessuna riga toccata. Il conteggio reale di un "
                 "gruppo e' il massimo di righe portate da un singolo file."),
    }


async def applica(db, actor: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Marca i doppioni. Mai cancellazioni: restano leggibili e tracciati."""
    fotografia = await analizza(db)

    righe = await db[COLLEZIONE].find(
        {"riconciliato": {"$ne": True}},
        {"_id": 0, "id": 1, "data": 1, "importo": 1, "descrizione": 1,
         "descrizione_originale": 1, "source_filename": 1, "created_at": 1,
         "riconciliato": 1, "importato_prima_nota": 1,
         "evidenza_bancaria_ufficiale": 1},
    ).to_list(LIMITE_DOCUMENTI)

    adesso = datetime.now(timezone.utc).isoformat()
    marcate = 0
    for gruppo in _gruppi_sospetti(righe):
        piano = _piano_per_gruppo(gruppo)
        if not piano:
            continue
        conservata = piano["tenere"][0]
        for doppione in piano["marcare"]:
            await db[COLLEZIONE].update_one(
                {"id": doppione["id"], "riconciliato": {"$ne": True}},
                {"$set": {
                    "riconciliato": True,
                    "tipo_riconciliazione": TIPO_RICONCILIAZIONE,
                    "dettagli_riconciliazione": {
                        "riga_conservata_id": conservata.get("id"),
                        "motivo": "stessa operazione con causale prefissata",
                        "marcato_da": (actor or {}).get("user_id") or "manutenzione",
                        "marcato_il": adesso,
                    },
                }, "$unset": {"stato_riconciliazione": ""}},
            )
            marcate += 1

    return {**fotografia, "righe_marcate": marcate, "success": True}
