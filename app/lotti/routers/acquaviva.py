import logging

"""
Router per prodotti semilavorati commerciali (Acquaviva, Vandemoortele, Alpha, ecc.).
Gestisce: listino, vendite giornaliere, registro invenduto e prezzo per pezzo.
"""
from fastapi import Depends, APIRouter, HTTPException, Query, Body, UploadFile, File, BackgroundTasks
from datetime import datetime, timezone, date
from typing import Optional, List
from pymongo import UpdateOne
import uuid, re, io, asyncio, unicodedata, json
from pathlib import Path
from urllib.parse import urlparse
import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/acquaviva", tags=["acquaviva"])
from app.lotti.db import database as db
# 25/07/2026 (TRANCHE 2 sicurezza): gli import e le sincronizzazioni di
# MASSA riscrivono cataloghi e listini interi. Riservati all'amministratore.
from app.lotti.auth import require_admin

ACQUAVIVA_BASE = "https://dolciariaacquaviva.com"
ACQUAVIVA_SHOP = f"{ACQUAVIVA_BASE}/shop/"
ACQUAVIVA_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "it-IT,it;q=0.9",
    "Accept": "text/html,application/xhtml+xml",
}

_LISTINO_2026_PATH = Path(__file__).resolve().parent.parent / "data" / "listino_acquaviva_vandemoortele_2026.json"
_ALIAS_FATTURA_PER_CODICE = {
    "57245": ["AQV BABY CRNT CALI STRA 35G 3.15KG", "BABY CORNETTO CALISE DRITTO VUOTO"],
    "57380": ["AQV CARUSO SICILIAN LMN CR 90G 4.95KG"],
    "CI0004L": ["AQV CMBLL MAXI SUGARED 100G 3KG", "CIAMBELLA MAXI ZUCCHERATA G. 100"],
    "CI0002": ["AQV CMBLL MINI SUGARED 22G 2.64KG", "CIAMBELLA MINI ZUCCHERATA G. 22/25"],
    "57408": ["AQV CODA D'ARAGOSTA 100G 7.5KG"],
    "57406": ["AQV CODA D'ARAGOSTA MGN 29G 7KG", "CODA D'ARAGOSTA MIG.GR.28/30"],
    "62020": ["AQV CORNETTO VEG BLACK AI FDB 80G 3,84KG"],
    "62018": ["AQV CORNETTO VEG CURCUMA VUOTO 75G 4,6KG"],
    "60944": ["AQV CRNT CALI STRA 95G 3.8KG", "CORNETTO CALISE DRITTO VUOTO 95G SG"],
    "60945": ["AQV CRNT CALI STRA CREA 105G 4.2KG"],
    "60933": ["AQV CRNT CURVED MLTCER BER 80G 4.16KG", "CORNETTO CURVO MULTICEREALI FRUTTI DI"],
    "57184": ["AQV CRNT STR MLTCER HONEY 80G 4.48KG", "CORNETTO DRITTO MULTIC. AL MIELE PREL."],
    "57177": ["AQV CRNT STR WHML 65G 4.03KG", "CORNETTO DRITTO INTGRALE VUOTO 65G S.G."],
    "60934": ["AQV CRNT VGN CURVED 70G 3.64KG", 'CORNETTO "VEGANO" CURVO VUOTO G. 70 SG'],
    "57204": ["AQV CRNT VGN POM & OATS 85G 3.825KG", "CORNETTO VEGANO MELAGRANA E AVENA G. 85"],
    "60935": ["AQV CRNT VGN STR ORANGE 80G 3.6KG", "CORNETTO VEGANO DRITTO ALL'ARANCIA"],
    "60937": ["AQV CROI DRMI STR PSTCH 95G 4.94KG"],
    "57216": ["AQV CROI STR CIN CRM BTR 95G 4.94KG", "CROISSANT DRITTO CREMA CANNELLA BURRO G."],
    "57356": ["AQV CROI STR PSTCH BTR 95G 4.94KG", "CROISSANT DRITTO PISTACCHIO BURRO 95G SG"],
    "57363": ["AQV GRAN CRNT CARUSO CRVD 85G 3.825KG", "GRAN CORNETTO CARUSO CURVO VUOTO GLASSAT"],
    "57629": ["AQV SFOGLIATELLA FROLLA MI 35G 7KG", "SFOGLIAT.FROLLA MIGNON GR.30"],
    "57625": ["AQV SFOGLIATELLA NAPOLETAN 35G 7KG", "SFOGL.NAP.MIGNON GR.30"],
    "57557": ["AQV SOFIA 82G 4.592KG"],
    "57659": ["AQV TAPPI GRANDI 57G 6KG", "TAPPI GRANDI G 55/60"],
    "57657": ["AQV TAPPI MIGNON FOR SFOGL 20G 4KG", "TAPPI MIGNON PER SFOGLIATE GR.20"],
    "SGC001": ["CORNETTO SENZA GLUTINE VUOTO G. 100"],
    "SGC002": ["CORNETTO SENZA GLUTINE ALBICOCCA G. 100"],
    "57530": ["PANCAKE G. 40"],
}


