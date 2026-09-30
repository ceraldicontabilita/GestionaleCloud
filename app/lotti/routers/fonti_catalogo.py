"""
fonti_catalogo.py — Cataloghi fornitori "incolla l'indirizzo" (richiesta Enzo
03/07/2026: "in admin... crea una pagina dove io inserendo il link tu capisci
che devi fare come stai facendo per Acquaviva/Saima, così posso aggiungere i
cataloghi dei miei fornitori ogni volta che inserisco l'indirizzo").

A differenza di saima.py/mepa.py (scraper scritti a mano guardando l'HTML
reale di UN sito specifico), questo è un connettore GENERICO best-effort:
1. cerca la sitemap del sito (sitemap.xml / sitemap_index.xml / varianti),
2. individua le URL che sembrano pagine-prodotto,
3. per ognuna legge i dati strutturati Schema.org (JSON-LD "Product", quasi
   tutti gli e-commerce moderni — WooCommerce/Shopify/Magento — li generano
   automaticamente per la SEO) o, in mancanza, i tag Open Graph.
Se il sito non espone nulla di tutto ciò, il risultato è onestamente vuoto
(nessun dato inventato) e lo stato della fonte passa a "errore" con il
motivo, non un catalogo fasullo.

I prodotti trovati finiscono nella STESSA collezione di catalogo_forno.py
(catalogo_forno_prodotti, chiave fornitore+codice_articolo) — nessun sistema
parallelo — arricchita qui con i campi opzionali immagine_url/prezzo/
descrizione/link_prodotto che il catalogo forno (import manuale da PDF) non
valorizza.
"""
import asyncio
import hashlib
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from fastapi import APIRouter, BackgroundTasks, Body, HTTPException, Depends
from pydantic import BaseModel

from app.lotti.db import database as db
from app.lotti.auth import require_admin
from app.lotti.servizi.fetch_sicuro import Risposta, UrlNonAmmesso, controlla_forma, scarica

logger = logging.getLogger("uvicorn.error")
router = APIRouter(prefix="/fonti-catalogo", tags=["fonti_catalogo"])

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "it-IT,it;q=0.9",
}
MAX_PRODOTTI = 300  # tetto di sicurezza: non far girare uno scraping infinito
SITEMAP_CANDIDATI = ["/sitemap.xml", "/sitemap_index.xml", "/product-sitemap.xml", "/sitemap-products.xml"]
PAROLE_PRODOTTO = ("prodotto", "prodotti", "product", "products", "shop", "negozio", "catalogo", "store")


def _slugify(nome: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "", nome.lower())
    return s or "fonte"


class NuovaFonte(BaseModel):
    nome: str
    url: str
    fornitore_key: Optional[str] = None


@router.get("")
async def lista_fonti():
    fonti = await db.fonti_catalogo_esterne.find({}, {"_id": 0}).sort("nome", 1).to_list(200)
    return fonti


@router.post("")
async def crea_fonte(payload: NuovaFonte = Body(...), _admin=Depends(require_admin)):
    nome = payload.nome.strip()
    url = payload.url.strip()
    if not nome or not url:
        raise HTTPException(400, "Nome e indirizzo sono obbligatori")
    if not url.startswith("http"):
        url = "https://" + url
    try:
        controlla_forma(url)
    except UrlNonAmmesso as exc:
        raise HTTPException(400, f"Indirizzo non ammesso: {exc}") from exc
    fornitore_key = _slugify(payload.fornitore_key or nome)
    esiste = await db.fonti_catalogo_esterne.find_one({"fornitore_key": fornitore_key})
    if esiste:
        raise HTTPException(409, f"Esiste già una fonte con chiave '{fornitore_key}'")
    doc = {
        "id": str(uuid.uuid4()),
        "nome": nome,
        "url": url,
        "fornitore_key": fornitore_key,
        "stato": "nuova",
        "ultima_sincronizzazione": None,
        "prodotti_trovati": 0,
        "ultimo_errore": None,
        "creato_il": datetime.now(timezone.utc).isoformat(),
    }
    await db.fonti_catalogo_esterne.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.delete("/{fonte_id}")
