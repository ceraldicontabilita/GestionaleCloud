"""Righe di ingrediente di una ricetta: cos'è una dose, cosa non è un ingrediente.

Sui dati veri (27/09/2026) 103 ricette su 318 non avevano nessuna dose, e 198
«ingredienti» erano intestazioni del vecchio ricettario importato («Peso
impasto totale (g)», «Pezzi prodotti (n)»). La produzione saltava in silenzio
gli ingredienti senza dose: dichiarava «0 lotti scalati» senza dire perché, e
il magazzino delle materie prime non scendeva mai. Qui c'è la regola unica;
chi scala il magazzino, chi calcola il costo e chi elenca le ricette da
completare la leggono da qui.
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Optional

# Intestazioni del ricettario Excel finite fra gli ingredienti: sono dati della
# ricetta (peso dell'impasto, resa in pezzi), non materie prime da scalare.
_INTESTAZIONE_RE = re.compile(
    r"^\s*(peso\s+(impasto|totale)|pezzi\s+prodott|resa\b|totale\s+(impasto|peso))",
    re.IGNORECASE,
)


def e_riga_intestazione(nome: Any) -> bool:
    return bool(_INTESTAZIONE_RE.match(str(nome or "")))


def dose(ingrediente: dict) -> Optional[float]:
    """La quantità dell'ingrediente, o ``None`` se non c'è. Uno zero, un testo
    o un numero negativo non sono una dose: la ricetta va completata."""
    valore = ingrediente.get("quantita")
    if valore in (None, ""):
        return None
    try:
        numero = float(str(valore).replace(",", "."))
    except (TypeError, ValueError):
        return None
    return numero if numero > 0 else None


def righe_ingredienti(ricetta: dict) -> list[dict]:
    """Solo gli ingredienti veri, con un nome, nell'ordine della ricetta."""
    righe = []
    for ing in ricetta.get("ingredienti_dettaglio") or []:
        if not isinstance(ing, dict):
            continue
        nome = str(ing.get("nome") or "").strip()
        if nome and not e_riga_intestazione(nome):
            righe.append(ing)
    return righe


def ingredienti_senza_dose(ricetta: dict) -> list[str]:
    return [str(i.get("nome")).strip() for i in righe_ingredienti(ricetta) if dose(i) is None]


def stato_dosi(ricetta: dict) -> dict:
    righe = righe_ingredienti(ricetta)
    mancanti = [str(i.get("nome")).strip() for i in righe if dose(i) is None]
    return {
        "ingredienti": len(righe),
        "senza_dose": mancanti,
        "completa": bool(righe) and not mancanti,
    }


def ricette_da_completare(ricette: Iterable[dict], reparto: Optional[str] = None) -> list[dict]:
    """Ricette con almeno un ingrediente senza dose (o senza ingredienti),
    prima quelle a cui ne mancano di più."""
    esito = []
    for r in ricette:
        if reparto and str(r.get("reparto") or "").lower() != reparto.lower():
            continue
        stato = stato_dosi(r)
        if stato["completa"]:
            continue
        esito.append({
            "id": r.get("id"),
            "nome": r.get("nome"),
            "reparto": r.get("reparto") or "",
            "ingredienti": stato["ingredienti"],
            "senza_dose": stato["senza_dose"],
        })
    esito.sort(key=lambda x: (-len(x["senza_dose"]), str(x["nome"] or "").lower()))
    return esito
