"""
Router per catalogo SAIMA S.p.a. — Materie prime, semilavorati, prodotti finiti.
Scarica e importa il catalogo prodotti da saimaspa.com nel dizionario ingredienti.
"""
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from app.routers.tracciabilita.server import db
from datetime import datetime, timezone
import uuid, re, asyncio, httpx
from bs4 import BeautifulSoup

router = APIRouter(prefix="/saima", tags=["saima"])

# ── categorie SAIMA con immagini locali scaricate ───────────────────────────────────
CATEGORIE_SAIMA = [
    {"nome": "AMIDI", "url": "https://www.saimaspa.com/app/site/categoriasito2.php?categoria=amidi&opt=1", "img": "/saima/amidi.png"},
    {"nome": "AROMI E SPEZIE", "url": "https://www.saimaspa.com/app/site/categoriasito2.php?categoria=AROMI%20E%20SPEZIE&opt=1", "img": "/saima/aromi-e-spezie.png"},
    {"nome": "BISCOTTERIA", "url": "https://www.saimaspa.com/app/site/categoriasito2.php?categoria=biscotteria&opt=1", "img": "/saima/biscotteria.png"},
    {"nome": "CANDITI", "url": "https://www.saimaspa.com/app/site/categoriasito2.php?categoria=CANDITI&opt=1", "img": "/saima/canditi.png"},
    {"nome": "CIOCCOLATO E SURROGATO", "url": "https://www.saimaspa.com/app/site/categoriasito2.php?categoria=CIOCCOLATO%20E%20SURROGATO&opt=1", "img": "/saima/cioccolato.png"},
    {"nome": "COADIUVANTI", "url": "https://www.saimaspa.com/app/site/categoriasito2.php?categoria=COADIUVANTI&opt=1", "img": "/saima/coadiuvanti.png"},
    {"nome": "COLORI", "url": "https://www.saimaspa.com/app/site/categoriasito2.php?categoria=COLORI&opt=1", "img": "/saima/colori.png"},
    {"nome": "CONFETTURE PASSATE E GELATINE", "url": "https://www.saimaspa.com/app/site/categoriasito2.php?categoria=CONFETTURE%20PASSATE%20E%20GELATINE&opt=1", "img": "/saima/confetture.png"},
    {"nome": "CREME VEGETALI", "url": "https://www.saimaspa.com/app/site/categoriasito2.php?categoria=CREME%20VEGETALI&opt=1", "img": "/saima/panna.png"},
    {"nome": "CROCCOLOSI", "url": "https://www.saimaspa.com/app/site/categoriasito2.php?categoria=CROCCOLOSI&opt=1", "img": "/saima/biscotteria.png"},
    {"nome": "DECORAZIONI", "url": "https://www.saimaspa.com/app/site/categoriasito2.php?categoria=decorazioni&opt=1", "img": "/saima/decorazioni.png"},
    {"nome": "DESSERT", "url": "https://www.saimaspa.com/app/site/categoriasito2.php?categoria=DESSERT&opt=1", "img": "/saima/dessert.png"},
    {"nome": "FARINE", "url": "https://www.saimaspa.com/app/site/categoriasito2.php?categoria=farine&opt=1", "img": "/saima/farine.png"},
    {"nome": "FRUTTA SECCA E SCIROPPATA", "url": "https://www.saimaspa.com/app/site/categoriasito2.php?categoria=FRUTTA%20SECCA%20E%20SCIROPPATA&opt=1", "img": "/saima/frutta.png"},
    {"nome": "FRUTTA SURGELATA", "url": "https://www.saimaspa.com/app/site/categoriasito2.php?categoria=frutta%20surgelata&opt=1", "img": "/saima/frutta.png"},
    {"nome": "GELATERIA", "url": "https://www.saimaspa.com/app/site/categoriasito2.php?categoria=gelateria&opt=1", "img": "/saima/gelateria.png"},
    {"nome": "GLASSE", "url": "https://www.saimaspa.com/app/site/categoriasito2.php?categoria=GLASSE&opt=1", "img": "/saima/GLASSE.png"},
    {"nome": "GRASSI", "url": "https://www.saimaspa.com/app/site/categoriasito2.php?categoria=grassi&opt=1", "img": "/saima/burro.png"},
    {"nome": "LATTE E DERIVATI", "url": "https://www.saimaspa.com/app/site/categoriasito2.php?categoria=latte%20e%20derivati&opt=1", "img": "/saima/latte.png"},
    {"nome": "LIEVITI", "url": "https://www.saimaspa.com/app/site/categoriasito2.php?categoria=lieviti&opt=1", "img": "/saima/farine.png"},
    {"nome": "MIELE", "url": "https://www.saimaspa.com/app/site/categoriasito2.php?categoria=MIELE&opt=1", "img": "/saima/mix.png"},
    {"nome": "MIX E MIGLIORATORI", "url": "https://www.saimaspa.com/app/site/categoriasito2.php?categoria=mix%20e%20miglioratori&opt=1", "img": "/saima/mix.png"},
    {"nome": "OVOPRODOTTI", "url": "https://www.saimaspa.com/app/site/categoriasito2.php?categoria=ovoprodotti&opt=1", "img": "/saima/panna.png"},
    {"nome": "PANE SURGELATO", "url": "https://www.saimaspa.com/app/site/categoriasito2.php?categoria=pane%20surgelato&opt=1", "img": "/saima/pane.png"},
    {"nome": "PANNA", "url": "https://www.saimaspa.com/app/site/categoriasito2.php?categoria=panna&opt=1", "img": "/saima/panna.png"},
    {"nome": "PASTA DI MANDORLE", "url": "https://www.saimaspa.com/app/site/categoriasito2.php?categoria=pasta%20di%20mandorle&opt=1", "img": "/saima/mix.png"},
    {"nome": "PASTE DA DECORAZIONE", "url": "https://www.saimaspa.com/app/site/categoriasito2.php?categoria=paste%20da%20decorazione&opt=1", "img": "/saima/decorazioni.png"},
    {"nome": "PASTICCERIA PRONTA", "url": "https://www.saimaspa.com/app/site/categoriasito2.php?categoria=pasticceria%20pronta&opt=1", "img": "/saima/biscotteria.png"},
    {"nome": "PASTICCERIA SURGELATA", "url": "https://www.saimaspa.com/app/site/categoriasito2.php?categoria=pasticceria%20surgelata&opt=1", "img": "/saima/SEMIFREDDI.png"},
    {"nome": "ROSTICCERIA PRONTA", "url": "https://www.saimaspa.com/app/site/categoriasito2.php?categoria=rosticceria%20pronta&opt=1", "img": "/saima/pane.png"},
    {"nome": "ROSTICCERIA SURGELATA", "url": "https://www.saimaspa.com/app/site/categoriasito2.php?categoria=rosticceria%20surgelata&opt=1", "img": "/saima/pane.png"},
    {"nome": "SEMIFREDDI", "url": "https://www.saimaspa.com/app/site/categoriasito2.php?categoria=SEMIFREDDI&opt=1", "img": "/saima/SEMIFREDDI.png"},
    {"nome": "VERDURA SURGELATA", "url": "https://www.saimaspa.com/app/site/categoriasito2.php?categoria=verdura%20surgelata&opt=1", "img": "/saima/frutta.png"},
    {"nome": "ZUCCHERO", "url": "https://www.saimaspa.com/app/site/categoriasito2.php?categoria=zucchero&opt=1", "img": "/saima/mix.png"},
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "it-IT,it;q=0.9",
}

