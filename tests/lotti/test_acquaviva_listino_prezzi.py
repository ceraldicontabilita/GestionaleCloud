from app.lotti.routers.acquaviva import _applica_prezzo_listino_confezione


def test_listino_acquaviva_espone_il_totale_della_confezione():
    prodotto = {
        "prezzo_listino_riferimento": 0.727,
        "qty_cartone": 45,
        "unita_misura": "PZ",
        "gia_acquistato": False,
    }
    risultato = _applica_prezzo_listino_confezione(prodotto)
    assert risultato["prezzo_listino_fornitore"] == 32.715
    assert risultato["prezzo_listino_unitario"] == 0.727
    assert risultato["unita_vendita"] == "ct 45 pz"
    assert risultato["prezzo_fonte"] == "listino_fornitore"


def test_listino_non_sovrascrive_un_prezzo_di_fattura():
    prodotto = {
        "prezzo_listino_riferimento": 0.727,
        "qty_cartone": 45,
        "gia_acquistato": True,
        "prezzo_fattura": 31.5,
    }
    risultato = _applica_prezzo_listino_confezione(prodotto)
    assert "prezzo_listino_fornitore" not in risultato
    assert risultato["prezzo_fattura"] == 31.5
