"""Saldo F24 per singolo tributo e proposte di pagamento parziale.

Un movimento bancario puo' saldare l'intero modello oppure una combinazione
univoca di righe a debito. Se esistono piu' combinazioni possibili il servizio
non associa nulla automaticamente.
"""
from __future__ import annotations

import hashlib
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime
from typing import Any, Dict, Iterable, List


SEZIONI = (
    "sezione_erario", "sezione_inps", "sezione_regioni",
    "sezione_tributi_locali", "sezione_inail",
)


def _centesimi(value: Any) -> int:
    try:
        return int((Decimal(str(value or 0)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except Exception:
        return 0


def _righe_sezione(value: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict) and isinstance(value.get("righe"), list):
        return value["righe"]
    return ()


def normalizza_tributi(f24: Dict[str, Any]) -> List[Dict[str, Any]]:
    righe: List[Dict[str, Any]] = []
    for sezione in SEZIONI:
        for indice, riga in enumerate(_righe_sezione(f24.get(sezione))):
            debito = _centesimi(riga.get("importo_debito"))
            credito = _centesimi(riga.get("importo_credito"))
            if debito <= 0 and credito <= 0:
                continue
            codice = str(
                riga.get("codice_tributo") or riga.get("causale")
                or riga.get("codice_sede") or ""
            ).strip()
            naturale = "|".join((
                sezione, str(indice), codice, str(riga.get("anno") or ""),
                str(riga.get("rateazione") or ""), str(debito), str(credito),
            ))
            righe.append({
                **riga,
                "tributo_id": "tr_" + hashlib.sha1(naturale.encode("utf-8")).hexdigest()[:16],
                "sezione": sezione,
                "indice": indice,
                "codice": codice,
                "debito_centesimi": debito,
                "credito_centesimi": credito,
            })
    return righe


def _allocati_per_tributo(allocazioni: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    totali: Dict[str, int] = {}
    for allocazione in allocazioni or ():
        importi = allocazione.get("importi_per_tributo") or {}
        for tributo_id, importo in importi.items():
            totali[tributo_id] = totali.get(tributo_id, 0) + _centesimi(importo)
    return totali


def saldo_tributi(f24: Dict[str, Any], allocazioni=None) -> Dict[str, Any]:
    righe = normalizza_tributi(f24)
    allocati = _allocati_per_tributo(allocazioni or f24.get("allocazioni_banca") or [])
    aperti = []
    debito = credito = pagato = 0
    for riga in righe:
        debito += riga["debito_centesimi"]
        credito += riga["credito_centesimi"]
        gia = min(allocati.get(riga["tributo_id"], 0), riga["debito_centesimi"])
        pagato += gia
        residuo = max(riga["debito_centesimi"] - gia, 0)
        if residuo:
            aperti.append({**riga, "residuo": residuo / 100})

    # Il credito compensa il documento complessivo, ma non viene attribuito
    # arbitrariamente a una singola riga a debito.
    saldo_documento = max(debito - credito, 0)
    residuo_documento = max(saldo_documento - pagato, 0)
    return {
        "debito": debito / 100,
        "credito": credito / 100,
        "saldo_documento": saldo_documento / 100,
        "pagato_banca": min(pagato, saldo_documento) / 100,
        "residuo": residuo_documento / 100,
        "righe_aperte": aperti,
        "stato": "pagato" if residuo_documento == 0 else ("parzialmente_pagato" if pagato else "da_pagare"),
    }


def _sottoinsiemi_univoci(righe: List[Dict[str, Any]], target: int):
    # Per ogni somma conserviamo al massimo due soluzioni: basta per sapere
    # che il risultato e' ambiguo senza far esplodere memoria e CPU.
    somme = {0: [()]}
    for riga in righe:
        valore = _centesimi(riga["residuo"])
        if valore <= 0 or valore > target:
            continue
        snapshot = list(somme.items())
        for parziale, soluzioni in snapshot:
            nuova = parziale + valore
            if nuova > target:
                continue
            destinazione = somme.setdefault(nuova, [])
            for soluzione in soluzioni:
                candidata = soluzione + (riga["tributo_id"],)
                if candidata not in destinazione:
                    destinazione.append(candidata)
                if len(destinazione) >= 2:
                    break
    return somme.get(target, [])


def proponi_allocazione(
    f24: Dict[str, Any], movimento: Dict[str, Any], allocazioni=None,
) -> Dict[str, Any]:
    movimento_id = str(movimento.get("id") or movimento.get("fingerprint") or "").strip()
    importo = _centesimi(abs(movimento.get("importo") or 0))
    saldo = saldo_tributi(f24, allocazioni)
    if not movimento_id or importo <= 0:
        return {"esito": "non_valido", "associazione_automatica": False}
    if any(str(a.get("movimento_id")) == movimento_id for a in (allocazioni or f24.get("allocazioni_banca") or [])):
        return {"esito": "gia_associato", "associazione_automatica": False}
    if importo > _centesimi(saldo["residuo"]):
        return {"esito": "importo_superiore_al_residuo", "associazione_automatica": False}

    # Con crediti/compensazioni si accetta automaticamente solo il saldo
    # completo. Un pagamento parziale richiede conferma per non attribuire il
    # credito alla riga sbagliata.
    if saldo["credito"] > 0 and importo != _centesimi(saldo["residuo"]):
        return {"esito": "compensazione_da_verificare", "associazione_automatica": False}

    soluzioni = _sottoinsiemi_univoci(saldo["righe_aperte"], importo)
    if len(soluzioni) != 1:
        return {
            "esito": "ambiguo" if len(soluzioni) > 1 else "nessuna_combinazione",
            "associazione_automatica": False,
            "numero_soluzioni": len(soluzioni),
        }
    ids = list(soluzioni[0])
    righe = {r["tributo_id"]: r for r in saldo["righe_aperte"]}
    importi = {tributo_id: righe[tributo_id]["residuo"] for tributo_id in ids}
    return {
        "esito": "univoco",
        "associazione_automatica": True,
        "movimento_id": movimento_id,
        "data_pagamento": movimento.get("data_contabile") or movimento.get("data"),
        "importo": importo / 100,
        "tributo_ids": ids,
        "codici_tributo": [righe[i]["codice"] for i in ids],
        "importi_per_tributo": importi,
    }


def applica_allocazione(f24: Dict[str, Any], proposta: Dict[str, Any]) -> Dict[str, Any]:
    if not proposta.get("associazione_automatica"):
        raise ValueError("La proposta non e' univoca")
    allocazioni = list(f24.get("allocazioni_banca") or [])
    if not any(str(a.get("movimento_id")) == proposta["movimento_id"] for a in allocazioni):
        allocazioni.append({
            "movimento_id": proposta["movimento_id"],
            "data_pagamento": proposta.get("data_pagamento"),
            "importo": proposta["importo"],
            "tributo_ids": proposta["tributo_ids"],
            "codici_tributo": proposta["codici_tributo"],
            "importi_per_tributo": proposta["importi_per_tributo"],
            "fonte": "estratto_conto",
        })
    saldo = saldo_tributi(f24, allocazioni)
    return {
        "allocazioni_banca": allocazioni,
        "saldo_tributi": saldo,
        "stato_pagamento": "PAGATO" if saldo["stato"] == "pagato" else "PARZIALMENTE_PAGATO_BANCA",
        "status": saldo["stato"],
        "pagato": saldo["stato"] == "pagato",
        "pagamento_verificato_banca": True,
        "fonte_prova_pagamento": "estratto_conto",
        "importo_residuo": saldo["residuo"],
    }


def proposte_globali_univoche(
    f24_list: List[Dict[str, Any]], movimenti: List[Dict[str, Any]], tolleranza_giorni: int = 3,
) -> List[Dict[str, Any]]:
    """Propone solo match univoci sia nel documento sia fra documenti diversi."""
    candidati_per_movimento: Dict[str, List[Dict[str, Any]]] = {}
    firme_movimenti: Dict[tuple, List[str]] = {}

    for movimento in movimenti:
        movimento_id = str(movimento.get("id") or movimento.get("fingerprint") or "")
        data_mov = movimento.get("data_contabile") or movimento.get("data")
        if not movimento_id or not data_mov:
            continue
        try:
            data_mov_dt = datetime.fromisoformat(str(data_mov)[:10])
        except ValueError:
            continue
        firma = (str(data_mov)[:10], _centesimi(abs(movimento.get("importo") or 0)))
        firme_movimenti.setdefault(firma, []).append(movimento_id)
        for f24 in f24_list:
            data_f24 = (f24.get("dati_generali") or {}).get("data_versamento")
            if not data_f24:
                continue
            try:
                data_f24_dt = datetime.fromisoformat(str(data_f24)[:10])
            except ValueError:
                continue
            if abs((data_f24_dt - data_mov_dt).days) > tolleranza_giorni:
                continue
            proposta = proponi_allocazione(f24, movimento)
            if proposta.get("associazione_automatica"):
                candidati_per_movimento.setdefault(movimento_id, []).append({
                    **proposta,
                    "f24_id": f24.get("id"),
                })

    # Un duplicato bancario con stessa data/importo non e' prova univoca.
    movimenti_duplicati = {
        movimento_id
        for ids in firme_movimenti.values() if len(ids) > 1
        for movimento_id in ids
    }
    univoche = [
        proposte[0] for movimento_id, proposte in candidati_per_movimento.items()
        if movimento_id not in movimenti_duplicati and len(proposte) == 1
    ]

    # Due movimenti non possono auto-saldare la stessa riga ancora aperta.
    conteggio_righe: Dict[tuple, int] = {}
    for proposta in univoche:
        for tributo_id in proposta["tributo_ids"]:
            chiave = (proposta.get("f24_id"), tributo_id)
            conteggio_righe[chiave] = conteggio_righe.get(chiave, 0) + 1
    return [
        proposta for proposta in univoche
        if all(conteggio_righe[(proposta.get("f24_id"), tid)] == 1 for tid in proposta["tributo_ids"])
    ]
