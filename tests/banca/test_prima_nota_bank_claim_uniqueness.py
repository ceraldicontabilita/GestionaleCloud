from app.routers.prima_nota_module.sync import _risolvi_rivendicazioni_movimenti


def _riga(fattura_id, numero, evidenza):
    return {
        "fattura_id": fattura_id,
        "fattura_numero": numero,
        "fornitore": "LEASYS ITALIA SPA",
        "importo": 1119.48,
        "evidenza_banca": evidenza,
        "strumento_bancario": {"codice": "riba", "label": "RiBa"},
        "movimento_banca": {"id": "ec-riba-1"},
        "stato_match": "match_forte",
    }


def test_due_fatture_stesso_importo_e_stessa_identita_restano_sospese():
    righe = [
        _riga("f1", "100", "strumento_fornitore_importo_data"),
        _riga("f2", "101", "strumento_fornitore_importo_data"),
    ]

    _risolvi_rivendicazioni_movimenti(righe)

    assert all(riga["movimento_banca"] is None for riga in righe)
    assert all(riga["stato_match"] == "ambiguo_importo_al_centesimo" for riga in righe)
    assert {c["fattura_id"] for c in righe[0]["candidati_ambigui"]} == {"f1", "f2"}


def test_numero_fattura_esplicito_prevale_su_match_generico():
    esplicita = _riga("f1", "100", "identita_fattura_importo")
    generica = _riga("f2", "101", "strumento_fornitore_importo_data")

    _risolvi_rivendicazioni_movimenti([esplicita, generica])

    assert esplicita["movimento_banca"]["id"] == "ec-riba-1"
    assert generica["movimento_banca"] is None
    assert generica["stato_match"] == "in_attesa_evidenza_specifica"
