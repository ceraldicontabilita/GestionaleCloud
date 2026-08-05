"""Classificazione prudente della destinazione dei bonifici.

Un pagamento riconducibile a un dipendente non deve mai essere proposto come
pagamento di una fattura fornitore. La classificazione usa marcatori gia'
salvati, IBAN, identita' completa e causali esplicitamente retributive.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable

from app.database import Collections
from app.services.identity_matching import identita_coincide


_CAUSALE_RETRIBUTIVA = re.compile(
    r"\b(stipendi?o|salari?o|retribuzione|cedolino|emolumenti|"
    r"competenze\s+(?:mese|mensili)|paga\s+(?:mese|mensile)|"
    r"(?:acconto|saldo)\s+stipendi?o)\b",
    re.IGNORECASE,
)


def _beneficiario(bonifico: Dict[str, Any]) -> tuple[str, str]:
    value = bonifico.get("beneficiario") or {}
    if isinstance(value, dict):
        nome = value.get("nome") or value.get("denominazione") or ""
        iban = value.get("iban") or ""
    else:
        nome = str(value)
        iban = bonifico.get("iban_beneficiario") or ""
    return str(nome).strip(), re.sub(r"\s+", "", str(iban)).upper()


def classifica_destinazione_dipendente(
    bonifico: Dict[str, Any], dipendenti: Iterable[Dict[str, Any]]
) -> Dict[str, Any]:
    """Restituisce una classificazione spiegabile, senza scegliere tra omonimi."""
    nome_beneficiario, iban_beneficiario = _beneficiario(bonifico)

    if (
        bonifico.get("salario_associato")
        or bonifico.get("operazione_salario_id")
        or bonifico.get("dipendente_id")
        or str(bonifico.get("stato_riconciliazione") or "").startswith("associato_salario")
    ):
        return {
            "destinazione_dipendente": True,
            "motivo_destinazione": "associazione_salario_esistente",
            "dipendente_nome_rilevato": bonifico.get("dipendente_nome"),
        }

    candidati = []
    for dip in dipendenti:
        nome = (
            dip.get("nome_completo")
            or f"{dip.get('nome', '')} {dip.get('cognome', '')}".strip()
        )
        iban = re.sub(r"\s+", "", str(dip.get("iban") or "")).upper()
        if iban_beneficiario and iban and iban_beneficiario == iban:
            candidati.append((dip, nome, "iban_dipendente"))
        elif nome_beneficiario and nome and identita_coincide(nome_beneficiario, nome):
            candidati.append((dip, nome, "identita_dipendente"))

    # Un solo riscontro anagrafico e' utilizzabile; gli omonimi restano ambigui.
    identita_uniche = {str(dip.get("id") or nome) for dip, nome, _ in candidati}
    if len(identita_uniche) == 1 and candidati:
        _, nome, motivo = candidati[0]
        return {
            "destinazione_dipendente": True,
            "motivo_destinazione": motivo,
            "dipendente_nome_rilevato": nome,
        }

    causale = str(bonifico.get("causale") or "")
    if _CAUSALE_RETRIBUTIVA.search(causale):
        return {
            "destinazione_dipendente": True,
            "motivo_destinazione": "causale_retributiva",
            "dipendente_nome_rilevato": None,
        }

    return {
        "destinazione_dipendente": False,
        "motivo_destinazione": "nessuna_evidenza_dipendente",
        "dipendente_nome_rilevato": None,
    }


async def classifica_bonifico_dipendente(db, bonifico: Dict[str, Any]) -> Dict[str, Any]:
    dipendenti = await db[Collections.EMPLOYEES].find(
        {}, {"_id": 0, "id": 1, "nome": 1, "cognome": 1, "nome_completo": 1, "iban": 1}
    ).to_list(5000)
    return classifica_destinazione_dipendente(bonifico, dipendenti)