async def elimina_fonte(fonte_id: str, elimina_prodotti: bool = False, _admin=Depends(require_admin)):
    fonte = await db.fonti_catalogo_esterne.find_one({"id": fonte_id})
    if not fonte:
        raise HTTPException(404, "Fonte non trovata")
    await db.fonti_catalogo_esterne.delete_one({"id": fonte_id})
    if elimina_prodotti:
        await db.catalogo_forno_prodotti.delete_many({"fornitore": fonte["fornitore_key"]})
    return {"ok": True}


def _domini_fonte(base_url: str) -> list:
    """Una fonte si legge solo sul proprio sito (e sottodomini): una sitemap che
    rimanda altrove, o alla rete interna, non viene seguita."""
    host = (urlparse(base_url).hostname or "").lower()
    return [host[4:] if host.startswith("www.") else host]


async def _get(client: httpx.AsyncClient, url: str, domini: list) -> Optional[Risposta]:
    try:
        return await scarica(url, domini=domini, headers=HEADERS, client=client)
    except UrlNonAmmesso as exc:
        logger.info("[fonti_catalogo] %s scartato: %s", url[:120], exc)
        return None


async def _trova_url_prodotti(client: httpx.AsyncClient, base_url: str) -> list:
    """Cerca una sitemap; se assente, prova a leggere i link della homepage."""
    origine = f"{urlparse(base_url).scheme}://{urlparse(base_url).netloc}"
    domini = _domini_fonte(base_url)
    urls_prodotto = []

    for path in SITEMAP_CANDIDATI:
        try:
            r = await _get(client, origine + path, domini)
            if r is None or r.status_code != 200 or "<" not in r.text:
                continue
            soup = BeautifulSoup(r.text, "xml")
            locs = [loc.get_text(strip=True) for loc in soup.find_all("loc")]
            if not locs:
                continue
            # sitemap indice -> ricorri UN livello nelle sotto-sitemap che sembrano prodotti
            sotto_sitemap = [l for l in locs if l.endswith(".xml") and any(p in l.lower() for p in PAROLE_PRODOTTO)]
            if sotto_sitemap and not any(p in path for p in ("product",)):
                for sm in sotto_sitemap[:5]:
                    r2 = await _get(client, sm, domini)
                    if r2 is None:
                        continue
                    soup2 = BeautifulSoup(r2.text, "xml")
                    urls_prodotto += [loc.get_text(strip=True) for loc in soup2.find_all("loc")]
            else:
                urls_prodotto += [l for l in locs if any(p in l.lower() for p in PAROLE_PRODOTTO)]
            if urls_prodotto:
                break
        except Exception as exc:
            logger.info("[fonti_catalogo] sitemap %s illeggibile: %s %s", path, type(exc).__name__, exc)
            continue

    if not urls_prodotto:
        # Fallback: leggo i link della homepage, tengo quelli che sembrano schede prodotto
        r = await _get(client, base_url, domini)
        if r is not None:
            soup = BeautifulSoup(r.text, "html.parser")
            visti = set()
            for a in soup.find_all("a", href=True):
                href = urljoin(base_url, a["href"])
                if href in visti or not href.startswith(origine):
                    continue
                if any(p in href.lower() for p in PAROLE_PRODOTTO):
                    visti.add(href)
                    urls_prodotto.append(href)

    # dedup preservando l'ordine, tetto di sicurezza
    visti = set()
    out = []
    for u in urls_prodotto:
        if u not in visti:
            visti.add(u)
            out.append(u)
    return out[:MAX_PRODOTTI]


