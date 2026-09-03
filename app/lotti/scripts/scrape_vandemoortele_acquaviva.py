#!/usr/bin/env python3
"""
SCRAPING VANDEMOORTELE - Dati tecnici prodotti Acquaviva
Estrae: ID articolo, Peso g/pz, Unità totali (pz/cartone) per tutti i prodotti Acquaviva
Aggiorna: prodotti_vendita e dizionario_prodotti nel MongoDB
"""

import asyncio
import os
import re
import time
import json
import urllib.request
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient

BASE_URL = "https://vandemoortele.com"

# Tutte le URL delle categorie Acquaviva da scrapare
CATEGORIE_ACQUAVIVA = [
    f"{BASE_URL}/it-it/products/cl1/pasticceria-17656/marca/acquaviva-39542",
    f"{BASE_URL}/it-it/products/cl1/viennoiserie-14975/marca/acquaviva-39542",
    f"{BASE_URL}/it-it/products/cl1/pane-2665/marca/acquaviva-39542",
    f"{BASE_URL}/it-it/products/cl1/focacce-17666/marca/acquaviva-39542",
    f"{BASE_URL}/it-it/products/cl1/pizze-17691/marca/acquaviva-39542",
    f"{BASE_URL}/it-it/products/cl1/snack-salati-17673/marca/acquaviva-39542",
    f"{BASE_URL}/it-it/products/cl1/sweet-treats-20406/marca/acquaviva-39542",
    f"{BASE_URL}/it-it/products/cl1/other-products-20401/marca/acquaviva-39542",
    f"{BASE_URL}/it-it/products/marca/acquaviva-39542",  # tutti
]


