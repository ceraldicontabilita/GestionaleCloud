"""Il numero del verbale riaddebitato da Leasys sta nelle NOTE di riga: va letto, tutti, senza inventarne."""

from app.services.noleggio.parsers import categorizza_spesa, estrai_numeri_verbale

NOTE = ("UTILIZZATORE CERALDI GROUP S.R.L. codice 1184586404 | EXT REFERENCE 1184586404-5020682842 | "
        "CAUSALE: Addebito spese amministrative per infrazioni | al codice della strada n. verbale 20260200899 | "
        "data del verbale 29.04.2026 | articolo violazione NB1 | emittente COMUNE DI NAPOLI | "
        "data notifica del verbale 11.05.2026 | data gestione multa 13.05.2026")


def test_legge_il_numero_dalle_note_della_riga():
    assert estrai_numeri_verbale("HB411GV X3 xDrive 20d Msport", NOTE) == ["20260200899"]


def test_categorizza_come_verbale_e_porta_il_numero():
    categoria, importo, metadata = categorizza_spesa("HB411GV X3 xDrive 20d Msport", 10.0, False, NOTE)
    assert categoria == "verbali" and importo == 10.0
    assert metadata["numero_verbale"] == "20260200899" and metadata["numeri_verbale"] == ["20260200899"]
    assert metadata["data_verbale"] == "29/04/2026"  # non la data di notifica


def test_piu_numeri_senza_doppioni_e_senza_codici_che_non_sono_verbali():
    testo = "n. verbale 20250662362 e Verbale Nr: A25111540620, di nuovo n. verbale 20250662362 | ref 1184586404-5020682842"
    assert estrai_numeri_verbale(testo) == ["20250662362", "A25111540620"]


def test_senza_numero_non_ne_inventa():
    assert estrai_numeri_verbale("CAUSALE: Addebito spese amministrative per infrazioni") == []


def test_la_riga_verbale_della_fattura_porta_numeri_e_data():
    from app.services.noleggio.processors import _aggiungi_verbale

    veicolo = {"verbali": [], "totale_verbali": 0}
    fattura = {"invoice_date": "2026-06-26", "invoice_number": "0000202611025701", "invoice_id": "f1", "supplier": "Leasys"}
    _aggiungi_verbale(veicolo, fattura, "HB411GV X3", 10.0, 2.2,
                      {"numero_verbale": "20260200899", "numeri_verbale": ["20260200899"], "data_verbale": "29/04/2026"})
    riga = veicolo["verbali"][0]
    assert riga["numeri_verbale"] == ["20260200899"] and riga["data_verbale"] == "29/04/2026"
