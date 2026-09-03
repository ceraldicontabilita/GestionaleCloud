#!/usr/bin/env python3
"""
Scrapa TUTTE le pagine di categoria su dolciariaacquaviva.com
usando URL statici /categoria-prodotto/XXX/page/N/
"""
import asyncio
import re
import time
import unicodedata
import os

import requests
from bs4 import BeautifulSoup
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timezone

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "it-IT,it;q=0.9",
}
DELAY = 1.2

# Tutte le categorie + sottocategorie del sito
CATEGORIES = [
    ("prelievitati", "Prelievitati"),
    ("prelievitati/semplici", "Prelievitati > Tradizionali"),
    ("prelievitati/la-lune", "Prelievitati > La Lune"),
    ("prelievitati/fagotti", "Prelievitati > Fagotti"),
    ("prelievitati/multicereali", "Prelievitati > Multicereali"),
    ("prelievitati/vegani", "Prelievitati > Vegani"),
    ("sfoglie", "Sfoglie"),
    ("semilavorati", "Semilavorati"),
    ("da-lievitare", "Da lievitare"),
    ("gia-cotti", "Già cotti"),
    ("gia-cotti/soffici", "Già cotti > Soffici"),
    ("gia-cotti/donuts", "Già cotti > Donuts"),
    ("gia-cotti/roundy", "Già cotti > Roundy"),
    ("gia-cotti/muffin", "Già cotti > Muffin"),
    ("gia-cotti/i-milanesi", "Già cotti > I Milanesi"),
    ("senza-glutine", "Senza Glutine"),
    ("tipici", "Tipici"),
    ("tipici/specialita-napoletane", "Tipici > Specialità Napoletane"),
    ("tipici/specialita-siciliane", "Tipici > Specialità Siciliane"),
    ("tipici/calise", "Tipici > Calise"),
    ("biscotti", "Biscotti"),
    ("dessert", "Dessert"),
    ("dessert/torte-pretagliate", "Dessert > Torte Pretagliate"),
    ("dessert/torte-intere", "Dessert > Torte Intere"),
    ("dessert/al-trancio", "Dessert > Al trancio"),
    ("dessert/al-cucchiaio", "Dessert > Al cucchiaio"),
    ("monoporzioni", "Monoporzioni"),
    ("snack", "Snack"),
    ("snack/da-scaldare", "Snack > Da scaldare"),
    ("snack/da-friggere", "Snack > Da friggere"),
    ("snack/da-cuocere", "Snack > Da cuocere"),
    ("snack/gia-fritti", "Snack > Già fritti"),
    ("snack/cornetti-salati", "Snack > Cornetti Salati"),
    ("pani-e-focacce", "Pani e focacce"),
    ("pani-e-focacce/focacce", "Pani e focacce > Focacce"),
    ("pani-e-focacce/pani-speciali", "Pani e focacce > Pani Speciali"),
    ("pani-e-focacce/baguette", "Pani e focacce > Baguette"),
    ("pani-e-focacce/morbidi", "Pani e focacce > Morbidi"),
    ("novita-2", "Novità"),
]


def normalize(s: str) -> str:
    s = s.lower().strip()
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\b\d+[\.,]?\d*\s*(g|kg|gr|ml|cl|lt|cm)\b", "", s)
    s = re.sub(r"\b(sg|bg|surgelato|surgelata)\b", "", s)
    return s.strip()


def word_overlap(a: str, b: str) -> float:
    wa = set(w for w in normalize(a).split() if len(w) > 2)
    wb = set(w for w in normalize(b).split() if len(w) > 2)
    if not wa or not wb:
        return 0.0
    common = wa & wb
    score = len(common) / max(len(wa | wb), 1)
    if wa.issubset(wb) or wb.issubset(wa):
        score = max(score, 0.8)
    return score


