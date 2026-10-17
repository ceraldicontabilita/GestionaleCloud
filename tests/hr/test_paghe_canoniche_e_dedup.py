from app.hr.services.sincronizza_paghe_mensili import (
    _mese_registro,
    _stato_e_saldo,
    deduplica_pagamenti,
)


def test_deduplica_elenco_e_pdf_conserva_evidenza_bancaria():
    elenco = {
        "id": "elenco", "dipendente_id": "dip-1", "data": "2025-06-05",
        "importo": 1056, "origine": "elenco-pagamenti-titolare", "cro": "CRO-1",
    }
    banca = {
        "id": "banca", "dipendente_id": "dip-1", "data": "2025-06-05",
        "importo": 1056, "origine": "gestionale-bonifico-pdf", "cro": "CRO-1",
    }

    assert deduplica_pagamenti([elenco, banca]) == [banca]


def test_non_collassa_fonti_diverse_senza_prova_comune():
    elenco = {
        "id": "elenco", "dipendente_id": "dip-1", "data": "2025-06-05",
        "importo": 1056, "origine": "elenco-pagamenti-titolare",
    }
    banca = {
        "id": "banca", "dipendente_id": "dip-1", "data": "2025-06-05",
        "importo": 1056, "origine": "gestionale-bonifico-pdf", "cro": "CRO-1",
    }

    assert deduplica_pagamenti([elenco, banca]) == [elenco, banca]


def test_hash_documento_comune_non_prova_un_pagamento_duplicato():
    base = {"dipendente_id": "dip-1", "data": "2025-06-05", "importo": 100,
            "hash": "HASH-ESTRATTO-CONTO"}
    elenco = {**base, "id": "1", "origine": "elenco-pagamenti-titolare"}
    banca = {**base, "id": "2", "origine": "gestionale-bonifico-pdf"}

    assert deduplica_pagamenti([elenco, banca]) == [elenco, banca]


def test_non_collassa_due_pagamenti_della_stessa_fonte():
    base = {"dipendente_id": "dip-1", "data": "2025-06-05", "importo": 100,
            "origine": "gestionale-bonifico-pdf"}
    primo, secondo = {**base, "id": "1"}, {**base, "id": "2"}

    assert deduplica_pagamenti([primo, secondo]) == [primo, secondo]


def test_mensilita_aggiuntive_hanno_periodo_tecnico_separato():
    assert _mese_registro({"mese": 12, "tipo_cedolino": "tredicesima"}) == 13
    assert _mese_registro({"mese": 7, "tipo_cedolino": "quattordicesima"}) == 14


def test_netto_zero_con_pagamento_resta_da_verificare():
    assert _stato_e_saldo(0, 1835) == {"stato_pagamento": "da_verificare", "saldo": 0.0}
