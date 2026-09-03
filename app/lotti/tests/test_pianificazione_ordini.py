from datetime import date, time

from app.lotti.servizi.pianificazione_ordini import (
    applica_fattori_quantita,
    giorni_consegna_profilo,
    piano_consegne,
)


def test_giorni_consegna_strutturati_prevalgono_sul_testo_legacy():
    assert giorni_consegna_profilo({
        "giorni_consegna_settimana": [3, 0],
        "giorni_consegna": "martedi",
    }) == [0, 3]


def test_giorni_consegna_legacy_restano_compatibili():
    assert giorni_consegna_profilo({"giorni_consegna": "lunedi e giovedì"}) == [0, 3]


def test_piano_salta_festivo_e_chiusura_fornitore():
    # 24/8/2026 e lunedi. Il fornitore consegna lun/gio, ma il 24 e festivo
    # aziendale e il 27 e chiuso dal fornitore: prima consegna utile 31/8.
    profilo = {
        "giorni_consegna_settimana": [0, 3],
        "lead_time_giorni": 0,
        "chiusure_programmate": [{"dal": "2026-08-27", "al": "2026-08-27"}],
    }
    piano = piano_consegne(date(2026, 8, 24), profilo, {date(2026, 8, 24)})
    assert piano["prima_consegna"] == "2026-08-31"
    assert piano["consegna_successiva"] == "2026-09-03"
    assert piano["giorni_copertura"] == 10
    assert piano["giorni_saltati"] == ["2026-08-24", "2026-08-27"]


def test_senza_calendario_non_inventa_giorni():
    piano = piano_consegne(date(2026, 8, 23), {}, set())
    assert piano["calendario_verificato"] is False
    assert piano["giorni_copertura"] == 7
    assert piano["prima_consegna"] is None


def test_limite_ordine_superato_sposta_il_preavviso():
    piano = piano_consegne(
        date(2026, 8, 24),
        {"giorni_consegna_settimana": [1], "lead_time_giorni": 1, "ora_limite_ordine": "10:00"},
        set(), ora_corrente=time(11, 0),
    )
    # Il martedi 25 non e piu raggiungibile dopo il cutoff: prima consegna 1/9.
    assert piano["prima_consegna"] == "2026-09-01"
    assert "limite ordine 10:00 gia superato" in piano["motivo"]


def test_quantita_usa_calendario_e_corrispettivi_con_limiti_prudenti():
    # 10 pezzi, 14 giorni di copertura, +20% corrispettivi = 24 pezzi.
    assert applica_fattori_quantita(10, 14, 1.2, "pz") == 24
    # Il fattore vendite e limitato al +30% anche con input anomalo.
    assert applica_fattori_quantita(10, 7, 9, "kg") == 13.0
