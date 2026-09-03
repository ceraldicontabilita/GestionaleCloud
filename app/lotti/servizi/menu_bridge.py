"""Ponte Lotti -> Menu digitale (richiesta del titolare, 03/09/2026):
"quando aggiungo un prodotto in Lotti fai in modo che lo aggiungi anche in
Menu con le stesse immagini e scelgo io se far comparire nel menu pubblico".

La fonte e' la ricetta di Lotti (collezione ``ricette``): ogni ricetta viene
SEMPRE replicata in ``menu_products`` (tabelle del Menu, progetto Supabase
``Lotti-HACCP``, client PostgREST sincrono di ``app.menu.supabase_client``)
con ``origine = "lotti"`` e chiave idempotente ``lotti_ref = "ricetta:<id>"``.
La colonna ``visible`` replica il flag ``menu_pubblico`` della ricetta: il
titolare la vede nell'area admin del Menu e decide se mostrarla ai clienti.

Immagini: i byte della foto (collezione ``foto_files`` di Lotti) vengono
copiati nel bucket Storage ``menu-images`` al percorso ``lotti/<foto_id>.<ext>``
e il prodotto Menu usa l'URL pubblico. L'id foto e' immutabile per contenuto
(un nuovo upload in Lotti crea un nuovo id), quindi se la riga Menu punta gia'
allo stesso ``foto_id`` non si ricarica nulla.

Il ponte non deve MAI far fallire un endpoint di Lotti: le funzioni pubbliche
restituiscono sempre un dizionario ``{"esito": ...}`` e non sollevano
eccezioni. Senza ``MENU_SUPABASE_URL`` (test di Lotti, sviluppo locale)
l'esito e' ``non_configurato`` e nessuna chiamata parte.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Optional

from app.menu.supabase_client import supabase

logger = logging.getLogger("uvicorn.error")

ORIGINE_LOTTI = "lotti"
STORAGE_BUCKET = "menu-images"
STORAGE_PREFIX = "lotti"
TABELLA_CATEGORIE = "menu_categories"
TABELLA_SOTTOCATEGORIE = "menu_subcategories"
TABELLA_PRODOTTI = "menu_products"

CATEGORIA_NOME = "Ceraldi Production"
CATEGORIA_NOME_IT = "Produzione Ceraldi"

# Gli id di menu_* sono assegnati dall'app (max(id)+1, come in
# menu_routes.py). Le righe importate da Qromo usano gli id di Qromo: per non
# collidere con un futuro prodotto Qromo, le righe create da Lotti partono da
# una base alta.
ID_MINIMO_LOTTI = 1_000_000

# reparto Lotti -> sottocategoria Menu (name, name_it)
SOTTOCATEGORIE_REPARTO = {
    "pasticceria": ("Pastry", "Pasticceria"),
    "rosticceria": ("Rotisserie", "Rosticceria"),
    "bar": ("Bar", "Bar"),
}
SOTTOCATEGORIA_ALTRO = ("Other", "Altro")

# Allergeni Lotti (app/lotti/allergeni.py, ALLERGENI_14) -> i 14 id UE del Menu
# (menu_allergens, seed_routes.py). Tutto il resto viene ignorato.
MAPPA_ALLERGENI_MENU = {
    "glutine": "gluten",
    "latte": "milk",
    "lattosio": "milk",
    "uova": "eggs",
    "frutta a guscio": "nuts",
    "pesce": "fish",
    "soia": "soy",
    "solfiti": "sulphites",
    "anidride solforosa": "sulphites",
    "crostacei": "crustaceans",
    "molluschi": "molluscs",
    "sedano": "celery",
    "senape": "mustard",
    "sesamo": "sesame",
    "lupini": "lupin",
    "arachidi": "peanuts",
}

ESTENSIONE_DA_MIME = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


def menu_configurato() -> bool:
    return bool(os.environ.get("MENU_SUPABASE_URL", "").strip().strip('"').strip("'"))


def lotti_ref_ricetta(ricetta_id: str) -> str:
    return f"ricetta:{ricetta_id}"


# ================== Trasformazioni pure ==================

def mappa_allergeni(allergeni: Optional[list]) -> list[str]:
    """Da nomi Lotti ("Glutine", "Frutta a guscio", ...) agli id del Menu."""
    risultato: list[str] = []
    for voce in allergeni or []:
        chiave = str(voce or "").strip().casefold()
        mappato = MAPPA_ALLERGENI_MENU.get(chiave)
        if mappato and mappato not in risultato:
            risultato.append(mappato)
    return risultato


def prezzo_menu(prezzo: Any) -> Optional[str]:
    """Formato del seed originale del Menu (``"3.50€"``); None se assente."""
    if prezzo in (None, ""):
        return None
    try:
        valore = float(prezzo)
    except (TypeError, ValueError):
        return None
    if valore <= 0:
        return None
    return f"{valore:.2f}€"


def _sottocategoria_per_reparto(reparto: Any) -> tuple[str, str]:
    return SOTTOCATEGORIE_REPARTO.get(str(reparto or "").strip().casefold(), SOTTOCATEGORIA_ALTRO)


def _estensione(mime: str) -> str:
    return ESTENSIONE_DA_MIME.get((mime or "").split(";", 1)[0].strip().casefold(), "jpg")


def _foto_id_da_url(foto_url: Any) -> Optional[str]:
    """Id foto dagli URL interni di Lotti ``/api/foto/<id>[?v=...]``."""
    if not foto_url:
        return None
    path = str(foto_url).split("?", 1)[0].rstrip("/")
    marker = "/api/foto/"
    if marker not in path:
        return None
    return path.split(marker, 1)[1] or None


def percorso_storage(foto_id: str, mime: str) -> str:
    return f"{STORAGE_PREFIX}/{foto_id}.{_estensione(mime)}"


def _descrizione(ricetta: dict) -> Optional[str]:
    # Solo `descrizione`: il campo `note` della ricetta e' "Note / Procedimento"
    # (FormRicetta.jsx) e non deve finire nel menu pubblico dei clienti.
    testo = str(ricetta.get("descrizione") or "").strip()
    return testo or None


# ================== Accesso al Menu (client sincrono, eseguito in thread) ==================

def _prossimo_id(tabella: str) -> int:
    ultimo = supabase.table(tabella).select("id").order("id", desc=True).limit(1).execute()
    massimo = int(ultimo.data[0]["id"]) if ultimo.data else 0
    return max(massimo + 1, ID_MINIMO_LOTTI)


def _categoria_lotti_id() -> int:
    res = (
        supabase.table(TABELLA_CATEGORIE).select("id")
        .eq("origine", ORIGINE_LOTTI).eq("name_it", CATEGORIA_NOME_IT)
        .limit(1).execute()
    )
    if res.data:
        return int(res.data[0]["id"])
    nuovo_id = _prossimo_id(TABELLA_CATEGORIE)
    supabase.table(TABELLA_CATEGORIE).insert({
        "id": nuovo_id, "name": CATEGORIA_NOME, "name_it": CATEGORIA_NOME_IT,
        "image": None, "origine": ORIGINE_LOTTI,
    }).execute()
    return nuovo_id


def _sottocategoria_lotti_id(categoria_id: int, reparto: Any) -> int:
    nome, nome_it = _sottocategoria_per_reparto(reparto)
    res = (
        supabase.table(TABELLA_SOTTOCATEGORIE).select("id")
        .eq("origine", ORIGINE_LOTTI).eq("category_id", categoria_id).eq("name_it", nome_it)
        .limit(1).execute()
    )
    if res.data:
        return int(res.data[0]["id"])
    nuovo_id = _prossimo_id(TABELLA_SOTTOCATEGORIE)
    supabase.table(TABELLA_SOTTOCATEGORIE).insert({
        "id": nuovo_id, "category_id": categoria_id, "name": nome, "name_it": nome_it,
        "image": None, "origine": ORIGINE_LOTTI,
    }).execute()
    return nuovo_id


def _riga_esistente(lotti_ref: str) -> Optional[dict]:
    res = supabase.table(TABELLA_PRODOTTI).select("*").eq("lotti_ref", lotti_ref).limit(1).execute()
    return res.data[0] if res.data else None


def _carica_immagine(foto: dict) -> str:
    """Copia i byte della foto Lotti nel bucket del Menu e restituisce l'URL pubblico."""
    mime = str(foto.get("mime") or "image/jpeg")
    percorso = percorso_storage(str(foto["_id"]), mime)
    supabase.storage.from_(STORAGE_BUCKET).upload(
        percorso, bytes(foto["data"]), {"content-type": mime, "upsert": "true"}
    )
    return supabase.storage.from_(STORAGE_BUCKET).get_public_url(percorso)


