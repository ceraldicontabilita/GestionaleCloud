"""Classificazione prudente della destinazione dei bonifici.

Un pagamento riconducibile a un dipendente non deve mai essere proposto come
pagamento di una fattura fornitore. La classificazione usa marcatori gia'
salvati, IBAN, identita' completa e causali esplicitamente retributive.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable

from app.database import Collections
from app.services.identity_matching import identita_coincide, nome_presente_nel_testo


_CAUSALE_RETRIBUTIVA = re.compile(
    r"\b(stipendi?o|salari?o|retribuzione|cedolino|emolumenti|"
    r"competenze\s+(?:mese|mensili)|paga\s+(?:mese|mensile)|"
    r"(?:acconto|saldo)\s+stipendi?o|tfr|trattamento\s+di\s+fine\s+rapporto)\b",
    re.IGNORECASE,
)


# Una causale che cita una fattura dice che e' un fornitore, anche col nome di un dipendente
# (l'esclusione vince sul nome, stessa regola del ponte HR): la pagina propone la fattura, non il periodo.
_CAUSALE_FATTURA = re.compile(r"fattur|\bFPR\b|\bFT\b\s*\d", re.IGNORECASE)


def _testo_bancario(bonifico: Dict[str, Any]) -> str:
    """Unisce solo i campi probatori del movimento bancario."""
    nome_beneficiario, iban_beneficiario = _beneficiario(bonifico)
    return " ".join(
        str(value or "")
        for value in (
            nome_beneficiario,
            iban_beneficiario,
            bonifico.get("causale"),
            bonifico.get("descrizione"),
            bonifico.get("descrizione_originale"),
            bonifico.get("ordinante"),
        )
        if value
    ).strip()


def _codice_fiscale(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def _beneficiario(bonifico: Dict[str, Any]) -> tuple[str, str]:
    value = bonifico.get("beneficiario") or {}
    if isinstance(value, dict):
        nome = value.get("nome") or value.get("denominazione") or ""
        iban = value.get("iban") or ""
    else:
        nome = str(value)
        iban = bonifico.get("iban_beneficiario") or ""
    return str(nome).strip(), re.sub(r"\s+", "", str(iban)).upper()


_RE_BENEFICIARIO = re.compile(r"\bFAVORE\s+(.+?)(?:\s+-\s+|$)", re.IGNORECASE)


def _candidato_per_cognome(dipendenti: Iterable[Dict[str, Any]], testo: str) -> list:
    """Ultimo gradino della scala di CLAUDE.md (CF -> nome completo ->
    cognome univoco), con lo stesso risolutore del ponte HR: la banca tronca
    il beneficiario («SANKAPALA ARACHCHILAGE JANANIE AYAC») e il nome completo
    non c'e' piu'. Mai quando la causale dice che e' altro (fattura, TFR,
    fornitore, commissione): l'esclusione vince sul nome."""
    from app.hr.routers.dipendenti_cloud import indici_da_dipendenti
    from app.services.hr_pagamenti_deposito import e_pagamento_non_stipendio, risolvi_dipendente

    elenco = list(dipendenti)
    if not testo or not elenco or e_pagamento_non_stipendio(testo):
        return []
    # Solo il beneficiario, e solo se comincia col cognome: la banca scrive
    # «FAVORE COGNOME NOME». Un cognome che e' anche un nome proprio o una
    # parola (Mauro, Palma, Vespa) altrove nella causale non basta.
    beneficiario = _RE_BENEFICIARIO.search(testo)
    if not beneficiario:
        return []
    beneficiario = re.sub(r"\s+", " ", beneficiario.group(1)).strip().lower()
    dipendente, motivo = risolvi_dipendente(indici_da_dipendenti(elenco), beneficiario)
    if motivo != "cognome" or not dipendente:
        return []
    cognome = re.sub(r"\s+", " ", str(dipendente.get("cognome") or "")).strip().lower()
    if not cognome or not beneficiario.startswith(cognome):
        return []
    nome = (
        dipendente.get("nome_completo")
        or f"{dipendente.get('nome', '')} {dipendente.get('cognome', '')}".strip()
    )
    return [(dipendente, nome, "cognome_univoco")]


