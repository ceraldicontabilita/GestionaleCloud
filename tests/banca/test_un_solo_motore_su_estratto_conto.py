"""Un solo motore reagisce all'import dell'estratto conto.

Sull'evento `estratto_conto.importato` erano registrati **due** handler:
`on_estratto_conto_importato_riprocessa`, che chiama il motore canonico
`riconcilia_documenti_e_pagamenti`, e `handler_matching_estratto_conto`, un
secondo motore che marcava fatture `pagato: True` su un punteggio, scriveva
in Prima Nota banca con `source="estratto_conto_auto"` e chiudeva le scadenze.

Misurato in produzione il 20/09/2026: zero righe `estratto_conto_auto` in
`prima_nota_banca` (722 righe) e zero proposte dei suoi quattro tipi in
`operazioni_da_confermare` (105 righe, tutte `riconciliazione_dubbio`). Non
aveva mai prodotto niente perche' tre gambe su quattro leggevano campi
inesistenti; i suoi test li fabbricavano, e passavano.

Cancellato. Resta il punteggio, in `services/match_storico_banca_fattura.py`,
perche' la migrazione d'avvio lo usa sugli abbinamenti gia' in archivio.
"""
import asyncio
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_il_secondo_motore_non_esiste_piu():
    assert not (ROOT / "app/handlers/estratto_conto.py").exists()
    bus = (ROOT / "app/services/event_bus.py").read_text(encoding="utf-8")
    assert "handler_matching_estratto_conto" not in bus


def test_un_solo_handler_sull_evento_estratto_conto_importato():
    from app.services import event_bus

    event_bus.register_all_handlers()
    handlers = event_bus._handlers.get(event_bus.EventTypes.ESTRATTO_CONTO_IMPORTATO, [])
    nomi = sorted({getattr(h, "__name__", str(h)) for h in handlers})
    assert nomi == ["on_estratto_conto_importato_riprocessa"], nomi


def test_il_punteggio_storico_resta_disponibile_alla_migrazione():
    from app.services.match_storico_banca_fattura import (
        SOGLIA_AUTO,
        punteggio_match_storico,
    )

    assert SOGLIA_AUTO == 0.90
    # importo esatto ma nessuna identita' in causale: non regge
    assert punteggio_match_storico(
        {"tipo": "uscita", "importo": 24.40, "descrizione": "BONIFICO"},
        {"total_amount": 24.40, "supplier_name": "Leasys Italia S.p.A",
         "invoice_number": "0000202610458640"},
    ) == 0.0


def test_nessun_ramo_disattivato_da_una_costante():
    """Un motore spento con `if not FLAG` resta un motore: si cancella.

    `FASE0_DISATTIVATO = True` teneva spenti da settembre due rami vietati dal
    regolamento contabile — F24 per solo importo (±0,05 €, senza data) e POS
    di cassa a tolleranza ±1 € — con l'idea di «rimuoverli in Fase 3». Erano
    121 righe che nessuno poteva eseguire e che qualunque `False` riaccendeva.
    """
    sorgente = (ROOT / "app/services/riconciliazione_bancaria.py").read_text(encoding="utf-8")
    assert "FASE0_DISATTIVATO" not in sorgente
    assert "DISATTIVATO" not in sorgente