def scrape_category_page(cat_slug: str, cat_label: str, page: int) -> list[dict]:
    if page == 1:
        url = f"https://dolciariaacquaviva.com/categoria-prodotto/{cat_slug}/"
    else:
        url = f"https://dolciariaacquaviva.com/categoria-prodotto/{cat_slug}/page/{page}/"

    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code == 404:
            return None  # Nessun'altra pagina
        if r.status_code != 200:
            return []
    except Exception as e:
        print(f"    Errore {url}: {e}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    products = []

    # Selettore WooCommerce standard
    selectors = [
        ".jet-woo-products__item",  # JetWoo
        "li.product",               # WooCommerce default
        ".products .product",
    ]

    items = []
    for sel in selectors:
        items = soup.select(sel)
        if items:
            break

    for item in items:
        # Nome
        title_el = item.select_one(".jet-woo-product-title a, .woocommerce-loop-product__title, h2 a, h3 a")
        if not title_el:
            continue
        nome = title_el.get_text(strip=True)

        # Immagine — priorità: src senza resize, poi data-src
        img_el = item.select_one("img")
        if not img_el:
            continue
        img_url = (img_el.get("src") or img_el.get("data-src") or "").strip()
        # Rimuovi ridimensionamenti tipo -300x300
        img_url_full = re.sub(r"-\d+x\d+(\.[a-zA-Z]+)$", r"\1", img_url)
        if not img_url_full or "placeholder" in img_url_full.lower():
            continue

        products.append({
            "nome": nome,
            "immagine_url": img_url_full,
            "categoria": cat_label,
        })

    return products


def scrape_all() -> list[dict]:
    all_products = []
    seen_names = set()

    for cat_slug, cat_label in CATEGORIES:
        page = 1
        cat_count = 0
        while True:
            products = scrape_category_page(cat_slug, cat_label, page)
            if products is None or (page > 1 and not products):
                break
            for p in products:
                key = normalize(p["nome"])
                if key not in seen_names:
                    seen_names.add(key)
                    all_products.append(p)
                    cat_count += 1
            if len(products) < 8:  # Meno di 8 = ultima pagina
                break
            page += 1
            time.sleep(DELAY)

        if cat_count > 0:
            print(f"  {cat_label}: {cat_count} prodotti (fino a pag. {page})")
        time.sleep(DELAY)

    return all_products


async def update_images(scraped: list[dict]):
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    db = client[os.environ.get("DB_NAME", "Gestionale")]

    db_products = await db.prodotti_vendita.find(
        {"fonte": "acquaviva"},
        {"_id": 0, "id": 1, "nome": 1}
    ).to_list(1000)

    print(f"\nProdotti DB: {len(db_products)}, Scraped: {len(scraped)}")

    aggiornati = 0
    non_trovati = []

    for db_prod in db_products:
        db_nome = db_prod["nome"]
        best_match = None
        best_score = 0.0

        for scraped_prod in scraped:
            score = word_overlap(db_nome, scraped_prod["nome"])
            if score > best_score:
                best_score = score
                best_match = scraped_prod

        threshold = 0.45
        if best_match and best_score >= threshold:
            update = {
                "immagine_url": best_match["immagine_url"],
                "categoria": best_match["categoria"],
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            await db.prodotti_vendita.update_one(
                {"id": db_prod["id"]},
                {"$set": update}
            )
            aggiornati += 1
        else:
            non_trovati.append(f"{db_nome} (best: {best_match['nome'] if best_match else '?'}, {best_score:.2f})")

    print(f"\n=== RISULTATI ===")
    print(f"Immagini aggiornate: {aggiornati}/{len(db_products)}")
    print(f"Non trovati: {len(non_trovati)}")
    for n in non_trovati[:20]:
        print(f"  - {n}")

    with open("/tmp/non_trovati_images.txt", "w") as f:
        f.write("\n".join(non_trovati))


if __name__ == "__main__":
    print("Scraping dolciariaacquaviva.com per categoria...")
    scraped = scrape_all()
    print(f"\nTotale prodotti unici scraped: {len(scraped)}")

    # Salva su file per debug
    with open("/tmp/acquaviva_scraped.txt", "w") as f:
        for p in scraped:
            f.write(f"{p['nome']} | {p['categoria']} | {p['immagine_url']}\n")
    print("Dati salvati in /tmp/acquaviva_scraped.txt")

    asyncio.run(update_images(scraped))
