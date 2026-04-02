"""
Router per catalogo MEPA Alimentari — Prodotti per pasticcerie, gelaterie, panificazione, HO.RE.CA.
Scarica e importa il catalogo dal sito mepaalimentari.com (WooCommerce) nel dizionario ingredienti.
"""
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from app.routers.tracciabilita.server import db
from datetime import datetime, timezone
import uuid, re, asyncio, httpx, os
from bs4 import BeautifulSoup
from db import database as db

router = APIRouter(prefix="/mepa", tags=["mepa"])

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "it-IT,it;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
}

# Categorie principali MEPA con URL e immagini
CATEGORIE_MEPA = [
    {"nome": "AMIDI & MIX PER CREMA PASTICCERA", "url": "https://www.mepaalimentari.com/amidi-mix-per-crema-pasticcera/", "img": "https://berqwp-cdn.sfo3.cdn.digitaloceanspaces.com/cache/www.mepaalimentari.com/wp-content/uploads/2025/06/100-595x595.webp"},
    {"nome": "AROMI, ESSENZE & SPEZIE", "url": "https://www.mepaalimentari.com/aromi-essenze-spezie/", "img": "https://berqwp-cdn.sfo3.cdn.digitaloceanspaces.com/cache/www.mepaalimentari.com/wp-content/uploads/2025/06/101-595x595.webp"},
    {"nome": "BISCOTTERIA", "url": "https://www.mepaalimentari.com/biscotteria/", "img": "https://berqwp-cdn.sfo3.cdn.digitaloceanspaces.com/cache/www.mepaalimentari.com/wp-content/uploads/2025/06/104-595x595.webp"},
    {"nome": "CIOCCOLATO & SURROGATO", "url": "https://www.mepaalimentari.com/cioccolato-surrogato/", "img": "https://berqwp-cdn.sfo3.cdn.digitaloceanspaces.com/cache/www.mepaalimentari.com/wp-content/uploads/2025/06/106-595x595.webp"},
    {"nome": "CONFETTURE, PASSATE & GELATINE", "url": "https://www.mepaalimentari.com/confetture-passate-gelatine/", "img": "https://berqwp-cdn.sfo3.cdn.digitaloceanspaces.com/cache/www.mepaalimentari.com/wp-content/uploads/2025/06/109-595x595.webp"},
    {"nome": "CREME SPALMABILI", "url": "https://www.mepaalimentari.com/creme-spalmabili/", "img": "https://berqwp-cdn.sfo3.cdn.digitaloceanspaces.com/cache/www.mepaalimentari.com/wp-content/uploads/2025/06/110-595x595.webp"},
    {"nome": "DECORAZIONI", "url": "https://www.mepaalimentari.com/decorazioni/", "img": "https://berqwp-cdn.sfo3.cdn.digitaloceanspaces.com/cache/www.mepaalimentari.com/wp-content/uploads/2025/06/112-595x595.webp"},
    {"nome": "FARINE", "url": "https://www.mepaalimentari.com/farine/", "img": "https://berqwp-cdn.sfo3.cdn.digitaloceanspaces.com/cache/www.mepaalimentari.com/wp-content/uploads/2025/06/114-595x595.webp"},
    {"nome": "FRUTTA", "url": "https://www.mepaalimentari.com/frutta/", "img": "https://berqwp-cdn.sfo3.cdn.digitaloceanspaces.com/cache/www.mepaalimentari.com/wp-content/uploads/2025/06/115-595x595.webp"},
    {"nome": "GASTRONOMIA", "url": "https://www.mepaalimentari.com/gastronomia/", "img": "https://berqwp-cdn.sfo3.cdn.digitaloceanspaces.com/cache/www.mepaalimentari.com/wp-content/uploads/2025/06/116-595x595.webp"},
    {"nome": "GELATERIA", "url": "https://www.mepaalimentari.com/gelateria/", "img": "https://berqwp-cdn.sfo3.cdn.digitaloceanspaces.com/cache/www.mepaalimentari.com/wp-content/uploads/2025/06/117-595x595.webp"},
    {"nome": "GLASSE", "url": "https://www.mepaalimentari.com/glasse/", "img": "https://berqwp-cdn.sfo3.cdn.digitaloceanspaces.com/cache/www.mepaalimentari.com/wp-content/uploads/2025/06/118-595x595.webp"},
    {"nome": "GRASSI", "url": "https://www.mepaalimentari.com/grassi/", "img": "https://berqwp-cdn.sfo3.cdn.digitaloceanspaces.com/cache/www.mepaalimentari.com/wp-content/uploads/2025/06/119-595x595.webp"},
    {"nome": "LATTE, DERIVATI & BEVANDE VEGETALI", "url": "https://www.mepaalimentari.com/latte-derivati-bevande-vegetali/", "img": "https://berqwp-cdn.sfo3.cdn.digitaloceanspaces.com/cache/www.mepaalimentari.com/wp-content/uploads/2025/06/120-595x595.webp"},
    {"nome": "LIEVITO", "url": "https://www.mepaalimentari.com/lievito/", "img": "https://berqwp-cdn.sfo3.cdn.digitaloceanspaces.com/cache/www.mepaalimentari.com/wp-content/uploads/2025/06/121-595x595.webp"},
    {"nome": "MIX E MIGLIORATORI", "url": "https://www.mepaalimentari.com/mix-e-miglioratori/", "img": "https://berqwp-cdn.sfo3.cdn.digitaloceanspaces.com/cache/www.mepaalimentari.com/wp-content/uploads/2025/06/122-595x595.webp"},
    {"nome": "OVOPRODOTTI", "url": "https://www.mepaalimentari.com/ovoprodotti/", "img": "https://berqwp-cdn.sfo3.cdn.digitaloceanspaces.com/cache/www.mepaalimentari.com/wp-content/uploads/2025/06/123-595x595.webp"},
    {"nome": "PANNA E CREME VEGETALI", "url": "https://www.mepaalimentari.com/panna-e-creme-vegetali/", "img": "https://berqwp-cdn.sfo3.cdn.digitaloceanspaces.com/cache/www.mepaalimentari.com/wp-content/uploads/2025/06/124-595x595.webp"},
    {"nome": "PASTA DI MANDORLE", "url": "https://www.mepaalimentari.com/pasta-di-mandorle/", "img": "https://berqwp-cdn.sfo3.cdn.digitaloceanspaces.com/cache/www.mepaalimentari.com/wp-content/uploads/2025/06/125-595x595.webp"},
    {"nome": "PASTICCERIA PRONTA", "url": "https://www.mepaalimentari.com/pasticceria-pronta/", "img": "https://berqwp-cdn.sfo3.cdn.digitaloceanspaces.com/cache/www.mepaalimentari.com/wp-content/uploads/2025/06/127-595x595.webp"},
    {"nome": "PASTICCERIA SURGELATA", "url": "https://www.mepaalimentari.com/pasticceria-surgelata/", "img": "https://berqwp-cdn.sfo3.cdn.digitaloceanspaces.com/cache/www.mepaalimentari.com/wp-content/uploads/2025/06/128-595x595.webp"},
    {"nome": "ROSTICCERIA SURGELATA", "url": "https://www.mepaalimentari.com/rosticceria-surgelata/", "img": "https://berqwp-cdn.sfo3.cdn.digitaloceanspaces.com/cache/www.mepaalimentari.com/wp-content/uploads/2025/06/130-595x595.webp"},
    {"nome": "SEMIFREDDI & DESSERT", "url": "https://www.mepaalimentari.com/semifreddi-dessert/", "img": "https://berqwp-cdn.sfo3.cdn.digitaloceanspaces.com/cache/www.mepaalimentari.com/wp-content/uploads/2025/06/131-595x595.webp"},
    {"nome": "ZUCCHERO & MIELE", "url": "https://www.mepaalimentari.com/zucchero-miele/", "img": "https://berqwp-cdn.sfo3.cdn.digitaloceanspaces.com/cache/www.mepaalimentari.com/wp-content/uploads/2025/06/133-595x595.webp"},
]


