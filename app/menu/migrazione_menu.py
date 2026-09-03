"""Migrazione controllata dei dati dell'app Menu nel registro del gestionale.

Sorgente: il progetto Supabase dell'app Menu (condiviso con Lotti), letto
via PostgREST con la chiave dell'app (env ``MENU_SUPABASE_URL`` e
``MENU_SUPABASE_KEY``, solo su Render). Tabelle ``menu_*`` piu' il
magazzino bar in ``lotti_documents`` (collection ``magazzino_bar_prodotti``).

Destinazione: collezioni omonime nel registro unico. Le immagini (Supabase
Storage, Qromo, sito Ceraldi) vengono scaricate e messe nell'archivio binari
a contenuto: il campo ``image`` diventa ``/api/menu/pubblico/immagini/<id>``
e l'indirizzo originale resta in ``image_origine``. Un'immagine che non si
riesce a scaricare mantiene l'URL originale e viene contata.

Regole (CLAUDE.md "cutover"): idempotente (ogni collezione viene svuotata e
reinserita dai suoi id), confronto dei conteggi sorgente/destinazione, mai
cancellazione della sorgente.

Uso: ``POST /api/menu/admin/migrazione-menu`` (solo admin) oppure da riga di
comando con le env del gestionale:

    python -m app.menu.migrazione_menu --dry-run
    python -m app.menu.migrazione_menu
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional

import httpx

from app.menu import storage as st

logger = logging.getLogger(__name__)

PAGINA = 1000
TABELLE = [
    "menu_categories", "menu_subcategories", "menu_products", "menu_allergens",
    "menu_qrcode_config", "menu_orders", "menu_sale", "menu_warehouse_movements",
]
COLLEZIONE_LOTTI = "magazzino_bar_prodotti"

Progress = Optional[Callable[[str, int], None]]


class SorgenteMenu:
    def __init__(self, url: str, key: str):
        self.base = url.rstrip("/") + "/rest/v1/"
        self.client = httpx.AsyncClient(
            headers={"apikey": key, "Authorization": f"Bearer {key}"}, timeout=60.0, follow_redirects=True,
        )

    async def chiudi(self) -> None:
        await self.client.aclose()

    async def righe(self, tabella: str, filtro: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        offset = 0
        while True:
            params = dict(filtro or {})
            params["select"] = "*"
            r = await self.client.get(
                self.base + tabella, params=params,
                headers={"Range-Unit": "items", "Range": f"{offset}-{offset + PAGINA - 1}"},
            )
            if r.status_code == 404:
                logger.warning("Tabella sorgente %s assente", tabella)
                return out
            r.raise_for_status()
            blocco = r.json()
            out.extend(blocco)
            if len(blocco) < PAGINA:
                return out
            offset += PAGINA

    async def scarica(self, url: str) -> Optional[tuple]:
        try:
            r = await self.client.get(url, headers={"Accept": "image/*"})
            r.raise_for_status()
            tipo = (r.headers.get("content-type") or "").split(";")[0].strip() or "image/jpeg"
            if not tipo.startswith("image/"):
                return None
            return r.content, tipo
        except Exception as exc:  # rete, 404, timeout: si conta e si va avanti
            logger.warning("Immagine non scaricata %s: %s", url, exc)
            return None


# ------------------------------------------------------------------ mappature

def _cat(r: Dict[str, Any]) -> Dict[str, Any]:
    return {"id": r["id"], "name": r.get("name"), "nameIT": r.get("name_it"), "image": r.get("image")}


def _sotto(r: Dict[str, Any]) -> Dict[str, Any]:
    return {"id": r["id"], "category_id": r.get("category_id"), "name": r.get("name"), "nameIT": r.get("name_it"), "image": r.get("image")}


def _prod(r: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": r["id"], "category_id": r.get("category_id"), "subcategory_id": r.get("subcategory_id"),
        "name": r.get("name"), "nameIT": r.get("name_it"), "price": r.get("price"),
        "description": r.get("description"), "descriptionIT": r.get("description_it"),
        "allergens": r.get("allergens") or [], "image": r.get("image"),
    }


def _allergene(r: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": r["id"], "name": r.get("name"), "nameIT": r.get("name_it"), "icon": r.get("icon"),
        "descriptionIT": r.get("description_it"), "descriptionEN": r.get("description_en"),
    }


def _ordine(r: Dict[str, Any]) -> Dict[str, Any]:
    r = dict(r)
    r["table"] = r.pop("table_name", None)
    return r


def _magazzino(r: Dict[str, Any]) -> Dict[str, Any]:
    data = dict(r.get("data") or {})
    data["id"] = r.get("doc_id")
    data.setdefault("created_at", r.get("created_at"))
    data.setdefault("updated_at", r.get("updated_at"))
    return data


MAPPE = {
    "menu_categories": (st.COLL_CATEGORIE, _cat),
    "menu_subcategories": (st.COLL_SOTTOCATEGORIE, _sotto),
    "menu_products": (st.COLL_PRODOTTI, _prod),
    "menu_allergens": (st.COLL_ALLERGENI, _allergene),
    "menu_qrcode_config": (st.COLL_QRCODE, dict),
    "menu_orders": (st.COLL_ORDINI, _ordine),
    "menu_sale": (st.COLL_SALE, dict),
    "menu_warehouse_movements": (st.COLL_MOVIMENTI, dict),
}


async def _porta_immagini(sorgente: SorgenteMenu, docs: List[Dict[str, Any]], cache: Dict[str, Optional[str]], esito: Dict[str, int]) -> None:
    for doc in docs:
        url = doc.get("image")
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            continue
        if url not in cache:
            scaricata = await sorgente.scarica(url)
            if scaricata is None:
                cache[url] = None
                esito["immagini_non_scaricate"] += 1
            else:
                contenuto, tipo = scaricata
                nome = url.rsplit("/", 1)[-1].split("?", 1)[0] or "immagine"
                salvata = await st.salva_immagine(contenuto, nome, tipo)
                cache[url] = salvata["url"]
                esito["immagini_scaricate"] += 1
        if cache[url]:
            doc["image_origine"] = url
            doc["image"] = cache[url]


async def migra(url: str, key: str, *, dry_run: bool = False, con_immagini: bool = True, progress: Progress = None) -> Dict[str, Any]:
    sorgente = SorgenteMenu(url, key)
    esito: Dict[str, Any] = {
        "dry_run": dry_run, "tabelle": {}, "immagini_scaricate": 0, "immagini_non_scaricate": 0, "coincide": True,
    }
    cache: Dict[str, Optional[str]] = {}
    try:
        blocchi: List[tuple] = []
        for tabella in TABELLE:
            collezione, mappa = MAPPE[tabella]
            righe = await sorgente.righe(tabella)
            docs = [mappa(r) for r in righe if r.get("id") is not None]
            blocchi.append((tabella, collezione, docs))
        righe = await sorgente.righe("lotti_documents", {"collection": f"eq.{COLLEZIONE_LOTTI}"})
        blocchi.append(("lotti_documents/" + COLLEZIONE_LOTTI, st.COLL_MAGAZZINO_BAR, [_magazzino(r) for r in righe if r.get("doc_id")]))

        for tabella, collezione, docs in blocchi:
            if progress:
                progress(tabella, len(docs))
            if not dry_run:
                if con_immagini and collezione in (st.COLL_CATEGORIE, st.COLL_SOTTOCATEGORIE, st.COLL_PRODOTTI):
                    await _porta_immagini(sorgente, docs, cache, esito)
                await st.elimina(collezione, {})
                for doc in docs:
                    await st.inserisci(collezione, doc)
            destinazione = len(docs) if dry_run else await st.db()[collezione].count_documents({})
            esito["tabelle"][tabella] = {"sorgente": len(docs), "destinazione": destinazione, "collezione": collezione}
            if destinazione != len(docs):
                esito["coincide"] = False
    finally:
        await sorgente.chiudi()
    return esito


def _main() -> None:
    import os

    from app.database import Database

    parser = argparse.ArgumentParser(description="Migrazione dati app Menu -> GestionaleCloud")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--senza-immagini", action="store_true")
    args = parser.parse_args()
    url, key = os.environ.get("MENU_SUPABASE_URL"), os.environ.get("MENU_SUPABASE_KEY")
    if not (url and key):
        raise SystemExit("Impostare MENU_SUPABASE_URL e MENU_SUPABASE_KEY nell'ambiente")

    async def _run():
        await Database.connect_db()
        try:
            esito = await migra(url, key, dry_run=args.dry_run, con_immagini=not args.senza_immagini, progress=lambda n, c: print(f"{n}: {c}"))
        finally:
            await Database.close_db()
        print(esito)
        if not esito["coincide"]:
            raise SystemExit(2)

    asyncio.run(_run())


if __name__ == "__main__":
    _main()
