from app.lotti.routers.utils import _registro_tracciabilita_esatto


def test_registro_esclude_somiglianze_testuali_e_accetta_solo_id_condiviso():
    fatture = [{
        "fornitore": "Fornitore",
        "numero_fattura": "10",
        "data_fattura": "2026-10-02",
        "prodotti": [
            {"descrizione": "Crema nocciola A", "prodotto_master_id": "p1"},
            {"descrizione": "Crema nocciola B", "prodotto_master_id": "p2"},
            {"descrizione": "Farina senza link"},
        ],
    }]
    ricette = [{
        "nome": "Cornetto", "ingredienti": ["crema", "farina"],
        "ingredienti_dettaglio": [{"nome": "Crema", "prodotto_master_id": "p1"}],
    }]

    righe = _registro_tracciabilita_esatto(fatture, ricette)

    assert len(righe) == 1
    assert righe[0]["prodotto"] == "Crema nocciola A"
    assert righe[0]["ricette"] == ["Cornetto"]
    assert righe[0]["tipo_collegamento"] == "identita_canonica"


def test_registro_mantiene_distinte_fatture_con_stessa_intestazione():
    fatture = [
        {"fornitore": "F", "numero_fattura": "10", "data_fattura": "2026-10-02",
         "prodotti": [{"descrizione": "A", "prodotto_id": "p1"}]},
        {"fornitore": "F", "numero_fattura": "10", "data_fattura": "2026-10-02",
         "prodotti": [{"descrizione": "B", "prodotto_id": "p2"}]},
    ]
    ricette = [{"nome": "R", "ingredienti_dettaglio": [{"prodotto_id": "p1"}]}]

    righe = _registro_tracciabilita_esatto(fatture, ricette)

    assert [(r["fattura_indice"], r["prodotto"]) for r in righe] == [(0, "A")]
