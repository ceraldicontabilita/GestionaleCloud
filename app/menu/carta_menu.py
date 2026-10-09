"""La carta pubblica del menu.

I prodotti pubblici provengono dalle tabelle ``menu_*`` dell'admin e del
ponte Lotti. I dettagli di presentazione (colori, foto locali, orari) stanno nel
dataset versionato in ``dati_carta/``: non decidono prezzo, allergeni o
pubblicazione. Non si espongono listini interni o prodotti rimossi usando una
seconda copia del catalogo.

Endpoint:
    GET  /api/menu/carta                     pubblico, per la pagina /menu/carta/
    PUT  /api/admin/carta/prodotti/{id}      admin, {"disponibile":bool?, "prezzo_centesimi":int?}
    DELETE /api/admin/carta/prodotti/{id}    410, usare la modifica canonica
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.menu.routes.qrcode_routes import verify_token
from app.menu.routes import menu_routes
from app.menu.models.menu_models import ProductUpdate

DATI = Path(__file__).resolve().parent / "dati_carta"
PREFISSO_FOTO = "/menu/carta/"

router_pubblico = APIRouter(prefix="/api/menu", tags=["Carta"])
router_admin = APIRouter(prefix="/api/admin/carta", tags=["Carta"])


@lru_cache(maxsize=1)
def _seme() -> Dict[str, Any]:
    return {nome: json.loads((DATI / f"{nome}.json").read_text(encoding="utf-8"))
            for nome in ("pub", "extras", "imgmap")}


def _foto(imgmap: Dict[str, str], url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    senza_full = re.sub(r"-full(\.\w+)$", r"\1", url)
    for candidato in (url, senza_full):
        if imgmap.get(candidato):
            return PREFISSO_FOTO + imgmap[candidato]
    return None


def _finestra(t: Dict[str, Any]) -> List[int]:
    return [t["hour_start"], t["minute_start"] or 0, t["hour_end"], t["minute_end"] or 0]


def costruisci_carta(pub: Dict[str, Any], extras: Dict[str, Any], imgmap: Dict[str, str]) -> Dict[str, Any]:
    """menus / cats / items come li usa carta.js. Prezzi in centesimi."""
    nome_allergene = {a["allergen_id"]: a["name_key"].replace("allergens_", "") for a in pub["allergens"]}
    allergeni: Dict[int, List[str]] = {}
    for x in pub["menusItemsAllergens"]:
        chiave = nome_allergene.get(x["allergen_id"])
        if chiave:
            allergeni.setdefault(x["menu_item_id"], []).append(chiave)
    orari_cat = {t["category_id"]: _finestra(t) for t in pub["menusCategoriesTimes"]}
    orari_prod = {t["item_id"]: _finestra(t) for t in pub["menusItemsTimes"]}

    items = []
    for i in sorted(pub["menusItems"], key=lambda i: i["order_number"]):
        extra = extras.get(str(i["menu_item_id"])) or {}
        dettagli = (extra.get("deepen") or {}).get("data") or {}
        composito = extra.get("composite") or None
        liste = []
        if composito:
            for lista in sorted(composito["lists"], key=lambda l: l["order_number"]):
                prodotti = [
                    {"n": p["product_name"], "p": p["product_price"]}
                    for p in sorted(composito["lists_products"], key=lambda p: p["order_number"])
                    if p["menu_item_list_id"] == lista["menu_item_list_id"] and p.get("available", 1)
                ]
                liste.append({"n": lista["name"], "p": prodotti})
        disponibile = i["available"]
        prezzo = i["price"]
        items.append({
            "id": i["menu_item_id"], "c": i["category_id"], "n": i["name"], "p": prezzo,
            "fp": i["full_price"], "pic": _foto(imgmap, i["picture"]),
            "d": (i["ingredients"] or "").strip() or None, "on": disponibile,
            "a": allergeni.get(i["menu_item_id"], []), "t": orari_prod.get(i["menu_item_id"]),
            "deep": 1 if (i.get("deepen") or dettagli) else 0,
            "long": (dettagli.get("long_description") or "").strip() or None,
            "mat": (dettagli.get("materials") or "").strip() or None,
            "lists": liste or None,
        })
    cats = [
        {"id": c["menu_category_id"], "m": c["menu_id"], "n": c["name"],
         "desc": (c["description"] or "").strip() or None, "pic": _foto(imgmap, c["picture"]),
         "on": c["active"], "col": c["color"] or "a67b01", "t": orari_cat.get(c["menu_category_id"])}
        for c in sorted(pub["menusCategories"], key=lambda c: c["order_number"])
    ]
    menus = [
        {"id": m["menu_id"], "n": m["name"].strip(), "on": m["available"],
         "pic": _foto(imgmap, m["picture"]), "col": m["color"] or "a67b01"}
        for m in sorted(pub["menus"], key=lambda m: m["order_number"])
    ]
    return {"menus": menus, "cats": cats, "items": items}


def _dataset() -> Dict[str, Any]:
    return _seme()


@router_pubblico.get("/carta")
async def carta_pubblica(destinazione: str = "pubblico", canale: Optional[str] = None):
    """``canale`` = ``sala`` | ``delivery``: la stessa carta, senza i prodotti non venduti in quel canale."""
    if destinazione not in {"pubblico", "bb"}:
        raise HTTPException(400, "Destinazione non valida")
    if canale not in {None, "", "sala", "delivery"}:
        raise HTTPException(400, "Canale non valido")
    dati = _dataset()
    carta = await _carta_dai_dati(dati, destinazione=destinazione)
    if canale:
        chiave = "sala" if canale == "sala" else "dlv"
        carta["items"] = [i for i in carta["items"] if i.get(chiave, 1)]
        in_uso = {i["c"] for i in carta["items"]}
        carta["cats"] = [c for c in carta["cats"] if c["id"] in in_uso]
        menu_in_uso = {c["m"] for c in carta["cats"]}
        carta["menus"] = [m for m in carta["menus"] if m["id"] in menu_in_uso]
    return carta


async def _carta_dai_dati(dati, *, destinazione="pubblico"):
    dettagli = costruisci_carta(dati["pub"], dati["extras"], dati.get("imgmap") or {})
    if destinazione == "bb":
        categorie, sottocategorie, prodotti = await menu_routes._fetch_all(catalogo_bb=True)
        # Destinazione indipendente dalla carta pubblica. La selezione usa
        # soltanto la riga Menu replicata dal ponte, mai il database ricette.
        prodotti = [dict(p, visible=True) for p in prodotti if p.get("menu_bb") is not False]
    else:
        categorie, sottocategorie, prodotti = await menu_routes._fetch_all(catalogo_carta=True)
    carta = carta_da_menu(categorie, sottocategorie, prodotti, dettagli, dati.get("imgmap") or {})
    if destinazione == "bb":
        allergeni = {p["id"]: p.get("allergens", []) for p in prodotti}
        for item in carta["items"]:
            item["allergeni_menu"] = allergeni[item["id"]]
    return carta


ALLERGENI_CARTA = {
    "molluscs": "clams", "sulphites": "dioxide", "eggs": "egg", "lupin": "lupins",
    "crustaceans": "shellfish", "soy": "soia", "nuts": "wot",
}


def carta_da_menu(categorie, sottocategorie, prodotti, dettagli, imgmap):
    """La carta e l'admin leggono le stesse righe; il dataset aggiunge solo dettagli.

    Nomi, prezzi, visibilita', allergeni, foto e gerarchia non provengono dal
    seme statico. La stessa lettura include i prodotti pubblicati da Lotti.
    """
    menu_extra = {m["id"]: m for m in dettagli["menus"]}
    cat_extra = {c["id"]: c for c in dettagli["cats"]}
    item_extra = {i["id"]: i for i in dettagli["items"]}
    categorie_id = {c["id"] for c in categorie}
    sub_by_id = {s["id"]: s for s in sottocategorie if s["category_id"] in categorie_id}

    def ordine(righe, originali):
        posizione = {r["id"]: indice for indice, r in enumerate(originali)}
        return sorted(righe, key=lambda r: (posizione.get(r["id"], len(posizione)), r["id"]))

    def foto(riga):
        url = riga.get("image")
        return _foto(imgmap, url) or url

    items = []
    for p in ordine(prodotti, dettagli["items"]):
        sub = sub_by_id.get(p["subcategory_id"])
        prezzo = menu_routes.prezzo_centesimi(p.get("price"))
        if p.get("visible") is False or (prezzo is None and p.get("origine") != "lotti") or not sub or sub["category_id"] != p["category_id"]:
            continue
        extra = item_extra.get(p["id"], {})
        descrizione = (p.get("descriptionIT") or p.get("description") or "").strip() or None
        # Un testo aggiornato dall'admin non deve aprire gli ingredienti vecchi.
        testo_invariato = descrizione == extra.get("d")
        items.append({
            **extra, "id": p["id"], "cod": p.get("codice_prodotto"), "c": p["subcategory_id"], "n": p["nameIT"] or p["name"],
            "p": prezzo, "fp": prezzo, "pic": foto(p), "d": descrizione, "on": 1,
            "a": [ALLERGENI_CARTA.get(a, a) for a in p.get("allergens", [])],
            "t": extra.get("t"), "deep": extra.get("deep", 0) if testo_invariato else 0,
            "long": extra.get("long") if testo_invariato else None,
            "mat": extra.get("mat") if testo_invariato else None, "lists": extra.get("lists"),
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
    cats = [{**cat_extra.get(s["id"], {}), "id": s["id"], "m": s["category_id"],
             "n": s["nameIT"] or s["name"], "pic": foto(s) or foto_sub.get(s["id"]), "on": 1,
             "col": cat_extra.get(s["id"], {}).get("col") or "5b7a6b"}
            for s in ordine(sottocategorie, dettagli["cats"]) if s["id"] in sub_piene]
    menu_pieni = {c["m"] for c in cats}
    foto_menu = {}
    for categoria in cats:
        if categoria.get("pic"):
            foto_menu.setdefault(categoria["m"], categoria["pic"])
    menus = [{**menu_extra.get(c["id"], {}), "id": c["id"], "n": c["nameIT"] or c["name"],
              "pic": foto(c) or foto_menu.get(c["id"]), "on": 1, "col": menu_extra.get(c["id"], {}).get("col") or "5b7a6b"}
             for c in ordine(categorie, dettagli["menus"]) if c["id"] in menu_pieni]
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