def _immagine_per_prodotto(ricetta: dict, foto: Optional[dict], esistente: Optional[dict]) -> Optional[str]:
    """URL da scrivere in ``image``: la foto Lotti copiata su Storage (senza
    ricaricarla se la riga punta gia' allo stesso foto_id), altrimenti un
    eventuale URL assoluto gia' pubblico, altrimenti quello gia' presente."""
    if foto and foto.get("data"):
        foto_id = str(foto["_id"])
        attuale = (esistente or {}).get("image") or ""
        if f"/{STORAGE_PREFIX}/{foto_id}." in attuale:
            return attuale
        return _carica_immagine(foto)
    foto_url = str(ricetta.get("foto_url") or "")
    if foto_url.startswith(("http://", "https://")):
        return foto_url
    return (esistente or {}).get("image")


def _pubblica_sync(ricetta: dict, foto: Optional[dict], visibile: bool) -> dict:
    lotti_ref = lotti_ref_ricetta(str(ricetta["id"]))
    esistente = _riga_esistente(lotti_ref)
    categoria_id = _categoria_lotti_id()
    sottocategoria_id = _sottocategoria_lotti_id(categoria_id, ricetta.get("reparto"))
    nome = str(ricetta.get("nome") or "").strip() or f"Ricetta {ricetta['id']}"
    descrizione = _descrizione(ricetta)
    immagine = _immagine_per_prodotto(ricetta, foto, esistente)

    riga = {
        "category_id": categoria_id,
        "subcategory_id": sottocategoria_id,
        "name": nome,
        "name_it": nome,
        "price": prezzo_menu(ricetta.get("prezzo_vendita")) or "",
        "description": descrizione,
        "description_it": descrizione,
        "allergens": mappa_allergeni(ricetta.get("allergeni") or ricetta.get("allergeni_auto")),
        "image": immagine,
        "origine": ORIGINE_LOTTI,
        "lotti_ref": lotti_ref,
        "visible": bool(visibile),
    }

    if esistente:
        prodotto_id = int(esistente["id"])
        supabase.table(TABELLA_PRODOTTI).update(riga).eq("id", prodotto_id).execute()
        esito = "aggiornato"
    else:
        prodotto_id = _prossimo_id(TABELLA_PRODOTTI)
        supabase.table(TABELLA_PRODOTTI).insert({"id": prodotto_id, **riga}).execute()
        esito = "pubblicato"

    return {
        "esito": esito,
        "menu_product_id": prodotto_id,
        "lotti_ref": lotti_ref,
        "visible": bool(visibile),
        "image": immagine,
        "category_id": categoria_id,
        "subcategory_id": sottocategoria_id,
    }


