"""La carta pubblica del menu, nella forma della replica del menu Qromo.

I prodotti pubblici provengono dalle stesse tabelle ``menu_*`` dell'admin e
del ponte Lotti. Il catalogo Qromo (``menu_carta`` o seme) aggiunge solamente
colori, foto locali, orari e dettagli non modificati: non decide prezzo,
allergeni o pubblicazione. Non si espongono listini interni o prodotti
rimossi usando una seconda copia del catalogo.

Endpoint:
    GET  /api/menu/carta                     pubblico, per la pagina /menu/carta/
    GET  /api/admin/carta/stato              admin
    POST /api/admin/carta/importa            admin, {"pub":…, "extras":…, "imgmap":…}
    PUT  /api/admin/carta/prodotti/{id}      admin, {"disponibile":bool?, "prezzo_centesimi":int?}
    DELETE /api/admin/carta/prodotti/{id}    410, usare la modifica canonica
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.menu.routes.qrcode_routes import verify_token
from app.menu.routes import menu_routes
from app.menu.models.menu_models import ProductUpdate

DATI = Path(__file__).resolve().parent / "dati_carta"
COLLEZIONE = "menu_carta"
ID_DATASET = "qromo"
PREFISSO_FOTO = "/menu/carta/"

router_pubblico = APIRouter(prefix="/api/menu", tags=["Carta"])
router_admin = APIRouter(prefix="/api/admin/carta", tags=["Carta"])


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


async def _db():
    from app.database import Database
    return Database.get_db()


async def _dataset() -> Dict[str, Any]:
    db = await _db()
    salvato = await db[COLLEZIONE].find_one({"id": ID_DATASET}, {"_id": 0})
    return salvato if salvato and salvato.get("pub") else _seme()


@router_pubblico.get("/carta")
async def carta_pubblica():
    dati = await _dataset()
    return await _carta_dai_dati(dati)


async def _carta_dai_dati(dati):
    dettagli = costruisci_carta(dati["pub"], dati["extras"], dati.get("imgmap") or {})
    categorie, sottocategorie, prodotti = await menu_routes._fetch_all()
    return carta_da_menu(categorie, sottocategorie, prodotti, dettagli, dati.get("imgmap") or {})


ALLERGENI_CARTA = {
    "molluscs": "clams", "sulphites": "dioxide", "eggs": "egg", "lupin": "lupins",
    "crustaceans": "shellfish", "soy": "soia", "nuts": "wot",
}


def carta_da_menu(categorie, sottocategorie, prodotti, dettagli, imgmap):
    """La carta e l'admin leggono le stesse righe; Qromo aggiunge solo dettagli.

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
        if p.get("visible") is False or prezzo is None or not sub or sub["category_id"] != p["category_id"]:
            continue
        extra = item_extra.get(p["id"], {})
        descrizione = (p.get("descriptionIT") or p.get("description") or "").strip() or None
        # Un testo aggiornato dall'admin non deve aprire gli ingredienti vecchi.
        testo_invariato = descrizione == extra.get("d")
        items.append({
            **extra, "id": p["id"], "c": p["subcategory_id"], "n": p["nameIT"] or p["name"],
            "p": prezzo, "fp": prezzo, "pic": foto(p), "d": descrizione, "on": 1,
            "a": [ALLERGENI_CARTA.get(a, a) for a in p.get("allergens", [])],
            "t": extra.get("t"), "deep": extra.get("deep", 0) if testo_invariato else 0,
            "long": extra.get("long") if testo_invariato else None,
            "mat": extra.get("mat") if testo_invariato else None, "lists": extra.get("lists"),
        })
    sub_piene = {i["c"] for i in items}
    cats = [{**cat_extra.get(s["id"], {}), "id": s["id"], "m": s["category_id"],
             "n": s["nameIT"] or s["name"], "pic": foto(s), "on": 1,
             "col": cat_extra.get(s["id"], {}).get("col") or "5b7a6b"}
            for s in ordine(sottocategorie, dettagli["cats"]) if s["id"] in sub_piene]
    menu_pieni = {c["m"] for c in cats}
    menus = [{**menu_extra.get(c["id"], {}), "id": c["id"], "n": c["nameIT"] or c["name"],
              "pic": foto(c), "on": 1, "col": menu_extra.get(c["id"], {}).get("col") or "5b7a6b"}
             for c in ordine(categorie, dettagli["menus"]) if c["id"] in menu_pieni]
    return {"menus": menus, "cats": cats, "items": items}


class Importa(BaseModel):
    pub: Dict[str, Any]
    extras: Dict[str, Any] = Field(default_factory=dict)
    imgmap: Dict[str, str] = Field(default_factory=dict)


def _controlla(pub: Dict[str, Any]) -> None:
    mancanti = [k for k in ("menus", "menusCategories", "menusItems", "allergens", "menusItemsAllergens",
                            "menusCategoriesTimes", "menusItemsTimes") if not isinstance(pub.get(k), list)]
    if mancanti:
        raise HTTPException(422, f"pub.json incompleto: mancano {', '.join(mancanti)}")


@router_admin.get("/stato")
async def stato(_utente: str = Depends(verify_token)):
    db = await _db()
    salvato = await db[COLLEZIONE].find_one({"id": ID_DATASET}, {"_id": 0, "importato_il": 1})
    dati = await _dataset()
    carta = await _carta_dai_dati(dati)
    return {
        "fonte": "importato" if salvato else "seme",
        "catalogo": "menu_products",
        "importato_il": (salvato or {}).get("importato_il"),
        "menu": len(carta["menus"]), "categorie": len(carta["cats"]), "prodotti": len(carta["items"]),
    }


@router_admin.post("/importa")
async def importa(corpo: Importa, _utente: str = Depends(verify_token)):
    _controlla(corpo.pub)
    carta = costruisci_carta(corpo.pub, corpo.extras, corpo.imgmap)
    db = await _db()
    await db[COLLEZIONE].replace_one(
        {"id": ID_DATASET},
        {"id": ID_DATASET, "pub": corpo.pub, "extras": corpo.extras, "imgmap": corpo.imgmap,
         "importato_il": datetime.now(timezone.utc).isoformat()},
        upsert=True,
    )
    return {"ok": True, "menu": len(carta["menus"]), "categorie": len(carta["cats"]),
            "prodotti": len(carta["items"]), "ambito": "dettagli_carta",
            "catalogo_aggiornato": False,
            "messaggio": "Importati i dettagli della carta. Nomi, prezzi, allergeni e pubblicazione restano quelli del catalogo Menu; il catalogo Qromo si importa con Sincronizza da Qromo."}


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