def classifica_destinazione_dipendente(
    bonifico: Dict[str, Any], dipendenti: Iterable[Dict[str, Any]]
) -> Dict[str, Any]:
    """Restituisce una classificazione spiegabile, senza scegliere tra omonimi."""
    nome_beneficiario, iban_beneficiario = _beneficiario(bonifico)
    testo_bancario = _testo_bancario(bonifico)
    testo_codici = _codice_fiscale(testo_bancario)

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
            "dipendente_id": bonifico.get("dipendente_id"),
            "identita_univoca": bool(bonifico.get("dipendente_id")),
        }

    if _CAUSALE_FATTURA.search(testo_bancario) and not _CAUSALE_RETRIBUTIVA.search(testo_bancario):
        return {
            "destinazione_dipendente": False,
            "motivo_destinazione": "causale_fattura",
            "dipendente_nome_rilevato": None,
            "dipendente_id": None,
            "identita_univoca": False,
        }

    candidati_iban = []
    candidati_codice_fiscale = []
    candidati_nome = []
    for dip in dipendenti:
        nome = (
            dip.get("nome_completo")
            or f"{dip.get('nome', '')} {dip.get('cognome', '')}".strip()
        )
        iban = re.sub(r"\s+", "", str(dip.get("iban") or "")).upper()
        codice_fiscale = _codice_fiscale(
            dip.get("codice_fiscale") or dip.get("cf")
        )
        if iban_beneficiario and iban and iban_beneficiario == iban:
            candidati_iban.append((dip, nome, "iban_dipendente"))
        if codice_fiscale and codice_fiscale in testo_codici:
            candidati_codice_fiscale.append(
                (dip, nome, "codice_fiscale_dipendente")
            )
        elif nome_beneficiario and nome and identita_coincide(nome_beneficiario, nome):
            candidati_nome.append((dip, nome, "identita_dipendente"))
        elif nome and nome_presente_nel_testo(nome, testo_bancario):
            candidati_nome.append(
                (dip, nome, "nome_completo_nella_descrizione")
            )

    # IBAN e codice fiscale sono entrambe prove forti. Se puntano a persone
    # diverse non scegliamo arbitrariamente: il movimento resta sospeso e,
    # soprattutto, non viene proposto come pagamento di una fattura.
    identita_iban = {
        str(dip.get("id") or nome) for dip, nome, _ in candidati_iban
    }
    identita_codice_fiscale = {
        str(dip.get("id") or nome)
        for dip, nome, _ in candidati_codice_fiscale
    }
    if (
        identita_iban
        and identita_codice_fiscale
        and identita_iban != identita_codice_fiscale
    ):
        return {
            "destinazione_dipendente": True,
            "motivo_destinazione": "conflitto_iban_codice_fiscale",
            "dipendente_nome_rilevato": None,
            "dipendente_id": None,
            "identita_univoca": False,
        }

    # Una prova forte prevale sul solo nome. Questo consente di distinguere
    # correttamente due omonimi quando la banca espone CF o IBAN.
    candidati = (
        candidati_iban
        or candidati_codice_fiscale
        or candidati_nome
        or _candidato_per_cognome(dipendenti, testo_bancario)
    )

    # Un solo riscontro anagrafico e' utilizzabile; gli omonimi restano ambigui.
    identita_uniche = {str(dip.get("id") or nome) for dip, nome, _ in candidati}
    if len(identita_uniche) == 1 and candidati:
        dipendente, nome, motivo = candidati[0]
        return {
            "destinazione_dipendente": True,
            "motivo_destinazione": motivo,
            "dipendente_nome_rilevato": nome,
            "dipendente_id": dipendente.get("id"),
            "dipendente_codice_fiscale": (
                dipendente.get("codice_fiscale") or dipendente.get("cf")
            ),
            "identita_univoca": True,
            "tipo_retribuzione": (
                "tfr"
                if re.search(r"\b(?:tfr|trattamento\s+di\s+fine\s+rapporto)\b", testo_bancario, re.I)
                else "stipendio"
            ),
        }

    if _CAUSALE_RETRIBUTIVA.search(testo_bancario):
        return {
            "destinazione_dipendente": True,
            "motivo_destinazione": "causale_retributiva",
            "dipendente_nome_rilevato": None,
            "dipendente_id": None,
            "identita_univoca": False,
            "tipo_retribuzione": (
                "tfr"
                if re.search(r"\b(?:tfr|trattamento\s+di\s+fine\s+rapporto)\b", testo_bancario, re.I)
                else "stipendio"
            ),
        }

    return {
        "destinazione_dipendente": False,
        "motivo_destinazione": "nessuna_evidenza_dipendente",
        "dipendente_nome_rilevato": None,
        "dipendente_id": None,
        "identita_univoca": False,
    }


async def classifica_bonifico_dipendente(db, bonifico: Dict[str, Any]) -> Dict[str, Any]:
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
        }
    ).to_list(5000)
    return classifica_destinazione_dipendente(bonifico, dipendenti)
