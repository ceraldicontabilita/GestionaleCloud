"""La carta pubblica del menu.

Categorie, prodotti e immagini provengono esclusivamente dalle tabelle
``menu_*`` dell'admin e dal ponte Lotti. Il vecchio snapshot esterno e la sua
mappa immagini sono stati rimossi: non esiste una seconda copia del catalogo.

Endpoint:
    GET  /api/menu/carta                     pubblico, per la pagina /menu/carta/
    PUT  /api/admin/carta/prodotti/{id}      admin, {"disponibile":bool?, "prezzo_centesimi":int?}
    DELETE /api/admin/carta/prodotti/{id}    410, usare la modifica canonica
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.menu.routes.qrcode_routes import verify_token
from app.menu.routes import menu_routes
from app.menu.models.menu_models import ProductUpdate

router_pubblico = APIRouter(prefix="/api/menu", tags=["Carta"])
router_admin = APIRouter(prefix="/api/admin/carta", tags=["Carta"])


@router_pubblico.get("/carta")
async def carta_pubblica(destinazione: str = "pubblico", canale: Optional[str] = None):
    """``canale`` = ``sala`` | ``delivery``: la stessa carta, senza i prodotti non venduti in quel canale."""
    if destinazione not in {"pubblico", "bb"}:
        raise HTTPException(400, "Destinazione non valida")
    if canale not in {None, "", "sala", "delivery"}:
        raise HTTPException(400, "Canale non valido")
    carta = await _carta_dai_menu(destinazione=destinazione)
    if canale:
        chiave = "sala" if canale == "sala" else "dlv"
        carta["items"] = [i for i in carta["items"] if i.get(chiave, 1)]
        in_uso = {i["c"] for i in carta["items"]}
        carta["cats"] = [c for c in carta["cats"] if c["id"] in in_uso]
        menu_in_uso = {c["m"] for c in carta["cats"]}
        carta["menus"] = [m for m in carta["menus"] if m["id"] in menu_in_uso]
    return carta


async def _carta_dai_menu(*, destinazione="pubblico"):
    if destinazione == "bb":
        categorie, sottocategorie, prodotti = await menu_routes._fetch_all(catalogo_bb=True)
        # Destinazione indipendente dalla carta pubblica. La selezione usa
        # soltanto la riga Menu replicata dal ponte, mai il database ricette.
        prodotti = [dict(p, visible=True) for p in prodotti if p.get("menu_bb") is not False]
    else:
        categorie, sottocategorie, prodotti = await menu_routes._fetch_all(catalogo_carta=True)
    carta = carta_da_menu(categorie, sottocategorie, prodotti)
    if destinazione == "bb":
        allergeni = {p["id"]: p.get("allergens", []) for p in prodotti}
        for item in carta["items"]:
            item["allergeni_menu"] = allergeni[item["id"]]
    return carta


ALLERGENI_CARTA = {
    "molluscs": "clams", "sulphites": "dioxide", "eggs": "egg", "lupin": "lupins",
    "crustaceans": "shellfish", "soy": "soia", "nuts": "wot",
}


def carta_da_menu(categorie, sottocategorie, prodotti):
    """Costruisce la carta esclusivamente dalle righe canoniche del Menu."""
    categorie_id = {c["id"] for c in categorie}
    sub_by_id = {s["id"]: s for s in sottocategorie if s["category_id"] in categorie_id}

    def ordine(righe):
        return sorted(righe, key=lambda r: r["id"])

    items = []
    for p in ordine(prodotti):
        sub = sub_by_id.get(p["subcategory_id"])
        prezzo = menu_routes.prezzo_centesimi(p.get("price"))
        if p.get("visible") is False or (prezzo is None and p.get("origine") != "lotti") or not sub or sub["category_id"] != p["category_id"]:
            continue
        descrizione = (p.get("descriptionIT") or p.get("description") or "").strip() or None
        items.append({
            "id": p["id"], "cod": p.get("codice_prodotto"), "c": p["subcategory_id"], "n": p["nameIT"] or p["name"],
            "p": prezzo, "fp": prezzo, "pic": p.get("image"), "d": descrizione, "on": 1,
            "a": [ALLERGENI_CARTA.get(a, a) for a in p.get("allergens", [])],
            "t": None, "deep": 0, "long": None, "mat": None, "lists": None,
            # scheda vendita: canali, esaurito, aggiunte (prezzo in centesimi) e rimozioni
            "sala": 1 if p.get("vendita_sala") is not False else 0,
            "dlv": 1 if p.get("vendita_delivery") is not False else 0,
            "disp": 0 if p.get("disponibile") is False else 1,
            "ag": [{"n": a.get("nome"), "p": a.get("prezzo_centesimi")} for a in (p.get("aggiunte") or []) if a.get("nome")],
            "rm": [r for r in (p.get("rimozioni") or []) if r],
        })
    sub_piene = {i["c"] for i in items}
    foto_sub = {}
    for item in items:
        if item.get("pic"):
            foto_sub.setdefault(item["c"], item["pic"])
    cats = [{"id": s["id"], "m": s["category_id"],
             "n": s["nameIT"] or s["name"], "pic": s.get("image") or foto_sub.get(s["id"]), "on": 1,
             "col": "5b7a6b"}
            for s in ordine(sottocategorie) if s["id"] in sub_piene]
    menu_pieni = {c["m"] for c in cats}
    foto_menu = {}
    for categoria in cats:
        if categoria.get("pic"):
            foto_menu.setdefault(categoria["m"], categoria["pic"])
    menus = [{"id": c["id"], "n": c["nameIT"] or c["name"],
              "pic": c.get("image") or foto_menu.get(c["id"]), "on": 1, "col": "5b7a6b"}
             for c in ordine(categorie) if c["id"] in menu_pieni]
    return _raggruppa_carta({"menus": menus, "cats": cats, "items": items})


def _raggruppa_carta(carta):
    """Organizzazione della carta, non un secondo catalogo: conserva gli ID
    prodotto e non modifica le categorie operative o gli originali."""
    menus, cats, items = carta["menus"], carta["cats"], carta["items"]
    produzione = next((m for m in menus if m["n"].casefold() == "produzione ceraldi"), None)
    bar = next((m for m in menus if m["n"].casefold() == "bar & dolci"), None)
    food = next((m for m in menus if m["n"].casefold() == "food"), None)
    dolci_bar = next((c for c in cats if bar and c["m"] == bar["id"] and c["n"].casefold() == "dolci"), None)
    colazioni = [c for c in cats if bar and c["m"] == bar["id"] and c["n"].casefold() in {"dolci", "colazione"}]
    if not produzione and not colazioni:
        return carta
    dolci = produzione or {"id": "dolci", "n": "Dolci", "on": 1, "col": "5b7a6b", "pic": None}
    if not produzione:
        menus.append(dolci)
    dolci["n"] = "Dolci"
    for c in colazioni:
        c["m"] = dolci["id"]
    if bar:
        bar["n"] = "Bar"
    for c in cats:
        if not produzione or c["m"] != produzione["id"] or c in colazioni:
            continue
        if c["n"].casefold() == "pasticceria":
            if dolci_bar:
                for i in items:
                    if i["c"] == c["id"]:
                        i["c"] = dolci_bar["id"]
            continue
        if c["n"].casefold() == "rosticceria":
            if not food:
                food = {"id": "food_lotti", "n": "Food", "on": 1, "col": "5b7a6b", "pic": c.get("pic")}
                menus.append(food)
            c["m"] = food["id"]
        elif c["n"].casefold() == "bar" and bar:
            c["m"] = bar["id"]
        else:
            # Il reparto Altro contiene sia dolci sia salati: nessuna associazione inventata.
            altri = next((m for m in menus if m["id"] == "altri_prodotti"), None)
            if not altri:
                altri = {"id": "altri_prodotti", "n": "Altri prodotti", "on": 1, "col": "5b7a6b", "pic": c.get("pic")}
                menus.append(altri)
            c["m"] = altri["id"]
    piene = {i["c"] for i in items}
    cats = [c for c in cats if c["id"] in piene]
    menu_pieni = {c["m"] for c in cats}
    menus = [m for m in menus if m["id"] in menu_pieni]
    for m in menus:
        if m["n"] == "Dolci":
            # Non usare la foto della rosticceria per la nuova card dei dolci.
            m["pic"] = next((i["pic"] for i in items if i.get("pic") and i["c"] in {c["id"] for c in cats if c["m"] == m["id"]}), None)
    return {"menus": menus, "cats": cats, "items": items}


class SceltaProdotto(BaseModel):
    disponibile: Optional[bool] = None
    prezzo_centesimi: Optional[int] = Field(default=None, ge=0, le=10_000_000)


@router_admin.put("/prodotti/{prodotto_id}")
async def imposta_prodotto(prodotto_id: int, corpo: SceltaProdotto, _utente: str = Depends(verify_token)):
    campi = {k: v for k, v in corpo.model_dump().items() if v is not None}
    if not campi:
        raise HTTPException(422, "Niente da cambiare")
    aggiornamento = {}
    if "disponibile" in campi:
        aggiornamento["visible"] = campi["disponibile"]
    if "prezzo_centesimi" in campi:
        aggiornamento["price"] = f"{Decimal(campi['prezzo_centesimi']) / 100:.2f}€"
    await menu_routes.update_product(prodotto_id, ProductUpdate(**aggiornamento), _utente)
    return {"ok": True, "prodotto": prodotto_id, **campi}


@router_admin.delete("/prodotti/{prodotto_id}")
async def toglie_override(prodotto_id: int, _utente: str = Depends(verify_token)):
    raise HTTPException(410, "La carta usa i prodotti del Menu: modifica prezzo e visibilita' in Gestione Menu > Prodotti.")
