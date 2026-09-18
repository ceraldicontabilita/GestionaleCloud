from app.services.f24_tributi_saldo import (
    applica_allocazione, proponi_allocazione, proposte_globali_univoche, saldo_tributi,
)
from app.services.estratto_conto_bpm_parser import riconcilia_f24_con_estratto
from app.services.f24_payment_evidence import stato_evidenza_pagamento


def f24_isa():
    importi = [("1990", 95.12), ("1991", 14.09), ("2001", 4613.50),
               ("6494", 449.00), ("8904", 20.04), ("8918", 170.77)]
    return {
        "id": "f24-isa",
        "sezione_erario": [
            {"codice_tributo": c, "anno": "2025", "importo_debito": v, "importo_credito": 0}
            for c, v in importi
        ],
        "totali": {"saldo_netto": 5362.52},
        "dati_generali": {"data_versamento": "2026-08-04"},
    }


def test_pagamento_2001_salda_solo_la_riga_e_lascia_tutti_i_residui():
    doc = f24_isa()
    proposta = proponi_allocazione(doc, {"id": "mov-1", "importo": -4613.50, "data_contabile": "2026-08-04"})
    assert proposta["associazione_automatica"] is True
    assert proposta["codici_tributo"] == ["2001"]
    patch = applica_allocazione(doc, proposta)
    assert patch["stato_pagamento"] == "PARZIALMENTE_PAGATO_BANCA"
    assert patch["pagato"] is False
    assert patch["importo_residuo"] == 749.02
    assert {r["codice"] for r in patch["saldo_tributi"]["righe_aperte"]} == {
        "1990", "1991", "6494", "8904", "8918"
    }


def test_pagamento_integrale_chiude_il_modello():
    doc = f24_isa()
    proposta = proponi_allocazione(doc, {"id": "mov-full", "importo": -5362.52})
    patch = applica_allocazione(doc, proposta)
    assert patch["pagato"] is True
    assert patch["importo_residuo"] == 0


def test_importo_ripetuto_non_viene_associato_automaticamente():
    doc = {
        "sezione_erario": [
            {"codice_tributo": "1040", "importo_debito": 100},
            {"codice_tributo": "1001", "importo_debito": 100},
        ]
    }
    proposta = proponi_allocazione(doc, {"id": "mov", "importo": -100})
    assert proposta["esito"] == "ambiguo"
    assert proposta["associazione_automatica"] is False


def test_stesso_movimento_non_puo_essere_applicato_due_volte():
    doc = f24_isa()
    p = proponi_allocazione(doc, {"id": "mov-1", "importo": -4613.50})
    patch = applica_allocazione(doc, p)
    doc.update(patch)
    assert proponi_allocazione(doc, {"id": "mov-1", "importo": -4613.50})["esito"] == "gia_associato"


def test_credito_richiede_conferma_sui_pagamenti_parziali():
    doc = {
        "sezione_erario": [
            {"codice_tributo": "2001", "importo_debito": 1000, "importo_credito": 0},
            {"codice_tributo": "6099", "importo_debito": 0, "importo_credito": 200},
        ]
    }
    assert saldo_tributi(doc)["saldo_documento"] == 800
    proposta = proponi_allocazione(doc, {"id": "mov", "importo": -500})
    assert proposta["esito"] == "compensazione_da_verificare"


def test_match_parziale_deve_essere_univoco_anche_fra_f24_diversi():
    uno = f24_isa()
    due = f24_isa()
    due["id"] = "altro-f24"
    movimento = {"id": "mov", "importo": -4613.50, "data_contabile": "2026-08-04"}
    assert proposte_globali_univoche([uno, due], [movimento]) == []
    proposte = proposte_globali_univoche([uno], [movimento])
    assert len(proposte) == 1
    assert proposte[0]["f24_id"] == "f24-isa"


def test_movimenti_bancari_duplicati_non_sono_prova_univoca():
    movimenti = [
        {"id": "mov-1", "importo": -4613.50, "data_contabile": "2026-08-04"},
        {"id": "mov-2", "importo": -4613.50, "data_contabile": "2026-08-04"},
    ]
    assert proposte_globali_univoche([f24_isa()], movimenti) == []


def test_riconciliazione_esistente_registra_il_pagamento_parziale_senza_chiudere_f24():
    risultato = riconcilia_f24_con_estratto(
        [f24_isa()],
        [{"id": "mov-2001", "importo": -4613.50, "data_contabile": "2026-08-04"}],
    )
    assert risultato["stats"]["parzialmente_pagati"] == 1
    assert risultato["stats"]["riconciliati"] == 0
    assert risultato["stats"]["non_pagati"] == 0
    parziale = risultato["f24_parzialmente_pagati"][0]
    assert parziale["pagato"] is False
    assert parziale["importo_residuo"] == 749.02
    assert risultato["movimenti_non_associati"] == []
    evidenza = stato_evidenza_pagamento(parziale)
    assert evidenza["stato"] == "PARZIALMENTE_PAGATO_BANCA"
    assert evidenza["pagato"] is False


def test_piu_pagamenti_dello_stesso_f24_si_accumulano_senza_duplicare_il_documento():
    risultato = riconcilia_f24_con_estratto(
        [f24_isa()],
        [
            {"id": "mov-2001", "importo": -4613.50, "data_contabile": "2026-08-04"},
            {"id": "mov-6494", "importo": -449.00, "data_contabile": "2026-08-04"},
        ],
    )
    assert risultato["stats"]["parzialmente_pagati"] == 1
    assert risultato["stats"]["non_pagati"] == 0
    assert len(risultato["f24_parzialmente_pagati"]) == 1
    parziale = risultato["f24_parzialmente_pagati"][0]
    assert len(parziale["allocazioni_banca"]) == 2
    assert parziale["importo_residuo"] == 300.02
    assert {r["codice"] for r in parziale["saldo_tributi"]["righe_aperte"]} == {
        "1990", "1991", "8904", "8918",
    }


def test_pagamenti_separati_di_tutti_i_tributi_chiudono_il_modello():
    movimenti = [
        {"id": f"mov-{codice}", "importo": -importo, "data_contabile": "2026-08-04"}
        for codice, importo in [
            ("1990", 95.12), ("1991", 14.09), ("2001", 4613.50),
            ("6494", 449.00), ("8904", 20.04), ("8918", 170.77),
        ]
    ]
    risultato = riconcilia_f24_con_estratto([f24_isa()], movimenti)
    assert risultato["stats"]["riconciliati"] == 1
    assert risultato["stats"]["parzialmente_pagati"] == 0
    assert risultato["stats"]["non_pagati"] == 0
    pagato = risultato["f24_riconciliati"][0]
    assert pagato["riconciliato_per_tributi"] is True
    assert pagato["pagato"] is True
    assert pagato["importo_residuo"] == 0
    assert len(pagato["allocazioni_banca"]) == 6
