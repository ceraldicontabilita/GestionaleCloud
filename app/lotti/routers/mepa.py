"""
Router per catalogo MEPA Alimentari — Prodotti per pasticcerie, gelaterie, panificazione, HO.RE.CA.
Scarica e importa il catalogo dal sito mepaalimentari.com (WooCommerce) nel dizionario ingredienti.
"""

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks, Depends
from datetime import datetime, timezone
import uuid
import logging
_LOG_INIT = logging.getLogger("uvicorn.error")
import re
import asyncio
import httpx
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from app.lotti.db import database as db
from app.lotti.auth import require_admin

router = APIRouter(prefix="/mepa", tags=["mepa"])

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "it-IT,it;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
}

# Categorie principali MEPA con URL e immagini
CATEGORIE_MEPA = [
    {
        "nome": "AMIDI & MIX PER CREMA PASTICCERA",
        "url": "https://www.mepaalimentari.com/amidi-mix-per-crema-pasticcera/",
        "img": "https://berqwp-cdn.sfo3.cdn.digitaloceanspaces.com/cache/www.mepaalimentari.com/wp-content/uploads/2025/06/100-595x595.webp",
    },
    {
        "nome": "AROMI, ESSENZE & SPEZIE",
        "url": "https://www.mepaalimentari.com/aromi-essenze-spezie/",
        "img": "https://berqwp-cdn.sfo3.cdn.digitaloceanspaces.com/cache/www.mepaalimentari.com/wp-content/uploads/2025/06/101-595x595.webp",
    },
    {
        "nome": "BISCOTTERIA",
        "url": "https://www.mepaalimentari.com/biscotteria/",
        "img": "https://berqwp-cdn.sfo3.cdn.digitaloceanspaces.com/cache/www.mepaalimentari.com/wp-content/uploads/2025/06/104-595x595.webp",
    },
    {
        "nome": "CIOCCOLATO & SURROGATO",
        "url": "https://www.mepaalimentari.com/cioccolato-surrogato/",
        "img": "https://berqwp-cdn.sfo3.cdn.digitaloceanspaces.com/cache/www.mepaalimentari.com/wp-content/uploads/2025/06/106-595x595.webp",
    },
    {
        "nome": "CONFETTURE, PASSATE & GELATINE",
        "url": "https://www.mepaalimentari.com/confetture-passate-gelatine/",
        "img": "https://berqwp-cdn.sfo3.cdn.digitaloceanspaces.com/cache/www.mepaalimentari.com/wp-content/uploads/2025/06/109-595x595.webp",
    },
    {
        "nome": "CREME SPALMABILI",
        "url": "https://www.mepaalimentari.com/creme-spalmabili/",
        "img": "https://berqwp-cdn.sfo3.cdn.digitaloceanspaces.com/cache/www.mepaalimentari.com/wp-content/uploads/2025/06/110-595x595.webp",
    },
    {
        "nome": "DECORAZIONI",
        "url": "https://www.mepaalimentari.com/decorazioni/",
        "img": "https://berqwp-cdn.sfo3.cdn.digitaloceanspaces.com/cache/www.mepaalimentari.com/wp-content/uploads/2025/06/112-595x595.webp",
    },
    {
        "nome": "FARINE",
        "url": "https://www.mepaalimentari.com/farine/",
        "img": "https://berqwp-cdn.sfo3.cdn.digitaloceanspaces.com/cache/www.mepaalimentari.com/wp-content/uploads/2025/06/114-595x595.webp",
    },
    {
        "nome": "FRUTTA",
        "url": "https://www.mepaalimentari.com/frutta/",
        "img": "https://berqwp-cdn.sfo3.cdn.digitaloceanspaces.com/cache/www.mepaalimentari.com/wp-content/uploads/2025/06/115-595x595.webp",
    },
    {
        "nome": "GASTRONOMIA",
        "url": "https://www.mepaalimentari.com/gastronomia/",
        "img": "https://berqwp-cdn.sfo3.cdn.digitaloceanspaces.com/cache/www.mepaalimentari.com/wp-content/uploads/2025/06/116-595x595.webp",
    },
    {
        "nome": "GELATERIA",
        "url": "https://www.mepaalimentari.com/gelateria/",
        "img": "https://berqwp-cdn.sfo3.cdn.digitaloceanspaces.com/cache/www.mepaalimentari.com/wp-content/uploads/2025/06/117-595x595.webp",
    },
    {
        "nome": "GLASSE",
        "url": "https://www.mepaalimentari.com/glasse/",
        "img": "https://berqwp-cdn.sfo3.cdn.digitaloceanspaces.com/cache/www.mepaalimentari.com/wp-content/uploads/2025/06/118-595x595.webp",
    },
    {
        "nome": "GRASSI",
        "url": "https://www.mepaalimentari.com/grassi/",
        "img": "https://berqwp-cdn.sfo3.cdn.digitaloceanspaces.com/cache/www.mepaalimentari.com/wp-content/uploads/2025/06/119-595x595.webp",
    },
    {
        "nome": "LATTE, DERIVATI & BEVANDE VEGETALI",
        "url": "https://www.mepaalimentari.com/latte-derivati-bevande-vegetali/",
        "img": "https://berqwp-cdn.sfo3.cdn.digitaloceanspaces.com/cache/www.mepaalimentari.com/wp-content/uploads/2025/06/120-595x595.webp",
    },
    {
        "nome": "LIEVITO",
        "url": "https://www.mepaalimentari.com/lievito/",
        "img": "https://berqwp-cdn.sfo3.cdn.digitaloceanspaces.com/cache/www.mepaalimentari.com/wp-content/uploads/2025/06/121-595x595.webp",
    },
    {
        "nome": "MIX E MIGLIORATORI",
        "url": "https://www.mepaalimentari.com/mix-e-miglioratori/",
        "img": "https://berqwp-cdn.sfo3.cdn.digitaloceanspaces.com/cache/www.mepaalimentari.com/wp-content/uploads/2025/06/122-595x595.webp",
    },
    {
        "nome": "OVOPRODOTTI",
        "url": "https://www.mepaalimentari.com/ovoprodotti/",
        "img": "https://berqwp-cdn.sfo3.cdn.digitaloceanspaces.com/cache/www.mepaalimentari.com/wp-content/uploads/2025/06/123-595x595.webp",
    },
    {
        "nome": "PANNA E CREME VEGETALI",
        "url": "https://www.mepaalimentari.com/panna-e-creme-vegetali/",
        "img": "https://berqwp-cdn.sfo3.cdn.digitaloceanspaces.com/cache/www.mepaalimentari.com/wp-content/uploads/2025/06/124-595x595.webp",
    },
    {
        "nome": "PASTA DI MANDORLE",
        "url": "https://www.mepaalimentari.com/pasta-di-mandorle/",
        "img": "https://berqwp-cdn.sfo3.cdn.digitaloceanspaces.com/cache/www.mepaalimentari.com/wp-content/uploads/2025/06/125-595x595.webp",
    },
    {
        "nome": "PASTICCERIA PRONTA",
        "url": "https://www.mepaalimentari.com/pasticceria-pronta/",
        "img": "https://berqwp-cdn.sfo3.cdn.digitaloceanspaces.com/cache/www.mepaalimentari.com/wp-content/uploads/2025/06/127-595x595.webp",
    },
    {
        "nome": "PASTICCERIA SURGELATA",
        "url": "https://www.mepaalimentari.com/pasticceria-surgelata/",
        "img": "https://berqwp-cdn.sfo3.cdn.digitaloceanspaces.com/cache/www.mepaalimentari.com/wp-content/uploads/2025/06/128-595x595.webp",
    },
    {
        "nome": "ROSTICCERIA SURGELATA",
        "url": "https://www.mepaalimentari.com/rosticceria-surgelata/",
        "img": "https://berqwp-cdn.sfo3.cdn.digitaloceanspaces.com/cache/www.mepaalimentari.com/wp-content/uploads/2025/06/130-595x595.webp",
    },
    {
        "nome": "SEMIFREDDI & DESSERT",
        "url": "https://www.mepaalimentari.com/semifreddi-dessert/",
        "img": "https://berqwp-cdn.sfo3.cdn.digitaloceanspaces.com/cache/www.mepaalimentari.com/wp-content/uploads/2025/06/131-595x595.webp",
    },
    {
        "nome": "ZUCCHERO & MIELE",
        "url": "https://www.mepaalimentari.com/zucchero-miele/",
        "img": "https://berqwp-cdn.sfo3.cdn.digitaloceanspaces.com/cache/www.mepaalimentari.com/wp-content/uploads/2025/06/133-595x595.webp",
    },
]