def _estrai_prodotto_da_html(html: str, url: str) -> Optional[dict]:
    """Prova JSON-LD Schema.org Product, poi Open Graph. None se non trova nulla di utile."""
    soup = BeautifulSoup(html, "html.parser")

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except Exception:
            continue
        candidati = data if isinstance(data, list) else [data]
        for c in candidati:
            if not isinstance(c, dict):
                continue
            tipo = c.get("@type", "")
            tipo = tipo if isinstance(tipo, str) else " ".join(tipo)
            if "Product" not in tipo:
                continue
            nome = c.get("name")
            if not nome:
                continue
            immagine = c.get("image")
            if isinstance(immagine, list):
                immagine = immagine[0] if immagine else None
            if isinstance(immagine, dict):
                immagine = immagine.get("url")
            offerte = c.get("offers")
            prezzo = None
            if isinstance(offerte, list):
                offerte = offerte[0] if offerte else None
            if isinstance(offerte, dict):
                prezzo = offerte.get("price")
            codice = c.get("sku") or c.get("mpn") or hashlib.md5(url.encode()).hexdigest()[:10]
            return {
                "nome": nome.strip(),
                "descrizione": (c.get("description") or "").strip()[:500],
                "immagine_url": immagine or "",
                "prezzo": float(prezzo) if prezzo not in (None, "") else 0.0,
                "codice_articolo": str(codice),
                "categoria": (c.get("category") or "") if isinstance(c.get("category"), str) else "",
            }

    # Fallback Open Graph
    def og(prop):
        tag = soup.find("meta", property=f"og:{prop}")
        return tag.get("content", "").strip() if tag else ""

    nome = og("title")
    if nome:
        return {
            "nome": nome,
            "descrizione": og("description")[:500],
            "immagine_url": og("image"),
            "prezzo": 0.0,
            "codice_articolo": hashlib.md5(url.encode()).hexdigest()[:10],
            "categoria": "",
        }
    return None


async def _sincronizza_fonte(fonte: dict):
    fonte_id = fonte["id"]
    fornitore_key = fonte["fornitore_key"]
    trovati = 0
    errore = None
    try:
        domini = _domini_fonte(fonte["url"])
        async with httpx.AsyncClient(follow_redirects=False) as client:
            urls = await _trova_url_prodotti(client, fonte["url"])
            if not urls:
                errore = "Nessuna pagina prodotto trovata (sitemap assente e homepage senza link riconoscibili)"
            for u in urls:
                try:
                    r = await _get(client, u, domini)
                    if r is None or r.status_code != 200:
                        continue
                    prodotto = _estrai_prodotto_da_html(r.text, u)
                    if not prodotto:
                        continue
                    prodotto["nome_completo"] = prodotto["nome"]
                    prodotto["fornitore"] = fornitore_key
                    prodotto["link_prodotto"] = u
                    prodotto["fonte_scraping"] = "generico_ldjson_og"
                    prodotto["data_aggiornamento"] = datetime.now(timezone.utc).isoformat()
                    await db.catalogo_forno_prodotti.update_one(
                        {"fornitore": fornitore_key, "codice_articolo": prodotto["codice_articolo"]},
                        {"$set": prodotto},
                        upsert=True,
                    )
                    trovati += 1
                except Exception as e:
                    logger.debug("[fonti_catalogo] errore prodotto %s: %s", u, e)
                await asyncio.sleep(0.2)
            if trovati == 0 and not errore:
                errore = "Pagine trovate ma nessuna con dati Schema.org/Open Graph riconoscibili"
    except Exception as e:
        errore = f"{type(e).__name__}: {e}"

    await db.fonti_catalogo_esterne.update_one(
        {"id": fonte_id},
        {"$set": {
            "stato": "attivo" if trovati > 0 else "errore",
            "ultima_sincronizzazione": datetime.now(timezone.utc).isoformat(),
            "prodotti_trovati": trovati,
            "ultimo_errore": errore,
        }},
    )
    logger.info("[fonti_catalogo] %s: %s prodotti (errore=%s)", fornitore_key, trovati, errore)


@router.post("/{fonte_id}/sincronizza")
async def sincronizza(fonte_id: str, background_tasks: BackgroundTasks, _admin=Depends(require_admin)):
    fonte = await db.fonti_catalogo_esterne.find_one({"id": fonte_id}, {"_id": 0})
    if not fonte:
        raise HTTPException(404, "Fonte non trovata")
    if fonte.get("tipo") == "listino":
        raise HTTPException(409, "Questo catalogo e' un listino: si aggiorna caricando il file nuovo, non dal sito")
    await db.fonti_catalogo_esterne.update_one({"id": fonte_id}, {"$set": {"stato": "in_corso"}})
    background_tasks.add_task(_sincronizza_fonte, fonte)
    return {"ok": True, "message": "Sincronizzazione avviata in background"}


# Il confronto dei prezzi al carrello non sta piu' qui: lo fa il motore unico
# `confronto-fornitori` (fatture XML + listini + lettura AI), vedi
# `GET /confronto-fornitori/migliore`.
