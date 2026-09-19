"""
test_riordino_consumi.py
─────────────────────────
Regression test per proposta_da_consumo (routers/ordini_fornitori.py):
la proposta d'ordine "da vero magazziniere" (richiesta Enzo 03/07/2026)
deve coprire GIORNI_COPERTURA giorni di consumo REALE tolto lo stock.
Funzione pura: nessun DB.
"""
from app.lotti.routers.ordini_fornitori import proposta_da_consumo, GIORNI_COPERTURA


def test_esempio_caffe():
    # consumo 10 pezzi/giorno, stock 20, copertura 7gg -> servono 50
    assert proposta_da_consumo(10, 20, 7) == 50


def test_stock_gia_sufficiente():
    # 2/giorno * 7gg = 14, stock 30 -> niente da ordinare
    assert proposta_da_consumo(2, 30, 7) == 0.0


def test_senza_storico_consumi_zero():
    assert proposta_da_consumo(0, 5) == 0.0
    assert proposta_da_consumo(-1, 5) == 0.0


def test_stock_negativo_trattato_come_zero():
    # stock negativo (rettifiche sballate) non deve gonfiare la proposta
    assert proposta_da_consumo(3, -10, 7) == 21


def test_copertura_default_costante():
    assert proposta_da_consumo(1, 0) == float(GIORNI_COPERTURA)


def test_arrotondamento_due_decimali():
    assert proposta_da_consumo(0.333, 0, 7) == 2.33