SAIMA_BASE = "https://www.saimaspa.com"


def build_saima_image_url(codice: str) -> str:
    """Costruisce l'URL dell'immagine prodotto SAIMA dal codice."""
    if not codice:
        return ""
    return f"{SAIMA_BASE}/app/public/prodotti/big/{codice.lower()}.jpg"


async def scrape_categoria_saima(url: str, categoria: str, img_categoria: str) -> list:
    """Scarica i prodotti di una categoria SAIMA leggendo i link ai prodotti."""
    prodotti = []
    visti = set()  # evita duplicati
    try:
        async with httpx.AsyncClient(timeout=25, follow_redirects=True) as client:
            r = await client.get(url, headers=HEADERS)
            if r.status_code != 200:
                return prodotti

            soup = BeautifulSoup(r.text, "html.parser")

            # Ogni prodotto ha DUE link con stesso href: uno vuoto (thumbnail) e uno con il nome
            # Filtriamo i link con testo non vuoto che puntano a prodottosito.php
            link_tags = [
                a for a in soup.find_all("a", href=True)
                if "prodottosito.php" in a.get("href", "") and a.get_text(strip=True)
            ]

            for a in link_tags:
                href = a["href"].strip()
                # Estrai codice dall'URL: ?cat=CODICE NUMERO
                cat_param = href.split("cat=")[-1].strip() if "cat=" in href else ""
                if not cat_param or cat_param in visti:
                    continue
                visti.add(cat_param)

                # Nome dal testo del link (può contenere unità es. "Nome prodotto'1 CF")
                nome_raw = a.get_text(strip=True)
                # Separa nome da unità confezione (separatore apice singolo)
                unita = ""
                if "'" in nome_raw:
                    parti = nome_raw.split("'")
                    nome_raw = parti[0].strip()
                    unita = parti[1].strip() if len(parti) > 1 else ""

                # Pulizia nome
                nome_raw = nome_raw.strip(" '\"")
                if len(nome_raw) < 3:
                    continue

                # URL immagine prodotto costruito dal codice
                immagine_url = build_saima_image_url(cat_param)

                # URL pagina prodotto
                link_prodotto = href if href.startswith("http") else f"{SAIMA_BASE}/app/site/{href}"

                prodotti.append({
                    "nome": nome_raw,
                    "codice_articolo": cat_param,
                    "categoria": categoria,
                    "immagine_url": immagine_url,
                    "immagine_categoria": img_categoria,
                    "descrizione": f"Confezione: {unita}" if unita else "",
                    "unita_confezione": unita,
                    "link_prodotto": link_prodotto,
                    "fonte": "saima",
                    "fornitore": "SAIMA S.p.a.",
                })

    except Exception as e:
        print(f"[SAIMA] Errore scraping {categoria}: {e}")

    return prodotti


