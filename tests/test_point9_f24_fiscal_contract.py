from pathlib import Path

from app.services.f24_payment_evidence import (
    STATO_DA_PAGARE,
    STATO_QUIETANZA_DA_VERIFICARE,
    patch_quietanza_associata,
    stato_evidenza_pagamento,
)
from app.services.f24_tributi_saldo import proponi_allocazione, saldo_tributi


def _modello_erario_sanitizzato():
    # Oracle derivato da un F24 reale verificato in Drive, ma senza identita'
    # del contribuente: 2003 = 2.009,67; 1668 = 20,00; credito = 0.
    return {
        "id": "f24-oracle-2020-sanitized",
        "sezione_erario": [
            {"codice_tributo": "2003", "anno": "2019", "importo_debito": 2009.67, "importo_credito": 0},
            {"codice_tributo": "1668", "anno": "2019", "importo_debito": 20.00, "importo_credito": 0},
        ],
    }


def test_modello_f24_reale_sanitizzato_quadra_saldo_finale():
    saldo = saldo_tributi(_modello_erario_sanitizzato())
    assert saldo["debito"] == 2029.67
    assert saldo["credito"] == 0.0
    assert saldo["saldo_documento"] == 2029.67
    assert saldo["residuo"] == 2029.67
    assert saldo["stato"] == "da_pagare"


def test_modello_senza_quietanza_o_banca_non_diventa_pagato():
    stato = stato_evidenza_pagamento(_modello_erario_sanitizzato())
    assert stato["stato"] == STATO_DA_PAGARE
    assert stato["pagato"] is False
    assert stato["verificato_banca"] is False


def test_quietanza_reale_sanitizzata_resta_documentale_fino_alla_banca():
    # Oracle derivato da quietanza AE reale: INPS RC01, debito 1.472,00,
    # credito 0. Il protocollo prova il versamento documentale, non l'addebito EC.
    f24 = {
        **_modello_erario_sanitizzato(),
        **patch_quietanza_associata(
            quietanza_id="quietanza-sanitized",
            protocollo="protocollo-sanitized/000001",
            data_quietanza="2025-11-21",
        ),
    }
    stato = stato_evidenza_pagamento(f24)
    assert stato["stato"] == STATO_QUIETANZA_DA_VERIFICARE
    assert stato["quietanza_presente"] is True
    assert stato["versato_documentalmente"] is True
    assert stato["pagato"] is False
    assert stato["verificato_banca"] is False


def test_credito_compensa_il_saldo_ma_non_e_un_pagamento():
    f24 = {
        "id": "credito-informativo",
        "sezione_erario": [
            {"codice_tributo": "2001", "anno": "2026", "importo_debito": 1000.00, "importo_credito": 0},
            {"codice_tributo": "6099", "anno": "2025", "importo_debito": 0, "importo_credito": 250.00},
        ],
    }
    saldo = saldo_tributi(f24)
    assert saldo["debito"] == 1000.0
    assert saldo["credito"] == 250.0
    assert saldo["saldo_documento"] == 750.0
    assert saldo["pagato_banca"] == 0.0
    assert saldo["residuo"] == 750.0

    proposta_parziale = proponi_allocazione(
        f24,
        {"id": "ec-parziale", "importo": -500.0, "data": "2026-08-20"},
    )
    assert proposta_parziale["associazione_automatica"] is False
    assert proposta_parziale["esito"] == "compensazione_da_verificare"


def test_modulo_legacy_f24_alert_non_deve_tornare_raggiungibile():
    root = Path("app")
    riferimenti = []
    for path in root.rglob("*.py"):
        if path.name == "f24_alert_system.py":
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "f24_alert_system" in text:
            riferimenti.append(str(path))
    assert riferimenti == []
