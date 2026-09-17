"""Test del façade di classificazione costi unificata: verifica che una sola
chiamata restituisca i tre assi (centro di costo, conto economico, piano dei
conti) delegando ai motori esistenti."""
from app.services.classificazione_unificata import classifica_costo_completo


def test_classifica_costo_completo_tre_assi():
    r = classifica_costo_completo(
        "Illy Caffè SpA", "Fornitura caffè in grani", importo=500
    )
    # Asse 1: centro di costo analitico
    assert r["centro_costo"]["id"]
    assert 0 <= r["centro_costo"]["confidence"] <= 1
    # Asse 2: conto economico civilistico + deducibilità (importo fornito)
    assert r["conto_economico"]["categoria"].startswith("B")
    assert r["conto_economico"]["deducibilita"]  # non vuota con importo
    # Asse 3: piano dei conti
    assert r["piano_conti"].get("conto_codice")


def test_classifica_costo_completo_senza_importo_e_senza_linee():
    # Senza importo la deducibilità CE resta vuota; senza linee usa la descrizione.
    r = classifica_costo_completo("Fornitore Ignoto XYZ", "voce generica")
    assert r["conto_economico"]["deducibilita"] == {}
    assert "categoria_merceologica" in r["piano_conti"]
    assert r["centro_costo"]["id"]
