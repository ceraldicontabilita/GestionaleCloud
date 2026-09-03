"""Magazzino bar: e' la collezione ``magazzino_bar_prodotti`` di Lotti (unico
magazzino condiviso, come nelle due app originali). I campi restano quelli di
Lotti (``nome``, ``unita``, ``stock``, ``categoria``, ``fornitore``,
``min_threshold``); l'API del menu li espone con i nomi storici
(``name``, ``unit``, ``quantity``...). Lo storico dei movimenti fatti dal
menu sta in ``menu_warehouse_movements``."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status

from app.menu import storage as st
from app.menu.models import MOVEMENT_TYPES


def _numero(v, default=0.0):
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def articolo_out(doc: Dict[str, Any]) -> Dict[str, Any]:
    soglia = doc.get("min_threshold")
    return {
        "id": doc.get("id"),
        "name": doc.get("nome") or doc.get("name") or "(senza nome)",
        "unit": doc.get("unita") or doc.get("unit") or "pz",
        "quantity": _numero(doc.get("stock", doc.get("quantity"))),
        "min_threshold": _numero(soglia, None) if soglia is not None else None,
        "category": doc.get("categoria") or doc.get("category"),
        "supplier": doc.get("fornitore") or doc.get("supplier"),
        "note": doc.get("note"),
        "updated_at": doc.get("updated_at") or doc.get("created_at"),
    }


async def elenco(solo_sotto_soglia: bool = False) -> List[Dict[str, Any]]:
    items = [articolo_out(d) for d in await st.tutti(st.COLL_MAGAZZINO_BAR)]
    items.sort(key=lambda i: str(i["name"]).casefold())
    if solo_sotto_soglia:
        items = [i for i in items if i["min_threshold"] is not None and i["quantity"] <= i["min_threshold"]]
    return items


async def _leggi(articolo_id: str) -> Dict[str, Any]:
    doc = await st.uno(st.COLL_MAGAZZINO_BAR, {"id": articolo_id})
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Articolo non trovato")
    return doc


async def crea(dati: Dict[str, Any]) -> Dict[str, Any]:
    adesso = st.adesso()
    doc = {
        "id": st.nuovo_id(), "nome": dati["name"], "unita": dati.get("unit") or "pz",
        "stock": _numero(dati.get("quantity")), "categoria": dati.get("category"),
        "fornitore": dati.get("supplier"), "note": dati.get("note"),
        "created_at": adesso, "updated_at": adesso, "origine": "menu",
    }
    if dati.get("min_threshold") is not None:
        doc["min_threshold"] = _numero(dati["min_threshold"])
    return articolo_out(await st.inserisci(st.COLL_MAGAZZINO_BAR, doc))


async def aggiorna(articolo_id: str, dati: Dict[str, Any]) -> Dict[str, Any]:
    await _leggi(articolo_id)
    mappa = {"name": "nome", "unit": "unita", "category": "categoria", "supplier": "fornitore", "note": "note", "min_threshold": "min_threshold"}
    valori = {mappa[k]: v for k, v in dati.items() if k in mappa and v is not None}
    valori["updated_at"] = st.adesso()
    return articolo_out(await st.aggiorna(st.COLL_MAGAZZINO_BAR, {"id": articolo_id}, valori))


async def elimina(articolo_id: str) -> None:
    if not await st.elimina(st.COLL_MAGAZZINO_BAR, {"id": articolo_id}):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Articolo non trovato")


async def movimento(articolo_id: str, tipo: str, quantita: float, nota: Optional[str], operatore: Optional[str]) -> Dict[str, Any]:
    if tipo not in MOVEMENT_TYPES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tipo movimento non valido")
    if quantita < 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La quantita' del movimento deve essere positiva")
    doc = await _leggi(articolo_id)
    item = articolo_out(doc)
    if tipo == "carico":
        nuova = item["quantity"] + quantita
    elif tipo == "scarico":
        nuova = item["quantity"] - quantita
    else:  # rettifica: valore assoluto
        nuova = quantita
    nuova = round(nuova, 3)
    aggiornato = await st.aggiorna(st.COLL_MAGAZZINO_BAR, {"id": articolo_id}, {"stock": nuova, "updated_at": st.adesso()})
    await st.inserisci(st.COLL_MOVIMENTI, {
        "id": st.nuovo_id(), "item_id": articolo_id, "item_name": item["name"], "type": tipo,
        "quantity": quantita, "resulting_quantity": nuova, "note": nota, "operatore": operatore,
        "created_at": st.adesso(),
    })
    return articolo_out(aggiornato)


async def movimenti(articolo_id: Optional[str] = None, limite: int = 100) -> List[Dict[str, Any]]:
    filtro = {"item_id": articolo_id} if articolo_id else {}
    docs = await st.tutti(st.COLL_MOVIMENTI, filtro)
    docs.sort(key=lambda m: str(m.get("created_at") or ""), reverse=True)
    return docs[:limite]