# Categorie presenti nel catalogo ufficiale ma assenti dalla prima versione del
# connettore. L'immagine resta vuota: la UI mostra il segnaposto finché il sito
# non fornisce una miniatura di categoria stabile; le foto prodotto sono invece
# sempre recuperate dalle singole schede.
CATEGORIE_MEPA.extend([
    {"nome": "ATTREZZATURE", "url": "https://www.mepaalimentari.com/attrezzature/", "img": ""},
    {"nome": "BAGNE", "url": "https://www.mepaalimentari.com/bagne/", "img": ""},
    {"nome": "CARTA & PLASTICA", "url": "https://www.mepaalimentari.com/carta-plastica/", "img": ""},
    {"nome": "COADIUVANTI, EMULSIONANTI", "url": "https://www.mepaalimentari.com/coadiuvanti-emulsionanti/", "img": ""},
    {"nome": "COLORANTI ALIMENTARI", "url": "https://www.mepaalimentari.com/coloranti-alimentari/", "img": ""},
    {"nome": "CRUNCH", "url": "https://www.mepaalimentari.com/crunch/", "img": ""},
    {"nome": "DETERGENZA", "url": "https://www.mepaalimentari.com/detergenza/", "img": ""},
    {"nome": "PASTE DA DECORAZIONE", "url": "https://www.mepaalimentari.com/paste-da-decorazione/", "img": ""},
    {"nome": "POMODORI", "url": "https://www.mepaalimentari.com/pomodori/", "img": ""},
    {"nome": "TOPPING", "url": "https://www.mepaalimentari.com/topping/", "img": ""},
])


