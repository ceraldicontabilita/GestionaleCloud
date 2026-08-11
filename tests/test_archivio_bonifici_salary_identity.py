from app.routers.bonifici_module.associazioni import (
    _salario_appartiene_al_dipendente,
)


def test_bonifico_taiano_non_mostra_cedolini_pocci_o_lesina():
    destinazione = {
        "dipendente_id": "dip-taiano",
        "dipendente_nome_rilevato": "TAIANO LUIGI",
        "identita_univoca": True,
    }

    assert _salario_appartiene_al_dipendente(
        {"dipendente_id": "dip-taiano", "dipendente": "TAIANO LUIGI"},
        destinazione,
    )
    assert not _salario_appartiene_al_dipendente(
        {"dipendente_id": "dip-pocci", "dipendente": "POCCI SALVATORE"},
        destinazione,
    )
    assert not _salario_appartiene_al_dipendente(
        {"dipendente_id": "dip-lesina", "dipendente": "LESINA ANGELA"},
        destinazione,
    )


def test_salario_legacy_senza_id_richiede_lo_stesso_nome_completo():
    destinazione = {
        "dipendente_id": "dip-taiano",
        "dipendente_nome_rilevato": "TAIANO LUIGI",
        "identita_univoca": True,
    }

    assert _salario_appartiene_al_dipendente(
        {"dipendente": "LUIGI TAIANO", "anno": 2026, "mese": 3},
        destinazione,
    )
    assert not _salario_appartiene_al_dipendente(
        {"dipendente": "POCCI SALVATORE", "anno": 2026, "mese": 4},
        destinazione,
    )
