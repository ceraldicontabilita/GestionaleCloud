"""Menu digitale dei clienti (QR al tavolo): nessuna sessione.

Il middleware globale lascia passare tutto ``/api/menu/pubblico/``; qui non
deve mai comparire un dato riservato (la password WiFi del QR resta
nell'area gestione).
"""
from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import Response

from app.menu import catalogo, ordini, storage as st
from app.menu.models import OrderCreate

router = APIRouter()


@router.get("/", summary="Menu completo: categorie, sottocategorie, prodotti e allergeni")
async def menu_completo():
    return await catalogo.menu_completo()


@router.get("/allergeni", summary="Elenco allergeni")
async def allergeni():
    return await catalogo.allergeni()


@router.get("/cerca", summary="Ricerca prodotti per nome")
async def cerca(q: str = Query(..., min_length=2, max_length=80), limit: int = Query(20, ge=1, le=100)):
    risultati = await catalogo.cerca_prodotti(q, limit)
    return {"results": risultati, "count": len(risultati)}


@router.get("/sale", summary="Sale del locale (solo i campi che servono per ordinare)")
async def sale():
    return await ordini.elenco_sale(pubblico=True)


@router.post("/ordini", status_code=status.HTTP_201_CREATED, summary="Invia un ordine dal tavolo")
async def crea_ordine(payload: OrderCreate):
    return await ordini.crea_ordine(payload, sorgente="cliente")


@router.get("/ordini/{ordine_id}", summary="Stato del proprio ordine")
async def stato_ordine(ordine_id: str):
    return await ordini.leggi_ordine(ordine_id)


@router.get("/qrcode/config", summary="Indirizzo pubblico del menu (per il QR)")
async def config_qr():
    doc = await st.uno(st.COLL_QRCODE, {"id": st.ID_CONFIG_QR})
    return {"menu_url": (doc or {}).get("menu_url") or ""}


@router.get("/immagini/{immagine_id}", summary="Immagine di categoria/sottocategoria/prodotto")
async def immagine(immagine_id: str):
    img = await st.leggi_immagine(immagine_id)
    if not img:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Immagine non trovata")
    return Response(
        content=img["content"],
        media_type=img["content_type"],
        headers={"Cache-Control": "public, max-age=86400, immutable"},
    )
