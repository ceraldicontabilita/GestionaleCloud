"""I due rami di riconciliazione vietati dal regolamento contabile non ci sono più.

`riconciliazione_bancaria` teneva spenti con `FASE0_DISATTIVATO = True` il ramo
F24 per solo importo (±0,05 € senza data) e il ramo POS-cassa a tolleranza
(±1 €): 121 righe che nessuno poteva eseguire e che un `False` riaccendeva.
Entrambi violano «nessuna entità si associa per solo importo» e l'accredito POS
riconosciuto solo con causale del circuito più il giorno operativo.

Il ramo NUMIA (`riconcilia_accredito_pos_ec`), che è quello corretto, resta.
"""
import inspect

from app.services import riconciliazione_bancaria as mod


def test_nessuna_guardia_fase0_e_nessun_ramo_spento():
    sorgente = inspect.getsource(mod)
    assert "FASE0_DISATTIVATO" not in sorgente
    assert "DISATTIVATO" not in sorgente


def test_il_ramo_f24_per_solo_importo_non_esiste_piu():
    sorgente = inspect.getsource(mod)
    assert '"F24" in descrizione.upper()' not in sorgente
    assert "_propaga_f24_pagato" not in sorgente
    # e il contatore che sarebbe rimasto sempre a zero è sparito con lui
    assert "riconciliati_f24" not in sorgente


def test_il_ramo_pos_a_tolleranza_non_esiste_piu():
    sorgente = inspect.getsource(mod)
    assert "'POS', 'NEXI', 'SUMUP', 'CARTE', 'BANCOMAT'" not in sorgente
    assert "pos_weekend" not in sorgente
    assert "pos_giornaliero" not in sorgente


def test_il_ramo_numia_resta_attivo():
    sorgente = inspect.getsource(mod)
    assert "_e_accredito_pos_numia_con_giorno(descrizione)" in sorgente
    assert "riconcilia_accredito_pos_ec" in sorgente
