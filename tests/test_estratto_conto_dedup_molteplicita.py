from collections import Counter

from app.routers.bank.estratto_conto import (
    _occorrenza_gia_importata,
    bank_operation_identity,
)


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


def test_chiave_bancaria_stabile_normalizza_prefisso_spazi_e_maiuscole():
    first = bank_operation_identity(
        "2026-08-07", "uscita", 23.10,
        "ADDEBITO DIRETTO SDD - SDD CORE: 49RJ PAYPAL", 1,
    )
    second = bank_operation_identity(
        "2026-08-07", "uscita", -23.10,
        "sdd core: 49rj   paypal", 1,
    )
    assert first == second


def test_chiave_bancaria_preserva_verso_e_molteplicita():
    base = bank_operation_identity(
        "2026-08-07", "uscita", 23.10, "OPERAZIONE", 1,
    )
    altra_occorrenza = bank_operation_identity(
        "2026-08-07", "uscita", 23.10, "OPERAZIONE", 2,
    )
    verso_opposto = bank_operation_identity(
        "2026-08-07", "entrata", 23.10, "OPERAZIONE", 1,
    )
    assert len({base, altra_occorrenza, verso_opposto}) == 3