async def scrape_pagina_mepa(url: str, categoria: str, img_categoria: str, pagina: int = 1) -> tuple:
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
                soup.select(".product-item.grid") or
                soup.find_all("li", class_=re.compile(r"product")) or
                soup.find_all("article", class_=re.compile(r"product")) or
                soup.find_all("div", class_=re.compile(r"product-item|wc-product"))
            )
            
            for item in items:
                # Nome prodotto
                nome_tag = (
                    item.select_one("h2.product-title") or
                    item.select_one(".woocommerce-loop-product__title") or
                    item.find("h2") or item.find("h3") or item.find("h4")
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
                        img_tag.get("data-berqwpsrc") or  # CDN MEPA
                        img_tag.get("data-lazy-src") or
                        img_tag.get("data-src") or
                        img_tag.get("src") or ""
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
                            pass
                
                # Link prodotto — MEPA usa href diretto
                link_tag = item.select_one("a[href*='/prodotto/']") or item.find("a", href=True)
                link_url = link_tag["href"] if link_tag and link_tag.get("href") and link_tag["href"] != "javascript:void(0);" else ""
                
                # SKU/codice dal link o da span.sku
                codice = ""
                sku_tag = item.find(class_=re.compile(r"sku"))
                if sku_tag:
                    codice = sku_tag.get_text(strip=True)
                
                # Categoria da breadcrumb o tag
                cat_tag = item.find(class_=re.compile(r"cat-links|product-cat|category"))
                categoria_prodotto = cat_tag.get_text(strip=True) if cat_tag else categoria
                
                prodotti.append({
                    "nome": nome,
                    "codice_articolo": codice,
                    "categoria": categoria,
                    "categoria_prodotto": categoria_prodotto,
                    "immagine_url": img_url,
                    "prezzo_listino": prezzo,
                    "link_prodotto": link_url,
                    "fornitore": "MEPA Alimentari",
                    "fonte": "mepa",
                })
            
            # Controlla paginazione
            next_btn = soup.find("a", class_=re.compile(r"next|page-next")) or soup.find("a", string=re.compile(r"Successiv|Next|→"))
            ha_pagina_successiva = bool(next_btn) and len(prodotti) >= 10
            
    except Exception as e:
        print(f"[MEPA] Errore scraping {categoria} p{pagina}: {e}")
    
    return prodotti, ha_pagina_successiva


async def scrape_dettaglio_mepa(url_prodotto: str) -> dict:
    """Scarica dettagli aggiuntivi di un singolo prodotto MEPA (sku, descrizione)."""
    extra = {}
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            r = await client.get(url_prodotto, headers=HEADERS)
            if r.status_code != 200:
                return extra
            soup = BeautifulSoup(r.text, "html.parser")
            
            # SKU
            sku = soup.find(class_=re.compile(r"sku"))
            if sku:
                extra["codice_articolo"] = sku.get_text(strip=True)
            
            # Descrizione breve
            desc_tag = soup.find(class_=re.compile(r"woocommerce-product-details__short-description|product-short-description"))
            if desc_tag:
                extra["descrizione"] = desc_tag.get_text(strip=True)[:300]
            
            # Descrizione lunga
            desc_long = soup.find(id=re.compile(r"tab-description"))
            if desc_long:
                extra["descrizione_lunga"] = desc_long.get_text(strip=True)[:500]
                
            # Peso
            peso_row = soup.find(string=re.compile(r"Peso|Weight", re.I))
            if peso_row:
                peso_parent = peso_row.parent
                if peso_parent:
                    peso_next = peso_parent.find_next_sibling()
                    if peso_next:
                        extra["peso_lordo"] = peso_next.get_text(strip=True)
    except Exception:
        pass
    return extra


@router.get("/categorie")
async def get_categorie_mepa():
    """Lista categorie MEPA con immagini."""
    return CATEGORIE_MEPA


@router.get("/prodotti")
async def get_prodotti_mepa(
    categoria: str = Query("", description="Filtra per categoria"),
    q: str = Query("", description="Ricerca per nome"),
    limit: int = Query(100),
    skip: int = Query(0)
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
    
    prodotti = await db.dizionario_ingredienti.find(query, {"_id": 0}).skip(skip).limit(limit).to_list(limit)
    total = await db.dizionario_ingredienti.count_documents(query)
    return {"prodotti": prodotti, "total": total}


@router.post("/scraping/avvia")
async def avvia_scraping_mepa(background_tasks: BackgroundTasks, solo_categorie: list = None, con_dettagli: bool = False):
    """Avvia scraping catalogo MEPA in background."""
    async def esegui_scraping():
        cat_list = solo_categorie or CATEGORIE_MEPA
        totale_importati = 0
        totale_aggiornati = 0
        
        for cat in cat_list:
            pagina = 1
            ha_pagina = True
            
            while ha_pagina and pagina <= 10:  # max 10 pagine per categoria
                prodotti, ha_pagina = await scrape_pagina_mepa(cat["url"], cat["nome"], cat["img"], pagina)
                
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
                    
                    existing = await db.dizionario_ingredienti.find_one(filtro, {"_id": 0})
                    if existing:
                        await db.dizionario_ingredienti.update_one(filtro, {"$set": p})
                        totale_aggiornati += 1
                    else:
                        p["id"] = str(uuid.uuid4())
                        await db.dizionario_ingredienti.insert_one(p)
                        totale_importati += 1
                
                pagina += 1
                await asyncio.sleep(0.8)  # rispetta il server MEPA
        
        await db.log_scraping.insert_one({
            "fonte": "mepa",
            "data": datetime.now(timezone.utc).isoformat(),
            "importati": totale_importati,
            "aggiornati": totale_aggiornati,
        })
        print(f"[MEPA] Scraping completato: {totale_importati} importati, {totale_aggiornati} aggiornati")
    
    background_tasks.add_task(esegui_scraping)
    return {"message": "Scraping MEPA avviato in background", "categorie": len(CATEGORIE_MEPA)}


@router.get("/scraping/stato")
async def stato_scraping_mepa():
    """Stato ultimo scraping MEPA."""
    ultimo = await db.log_scraping.find_one({"fonte": "mepa"}, {"_id": 0}, sort=[("data", -1)])
    count = await db.dizionario_ingredienti.count_documents({"fonte": "mepa"})
    
    return {"prodotti_nel_db": count, "ultimo_scraping": ultimo}


@router.get("/dettaglio-prodotto")
async def dettaglio_prodotto_mepa(url: str = Query(..., description="URL pagina prodotto MEPA")):
    """
    Scarica on-demand i dettagli di un singolo prodotto MEPA.
    Include immagine grande, descrizione, sku, dati nutrizionali.
    """
    extra = await scrape_dettaglio_mepa(url)
    if not extra:
        raise HTTPException(status_code=404, detail="Prodotto non trovato su MEPA")
    extra["link_prodotto"] = url
    return extra
