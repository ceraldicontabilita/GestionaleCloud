from app.services.calendario_piano import collega_scadenze, voci_della_scadenza
from app.services import piano_tributi as pt


def _griglia(stato):
    voce = {"id": "ritenute_1001", "etichetta": "Ritenute lavoro dipendente", "codici": ["1001"], "obbligatorio": True}
    casella = {"periodo": "03", "stato": stato, "etichetta_stato": pt.ETICHETTE[stato], "giorni_scaduto": 5,
               "importo": None, "modelli": []}
    return {"voci": [{"voce": voce, "caselle": [casella]}]}


def test_mappa_scadenze_e_voci():
    assert voci_della_scadenza("ritenute_2026_03") == [("ritenute_1001", "03")]
    assert voci_della_scadenza("inps_2026_11") == [("inps_dm10", "11")]
    assert voci_della_scadenza("iva_liq_2026_02") == [("iva_mensile", "02")]
    assert ("ires_saldo", "06") in voci_della_scadenza("ires_saldo_2025")
    assert voci_della_scadenza("cu_2026") == []


def test_codici_attesi_e_conferma_senza_f24():
    s = [{"id": "ritenute_2026_03", "completato": True, "provenienza_stato": "conferma_manuale"}]
    out = collega_scadenze(s, _griglia(pt.SCADUTO_NON_PAGATO))[0]
    assert out["codici_attesi"] == ["1001"]
    assert out["conferma_senza_f24"] is True
    assert out["completato"] is True  # la conferma del titolare non si tocca


def test_pagato_con_quietanza_non_segnala_incoerenze():
    s = [{"id": "ritenute_2026_03", "completato": True, "provenienza_stato": "conferma_manuale"}]
    out = collega_scadenze(s, _griglia(pt.PAGATO_QUIETANZA))[0]
    assert out["conferma_senza_f24"] is False


def test_scadenza_senza_codici_resta_com_e():
    s = [{"id": "cu_2026"}]
    assert "codici_attesi" not in collega_scadenze(s, _griglia(pt.PAGATO))[0]
