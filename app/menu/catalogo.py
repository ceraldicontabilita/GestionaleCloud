"""Catalogo del menu: categorie, sottocategorie, prodotti, allergeni.

I documenti sono salvati gia' nella forma esposta dall'API (``nameIT``,
``descriptionIT``...), la stessa che il frontend usa da sempre: nessuna
mappatura snake/camel intermedia. Gli id numerici delle vecchie tabelle
restano gli stessi (i prodotti li citano in ``product_id`` degli ordini).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.menu import storage as st
from app.menu.allergeni import ALLERGENI_DEFAULT


def _ordina_per_id(docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(docs, key=lambda d: (int(d.get("id") or 0), str(d.get("id"))))


async def allergeni() -> List[Dict[str, Any]]:
    docs = await st.tutti(st.COLL_ALLERGENI)
    if not docs:
        for a in ALLERGENI_DEFAULT:
            await st.inserisci(st.COLL_ALLERGENI, dict(a))
        docs = [dict(a) for a in ALLERGENI_DEFAULT]
    ordine = {a["id"]: i for i, a in enumerate(ALLERGENI_DEFAULT)}
    return sorted(docs, key=lambda d: (ordine.get(d.get("id"), 99), str(d.get("id"))))


def _pulisci_prodotto(p: Dict[str, Any]) -> Dict[str, Any]:
    p = dict(p)
    p.setdefault("allergens", [])
    p.setdefault("description", None)
    p.setdefault("descriptionIT", None)
    p.setdefault("image", None)
    return p


async def albero() -> List[Dict[str, Any]]:
    """Categorie -> sottocategorie -> prodotti (``items``), ordinati per id."""
    categorie = _ordina_per_id(await st.tutti(st.COLL_CATEGORIE))
    sottocategorie = _ordina_per_id(await st.tutti(st.COLL_SOTTOCATEGORIE))
    prodotti = [_pulisci_prodotto(p) for p in _ordina_per_id(await st.tutti(st.COLL_PRODOTTI))]
    per_sotto: Dict[Any, List[Dict[str, Any]]] = {}
    for p in prodotti:
        per_sotto.setdefault(p.get("subcategory_id"), []).append(p)
    per_cat: Dict[Any, List[Dict[str, Any]]] = {}
    for s in sottocategorie:
        s = dict(s)
        s["items"] = per_sotto.get(s.get("id"), [])
        per_cat.setdefault(s.get("category_id"), []).append(s)
    out = []
    for c in categorie:
        c = dict(c)
        c["subcategories"] = per_cat.get(c.get("id"), [])
        out.append(c)
    return out


async def menu_completo() -> Dict[str, Any]:
    return {"categories": await albero(), "allergens": await allergeni()}


async def prodotti_piatti() -> List[Dict[str, Any]]:
    """Elenco piatto dei prodotti con il nome (IT) di categoria e sottocategoria."""
    nomi_cat = {c.get("id"): c.get("nameIT") for c in await st.tutti(st.COLL_CATEGORIE)}
    nomi_sotto = {s.get("id"): s.get("nameIT") for s in await st.tutti(st.COLL_SOTTOCATEGORIE)}
    out = []
    for p in _ordina_per_id(await st.tutti(st.COLL_PRODOTTI)):
        p = _pulisci_prodotto(p)
        p["categoryName"] = nomi_cat.get(p.get("category_id"), "N/A")
        p["subcategoryName"] = nomi_sotto.get(p.get("subcategory_id"), "N/A")
        out.append(p)
    return out


async def cerca_prodotti(q: str, limit: int = 20) -> List[Dict[str, Any]]:
    q = q.casefold()
    trovati = [
        _pulisci_prodotto(p) for p in _ordina_per_id(await st.tutti(st.COLL_PRODOTTI))
        if q in str(p.get("name") or "").casefold() or q in str(p.get("nameIT") or "").casefold()
    ]
    return trovati[:limit]


# ------------------------------------------------------------------ scritture

async def crea_categoria(dati: Dict[str, Any]) -> Dict[str, Any]:
    doc = {"id": await st.prossimo_id_intero(st.COLL_CATEGORIE, 1), "name": dati["name"], "nameIT": dati["nameIT"], "image": dati.get("image")}
    return await st.inserisci(st.COLL_CATEGORIE, doc)


async def aggiorna_categoria(categoria_id: int, valori: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    return await st.aggiorna(st.COLL_CATEGORIE, {"id": categoria_id}, valori)


async def elimina_categoria(categoria_id: int) -> bool:
    """Cancella la categoria con tutte le sottocategorie e i prodotti (come
    l'ON DELETE CASCADE delle vecchie tabelle)."""
    n = await st.elimina(st.COLL_CATEGORIE, {"id": categoria_id})
    if not n:
        return False
    await st.elimina(st.COLL_SOTTOCATEGORIE, {"category_id": categoria_id})
    await st.elimina(st.COLL_PRODOTTI, {"category_id": categoria_id})
    return True


async def crea_sottocategoria(dati: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not await st.uno(st.COLL_CATEGORIE, {"id": dati["category_id"]}):
        return None
    doc = {
        "id": await st.prossimo_id_intero(st.COLL_SOTTOCATEGORIE, 10),
        "category_id": dati["category_id"], "name": dati["name"], "nameIT": dati["nameIT"], "image": dati.get("image"),
    }
    return await st.inserisci(st.COLL_SOTTOCATEGORIE, doc)


async def aggiorna_sottocategoria(sotto_id: int, valori: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    return await st.aggiorna(st.COLL_SOTTOCATEGORIE, {"id": sotto_id}, valori)


async def elimina_sottocategoria(sotto_id: int) -> bool:
    n = await st.elimina(st.COLL_SOTTOCATEGORIE, {"id": sotto_id})
    if not n:
        return False
    await st.elimina(st.COLL_PRODOTTI, {"subcategory_id": sotto_id})
    return True


async def crea_prodotto(dati: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    sotto = await st.uno(st.COLL_SOTTOCATEGORIE, {"id": dati["subcategory_id"]})
    if not sotto:
        return None
    doc = {
        "id": await st.prossimo_id_intero(st.COLL_PRODOTTI, 100),
        "category_id": sotto.get("category_id", dati.get("category_id")),
        "subcategory_id": dati["subcategory_id"],
        "name": dati["name"], "nameIT": dati["nameIT"], "price": dati["price"],
        "description": dati.get("description"), "descriptionIT": dati.get("descriptionIT"),
        "allergens": list(dati.get("allergens") or []), "image": dati.get("image"),
    }
    return await st.inserisci(st.COLL_PRODOTTI, doc)


async def aggiorna_prodotto(prodotto_id: int, valori: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if "subcategory_id" in valori:
        sotto = await st.uno(st.COLL_SOTTOCATEGORIE, {"id": valori["subcategory_id"]})
        if not sotto:
            return None
        valori = dict(valori, category_id=sotto.get("category_id"))
    return await st.aggiorna(st.COLL_PRODOTTI, {"id": prodotto_id}, valori)


async def elimina_prodotto(prodotto_id: int) -> bool:
    return bool(await st.elimina(st.COLL_PRODOTTI, {"id": prodotto_id}))
