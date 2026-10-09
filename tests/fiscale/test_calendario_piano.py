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
    assert ("ires_saldo", None) in voci_della_scadenza("ires_saldo_2025")
    assert voci_della_scadenza("cu_2026") == []


def test_codici_attesi_e_conferma_senza_f24():
    s = [{"id": "ritenute_2026_03", "completato": True, "provenienza_stato": "conferma_manuale"}]
    out = collega_scadenze(s, _griglia(pt.MANCA_F24))[0]
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


def test_iva_mensile_porta_solo_il_codice_del_mese():
    voce = {"id": "iva_mensile", "etichetta": "IVA", "codici": [f"60{m:02d}" for m in range(1, 13)],
            "obbligatorio": False}
    casella = {"periodo": "02", "stato": pt.FUTURO, "etichetta_stato": pt.ETICHETTE[pt.FUTURO], "modelli": []}
    out = collega_scadenze([{"id": "iva_liq_2026_02"}], {"voci": [{"voce": voce, "caselle": [casella]}]})[0]
    assert out["codici_attesi"] == ["6002"]


def test_annuale_segue_la_scadenza_configurata_e_modello_non_pagato_non_e_mancante():
    voce = {"id": "ires_saldo", "etichetta": "IRES saldo", "codici": ["2003"], "obbligatorio": True}
    casella = {"periodo": "07", "scadenza": "2026-07-31", "stato": pt.SCADUTO_NON_PAGATO,
               "etichetta_stato": "x", "modelli": []}
    s = [{"id": "ires_saldo_2025", "data": "2026-07-30", "completato": True,
          "provenienza_stato": "conferma_manuale"}]
    out = collega_scadenze(s, {"voci": [{"voce": voce, "caselle": [casella]}]})[0]
    assert out["codici_attesi"] == ["2003"]
    assert out["conferma_senza_f24"] is False
    # scadenza spostata di un mese rispetto al calendario: nessun aggancio
    lontana = [{"id": "ires_saldo_2025", "data": "2026-06-30"}]
    assert "piano_voci" not in collega_scadenze(lontana, {"voci": [{"voce": voce, "caselle": [casella]}]})[0]


def test_annuale_con_due_scadenze_configurate_sceglie_il_mese_del_calendario():
    voce = {"id": "ires_saldo", "etichetta": "IRES saldo", "codici": ["2003"], "obbligatorio": True}
    caselle = [
        {"periodo": "06", "scadenza": "2026-06-16", "stato": pt.SCADUTO_NON_PAGATO, "etichetta_stato": "no", "modelli": []},
        {"periodo": "06", "scadenza": "2026-06-30", "stato": pt.PAGATO_QUIETANZA, "etichetta_stato": "ok", "modelli": []},
    ]
    s = [{"id": "ires_saldo_2025", "data": "2026-06-30"}]
    out = collega_scadenze(s, {"voci": [{"voce": voce, "caselle": caselle}]})[0]
    assert out["piano_voci"][0]["stato"] == pt.PAGATO_QUIETANZA