def fetch_page(url: str) -> str:
    """Scarica una pagina HTML con user-agent browser."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  [WARN] Fetch failed {url}: {e}")
        return ""


def parse_products_from_html(html: str) -> list:
    """
    Estrae prodotti dalla pagina lista Vandemoortele.
    Pattern cercati:
      ID articolo: \\n\\n57402
      Peso: \\n\\n100 g\\n
      Unità totali: \\n\\n75\\nunità
    """
    products = []

    # Pattern per blocchi prodotto
    # Ogni prodotto ha: ID, Peso, Unità, URL prodotto
    block_pattern = re.compile(
        r'ID dell\'articolo:\\?\s*\\?\n\s*\\?\n\s*([\d]+)'   # ID
        r'.*?'
        r'Peso:\\?\s*\\?\n\s*\\?\n\s*([\d.,]+)\s*g'          # Peso g
        r'.*?'
        r'Unità totali:\\?\s*\\?\n\s*\\?\n\s*([\d]+)',        # Unità pz
        re.DOTALL
    )

    # Pattern alternativo per markdown renderizzato
    block_pattern2 = re.compile(
        r'ID dell\'articolo:\\\s*\\\s*\\?\s*([\d]+)'
        r'.*?'
        r'Peso:\\\s*\\\s*\\?\s*([\d.,]+)\s*g'
        r'.*?'
        r'Unità totali:\\\s*\\\s*\\?\s*([\d]+)',
        re.DOTALL
    )

    # Pattern semplice per pagina text-scraped
    # Cerca blocchi: "ID dell'articolo:\n\n57402" poi "Peso:\n\n100 g" poi "Unità totali:\n\n75"
    id_pattern = re.compile(r"ID dell'articolo:\s*[\\\n]+\s*([\d]{5,6})")
    peso_pattern = re.compile(r"Peso:\s*[\\\n]+\s*([\d.,]+)\s*g")
    unita_pattern = re.compile(r"Unità totali:\s*[\\\n]+\s*([\d]+)")
    url_pattern = re.compile(r'href="(https://vandemoortele\.com/it-it/products/[^"]+)"')

    ids = id_pattern.findall(html)
    pesi = peso_pattern.findall(html)
    unita = unita_pattern.findall(html)
    urls = [u for u in url_pattern.findall(html) if "/products/" in u and "/cl1/" not in u and "/marca/" not in u]

    print(f"  Trovati: {len(ids)} ID, {len(pesi)} pesi, {len(unita)} unità")

    # Associa per posizione
    n = min(len(ids), len(pesi), len(unita))
    for i in range(n):
        peso_raw = pesi[i].replace(",", ".")
        try:
            peso_g = float(peso_raw)
            pz_cart = int(unita[i])
            codice = ids[i].strip()
            url = urls[i] if i < len(urls) else ""
            weight_cartone = round(peso_g * pz_cart / 1000, 3)  # kg

            products.append({
                "codice": codice,
                "peso_pezzo_g": peso_g,
                "pezzi_cartone": pz_cart,
                "peso_cartone_kg": weight_cartone,
                "url_scheda": url,
            })
        except (ValueError, IndexError):
            continue

    return products


async def update_db(all_products: list) -> dict:
    """Aggiorna prodotti_vendita e dizionario_prodotti con i dati Vandemoortele."""
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    db = client[os.environ.get("DB_NAME", "Gestionale")]
    now = datetime.now(timezone.utc).isoformat()

    stats = {"aggiornati_pv": 0, "aggiornati_diz": 0, "non_trovati": 0, "costo_calcolato": 0}

    # Costruisci mappa codice → dati vandemoortele
    vande_map = {p["codice"]: p for p in all_products}
    print(f"\nDati Vandemoortele pronti: {len(vande_map)} prodotti unici")

    # Carica tutti i prodotti acquaviva dal DB una volta sola
    db_prodotti = {}
    async for p in db.prodotti_vendita.find({"fonte": "acquaviva"}, {"_id": 0}):
        codice = str(p.get("codice_prodotto", "")).strip()
        if codice:
            db_prodotti[codice] = p

    print(f"Prodotti Acquaviva nel DB: {len(db_prodotti)}")

    for codice, vande in vande_map.items():
        db_prod = db_prodotti.get(codice)
        if not db_prod:
            stats["non_trovati"] += 1
            continue

        peso_g = vande["peso_pezzo_g"]
        pz_cart = vande["pezzi_cartone"]
        peso_cart_kg = vande["peso_cartone_kg"]

        update = {
            "peso_pezzo_g": peso_g,
            "pezzi_cartone": pz_cart,
            "peso_cartone_kg": peso_cart_kg,
            "fonte_dati": "vandemoortele.com",
            "updated_at": now,
        }

        # Calcola costo per pezzo se abbiamo il prezzo cartone
        prezzo_cart = float(db_prod.get("costo_produzione_cartone") or 0)
        if prezzo_cart > 0 and pz_cart > 0:
            costo_pezzo = round(prezzo_cart / pz_cart, 4)
            update["costo_produzione"] = costo_pezzo
            stats["costo_calcolato"] += 1

        await db.prodotti_vendita.update_one(
            {"codice_prodotto": codice, "fonte": "acquaviva"},
            {"$set": update}
        )
        stats["aggiornati_pv"] += 1

        # Aggiorna anche dizionario_prodotti (se esiste record per questo codice)
        diz_update = {
            "peso_pezzo_g": peso_g,
            "pezzi_per_confezione": pz_cart,
        }
        # Se peso confezione nel diz è il pezzo (< 1 kg), correggilo al cartone
        diz_result = await db.dizionario_prodotti.update_many(
            {"codice_prodotto": codice},
            {"$set": diz_update}
        )
        if diz_result.modified_count > 0:
            stats["aggiornati_diz"] += diz_result.modified_count

    # Ricalcola prezzo_kg nel dizionario per i record corretti
    print("Ricalcolo prezzo_kg nel dizionario dopo aggiornamento peso...")
    async for diz in db.dizionario_prodotti.find({"peso_pezzo_g": {"$gt": 0}, "pezzi_per_confezione": {"$gt": 0}}):
        peso_g = float(diz.get("peso_pezzo_g", 0))
        pz_cart = int(diz.get("pezzi_per_confezione", 0))
        peso_conf = float(diz.get("peso_confezione", 0))
        prezzo_conf = float(diz.get("prezzo_confezione", 0))

        if prezzo_conf > 0 and peso_g > 0 and pz_cart > 0:
            # Verifica se peso_confezione è sbagliato (= peso pezzo invece di cartone)
            peso_corretto_kg = round(peso_g * pz_cart / 1000, 3)
            if abs(peso_conf - peso_g / 1000) < 0.001:  # era il peso del singolo pezzo!
                new_prezzo_kg = round(prezzo_conf / peso_corretto_kg, 4)
                new_costo_pezzo = round(prezzo_conf / pz_cart, 4)
                await db.dizionario_prodotti.update_one(
                    {"_id": diz["_id"]},
                    {"$set": {
                        "peso_confezione": peso_corretto_kg,
                        "prezzo_kg": new_prezzo_kg,
                        "costo_per_pezzo": new_costo_pezzo,
                    }}
                )
                stats["aggiornati_diz"] += 1

    return stats


async def main():
    print("=== SCRAPING VANDEMOORTELE - Dati Acquaviva ===\n")

    all_products = []
    seen_codes = set()

    for url in CATEGORIE_ACQUAVIVA:
        print(f"\nScraping: {url.split('/marca/')[0].split('/cl1/')[-1] if '/cl1/' in url else 'ALL'}")
        html = fetch_page(url)
        if not html:
            continue

        products = parse_products_from_html(html)
        new_count = 0
        for p in products:
            if p["codice"] not in seen_codes:
                seen_codes.add(p["codice"])
                all_products.append(p)
                new_count += 1

        print(f"  Nuovi prodotti: {new_count} (totale: {len(all_products)})")
        time.sleep(0.5)  # rispetta il server

    print(f"\n=== Totale prodotti raccolti: {len(all_products)} ===")

    # Salva i dati raccolti in un file di log
    log_path = "/tmp/vandemoortele_scraped.json"
    with open(log_path, "w") as f:
        json.dump(all_products, f, indent=2, ensure_ascii=False)
    print(f"Dati salvati in: {log_path}")

    print("\nAggiornamento database...")
    stats = await update_db(all_products)

    print(f"""
=== RISULTATI ===
Prodotti aggiornati in prodotti_vendita: {stats['aggiornati_pv']}
Record aggiornati nel dizionario:        {stats['aggiornati_diz']}
Costi per pezzo ricalcolati:             {stats['costo_calcolato']}
Prodotti Vandemoortele non in DB:        {stats['non_trovati']}
""")


if __name__ == "__main__":
    asyncio.run(main())
