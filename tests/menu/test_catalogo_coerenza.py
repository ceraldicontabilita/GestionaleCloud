from app.services.catalogo_coerenza import verifica_catalogo


def test_riferimento_qualificato_e_allergeni_vigenti_anche_vuoti():
    products = [
        {
            "id": 1,
            "lotti_ref": "ricetta:R1",
            "price": "€ 4,50",
            "allergens": [],
            "visible": True,
        }
    ]
    recipes = [
        {
            "_id": "R1",
            "allergeni": [],
            "allergeni_auto": ["Latte"],
            "prezzo_vendita": 4.5,
            "menu_pubblico": True,
        }
    ]
    assert verifica_catalogo(products, recipes, {"milk"})["prodotti_da_verificare"] == 0


def test_ricetta_assente_e_allergeni_discordanti_restano_visibili_nel_controllo():
    products = [
        {
            "id": 1,
            "lotti_ref": "ricetta:assente",
            "price": "4.00€",
            "allergens": [],
            "visible": True,
        },
        {
            "id": 2,
            "lotti_ref": "ricetta:R2",
            "price": "4.00€",
            "allergens": ["milk"],
            "visible": True,
        },
    ]
    recipes = [{"id": "R2", "allergeni": ["Uova"], "prezzo_vendita": 4}]
    report = verifica_catalogo(products, recipes, {"milk", "eggs"})
    assert report["pubblicati_da_verificare"] == 2
    assert report["prodotti"][0]["problemi"] == ["Ricetta collegata non trovata"]
    assert "Allergeni diversi dalla ricetta" in report["prodotti"][1]["problemi"]
