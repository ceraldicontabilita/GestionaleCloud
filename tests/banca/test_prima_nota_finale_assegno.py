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


def test_finale_assegno_ritrova_numero_ufficiale_bpm_senza_suffisso():
    assert _numero_assegno_corrisponde_frammento(
        "0208769328", "328-01",
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


def test_finale_assegno_accetta_le_ultime_cifre_col_trattino_dove_le_scrive_il_titolare():
    # Sulla fattura 1588 del 30/09/2026 il titolare ha scritto «694-90»:
    # il trattino e' un separatore, l'assegno BPM e' 0208769490.
    assert _numero_assegno_corrisponde_frammento("0208769490", "694-90")
    assert _numero_assegno_corrisponde_frammento("0208769490", "7694-90")  # quattro cifre prima del trattino
    assert _numero_assegno_corrisponde_frammento("0208769490", "69490")
    assert _numero_assegno_corrisponde_frammento("0208769490", "8769490")
    assert not _numero_assegno_corrisponde_frammento("0208769491", "694-90")
    assert _numero_assegno_corrisponde_frammento("0208769490", "94-90")  # quattro cifre: ancora una coda
    assert not _numero_assegno_corrisponde_frammento("0208769490", "90")  # due cifre: troppo poche
    assert not _numero_assegno_corrisponde_frammento("0208769490", "69-4-90")


def test_la_ricerca_rifiuta_frammenti_non_numerici_o_troppo_corti():
    from app.routers.prima_nota_module.sync import _frammento_assegno_valido

    assert _frammento_assegno_valido("694-90")
    assert _frammento_assegno_valido("0208769490")
    assert not _frammento_assegno_valido("94")
    assert not _frammento_assegno_valido("02087694901")
    assert not _frammento_assegno_valido("694/90")
