"""Schermate di banco: ordini, cassa, cucina, magazzino bar.

Aperte a qualunque sessione valida, comprese quelle del portale dipendenti
(``dipendente``, ``responsabile_turni``); la sessione ``sola_lettura`` puo'
solo leggere (lo impone il middleware globale sui metodi di scrittura).
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query, status

from app.menu import magazzino, ordini
from app.menu.auth import nome_utente, require_menu_staff
from app.menu.models import (
    MovementCreate, OrderCreate, OrderPaymentUpdate, OrderStatusUpdate,
    WarehouseItemCreate, WarehouseItemUpdate,
)

router = APIRouter()


# ------------------------------------------------------------------ ordini

@router.get("/ordini", summary="Elenco ordini (per stato o solo attivi)")
async def elenco_ordini(status: Optional[str] = None, active_only: bool = False):
    return await ordini.elenco_ordini(status, active_only)


@router.post("/ordini", status_code=status.HTTP_201_CREATED, summary="Ordine registrato alla cassa")
async def ordine_cassa(payload: OrderCreate, utente=Depends(require_menu_staff)):
    return await ordini.crea_ordine(payload, sorgente="cassa", creato_da=nome_utente(utente))


@router.patch("/ordini/{ordine_id}/stato", summary="Avanza o annulla un ordine")
async def stato(ordine_id: str, payload: OrderStatusUpdate):
    return await ordini.aggiorna_stato(ordine_id, payload.status)


@router.patch("/ordini/{ordine_id}/pagamento", summary="Segna un ordine come pagato")
async def pagamento(ordine_id: str, payload: OrderPaymentUpdate):
    return await ordini.aggiorna_pagamento(ordine_id, payload.paid, payload.payment_method)


@router.delete("/ordini/{ordine_id}", summary="Elimina un ordine")
async def elimina_ordine(ordine_id: str):
    await ordini.elimina_ordine(ordine_id)
    return {"success": True}


@router.get("/sale", summary="Sale del locale")
async def sale():
    return await ordini.elenco_sale()


# ------------------------------------------------------------------ magazzino bar

@router.get("/magazzino/articoli", summary="Articoli del magazzino bar (condiviso con Lotti)")
async def articoli(low_stock_only: bool = False):
    return await magazzino.elenco(low_stock_only)


@router.post("/magazzino/articoli", status_code=status.HTTP_201_CREATED, summary="Nuovo articolo")
async def nuovo_articolo(payload: WarehouseItemCreate):
    return await magazzino.crea(payload.model_dump())


@router.put("/magazzino/articoli/{articolo_id}", summary="Modifica articolo")
async def modifica_articolo(articolo_id: str, payload: WarehouseItemUpdate):
    return await magazzino.aggiorna(articolo_id, payload.model_dump(exclude_none=True))


@router.delete("/magazzino/articoli/{articolo_id}", summary="Elimina articolo (anche da Lotti)")
async def elimina_articolo(articolo_id: str):
    await magazzino.elimina(articolo_id)
    return {"success": True}


@router.post("/magazzino/articoli/{articolo_id}/movimento", summary="Carico, scarico o rettifica")
async def movimento(articolo_id: str, payload: MovementCreate, utente=Depends(require_menu_staff)):
    return await magazzino.movimento(articolo_id, payload.type, payload.quantity, payload.note, nome_utente(utente))


@router.get("/magazzino/movimenti", summary="Storico movimenti fatti dal menu")
async def movimenti(item_id: Optional[str] = None, limit: int = Query(100, ge=1, le=1000)):
    return await magazzino.movimenti(item_id, limit)
