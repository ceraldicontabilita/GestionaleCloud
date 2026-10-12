"""Prezzi comunicati direttamente dai fornitori per i cataloghi.

Il valore e la sua provenienza restano separati dai prezzi realmente pagati
estratti dalle fatture XML. In questo modo un preventivo/listino non diventa
per errore evidenza contabile di un acquisto.
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.lotti.auth import require_admin
from app.lotti.db import database as db


router = APIRouter(prefix="/cataloghi", tags=["cataloghi_prezzi"])


async def _catalogo_fonte(fonte: str) -> list[dict]:
    if fonte in {"mepa", "saima"}:
        return await db.dizionario_ingredienti.find({"fonte": fonte}, {"_id": 0}).to_list(None)
    if fonte in {"acquaviva", "alpha", "alfa"}:
        fonti = ["acquaviva", "vandemoortele"] if fonte == "acquaviva" else ["alpha"]
        return await db.acquaviva_prodotti.find({"fonte": {"$in": fonti}}, {"_id": 0}).to_list(None)
    return await db.catalogo_forno_prodotti.find({"fornitore": fonte}, {"_id": 0}).to_list(None)


def _chiave_prodotto(prodotto: dict) -> str:
    valore = prodotto.get("codice_articolo") or prodotto.get("codice") or prodotto.get("id") or ""
    return str(valore).strip().casefold()


_CAMPI_PREFERITO = {
    "id", "nome", "nome_completo", "nome_standard", "nome_display", "descrizione",
    "codice", "codice_articolo", "categoria", "sottocategoria", "fornitore", "fonte",
    "immagine_url", "foto_url", "link_prodotto", "unita_confezione", "unita_vendita",
    "grammi", "peso_g", "pezzi_cartone", "pz_confezione", "qty_cartone", "ean",
    "prezzo", "prezzo_vendita", "prezzo_listino", "prezzo_fornitore", "fonte_catalogo",
    "prezzo_listino_data", "offerta_fino", "in_ricette",
}


def _snapshot_preferito(prodotto: dict, fonte: str) -> dict:
    snapshot = {k: v for k, v in prodotto.items() if k in _CAMPI_PREFERITO and v is not None}
    snapshot["fonte"] = fonte
    snapshot.setdefault("fornitore", fonte)
    snapshot["gia_acquistato"] = False
    snapshot["preferito_manuale"] = True
    return snapshot


@router.get("/preferiti/{fonte}")
async def preferiti_acquisti(fonte: str):
    from app.lotti.servizi.preferiti_cataloghi import fatture_catalogo, articoli_acquistati, collega_preferiti

    fonte = fonte.strip().lower()
    catalogo = await _catalogo_fonte(fonte)
    fatture = await fatture_catalogo(db, fonte)
    acquistati = collega_preferiti(articoli_acquistati(fatture), catalogo, fonte)
    manuali = await db.cataloghi_preferiti_manuali.find({"fonte": fonte}, {"_id": 0}).to_list(None)
    prodotti = {_chiave_prodotto(p): p for p in acquistati}
    for manuale in manuali:
        snapshot = dict(manuale.get("prodotto") or {})
        chiave = manuale.get("prodotto_chiave") or _chiave_prodotto(snapshot)
        if not chiave:
            continue
        if chiave in prodotti:
            prodotti[chiave]["preferito_manuale"] = True
        else:
            snapshot.update({"fonte": fonte, "fornitore": snapshot.get("fornitore") or fonte,
                             "gia_acquistato": False, "preferito_manuale": True})
            prodotti[chiave] = snapshot
    elenco = sorted(prodotti.values(), key=lambda p: str(p.get("nome_display") or p.get("nome_completo") or p.get("nome") or "").casefold())
    return {"prodotti": elenco, "totale": len(elenco), "acquistati": len(acquistati),
            "preferiti_manuali": len(manuali), "fatture": len(fatture)}


class PreferitoManualeUpdate(BaseModel):
    prodotto: dict
    preferito: bool = True


@router.put("/preferiti/{fonte}")
async def aggiorna_preferito_manuale(
    fonte: str,
    payload: PreferitoManualeUpdate,
    _admin=Depends(require_admin),
):
    fonte = fonte.strip().lower()
    snapshot = _snapshot_preferito(payload.prodotto, fonte)
    chiave = _chiave_prodotto(snapshot)
    if not chiave or not (snapshot.get("nome") or snapshot.get("nome_completo") or snapshot.get("nome_display")):
        raise HTTPException(422, "Prodotto non identificabile")
    filtro = {"fonte": fonte, "prodotto_chiave": chiave}
    if payload.preferito:
        await db.cataloghi_preferiti_manuali.update_one(
            filtro,
            {"$set": {**filtro, "prodotto": snapshot, "aggiornato_il": datetime.now(timezone.utc).isoformat()}},
            upsert=True,
        )
    else:
        await db.cataloghi_preferiti_manuali.delete_one(filtro)
    return {"ok": True, "preferito": payload.preferito, "prodotto_chiave": chiave}


class PrezzoFornitoreUpdate(BaseModel):
    fonte: str
    prezzo: float = Field(ge=0, le=1_000_000)
    prodotto_id: Optional[str] = ""
    codice_articolo: Optional[str] = ""
    fornitore: Optional[str] = ""


def _filtro_prodotto(payload: PrezzoFornitoreUpdate) -> tuple[str, dict]:
    fonte = (payload.fonte or "").strip().lower()
    if fonte in {"saima", "mepa"}:
        filtro = {"fonte": fonte}
        if payload.prodotto_id:
            filtro["id"] = payload.prodotto_id
        elif payload.codice_articolo:
            filtro["codice_articolo"] = payload.codice_articolo
        else:
            raise HTTPException(422, "ID o codice articolo obbligatorio")
        return "dizionario_ingredienti", filtro

    if fonte in {"acquaviva", "alpha"}:
        if not payload.prodotto_id:
            raise HTTPException(422, "ID prodotto obbligatorio")
        return "acquaviva_prodotti", {"id": payload.prodotto_id}

    fornitore = (payload.fornitore or fonte).strip().lower()
    if not fornitore or not payload.codice_articolo:
        raise HTTPException(422, "Fornitore e codice articolo obbligatori")
    return "catalogo_forno_prodotti", {
        "fornitore": fornitore,
        "codice_articolo": payload.codice_articolo,
    }


@router.put("/prezzo")
async def salva_prezzo_fornitore(
    payload: PrezzoFornitoreUpdate,
    _admin=Depends(require_admin),
):
    collezione, filtro = _filtro_prodotto(payload)
    aggiornato_il = datetime.now(timezone.utc).isoformat()
    result = await getattr(db, collezione).update_one(
        filtro,
        {"$set": {
            "prezzo_fornitore": float(payload.prezzo),
            "prezzo_fornitore_data": aggiornato_il,
            "prezzo_fornitore_fonte": "comunicato_dal_fornitore",
            "prezzo_fornitore_iva_esclusa": True,
        }},
    )
    if not result.matched_count:
        raise HTTPException(404, "Prodotto catalogo non trovato")
    return {
        "ok": True,
        "prezzo_fornitore": float(payload.prezzo),
        "prezzo_fornitore_data": aggiornato_il,
        "fonte": "comunicato_dal_fornitore",
        "iva_esclusa": True,
    }