async def scrape_dettaglio_saima_prodotto(codice: str) -> dict:
    """Scarica i dettagli di un singolo prodotto SAIMA dal suo codice."""
    import urllib.parse
    extra = {}
    try:
        url = f"{SAIMA_BASE}/app/site/prodottosito.php?cat={urllib.parse.quote(codice)}"
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            r = await client.get(url, headers=HEADERS)
            if r.status_code != 200:
                return extra
            soup = BeautifulSoup(r.text, "html.parser")
            text_lines = [l.strip() for l in soup.get_text(separator="\n").split("\n") if l.strip()]

            # Struttura pagina prodotto:
            # COD.
            # CODICE
            # CONFEZIONE
            # valore
            # DESCRIZONE
            # testo
            for i, line in enumerate(text_lines):
                if line == "COD." and i + 1 < len(text_lines):
                    extra["codice_verificato"] = text_lines[i + 1]
                if line == "CONFEZIONE" and i + 1 < len(text_lines):
                    extra["unita_confezione"] = text_lines[i + 1]
                if line in ("DESCRIZONE", "DESCRIZIONE") and i + 1 < len(text_lines):
                    extra["descrizione_lunga"] = text_lines[i + 1]

            # Immagine prodotto dalla tabella HTML
            for img in soup.find_all("img"):
                src = img.get("src", "")
                if "prodotti/big" in src:
                    if src.startswith("../"):
                        src = f"{SAIMA_BASE}/app/" + src[3:]
                    elif src.startswith("/"):
                        src = SAIMA_BASE + src
                    extra["immagine_prodotto"] = src
                    break

    except Exception as e:
        print(f"[SAIMA] Errore dettaglio {codice}: {e}")
    return extra


