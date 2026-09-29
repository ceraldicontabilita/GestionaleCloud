"""La carta pubblica del menu, nella forma della replica del menu Qromo.

Tre livelli (menu -> categorie -> prodotti) con colori, foto, orari di
disponibilita', ingredienti e liste di variazioni: quello che il menu del
gestionale (due livelli, `menu_categories`/`menu_subcategories`/`menu_products`)
non conserva. I dati sono il catalogo pubblico Qromo (`dati_carta/pub.json` e
`extras.json`); quelli importati dall'admin (collezione ``menu_carta``) hanno
la precedenza sul seme incluso nel repository.

Sopra il catalogo, le scelte fatte dall'admin restano in ``menu_carta_override``
(prodotto -> disponibile / prezzo): un nuovo import non le cancella.

Endpoint:
    GET  /api/menu/carta                     pubblico, per la pagina /menu/carta/
    GET  /api/admin/carta/stato              admin
    POST /api/admin/carta/importa            admin, {"pub":…, "extras":…, "imgmap":…}
    PUT  /api/admin/carta/prodotti/{id}      admin, {"disponibile":bool?, "prezzo_centesimi":int?}
    DELETE /api/admin/carta/prodotti/{id}    admin, toglie l'override
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.menu.routes.qrcode_routes import verify_token

DATI = Path(__file__).resolve().parent / "dati_carta"
COLLEZIONE = "menu_carta"
COLLEZIONE_OVERRIDE = "menu_carta_override"
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


def costruisci_carta(pub: Dict[str, Any], extras: Dict[str, Any], imgmap: Dict[str, str],
                     override: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Any]:
    """menus / cats / items come li usa carta.js. Prezzi in centesimi."""
    override = override or {}
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
        scelta = override.get(str(i["menu_item_id"])) or {}
        disponibile = i["available"]
        if scelta.get("disponibile") is not None:
            disponibile = 1 if scelta["disponibile"] else 0
        prezzo = scelta["prezzo_centesimi"] if scelta.get("prezzo_centesimi") is not None else i["price"]
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


async def _overrides() -> Dict[str, Dict[str, Any]]:
    db = await _db()
    righe = await db[COLLEZIONE_OVERRIDE].find({}, {"_id": 0}).to_list(5000)
    return {str(r["id"]): r for r in righe if r.get("id") is not None}


@router_pubblico.get("/carta")
async def carta_pubblica():
    dati = await _dataset()
    return costruisci_carta(dati["pub"], dati["extras"], dati.get("imgmap") or {}, await _overrides())


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
    carta = costruisci_carta(dati["pub"], dati["extras"], dati.get("imgmap") or {})
    return {
        "fonte": "importato" if salvato else "seme",
        "importato_il": (salvato or {}).get("importato_il"),
        "menu": len(carta["menus"]), "categorie": len(carta["cats"]), "prodotti": len(carta["items"]),
        "override": len(await _overrides()),
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
            "prodotti": len(carta["items"])}


class SceltaProdotto(BaseModel):
    disponibile: Optional[bool] = None
    prezzo_centesimi: Optional[int] = Field(default=None, ge=0, le=10_000_000)


@router_admin.put("/prodotti/{prodotto_id}")
async def imposta_prodotto(prodotto_id: int, corpo: SceltaProdotto, _utente: str = Depends(verify_token)):
    dati = await _dataset()
    if prodotto_id not in {i["menu_item_id"] for i in dati["pub"]["menusItems"]}:
        raise HTTPException(404, "Prodotto non in carta")
    campi = {k: v for k, v in corpo.model_dump().items() if v is not None}
    if not campi:
        raise HTTPException(422, "Niente da cambiare")
    db = await _db()
    await db[COLLEZIONE_OVERRIDE].update_one(
        {"id": prodotto_id},
        {"$set": {**campi, "id": prodotto_id, "aggiornato_il": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    return {"ok": True, "prodotto": prodotto_id, **campi}


@router_admin.delete("/prodotti/{prodotto_id}")
async def toglie_override(prodotto_id: int, _utente: str = Depends(verify_token)):
    db = await _db()
    await db[COLLEZIONE_OVERRIDE].delete_one({"id": prodotto_id})
    return {"ok": True}
