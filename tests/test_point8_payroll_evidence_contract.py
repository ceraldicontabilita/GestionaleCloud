from pathlib import Path

from app.services.stipendi_bonifici import stato_operativo_salario


def test_documento_bonifico_non_diventa_prova_bancaria():
    stato = stato_operativo_salario({
        "importo_busta": 1200.0,
        "importo_bonifico_documentato": 1200.0,
        "importo_bonifico": 0,
    })
    assert stato["importo_documentato"] == 1200.0
    assert stato["importo_riscontrato_banca"] == 0.0
    assert stato["residuo_bancario"] == 1200.0
    assert stato["residuo_documentale"] == 0.0
    assert stato["stato_pagamento"] == "DOCUMENTATO_ATTESA_BANCA"


def test_acconto_bancario_reale_espone_residuo():
    stato = stato_operativo_salario({
        "importo_busta": 1200.0,
        "importo_bonifico": 500.0,
        "movimenti_bancari_ids": ["ec-1"],
    })
    assert stato["importo_riscontrato_banca"] == 500.0
    assert stato["residuo_bancario"] == 700.0
    assert stato["stato_pagamento"] == "PARZIALMENTE_RICONCILIATO"


def test_importo_pieno_non_promuove_senza_validazione_completa():
    riga = {
        "importo_busta": 1200.0,
        "importo_bonifico": 1200.0,
        "movimento_bancario_id": "ec-1",
    }
    assert stato_operativo_salario(riga)["stato_pagamento"] == "DA_VERIFICARE"
    assert stato_operativo_salario(
        riga, riconciliazione_completa_verificata=True,
    )["stato_pagamento"] == "RICONCILIATO"


def test_importi_oltre_netto_sono_conflitto():
    stato = stato_operativo_salario({
        "importo_busta": 1000.0,
        "importo_bonifico_documentato": 1100.0,
    })
    assert stato["stato_pagamento"] == "CONFLITTO"


def test_vecchia_pagina_salari_non_ha_store_o_hook_frontend():
    assert not Path("frontend/src/stores/primaNotaStore.js").exists()
    assert not Path("frontend/src/hooks/usePrimaNota.js").exists()
    main = Path("frontend/src/main.jsx").read_text()
    assert 'path="/salari"' not in main
