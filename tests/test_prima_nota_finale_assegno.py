from app.routers.prima_nota_module.sync import (
    _numero_assegno_corrisponde_frammento,
)


def test_finale_assegno_usa_tre_cifre_e_suffisso_a_due_cifre():
    assert _numero_assegno_corrisponde_frammento(
        "0208770000-01", "000-01",
    )


def test_finale_assegno_legge_anche_vecchi_suffissi_senza_zero():
    assert _numero_assegno_corrisponde_frammento(
        "0208769431-7", "431-07",
    )


def test_finale_assegno_non_accetta_numero_o_suffisso_diversi():
    assert not _numero_assegno_corrisponde_frammento(
        "0208770000-01", "999-01",
    )
    assert not _numero_assegno_corrisponde_frammento(
        "0208770000-01", "000-02",
    )
    assert not _numero_assegno_corrisponde_frammento(
        "0208770000-01", "00001",
    )
