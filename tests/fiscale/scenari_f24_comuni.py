"""Costruttori comuni degli scenari funzionali F24 (`test_scenari_funzionali_*.py`).

Si sostituisce soltanto la LETTURA del PDF (i parser, che non sono il motore sotto
collaudo): modello, quietanza ed estratto conto passano poi dagli stessi servizi
di import del gestionale, con l'archivio in memoria.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app.services.archivio_documenti_memoria import ClientArchivioMemoria

CF = "01879020517"

# Riga: (sezione, codice, periodo, debito, credito); gli importi sono stringhe/Decimal.
Riga = Tuple[str, str, str, Any, Any]


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def db_nuovo(nome: str):
    return ClientArchivioMemoria()[nome]


def cents(valore: Any) -> int:
    return int((Decimal(str(valore)) * 100).quantize(Decimal("1")))


def _sezioni(righe: Iterable[Riga]) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {
        "sezione_erario": [], "sezione_inps": [], "sezione_regioni": [],
        "sezione_tributi_locali": [], "sezione_inail": [],
    }
    for sezione, codice, periodo, debito, credito in righe:
        riga = {
            "codice_tributo": codice, "periodo_riferimento": periodo,
            "importo_debito": float(Decimal(str(debito))), "importo_credito": float(Decimal(str(credito))),
        }
        if sezione == "sezione_inps":
            # come le legge il parser: sede, causale (DM10, RC01...), matricola, periodo MM/AAAA
            riga = {"codice_sede": "5100", "causale": codice, "matricola": "5124776507",
                    "periodo_riferimento": periodo, "importo_debito": riga["importo_debito"],
                    "importo_credito": riga["importo_credito"]}
        out[sezione].append(riga)
    return out


def saldo(righe: Iterable[Riga]) -> Decimal:
    return sum((Decimal(str(d)) - Decimal(str(c)) for _s, _c, _p, d, c in righe), Decimal("0"))


def modello_parsed(righe: List[Riga], data_versamento: str, *, cf: str = CF) -> Dict[str, Any]:
    s = saldo(righe)
    return {
        "dati_generali": {"codice_fiscale": cf, "data_versamento": data_versamento},
        **_sezioni(righe),
        "totali": {"totale_debito": float(sum(Decimal(str(r[3])) for r in righe)),
                   "totale_credito": float(sum(Decimal(str(r[4])) for r in righe)),
                   "saldo_netto": float(s), "saldo_netto_cents": cents(s)},
        "validazione": {"saldo_quadrato": True, "differenza_saldo": 0.0, "parser_version": "scenario-v1"},
    }


def quietanza_parsed(righe: List[Riga], data_pagamento: str, protocollo: str, *,
                     cf: str = CF, saldo_stampato: Optional[Any] = None) -> Dict[str, Any]:
    s = saldo(righe) if saldo_stampato is None else Decimal(str(saldo_stampato))
    return {
        "dati_generali": {"protocollo_telematico": protocollo, "saldo_delega": float(s),
                          "data_pagamento": data_pagamento, "codice_fiscale": cf},
        **_sezioni(righe),
        "totali": {"saldo_netto": float(s), "saldo_netto_cents": cents(s)},
        "validazione": {"saldo_quadrato": True, "differenza_saldo": 0.0, "parser_version": "scenario-v1"},
    }


def causale_i24(incasso: Optional[str] = None, progressivo: str = "2026-08-19-22.35.33.939744076309") -> str:
    testo = "I24 AGENZIA ENTRATE - PAG.TO TELEMATICO"
    if incasso:
        testo += f" - DATA INCASSO {incasso} {progressivo}"
    return testo


def collezione(db, nome: str) -> List[Dict[str, Any]]:
    return run(db[nome].find({}, {"_id": 0}).to_list(None))
