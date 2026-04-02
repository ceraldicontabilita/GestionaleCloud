"""
Router per ricettari SAIMA S.p.a.
Fornisce i link ai PDF ricettari scaricabili dal sito SAIMA.
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from app.routers.tracciabilita.server import db
from pydantic import BaseModel
import httpx
from bs4 import BeautifulSoup
from db import database as db
from datetime import datetime, timezone

router = APIRouter(prefix="/saima/ricettari", tags=["saima"])

# Ricettari SAIMA — dati statici + link PDF
# Sezione Ricorrenze (6 ricettari)
RICETTARI_RICORRENZE = [
    {"id": "carnevale", "nome": "Carnevale", "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2023/01/Ricettario-Carnevale.pdf", "url_pagina": "https://www.saimaspa.com/default-item/carnevale-ricettario/", "sezione": "Ricorrenze"},
    {"id": "prima-colazione", "nome": "Prima Colazione", "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2022/10/Ricettario-prima-colazione.pdf", "url_pagina": "https://www.saimaspa.com/default-item/prima-colazione-ricettario/", "sezione": "Ricorrenze"},
    {"id": "dolci-easy", "nome": "Dolci Easy", "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2022/10/ricettario-dolci-easy.pdf", "url_pagina": "https://www.saimaspa.com/default-item/dolci-easy-ricettario/", "sezione": "Ricorrenze"},
    {"id": "snack-take-away", "nome": "Snack Take Away", "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2022/10/Ricettario-snack-take-away.pdf", "url_pagina": "https://www.saimaspa.com/default-item/snack-take-away-ricettario/", "sezione": "Ricorrenze"},
    {"id": "torroni", "nome": "Torroni", "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2022/09/Ricettario-Torroni.pdf", "url_pagina": "https://www.saimaspa.com/default-item/torroni-ricettario/", "sezione": "Ricorrenze"},
    {"id": "halloween", "nome": "Halloween", "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2023/09/Ricettario-halloween_2023.pdf", "url_pagina": "https://www.saimaspa.com/default-item/halloween-ricettario/", "sezione": "Ricorrenze"},
]

# Sezione Applicazioni Prodotto (19 ricettari)
RICETTARI_APPLICAZIONI = [
    {"id": "cometa-ricettario-natale", "nome": "Cometa Ricettario Natale", "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2023/11/Ricettario-Cometa.pdf", "url_pagina": "https://www.saimaspa.com/default-item/cometa-ricettario-natale/", "sezione": "Applicazioni Prodotto"},
    {"id": "ricettario-jolly-zelandia", "nome": "Ricettario Jolly Zelandia", "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2023/05/Ricettario-jolly-Zelandia.pdf", "url_pagina": "https://www.saimaspa.com/default-item/ricettario-jolly-zelandia/", "sezione": "Applicazioni Prodotto"},
    {"id": "ricettario-bs-komplet", "nome": "Ricettario b+s Komplet", "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2023/03/Ricettario-bs.pdf", "url_pagina": "https://www.saimaspa.com/default-item/ricettario-bs-komplet/", "sezione": "Applicazioni Prodotto"},
    {"id": "waldkorn-ricettario", "nome": "Waldkorn", "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2022/10/Ricettario-Waldkorn.pdf", "url_pagina": "https://www.saimaspa.com/default-item/waldkorn-ricettario/", "sezione": "Applicazioni Prodotto"},
    {"id": "pan-della-vigna-ricettario", "nome": "Pan della Vigna", "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2022/10/Ricettario-Pan-della-vigna.pdf", "url_pagina": "https://www.saimaspa.com/default-item/pan-della-vigna-ricettario/", "sezione": "Applicazioni Prodotto"},
    {"id": "croissant-ricettario", "nome": "Croissant", "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2022/10/Ricettario-Croissant.pdf", "url_pagina": "https://www.saimaspa.com/default-item/croissant-ricettario/", "sezione": "Applicazioni Prodotto"},
    {"id": "pancampagna-rustico-ricettario", "nome": "Pancampagna Rustico", "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2022/10/Ricettario-Pancampagna-Rustico.pdf", "url_pagina": "https://www.saimaspa.com/default-item/pancampagna-rustico-ricettario/", "sezione": "Applicazioni Prodotto"},
    {"id": "rex-bucheron-ricettario", "nome": "Rex Bucheron", "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2022/10/Ricettario-Rex-Bucheron.pdf", "url_pagina": "https://www.saimaspa.com/default-item/rex-bucheron-ricettario/", "sezione": "Applicazioni Prodotto"},
    {"id": "craft-malz-ricettario-2", "nome": "Craft Malz", "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2022/10/Ricettario-Craft-Malz.pdf", "url_pagina": "https://www.saimaspa.com/default-item/craft-malz-ricettario-2/", "sezione": "Applicazioni Prodotto"},
    {"id": "soft-break-ricettario", "nome": "Soft Break", "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2022/10/Ricettario-Soft-Break.pdf", "url_pagina": "https://www.saimaspa.com/default-item/soft-break-ricettario/", "sezione": "Applicazioni Prodotto"},
    {"id": "cake-nature-ricettario", "nome": "Cake Nature", "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2022/10/Ricettario-Cake-Nature.pdf", "url_pagina": "https://www.saimaspa.com/default-item/cake-nature-ricettario/", "sezione": "Applicazioni Prodotto"},
    {"id": "chocospalmabili-bonfritto-e-forno", "nome": "Bonfritto e Forno (Choco Spalmabili)", "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2022/10/Ricettario-Bonfritto-e-Forno.pdf", "url_pagina": "https://www.saimaspa.com/default-item/chocospalmabili-bonfritto-e-forno/", "sezione": "Applicazioni Prodotto"},
    {"id": "5-ricette-in-5-minuti-ricettario", "nome": "5 Ricette in 5 Minuti", "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2022/10/Ricettario-5-ricette-in-5-minuti.pdf", "url_pagina": "https://www.saimaspa.com/default-item/5-ricette-in-5-minuti-ricettario/", "sezione": "Applicazioni Prodotto"},
    {"id": "choquit-ricettario", "nome": "Choquit", "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2022/10/Ricettario-Choquit.pdf", "url_pagina": "https://www.saimaspa.com/default-item/choquit-ricettario/", "sezione": "Applicazioni Prodotto"},
    {"id": "pasticceria-mignon-ricettario", "nome": "Pasticceria Mignon", "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2022/10/Ricettario-Pasticceria-Mignon.pdf", "url_pagina": "https://www.saimaspa.com/default-item/pasticceria-mignon-ricettario/", "sezione": "Applicazioni Prodotto"},
    {"id": "creme-con-cioccolato-callebaut-ricettario", "nome": "Creme con Cioccolato Callebaut", "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2022/10/Ricettario-Creme-con-Cioccolato-Callebaut.pdf", "url_pagina": "https://www.saimaspa.com/default-item/creme-con-cioccolato-callebaut-ricettario/", "sezione": "Applicazioni Prodotto"},
    {"id": "mix-savoiardo-ricettario", "nome": "Mix Savoiardo", "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2022/10/Ricettario-Mix-Savoiardo.pdf", "url_pagina": "https://www.saimaspa.com/default-item/mix-savoiardo-ricettario/", "sezione": "Applicazioni Prodotto"},
    {"id": "scrocchiarella-ricettario", "nome": "Scrocchiarella", "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2022/10/Ricettario-Scrocchiarella.pdf", "url_pagina": "https://www.saimaspa.com/default-item/scrocchiarella-ricettario/", "sezione": "Applicazioni Prodotto"},
    {"id": "mix-muffin-ricettario", "nome": "Mix Muffin", "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2022/10/Ricettario-Mix-muffin.pdf", "url_pagina": "https://www.saimaspa.com/default-item/mix-muffin-ricettario/", "sezione": "Applicazioni Prodotto"},
]

RICETTARI_STATICI = RICETTARI_RICORRENZE + RICETTARI_APPLICAZIONI

# Ricettari MEPA Alimentari — aggiungi manualmente tramite l'interfaccia
# Nessun PDF pubblicamente disponibile
RICETTARI_MEPA = []

ALL_RICETTARI_STATICI = RICETTARI_STATICI + RICETTARI_MEPA

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "it-IT,it;q=0.9",
}


@router.get("")
async def get_ricettari():
    """Restituisce la lista dei ricettari SAIMA + MEPA con link PDF (senza duplicati)."""
    # Prima controlla se ci sono ricettari extra in DB
    db_extra = await db.saima_ricettari.find({}, {"_id": 0}).to_list(100)
    
    # Prende solo quelli non già presenti nella lista statica
    ids_statici = {r["id"] for r in ALL_RICETTARI_STATICI}
    nuovi = [extra for extra in db_extra if extra.get("id") not in ids_statici]
    
    # Unisce statici + solo i nuovi dal DB
    return list(ALL_RICETTARI_STATICI) + nuovi


@router.get("/pdf-proxy")
async def proxy_pdf(url: str = Query(..., description="URL del PDF da proxare")):
    """
    Proxy backend per visualizzare PDF SAIMA inline nell'app.
    Scarica il PDF da SAIMA e lo restituisce con gli header corretti per l'embedding.
    """
    import urllib.parse
    # Whitelist: domini autorizzati
    DOMINI_AUTORIZZATI = {"saimaspa.com", "www.saimaspa.com", "mepaalimentari.com", "www.mepaalimentari.com"}
    parsed = urllib.parse.urlparse(url)
    if parsed.netloc not in DOMINI_AUTORIZZATI:
        raise HTTPException(status_code=403, detail=f"URL non autorizzato: {parsed.netloc}")
    
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            r = await client.get(url, headers=HEADERS)
            if r.status_code != 200:
                raise HTTPException(status_code=502, detail=f"PDF non disponibile: HTTP {r.status_code}")
            content_type = r.headers.get("content-type", "application/pdf")
            if "html" in content_type.lower():
                raise HTTPException(status_code=502, detail="Il server ha restituito HTML invece del PDF")
            from fastapi.responses import Response
            return Response(
                content=r.content,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": "inline",
                    "Cache-Control": "public, max-age=3600",
                    "X-Content-Type-Options": "nosniff",
                    "Content-Security-Policy": "default-src 'self'",
                }
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Errore download PDF: {str(e)}")


@router.post("/aggiorna")
async def aggiorna_ricettari(background_tasks: BackgroundTasks):
    """Tenta di recuperare ricettari aggiuntivi dal sito SAIMA (esegue in background)."""

    async def esegui():
        sezioni = [
            "https://www.saimaspa.com/ricettari-e-ricette/",
            "https://www.saimaspa.com/ricettari-ricorrenze/",
        ]
        found = []
        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
                for sezione in sezioni:
                    r = await client.get(sezione, headers=HEADERS)
                    soup = BeautifulSoup(r.text, "html.parser")
                    for a in soup.find_all("a", href=True):
                        href = a["href"]
                        if "/default-item/" in href:
                            nome = a.get_text(strip=True)
                            if nome and href not in [x["url_pagina"] for x in found]:
                                found.append({"nome": nome, "url_pagina": href})
                
                # Per ognuno recupera il link PDF
                for item in found:
                    rid = item["url_pagina"].split("/default-item/")[-1].strip("/")
                    # Evita duplicati con statici
                    if any(r["id"] == rid for r in RICETTARI_STATICI):
                        continue
                    try:
                        r = await client.get(item["url_pagina"], headers=HEADERS)
                        soup = BeautifulSoup(r.text, "html.parser")
                        for a in soup.find_all("a", href=True):
                            if ".pdf" in a["href"].lower() and "Privacy" not in a.get_text() and "Cookie" not in a.get_text():
                                ricettario = {
                                    "id": rid,
                                    "nome": item["nome"].replace(" – Ricettario", "").strip(),
                                    "url_pdf": a["href"],
                                    "url_pagina": item["url_pagina"],
                                    "sezione": "Aggiornato",
                                    "data_aggiornamento": datetime.now(timezone.utc).isoformat(),
                                }
                                await db.saima_ricettari.update_one(
                                    {"id": rid}, {"$set": ricettario}, upsert=True
                                )
                                break
                    except Exception:
                        pass
        except Exception as e:
            print(f"[SAIMA Ricettari] Errore aggiornamento: {e}")

    background_tasks.add_task(esegui)
    return {"message": "Aggiornamento ricettari avviato in background"}


class NuovoRicettario(BaseModel):
    nome: str
    url_pdf: str
    sezione: str = "MEPA"
    fornitore: str = ""

@router.post("/aggiungi")
async def aggiungi_ricettario(body: NuovoRicettario):
    """Aggiunge un ricettario custom (MEPA o altro) tramite URL PDF diretto."""
    import re, urllib.parse
    # Genera ID univoco dal nome
    rid = re.sub(r'[^a-z0-9]+', '-', body.nome.lower()).strip('-')
    # Verifica URL
    parsed = urllib.parse.urlparse(body.url_pdf)
    if not parsed.scheme.startswith("http"):
        raise HTTPException(400, "URL non valido")
    doc = {
        "id": rid,
        "nome": body.nome.strip(),
        "url_pdf": body.url_pdf.strip(),
        "url_pagina": body.url_pdf,
        "sezione": body.sezione,
        "fornitore": body.fornitore,
        "aggiunto_manualmente": True,
        "data_aggiornamento": datetime.now(timezone.utc).isoformat(),
    }
    await db.saima_ricettari.update_one({"id": rid}, {"$set": doc}, upsert=True)
    return {"success": True, "id": rid, "nome": body.nome}


@router.delete("/{ricettario_id}")
async def elimina_ricettario(ricettario_id: str):
    """Elimina un ricettario custom dal DB (non quelli statici SAIMA)."""
    # Verifica non sia uno statico
    ids_statici = {r["id"] for r in ALL_RICETTARI_STATICI}
    if ricettario_id in ids_statici:
        raise HTTPException(400, "Non puoi eliminare i ricettari SAIMA statici")
    r = await db.saima_ricettari.delete_one({"id": ricettario_id})
    if r.deleted_count == 0:
        raise HTTPException(404, "Ricettario non trovato")
    return {"success": True}
