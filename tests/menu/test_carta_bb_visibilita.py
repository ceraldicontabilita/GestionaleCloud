import asyncio
from app.menu import carta_menu as carta


def test_destinazione_bb_rispetta_spunta_indipendente_dal_pubblico(monkeypatch):
    categorie=[{"id":1,"nameIT":"Produzione Ceraldi","name":"Produzione Ceraldi"}]
    sotto=[{"id":10,"category_id":1,"nameIT":"Pasticceria","name":"Pasticceria"}]
    prodotti=[{"id":i,"nameIT":f"Prodotto {i}","name":f"Prodotto {i}","category_id":1,"subcategory_id":10,"price":"2.50€","origine":"lotti","lotti_ref":f"ricetta:r{i}","visible":False,"allergens":["milk"]} for i in (1,2,3)]
    prodotti[0]["menu_bb"] = True
    prodotti[1].update(menu_bb=False, visible=True)
    async def leggi(**kwargs):
        assert kwargs == {"catalogo_bb":True}
        return categorie,sotto,prodotti
    monkeypatch.setattr(carta.menu_routes,"_fetch_all",leggi)
    async def scenario():
        prima=await carta._carta_dai_dati(carta._seme(),destinazione="bb")
        assert {i["id"] for i in prima["items"]} == {1,3}
        assert prima["items"][0]["allergeni_menu"] == ["milk"]
        prodotti[0]["menu_bb"] = False
        dopo=await carta._carta_dai_dati(carta._seme(),destinazione="bb")
        assert {i["id"] for i in dopo["items"]} == {3}
        assert prodotti[0]["visible"] is False
    asyncio.run(scenario())
