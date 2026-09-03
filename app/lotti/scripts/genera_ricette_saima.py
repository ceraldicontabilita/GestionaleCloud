"""Genera il bundle operativo dei ricettari SAIMA ufficiali.

Il comando legge i PDF gia scaricati in ``tmp/pdfs/saima`` e produce:

* ``backend/data/ricette_saima.json`` con testi, dosi e provenienza;
* ``frontend/public/saima/ricette/*.webp`` con la foto della singola ricetta.

Non inventa dosi o rese. Le righe non interpretabili restano nel testo fonte e
la resa viene marcata come da impostare nell'applicazione.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import pdfplumber
from PIL import Image
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[2]
PDF_DIR = ROOT / "tmp" / "pdfs" / "saima"
OUT_JSON = ROOT / "backend" / "data" / "ricette_saima.json"
OUT_IMAGES = ROOT / "frontend" / "public" / "saima" / "ricette"


def _slug(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:96]


def _clean(value: str) -> str:
    text = re.sub(r"-\s*\n\s*", "", value or "")
    return "\n".join(" ".join(line.split()) for line in text.splitlines() if line.strip())


def _title_from_text(text: str, book_name: str) -> str:
    before = re.split(r"\bINGREDIENTI\b", text or "", maxsplit=1, flags=re.I)[0]
    lines = [" ".join(x.split()).strip(" -") for x in before.splitlines() if x.strip()]
    ignored = {"ricettario", "applicazioni prodotto", book_name.lower()}
    candidates = [x for x in lines if len(x) > 2 and x.lower() not in ignored]
    return candidates[-1] if candidates else ""


QTY_RX = re.compile(
    r"^(?P<nome>.+?)\s+(?P<qta>\d+(?:[.,]\d+)?(?:\s*[-/]\s*\d+(?:[.,]\d+)?)?)\s*"
    r"(?P<unita>kg|g|gr|mg|l|lt|ml|cl|pz|pezzi|n°|n)\b\.?(?:\s+\d+(?:[.,]\d+)?\s*%)?",
    flags=re.I,
)
QB_RX = re.compile(r"^(?P<nome>.+?)\s+q\.?\s*b\.?$", flags=re.I)
_NOT_AN_INGREDIENT = re.compile(
    r"^(?:per\s+\d|totale\b|resa\b|utilizzare\b|modalit|procedimento|preparazione|cottura|temperatura|ricettario|pagina\b)"
    r"|\b(?:impastare|aggiungere|cuocere|lasciare|raschiare|incorporare|infornare|ottenere|ottengono|velocit[àa])\b",
    flags=re.I,
)
_INVALID_TITLE = re.compile(
    r"\b(?:ingredienti|procedimento|impastare|utilizzare|montare)\b"
    r"|iinn|pprrooc|^o\s+uvetta$|panettone con preimpasto pandoro con preimpasto",
    flags=re.I,
)


def _parse_ingredients(text: str, *, allow_quantityless: bool = False) -> list[dict]:
    rows: list[dict] = []
    section = ""
    for raw in (text or "").splitlines():
        line = " ".join(raw.split()).strip(" •·-")
        if not line or line.upper() == "INGREDIENTI":
            continue
        match = QTY_RX.match(line)
        if not match:
            qb_match = QB_RX.match(line)
            if qb_match and not _NOT_AN_INGREDIENT.search(qb_match.group("nome")):
                rows.append({"nome": qb_match.group("nome").strip(), "quantita": 0, "quantita_testo": "q.b.", "unita_misura": "q.b.", "sezione": section})
                continue
            # Le intestazioni (Farcitura, Glassa...) vengono conservate come
            # sezione, non trasformate in un ingrediente inesistente.
            if len(line.split()) <= 4 and not any(ch.isdigit() for ch in line):
                if allow_quantityless and not _NOT_AN_INGREDIENT.search(line):
                    rows.append({"nome": line, "quantita": 0, "unita_misura": "", "sezione": section})
                    continue
                section = line
            continue
        if _NOT_AN_INGREDIENT.search(match.group("nome")):
            continue
        unit = match.group("unita").lower().rstrip(".")
        unit = {"gr": "g", "lt": "l", "pezzi": "pz", "n": "pz", "n°": "pz"}.get(unit, unit)
        qty_raw = match.group("qta").replace(",", ".")
        qty_match = re.match(r"\d+(?:\.\d+)?", qty_raw)
        qty_number = qty_match.group(0) if qty_match else "0"
        # Nei ricettari italiani il punto separa spesso le migliaia:
        # ``1.300 g`` significa 1300 g, non 1,3 g.
        if unit in {"g", "mg"} and re.fullmatch(r"\d{1,3}\.\d{3}", qty_number):
            qty_number = qty_number.replace(".", "")
        qty = float(qty_number)
        rows.append(
            {
                "nome": match.group("nome").strip(),
                "quantita": qty,
                "quantita_testo": qty_raw,
                "unita_misura": unit,
                "sezione": section,
            }
        )
    return rows


def _department(title: str, procedure: str) -> str:
    text = f"{title} {procedure}".lower()
    savory = (
        "pane", "pizza", "focacc", "scrocchiarella", "pancampagna", "waldkorn",
        "sandwich", "panino", "salato", "rustico", "grissin", "cracker",
    )
    return "rosticceria" if any(word in text for word in savory) else "pasticceria"


def _recipe_crops(page) -> tuple[str, str]:
    verticals = [
        line for line in page.lines
        if abs(float(line.get("x1", 0)) - float(line.get("x0", 0))) < 1
        and float(line.get("height", 0)) > page.height * 0.25
    ]
    if verticals:
        divider = max(verticals, key=lambda x: float(x.get("height", 0)))
        x = float(divider["x0"])
        top = max(0.0, float(divider.get("top", 0)))
        left = page.crop((0, top, max(1, x - 2), page.height)).extract_text() or ""
        right = page.crop((min(page.width - 1, x + 2), top, page.width, page.height)).extract_text() or ""
        return _clean(left), _clean(right)

    full = _clean(page.extract_text() or "")
    if "INGREDIENTI" not in full.upper():
        return "", ""
    tail = re.split(r"\bINGREDIENTI\b", full, maxsplit=1, flags=re.I)[1]
    parts = re.split(r"\b(?:PROCEDIMENTO|PREPARAZIONE)\b", tail, maxsplit=1, flags=re.I)
    return _clean(parts[0]), _clean(parts[1] if len(parts) > 1 else "")


def _extract_image(reader: PdfReader, page_index: int, destination: Path) -> str:
    try:
        images = list(reader.pages[page_index].images)
        if not images:
            return ""
        source = max(images, key=lambda item: item.image.width * item.image.height).image.convert("RGB")
        source.thumbnail((1000, 760), Image.Resampling.LANCZOS)
        destination.parent.mkdir(parents=True, exist_ok=True)
        source.save(destination, "WEBP", quality=82, method=6)
        return f"/saima/ricette/{destination.name}"
    except Exception:
        return ""


MANUAL_IMAGE_ONLY = [
    {
        "nome": "Crema e amarena",
        "pagina": 2,
        "ingredienti": "Crema pasticcera Saima in sac a poche\nCannolini wafer medi Bussy\nAmarena intera tantofrutto cal. 16/18 Giuso\nTopping Amarena Giuso\nPasta vaniglia Madagascar Superpremium Giuso",
        "procedimento": "Aromatizzare la crema pasticcera con la pasta vaniglia (15 g per kg di crema). Farcire i cannolini di wafer e adagiarli su un piatto precedentemente decorato con il topping all'amarena. Infine guarnire con le amarene intere.",
        "crop": (0.31, 0.00, 1.00, 0.37),
    },
    {
        "nome": "Parfait ai profumi d'estate",
        "pagina": 2,
        "ingredienti": "Parfait Debic\nRollè di pan di Spagna\nCreme Fredde Giuso (amarena, mango, fragola, limone)\nAroma alcolico vaniglia Valbruna\nCrispearls cioccolato bianco Callebaut",
        "procedimento": "Adagiare uno strato di crispearls sul fondo del bicchiere e ricoprire con il parfait precedentemente montato. Inserire il disco di pan di Spagna bagnato nell'aroma alla vaniglia e ricoperto con crema fredda. Completare con parfait e crema fredda e decorare a piacere.",
        "crop": (0.00, 0.55, 0.58, 1.00),
    },
    {
        "nome": "Tre cioccolati",
        "pagina": 3,
        "ingredienti": "Mousse cioccolato fondente Callebaut\nMousse cioccolato al latte Callebaut\nMousse cioccolato bianco Callebaut\nGlassa Splendidee cioccolato Giuso\nCrispearls Callebaut",
        "procedimento": "Montare per 5 minuti le mousse separatamente, miscelando il contenuto di ogni busta con 1 litro di latte freddo. Alternare i tre strati, lasciare raffreddare e ricoprire con la glassa al cioccolato. Decorare con i crispearls.",
        "crop": (0.00, 0.00, 0.58, 0.35),
    },
    {
        "nome": "Pompon alla vaniglia",
        "pagina": 3,
        "ingredienti": "Savarin grandi\nParfait Debic\nPasta Vaniglia Madagascar Superpremium Giuso\nAroma alcolico vaniglia Valbruna\nVariegato tuttobosco Giuso",
        "procedimento": "Immergere il savarin nella bagna alla vaniglia naturale. Montare il parfait aromatizzato con la pasta Madagascar. Guarnire il savarin, adagiato su un fondo di variegato tuttobosco, con il sac a poche.",
        "crop": (0.00, 0.60, 0.62, 1.00),
    },
    {
        "nome": "Millefoglie scomposta",
        "pagina": 4,
        "ingredienti": "Pasta sfoglia\nCrema pasticcera Saima in sac a poche\nAmarena intera tantofrutto cal. 16/18 Giuso\nTopping Amarena Giuso\nCrispearls cioccolato fondente Callebaut",
        "procedimento": "Cuocere la pasta sfoglia. Spezzettarla e disporla nei piattini decorati con topping amarena. Ricoprire con crema pasticcera e crispearls fondenti, completare con altra sfoglia e decorare con amarene e zucchero a velo.",
        "crop": (0.10, 0.00, 0.93, 0.40),
    },
]


MANUAL_SCROCCHIARELLA = [
    {
        "nome": "Scrocchiarella Classica pomodoro e mozzarella",
        "pagina": 4,
        "ingredienti": "Pomodori tondi a fette\nMozzarella a fette (bocconcini o fior di latte)\nPomodorini pachino gialli e rossi\nSale\nOlio\nOrigano\nBasilico",
        "procedimento": "Cuocere la Scrocchiarella su griglia o teglia forata per 8-10 minuti a 230/240 °C. Terminata la cottura, farcire alternando pomodori e mozzarella, aggiungere i pomodorini e condire con sale, olio, origano e basilico.",
        "crop": (0.00, 0.00, 1.00, 0.55),
    },
    {
        "nome": "Scrocchiarella Riso Venere zucchine e gamberetti",
        "pagina": 4,
        "ingredienti": "Zucchine a listarelle\nGamberetti\nScamorza a fette\nSale\nOlio\nBasilico",
        "procedimento": "Farcire con la scamorza e cuocere a 230/240 °C. A metà cottura aggiungere zucchine e gamberetti, completare la cottura e condire con sale e olio.",
        "crop": (0.00, 0.45, 1.00, 1.00),
    },
    {
        "nome": "Scrocchiarella Classica Margherita",
        "pagina": 5,
        "ingredienti": "Salsa di pomodoro\nMozzarella a fette (bocconcini o fior di latte)\nParmigiano grattugiato\nBasilico\nSale\nOlio",
        "procedimento": "Farcire con pomodoro e mozzarella, condire e cuocere su griglia o teglia forata per 8-10 minuti a 230/240 °C. Completare con parmigiano, olio e basilico.",
        "crop": (0.00, 0.00, 1.00, 0.55),
    },
    {
        "nome": "Scrocchiarella Sandwich mortadella, bufala e pistacchio",
        "pagina": 5,
        "ingredienti": "Mortadella a fette\nStraccetti di bufala\nCrema Pistacchio\nCrema 7chef Bufalina\nGranella di Pistacchio\nSale\nOlio",
        "procedimento": "Cuocere la Scrocchiarella su griglia o teglia forata per 8-10 minuti a 230/240 °C e farcire con gli ingredienti indicati nel ricettario ufficiale.",
        "crop": (0.00, 0.45, 1.00, 1.00),
    },
    {
        "nome": "Scrocchiarella Classica ortolana",
        "pagina": 6,
        "ingredienti": "Scamorza a fette\nPeperoni\nZucchine\nOlive\nPomodorini gialli e rossi\nScaglie di parmigiano\nSale\nOlio",
        "procedimento": "Farcire con scamorza e verdure, cuocere per 8-10 minuti a 230/240 °C e completare con scaglie di parmigiano e olio.",
        "crop": (0.00, 0.00, 1.00, 0.55),
    },
    {
        "nome": "Scrocchiarella Classica patate e salsiccia",
        "pagina": 6,
        "ingredienti": "Mozzarella a fette (bocconcini o fior di latte)\nPatate al forno\nSalsiccia precedentemente cotta\nSale\nOlio",
        "procedimento": "Farcire con mozzarella, salsiccia e patate e completare la cottura su griglia o teglia forata per 8-10 minuti a 230/240 °C.",
        "crop": (0.00, 0.45, 1.00, 1.00),
    },
    {
        "nome": "Scrocchiarella Riso Venere prosciutto crudo e mozzarella",
        "pagina": 7,
        "ingredienti": "Prosciutto crudo a fette\nMozzarella di bufala a fette\nScaglie di parmigiano\nLattughino o rucola\nSale\nOlio",
        "procedimento": "Cuocere la Scrocchiarella per 8-10 minuti a 230/240 °C. Farcire con prosciutto crudo, mozzarella, parmigiano e lattughino, quindi condire con sale e olio.",
        "crop": (0.00, 0.00, 1.00, 0.55),
    },
    {
        "nome": "Scrocchiarella Riso Venere salmone e stracchino",
        "pagina": 7,
        "ingredienti": "Salmone affumicato\nCrema 7chef stracchino\nErbette di stagione\nBuccia di limone\nSale\nOlio",
        "procedimento": "Cuocere la Scrocchiarella per 8-10 minuti a 230/240 °C e completare con gli ingredienti indicati nel ricettario ufficiale.",
        "crop": (0.00, 0.45, 1.00, 1.00),
    },
]


MANUAL_BS_KOMPLET = [
    {
        "nome": "Pan di Spagna B+S",
        "pagina": 2,
        "ingredienti": "B+S 600 g\nFarina debole 600 g\nZucchero 800 g\nUova 1000 g\nAcqua 400 g",
        "procedimento": "Montare tutti gli ingredienti in planetaria con frusta ad alta velocità per circa 10 minuti, colare nello stampo unto e cuocere come indicato nel ricettario ufficiale.",
    },
    {
        "nome": "Pan di Spagna al cacao B+S",
        "pagina": 2,
        "ingredienti": "B+S 600 g\nFarina debole 600 g\nZucchero 800 g\nUova 1100 g\nAcqua 400 g\nCacao 100 g",
        "procedimento": "Montare tutti gli ingredienti in planetaria con frusta ad alta velocità per circa 10 minuti, colare nello stampo unto e cuocere come indicato nel ricettario ufficiale.",
    },
    {
        "nome": "Arrotolato B+S",
        "pagina": 3,
        "ingredienti": "B+S 300 g\nFarina debole 300 g\nZucchero 500 g\nUova 600 g\nAcqua 200 g",
        "procedimento": "Montare tutti gli ingredienti con frusta ad alta velocità per circa 10 minuti, stendere su carta da forno e cuocere a 240 °C per circa 4 minuti come da ricettario.",
    },
    {
        "nome": "Arrotolato al cacao B+S",
        "pagina": 3,
        "ingredienti": "B+S 300 g\nFarina debole 300 g\nZucchero 500 g\nUova 700 g\nAcqua 200 g\nCacao 100 g",
        "procedimento": "Montare tutti gli ingredienti con frusta ad alta velocità per circa 10 minuti, stendere su carta da forno e cuocere a 240 °C per circa 4 minuti come da ricettario.",
    },
    {
        "nome": "Tutto cioccolato B+S",
        "pagina": 3,
        "ingredienti": "B+S 600 g\nCioccolato fondente 400 g\nBurro 300 g\nFarina debole 600 g\nUova 1300 g\nCacao 100 g\nZucchero 800 g",
        "procedimento": "Sciogliere cioccolato e burro e unire il cacao. Montare separatamente i restanti ingredienti, incorporare la salsa, colare nello stampo unto e cuocere come da ricettario.",
    },
    {
        "nome": "Torta paradiso B+S",
        "pagina": 4,
        "ingredienti": "B+S 400 g\nUova 400 g\nTuorli 300 g\nZucchero 800 g\nFarina debole 400 g\nBurro sciolto 800 g\nFarina di mandorle 100 g\nPalermo Limone 10 g",
        "procedimento": "Montare gli ingredienti con frusta ad alta velocità per circa 5 minuti, colare nello stampo unto e cuocere come indicato nel ricettario ufficiale.",
    },
    {
        "nome": "Biscotti all'uovo B+S",
        "pagina": 4,
        "ingredienti": "B+S 900 g\nUova 1200 g\nZucchero 600 g\nFarina debole 300 g\nFavorit Orange 10 g",
        "procedimento": "Montare B+S, uova e zucchero per circa 10 minuti, incorporare la farina setacciata, formare su teglie unte e infarinate e cuocere come da ricettario.",
    },
]


def _manual_page_photo(pdf_path: Path, page_number: int, crop: tuple, destination: Path) -> str:
    """Ritaglia la sola fotografia dalle pagine immagine del mini ricettario."""
    try:
        import pypdfium2 as pdfium

        document = pdfium.PdfDocument(str(pdf_path))
        rendered = document[page_number - 1].render(scale=1.8).to_pil().convert("RGB")
        width, height = rendered.size
        box = (
            int(width * crop[0]), int(height * crop[1]),
            int(width * crop[2]), int(height * crop[3]),
        )
        image = rendered.crop(box)
        image.thumbnail((1000, 760), Image.Resampling.LANCZOS)
        destination.parent.mkdir(parents=True, exist_ok=True)
        image.save(destination, "WEBP", quality=82, method=6)
        return f"/saima/ricette/{destination.name}"
    except Exception:
        return ""


def build() -> dict:
    manifest = json.loads((PDF_DIR / "manifest.json").read_text(encoding="utf-8"))
    books = manifest if isinstance(manifest, list) else (manifest.get("items") or [])
    OUT_IMAGES.mkdir(parents=True, exist_ok=True)
    # La cartella contiene solo file generati da questo script: rimuovere gli
    # asset non più referenziati evita foto orfane dopo una nuova estrazione.
    for stale in OUT_IMAGES.glob("*.webp"):
        stale.unlink()
    recipes: list[dict] = []
    seen: set[str] = set()

    for book in books:
        book_id = book["id"]
        pdf_path = PDF_DIR / f"{book_id}.pdf"
        if not pdf_path.exists():
            continue
        source_hash = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
        reader = PdfReader(str(pdf_path))
        with pdfplumber.open(pdf_path) as pdf:
            for idx, page in enumerate(pdf.pages):
                full = _clean(page.extract_text() or "")
                if "INGREDIENTI" not in full.upper():
                    continue
                title = _title_from_text(full, book.get("nome", ""))
                if not title or _INVALID_TITLE.search(title):
                    continue
                ingredients_text, procedure = _recipe_crops(page)
                ingredients = _parse_ingredients(ingredients_text)
                if not ingredients:
                    continue
                key = _slug(title)
                dedupe = f"{key}:{hashlib.sha1(ingredients_text.encode('utf-8')).hexdigest()[:10]}"
                if dedupe in seen:
                    continue
                seen.add(dedupe)
                rid = f"saima:{book_id}:{key}:p{idx + 1}"
                image_name = f"{book_id}-{key}.webp"
                photo = _extract_image(reader, idx, OUT_IMAGES / image_name)
                recipes.append(
                    {
                        "id": rid,
                        "nome": title.title(),
                        "reparto": _department(title, procedure),
                        "origine": "saima",
                        "fonte_archivio": "SAIMA S.p.a.",
                        "ricettario_saima_id": book_id,
                        "ricettario_saima_nome": book.get("nome", book_id),
                        "url_pdf": book.get("url_pdf", ""),
                        "url_pagina": book.get("url_pagina", ""),
                        "pagina_fonte": idx + 1,
                        "sha256_fonte": source_hash,
                        "ingredienti": [item["nome"] for item in ingredients],
                        "ingredienti_dettaglio": ingredients,
                        "ingredienti_testo": ingredients_text,
                        "procedimento_testo": procedure or "Procedimento presente nel PDF ufficiale.",
                        "note": procedure,
                        "foto_url": photo,
                        "porzioni": 0,
                        "pezzi_ricetta_base": 0,
                        "resa_da_impostare": True,
                        "sola_lettura": False,
                        "approvata": True,
                    }
                )

        if book_id == "5-ricette-in-5-minuti-ricettario":
            for item in MANUAL_IMAGE_ONLY:
                key = _slug(item["nome"])
                dedupe = f"manual:{key}"
                if dedupe in seen:
                    continue
                seen.add(dedupe)
                rid = f"saima:{book_id}:{key}:p{item['pagina']}"
                ingredients = _parse_ingredients(item["ingredienti"], allow_quantityless=True)
                image_name = f"{book_id}-{key}.webp"
                photo = _manual_page_photo(pdf_path, item["pagina"], item["crop"], OUT_IMAGES / image_name)
                recipes.append(
                    {
                        "id": rid,
                        "nome": item["nome"],
                        "reparto": "pasticceria",
                        "origine": "saima",
                        "fonte_archivio": "SAIMA S.p.a.",
                        "ricettario_saima_id": book_id,
                        "ricettario_saima_nome": book.get("nome", book_id),
                        "url_pdf": book.get("url_pdf", ""),
                        "url_pagina": book.get("url_pagina", ""),
                        "pagina_fonte": item["pagina"],
                        "sha256_fonte": source_hash,
                        "ingredienti": [row["nome"] for row in ingredients],
                        "ingredienti_dettaglio": ingredients,
                        "ingredienti_testo": item["ingredienti"],
                        "procedimento_testo": item["procedimento"],
                        "note": item["procedimento"],
                        "foto_url": photo,
                        "porzioni": 0,
                        "pezzi_ricetta_base": 0,
                        "resa_da_impostare": True,
                        "sola_lettura": False,
                        "approvata": True,
                    }
                )

        if book_id == "scrocchiarella-ricettario":
            for item in MANUAL_SCROCCHIARELLA:
                key = _slug(item["nome"])
                dedupe = f"manual:{key}"
                if dedupe in seen:
                    continue
                seen.add(dedupe)
                rid = f"saima:{book_id}:{key}:p{item['pagina']}"
                ingredients = _parse_ingredients(item["ingredienti"], allow_quantityless=True)
                image_name = f"{book_id}-{key}.webp"
                photo = _manual_page_photo(pdf_path, item["pagina"], item["crop"], OUT_IMAGES / image_name)
                recipes.append(
                    {
                        "id": rid,
                        "nome": item["nome"],
                        "reparto": "rosticceria",
                        "origine": "saima",
                        "fonte_archivio": "SAIMA S.p.a.",
                        "ricettario_saima_id": book_id,
                        "ricettario_saima_nome": book.get("nome", book_id),
                        "url_pdf": book.get("url_pdf", ""),
                        "url_pagina": book.get("url_pagina", ""),
                        "pagina_fonte": item["pagina"],
                        "sha256_fonte": source_hash,
                        "ingredienti": [row["nome"] for row in ingredients],
                        "ingredienti_dettaglio": ingredients,
                        "ingredienti_testo": item["ingredienti"],
                        "procedimento_testo": item["procedimento"],
                        "note": item["procedimento"],
                        "foto_url": photo,
                        "porzioni": 0,
                        "pezzi_ricetta_base": 0,
                        "resa_da_impostare": True,
                        "sola_lettura": False,
                        "approvata": True,
                    }
                )

        if book_id == "ricettario-bs-komplet":
            for item in MANUAL_BS_KOMPLET:
                key = _slug(item["nome"])
                dedupe = f"manual:{key}"
                if dedupe in seen:
                    continue
                seen.add(dedupe)
                ingredients = _parse_ingredients(item["ingredienti"])
                recipes.append(
                    {
                        "id": f"saima:{book_id}:{key}:p{item['pagina']}",
                        "nome": item["nome"],
                        "reparto": "pasticceria",
                        "origine": "saima",
                        "fonte_archivio": "SAIMA S.p.a.",
                        "ricettario_saima_id": book_id,
                        "ricettario_saima_nome": book.get("nome", book_id),
                        "url_pdf": book.get("url_pdf", ""),
                        "url_pagina": book.get("url_pagina", ""),
                        "pagina_fonte": item["pagina"],
                        "sha256_fonte": source_hash,
                        "ingredienti": [row["nome"] for row in ingredients],
                        "ingredienti_dettaglio": ingredients,
                        "ingredienti_testo": item["ingredienti"],
                        "procedimento_testo": item["procedimento"],
                        "note": item["procedimento"],
                        "foto_url": "",
                        "porzioni": 0,
                        "pezzi_ricetta_base": 0,
                        "resa_da_impostare": True,
                        "sola_lettura": False,
                        "approvata": True,
                    }
                )

    payload = {
        "meta": {
            "fonte": "https://www.saimaspa.com/applicazioni-prodotto/",
            "generato_il": datetime.now(timezone.utc).isoformat(),
            "totale_ricette": len(recipes),
            "totale_ricettari": len(books),
        },
        "ricette": recipes,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


if __name__ == "__main__":
    if not PDF_DIR.exists():
        sys.exit(f"Cartella PDF non trovata: {PDF_DIR}")
    result = build()
    print(json.dumps(result["meta"], ensure_ascii=False, indent=2))