async def inizializza_mapping_vandemoortele_2026() -> dict:
    """Arricchisce idempotentemente il catalogo web con i codici di migrazione 2025/2026.

    Non crea doppioni e non tocca foto, descrizioni web o prezzi reali: aggiunge
    soltanto quantità cartone, pesi e alias utili a riconoscere le fatture VDM.
    """
    if not _LISTINO_2026_PATH.exists():
        return {"aggiornati": 0, "motivo": "file assente"}
    payload = json.loads(_LISTINO_2026_PATH.read_text(encoding="utf-8"))
    esistenti = await db.acquaviva_prodotti.find({}, {"_id": 0}).to_list(2000)
    lookup = {}
    nomi = {}
    for prodotto in esistenti:
        for campo in ("codice_articolo", "codice", "codice_aqv_2025", "codice_aqv_2026"):
            valore = str(prodotto.get(campo) or "").strip().upper()
            if valore:
                lookup.setdefault(valore, prodotto)
        nome = re.sub(r"\s+", " ", str(prodotto.get("nome") or "").strip().upper())
        if nome:
            nomi.setdefault(nome, prodotto)
    operazioni = []
    for riga in payload.get("prodotti", []):
        vecchio = str(riga.get("codice_aqv_2025") or "").strip()
        nuovo = str(riga.get("codice_aqv_2026") or "").strip()
        nome = re.sub(r"\s+", " ", str(riga.get("descrizione") or "").strip().upper())
        prodotto = lookup.get(nuovo.upper()) or lookup.get(vecchio.upper()) or nomi.get(nome)
        if not prodotto or not prodotto.get("id"):
            continue
        grammi = float(riga.get("grammi") or 0)
        pezzi = float(riga.get("qty_cartone") or 0)
        campi = {
            "codice_aqv_2025": vecchio,
            "codice_aqv_2026": nuovo,
            "codici_alias": [c for c in dict.fromkeys([vecchio, nuovo]) if c],
            "grammi": grammi,
            "qty_cartone": pezzi,
            "pz_confezione": pezzi,
            "peso_totale_cartone_g": round(grammi * pezzi, 2) if grammi and pezzi else 0,
            "categoria_aqv": riga.get("categoria_aqv", ""),
            "categoria_vdm": riga.get("categoria_vdm", ""),
            "data_listino": "2026-01-01",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        operazioni.append(UpdateOne({"id": prodotto["id"]}, {"$set": campi}))
    aggiornati_listino = len(operazioni)
    # Alcune referenze storiche non sono nel listino JSON corrente ma sono gia'
    # presenti nel catalogo web. Le colleghiamo solo tramite il codice ufficiale.
    for codice, alias in _ALIAS_FATTURA_PER_CODICE.items():
        prodotto = lookup.get(codice.upper())
        if not prodotto or not prodotto.get("id"):
            continue
        operazioni.append(
            UpdateOne(
                {"id": prodotto["id"]},
                {"$addToSet": {"alias_fattura": {"$each": alias}}},
            )
        )
    if operazioni:
        await db.acquaviva_prodotti.bulk_write(operazioni, ordered=False)
    return {
        "aggiornati": aggiornati_listino,
        "alias_aggiornati": len(operazioni) - aggiornati_listino,
        "righe_listino": len(payload.get("prodotti", [])),
    }

ACQUAVIVA_CATEGORIE = [
    {"nome": "Prelievitati", "img": ""},
    {"nome": "Sfoglie", "img": ""},
    {"nome": "Semilavorati", "img": ""},
    {"nome": "Da lievitare", "img": ""},
    {"nome": "Già cotti", "img": ""},
    {"nome": "Senza Glutine", "img": ""},
    {"nome": "Tipici", "img": ""},
    {"nome": "Biscotti", "img": ""},
    {"nome": "Dessert", "img": ""},
    {"nome": "Monoporzioni", "img": ""},
    {"nome": "Snack", "img": ""},
    {"nome": "Pani e focacce", "img": ""},
    {"nome": "Novità", "img": ""},
]

# ── ALLERGENI — keywords molto più ampie per copertura da Descrizione ─────────
ALLERGENI_MAP = {
    "glutine": [
        "farina",
        "grano",
        "frument",
        "orzo",
        "segale",
        "farro",
        "avena",
        "kamut",
        "semola",
        "pasta",
        "pane",
        "biscot",
        "brioche",
        "croissant",
        "cornett",
        "sfoglia",
        "lievit",
        "focacc",
        "crackers",
        "cracker",
        "grissini",
    ],
    "latte": [
        "latte",
        "burro",
        "panna",
        "formaggio",
        "mozzarella",
        "ricotta",
        "mascarpone",
        "yogurt",
        "latticin",
        "besciamella",
        "cheddar",
        "grana",
        "parmigian",
        "parvé",
        "caciott",
        "lattiero",
    ],
    "uova": ["uov", "albume", "tuorlo", "maionese"],
    "frutta a guscio": [
        "nocciola",
        "noce",
        "mandorla",
        "pistacchio",
        "anacardo",
        "pinoli",
        "arachid",
        "pecan",
        "noce di cocco",
        "frutta a guscio",
        "granella di noce",
    ],
    "soia": ["soia", "tofu", "lecitina di soia", "proteina di soia"],
    "sesamo": ["sesamo", "tahina"],
    "senape": ["senape", "mostarda"],
    "sedano": ["sedano"],
    "solfiti": ["solfiti", "solforosa", "metabisolfito", "e220", "e221", "e222", "e223", "e224"],
    "pesce": [
        "pesce",
        "merluzzo",
        "salmone",
        "tonno",
        "acciuga",
        "sardina",
        "orata",
        "baccalà",
        "alice",
    ],
    "crostacei": ["gambero", "aragosta", "granchio", "scampo", "astice"],
    "molluschi": ["cozze", "vongole", "calamaro", "polpo", "seppia", "ostrica"],
    "lupini": ["lupini", "lupino"],
    "margarina": ["margarina"],  # non allergene ufficiale ma importante
}

# Allergeni che richiedono dichiarazione obbligatoria
ALLERGENI_UE = {
    "glutine",
    "latte",
    "uova",
    "frutta a guscio",
    "soia",
    "sesamo",
    "senape",
    "sedano",
    "solfiti",
    "pesce",
    "crostacei",
    "molluschi",
    "lupini",
}


def rileva_allergeni(nome: str = "", descrizione: str = "", categoria: str = "") -> List[str]:
    """Rileva allergeni dal nome + descrizione + categoria del prodotto."""
    testo = f"{nome} {descrizione} {categoria}".lower()
    trovati = []
    for allergene, kws in ALLERGENI_MAP.items():
        if any(kw in testo for kw in kws):
            trovati.append(allergene)
    return trovati


def rileva_allergeni_da_testo(testo: str) -> List[str]:
    return rileva_allergeni(descrizione=testo)


def _parse_lista_ingredienti_pdf(content: bytes) -> List[dict]:
    """Estrae la tabella CODICE/DESCRIZIONE/LISTA INGREDIENTI.

    Il codice e' l'unica identita' usata dall'import: il nome resta evidenza
    leggibile ma non viene mai usato per forzare un'associazione.
    """
    try:
        import pdfplumber
    except ImportError as exc:
        raise HTTPException(500, "pdfplumber non disponibile. Contattare l'amministratore.") from exc

    righe: List[dict] = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for pagina, page in enumerate(pdf.pages, 1):
            for table in page.extract_tables() or []:
                for row in table or []:
                    if not row or len(row) < 3:
                        continue
                    codice = re.sub(r"\s+", "", str(row[0] or ""))
                    nome = re.sub(r"\s+", " ", str(row[1] or "")).strip()
                    ingredienti = re.sub(r"\s+", " ", str(row[2] or "")).strip()
                    if not codice.isdigit() or not nome or not ingredienti:
                        continue
                    righe.append({
                        "codice": codice,
                        "nome_documento": nome,
                        "ingredienti_str": ingredienti,
                        "pagina": pagina,
                    })
    # Un codice duplicato nel documento e' ambiguo: non scegliamo una riga.
    conteggi = {}
    for riga in righe:
        conteggi[riga["codice"]] = conteggi.get(riga["codice"], 0) + 1
    return [r for r in righe if conteggi[r["codice"]] == 1]


def _codici_catalogo(prodotto: dict) -> set[str]:
    valori = [
        prodotto.get("codice"), prodotto.get("codice_articolo"),
        prodotto.get("codice_aqv_2025"), prodotto.get("codice_aqv_2026"),
        *(prodotto.get("codici_alias") or []),
    ]
    return {re.sub(r"\s+", "", str(v or "")) for v in valori if str(v or "").strip()}


async def _applica_lista_ingredienti(righe: List[dict], nome_file: str) -> dict:
    """Applica ingredienti/allergeni solo ai codici catalogo univoci.

    Aggiorna anche i dizionari usati dal ricettario e aggiunge alle ricette
    collegate gli allergeni del prodotto, senza cancellare dichiarazioni gia'
    presenti o conferme manuali.
    """
    from app.lotti.allergeni import rileva_allergeni as rileva_allergeni_ufficiali

    catalogo = await db.acquaviva_prodotti.find(
        {"fonte": {"$in": ["acquaviva", "vandemoortele"]}}, {"_id": 0}
    ).to_list(5000)
    per_codice: dict[str, list[dict]] = {}
    for prodotto in catalogo:
        for codice in _codici_catalogo(prodotto):
            per_codice.setdefault(codice, []).append(prodotto)

    aggiornati = []
    non_trovati = []
    ambigui = []
    timestamp = datetime.now(timezone.utc).isoformat()
    for riga in righe:
        candidati = per_codice.get(riga["codice"], [])
        ids = {p.get("id") for p in candidati if p.get("id")}
        if len(ids) != 1:
            (ambigui if len(ids) > 1 else non_trovati).append({
                "codice": riga["codice"], "nome": riga["nome_documento"]
            })
            continue
        prodotto = next(p for p in candidati if p.get("id") in ids)
        allergeni, _ = rileva_allergeni_ufficiali([riga["ingredienti_str"]])
        campi = {
            "ingredienti_str": riga["ingredienti_str"],
            "ingredienti": riga["ingredienti_str"],
            "allergeni": allergeni,
            "allergeni_fonte": {
                "tipo": "lista_ingredienti_fornitore",
                "file": nome_file,
                "codice": riga["codice"],
                "pagina": riga["pagina"],
                "importato_il": timestamp,
            },
            "updated_at": timestamp,
        }
        pid = prodotto["id"]
        await db.acquaviva_prodotti.update_one({"id": pid}, {"$set": campi})
        # Solo documenti gia' promossi nel ricettario: nessun nuovo ingrediente
        # operativo viene creato dall'import del PDF.
        for collection in (db.dizionario_prodotti, db.dizionario_ingredienti):
            await collection.update_one({"id": pid}, {"$set": campi})
        aggiornati.append({"id": pid, "codice": riga["codice"], "allergeni": allergeni})

    allergeni_per_id = {r["id"]: r["allergeni"] for r in aggiornati}
    ricette_aggiornate = 0
    if allergeni_per_id:
        ricette = await db.ricette.find(
            {}, {"_id": 0, "id": 1, "ingredienti_dettaglio": 1, "allergeni": 1,
                 "allergeni_auto": 1, "allergeni_da_confermare": 1}
        ).to_list(5000)
        for ricetta in ricette:
            ereditati = []
            for dettaglio in ricetta.get("ingredienti_dettaglio") or []:
                if not isinstance(dettaglio, dict):
                    continue
                pid = dettaglio.get("prodotto_master_id") or dettaglio.get("prodotto_id")
                for allergene in allergeni_per_id.get(pid, []):
                    if allergene not in ereditati:
                        ereditati.append(allergene)
            if not ereditati:
                continue
            correnti = list(ricetta.get("allergeni") or [])
            automatici = list(ricetta.get("allergeni_auto") or [])
            nuovi = [a for a in ereditati if a not in correnti]
            for allergene in ereditati:
                if allergene not in correnti:
                    correnti.append(allergene)
                if allergene not in automatici:
                    automatici.append(allergene)
            update = {
                "allergeni": correnti,
                "allergeni_auto": automatici,
                "allergeni_catalogo_fornitore": ereditati,
                "allergeni_catalogo_aggiornati_il": timestamp,
            }
            # Un nuovo allergene richiede controllo umano della ricetta; una
            # conferma precedente resta valida se il dato era gia' presente.
            if nuovi:
                update["allergeni_da_confermare"] = True
            await db.ricette.update_one({"id": ricetta["id"]}, {"$set": update})
            ricette_aggiornate += 1

    return {
        "righe_pdf": len(righe),
        "prodotti_aggiornati": len(aggiornati),
        "ricette_aggiornate": ricette_aggiornate,
        "non_trovati": non_trovati,
        "ambigui": ambigui,
    }


def _normalizza_nome_catalogo(value: str) -> str:
    value = unicodedata.normalize("NFKD", str(value or "").casefold())
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _ripara_testo_acquaviva(value: str) -> str:
    """Il sito espone alcune vecchie schede con U+FFFD già nell'HTML.
    Correggiamo solo i marchi/simboli noti, senza inventare il resto del nome."""
    text = str(value or "")
    replacements = {
        "Doram�": "Doramì",
        "Boscor�": "Boscorè",
        "Ciocopi�": "Ciocopiù",
        "pi�": "più",
        "gi�": "già",
        "qualit�": "qualità",
        "bont�": "bontà",
        "novit�": "novità",
        "specialit�": "specialità",
        "caff�": "caffè",
        "dall�": "dall’",
        "18�30": "18×30",
        "40�30": "40×30",
        " � ": " – ",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def _foto_acquaviva_originale(url: str) -> str:
    """Rimuove solo il suffisso di resize WordPress, preservando il file vero."""
    return re.sub(r"-\d+x\d+(?=\.[a-zA-Z0-9]+(?:\?|$))", "", str(url or "").strip())


def _parse_acquaviva_listing(html: str) -> List[dict]:
    """Parser puro della griglia ufficiale: usato sia dallo scraper sia dai test."""
    soup = BeautifulSoup(html or "", "html.parser")
    prodotti = []
    for item in soup.select(".jet-woo-products__item, li.product, .products .product"):
        titolo = item.select_one(
            ".jet-woo-product-title a, .woocommerce-loop-product__title, h2 a, h3 a, h5 a"
        )
        if not titolo:
            continue
        nome = _ripara_testo_acquaviva(titolo.get_text(" ", strip=True))
        link = (titolo.get("href") or "").strip()
        if len(nome) < 2 or not link:
            continue

        img = item.select_one("img")
        foto = ""
        if img:
            foto = (
                img.get("data-src")
                or img.get("data-lazy-src")
                or img.get("src")
                or ""
            )
            foto = _foto_acquaviva_originale(foto)

        categorie = list(dict.fromkeys(
            a.get_text(" ", strip=True)
            for a in item.select(".jet-woo-product-categories a, .product-category a")
            if a.get_text(" ", strip=True)
        ))
        categoria = " > ".join(categorie)
        prodotto_id = item.get("data-product-id") or ""
        codice_img = ""
        if foto:
            match = re.search(r"/([A-Za-z]{1,8}\d{3,})(?:[-_.])", foto)
            if match:
                codice_img = match.group(1).upper()

        prodotti.append({
            "id": str(uuid.uuid5(uuid.NAMESPACE_URL, link)),
            "nome": nome,
            "nome_display": nome,
            "nome_normalizzato": _normalizza_nome_catalogo(nome),
            "codice_articolo": codice_img,
            "codice_sito": str(prodotto_id),
            "categoria": categoria,
            "categorie_sorgente": categorie,
            "immagine_url": foto,
            "foto_url": foto,
            "link_prodotto": link,
            "fornitore": "Dolciaria Acquaviva",
            "fonte": "acquaviva",
            "attivo": True,
        })
    return prodotti


def _parse_acquaviva_dettaglio(html: str) -> dict:
    soup = BeautifulSoup(html or "", "html.parser")
    dettaglio = {}
    h1 = soup.select_one("h1")
    if h1:
        dettaglio["nome_verificato"] = _ripara_testo_acquaviva(h1.get_text(" ", strip=True))

    tabella = soup.select_one("table")
    if tabella:
        righe = tabella.select("tr")
        headers = []
        values = []
        if len(righe) >= 2:
            headers = [
                cell.get_text(" ", strip=True).upper()
                for cell in righe[0].select("th, td")
            ]
            values = [cell.get_text(" ", strip=True) for cell in righe[1].select("th, td")]
        if headers and values:
            campi = dict(zip(headers, values))
            dettaglio["specifiche"] = campi
            dettaglio["codice_articolo"] = campi.get("CODICE", "")
            dettaglio["peso_g"] = campi.get("GRAMMI", "")
            dettaglio["pz_confezione"] = campi.get("PZ CONF", campi.get("PZ CONF.", ""))
            if dettaglio["pz_confezione"]:
                dettaglio["unita_confezione"] = f"{dettaglio['pz_confezione']} pz"

    contenuto = soup.select_one(".elementor-widget-woocommerce-product-content")
    if contenuto:
        clone = BeautifulSoup(str(contenuto), "html.parser")
        for table in clone.select("table"):
            table.decompose()
        descrizione = clone.get_text(" ", strip=True)
        if descrizione:
            dettaglio["descrizione_lunga"] = _ripara_testo_acquaviva(descrizione[:1000])

    img = soup.select_one(
        ".woocommerce-product-gallery img, .jet-woo-builder-product img, main img"
    )
    if img:
        foto = img.get("data-large_image") or img.get("data-src") or img.get("src") or ""
        if foto:
            dettaglio["immagine_prodotto"] = _foto_acquaviva_originale(foto)
    return dettaglio


def _url_acquaviva_sicuro(url: str) -> bool:
    parsed = urlparse(str(url or ""))
    return parsed.scheme == "https" and parsed.hostname in {
        "dolciariaacquaviva.com", "www.dolciariaacquaviva.com"
    }


async def _scarica_dettaglio_acquaviva(client: httpx.AsyncClient, url: str) -> dict:
    if not _url_acquaviva_sicuro(url):
        return {}
    response = await client.get(url, headers=ACQUAVIVA_HEADERS)
    if response.status_code != 200:
        return {}
    # Il sito dichiara UTF-8 ma alcune pagine storiche contengono byte
    # Windows-1252 (per esempio ``qualit\u00e0``). httpx li sostituisce con U+FFFD:
    # in quel caso decodifichiamo i byte originali, senza alterare le pagine
    # realmente UTF-8.
    html = response.text
    if "\ufffd" in html:
        html = response.content.decode("cp1252", errors="replace")
    return _parse_acquaviva_dettaglio(html)


# ── ENDPOINTS ────────────────────────────────────────────────────────────────


@router.get("/prodotti")
async def get_acquaviva_prodotti(
    search: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    categoria: Optional[str] = Query(None),
    fonte: Optional[str] = Query(None),  # "acquaviva", "alpha", "vandemoortele", None=tutti
):
    query = {}
    if fonte:
        query["fonte"] = fonte
    else:
        # Per default mostra tutti i semilavorati (acquaviva + vandemoortele, non alpha)
        query["fonte"] = {"$in": ["acquaviva", "vandemoortele"]}
    testo_ricerca = search or q
    if testo_ricerca:
        query["nome"] = {"$regex": testo_ricerca, "$options": "i"}
    if categoria:
        query["categoria"] = {"$regex": categoria, "$options": "i"}
    items = await db.acquaviva_prodotti.find(query, {"_id": 0}).sort("nome", 1).to_list(1000)
    ids = [p.get("id") for p in items if p.get("id")]
    if ids:
        attivi = await db.dizionario_prodotti.find(
            {"id": {"$in": ids}, "attivo": {"$ne": False}}, {"_id": 0, "id": 1}
        ).to_list(2000)
        attivi_ids = {p.get("id") for p in attivi}
        for prodotto in items:
            prodotto["in_ricette"] = prodotto.get("id") in attivi_ids
    # Prezzo e flag "già acquistato" SOLO dalle fatture reali (match per nome ufficiale),
    # stesso meccanismo di SAIMA/MEPA. I prodotti mai comprati restano senza prezzo.
    try:
        from app.lotti.routers.utils import prezzi_fatture_per_fornitore, applica_prezzo_da_fatture
        prezzi = await prezzi_fatture_per_fornitore(db, "acquaviva|vandemoortele|alpha")
        items = applica_prezzo_da_fatture(items, prezzi)
    except Exception:
        logger.debug("[acquaviva] errore non bloccante ignorato")
    return items


@router.post("/prodotti/{prodotto_id}/usa-in-ricette")
async def usa_prodotto_acquaviva_in_ricette(
    prodotto_id: str,
    _admin=Depends(require_admin),
):
    prodotto = await db.acquaviva_prodotti.find_one({"id": prodotto_id}, {"_id": 0})
    if not prodotto:
        raise HTTPException(404, "Prodotto Acquaviva non trovato")
    fonte_prodotto = prodotto.get("fonte") or "acquaviva"
    doc = {
        **prodotto,
        "id": prodotto_id,
        "fonte": fonte_prodotto,
        f"is_{fonte_prodotto}": True,
        "attivo": True,
        "data_aggiornamento": datetime.now(timezone.utc).isoformat(),
    }
    # Fonte canonica del food cost e dell'autocomplete ricette. Manteniamo
    # anche la vecchia collection per compatibilità con installazioni storiche.
    await db.dizionario_prodotti.update_one({"id": prodotto_id}, {"$set": doc}, upsert=True)
    await db.dizionario_ingredienti.update_one({"id": prodotto_id}, {"$set": doc}, upsert=True)
    return {"ok": True, "id": prodotto_id}


@router.get("/categorie")
async def get_acquaviva_categorie():
    """Categorie principali pubblicate dal catalogo ufficiale Acquaviva."""
    return ACQUAVIVA_CATEGORIE


@router.get("/dettaglio-prodotto")
async def dettaglio_prodotto_acquaviva(url: str = Query(...)):
    """Dettaglio ufficiale on-demand, limitato al dominio Acquaviva."""
    if not _url_acquaviva_sicuro(url):
        raise HTTPException(400, "URL prodotto Acquaviva non valido")
    async with httpx.AsyncClient(timeout=25, follow_redirects=True) as client:
        dettaglio = await _scarica_dettaglio_acquaviva(client, url)
    if not dettaglio:
        raise HTTPException(404, "Prodotto non trovato sul sito Acquaviva")
    dettaglio["link_prodotto"] = url
    return dettaglio


async def _esegui_scraping_acquaviva(con_dettagli: bool = False):
    iniziato = datetime.now(timezone.utc).isoformat()
    await db.sync_status.update_one(
        {"_id": "scraping_acquaviva"},
        {"$set": {"stato": "in_corso", "iniziato": iniziato, "errore": ""}},
        upsert=True,
    )
    importati = aggiornati = pagine = 0
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            for pagina in range(1, 51):
                url = ACQUAVIVA_SHOP if pagina == 1 else f"{ACQUAVIVA_SHOP}page/{pagina}/"
                response = await client.get(url, headers=ACQUAVIVA_HEADERS)
                if response.status_code == 404:
                    break
                response.raise_for_status()
                prodotti = _parse_acquaviva_listing(response.text)
                if not prodotti:
                    break
                pagine += 1

                for prodotto in prodotti:
                    if con_dettagli and prodotto.get("link_prodotto"):
                        extra = await _scarica_dettaglio_acquaviva(
                            client, prodotto["link_prodotto"]
                        )
                        if extra:
                            prodotto.update(extra)
                            if extra.get("codice_articolo"):
                                prodotto["codice"] = extra["codice_articolo"]
                            if extra.get("immagine_prodotto"):
                                prodotto["immagine_url"] = extra["immagine_prodotto"]
                                prodotto["foto_url"] = extra["immagine_prodotto"]
                        await asyncio.sleep(0.15)

                    prodotto["allergeni"] = rileva_allergeni(
                        prodotto.get("nome", ""),
                        prodotto.get("descrizione_lunga", ""),
                        prodotto.get("categoria", ""),
                    )
                    prodotto["data_aggiornamento"] = datetime.now(timezone.utc).isoformat()
                    filtro_match = {"$or": [
                        {"link_prodotto": prodotto["link_prodotto"]},
                        {
                            "fonte": "acquaviva",
                            "nome_normalizzato": prodotto["nome_normalizzato"],
                        },
                    ]}
                    esistente = await db.acquaviva_prodotti.find_one(
                        filtro_match, {"_id": 1, "id": 1}
                    )
                    if esistente:
                        prodotto["id"] = esistente.get("id") or prodotto["id"]
                        await db.acquaviva_prodotti.update_one(
                            {"_id": esistente["_id"]}, {"$set": prodotto}
                        )
                        aggiornati += 1
                    else:
                        await db.acquaviva_prodotti.insert_one({
                            **prodotto,
                            "codice": prodotto.get("codice") or prodotto.get("codice_articolo"),
                            "prezzo_singolo": 0,
                            "prezzo_vendita": 0,
                            "created_at": datetime.now(timezone.utc).isoformat(),
                        })
                        importati += 1
                await asyncio.sleep(0.35)

        fine = datetime.now(timezone.utc).isoformat()
        log = {
            "fonte": "acquaviva",
            "data": fine,
            "importati": importati,
            "aggiornati": aggiornati,
            "pagine": pagine,
            "con_dettagli": con_dettagli,
        }
        # Motor aggiunge ``_id`` al dizionario passato a insert_one. Manteniamo
        # immutabile ``log`` perché subito dopo viene riusato nel documento di
        # stato, dove tentare di impostare un altro ``_id`` farebbe fallire la
        # conclusione di uno scraping altrimenti già riuscito.
        await db.log_scraping.insert_one(dict(log))
        totale = await db.acquaviva_prodotti.count_documents({"fonte": "acquaviva"})
        await db.sync_status.update_one(
            {"_id": "scraping_acquaviva"},
            {"$set": {"stato": "completato", "fine": fine, "totale": totale, **log}},
            upsert=True,
        )
    except Exception as exc:
        logger.exception("[acquaviva] scraping catalogo fallito")
        await db.sync_status.update_one(
            {"_id": "scraping_acquaviva"},
            {"$set": {
                "stato": "errore",
                "fine": datetime.now(timezone.utc).isoformat(),
                "errore": str(exc)[:500],
            }},
            upsert=True,
        )


@router.post("/scraping/avvia")
async def avvia_scraping_acquaviva(
    background_tasks: BackgroundTasks,
    con_dettagli: bool = Query(False),
    _admin=Depends(require_admin),
):
    stato = await db.sync_status.find_one({"_id": "scraping_acquaviva"}, {"_id": 0})
    if stato and stato.get("stato") == "in_corso":
        return {"avviato": False, "messaggio": "Aggiornamento Acquaviva già in corso"}
    background_tasks.add_task(_esegui_scraping_acquaviva, con_dettagli)
    return {"avviato": True, "messaggio": "Aggiornamento Acquaviva avviato"}


@router.get("/scraping/stato")
async def stato_scraping_acquaviva():
    stato = await db.sync_status.find_one({"_id": "scraping_acquaviva"}, {"_id": 0})
    ultimo = await db.log_scraping.find_one(
        {"fonte": "acquaviva"}, {"_id": 0}, sort=[("data", -1)]
    )
    totale = await db.acquaviva_prodotti.count_documents({"fonte": "acquaviva"})
    return {
        "prodotti_nel_db": totale,
        "ultimo_scraping": ultimo,
        "stato": (stato or {}).get("stato", "mai_eseguito"),
        "errore": (stato or {}).get("errore", ""),
    }


@router.get("/export-foto-zip")
async def export_foto_zip():
    """ZIP con le foto dei prodotti Acquaviva/VDM, ogni file rinominato col
    NOME DEL PRODOTTO (richiesta Enzo 23/07/2026: "estrai foto acquaviva con
    relativi nomi e dammi zip"). Le foto vengono da foto_files su Mongo
    (/api/foto/...) o, se l'URL è esterno, scaricate al volo (best-effort)."""
    import io
    import zipfile
    import httpx as _httpx
    from fastapi.responses import Response

    prodotti = await db.acquaviva_prodotti.find(
        {"foto_url": {"$nin": [None, ""]}},
        {"_id": 0, "nome": 1, "foto_url": 1, "codice": 1},
    ).sort("nome", 1).to_list(3000)

    def _nome_file(nome: str) -> str:
        n = re.sub(r"[^\w\sàèéìòù-]", "", str(nome or "prodotto"), flags=re.UNICODE)
        return re.sub(r"\s+", " ", n).strip()[:120] or "prodotto"

    _EXT = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
    buf = io.BytesIO()
    inseriti, mancanti = 0, []
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        visti = set()
        async with _httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            for p in prodotti:
                url = str(p.get("foto_url") or "")
                dati, mime = None, "image/jpeg"
                m = re.search(r"/api/foto/([^?]+)", url)
                if m:
                    doc = await db.foto_files.find_one({"_id": m.group(1)})
                    if doc and doc.get("data"):
                        dati, mime = bytes(doc["data"]), doc.get("mime", "image/jpeg")
                elif url.startswith("http"):
                    try:
                        r = await client.get(url)
                        if r.status_code == 200 and r.headers.get("content-type", "").startswith("image/"):
                            dati, mime = r.content, r.headers["content-type"].split(";")[0]
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("[Acquaviva] immagine remota non scaricata: %s", exc)
                if not dati:
                    mancanti.append(p.get("nome") or "?")
                    continue
                base = _nome_file(p.get("nome"))
                nome_zip = base
                i = 2
                while nome_zip in visti:
                    nome_zip = f"{base} ({i})"
                    i += 1
                visti.add(nome_zip)
                zf.writestr(nome_zip + _EXT.get(mime, ".jpg"), dati)
                inseriti += 1
        if mancanti:
            zf.writestr("_foto_non_recuperate.txt",
                        "Prodotti con foto_url non scaricabile:\n" + "\n".join(mancanti))
    buf.seek(0)
    return Response(
        content=buf.getvalue(), media_type="application/zip",
        headers={"Content-Disposition":
                 f'attachment; filename="foto_acquaviva_{inseriti}_prodotti.zip"'},
    )


@router.get("/prodotti/senza-glutine")
async def get_prodotti_senza_glutine(search: Optional[str] = Query(None)):
    """Prodotti senza glutine di TUTTI i fornitori attivi tipo 'senza_glutine' (registro)."""
    from app.lotti.routers.fornitori_rivendita import fonti_attive
    fonti = await fonti_attive("senza_glutine")
    query = {"fonte": {"$in": fonti or ["alpha"]}}
    if search:
        query["nome"] = {"$regex": search, "$options": "i"}
    items = await db.acquaviva_prodotti.find(query, {"_id": 0}).sort("nome", 1).to_list(500)
    ids = [p.get("id") for p in items if p.get("id")]
    if ids:
        attivi = await db.dizionario_prodotti.find(
            {"id": {"$in": ids}, "attivo": {"$ne": False}}, {"_id": 0, "id": 1}
        ).to_list(1000)
        attivi_ids = {p.get("id") for p in attivi}
        for prodotto in items:
            prodotto["in_ricette"] = prodotto.get("id") in attivi_ids
    # Prezzo/quantità SOLO da fatture reali (stesso motore degli altri cataloghi):
    # chi sfoglia vede subito quali prodotti senza glutine sono già stati comprati.
    try:
        from app.lotti.routers.utils import prezzi_fatture_per_fornitore, applica_prezzo_da_fatture
        prezzi = await prezzi_fatture_per_fornitore(db, "|".join(fonti or ["alpha"]))
        items = applica_prezzo_da_fatture(items, prezzi)
    except Exception:
        logger.debug("[acquaviva] aggancio prezzi senza-glutine fallito (non bloccante)")
    return items


@router.post("/import-listino-2026")
async def import_listino_2026(payload: dict = Body(...), _admin=Depends(require_admin)):
    """
    Importa il listino Acquaviva/VDM 2026 con tutti i campi:
    codice_aqv_2025, codice_aqv_2026, categoria_aqv, categoria_vdm,
    descrizione, grammi, qty_cartone, unita_misura, prezzo_ct, iva_pct, ct_ble, ct_strato.

    Merge su: codice_aqv_2026 (che corrisponde al campo 'codice' nel DB).
    Se il prodotto esiste già, aggiorna SOLO i campi listino senza toccare prezzi vendita o foto.
    """
    prodotti = payload.get("prodotti", [])
    fonte = payload.get("fonte", "acquaviva")

    importati = 0
    aggiornati = 0
    errori = []

    for prod in prodotti:
        codice_2026 = str(prod.get("codice_aqv_2026", "") or "").strip()
        codice_2025 = str(prod.get("codice_aqv_2025", "") or "").strip()
        nome = (prod.get("descrizione", "") or "").strip()

        if not nome:
            continue

        # Codice principale = 2026, fallback 2025
        codice_principale = codice_2026 if codice_2026 else codice_2025

        # Grammi: parsing robusto (può essere "30-35", "18-20", ecc.)
        grammi_raw = str(prod.get("grammi", "") or "")
        grammi = 0.0
        try:
            grammi = float(grammi_raw.replace(",", ".").split("-")[0].split("/")[0].strip())
        except Exception as e:
            logging.exception(f"[acquaviva] Errore non gestito: {e}")

        # Prezzo CT (prezzo per cartone/confezione)
        prezzo_ct = 0.0
        try:
            prezzo_ct = float(str(prod.get("prezzo_ct", 0) or 0))
        except Exception as e:
            logging.exception(f"[acquaviva] Errore non gestito: {e}")

        qty_cartone = 0.0
        try:
            qty_cartone = float(str(prod.get("qty_cartone", 0) or 0))
        except Exception as e:
            logging.exception(f"[acquaviva] Errore non gestito: {e}")

        # Prezzo per singolo pezzo

        iva_pct = 10.0
        try:
            iva_pct = float(str(prod.get("iva_pct", 10) or 10))
        except Exception as e:
            logging.exception(f"[acquaviva] Errore non gestito: {e}")

        ct_ble = 0
        try:
            ct_ble = int(float(str(prod.get("ct_ble", 0) or 0)))
        except Exception as e:
            logging.exception(f"[acquaviva] Errore non gestito: {e}")

        ct_strato = 0
        try:
            ct_strato = int(float(str(prod.get("ct_strato", 0) or 0)))
        except Exception as e:
            logging.exception(f"[acquaviva] Errore non gestito: {e}")

        categoria_aqv = prod.get("categoria_aqv", "") or ""
        categoria_vdm = prod.get("categoria_vdm", "") or ""
        unita_misura = prod.get("unita_misura", "PZ") or "PZ"

        allergeni = rileva_allergeni(nome=nome, descrizione=nome, categoria=categoria_aqv)

        # Campi da aggiornare / inserire.
        # NB: prezzo_ct è il prezzo di LISTINO, non un acquisto reale: lo conserviamo
        # solo come riferimento (prezzo_listino_riferimento) e NON come prezzo del
        # prodotto. Il prezzo mostrato e il flag "già acquistato" arrivano solo dalle
        # fatture XML, agganciati in GET /acquaviva/prodotti. Azzeriamo qui i campi
        # prezzo per non lasciare in giro i vecchi prezzi di listino.
        campi_listino = {
            "codice_aqv_2025": codice_2025,
            "codice_aqv_2026": codice_2026,
            "categoria_aqv": categoria_aqv,
            "categoria_vdm": categoria_vdm,
            "nome": nome,
            "grammi": grammi,
            "pz_confezione": qty_cartone,
            "qty_cartone": qty_cartone,
            "unita_misura": unita_misura,
            "prezzo_listino_riferimento": prezzo_ct,
            "prezzo_acquisto_confezione": 0,
            "prezzo_singolo": 0,
            "gia_acquistato": False,
            "iva_pct": iva_pct,
            "ct_ble": ct_ble,
            "ct_strato": ct_strato,
            "fonte": fonte,
            "data_listino": "2026-01-01",
            "allergeni": allergeni,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            # Cerca per codice 2026, poi per codice 2025 (migrazione)
            esistente = None
            if codice_2026:
                esistente = await db.acquaviva_prodotti.find_one({"codice": codice_2026})
            if not esistente and codice_2025:
                esistente = await db.acquaviva_prodotti.find_one({"codice": codice_2025})
            if not esistente:
                esistente = await db.acquaviva_prodotti.find_one(
                    {"nome": {"$regex": nome[:15], "$options": "i"}}
                )

            if esistente:
                # Aggiorna — mantiene prezzo_vendita, foto_url esistenti
                update_set = {**campi_listino, "codice": codice_principale}
                await db.acquaviva_prodotti.update_one(
                    {"_id": esistente["_id"]}, {"$set": update_set}
                )
                aggiornati += 1
            else:
                # Inserisci nuovo
                doc = {
                    **campi_listino,
                    "codice": codice_principale,
                    "categoria": f"{categoria_aqv} | {categoria_vdm}",
                    "foto_url": "",
                    "ingredienti_str": "",
                    "descrizione": "",
                    "prezzo_acquisto_confezione": prezzo_ct,
                    "prezzo_vendita": 0,
                    "id": str(uuid.uuid4()),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                await db.acquaviva_prodotti.insert_one(doc)
                importati += 1
        except Exception as e:
            errori.append(f"{nome}: {str(e)[:80]}")

    return {
        "importati": importati,
        "aggiornati": aggiornati,
        "totale": importati + aggiornati,
        "errori": errori[:10],  # Mostra max 10 errori
    }


@router.post("/import-listino-pdf")
async def import_listino_da_pdf(file: UploadFile = File(...), _admin=Depends(require_admin)):
    """
    Parsa il listino Acquaviva 2026 in PDF e aggiorna i prezzi
    sui prodotti già presenti in acquaviva_prodotti.
    Matching per codice (codice_aqv_2026 o codice_aqv_2025).
    Non crea prodotti nuovi — aggiorna solo i 352 esistenti.
    """
    content = await file.read()
    prodotti = []

    try:
        import pdfplumber

        with pdfplumber.open(io.BytesIO(content)) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        if not row or len(row) < 9:
                            continue
                        # Colonne: [cod2025, cod2026, cat_aqv, cat_vdm, descrizione, g, qty_ct, um, prezzo_unit, €ct, iva, ...]
                        cod2025 = str(row[0] or "").strip()
                        cod2026 = str(row[1] or "").strip()
                        nome = str(row[4] or "").strip()
                        if not nome or cod2026 in ("CODICE AQV 2026", "CODICE\nAQV 2026", ""):
                            continue
                        if (
                            not cod2025.replace(" ", "").isdigit()
                            and not cod2026.replace(" ", "").isdigit()
                        ):
                            continue
                        try:
                            grammi = float(
                                re.sub(r"\s+", "", str(row[5] or "0")).replace(",", ".") or "0"
                            )
                            qty_cartone = float(
                                re.sub(r"\s+", "", str(row[6] or "1")).replace(",", ".") or "1"
                            )
                            um = str(row[7] or "PZ").strip().replace(" ", "") or "PZ"
                            prezzo_unit = float(
                                re.sub(r"\s+", "", str(row[8] or "0")).replace(",", ".") or "0"
                            )
                            prezzo_ct = float(
                                re.sub(r"\s+", "", str(row[9] or "0")).replace(",", ".") or "0"
                            )
                            iva = int(
                                float(
                                    re.sub(r"\s+", "", str(row[10] or "10")).replace(",", ".")
                                    or "10"
                                )
                            )
                        except (ValueError, TypeError, IndexError):
                            continue
                        if prezzo_unit <= 0 and prezzo_ct <= 0:
                            continue
                        prodotti.append(
                            {
                                "codice_aqv_2025": cod2025 or cod2026,
                                "codice_aqv_2026": cod2026 or cod2025,
                                "nome": nome,
                                "grammi": grammi,
                                "pz_confezione": int(qty_cartone) if qty_cartone >= 1 else 1,
                                "unita_misura": um,
                                "prezzo_acquisto_confezione": (
                                    prezzo_ct if prezzo_ct > 0 else prezzo_unit
                                ),
                                "prezzo_singolo": round(prezzo_unit, 4),
                                "iva_pct": iva,
                            }
                        )
    except ImportError as exc:
        raise HTTPException(500, "pdfplumber non disponibile. Contattare l'amministratore.") from exc

    if not prodotti:
        raise HTTPException(
            400, "Nessun prodotto estratto dal PDF. Verificare il formato del file."
        )

    aggiornati = 0
    non_trovati = []

    # Carica tutti i prodotti AQV dal DB in un colpo solo (evita N+1 query)
    tutti_prodotti = await db.acquaviva_prodotti.find(
        {}, {"_id": 0, "id": 1, "codice": 1, "codice_aqv_2026": 1, "codice_aqv_2025": 1}
    ).to_list(2000)

    # Costruisce lookup per cod2026 e cod2025
    lookup: dict = {}
    for p in tutti_prodotti:
        for campo in ("codice", "codice_aqv_2026", "codice_aqv_2025"):
            val = str(p.get(campo, "") or "").strip()
            if val:
                lookup[val] = p["id"]

    bulk_ops = []

    for prod in prodotti:
        cod2026 = prod.get("codice_aqv_2026", "")
        cod2025 = prod.get("codice_aqv_2025", "")
        pid = lookup.get(cod2026) or lookup.get(cod2025)
        if pid:
            bulk_ops.append(
                UpdateOne(
                    {"id": pid},
                    {
                        "$set": {
                            "prezzo_acquisto_confezione": prod["prezzo_acquisto_confezione"],
                            "prezzo_singolo": prod["prezzo_singolo"],
                            "prezzo_ct": prod["prezzo_acquisto_confezione"],
                            "codice_aqv_2026": cod2026,
                            "codice_aqv_2025": cod2025,
                            "iva_pct": prod["iva_pct"],
                            "grammi": prod["grammi"],
                            "pz_confezione": prod["pz_confezione"],
                            "data_listino": "2026-01-01",
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                        }
                    },
                )
            )
            aggiornati += 1
        else:
            non_trovati.append(f"{cod2026 or cod2025} — {prod['nome'][:40]}")

    if bulk_ops:
        await db.acquaviva_prodotti.bulk_write(bulk_ops, ordered=False)

    return {
        "estratti_da_pdf": len(prodotti),
        "aggiornati_nel_db": aggiornati,
        "non_trovati_nel_db": len(non_trovati),
        "esempi_non_trovati": non_trovati[:10],
    }


@router.post("/import-ingredienti-pdf")
async def import_ingredienti_da_pdf(
    file: UploadFile = File(...), _admin=Depends(require_admin)
):
    """Importa la lista ingredienti ufficiale AQV/VDM per codice esatto.

    Non crea prodotti e non usa il nome per il matching. Il report espone ogni
    codice assente o ambiguo, cosi' l'operatore puo' verificarlo senza perdita
    di informazione.
    """
    content = await file.read()
    if not content.startswith(b"%PDF"):
        raise HTTPException(400, "Il file caricato non e' un PDF valido")
    righe = _parse_lista_ingredienti_pdf(content)
    if not righe:
        raise HTTPException(400, "Nessuna riga ingredienti trovata nel PDF")
    return await _applica_lista_ingredienti(righe, file.filename or "lista_ingredienti.pdf")


@router.get("/cartelli-bar")
async def get_cartelli_bar(
    search: Optional[str] = Query(None),
    solo_in_ricette: bool = Query(False),
):
    """Prodotti con ingredienti verificabili pronti per i cartelli del bar."""
    query = {
        "fonte": {"$in": ["acquaviva", "vandemoortele"]},
        "ingredienti_str": {"$nin": [None, ""]},
    }
    if search:
        query["$or"] = [
            {"nome": {"$regex": re.escape(search), "$options": "i"}},
            {"codice": {"$regex": re.escape(search), "$options": "i"}},
            {"codice_aqv_2026": {"$regex": re.escape(search), "$options": "i"}},
        ]
    prodotti = await db.acquaviva_prodotti.find(query, {"_id": 0}).sort("nome", 1).to_list(5000)
    ids = [p.get("id") for p in prodotti if p.get("id")]
    attivi = set()
    if ids:
        usati = await db.dizionario_prodotti.find(
            {"id": {"$in": ids}, "attivo": {"$ne": False}}, {"_id": 0, "id": 1}
        ).to_list(5000)
        attivi = {p.get("id") for p in usati}
    risultato = []
    for prodotto in prodotti:
        in_ricette = prodotto.get("id") in attivi
        if solo_in_ricette and not in_ricette:
            continue
        risultato.append({
            "id": prodotto.get("id"),
            "codice": prodotto.get("codice_aqv_2026") or prodotto.get("codice")
                      or prodotto.get("codice_articolo"),
            "nome": prodotto.get("nome"),
            "foto_url": prodotto.get("foto_url") or prodotto.get("immagine_url"),
            "ingredienti": prodotto.get("ingredienti_str"),
            "allergeni": prodotto.get("allergeni") or [],
            "in_ricette": in_ricette,
            "fonte": prodotto.get("fonte"),
        })
    return {"prodotti": risultato, "totale": len(risultato)}


@router.put("/prodotti/{prodotto_id}/prezzo")
async def set_prezzi_prodotto(
    prodotto_id: str,
    prezzo_vendita: Optional[float] = Query(None),
    prezzo_acquisto_confezione: Optional[float] = Query(None),
    pz_confezione: Optional[float] = Query(None), _admin=Depends(require_admin),
):
    """Aggiorna prezzi e pezzi per confezione di un prodotto semilavorato."""
    upd = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if prezzo_vendita is not None:
        upd["prezzo_vendita"] = prezzo_vendita
    if prezzo_acquisto_confezione is not None:
        upd["prezzo_acquisto_confezione"] = prezzo_acquisto_confezione
        # Ricalcola prezzo singolo
        prod = await db.acquaviva_prodotti.find_one({"id": prodotto_id})
        pz = pz_confezione or (prod.get("pz_confezione") if prod else 1) or 1
        upd["prezzo_singolo"] = round(prezzo_acquisto_confezione / pz, 4) if pz > 0 else 0
    if pz_confezione is not None:
        upd["pz_confezione"] = pz_confezione
    if not upd:
        return {"ok": False, "msg": "Nessun valore da aggiornare"}
    await db.acquaviva_prodotti.update_one({"id": prodotto_id}, {"$set": upd})
    return {"ok": True}


@router.get("/acquistati-da-fatture")
async def get_prodotti_acquistati_da_fatture():
    """
    Restituisce i prodotti Acquaviva/Vandemoortele effettivamente acquistati
    (trovati nelle fatture XML), non tutto il catalogo.
    Restituisce descrizione fattura + pz_cartone + peso_g + costo_pezzo + info prodotto_vendita (se linkato).
    """
    import re

    # Tutti i prodotti dalle fatture Vandemoortele
    fatture = await db.fatture.find(
        {"fornitore": {"$regex": "vandemoortele", "$options": "i"}},
        {"_id": 0, "prodotti": 1, "data_fattura": 1},
    ).to_list(200)

    # Aggrega per descrizione
    per_desc = {}
    for fat in fatture:
        for p in fat.get("prodotti", []):
            desc = p.get("descrizione", "").strip()
            qty = float(p.get("quantita", 0) or 0)
            prezzo = float(p.get("prezzo", 0) or 0)
            if not desc or qty <= 0:
                continue
            m_peso = re.search(r"(\d+\.?\d*)\s*G\b", desc.upper())
            peso_g = float(m_peso.group(1)) if m_peso else None
            m_kg = re.search(r"(\d+\.?\d*)\s*KG", desc.upper())
            kg_cart = float(m_kg.group(1)) if m_kg else None
            pz_cart = round(kg_cart * 1000 / peso_g) if kg_cart and peso_g and peso_g > 0 else None
            if desc not in per_desc:
                per_desc[desc] = {
                    "descrizione": desc,
                    "cartoni_totali": 0,
                    "peso_g": peso_g,
                    "pz_cartone": pz_cart,
                    "prezzo_cartone": prezzo,
                    "costo_pezzo": round(prezzo / pz_cart, 4) if pz_cart and prezzo > 0 else 0,
                }
            per_desc[desc]["cartoni_totali"] += qty

    # Cerca match in prodotti_vendita (per nome parziale)
    pv_acq = await db.prodotti_vendita.find(
        {"fonte": "acquaviva"},
        {
            "_id": 0,
            "id": 1,
            "nome": 1,
            "prezzo_vendita": 1,
            "costo_produzione": 1,
            "margine_percentuale": 1,
            "pezzi_cartone": 1,
            "peso_pezzo_g": 1,
            "immagine_url": 1,
            "categoria": 1,
            "attivo": 1,
        },
    ).to_list(500)

    # Crea mappa nome_semplice → prodotto_vendita
    pv_map = {}
    for pv in pv_acq:
        chiave = pv["nome"].lower().replace(" ", "")[:10]
        pv_map[chiave] = pv

    risultati = []
    pv_usati = set()  # evita duplicati nella lista risultati
    for desc, info in sorted(per_desc.items(), key=lambda x: -x[1]["cartoni_totali"]):
        # Cerca match prodotto_vendita per parole chiave (non già usato)
        match_pv = None
        desc_upper = desc.upper()
        for pv in pv_acq:
            if pv["id"] in pv_usati:
                continue
            nome_low = pv["nome"].lower()
            nome_words = [w for w in nome_low.split() if len(w) > 3]
            # Calcola quante parole del nome_pv appaiono nella descrizione fattura
            hits = sum(1 for w in nome_words if w.upper() in desc_upper or w in desc_upper.lower())
            if hits >= min(2, len(nome_words)):
                match_pv = pv
                pv_usati.add(pv["id"])
                break

        row = {
            "id": match_pv["id"] if match_pv else None,
            "nome": match_pv["nome"] if match_pv else desc,
            "descrizione_fattura": desc,
            "cartoni_totali": info["cartoni_totali"],
            "peso_g": info["peso_g"],
            "pz_cartone": match_pv.get("pezzi_cartone") if match_pv else info["pz_cartone"],
            "prezzo_cartone": info["prezzo_cartone"],
            "costo_pezzo": (
                match_pv.get("costo_produzione")
                if match_pv and match_pv.get("costo_produzione")
                else info["costo_pezzo"]
            ),
            "prezzo_vendita": match_pv.get("prezzo_vendita", 0) if match_pv else 0,
            "margine_pct": match_pv.get("margine_percentuale", 0) if match_pv else 0,
            "immagine_url": match_pv.get("immagine_url") if match_pv else None,
            "categoria": match_pv.get("categoria", "") if match_pv else "",
            "attivo": match_pv.get("attivo", True) if match_pv else True,
            "in_prodotti_vendita": match_pv is not None,
            "fonte": "acquaviva",
        }
        risultati.append(row)

    return {
        "totale": len(risultati),
        "con_prezzo": sum(1 for r in risultati if (r.get("prezzo_vendita") or 0) > 0),
        "prodotti": risultati,
    }


# ── Fuzzy match nome banco ↔ descrizione fattura (condiviso col check colazione) ──
_MAPPING_NOMI_BANCO = {
    "baby": ["baby"], "tappo": ["tappi"], "tappi": ["tappi"],
    "sfogliatella napoletana": ["napoletan"], "sfogliatella frolla": ["frolla"],
    "coda": ["coda"], "calise": ["cali stra"],
    "integrale miele": ["whml", "mltcer honey"], "multicereali": ["mltcer"],
    "frutti di bosco": ["mltcer ber", "fdb"], "ciambella": ["cmbll"],
    "arancia": ["orange"], "melagrana": ["pom"], "pistacchi": ["pstch"],
    "cannella": ["cin crm"], "mandorle": ["almonds", "doram"],
    "doramì": ["doram"], "dorama": ["doram"], "vegano": ["vgn"], "black": ["black"],
}


def _match_desc_banco(nome_banco: str, desc_fattura: str) -> bool:
    """True se il nome-prodotto del banco corrisponde alla descrizione di
    fattura Vandemoortele (mapping sigle + fallback token comuni)."""
    nome_lower = (nome_banco or "").lower()
    desc_lower = (desc_fattura or "").lower()
    for kw_nome, kw_lista_fattura in _MAPPING_NOMI_BANCO.items():
        if kw_nome in nome_lower:
            for kw_f in kw_lista_fattura:
                if kw_f in desc_lower:
                    return True
    token_desc = set(desc_lower.split()[:5])
    token_nome = set(nome_lower.split()[:5])
    return len(token_desc & token_nome) >= 2


async def calcola_magazzino_congelatore():
    """
    Calcola il magazzino semilavorati (Acquaviva/Vandemoortele) in congelatore.
    Funzione RIUSABILE (02/07/2026): la usa l'endpoint sotto e il check
    "sta per finire" della colazione (colazione.py) per far partire i
    riordini verso la sezione ordini centralizzata.

    Formula reale:
    - ENTRATE  = cartoni acquistati dalle fatture Vandemoortele × pezzi per cartone
                 (il n. pezzi per cartone si ricava da: peso_cartone_kg / peso_pezzo_g)
    - USCITE   = pezzi portati al banco ogni giorno (vendite_banco fonte=colazione, pezzi_prodotti)
    - Gli invenduti NON rientrano in congelatore (vengono scartati/consumati)
    - SALDO CONGELATORE = ENTRATE - USCITE

    Restituisce:
    - Totale pezzi in congelatore (entrate - uscite) per prodotto
    - Lista dettagliata per prodotto Vandemoortele
    """
    from datetime import datetime, timezone
    import re

    anno = datetime.now(timezone.utc).year
    data_inizio_anno = f"{anno}-01-01"

    # ── 1. ENTRATE: solo dalle ultime 2 fatture Vandemoortele ──────────────────
    # Le fatture precedenti sono già state consumate completamente.
    # Solo i cartoni delle ultime 2 consegne sono fisicamente ancora in congelatore.
    tutte_fatture = (
        await db.fatture.find(
            {"fornitore": {"$regex": "vandemoortele", "$options": "i"}},
            {"_id": 0, "prodotti": 1, "data_fattura": 1, "numero_fattura": 1},
        )
        .to_list(200)
    )

    # Ordino per data VERA (data_fattura è a formato misto dd/mm/yyyy + ISO): un
    # sort lessicografico faceva passare "31/12/2024" davanti a "2026-07-01" e le
    # "ultime 2 fatture" per la giacenza congelatore erano quelle sbagliate.
    from app.lotti.routers.utils import parse_data_flessibile
    tutte_fatture.sort(
        key=lambda f: parse_data_flessibile(f.get("data_fattura")) or date(1900, 1, 1),
        reverse=True,
    )
    # Prendo solo le ultime 2
    fatture = tutte_fatture[:2]

    # Aggrega cartoni per descrizione
    entrate_desc = {}  # desc → {cartoni, peso_g, kg_cartone, prezzo_cartone}
    for fat in fatture:
        for p in fat.get("prodotti", []):
            desc = p.get("descrizione", "").strip()
            qty = float(p.get("quantita", 0) or 0)
            prezzo = float(p.get("prezzo", 0) or 0)
            if not desc or qty <= 0:
                continue

            # Estrai peso pezzo (es. 35G, 80G, 100G) dalla descrizione
            m_peso = re.search(r"(\d+\.?\d*)\s*G\b", desc.upper())
            peso_g = float(m_peso.group(1)) if m_peso else None

            # Estrai peso cartone in KG — prende l'ULTIMO valore KG plausibile (< 50kg)
            # Gestisce errori come "494KG" (ocr/typo di 4.94KG) e "3,84KG" (virgola)
            m_kg_all = re.findall(r"([\d]+[.,]?[\d]*)\s*KG", desc.upper())
            kg_cart = None
            for val in reversed(m_kg_all):
                v = float(val.replace(",", "."))
                if 0.5 < v < 50:  # peso cartone realistico tra 0.5 e 50 kg
                    kg_cart = v
                    break
            # Se ancora None, prova a correggere valori anomali come 494 → 4.94
            if kg_cart is None and m_kg_all:
                v = float(m_kg_all[-1].replace(",", "."))
                if v > 50:
                    kg_cart = round(v / 100, 2)

            # Calcola pezzi per cartone
            pz_cart = round(kg_cart * 1000 / peso_g) if kg_cart and peso_g and peso_g > 0 else None

            if desc not in entrate_desc:
                entrate_desc[desc] = {
                    "cartoni": 0,
                    "peso_g": peso_g,
                    "kg_cartone": kg_cart,
                    "pz_cartone": pz_cart,
                    "prezzo_cartone": prezzo,
                    "pz_totali": 0,
                }
            entrate_desc[desc]["cartoni"] += qty
            if pz_cart:
                entrate_desc[desc]["pz_totali"] += int(qty * pz_cart)

    # ── 2. USCITE: pezzi portati al banco dalla data della penultima fattura ────
    # Solo le uscite successive alla consegna più vecchia tra le 2 in congelatore
    # vendite_banco.data è ISO (YYYY-MM-DD): la data della fattura va portata in
    # ISO prima del confronto $gte, altrimenti "05/07/2026" vs "2026-07-05" è un
    # confronto tra stringhe di formati diversi → giacenza congelatore sballata.
    _dmin = parse_data_flessibile(fatture[-1]["data_fattura"]) if fatture else None
    data_min_fattura = _dmin.strftime("%Y-%m-%d") if _dmin else data_inizio_anno
    uscite = await db.vendite_banco.aggregate(
        [
            {"$match": {"fonte": "colazione", "data": {"$gte": data_min_fattura}}},
            {"$group": {"_id": "$prodotto_nome", "pezzi_usciti": {"$sum": "$pezzi_prodotti"}}},
        ]
    ).to_list(500)

    # Somma totale uscite
    totale_uscite = sum(u["pezzi_usciti"] for u in uscite)
    uscite_per_nome = {u["_id"]: u["pezzi_usciti"] for u in uscite}

    # ── 3. Costruisci risposta per prodotto ──────────────────────────────────
    totale_entrate = sum(e["pz_totali"] for e in entrate_desc.values())
    saldo_congelatore = max(0, totale_entrate - totale_uscite)

    prodotti_result = []
    for desc, info in sorted(entrate_desc.items(), key=lambda x: -x[1]["pz_totali"]):
        pezzi_entrati = info["pz_totali"]
        pz_cart = info.get("pz_cartone")

        pezzi_usciti_prod = 0
        for nome_uscita, pz_usciti in uscite_per_nome.items():
            if _match_desc_banco(nome_uscita, desc):
                pezzi_usciti_prod += pz_usciti

        saldo_prod = max(0, pezzi_entrati - pezzi_usciti_prod)

        prodotti_result.append(
            {
                "descrizione_fattura": desc,
                "cartoni_acquistati": info["cartoni"],
                "pz_cartone": pz_cart,
                "peso_g": info.get("peso_g"),
                "pezzi_entrati": pezzi_entrati,
                "pezzi_usciti": pezzi_usciti_prod,
                "saldo": saldo_prod,
                "prezzo_cartone": info.get("prezzo_cartone", 0),
                "costo_pezzo": round(info.get("prezzo_cartone", 0) / pz_cart, 4) if pz_cart else 0,
            }
        )

    return {
        "anno": anno,
        "data_inizio": data_inizio_anno,
        "num_fatture_vandemoortele": len(fatture),
        "fatture_in_congelatore": [
            {"numero": f.get("numero_fattura"), "data": f.get("data_fattura")} for f in fatture
        ],
        "totale_pezzi_entrati": totale_entrate,
        "totale_pezzi_usciti": totale_uscite,
        "saldo_congelatore": saldo_congelatore,
        "num_referenze": len(prodotti_result),
        # Riepilogo uscite per nome prodotto (dai vendite_banco)
        "uscite_per_prodotto": [
            {"nome": k, "pezzi": v} for k, v in sorted(uscite_per_nome.items(), key=lambda x: -x[1])
        ],
        "prodotti": prodotti_result,
    }


@router.get("/magazzino-congelatore")
async def get_magazzino_congelatore():
    """Endpoint: delega al calcolo riusabile (vedi calcola_magazzino_congelatore)."""
    return await calcola_magazzino_congelatore()


@router.post("/sync-prezzi")
async def sync_prezzi_da_fatture(fonte: Optional[str] = Query(None), _admin=Depends(require_admin)):
    """
    Sincronizza i prezzi di acquisto per tutti i prodotti semilavorati
    cercando nelle fatture dei fornitori (Acquaviva, Vandemoortele, Alpha).
    Restituisce quanti prodotti sono stati aggiornati con un prezzo trovato.
    """
    return await _sync_prezzi_core(fonte=fonte)


async def _sync_prezzi_core(fonte: Optional[str] = None) -> dict:
    """Logica effettiva sync prezzi — chiamabile da pipeline e da HTTP."""

    query_prod = {}
    if fonte:
        query_prod["fonte"] = fonte
    else:
        query_prod["fonte"] = {"$in": ["acquaviva", "vandemoortele", "alpha"]}

    prodotti = await db.acquaviva_prodotti.find(query_prod, {"_id": 0}).to_list(2000)

    # Carica tutte le righe prodotto dalle fatture Acquaviva/Vandemoortele/Alpha
    fatture_semi = await db.fatture.find(
        {"fornitore": {"$regex": "acquaviva|vandemoortele|alpha|progetto", "$options": "i"}},
        {"prodotti": 1, "fornitore": 1, "data_fattura": 1, "_id": 0},
    ).to_list(1000)

    # Costruisci mappa: nome_lower -> {prezzo, quantita}
    prezzi_map: dict = {}
    for f in fatture_semi:
        for p in f.get("prodotti") or []:
            desc = (p.get("descrizione") or "").strip()
            if not desc:
                continue
            key = desc.lower()
            prezzo = float(p.get("prezzo") or 0)
            if prezzo > 0 and key not in prezzi_map:
                prezzi_map[key] = {
                    "prezzo": prezzo,
                    "quantita": float(p.get("quantita") or 1),
                    "fornitore": f.get("fornitore", ""),
                }

    def _match(nome: str) -> dict:
        nk = nome.lower().strip()
        if nk in prezzi_map:
            return prezzi_map[nk]
        # Primo token significativo (10+ chars)
        for dk, dv in prezzi_map.items():
            if len(nk) >= 6 and nk[:10] in dk:
                return dv
            if len(dk) >= 6 and dk[:10] in nk:
                return dv
        return {}

    aggiornati = 0
    non_trovati = 0
    for prod in prodotti:
        match = _match(prod.get("nome", ""))
        if not match:
            non_trovati += 1
            continue
        prezzo_fatt = match["prezzo"]
        pz = float(prod.get("pz_confezione") or match.get("quantita") or 1)

        # Per prodotti Alpha (Progetto Alpha S.R.L.S): il prezzo in fattura è già per pezzo
        # Per Acquaviva/Vandemoortele: il prezzo è per confezione → dividi per pz
        if prod.get("fonte") == "alpha":
            prezzo_sing = prezzo_fatt  # già prezzo al pezzo
            prezzo_conf = round(prezzo_fatt * pz, 4)
        else:
            prezzo_conf = prezzo_fatt
            prezzo_sing = round(prezzo_fatt / pz, 4) if pz > 0 else 0

        await db.acquaviva_prodotti.update_one(
            {"id": prod["id"]},
            {
                "$set": {
                    "prezzo_acquisto_confezione": prezzo_conf,
                    "prezzo_singolo": prezzo_sing,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            },
        )
        aggiornati += 1

    return {"aggiornati": aggiornati, "non_trovati": non_trovati, "totale": len(prodotti)}


@router.post("/import-alpha")
async def import_alpha_da_xml(payload: dict, _admin=Depends(require_admin)):
    """
    Importa prodotti PROGETTO ALPHA direttamente da file XML p7m.
    Riceve lista prodotti già parsati e crea i record nel catalogo.
    """
    prodotti_raw = payload.get("prodotti", [])
    if not prodotti_raw:
        return {"importati": 0, "msg": "Nessun prodotto fornito"}

    importati = 0
    aggiornati = 0
    for p in prodotti_raw:
        nome = (p.get("nome") or "").strip()
        if not nome:
            continue
        prezzo_unit = float(p.get("prezzo_unitario") or 0)
        qty = float(p.get("quantita") or 1)
        allergeni = rileva_allergeni(nome=nome, descrizione=p.get("descrizione") or "")

        doc = {
            "nome": nome,
            "categoria": "Senza Glutine",
            "grammi": 0,
            "pz_confezione": qty,
            "foto_url": "",
            "ingredienti_str": "",
            "descrizione": p.get("descrizione") or "",
            "allergeni": allergeni,
            "prezzo_acquisto_confezione": round(prezzo_unit * qty, 4),
            "prezzo_singolo": prezzo_unit,
            "prezzo_vendita": 0,
            "fonte": "alpha",
            "codice": f"ALPHA-{nome[:20].replace(' ','-').upper()}",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        esistente = await db.acquaviva_prodotti.find_one({"nome": nome, "fonte": "alpha"})
        if esistente:
            await db.acquaviva_prodotti.update_one({"nome": nome, "fonte": "alpha"}, {"$set": doc})
            aggiornati += 1
        else:
            doc["id"] = str(uuid.uuid4())
            doc["created_at"] = datetime.now(timezone.utc).isoformat()
            await db.acquaviva_prodotti.insert_one(doc)
            importati += 1

    return {"importati": importati, "aggiornati": aggiornati, "totale": importati + aggiornati}
