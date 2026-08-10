from app.engines import tributi_engine as te
from app.services.estratto_conto_bpm_parser import riconcilia_f24_con_estratto
from app.services.f24_payment_evidence import (
    STATO_PAGATO_BANCA,
    STATO_QUIETANZA_DA_VERIFICARE,
    stato_evidenza_pagamento,
)


def _f24(**extra):
    return {
        "id": "f24-iva",
        "dati_generali": {"periodo_riferimento": "06/2026", "data_versamento": "2026-07-16"},
        "sezione_erario": [
            {"codice_tributo": "6006", "periodo_riferimento": "06/2026", "importo_debito": 1000.0}
        ],
        "totali": {"saldo_netto": 1000.0},
        **extra,
    }


def test_quietanza_non_e_prova_bancaria():
    doc = _f24(
        status="pagato",
        quietanza_id="quiet-1",
        data_pagamento_quietanza="2026-07-16",
    )
    evidenza = stato_evidenza_pagamento(doc)
    assert evidenza["stato"] == STATO_QUIETANZA_DA_VERIFICARE
    assert evidenza["pagato"] is False
    assert evidenza["versato_documentalmente"] is True
    assert evidenza["data_versamento_documentale"] == "2026-07-16"

    analisi = te.classifica_f24(doc)
    assert analisi["data_pagamento"] is None
    assert analisi["stato"] == "quietanza_presente_da_verificare_banca"


def test_movimento_bancario_identificato_e_prova_pagamento():
    doc = _f24(
        movimento_bancario_id="mov-1",
        data_pagamento_effettivo="2026-07-16",
    )
    evidenza = stato_evidenza_pagamento(doc)
    assert evidenza["stato"] == STATO_PAGATO_BANCA
    assert evidenza["pagato"] is True

    analisi = te.classifica_f24(doc)
    assert analisi["data_pagamento"] == "2026-07-16"
    assert analisi["stato"] == "pagato_nei_termini"


def test_match_banca_richiede_data_e_candidato_univoco():
    senza_data = [{"id": "m0", "importo": -1000.0}]
    res = riconcilia_f24_con_estratto([_f24()], senza_data)
    assert res["stats"]["riconciliati"] == 0

    duplicati = [
        {"id": "m1", "importo": -1000.0, "data_contabile": "2026-07-16"},
        {"id": "m2", "importo": -1000.0, "data_contabile": "2026-07-17"},
    ]
    res = riconcilia_f24_con_estratto([_f24()], duplicati)
    assert res["stats"]["riconciliati"] == 0
    assert res["stats"]["ambigui"] == 1
    assert res["f24_non_pagati"][0]["match_ambiguo"] is True


def test_match_banca_univoco():
    movimenti = [
        {"id": "m1", "importo": -1000.0, "data_contabile": "2026-07-16"},
    ]
    res = riconcilia_f24_con_estratto([_f24()], movimenti)
    assert res["stats"]["riconciliati"] == 1
    assert res["f24_riconciliati"][0]["movimento_bancario"]["id"] == "m1"