async def scrape_pagina_mepa(
    url: str, categoria: str, img_categoria: str, pagina: int = 1
) -> tuple:
    """Scarica i prodotti di una pagina di una categoria MEPA (WooCommerce)."""
    prodotti = []
    ha_pagina_successiva = False

    page_url = url if pagina == 1 else f"{url}page/{pagina}/"

    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            r = await client.get(page_url, headers=HEADERS)
            if r.status_code != 200:
                return prodotti, False

            soup = BeautifulSoup(r.text, "html.parser")

            # WooCommerce/NASA theme MEPA: prodotti in .product-item.grid
            items = (
                soup.select(".product-item.grid")
                or soup.find_all("li", class_=re.compile(r"product"))
                or soup.find_all("article", class_=re.compile(r"product"))
                or soup.find_all("div", class_=re.compile(r"product-item|wc-product"))
            )

            for item in items:
                # Nome prodotto
                nome_tag = (
                    item.select_one("h2.product-title")
                    or item.select_one(".woocommerce-loop-product__title")
                    or item.find("h2")
                    or item.find("h3")
                    or item.find("h4")
                )
                if not nome_tag:
                    continue
                nome = nome_tag.get_text(strip=True)
                if len(nome) < 2:
                    continue

                # Immagine — MEPA usa CDN con attributo data-berqwpsrc
                img_tag = item.find("img")
                img_url = img_categoria
                if img_tag:
                    src = (
                        img_tag.get("data-berqwpsrc")  # CDN MEPA
                        or img_tag.get("data-lazy-src")
                        or img_tag.get("data-src")
                        or img_tag.get("src")
                        or ""
                    )
                    if src and "base64" not in src and not src.startswith("data:"):
                        img_url = src.split("?")[0]  # rimuovi parametri CDN

                # Prezzo
                prezzo = 0.0
                prezzo_tag = item.find(class_=re.compile(r"price|woocommerce-Price"))
                if prezzo_tag:
                    prezzo_txt = prezzo_tag.get_text(strip=True)
                    prezzo_match = re.search(r"[\d,]+\.?\d*", prezzo_txt.replace(",", "."))
                    if prezzo_match:
                        try:
                            prezzo = float(prezzo_match.group())
                        except Exception:
                            _LOG_INIT.debug("[mepa] errore non bloccante ignorato")

                # Link prodotto — MEPA usa href diretto
                link_tag = item.select_one("a[href*='/prodotto/']") or item.find("a", href=True)
                link_url = (
                    link_tag["href"]
                    if link_tag
                    and link_tag.get("href")
                    and link_tag["href"] != "javascript:void(0);"
                    else ""
                )

                # SKU/codice dal link o da span.sku
                codice = ""
                sku_tag = item.find(class_=re.compile(r"sku"))
                if sku_tag:
                    codice = sku_tag.get_text(strip=True)

                # Categoria da breadcrumb o tag
                cat_tag = item.find(class_=re.compile(r"cat-links|product-cat|category"))
                categoria_prodotto = cat_tag.get_text(strip=True) if cat_tag else categoria

                prodotti.append(
                    {
                        "nome": nome,
                        "codice_articolo": codice,
                        "categoria": categoria,
                        "categoria_prodotto": categoria_prodotto,
                        "immagine_url": img_url,
                        "prezzo_listino": prezzo,
                        "link_prodotto": link_url,
                        "fornitore": "MEPA Alimentari",
                        "fonte": "mepa",
                    }
                )

            # Controlla paginazione
            next_btn = soup.find("a", class_=re.compile(r"next|page-next")) or soup.find(
                "a", string=re.compile(r"Successiv|Next|→")
            )
            ha_pagina_successiva = bool(next_btn) and len(prodotti) >= 10

    except Exception as e:
        print(f"[MEPA] Errore scraping {categoria} p{pagina}: {e}")

    return prodotti, ha_pagina_successiva


