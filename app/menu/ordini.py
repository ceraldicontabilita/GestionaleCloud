"""Ordini del menu digitale e della cassa, sale e coperto."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status

from app.menu import storage as st
from app.menu.models import ORDER_SOURCES, ORDER_STATUSES, OrderCreate, compute_total

STATI_ATTIVI = [s for s in ORDER_STATUSES if s not in ("completato", "annullato")]
MAX_RIGHE = 60
MAX_QUANTITA = 99

CAMPI_SALA_PUBBLICI = ("id", "nome", "ordini_abilitati", "coperto_attivo", "coperto_importo", "disabilita_contanti_qr")


async def elenco_sale(pubblico: bool = False) -> List[Dict[str, Any]]:
    sale = await st.tutti(st.COLL_SALE)
    sale.sort(key=lambda s: str(s.get("nome") or "").casefold())
    if pubblico:
        sale = [{k: s.get(k) for k in CAMPI_SALA_PUBBLICI} for s in sale]
    return sale


async def crea_ordine(payload: OrderCreate, sorgente: str, creato_da: Optional[str] = None) -> Dict[str, Any]:
    if sorgente not in ORDER_SOURCES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Sorgente ordine non valida")
    if not payload.items:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "L'ordine deve contenere almeno un prodotto")
    if len(payload.items) > MAX_RIGHE:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Troppe righe nell'ordine (massimo {MAX_RIGHE})")
    for riga in payload.items:
        if riga.quantity < 1 or riga.quantity > MAX_QUANTITA:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Quantita' non valida")

    sala_nome = None
    totale_coperto = 0.0
    if payload.sala_id:
        sala = await st.uno(st.COLL_SALE, {"id": payload.sala_id})
        if not sala:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Sala non trovata")
        if not sala.get("ordini_abilitati", True):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f'Gli ordini non sono al momento abilitati per la sala "{sala["nome"]}"')
        sala_nome = sala["nome"]
        if sorgente == "cliente" and sala.get("disabilita_contanti_qr") and payload.payment_method == "contanti":
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f'Il pagamento in contanti non e\' disponibile per gli ordini QR nella sala "{sala["nome"]}". Scegli un altro metodo di pagamento.',
            )
        if sala.get("coperto_attivo") and sala.get("coperto_importo"):
            coperti = payload.numero_coperti or 1
            totale_coperto = round(float(sala["coperto_importo"]) * coperti, 2)

    adesso = st.adesso()
    ordine = {
        "id": st.nuovo_id(),
        "items": [r.model_dump() for r in payload.items],
        "table": payload.table,
        "customer_name": payload.customer_name,
        "note": payload.note,
        "source": sorgente,
        "status": "nuovo",
        # Un ordine dal QR non e' mai "gia' pagato": lo segna la cassa.
        "paid": bool(payload.paid) if sorgente == "cassa" else False,
        "payment_method": payload.payment_method,
        "total": round(compute_total(payload.items) + totale_coperto, 2),
        "sala_id": payload.sala_id,
        "sala_nome": sala_nome,
        "numero_coperti": payload.numero_coperti,
        "totale_coperto": totale_coperto,
        "created_by": creato_da,
        "created_at": adesso,
        "updated_at": adesso,
    }
    return await st.inserisci(st.COLL_ORDINI, ordine)


async def leggi_ordine(ordine_id: str) -> Dict[str, Any]:
    ordine = await st.uno(st.COLL_ORDINI, {"id": ordine_id})
    if not ordine:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ordine non trovato")
    return ordine


async def elenco_ordini(stato: Optional[str] = None, solo_attivi: bool = False, limite: int = 500) -> List[Dict[str, Any]]:
    filtro: Dict[str, Any] = {}
    if stato:
        if stato not in ORDER_STATUSES:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Stato non valido")
        filtro["status"] = stato
    elif solo_attivi:
        filtro["status"] = {"$in": STATI_ATTIVI}
    ordini = await st.tutti(st.COLL_ORDINI, filtro)
    ordini.sort(key=lambda o: str(o.get("created_at") or ""))
    return ordini[-limite:]


async def aggiorna_stato(ordine_id: str, stato: str) -> Dict[str, Any]:
    if stato not in ORDER_STATUSES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Stato non valido")
    ordine = await st.aggiorna(st.COLL_ORDINI, {"id": ordine_id}, {"status": stato, "updated_at": st.adesso()})
    if not ordine:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ordine non trovato")
    return ordine


async def aggiorna_pagamento(ordine_id: str, pagato: bool, metodo: Optional[str]) -> Dict[str, Any]:
    ordine = await st.aggiorna(st.COLL_ORDINI, {"id": ordine_id}, {"paid": bool(pagato), "payment_method": metodo, "updated_at": st.adesso()})
    if not ordine:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ordine non trovato")
    return ordine


async def elimina_ordine(ordine_id: str) -> None:
    if not await st.elimina(st.COLL_ORDINI, {"id": ordine_id}):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ordine non trovato")
