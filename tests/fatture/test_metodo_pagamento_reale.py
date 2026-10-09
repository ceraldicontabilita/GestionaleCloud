"""Il metodo di pagamento mostrato e' quello REALE, non quello previsto.

Segnalazione utente (07/08/2026): fattura BIG FOOD registrata in Cassa, ma il
PDF esportato diceva "misto". "Misto" era il piano di pagamento dell'XML —
un'intenzione. Il pagamento vero era la scrittura in Prima Nota Cassa.
"""
from app.routers.fatture_module.crud import (
    _metodo_reale,
    _normalizza_da_invoices,
)


def test_il_caso_big_food_pagata_in_cassa_non_dice_piu_misto():
    doc = {
        "id": "f1", "invoice_number": "V1039286", "supplier_name": "BIG FOOD SRL",
        "payment_method": "misto",              # il piano dell'XML
        "metodo_pagamento_effettivo": "cassa",  # la conferma reale
        "prima_nota_tipo": "cassa", "prima_nota_cassa_id": "pn-1",
        "pagato": True, "stato": "pagata",
    }
    assert _metodo_reale(doc) == "cassa"
    assert _normalizza_da_invoices(doc)["metodo_pagamento_effettivo"] == "cassa"


def test_senza_conferma_esplicita_decide_la_scrittura_di_prima_nota():
    assert _metodo_reale({"payment_method": "misto",
                          "prima_nota_cassa_id": "pn-1"}) == "cassa"
    assert _metodo_reale({"payment_method": "misto",
                          "prima_nota_banca_id": "pn-2"}) == "banca"


def test_cassa_e_banca_insieme_e_misto_davvero():
    """Il pagamento diviso esiste: li' "misto" e' un fatto, non un'etichetta."""
    assert _metodo_reale({
        "prima_nota_cassa_id": "pn-1", "prima_nota_banca_id": "pn-2",
    }) == "misto"


def test_una_fattura_non_pagata_mostra_il_metodo_previsto():
    """Finche' non c'e' un pagamento, l'intenzione e' l'unica informazione."""
    assert _metodo_reale({"payment_method": "bonifico"}) == "bonifico"
    assert _metodo_reale({}) == ""


def test_la_sospensione_esplicita_resta_visibile():
    assert _metodo_reale({
        "metodo_pagamento_effettivo": "sospesa", "payment_method": "misto",
    }) == "sospesa"