@router.get("/categorie")
async def get_categorie_saima():
    """Restituisce la lista delle categorie SAIMA con immagini."""
    return CATEGORIE_SAIMA


@router.get("/prodotti")
async def get_prodotti_saima(
    categoria: str = Query("", description="Filtra per categoria"),
    q: str = Query("", description="Ricerca per nome"),
    limit: int = Query(100)
):
    """Restituisce i prodotti SAIMA dal DB locale."""
    query = {"fonte": "saima"}
    if categoria:
        query["categoria"] = {"$regex": categoria, "$options": "i"}
    if q:
        query["$or"] = [
            {"nome": {"$regex": q, "$options": "i"}},
            {"codice_articolo": {"$regex": q, "$options": "i"}},
            {"descrizione": {"$regex": q, "$options": "i"}},
        ]

    prodotti = await db.dizionario_ingredienti.find(query, {"_id": 0}).limit(limit).to_list(limit)
    return prodotti


@router.get("/dettaglio-prodotto")
async def dettaglio_prodotto_saima(codice: str = Query(..., description="Codice prodotto SAIMA")):
    """
    Scarica on-demand i dettagli di un singolo prodotto SAIMA dal sito.
    Include immagine specifica del prodotto, descrizione, confezione.
    """
    extra = await scrape_dettaglio_saima_prodotto(codice)
    if not extra:
        raise HTTPException(status_code=404, detail="Prodotto non trovato sul sito SAIMA")
    extra["codice"] = codice
    extra["link_prodotto"] = f"{SAIMA_BASE}/app/site/prodottosito.php?cat={codice}"
    return extra


@router.post("/scraping/avvia")
async def avvia_scraping_saima(background_tasks: BackgroundTasks, categorie: list = None):
    """Avvia lo scraping del catalogo SAIMA in background."""

    async def esegui_scraping():
        cat_list = categorie or CATEGORIE_SAIMA
        totale_importati = 0
        totale_aggiornati = 0

        for cat in cat_list:
            prodotti = await scrape_categoria_saima(cat["url"], cat["nome"], cat["img"])
            for p in prodotti:
                nome_norm = p["nome"].lower().strip()
                p["nome_normalizzato"] = nome_norm
                p["nome_display"] = p["nome"].title()
                p["attivo"] = True
                p["is_saima"] = True
                p["prezzo_kg"] = 0.0
                p["costo_per_pezzo"] = 0.0
                p["data_aggiornamento"] = datetime.now(timezone.utc).isoformat()

                filtro = {"fonte": "saima"}
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

            await asyncio.sleep(0.3)

        await db.log_scraping.insert_one({
            "fonte": "saima",
            "data": datetime.now(timezone.utc).isoformat(),
            "importati": totale_importati,
            "aggiornati": totale_aggiornati,
        })
        print(f"[SAIMA] Scraping completato: {totale_importati} importati, {totale_aggiornati} aggiornati")

    background_tasks.add_task(esegui_scraping)
    return {"message": "Scraping SAIMA avviato in background", "categorie": len(CATEGORIE_SAIMA)}


@router.get("/scraping/stato")
async def stato_scraping_saima():
    """Stato dell'ultimo scraping SAIMA."""
    ultimo = await db.log_scraping.find_one({"fonte": "saima"}, {"_id": 0}, sort=[("data", -1)])
    count = await db.dizionario_ingredienti.count_documents({"fonte": "saima"})
    return {"prodotti_nel_db": count, "ultimo_scraping": ultimo}