def _url_mepa_sicuro(url: str) -> bool:
    parsed = urlparse(str(url or ""))
    return parsed.scheme == "https" and parsed.hostname in {
        "mepaalimentari.com", "www.mepaalimentari.com"
    }


def _parse_dettaglio_mepa(html: str) -> dict:
    """Estrae solo informazioni dichiarate nella pagina ufficiale MEPA."""
    extra = {}
    soup = BeautifulSoup(html or "", "html.parser")

    sku = soup.find(class_=re.compile(r"sku"))
    if sku:
        extra["codice_articolo"] = sku.get_text(" ", strip=True)
    if not extra.get("codice_articolo"):
        for heading in soup.select(".elementor-heading-title"):
            testo = heading.get_text(" ", strip=True)
            match = re.match(r"COD\s*:\s*(.+)", testo, re.I)
            if match:
                extra["codice_articolo"] = match.group(1).strip()
                break

    desc_tag = soup.select_one(
        ".woocommerce-product-details__short-description, .product-short-description"
    )
    if desc_tag:
        extra["descrizione"] = desc_tag.get_text(" ", strip=True)[:500]

    desc_long = soup.select_one("#tab-description, .woocommerce-Tabs-panel--description")
    if desc_long:
        extra["descrizione_lunga"] = desc_long.get_text(" ", strip=True)[:1000]

    breadcrumb = soup.select_one("nav.woocommerce-breadcrumb")
    categoria = ""
    if breadcrumb:
        parti = [p.strip() for p in breadcrumb.get_text("/", strip=True).split("/")]
        parti = [p for p in parti if p and p.lower() != "home"]
        if parti:
            categoria = " / ".join(parti)
            extra["categoria_dettaglio"] = categoria

    confezione = ""
    for heading in soup.select(".elementor-heading-title"):
        testo = heading.get_text(" ", strip=True)
        if re.match(r"^(CT|CF|CRT|CONF)\b", testo, re.I):
            confezione = testo
            extra["unita_confezione"] = testo
            break

    # Molte pagine MEPA non pubblicano testo promozionale. In quel caso la
    # descrizione resta comunque utile e verificabile: usa esclusivamente
    # confezione e percorso categoria presenti nella pagina ufficiale.
    if not extra.get("descrizione"):
        parti = []
        if categoria:
            parti.append(f"Categoria: {categoria}")
        if confezione:
            parti.append(f"Confezione: {confezione}")
        if parti:
            extra["descrizione"] = " \u00b7 ".join(parti)

    foto = soup.select_one('meta[property="og:image"]')
    if foto and foto.get("content"):
        extra["immagine_prodotto"] = foto["content"].strip()
    return extra


