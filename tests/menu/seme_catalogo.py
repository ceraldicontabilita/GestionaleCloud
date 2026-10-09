"""Fixture dei test del Menu: righe ``menu_*`` ricavate dal dataset della carta (``dati_carta/pub.json``).

Serve solo ai test, per avere un catalogo realistico (769 prodotti) nelle tabelle finte. Nessun accesso a rete o database."""
from typing import Any, Dict, List, Optional

PREFISSO_MENU_BANCO = "BANCO - "

# Riduzione dei 39 tag del dataset ai 14 allergeni UE (id gia' presenti in menu_allergens).
MAPPA_ALLERGENI_SEME = {
    "allergens_celery": "celery",
    "allergens_clams": "molluscs",
    "allergens_dioxide": "sulphites",
    "allergens_egg": "eggs",
    "allergens_fish": "fish",
    "allergens_gluten": "gluten",
    "allergens_lupins": "lupin",
    "allergens_milk": "milk",
    "allergens_mustard": "mustard",
    "allergens_peanuts": "peanuts",
    "allergens_sesame": "sesame",
    "allergens_shellfish": "crustaceans",
    "allergens_soia": "soy",
    "allergens_wot": "nuts",
    "allergens_almond": "nuts",
    "allergens_barley": "gluten",
    "allergens_brazil_nuts": "nuts",
    "allergens_cashew": "nuts",
    "allergens_hazelnuts": "nuts",
    "allergens_macadamia": "nuts",
    "allergens_oats": "gluten",
    "allergens_pecan": "nuts",
    "allergens_pistachios": "nuts",
    "allergens_rye": "gluten",
    "allergens_spelt": "gluten",
    "allergens_walnuts": "nuts",
    "allergens_wheat": "gluten",
    "allergens_kamut": "gluten",
}



def _prezzo(centesimi: Optional[int]) -> str:
    """Stesso formato del seed originale (``"3.50€"``)."""
    return f"{(centesimi or 0) / 100:.2f}€"


def _pulisci(testo: Optional[str]) -> Optional[str]:
    if not isinstance(testo, str):
        return None
    testo = testo.strip()
    return testo or None


def trasforma_catalogo(dati: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """Da ``{"menus", "menusCategories", "menusItems", "menusItemsAllergens", "allergens"}``
    alle righe (colonne snake_case) di ``menu_categories`` / ``menu_subcategories``
    / ``menu_products``. Nessun accesso a rete o database."""
    menu_da_includere = {
        m["menu_id"] for m in dati["menus"]
        if m.get("available") == 1 and not str(m.get("name") or "").startswith(PREFISSO_MENU_BANCO)
    }
    categorie_dataset = [m for m in dati["menus"] if m["menu_id"] in menu_da_includere]

    sottocategorie_dataset = [
        c for c in dati["menusCategories"]
        if c.get("menu_id") in menu_da_includere and c.get("active") == 1
    ]
    id_sottocategorie = {c["menu_category_id"] for c in sottocategorie_dataset}

    prodotti_dataset = [
        p for p in dati["menusItems"]
        if p.get("category_id") in id_sottocategorie and p.get("available") == 1
    ]
    id_prodotti = {p["menu_item_id"] for p in prodotti_dataset}

    # Sottocategorie/categorie senza nemmeno un prodotto pubblicato (es. "Comunicazioni")
    # non vanno replicate: il cliente non le vedrebbe nemmeno sul menu vero.
    sottocategorie_con_prodotti = {p["category_id"] for p in prodotti_dataset}
    sottocategorie_dataset = [c for c in sottocategorie_dataset if c["menu_category_id"] in sottocategorie_con_prodotti]
    sottocat_by_id = {c["menu_category_id"]: c for c in sottocategorie_dataset}
    categorie_con_sottocategorie = {c["menu_id"] for c in sottocategorie_dataset}
    categorie_dataset = [c for c in categorie_dataset if c["menu_id"] in categorie_con_sottocategorie]

    nome_allergene = {a["allergen_id"]: a.get("name_key") for a in dati["allergens"]}
    allergeni_per_prodotto: Dict[int, List[str]] = {}
    for legame in dati["menusItemsAllergens"]:
        if legame.get("menu_item_id") not in id_prodotti:
            continue
        mappato = MAPPA_ALLERGENI_SEME.get(nome_allergene.get(legame.get("allergen_id")))
        if not mappato:
            continue
        lista = allergeni_per_prodotto.setdefault(legame["menu_item_id"], [])
        if mappato not in lista:
            lista.append(mappato)

    righe_categorie = []
    for c in categorie_dataset:
        nome = _pulisci(c.get("name")) or f"Menu {c['menu_id']}"
        righe_categorie.append({"id": c["menu_id"], "name": nome, "name_it": nome, "image": c.get("picture") or None})

    righe_sottocategorie = []
    for c in sottocategorie_dataset:
        nome = _pulisci(c.get("name")) or f"Sezione {c['menu_category_id']}"
        righe_sottocategorie.append({
            "id": c["menu_category_id"], "category_id": c["menu_id"],
            "name": nome, "name_it": nome, "image": c.get("picture") or None,
        })

    righe_prodotti = []
    for p in prodotti_dataset:
        sottocat = sottocat_by_id[p["category_id"]]
        nome = _pulisci(p.get("name")) or f"Prodotto {p['menu_item_id']}"
        descrizione = _pulisci(p.get("ingredients"))
        righe_prodotti.append({
            "id": p["menu_item_id"], "category_id": sottocat["menu_id"], "subcategory_id": p["category_id"],
            "name": nome, "name_it": nome, "price": _prezzo(p.get("price")),
            "description": descrizione, "description_it": descrizione,
            "allergens": allergeni_per_prodotto.get(p["menu_item_id"], []),
            "image": p.get("picture") or None,
        })

    return {
        "categories": righe_categorie,
        "subcategories": righe_sottocategorie,
        "products": righe_prodotti,
    }