def _rimuovi_sync(lotti_ref: str) -> dict:
    res = supabase.table(TABELLA_PRODOTTI).delete().eq("lotti_ref", lotti_ref).execute()
    rimossi = len(res.data or []) if getattr(res, "data", None) is not None else 0
    return {"esito": "rimosso", "lotti_ref": lotti_ref, "rimossi": rimossi}


# ================== API asincrona usata dal router ricette ==================

async def _foto_ricetta(ricetta: dict, db: Any) -> Optional[dict]:
    foto_id = _foto_id_da_url(ricetta.get("foto_url"))
    if not foto_id or db is None:
        return None
    return await db.foto_files.find_one({"_id": foto_id})


async def pubblica_prodotto_nel_menu(ricetta: dict, *, visibile: bool, db: Any = None) -> dict:
    """Crea o aggiorna nel Menu il prodotto corrispondente alla ricetta.
    Non solleva mai: esito ``pubblicato`` / ``aggiornato`` / ``non_configurato`` / ``errore``."""
    if not menu_configurato():
        return {"esito": "non_configurato", "lotti_ref": lotti_ref_ricetta(str(ricetta.get("id")))}
    try:
        if db is None:
            from app.lotti.db import database as db
        foto = await _foto_ricetta(ricetta, db)
        return await asyncio.to_thread(_pubblica_sync, ricetta, foto, visibile)
    except Exception as e:  # pragma: no cover - dipende dal servizio esterno
        logger.exception("Lotti->Menu: pubblicazione ricetta %s fallita", ricetta.get("id"))
        return {"esito": "errore", "errore": str(e), "lotti_ref": lotti_ref_ricetta(str(ricetta.get("id")))}


async def rimuovi_prodotto_dal_menu(lotti_ref: str) -> dict:
    """Toglie dal Menu la riga con quel ``lotti_ref``. Non solleva mai."""
    if not menu_configurato():
        return {"esito": "non_configurato", "lotti_ref": lotti_ref}
    try:
        return await asyncio.to_thread(_rimuovi_sync, lotti_ref)
    except Exception as e:  # pragma: no cover - dipende dal servizio esterno
        logger.exception("Lotti->Menu: rimozione %s fallita", lotti_ref)
        return {"esito": "errore", "errore": str(e), "lotti_ref": lotti_ref}
