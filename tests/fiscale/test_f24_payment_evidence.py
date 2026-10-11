from app.engines import tributi_engine as te
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
    assert evidenza["pagato"] is True
    assert evidenza["verificato_banca"] is False
    assert evidenza["versato_documentalmente"] is True
    assert evidenza["data_versamento_documentale"] == "2026-07-16"

    analisi = te.classifica_f24(doc)
    assert analisi["data_pagamento"] == "2026-07-16"
    assert analisi["stato"] == "pagato_nei_termini"


def test_quietanza_completa_non_attende_il_residuo_della_riconciliazione_bancaria():
    evidenza = stato_evidenza_pagamento(_f24(
        quietanza_id="q", data_pagamento_quietanza="2026-07-16",
        allocazioni_banca=[{"id": "parziale"}], importo_residuo_cents=40000,
        movimento_bancario_id="parziale", data_pagamento_effettivo="2026-07-16",
    ))
    assert evidenza["pagato"] is True
    assert evidenza["verificato_banca"] is False


def test_collegamento_quietanza_parziale_non_salda_l_intero_modello():
    evidenza = stato_evidenza_pagamento(_f24(
        quietanza_id="q", data_pagamento_quietanza="2026-07-16",
        collegamento_quietanza_titolare={"righe": [{"differenza_cents": -40000}]},
    ))
    assert evidenza["pagato"] is False


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