async def scrape_dettaglio_mepa(
    url_prodotto: str,
    client: httpx.AsyncClient | None = None,
) -> dict:
    """Scarica dettagli aggiuntivi di un singolo prodotto MEPA."""
    if not _url_mepa_sicuro(url_prodotto):
        return {}
    try:
        async def _scarica(active_client: httpx.AsyncClient) -> dict:
            r = await active_client.get(url_prodotto, headers=HEADERS)
            if r.status_code != 200:
                return {}
            return _parse_dettaglio_mepa(r.text)

        if client is not None:
            return await _scarica(client)
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as own_client:
            return await _scarica(own_client)
    except Exception:
        _LOG_INIT.debug("[mepa] errore non bloccante ignorato")
        return {}


@router.get("/categorie")
async def get_categorie_mepa():
    """Lista categorie MEPA con immagini."""
    return CATEGORIE_MEPA


@router.get("/prodotti")
async def get_prodotti_mepa(
    categoria: str = Query("", description="Filtra per categoria"),
    q: str = Query("", description="Ricerca per nome"),
    limit: int = Query(100),
    skip: int = Query(0),
):
    """Prodotti MEPA dal DB locale."""
    query = {"fonte": "mepa"}
    if categoria:
        query["categoria"] = {"$regex": categoria, "$options": "i"}
    if q:
        query["$or"] = [
            {"nome": {"$regex": q, "$options": "i"}},
            {"codice_articolo": {"$regex": q, "$options": "i"}},
            {"descrizione": {"$regex": q, "$options": "i"}},
        ]

    prodotti = (
        await db.dizionario_ingredienti.find(query, {"_id": 0})
        .skip(skip)
        .limit(limit)
        .to_list(limit)
    )
    # Aggancia il prezzo realmente pagato dalle fatture MEPA (match per nome ufficiale).
    try:
        from app.lotti.routers.utils import prezzi_fatture_per_fornitore, applica_prezzo_da_fatture
        prezzi = await prezzi_fatture_per_fornitore(db, "mepa")
        prodotti = applica_prezzo_da_fatture(prodotti, prezzi)
    except Exception:
        _LOG_INIT.debug("[mepa] errore non bloccante ignorato")
    total = await db.dizionario_ingredienti.count_documents(query)
    return {"prodotti": prodotti, "total": total}


