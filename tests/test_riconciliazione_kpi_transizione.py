from app.services.riconciliazione_kpi import calcola_contatori_movimenti, verifica_transizione


def test_conferma_diminuisce_da_riconciliare_e_aumenta_riconciliati():
    prima_righe = [
        {"id": "1", "importo": -100, "riconciliato": False},
        {"id": "2", "importo": -200, "riconciliato": False},
        {"id": "3", "importo": 300, "riconciliato": True},
    ]
    prima = calcola_contatori_movimenti(prima_righe)
    dopo_righe = [{**r, "riconciliato": True} if r["id"] == "1" else r for r in prima_righe]
    dopo = calcola_contatori_movimenti(dopo_righe)
    assert verifica_transizione(prima, dopo) == {
        "ok": True,
        "delta_riconciliati": 1,
        "delta_da_riconciliare": -1,
        "totale_invariato": True,
    }


def test_duplicazione_durante_riconciliazione_fa_fallire_invariante():
    prima = calcola_contatori_movimenti([{"id": "1", "importo": 10, "riconciliato": False}])
    dopo = calcola_contatori_movimenti([
        {"id": "1", "importo": 10, "riconciliato": True},
        {"id": "duplicato", "importo": 10, "riconciliato": True},
    ])
    assert verifica_transizione(prima, dopo)["ok"] is False
