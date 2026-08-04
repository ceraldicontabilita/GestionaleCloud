from collections import Counter

from app.routers.bank.estratto_conto import _occorrenza_gia_importata


def test_due_operazioni_identiche_nello_stesso_estratto_restano_due():
    existing = Counter()
    incoming = Counter()
    key = ("2026-04-30", 25.00, "COMMISSIONI POS")

    assert _occorrenza_gia_importata(existing, incoming, key) is False
    assert _occorrenza_gia_importata(existing, incoming, key) is False


def test_reimport_salta_esattamente_le_occorrenze_gia_presenti():
    existing = Counter({("2026-04-30", 25.00, "COMMISSIONI POS"): 2})
    incoming = Counter()
    key = ("2026-04-30", 25.00, "COMMISSIONI POS")

    assert _occorrenza_gia_importata(existing, incoming, key) is True
    assert _occorrenza_gia_importata(existing, incoming, key) is True
    assert _occorrenza_gia_importata(existing, incoming, key) is False