@router.post("/scraping/avvia")
async def avvia_scraping_mepa(
    background_tasks: BackgroundTasks,
    solo_categorie: list = None,
    con_dettagli: bool = False,
    _admin=Depends(require_admin),
):
    """Avvia scraping catalogo MEPA in background."""
    stato = await db.sync_status.find_one({"_id": "scraping_mepa"}, {"_id": 0})
    if stato and stato.get("stato") == "in_corso":
        return {"avviato": False, "messaggio": "Aggiornamento MEPA già in corso"}
    await db.sync_status.update_one(
        {"_id": "scraping_mepa"},
        {"$set": {
            "stato": "in_corso",
            "iniziato_il": datetime.now(timezone.utc).isoformat(),
            "errore": "",
        }},
        upsert=True,
    )

    async def esegui_scraping():
        cat_list = solo_categorie or CATEGORIE_MEPA
        totale_importati = 0
        totale_aggiornati = 0

        for cat in cat_list:
            pagina = 1
            ha_pagina = True

            while ha_pagina and pagina <= 10:  # max 10 pagine per categoria
                prodotti, ha_pagina = await scrape_pagina_mepa(
                    cat["url"], cat["nome"], cat["img"], pagina
                )

                for p in prodotti:
                    nome_norm = p["nome"].lower().strip()
                    p["nome_normalizzato"] = nome_norm
                    p["nome_display"] = p["nome"].title()
                    p["attivo"] = True
                    p["is_mepa"] = True
                    p["data_aggiornamento"] = datetime.now(timezone.utc).isoformat()
                    p["prezzo_kg"] = p.get("prezzo_listino", 0.0)
                    p["costo_per_pezzo"] = 0.0

                    # Dettagli aggiuntivi
                    if con_dettagli and p.get("link_prodotto"):
                        extra = await scrape_dettaglio_mepa(p["link_prodotto"])
                        p.update(extra)
                        await asyncio.sleep(0.3)

                    filtro = {"fonte": "mepa"}
                    if p.get("codice_articolo"):
                        filtro["codice_articolo"] = p["codice_articolo"]
                    else:
                        filtro["nome_normalizzato"] = nome_norm

                    result = await db.dizionario_ingredienti.update_one(
                        filtro,
                        {"$set": p, "$setOnInsert": {"id": str(uuid.uuid4())}},
                        upsert=True,
                    )
                    if result.upserted_id is not None:
                        totale_importati += 1
                    else:
                        totale_aggiornati += 1

                pagina += 1
                await asyncio.sleep(0.8)  # rispetta il server MEPA

        await db.log_scraping.insert_one(
            {
                "fonte": "mepa",
                "data": datetime.now(timezone.utc).isoformat(),
                "importati": totale_importati,
                "aggiornati": totale_aggiornati,
            }
        )
        print(
            f"[MEPA] Scraping completato: {totale_importati} importati, {totale_aggiornati} aggiornati"
        )

    async def esegui_scraping_con_stato():
        try:
            await esegui_scraping()
            await db.sync_status.update_one(
                {"_id": "scraping_mepa"},
                {"$set": {
                    "stato": "completato",
                    "completato_il": datetime.now(timezone.utc).isoformat(),
                    "errore": "",
                }},
            )
        except Exception as exc:
            await db.sync_status.update_one(
                {"_id": "scraping_mepa"},
                {"$set": {
                    "stato": "errore",
                    "completato_il": datetime.now(timezone.utc).isoformat(),
                    "errore": str(exc)[:1000],
                }},
            )
            _LOG_INIT.exception("Scraping MEPA fallito")

    background_tasks.add_task(esegui_scraping_con_stato)
    return {"avviato": True, "message": "Scraping MEPA avviato in background", "categorie": len(CATEGORIE_MEPA)}


@router.get("/scraping/stato")
async def stato_scraping_mepa():
    """Stato ultimo scraping MEPA."""
    ultimo = await db.log_scraping.find_one({"fonte": "mepa"}, {"_id": 0}, sort=[("data", -1)])
    count = await db.dizionario_ingredienti.count_documents({"fonte": "mepa"})
    stato = await db.sync_status.find_one({"_id": "scraping_mepa"}, {"_id": 0})

    return {
        "prodotti_nel_db": count,
        "ultimo_scraping": ultimo,
        "stato": (stato or {}).get("stato", "mai_eseguito"),
        "errore": (stato or {}).get("errore", ""),
    }


@router.get("/dettaglio-prodotto")
async def dettaglio_prodotto_mepa(url: str = Query(..., description="URL pagina prodotto MEPA")):
    """
    Scarica on-demand i dettagli di un singolo prodotto MEPA.
    Include immagine grande, descrizione, sku, dati nutrizionali.
    """
    if not _url_mepa_sicuro(url):
        raise HTTPException(status_code=400, detail="URL prodotto MEPA non valido")
    extra = await scrape_dettaglio_mepa(url)
    if not extra:
        raise HTTPException(status_code=404, detail="Prodotto non trovato su MEPA")
    extra["link_prodotto"] = url
    return extra
