"""
Router Ricette — estratto da server.py
GET  /api/ricette                    — lista
GET  /api/ricette/{id}               — dettaglio
POST /api/ricette                    — crea
PUT  /api/ricette/{id}               — aggiorna
DELETE /api/ricette/{id}             — elimina
GET  /api/ricette-prezzi             — calcolo costo/pezzo + margine + varianti
PUT  /api/ricette/{id}/prezzo-vendita — imposta prezzo vendita
PUT  /api/ricette/{id}/reparto       — assegna reparto
PUT  /api/ricette/{id}/foto          — salva URL foto
POST /api/ricette/{id}/upload-foto   — upload immagine
PUT  /api/ricette/{id}/ingredienti-dettaglio — aggiorna quantità ingredienti
GET  /api/ricette-libro              — ricettario importato da Excel
GET  /api/ricette/export/pdf         — export HTML stampabile
GET  /api/ricette/export/csv         — export CSV
GET  /api/ricette/export/json        — export JSON
POST /api/ricette/auto-assegna-reparti
POST /api/ricette/pulisci-ingredienti
POST /api/ricette/popola-quantita-esempio
GET  /api/tablet/{reparto}          — prodotti per vista tablet
"""

from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Body, Depends
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Any
from datetime import datetime, timezone
from pathlib import Path
import uuid
import hashlib
import logging
import json
import unicodedata
_LOG_INIT = logging.getLogger("uvicorn.error")
import re
import shutil
import mimetypes

from app.lotti.db import database as db
from app.lotti.auth import require_admin, require_automation_or_admin

ROOT_DIR = Path(__file__).resolve().parent.parent

router = APIRouter(tags=["Ricette"])

_ARCHIVIO_DOLCE_PATH = Path(__file__).resolve().parent.parent / "data" / "archivio_dolce.json"
_RICETTARIO_EXCEL_PATH = Path(__file__).resolve().parent.parent / "data" / "ricettario_excel_ceraldi.json"


def _chiave_ricetta(nome: str) -> str:
    """Chiave prudente per collegare l'archivio documentale alle ricette operative."""
    testo = unicodedata.normalize("NFKD", str(nome or ""))
    testo = "".join(ch for ch in testo if not unicodedata.combining(ch)).lower()
    return re.sub(r"[^a-z0-9]+", " ", testo).strip()


def _carica_archivio_dolce() -> dict:
    if not _ARCHIVIO_DOLCE_PATH.exists():
        return {"meta": {}, "recipes": [], "components": []}
    with _ARCHIVIO_DOLCE_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _righe_ingredienti_archivio(value: str) -> List[dict]:
    """Converte le righe leggibili dell'archivio in ingredienti modificabili.

    La fonte resta comunque conservata integralmente in ``ingredienti_testo``:
    questo parser e volutamente prudente e non inventa quantita quando una riga
    e un titolo di sezione o un numero di pagina.
    """
    risultato = []
    unita_rx = r"kg|g|gr|mg|l|lt|ml|cl|pz|pezzi|n|%"
    for raw in str(value or "").splitlines():
        riga = " ".join(raw.strip().split())
        if not riga or riga.endswith(":") or re.fullmatch(r"\d+", riga):
            continue
        match = re.match(
            rf"^(.*?)(?:\s+)(\d+(?:[.,]\d+)?)\s*({unita_rx})\.?$",
            riga,
            flags=re.IGNORECASE,
        )
        if match:
            nome, quantita, unita = match.groups()
            risultato.append({
                "nome": nome.strip(),
                "quantita": float(quantita.replace(",", ".")),
                "unita_misura": "pz" if unita.lower() in {"n", "pezzi"} else unita.lower(),
            })
        else:
            risultato.append({"nome": riga, "quantita": 0, "unita_misura": ""})
    return risultato


def _voce_archivio_unificata(item: dict) -> dict:
    """Adatta una voce documentale alla stessa forma delle ricette Ceraldi."""
    kind = item.get("kind") or "recipe"
    dettagli = _righe_ingredienti_archivio(item.get("ingredients"))
    return {
        "id": f"archivio:{kind}:{item.get('id')}",
        "nome": item.get("name") or "Ricetta senza nome",
        "reparto": "pasticceria",
        "origine": "archivio",
        "archivio_id": item.get("id"),
        "tipo_archivio": kind,
        "ingredienti": [r["nome"] for r in dettagli],
        "ingredienti_dettaglio": dettagli,
        "ingredienti_testo": item.get("ingredients") or "",
        "procedimento_testo": item.get("procedure") or "",
        "note_archivio": item.get("notes") or "",
        "fonte_archivio": item.get("source") or "",
        "provenienza_archivio": item.get("provenance") or {},
        "numero_archivio": item.get("number"),
        "parent_recipe": item.get("parentRecipe"),
        "componenti_testo": item.get("components") or "",
        "documentazione_archivio": item,
        "sola_lettura": True,
        "porzioni": 0,
    }


# ── Seed una-tantum 23/07/2026 (dettatura Enzo): ricette col SOLO NOME ───────
# Enzo compilerà ingredienti/foto dall'app. Nomi normalizzati dalla dettatura
# vocale ("Aspritz"→Spritz, "Minion"→mignon, "zuppolina"→zeppolina,
# "divini amor"→Divino Amore, "profitterol"→Profiterole). Flag in
# sistema_stato: gira UNA volta sola — se poi ne elimina una, non ricompare.
RICETTE_SOLO_NOME_23072026 = [
    # Bar
    ("Spritz", "bar"),
    ("Crema di caffè", "bar"),
    # Pasticceria
    ("Sanguinaccio", "pasticceria"),
    ("Segreto amalfitano", "pasticceria"),
    ("Millefoglie crema ed amarena", "pasticceria"),
    ("Deliziosa", "pasticceria"),
    ("Deliziosa al cioccolato", "pasticceria"),
    ("Biscotto all'amarena", "pasticceria"),
    ("Pasticcino al limone", "pasticceria"),
    ("Zeppolina di San Giuseppe", "pasticceria"),
    ("Zeppola di San Giuseppe", "pasticceria"),
    ("Occhio di bue al cioccolato", "pasticceria"),
    ("Occhio di bue all'albicocca", "pasticceria"),
    ("Occhio di bue al pistacchio", "pasticceria"),
    ("Sfogliatella Santa Rosa", "pasticceria"),
    ("Sfogliatella mignon Santa Rosa", "pasticceria"),
    ("Graffetta mignon", "pasticceria"),
    ("Pan di Spagna", "pasticceria"),
    ("Roccocò", "pasticceria"),
    ("Mustacciolo", "pasticceria"),
    ("Quaresimali", "pasticceria"),
    ("Divino Amore", "pasticceria"),
    ("Sapienze", "pasticceria"),
    ("Susamielli", "pasticceria"),
    ("Struffoli classico al kg", "pasticceria"),
    ("Struffoli mignon", "pasticceria"),
    ("Profiterole mignon", "pasticceria"),
    ("Profiterole al kg", "pasticceria"),
    # Rosticceria
    ("Bollino sottilette e salame", "rosticceria"),
    ("Bollino sottilette e prosciutto cotto", "rosticceria"),
    ("Bollino uova e stracciatella", "rosticceria"),
    ("Focaccina Margherita", "rosticceria"),
    ("Focaccina Marinara", "rosticceria"),
    ("Focaccina mozzarella bianca", "rosticceria"),
    ("Focaccina con scarole", "rosticceria"),
    ("Focaccina con tonno e mozzarella", "rosticceria"),
    ("Focaccina con fagioli rossi", "rosticceria"),
    ("Bastoncino al forno prosciutto e mozzarella", "rosticceria"),
    ("Bastoncino al forno tonno e mozzarella", "rosticceria"),
    ("Hot dog", "rosticceria"),
    ("Pizza fritta con ricotta", "rosticceria"),
    ("Pizza fritta con scarola", "rosticceria"),
    ("Pizza fritta con prosciutto e mozzarella", "rosticceria"),
]

# Secondo lotto (dettatura successiva, stesso giorno): i savarese mignon.
RICETTE_SOLO_NOME_23072026_B2 = [
    ("Savarese mignon panna", "pasticceria"),
    ("Savarese mignon panna e pistacchio", "pasticceria"),
    ("Savarese mignon panna e cioccolato", "pasticceria"),
    ("Savarese mignon crema ed amarena", "pasticceria"),
]


# Ingredienti PROPOSTI per le ricette dettate (23/07/2026, richiesta Enzo:
# "vedi se puoi impostare gli ingredienti"). Quantità indicative per ~10 pezzi
# dove ha senso: sono una BASE che Enzo corregge dall'app — per questo vengono
# marcate origine_ingredienti="automatica" (badge "🤖 proposti in automatico")
# e applicate SOLO alle ricette ancora senza ingredienti.
INGREDIENTI_DETTATI_23072026 = {
    # Bar
    "Spritz": [("Prosecco", 900, "ml"), ("Aperol", 600, "ml"), ("Acqua frizzante", 300, "ml"), ("Arance", 2, "pz")],
    "Crema di caffè": [("Caffe espresso", 200, "ml"), ("Panna", 250, "ml"), ("Zucchero", 100, "g")],
    # Pasticceria
    "Sanguinaccio": [("Cioccolato fondente", 300, "g"), ("Cacao amaro", 80, "g"), ("Latte", 500, "ml"), ("Zucchero", 250, "g"), ("Amido di mais", 40, "g"), ("Cannella", 2, "g"), ("Canditi", 50, "g")],
    "Segreto amalfitano": [("Pan di Spagna", 400, "g"), ("Crema pasticcera", 300, "g"), ("Panna", 200, "ml"), ("Limoncello", 50, "ml"), ("Limoni", 2, "pz"), ("Zucchero a velo", 30, "g")],
    "Millefoglie crema ed amarena": [("Pasta sfoglia", 500, "g"), ("Crema pasticcera", 500, "g"), ("Amarene", 150, "g"), ("Zucchero a velo", 50, "g")],
    "Deliziosa": [("Pasta frolla", 400, "g"), ("Crema pasticcera", 300, "g"), ("Panna", 200, "ml"), ("Zucchero a velo", 30, "g")],
    "Deliziosa al cioccolato": [("Pasta frolla", 400, "g"), ("Crema pasticcera", 250, "g"), ("Cioccolato fondente", 150, "g"), ("Panna", 200, "ml"), ("Cacao amaro", 20, "g")],
    "Biscotto all'amarena": [("Pan di Spagna", 300, "g"), ("Farina", 150, "g"), ("Zucchero", 100, "g"), ("Confettura di amarene", 200, "g"), ("Cacao amaro", 30, "g"), ("Rum", 20, "ml"), ("Glassa di zucchero", 100, "g")],
    "Pasticcino al limone": [("Pasta frolla", 300, "g"), ("Crema al limone", 250, "g"), ("Limoni", 2, "pz"), ("Zucchero a velo", 30, "g")],
    "Zeppolina di San Giuseppe": [("Farina", 250, "g"), ("Uova", 4, "pz"), ("Burro", 70, "g"), ("Acqua", 250, "ml"), ("Crema pasticcera", 300, "g"), ("Amarene", 80, "g"), ("Zucchero a velo", 20, "g")],
    "Zeppola di San Giuseppe": [("Farina", 250, "g"), ("Uova", 4, "pz"), ("Burro", 70, "g"), ("Acqua", 250, "ml"), ("Crema pasticcera", 400, "g"), ("Amarene", 100, "g"), ("Zucchero a velo", 30, "g")],
    "Occhio di bue al cioccolato": [("Pasta frolla", 450, "g"), ("Cioccolato fondente", 180, "g"), ("Zucchero a velo", 30, "g")],
    "Occhio di bue all'albicocca": [("Pasta frolla", 450, "g"), ("Confettura di albicocche", 200, "g"), ("Zucchero a velo", 30, "g")],
    "Occhio di bue al pistacchio": [("Pasta frolla", 450, "g"), ("Crema di pistacchio", 200, "g"), ("Zucchero a velo", 30, "g")],
    "Sfogliatella Santa Rosa": [("Farina", 250, "g"), ("Semola rimacinata", 250, "g"), ("Ricotta", 500, "g"), ("Zucchero", 200, "g"), ("Strutto", 150, "g"), ("Canditi", 80, "g"), ("Cannella", 2, "g"), ("Uova", 1, "pz"), ("Crema pasticcera", 200, "g"), ("Amarene", 100, "g")],
    "Sfogliatella mignon Santa Rosa": [("Farina", 250, "g"), ("Semola rimacinata", 250, "g"), ("Ricotta", 500, "g"), ("Zucchero", 200, "g"), ("Strutto", 150, "g"), ("Canditi", 80, "g"), ("Cannella", 2, "g"), ("Uova", 1, "pz"), ("Crema pasticcera", 200, "g"), ("Amarene", 100, "g")],
    "Graffetta mignon": [("Farina", 400, "g"), ("Patate", 200, "g"), ("Uova", 2, "pz"), ("Burro", 80, "g"), ("Zucchero", 150, "g"), ("Lievito di birra", 15, "g"), ("Latte", 100, "ml"), ("Sale", 5, "g"), ("Olio di semi", 500, "ml")],
    "Pan di Spagna": [("Uova", 6, "pz"), ("Zucchero", 180, "g"), ("Farina", 180, "g"), ("Vaniglia", 2, "g"), ("Sale", 2, "g")],
    "Roccocò": [("Farina", 400, "g"), ("Mandorle", 200, "g"), ("Zucchero", 300, "g"), ("Canditi", 100, "g"), ("Pisto (spezie)", 10, "g"), ("Ammoniaca per dolci", 5, "g"), ("Acqua", 80, "ml")],
    "Mustacciolo": [("Farina", 400, "g"), ("Zucchero", 200, "g"), ("Miele", 100, "g"), ("Cacao amaro", 50, "g"), ("Pisto (spezie)", 10, "g"), ("Cioccolato fondente", 300, "g"), ("Ammoniaca per dolci", 5, "g")],
    "Quaresimali": [("Mandorle", 300, "g"), ("Farina", 200, "g"), ("Zucchero", 200, "g"), ("Uova", 2, "pz"), ("Cannella", 2, "g")],
    "Divino Amore": [("Mandorle", 250, "g"), ("Zucchero", 200, "g"), ("Uova", 2, "pz"), ("Canditi", 80, "g"), ("Alchermes", 30, "ml"), ("Glassa di zucchero", 100, "g")],
    "Sapienze": [("Farina", 300, "g"), ("Mandorle", 150, "g"), ("Zucchero", 150, "g"), ("Miele", 50, "g"), ("Cannella", 2, "g"), ("Uova", 1, "pz")],
    "Susamielli": [("Farina", 400, "g"), ("Miele", 300, "g"), ("Mandorle", 150, "g"), ("Pisto (spezie)", 10, "g"), ("Zucchero", 50, "g")],
    "Struffoli classico al kg": [("Farina", 400, "g"), ("Uova", 4, "pz"), ("Zucchero", 50, "g"), ("Miele", 300, "g"), ("Burro", 50, "g"), ("Canditi", 80, "g"), ("Confettini colorati", 40, "g"), ("Limoni", 1, "pz"), ("Olio di semi", 500, "ml")],
    "Struffoli mignon": [("Farina", 400, "g"), ("Uova", 4, "pz"), ("Zucchero", 50, "g"), ("Miele", 300, "g"), ("Burro", 50, "g"), ("Canditi", 80, "g"), ("Confettini colorati", 40, "g"), ("Limoni", 1, "pz"), ("Olio di semi", 500, "ml")],
    "Profiterole mignon": [("Farina", 150, "g"), ("Uova", 4, "pz"), ("Burro", 100, "g"), ("Acqua", 250, "ml"), ("Panna", 400, "ml"), ("Cioccolato fondente", 300, "g"), ("Zucchero", 80, "g")],
    "Profiterole al kg": [("Farina", 150, "g"), ("Uova", 4, "pz"), ("Burro", 100, "g"), ("Acqua", 250, "ml"), ("Panna", 400, "ml"), ("Cioccolato fondente", 300, "g"), ("Zucchero", 80, "g")],
    "Savarese mignon panna": [("Farina", 250, "g"), ("Uova", 4, "pz"), ("Burro", 80, "g"), ("Zucchero", 30, "g"), ("Lievito di birra", 10, "g"), ("Bagna al liquore", 100, "ml"), ("Panna", 250, "ml")],
    "Savarese mignon panna e pistacchio": [("Farina", 250, "g"), ("Uova", 4, "pz"), ("Burro", 80, "g"), ("Zucchero", 30, "g"), ("Lievito di birra", 10, "g"), ("Bagna al liquore", 100, "ml"), ("Panna", 200, "ml"), ("Crema di pistacchio", 150, "g")],
    "Savarese mignon panna e cioccolato": [("Farina", 250, "g"), ("Uova", 4, "pz"), ("Burro", 80, "g"), ("Zucchero", 30, "g"), ("Lievito di birra", 10, "g"), ("Bagna al liquore", 100, "ml"), ("Panna", 200, "ml"), ("Cioccolato fondente", 150, "g")],
    "Savarese mignon crema ed amarena": [("Farina", 250, "g"), ("Uova", 4, "pz"), ("Burro", 80, "g"), ("Zucchero", 30, "g"), ("Lievito di birra", 10, "g"), ("Bagna al liquore", 100, "ml"), ("Crema pasticcera", 250, "g"), ("Amarene", 100, "g")],
    # Rosticceria
    "Bollino sottilette e salame": [("Farina", 500, "g"), ("Latte", 200, "ml"), ("Lievito di birra", 12, "g"), ("Zucchero", 20, "g"), ("Sale", 8, "g"), ("Sottilette", 150, "g"), ("Salame", 150, "g"), ("Uova", 1, "pz")],
    "Bollino sottilette e prosciutto cotto": [("Farina", 500, "g"), ("Latte", 200, "ml"), ("Lievito di birra", 12, "g"), ("Zucchero", 20, "g"), ("Sale", 8, "g"), ("Sottilette", 150, "g"), ("Prosciutto cotto", 150, "g"), ("Uova", 1, "pz")],
    "Bollino uova e stracciatella": [("Farina", 500, "g"), ("Latte", 200, "ml"), ("Lievito di birra", 12, "g"), ("Zucchero", 20, "g"), ("Sale", 8, "g"), ("Uova sode", 3, "pz"), ("Stracciatella", 200, "g")],
    "Focaccina Margherita": [("Farina", 500, "g"), ("Pomodoro", 300, "g"), ("Fiordilatte", 200, "g"), ("Lievito di birra", 10, "g"), ("Olio extravergine di oliva", 30, "ml"), ("Basilico", 5, "g"), ("Sale", 10, "g")],
    "Focaccina Marinara": [("Farina", 500, "g"), ("Pomodoro", 300, "g"), ("Aglio", 10, "g"), ("Origano", 5, "g"), ("Olio extravergine di oliva", 30, "ml"), ("Lievito di birra", 10, "g"), ("Sale", 10, "g")],
    "Focaccina mozzarella bianca": [("Farina", 500, "g"), ("Fiordilatte", 250, "g"), ("Olio extravergine di oliva", 30, "ml"), ("Lievito di birra", 10, "g"), ("Sale", 10, "g")],
    "Focaccina con scarole": [("Farina", 500, "g"), ("Scarola", 300, "g"), ("Olive nere", 80, "g"), ("Capperi", 20, "g"), ("Olio extravergine di oliva", 30, "ml"), ("Lievito di birra", 10, "g"), ("Sale", 10, "g")],
    "Focaccina con tonno e mozzarella": [("Farina", 500, "g"), ("Tonno", 200, "g"), ("Fiordilatte", 200, "g"), ("Olio extravergine di oliva", 30, "ml"), ("Lievito di birra", 10, "g"), ("Sale", 10, "g")],
    "Focaccina con fagioli rossi": [("Farina", 500, "g"), ("Fagioli rossi", 250, "g"), ("Fiordilatte", 150, "g"), ("Olio extravergine di oliva", 30, "ml"), ("Lievito di birra", 10, "g"), ("Sale", 10, "g")],
    "Bastoncino al forno prosciutto e mozzarella": [("Farina", 500, "g"), ("Latte", 200, "ml"), ("Burro", 80, "g"), ("Lievito di birra", 12, "g"), ("Prosciutto cotto", 150, "g"), ("Fiordilatte", 200, "g"), ("Sale", 8, "g")],
    "Bastoncino al forno tonno e mozzarella": [("Farina", 500, "g"), ("Latte", 200, "ml"), ("Burro", 80, "g"), ("Lievito di birra", 12, "g"), ("Tonno", 150, "g"), ("Fiordilatte", 200, "g"), ("Sale", 8, "g")],
    "Hot dog": [("Farina", 500, "g"), ("Latte", 200, "ml"), ("Burro", 60, "g"), ("Zucchero", 30, "g"), ("Lievito di birra", 12, "g"), ("Wurstel", 10, "pz"), ("Sale", 8, "g")],
    "Pizza fritta con ricotta": [("Farina", 500, "g"), ("Lievito di birra", 10, "g"), ("Ricotta", 300, "g"), ("Provola", 150, "g"), ("Pepe", 3, "g"), ("Olio di semi", 1000, "ml"), ("Sale", 10, "g")],
    "Pizza fritta con scarola": [("Farina", 500, "g"), ("Lievito di birra", 10, "g"), ("Scarola", 300, "g"), ("Olive nere", 80, "g"), ("Olio di semi", 1000, "ml"), ("Sale", 10, "g")],
    "Pizza fritta con prosciutto e mozzarella": [("Farina", 500, "g"), ("Lievito di birra", 10, "g"), ("Prosciutto cotto", 150, "g"), ("Fiordilatte", 200, "g"), ("Pomodoro", 100, "g"), ("Olio di semi", 1000, "ml"), ("Sale", 10, "g")],
}


async def seed_ingredienti_dettati():
    """Riempe di ingredienti PROPOSTI le ricette dettate — SOLO quelle ancora
    vuote (mai sopra il lavoro di Enzo), marcate origine 'automatica'."""
    FLAG = "seed_ingredienti_nomi_23072026"
    if await db.sistema_stato.find_one({"chiave": FLAG}):
        return
    aggiornate = 0
    for nome, ings in INGREDIENTI_DETTATI_23072026.items():
        r = await db.ricette.find_one(
            {"nome": {"$regex": f"^{re.escape(nome)}$", "$options": "i"}},
            {"_id": 0, "id": 1, "ingredienti": 1, "ingredienti_dettaglio": 1})
        if not r:
            continue
        if r.get("ingredienti_dettaglio") or r.get("ingredienti"):
            continue  # Enzo ci ha già messo mano: non si tocca
        await db.ricette.update_one({"id": r["id"]}, {"$set": {
            "ingredienti": [n for n, _q, _u in ings],
            "ingredienti_dettaglio": [
                {"nome": n, "quantita": q, "unita_misura": u} for n, q, u in ings],
            "origine_ingredienti": "automatica",
        }})
        aggiornate += 1
    await db.sistema_stato.update_one(
        {"chiave": FLAG},
        {"$set": {"chiave": FLAG, "valore": f"{aggiornate} ricette riempite",
                  "quando": datetime.now(timezone.utc).isoformat()}},
        upsert=True)
    _LOG_INIT.info(f"[SEED] ingredienti dettati 23/07/2026: {aggiornate} ricette riempite")


# Foto dal web per le ricette dettate (Enzo 23/07/2026: "carica le foto").
# Il sandbox di sviluppo non può scaricare immagini → lo fa il SERVER su
# Render, da Wikimedia Commons (immagini a licenza libera), in background.
# Termine di ricerca curato per prodotto; None = nessun termine affidabile
# (es. "occhio di bue" su Commons trova UOVA FRITTE, i bollini sono prodotti
# locali): meglio nessuna foto che una sbagliata — le mette Enzo via Drive.
FOTO_WEB_TERMINI_23072026 = {
    "Spritz": "Spritz Aperol",
    "Crema di caffè": "crema di caffè",
    "Sanguinaccio": "sanguinaccio dolce cioccolato",
    "Segreto amalfitano": "delizia al limone",
    "Millefoglie crema ed amarena": "mille-feuille",
    "Deliziosa": None,
    "Deliziosa al cioccolato": None,
    "Biscotto all'amarena": "biscotto amarena",
    "Pasticcino al limone": None,
    "Zeppolina di San Giuseppe": "zeppole di San Giuseppe",
    "Zeppola di San Giuseppe": "zeppola di San Giuseppe",
    "Occhio di bue al cioccolato": None,
    "Occhio di bue all'albicocca": None,
    "Occhio di bue al pistacchio": None,
    "Sfogliatella Santa Rosa": "sfogliatella Santa Rosa",
    "Sfogliatella mignon Santa Rosa": "sfogliatella Santa Rosa",
    "Graffetta mignon": "graffa napoletana",
    "Pan di Spagna": "pan di spagna sponge cake",
    "Roccocò": "roccocò",
    "Mustacciolo": "mostaccioli",
    "Quaresimali": "quaresimali",
    "Divino Amore": None,
    "Sapienze": None,
    "Susamielli": "susamielli",
    "Struffoli classico al kg": "struffoli",
    "Struffoli mignon": "struffoli napoletani",
    "Profiterole mignon": "profiteroles",
    "Profiterole al kg": "profiteroles chocolate",
    "Savarese mignon panna": "savarin dessert",
    "Savarese mignon panna e pistacchio": "savarin chantilly",
    "Savarese mignon panna e cioccolato": "savarin dessert cream",
    "Savarese mignon crema ed amarena": "savarin",
    "Bollino sottilette e salame": None,
    "Bollino sottilette e prosciutto cotto": None,
    "Bollino uova e stracciatella": None,
    "Focaccina Margherita": "pizza margherita",
    "Focaccina Marinara": "pizza marinara",
    "Focaccina mozzarella bianca": "focaccia con mozzarella",
    "Focaccina con scarole": "pizza di scarole",
    "Focaccina con tonno e mozzarella": None,
    "Focaccina con fagioli rossi": None,
    "Bastoncino al forno prosciutto e mozzarella": None,
    "Bastoncino al forno tonno e mozzarella": None,
    "Hot dog": "hot dog bun",
    "Pizza fritta con ricotta": "pizza fritta napoletana",
    "Pizza fritta con scarola": "pizza fritta",
    "Pizza fritta con prosciutto e mozzarella": "pizza fritta Napoli",
}

_UA_COMMONS = {"User-Agent": "LottiHACCP/1.0 (gestionale interno Ceraldi Group)"}


async def _cerca_foto_commons(client, termine: str):
    """Prima immagine pertinente da Wikimedia Commons (licenze libere)."""
    r = await client.get("https://commons.wikimedia.org/w/api.php", params={
        "action": "query", "format": "json",
        "generator": "search", "gsrsearch": f"{termine} filetype:bitmap",
        "gsrnamespace": 6, "gsrlimit": 3,
        "prop": "imageinfo", "iiprop": "url|mime", "iiurlwidth": 800,
    })
    pages = ((r.json().get("query") or {}).get("pages") or {})
    for p in sorted(pages.values(), key=lambda x: x.get("index", 99)):
        for ii in p.get("imageinfo") or []:
            url = ii.get("thumburl") or ii.get("url")
            if url:
                return url, ii.get("mime") or "image/jpeg"
    return None, None


async def importa_foto_da_web(solo_senza_foto: bool = True) -> dict:
    """Scarica una foto per ogni ricetta dettata ancora SENZA foto e la salva
    su Mongo (foto_files) come ogni altra foto dell'app. Best-effort."""
    import httpx
    esiti = {"caricate": [], "senza_risultato": [], "gia_con_foto": [], "senza_termine": []}
    async with httpx.AsyncClient(timeout=30, headers=_UA_COMMONS, follow_redirects=True) as client:
        for nome, termine in FOTO_WEB_TERMINI_23072026.items():
            ricetta = await db.ricette.find_one(
                {"nome": {"$regex": f"^{re.escape(nome)}$", "$options": "i"}},
                {"_id": 0, "id": 1, "foto_url": 1})
            if not ricetta:
                continue
            if solo_senza_foto and ricetta.get("foto_url"):
                esiti["gia_con_foto"].append(nome)
                continue
            if not termine:
                esiti["senza_termine"].append(nome)
                continue
            try:
                url, mime = await _cerca_foto_commons(client, termine)
                if not url:
                    esiti["senza_risultato"].append(nome)
                    continue
                img = await client.get(url)
                if img.status_code != 200 or len(img.content) < 2000:
                    esiti["senza_risultato"].append(nome)
                    continue
                versione = int(datetime.now(timezone.utc).timestamp())
                fid = "web_" + ricetta["id"]
                await db.foto_files.update_one(
                    {"_id": fid},
                    {"$set": {"_id": fid,
                              "mime": img.headers.get("content-type") or mime,
                              "data": img.content, "ricetta_id": ricetta["id"],
                              "versione": versione, "fonte": "wikimedia_commons",
                              "url_origine": url,
                              "updated_at": datetime.now(timezone.utc).isoformat()}},
                    upsert=True)
                await db.ricette.update_one(
                    {"id": ricetta["id"]},
                    {"$set": {"foto_url": f"/api/foto/{fid}?v={versione}"}})
                esiti["caricate"].append(nome)
            except Exception as e:
                _LOG_INIT.warning(f"[FOTO WEB] {nome}: {type(e).__name__}: {e}")
                esiti["senza_risultato"].append(nome)
    return esiti


@router.post("/ricette/importa-foto-web")
async def importa_foto_web_endpoint(solo_senza_foto: bool = True):
    """Rilancio manuale del recupero foto dal web (solo ricette senza foto)."""
    esiti = await importa_foto_da_web(solo_senza_foto)
    return {"ok": True, **{k: len(v) for k, v in esiti.items()}, "dettaglio": esiti}


async def seed_foto_web():
    """Una tantum, in background: non blocca l'avvio del server."""
    FLAG = "seed_foto_web_23072026"
    if await db.sistema_stato.find_one({"chiave": FLAG}):
        return
    await db.sistema_stato.update_one(
        {"chiave": FLAG},
        {"$set": {"chiave": FLAG, "valore": "in corso",
                  "quando": datetime.now(timezone.utc).isoformat()}}, upsert=True)
    esiti = await importa_foto_da_web(True)
    await db.sistema_stato.update_one(
        {"chiave": FLAG},
        {"$set": {"valore": f"caricate {len(esiti['caricate'])}, "
                            f"senza risultato {len(esiti['senza_risultato'])}, "
                            f"senza termine {len(esiti['senza_termine'])}",
                  "esiti": esiti}}, upsert=True)
    _LOG_INIT.info(f"[SEED] foto web 23/07/2026: {len(esiti['caricate'])} caricate")


async def seed_ricette_solo_nome():
    await _seed_lotto_nomi("seed_ricette_nomi_23072026", RICETTE_SOLO_NOME_23072026)
    await _seed_lotto_nomi("seed_ricette_nomi_23072026_b2", RICETTE_SOLO_NOME_23072026_B2)
    await seed_ingredienti_dettati()
    import asyncio
    asyncio.create_task(seed_foto_web())


async def _seed_lotto_nomi(FLAG: str, lista: list):
    """Crea le ricette dettate da Enzo (solo nome, ingredienti vuoti).
    Idempotente e prudente: salta i nomi già esistenti (case-insensitive) e
    dopo il primo giro non tocca più nulla (flag in sistema_stato)."""
    if await db.sistema_stato.find_one({"chiave": FLAG}):
        return
    creati = 0
    for nome, reparto in lista:
        esiste = await db.ricette.find_one(
            {"nome": {"$regex": f"^{re.escape(nome)}$", "$options": "i"}}, {"_id": 1})
        if esiste:
            continue
        await db.ricette.insert_one({
            "id": str(uuid.uuid4()),
            "nome": nome,
            "reparto": reparto,
            "ingredienti": [],
            "ingredienti_dettaglio": [],
            "porzioni": 10,
            "note": "",
            "origine_ingredienti": "manuale",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        creati += 1
    await db.sistema_stato.update_one(
        {"chiave": FLAG},
        {"$set": {"chiave": FLAG, "valore": f"{creati} ricette create",
                  "quando": datetime.now(timezone.utc).isoformat()}},
        upsert=True)
    _LOG_INIT.info(f"[SEED] ricette solo-nome ({FLAG}): {creati} create")


# ─── Modelli ──────────────────────────────────────────────────────────────────
class Ricetta(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    nome: str
    ingredienti: List[Any] = []
    ingredienti_dettaglio: List[dict] = []
    componenti: Optional[List[dict]] = []  # BOM: [{tipo, ref_id, nome, quantita, unita_misura}]
    porzioni: Optional[float] = 1
    note: str = ""
    approvata: Optional[bool] = None  # None=vecchia, False=nuova da approvare, True=approvata
    costo_totale: Optional[float] = None
    costo_porzione: Optional[float] = None
    completezza: Optional[str] = None
    ricetta_base_id: Optional[str] = None
    ricetta_base_nome: Optional[str] = None
    ingrediente_variante: Optional[dict] = None
    prezzo_vendita: Optional[float] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RicettaCreate(BaseModel):
    model_config = ConfigDict(extra="allow")  # accetta campi extra senza errori
    nome: str
    ingredienti: List[Any] = []
    ingredienti_dettaglio: List[dict] = []
    componenti: Optional[List[dict]] = []
    porzioni: int = 1
    note: str = ""
    ricetta_base_id: Optional[str] = None
    ricetta_base_nome: Optional[str] = None
    ingrediente_variante: Optional[dict] = None
    prezzo_vendita: Optional[float] = None
    reparto: Optional[str] = None
    foto_url: Optional[str] = None
    stagionale: Optional[bool] = False
    allergeni_auto: Optional[List[str]] = []  # allergeni calcolati dal frontend
    allergeni: Optional[List[str]] = []  # allergeni manuali
    allergeni_confermati: bool = False  # True solo dopo una modifica umana esplicita


# ─── Helper reparti e nomi ────────────────────────────────────────────────────
_PASTICCERIA_KW = [
    "torta",
    "crema",
    "mousse",
    "cheesecake",
    "mille foglie",
    "profitterol",
    "cannolo",
    "sfogliatella",
    "babà",
    "baba",
    "frolla",
    "crostata",
    "macaron",
    "eclair",
    "choux",
    "gelato",
    "semifreddo",
    "tiramisu",
    "tiramisù",
    "panna cotta",
    "pannacotta",
    "crèpe",
    "crepe",
    "waffle",
    "donut",
    "muffin",
    "cupcake",
    "brownie",
    "cookies",
    "biscotto",
    "biscotti",
    "meringhe",
    "meringa",
    "ganache",
    "glassa",
    "confettura",
    "marmellata",
    "namelaka",
    "cremoso",
    "cornetto",
    "brioche",
    "pasticceria",
    "dolce",
    "dessert",
    "budino",
    "flan",
    "strudel",
    "paris-brest",
    "tronchetto",
    "charlotte",
    "cassata",
    "pastiera",
    "struffoli",
    "zeppole",
    "ciambella",
    "ciambellone",
    "pandoro",
    "panettone",
    "colomba",
    "frittelle",
    "bombolone",
    "maritozzo",
    "diplomatico",
    "zuccotto",
    "gianduja",
    "cremino",
    "mignon",
    "savarin",
    "cassatin",
    "coda di aragosta",
    "crostatin",
    "croccantin",
    "delizia",
    "fiocco di neve",
    "francesina",
    "krans",
    "kranz",
    "pan di spagna",
    "pasta di mandorle",
    "pasta sfoglia",
    "pasticcin",
    "prussian",
    "zuccherat",
    "savoiard",
    "chantilly",
    "caprese cioccolato",
    "caprese limone",
    "caprese al cioccolato",
    "caprese al limone",
    "panna",
    "nocciol",
    "cioccol",
    # Nomi tradizionali presenti nel ricettario Ceraldi. Non contengono una
    # parola dolce generica, ma sono prodotti di pasticceria (alcuni sono
    # varianti di brioche/pasta choux importate da Cartel1).
    "buondì",
    "buondi",
    "via col vento",
    "vesuvio",
]
_ROSTICCERIA_KW = [
    "pizza",
    "focaccia",
    "calzone",
    "piadina",
    "panino",
    "sandwich",
    "burger",
    "tramezzino",
    "bruschetta",
    "crostino",
    "arancino",
    "arancina",
    "arancini",
    "supplì",
    "frittata",
    "quiche",
    "mozzarella in carrozza",
    "impanata",
    "fritto",
    "frittura",
    "lasagna",
    "lasagne",
    "gnocchi",
    "risotto",
    "polenta",
    "polpetta",
    "polpette",
    "cotoletta",
    "scaloppina",
    "arrosto",
    "pollo",
    "carne",
    "pesce",
    "baccalà",
    "alici",
    "acciughe",
    "polpo",
    "calamari",
    "gamberi",
    "cozze",
    "vongole",
    "frittella salata",
    "torta salata",
    "rustici",
    "panzerotti",
    "vol-au-vent",
    "croissant salato",
]


_SAVORY_OVERRIDE = (
    "salat", "rustic", "casatiell", "tortano", "scarole", "parmigian",
    "gattò", "gatto di patate", "gateau di patate", "panzerott", "salsiccia",
    "ragù", "ragu",
)

_INGREDIENTI_DOLCI = (
    "zucchero", "cioccol", "cacao", "confettura", "marmellata", "panna",
    "crema pasticc", "fragolin", "amarena", "mandorl", "nocciol", "pistac",
    "aroma croissant", "granella di zucchero", "candit", "vaniglia",
)

_INGREDIENTI_SALATI = (
    "prosciutto", "salame", "mozzarella", "pomodoro", "tonno", "acciug",
    "wurstel", "wrustel", "carne", "ragù", "ragu", "salsiccia", "friariell",
    "melanz", "peperon", "scarol", "parmigian", "provol", "mortadella",
)

_BAR_KW = (
    "spritz", "caffe", "caffè", "cappuccino", "schiumato", "aperitivo",
    "amaro", "whisky", "whiskey", "rum", "vodka", "gin", "cocktail",
    "birra", "prosecco", "spumante", "vino", "liquore", "grappa",
    "succo", "spremuta", "bibita", "acqua tonica", "soda", "cola",
    "the freddo", "tè freddo", "te freddo",
)

_BAR_OVERRIDE = (
    "crema di caffe", "crema di caffè",
)


def _categorizza_reparto(
    nome: str,
    ingredienti: Optional[List[str]] = None,
    ricetta_base_nome: Optional[str] = None,
) -> str:
    """Classifica solo quando esistono segnali sufficienti.

    Cartel1 contiene anche nomi tradizionali poco descrittivi (per esempio
    ``Treccia``) e varianti collegate a una base. Per questi casi usiamo base e
    ingredienti; se il risultato resta incerto ritorniamo ``altro`` invece di
    spostare automaticamente tutto in rosticceria.
    """
    n = (nome or "").lower()
    # Solo le preparazioni inequivocabilmente da bar precedono i dolci. Gli
    # aromi (rum, liquore, caffe) non devono trasformare Babà/Torte in bevande.
    if any(kw in n for kw in _BAR_OVERRIDE):
        return "bar"
    # «Casatiello dolce», «pizza dolce» e nomi analoghi sono dolci anche se
    # contengono una parola normalmente salata. Richiediamo la parola intera
    # per non confondere per esempio «agrodolce».
    if re.search(r"(?<!\w)dolce(?!\w)", n):
        return "pasticceria"
    if any(kw in n for kw in _SAVORY_OVERRIDE):
        return "rosticceria"
    for kw in _PASTICCERIA_KW:
        if kw in n:
            return "pasticceria"
    # I termini del bar devono coincidere con parole/frasi complete: un
    # semplice ``kw in n`` classificava per esempio "cioccolato" come bar
    # perché contiene accidentalmente la sequenza "cola".
    if any(re.search(rf"(?<!\w){re.escape(kw)}(?!\w)", n) for kw in _BAR_KW):
        return "bar"
    for kw in _ROSTICCERIA_KW:
        # Anche qui servono confini: "cozze" non deve coincidere con
        # "scozzesi" (Croccantini scozzesi e un dolce).
        if re.search(rf"(?<!\w){re.escape(kw)}(?!\w)", n):
            return "rosticceria"

    base = (ricetta_base_nome or "").lower().strip()
    if base and base != n:
        reparto_base = _categorizza_reparto(base)
        if reparto_base != "altro":
            return reparto_base

    testo_ingredienti = " ".join(str(value or "").lower() for value in (ingredienti or []))
    if testo_ingredienti:
        segnali_salati = sum(kw in testo_ingredienti for kw in _INGREDIENTI_SALATI)
        segnali_dolci = sum(kw in testo_ingredienti for kw in _INGREDIENTI_DOLCI)
        if segnali_salati:
            return "rosticceria"
        if segnali_dolci >= 2:
            return "pasticceria"
    return "altro"


def _reparto_finale_auto(reparto_corrente: str, reparto_calcolato: str) -> str:
    """Applica la classificazione automatica senza cancellare scelte esplicite."""
    corrente = (reparto_corrente or "").lower().strip()
    if reparto_calcolato == "altro":
        return corrente
    return reparto_calcolato


_ORIGINI_RICETTARI_FORNITORI = {
    "acquaviva",
    "alfa",
    "alpha",
    "bindi",
    "il_pasticcere",
    "mepa",
    "saima",
    "sammontana",
    "tre_marie",
    "tremarie",
    "vandemoortele",
}


def _origine_normalizzata(value: Any) -> str:
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(ch for ch in value if not unicodedata.combining(ch)).casefold()
    return re.sub(r"[^a-z0-9]+", "_", value).strip("_")


def _riferimento_ricettario_fornitore(ricetta: dict) -> bool:
    """Distingue una ricetta ufficiale del fornitore da una ricetta Ceraldi.

    Avere un ingrediente acquistato da SAIMA/Acquaviva non basta: serve una
    provenienza esplicita del *ricettario*. In questo modo non nascondiamo mai
    una ricetta interna soltanto perche usa un prodotto di quel fornitore.
    """
    origine = _origine_normalizzata(ricetta.get("origine"))
    if origine in _ORIGINI_RICETTARI_FORNITORI:
        return True
    return any(
        ricetta.get(field)
        for field in (
            "ricettario_saima_id",
            "ricettario_mepa_id",
            "ricettario_acquaviva_id",
            "ricettario_fornitore_id",
        )
    )


def _ricetta_visibile_tablet(ricetta: dict) -> bool:
    """Mostra sulle card operative solo ricette Ceraldi realmente attivate."""
    if ricetta.get("visibile_tablet") is False or ricetta.get("sola_lettura") is True:
        return False
    if ricetta.get("visibile_tablet") is True:
        return True
    return not _riferimento_ricettario_fornitore(ricetta)


def _nomi_ingredienti_ricetta(ricetta: dict) -> List[str]:
    dettagli = ricetta.get("ingredienti_dettaglio") or ricetta.get("ingredienti") or []
    return [
        str(item.get("nome") or "") if isinstance(item, dict) else str(item or "")
        for item in dettagli
    ]


def _reparto_operativo_ricetta(ricetta: dict) -> str:
    """Corregge dolce/salato solo quando nome/base/ingredienti sono chiari."""
    corrente = (ricetta.get("reparto") or "").lower().strip()
    calcolato = _categorizza_reparto(
        ricetta.get("nome", ""),
        ingredienti=_nomi_ingredienti_ricetta(ricetta),
        ricetta_base_nome=ricetta.get("ricetta_base_nome"),
    )
    return _reparto_finale_auto(corrente, calcolato)


def _pulisci_nome_ing(nome: str) -> str:
    if not nome:
        return ""
    cleaned = re.sub(
        r"\s+[A-Z]{1,4}[./][A-Z0-9]{1,10}(?:[./][A-Z0-9]{1,10})*", "", nome, flags=re.IGNORECASE
    )
    cleaned = re.sub(
        r"\s+\d+(?:[.,]\d+)?\s*(?:kg|g|ml|l|lt|cl)\b", "", cleaned, flags=re.IGNORECASE
    )
    cleaned = re.sub(r"\s+\d+$", "", cleaned)
    return " ".join(cleaned.split()).strip()


def _carica_ricettario_excel() -> dict:
    if not _RICETTARIO_EXCEL_PATH.exists():
        raise HTTPException(404, "Bundle dei ricettari Excel non trovato")
    try:
        payload = json.loads(_RICETTARIO_EXCEL_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(500, f"Bundle dei ricettari Excel non leggibile: {exc}") from exc
    recipes = payload.get("recipes") if isinstance(payload, dict) else None
    sources = (payload.get("meta") or {}).get("sources") if isinstance(payload, dict) else None
    if not isinstance(recipes, list) or not recipes or not isinstance(sources, list) or len(sources) != 4:
        raise HTTPException(500, "Bundle dei ricettari Excel incompleto")
    keys = [item.get("chiave") for item in recipes]
    if any(not key for key in keys) or len(keys) != len(set(keys)):
        raise HTTPException(500, "Bundle dei ricettari Excel con nomi mancanti o duplicati")
    return payload


def _dosi_compilate(details: list) -> int:
    return sum(
        isinstance(item, dict) and item.get("quantita") not in (None, "")
        for item in (details or [])
    )


async def _importa_ricettario_excel(anteprima: bool, admin: Optional[dict] = None) -> dict:
    """Integra le quattro fonti senza cancellare foto o correzioni manuali.

    Il nome normalizzato è l'unico criterio di deduplicazione. Le ricette già
    curate a mano mantengono ingredienti e dosi; quelle vuote o provenienti dai
    vecchi import vengono arricchite con la fonte più completa del bundle.
    """
    from app.lotti.routers.utils import _rileva_allergeni

    bundle = _carica_ricettario_excel()
    bundle_hash = (bundle.get("meta") or {}).get("bundle_sha256") or ""
    current = await db.ricette.find({}, {"_id": 0}).to_list(5000)
    groups: dict[str, list[dict]] = {}
    for item in current:
        key = _chiave_ricetta(item.get("nome"))
        if key:
            groups.setdefault(key, []).append(item)

    operations = []
    conflicts = []
    imported_sources = {"cartel1_xlsx", "tracciabilita_xlsm", "ricettari_excel_ceraldi"}
    for source in bundle["recipes"]:
        key = source["chiave"]
        matches = groups.get(key) or []
        if len(matches) > 1:
            conflicts.append({"nome": source.get("nome"), "ids": [item.get("id") for item in matches]})
        existing = matches[0] if matches else None
        source_details = source.get("ingredienti_dettaglio") or []
        source_names = [item.get("nome") for item in source_details if isinstance(item, dict) and item.get("nome")]
        existing_details = (existing or {}).get("ingredienti_dettaglio") or []
        existing_origin = (existing or {}).get("fonte") or (existing or {}).get("origine_ingredienti") or ""
        may_replace_import = existing_origin in imported_sources or existing_origin in {"automatica", "ricettario_excel"}
        use_source_details = bool(source_details) and (
            not existing_details
            or (may_replace_import and _dosi_compilate(source_details) > _dosi_compilate(existing_details))
        )

        desired = {
            "fonti_excel": source.get("fonti_excel") or [],
            "ricettario_excel_bundle_sha256": bundle_hash,
        }
        if use_source_details:
            desired.update({
                "ingredienti": source_names,
                "ingredienti_dettaglio": source_details,
                "origine_ingredienti": "ricettario_excel",
            })
        if source.get("procedimento_testo") and not (existing or {}).get("procedimento_testo"):
            desired["procedimento_testo"] = source["procedimento_testo"]
        if source.get("note") and not (existing or {}).get("note_ricettario"):
            desired["note_ricettario"] = source["note"]
        if source.get("porzioni") and not (existing or {}).get("porzioni"):
            desired["porzioni"] = source["porzioni"]

        if existing:
            changed = any(existing.get(field) != value for field, value in desired.items())
            action = "aggiornata" if changed else "invariata"
            recipe_id = existing["id"]
        else:
            reparto = source.get("reparto_hint") or _categorizza_reparto(source.get("nome"), ingredienti=source_names)
            allergens = _rileva_allergeni(source_names).get("allergeni_presenti", []) if source_names else []
            recipe_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"ceraldiapp:ricettario-excel:{key}"))
            desired = {
                "id": recipe_id,
                "nome": source["nome"],
                "reparto": reparto or "altro",
                "ingredienti": source_names,
                "ingredienti_dettaglio": source_details,
                "porzioni": source.get("porzioni") or 0,
                "note": "",
                "note_ricettario": source.get("note") or "",
                "procedimento_testo": source.get("procedimento_testo") or "",
                "fonti_excel": source.get("fonti_excel") or [],
                "ricettario_excel_bundle_sha256": bundle_hash,
                "fonte": "ricettari_excel_ceraldi",
                "origine_ingredienti": "ricettario_excel",
                "allergeni": allergens,
                "allergeni_auto": allergens,
                "allergeni_verificato": bool(source_names),
                "allergeni_da_confermare": bool(source_names),
                "approvata": True,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            action = "creata"
        operations.append({
            "id": recipe_id,
            "nome": source["nome"],
            "azione": action,
            "campi": desired,
            "ingredienti": len(source_details),
            "preparazione": bool(source.get("procedimento_testo")),
        })

    summary = {
        "totale_bundle": len(bundle["recipes"]),
        "create": sum(item["azione"] == "creata" for item in operations),
        "aggiornate": sum(item["azione"] == "aggiornata" for item in operations),
        "invariate": sum(item["azione"] == "invariata" for item in operations),
        "con_ingredienti": (bundle.get("meta") or {}).get("con_ingredienti", 0),
        "con_preparazione": (bundle.get("meta") or {}).get("con_preparazione", 0),
        "conflitti_esistenti": conflicts,
    }
    if anteprima:
        return {"ok": True, "anteprima": True, "bundle_sha256": bundle_hash, **summary}

    changed = [item for item in operations if item["azione"] != "invariata"]
    backup_id = None
    now = datetime.now(timezone.utc).isoformat()
    if changed:
        backup_id = str(uuid.uuid4())
        await db.ricette_import_backup.insert_one({
            "id": backup_id,
            "tipo": "prima_import_ricettari_excel",
            "bundle_sha256": bundle_hash,
            "created_at": now,
            "operatore": (admin or {}).get("nome") or (admin or {}).get("sub"),
            "ricette": current,
        })
    for item in changed:
        fields = {**item["campi"], "ricettario_excel_imported_at": now}
        if item["azione"] == "creata":
            await db.ricette.insert_one(fields)
        else:
            await db.ricette.update_one({"id": item["id"]}, {"$set": fields})
    return {
        "ok": True,
        "anteprima": False,
        "bundle_sha256": bundle_hash,
        "backup_id": backup_id,
        **summary,
    }


# ─── Endpoints ────────────────────────────────────────────────────────────────
@router.get("/ricette")
async def get_ricette(search: Optional[str] = Query(None)):
    q = {}
    if search:
        q["nome"] = {"$regex": search, "$options": "i"}
    return await db.ricette.find(q, {"_id": 0}).sort("nome", 1).to_list(3000)


@router.post("/ricette/importa-excel")
async def importa_ricettari_excel(
    anteprima: bool = Query(True),
    _admin=Depends(require_admin),
):
    """Importa i quattro ricettari Ceraldi con anteprima, backup e idempotenza."""
    return await _importa_ricettario_excel(anteprima=anteprima, admin=_admin)


@router.get("/ricette-archivio")
async def get_ricette_archivio():
    """Archivio professionale consultabile, collegato senza duplicare le ricette operative.

    Il file importato resta immutabile e conserva foglio/riga/hash della fonte. Quando
    una ricetta ha lo stesso nome di una ricetta Ceraldi, restituiamo il suo id: il
    frontend può aprire l'editor, produrre e stampare con i flussi già esistenti.
    """
    archivio = _carica_archivio_dolce()
    operative = await db.ricette.find(
        {}, {"_id": 0, "id": 1, "nome": 1, "reparto": 1, "foto_url": 1}
    ).to_list(1000)
    per_nome = {_chiave_ricetta(r.get("nome")): r for r in operative if r.get("nome")}

    def collega(item: dict) -> dict:
        risultato = dict(item)
        ricetta = per_nome.get(_chiave_ricetta(item.get("name")))
        if ricetta:
            risultato["ricetta_operativa"] = ricetta
        return risultato

    recipes = [collega(item) for item in archivio.get("recipes", [])]
    components = [collega(item) for item in archivio.get("components", [])]
    return {
        "meta": archivio.get("meta", {}),
        "recipes": recipes,
        "components": components,
        "ricette_operative": len(operative),
        "collegate": sum(1 for item in recipes if item.get("ricetta_operativa")),
    }


@router.get("/ricette-unificate")
async def get_ricette_unificate(search: Optional[str] = Query(None)):
    """Un solo ricettario: ricette operative e fonte importata nella stessa lista.

    A parita di nome la ricetta Ceraldi e il record proprietario e riceve la
    documentazione della fonte; non viene creata una seconda copia. Le voci
    senza corrispondenza restano consultabili e possono essere rese operative
    con l'endpoint dedicato.
    """
    operative = await db.ricette.find({}, {"_id": 0}).sort("nome", 1).to_list(2000)
    per_nome = {_chiave_ricetta(r.get("nome")): r for r in operative if r.get("nome")}
    archivio = _carica_archivio_dolce()
    sole_per_nome = {}
    for item in [*(archivio.get("recipes") or []), *(archivio.get("components") or [])]:
        chiave = _chiave_ricetta(item.get("name"))
        operativa = per_nome.get(chiave)
        if operativa:
            docs = operativa.setdefault("documentazioni_archivio", [])
            docs.append(item)
            operativa.setdefault("documentazione_archivio", item)
            operativa["origine"] = operativa.get("origine") or "ceraldi"
        else:
            esistente = sole_per_nome.get(chiave)
            if esistente:
                esistente.setdefault("documentazioni_archivio", []).append(item)
            else:
                voce = _voce_archivio_unificata(item)
                voce["documentazioni_archivio"] = [item]
                sole_per_nome[chiave] = voce

    tutte = [*operative, *sole_per_nome.values()]
    if search:
        q = _chiave_ricetta(search)
        tutte = [r for r in tutte if q in _chiave_ricetta(
            " ".join([
                str(r.get("nome") or ""),
                str(r.get("ingredienti_testo") or ""),
                str(r.get("procedimento_testo") or ""),
            ])
        )]
    tutte.sort(key=lambda r: _chiave_ricetta(r.get("nome")))
    return tutte


@router.post("/ricette-archivio/{kind}/{archivio_id}/rendi-operativa")
async def rendi_ricetta_archivio_operativa(
    kind: str,
    archivio_id: str,
    _admin=Depends(require_admin),
):
    """Crea una ricetta modificabile dalla fonte, in modo idempotente."""
    if kind not in {"recipe", "component"}:
        raise HTTPException(400, "Tipo archivio non valido")
    archivio = _carica_archivio_dolce()
    chiave_lista = "recipes" if kind == "recipe" else "components"
    item = next(
        (x for x in archivio.get(chiave_lista, []) if str(x.get("id")) == archivio_id),
        None,
    )
    if not item:
        raise HTTPException(404, "Ricetta non trovata nell'archivio")

    chiave_nome = _chiave_ricetta(item.get("name"))
    for esistente in await db.ricette.find({}, {"_id": 0}).to_list(3000):
        if _chiave_ricetta(esistente.get("nome")) == chiave_nome:
            return {"creata": False, "ricetta": esistente}

    dettagli = _righe_ingredienti_archivio(item.get("ingredients"))
    nomi = [r.get("nome") for r in dettagli if r.get("nome")]
    from app.lotti.routers.utils import _rileva_allergeni
    allergeni = (_rileva_allergeni(nomi) or {}).get("allergeni_presenti", []) if nomi else []
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": str(uuid.uuid4()),
        "nome": item.get("name") or "Ricetta importata",
        "reparto": "pasticceria",
        "ingredienti": nomi,
        "ingredienti_dettaglio": dettagli,
        "porzioni": 1,
        "note": "\n\n".join(x for x in [item.get("procedure"), item.get("notes")] if x),
        "procedimento_testo": item.get("procedure") or "",
        "ingredienti_testo": item.get("ingredients") or "",
        "origine": "archivio_importato",
        "archivio_id": item.get("id"),
        "tipo_archivio": kind,
        "fonte_archivio": item.get("source") or "",
        "provenienza_archivio": item.get("provenance") or {},
        "allergeni_auto": allergeni,
        "allergeni": allergeni,
        "allergeni_verificato": bool(nomi),
        "allergeni_da_confermare": bool(nomi),
        "created_at": now,
    }
    await db.ricette.insert_one(doc)
    doc.pop("_id", None)
    return {"creata": True, "ricetta": doc}


@router.get("/ricette-prezzi")
async def get_ricette_prezzi():
    ricette = await db.ricette.find({}, {"_id": 0}).sort("nome", 1).to_list(500)
    dizionario = await db.dizionario_prodotti.find({}, {"_id": 0}).to_list(5000)
    diz_map = {
        (d.get("nome_normalizzato") or "").lower(): d.get("prezzo_kg", 0) or 0 for d in dizionario
    }

    def _pkg(nome: str) -> float:
        nl = nome.lower().strip()
        if nl in diz_map:
            return diz_map[nl]
        for k, v in diz_map.items():
            if nl in k or k in nl:
                return v
        return 0

    risultati = []
    for r in ricette:
        if r.get("ricetta_base_id"):
            continue
        costo_tot = r.get("costo_totale") or 0
        porzioni = max(float(r.get("porzioni") or 1), 1)
        costo_pezzo = costo_tot / porzioni if costo_tot else 0
        prezzo_vendita = r.get("prezzo_vendita") or 0
        margine = (
            ((prezzo_vendita - costo_pezzo) / prezzo_vendita * 100)
            if prezzo_vendita > 0 and costo_pezzo > 0
            else 0
        )
        varianti = [v for v in ricette if v.get("ricetta_base_id") == r["id"]]
        varianti_out = []
        for v in sorted(varianti, key=lambda x: x["nome"]):
            ing_var = v.get("ingrediente_variante") or {}
            costo_var_extra = 0
            if ing_var.get("quantita") and ing_var.get("nome"):
                costo_var_extra = (float(ing_var.get("quantita") or 0) / 1000) * (
                    ing_var.get("costo_unitario") or _pkg(ing_var["nome"])
                )
            costo_var_pezzo = costo_pezzo + costo_var_extra
            pv_var = v.get("prezzo_vendita") or prezzo_vendita
            margine_var = (
                ((pv_var - costo_var_pezzo) / pv_var * 100)
                if pv_var > 0 and costo_var_pezzo > 0
                else 0
            )
            varianti_out.append(
                {
                    "id": v["id"],
                    "nome": v["nome"],
                    "ingrediente_variante": ing_var,
                    "costo_variante_extra": round(costo_var_extra, 4),
                    "costo_pezzo": round(costo_var_pezzo, 4),
                    "prezzo_vendita": pv_var,
                    "margine_pct": round(margine_var, 1),
                }
            )
        risultati.append(
            {
                "id": r["id"],
                "nome": r["nome"],
                "porzioni": porzioni,
                "costo_totale": costo_tot,
                "costo_pezzo": round(costo_pezzo, 4),
                "prezzo_vendita": prezzo_vendita,
                "margine_pct": round(margine, 1),
                "reparto": r.get("reparto", ""),
                "varianti": varianti_out,
            }
        )
    return risultati


@router.get("/ricette/{ricetta_id}/pdf-scheda", response_class=HTMLResponse)
async def scheda_ricetta_pdf(ricetta_id: str):
    """Scheda ricetta stampabile in stile Ceraldi (palette Lotti salvia/crema),
    alimentata dai dati REALI: ingredienti+dosi, costi, allergeni, reparto, foto.
    Procedimento, segreti, varianti e impiattamento sono campi opzionali della
    ricetta: se presenti vengono mostrati, altrimenti la sezione si nasconde."""
    from html import escape as _e
    r = await db.ricette.find_one({"id": ricetta_id}, {"_id": 0})
    if not r:
        raise HTTPException(404, "Ricetta non trovata")

    # ── Cascata allergeni HACCP: per ogni ingrediente, eredita composizione/allergeni
    # del prodotto composto acquistato (margarine, est. zuppa inglese, farciture, ...) ──
    try:
        from app.lotti.routers.schede_tecniche import risolvi_scheda
        from app.lotti.routers.lotti_produzione import peek_lotto_fifo_attivo
        allergeni_cascata = []
        avviso_azoici = False
        for d in (r.get("ingredienti_dettaglio") or []):
            if not isinstance(d, dict):
                continue
            # Prodotto composto reale = quello del LOTTO FIFO-ATTIVO (single source),
            # non un nome_fattura congelato all'import (che poteva essere errato/last-wins).
            lotto = None
            try:
                lotto = await peek_lotto_fifo_attivo(d)
            except Exception:
                lotto = None
            # nome_canonico (atomico, es. "Margarina") per primo: piu' pulito del
            # nome fattura grezzo per trovare la scheda tecnica giusta.
            candidati = [c for c in [(d.get("nome_canonico") or "").strip(),
                                     (d.get("nome") or "").strip(),
                                     ((lotto or {}).get("prodotto_nome") or "").strip()] if c]
            candidati = list(dict.fromkeys(candidati))  # dedup preservando l'ordine
            if not candidati:
                continue
            res = {"trovata": False}
            for cand in candidati:
                try:
                    res = await risolvi_scheda(cand)
                except Exception:
                    res = {"trovata": False}
                if res.get("trovata"):
                    break
            if not res.get("trovata"):
                continue
            sc = res.get("scheda") or {}
            comp = sc.get("composizione") or []
            if comp:
                d["_composizione"] = comp
            if sc.get("url") or sc.get("fonte_url"):
                d["_scheda_url"] = sc.get("url") or sc.get("fonte_url")
            if sc.get("coloranti"):
                d["_coloranti"] = sc["coloranti"]
            if sc.get("avviso_coloranti_azoici"):
                d["_azoici"] = True
                avviso_azoici = True
            for a in (sc.get("allergeni") or []):
                if a and a not in allergeni_cascata:
                    allergeni_cascata.append(a)
        r["_allergeni_cascata"] = allergeni_cascata
        r["_avviso_azoici"] = avviso_azoici
    except Exception:
        pass

    return HTMLResponse(content=_render_scheda_ceraldi(r))


@router.get("/ricette/{ricetta_id}/tracciabilita-fifo")
async def tracciabilita_fifo(ricetta_id: str):
    """Per ogni ingrediente della ricetta ritorna il lotto fornitore FIFO-ATTIVO
    (il piu' vecchio per data_fattura con giacenza residua), DERIVATO al volo.
    Single source della provenienza: sostituisce i campi congelati all'import."""
    r = await db.ricette.find_one({"id": ricetta_id}, {"_id": 0})
    if not r:
        raise HTTPException(404, "Ricetta non trovata")
    from app.lotti.routers.lotti_produzione import peek_lotto_fifo_attivo
    try:
        from app.lotti.routers.schede_tecniche import risolvi_scheda
    except Exception:
        risolvi_scheda = None
    out = []
    for d in (r.get("ingredienti_dettaglio") or []):
        if not isinstance(d, dict):
            continue
        nome = (d.get("nome") or "").strip()
        if not nome:
            continue
        lotto = await peek_lotto_fifo_attivo(d)
        # Cascata HACCP: composizione/allergeni del prodotto composto (scheda tecnica),
        # cercata sul prodotto del lotto attivo e in fallback sul nome ingrediente.
        comp = {}
        if risolvi_scheda:
            # nome_canonico (atomico) per primo: stessa priorita' di pdf-scheda.
            candidati_chiave = [d.get("nome_canonico"), (lotto or {}).get("prodotto_nome"), nome]
            candidati_chiave = list(dict.fromkeys(c for c in candidati_chiave if c))
            for chiave in candidati_chiave:
                if not chiave:
                    continue
                try:
                    sc = await risolvi_scheda(chiave)
                except Exception:
                    sc = None
                if sc and sc.get("trovata"):
                    s = sc.get("scheda") or {}
                    comp = {
                        "composizione": s.get("composizione") or [],
                        "allergeni": s.get("allergeni") or [],
                        "coloranti": s.get("coloranti") or [],
                        "avviso_coloranti_azoici": s.get("avviso_coloranti_azoici") or [],
                        "impiego": s.get("impiego") or "",
                        # link alla scheda tecnica del produttore (ricerca web/scrape)
                        "scheda_url": s.get("url") or s.get("fonte_url") or "",
                    }
                    break
        if lotto:
            out.append({
                "ingrediente": nome,
                "trovato": True,
                "fornitore": lotto.get("fornitore", ""),
                "prodotto": lotto.get("prodotto_nome", ""),
                "lotto_id_fornitore": lotto.get("lotto_id_fornitore", ""),
                "data_fattura": lotto.get("data_fattura", ""),
                "data_scadenza": lotto.get("data_scadenza", ""),
                "quantita_disponibile": lotto.get("quantita_disponibile", 0),
                "unita_misura": lotto.get("unita_misura", ""),
                **comp,
            })
        else:
            out.append({"ingrediente": nome, "trovato": False, **comp})
    return {"ricetta": r.get("nome", ""), "ingredienti": out}


@router.post("/ricette/pulisci-riferimenti-congelati")
async def pulisci_riferimenti_congelati(_admin=Depends(require_admin)):
    """One-shot: rimuove dai dettagli ingrediente i campi-provenienza CONGELATI
    all'import (last-wins) ormai inutilizzati — la provenienza e' DERIVATA dal lotto
    FIFO-attivo. Campi rimossi: fornitore, numero_fattura, data_fattura, data_scadenza,
    lotto_fornitore, aggiornato_il, nome_fattura. Niente dati morti/fuorvianti."""
    STALE = ("fornitore", "numero_fattura", "data_fattura", "data_scadenza",
             "lotto_fornitore", "aggiornato_il", "nome_fattura")
    ricette = await db.ricette.find(
        {}, {"_id": 0, "id": 1, "ingredienti_dettaglio": 1}
    ).to_list(2000)
    n_ric = 0
    n_campi = 0
    for r in ricette:
        det = r.get("ingredienti_dettaglio") or []
        changed = False
        for d in det:
            if isinstance(d, dict):
                for k in STALE:
                    if k in d:
                        d.pop(k, None)
                        changed = True
                        n_campi += 1
        if changed:
            await db.ricette.update_one(
                {"id": r["id"]},
                {
                    "$set": {"ingredienti_dettaglio": det},
                    "$unset": {"ultima_fattura_fornitore": "", "ingredienti_aggiornati_il": ""},
                },
            )
            n_ric += 1
    return {"ricette_pulite": n_ric, "campi_rimossi": n_campi}


def _render_scheda_ceraldi(r: dict) -> str:
    """Costruisce l'HTML della scheda. Funzione pura: testabile e riusabile."""
    from html import escape as _e

    nome = _e(str(r.get("nome", "Ricetta")))
    reparto = _e(str(r.get("reparto", "") or ""))
    porzioni = r.get("porzioni") or 0
    costo_tot = r.get("costo_totale")
    costo_porz = r.get("costo_porzione")
    note = _e(str(r.get("note", "") or ""))
    foto = r.get("foto_url") or ""
    allergeni = r.get("allergeni") or []
    occhiello = _e(str(r.get("occhiello", "") or ""))

    # ── INGREDIENTI (dati reali) ──
    det = r.get("ingredienti_dettaglio", []) or []
    simp = r.get("ingredienti", []) or []
    ig_rows = ""
    if det:
        for d in det:
            n = _e(str(d.get("nome", "")))
            q = d.get("quantita", "")
            u = _e(str(d.get("unita_misura", d.get("unita", ""))))
            qta = f"{q:g}".rstrip("0").rstrip(".") if isinstance(q, (int, float)) else _e(str(q))
            ig_rows += f'<div class="ig"><span class="nome">{n}</span><span class="q">{qta} {u}</span></div>'
            comp_ing = d.get("_composizione") or []
            if comp_ing:
                comp_txt = _e(", ".join(str(c) for c in comp_ing))
                azo = ' <b style="color:#b00020">⚠ coloranti azoici</b>' if d.get("_azoici") else ""
                link_sc = ""
                if d.get("_scheda_url"):
                    link_sc = (f' <a href="{_e(str(d["_scheda_url"]))}" '
                               f'style="color:#5b7a6b;font-size:9px">scheda tecnica ↗</a>')
                ig_rows += (f'<div style="font-size:9px;color:#777;line-height:1.3;'
                            f'margin:-3px 0 7px 2px">↳ {comp_txt}{azo}{link_sc}</div>')
    elif simp:
        for s in simp:
            ig_rows += f'<div class="ig"><span class="nome">{_e(str(s))}</span></div>'
    else:
        ig_rows = '<div class="vuoto">Nessun ingrediente inserito.</div>'

    # ── meta dinamica ──
    meta = []
    if reparto:
        meta.append(("Reparto", reparto.capitalize()))
    if porzioni:
        pz = f"{porzioni:g}" if isinstance(porzioni, (int, float)) else str(porzioni)
        meta.append(("Porzioni", pz))
    if costo_tot is not None:
        meta.append(("Costo totale", f"€ {float(costo_tot):.2f}".replace(".", ",")))
    if costo_porz is not None:
        meta.append(("Costo/porz", f"€ {float(costo_porz):.2f}".replace(".", ",")))
    if not meta:
        meta.append(("Scheda", "Ricetta"))
    meta_html = "".join(f'<div><div class="k">{_e(k)}</div><div class="v">{_e(v)}</div></div>' for k, v in meta)

    # ── copertina (foto se presente) ──
    cover_html = ""
    if foto:
        cover_html = f'<div class="cover" style="background-image:url(\'{_e(foto)}\')"></div>'

    # ── PROCEDIMENTO (campo opzionale: lista di passi o testo) ──
    proc = r.get("procedimento") or []
    proc_html = ""
    if isinstance(proc, str) and proc.strip():
        proc = [p.strip() for p in proc.split("\n") if p.strip()]
    if isinstance(proc, list) and proc:
        passi = ""
        for i, p in enumerate(proc, 1):
            if isinstance(p, dict):
                titolo = _e(str(p.get("titolo", "")))
                testo = _e(str(p.get("testo", p.get("descrizione", ""))))
                b = f"<b>{titolo}.</b> " if titolo else ""
                passi += f'<div class="passo"><span class="num">{i}</span><span class="txt">{b}{testo}</span></div>'
            else:
                passi += f'<div class="passo"><span class="num">{i}</span><span class="txt">{_e(str(p))}</span></div>'
        critico = r.get("dettaglio_critico") or ""
        crit_html = f'<div class="critico">⚠ {_e(str(critico))}</div>' if critico else ""
        proc_html = f"""<section class="sezione"><div class="h"><span class="n">2</span><h2>Procedimento</h2><span class="sotto">passo dopo passo</span></div>
        <div class="passi">{passi}</div>{crit_html}</section>"""

    # ── SEGRETI & DATI ──
    consigli = r.get("consigli") or []
    errore = r.get("errore_da_evitare") or ""
    nutr = r.get("nutrizionale") or r.get("nutrizione") or r.get("valori_nutrizionali") or {}
    box = []
    if consigli:
        li = "".join(f"<li>{_e(str(c))}</li>" for c in consigli)
        box.append(f'<div class="box"><div class="et ok">✓ Consigli dello chef</div><ul>{li}</ul></div>')
    if errore:
        box.append(f'<div class="box"><div class="et no">✕ Errore da evitare</div><p>{_e(str(errore))}</p></div>')
    def _raw(k):
        v = nutr.get(k) if isinstance(nutr, dict) else None
        if v in (None, ""):
            return None
        try:
            return float(str(v).replace(",", "."))
        except (TypeError, ValueError):
            return None

    # Peso della porzione, ricavato dagli ingredienti a peso (g/kg/ml/l).
    def _grammi(q, u):
        try:
            q = float(str(q).replace(",", "."))
        except (TypeError, ValueError):
            return 0.0
        u = (str(u or "")).lower().strip()
        if u in ("g", "gr", "grammi", "ml"):
            return q
        if u in ("kg", "l", "lt", "litri"):
            return q * 1000
        return 0.0

    peso_tot = sum(_grammi(d.get("quantita"), d.get("unita_misura", d.get("unita", ""))) for d in (det or []))
    porz_n = float(porzioni) if isinstance(porzioni, (int, float)) and porzioni else 0
    peso_porz = (peso_tot / porz_n) if (peso_tot > 0 and porz_n) else 0
    fp = peso_porz / 100.0 if peso_porz else 0

    def _fmt(v, unit):
        return f"{v:g} {unit}".strip() if v is not None else "—"

    # Righe: (label, valore_per_100g, unità, indent). Energia gestita a parte.
    nutri_rows = []
    if _raw("kcal") is not None or _raw("kj") is not None:
        e100 = " / ".join(x for x in (_fmt(_raw("kcal"), "kcal") if _raw("kcal") is not None else None,
                                      _fmt(_raw("kj"), "kJ") if _raw("kj") is not None else None) if x)
        eporz = ""
        if fp:
            eporz = " / ".join(x for x in (_fmt(round(_raw("kcal") * fp), "kcal") if _raw("kcal") is not None else None,
                                           _fmt(round(_raw("kj") * fp), "kJ") if _raw("kj") is not None else None) if x)
        nutri_rows.append(("Energia", e100, eporz, False))
    for label, key, indent in [
        ("Grassi", "grassi", False),
        ("di cui acidi grassi saturi", "saturi", True),
        ("Carboidrati", "carboidrati", False),
        ("di cui zuccheri", "zuccheri", True),
        ("Fibre", "fibre", False),
        ("Proteine", "proteine", False),
        ("Sale", "sale", False),
    ]:
        v = _raw(key)
        if v is not None:
            v100 = _fmt(round(v, 1), "g")
            vporz = _fmt(round(v * fp, 1), "g") if fp else ""
            nutri_rows.append((label, v100, vporz, indent))

    if nutri_rows:
        has_porz = bool(fp)
        th_porz = f'<th style="text-align:right;padding:5px 8px;font-size:9px;color:#888;font-weight:600">per porzione<br><span style="font-weight:400">~{peso_porz:.0f} g</span></th>' if has_porz else ""
        trs = ""
        for label, v100, vporz, indent in nutri_rows:
            pad = "padding-left:18px;color:#666;font-weight:400" if indent else "font-weight:600"
            td_porz = (f'<td style="padding:5px 8px;border-bottom:1px solid #eee;text-align:right;'
                       f'font-variant-numeric:tabular-nums;white-space:nowrap;color:#555">{_e(vporz)}</td>') if has_porz else ""
            trs += (
                f'<tr><td style="padding:5px 8px;border-bottom:1px solid #eee;{pad}">{_e(label)}</td>'
                f'<td style="padding:5px 8px;border-bottom:1px solid #eee;text-align:right;'
                f'font-variant-numeric:tabular-nums;white-space:nowrap">{_e(v100)}</td>{td_porz}</tr>'
            )
        head = ('<tr><th style="text-align:left;padding:5px 8px;font-size:9px;color:#888;font-weight:600"></th>'
                '<th style="text-align:right;padding:5px 8px;font-size:9px;color:#888;font-weight:600">per 100 g</th>'
                f'{th_porz}</tr>')
        box.append(
            '<div class="box"><div class="et dat">★ Dichiarazione nutrizionale</div>'
            '<div style="font-size:9px;color:#888;margin:-2px 0 6px">Valori medi'
            + (' — per 100 g e per porzione' if fp else ' per 100 g') + '</div>'
            f'<table style="width:100%;border-collapse:collapse;font-size:11px"><thead>{head}</thead><tbody>{trs}</tbody></table></div>'
        )
    if costo_porz is not None or costo_tot is not None:
        celle = ""
        if costo_porz is not None:
            celle += f'<div><div class="vv">€{float(costo_porz):.2f}</div><div class="kk">costo/porz</div></div>'
        if costo_tot is not None:
            celle += f'<div><div class="vv">€{float(costo_tot):.2f}</div><div class="kk">costo totale</div></div>'
        box.append(f'<div class="box"><div class="et dat">★ Costo</div><div class="nutri">{celle}</div></div>')
    segreti_html = ""
    if box:
        segreti_html = f'<section class="sezione"><div class="h"><span class="n">3</span><h2>Segreti &amp; dati</h2></div><div class="tre">{"".join(box)}</div></section>'

    # ── IMPIATTAMENTO ──
    impiatto = r.get("impiattamento") or []
    impiatto_html = ""
    if isinstance(impiatto, str) and impiatto.strip():
        impiatto = [impiatto.strip()]
    if isinstance(impiatto, list) and impiatto:
        elems = ""
        for it in impiatto:
            if isinstance(it, dict):
                t = _e(str(it.get("elemento", it.get("nome", ""))))
                d = _e(str(it.get("nota", it.get("descrizione", ""))))
                elems += f'<div class="var"><span class="pall"></span><div><div class="nome">{t}</div><div class="desc">{d}</div></div></div>'
            else:
                elems += f'<div class="var"><span class="pall"></span><div><div class="nome">{_e(str(it))}</div></div></div>'
        impiatto_html = f'<section class="sezione"><div class="h"><span class="n">5</span><h2>Impiattamento</h2><span class="sotto">a modo nostro</span></div><div class="varianti">{elems}</div></section>'

    # ── VARIANTI ──
    varianti = r.get("varianti") or []
    var_html = ""
    if isinstance(varianti, list) and varianti:
        vv = ""
        for v in varianti:
            if isinstance(v, dict):
                t = _e(str(v.get("nome", "")))
                d = _e(str(v.get("descrizione", v.get("desc", ""))))
                vv += f'<div class="var"><span class="pall"></span><div><div class="nome">{t}</div><div class="desc">{d}</div></div></div>'
            else:
                vv += f'<div class="var"><span class="pall"></span><div><div class="nome">{_e(str(v))}</div></div></div>'
        var_html = f'<section class="sezione"><div class="h"><span class="n">6</span><h2>Varianti</h2><span class="sotto">stessa base, tante idee</span></div><div class="varianti">{vv}</div></section>'

    # ── allergeni (manuali della ricetta + ereditati a cascata dai prodotti composti) + note ──
    extra_html = ""
    allerg_tutti = list(dict.fromkeys(list(allergeni) + (r.get("_allergeni_cascata") or [])))
    if allerg_tutti:
        chips = "".join(f'<span class="chip">{_e(str(a))}</span>' for a in allerg_tutti)
        extra_html += f'<div class="allerg"><span class="lab">Allergeni</span>{chips}</div>'
    if r.get("_avviso_azoici"):
        extra_html += ('<div class="riposo" style="color:#b00020;font-size:11px;line-height:1.4">'
                       '⚠ Contiene coloranti azoici (E102/E110/E122/E124/E129): '
                       'può influire negativamente su attività e attenzione dei bambini.</div>')
    if note:
        extra_html += f'<div class="riposo">{note}</div>'

    occhiello_html = f'<div class="occhiello">{occhiello}</div>' if occhiello else ""
    rep_html = f'<div class="eyebrow">{reparto.capitalize()}</div>' if reparto else ""

    return f"""<!doctype html><html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Scheda — {nome}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:ital,wght@0,400;0,500;0,600;0,700;0,800;1,600&family=Fraunces:opsz,ital,wght@9..144,0,500;9..144,0,600;9..144,0,700;9..144,0,900;9..144,1,500&display=swap" rel="stylesheet">
<style>
:root{{--salvia:#5b7a6b;--verde:#3d8168;--crema:#faf7f0;--carta:#fffefb;--linea:#e6e0d4;--ink:#2a3329;--muto:#6b7669;--caldo:#8a6f47;--soft:#e8efe9;--rosso:#d35f4e;--ambra:#c4894a;}}
*{{box-sizing:border-box;}}
html,body{{margin:0;padding:0;background:#ded8c9;color:var(--ink);font-family:'Plus Jakarta Sans',system-ui,sans-serif;-webkit-text-size-adjust:100%;}}
.wrap{{width:100%;max-width:820px;margin:0 auto;padding:14px;}}
.foglio{{background:var(--carta);border-radius:18px;overflow:hidden;box-shadow:0 10px 40px rgba(42,51,41,.16);}}
.cover{{height:200px;background-size:cover;background-position:center;}}
.testata{{background:linear-gradient(135deg,var(--salvia),var(--verde));color:#fff;padding:clamp(20px,5vw,30px) clamp(18px,5vw,34px) clamp(18px,4vw,22px);}}
.marchio{{display:flex;align-items:center;gap:12px;}}
.logo{{width:42px;height:42px;border-radius:11px;background:rgba(255,255,255,.16);display:grid;place-items:center;font-family:'Fraunces',serif;font-weight:900;font-size:22px;flex:none;}}
.marchio .nome{{font-weight:800;font-size:14px;letter-spacing:.5px;line-height:1.1;}}
.marchio .sub{{font-size:11px;opacity:.82;font-weight:500;}}
.eyebrow{{margin-top:16px;font-size:11px;font-weight:700;letter-spacing:2.5px;text-transform:uppercase;opacity:.78;}}
h1.titolo{{font-family:'Fraunces',serif;font-weight:900;font-size:clamp(26px,7vw,40px);line-height:1.04;margin:4px 0 0;letter-spacing:-.5px;}}
.occhiello{{margin-top:8px;font-size:clamp(12px,3.4vw,14px);opacity:.92;font-style:italic;font-family:'Fraunces',serif;}}
.meta{{display:grid;grid-template-columns:repeat(auto-fit,minmax(80px,1fr));margin-top:18px;border-top:1px solid rgba(255,255,255,.2);}}
.meta div{{padding:11px 6px 3px;text-align:center;border-right:1px solid rgba(255,255,255,.14);}}
.meta div:last-child{{border-right:none;}}
.meta .k{{font-size:9.5px;letter-spacing:1px;text-transform:uppercase;opacity:.72;font-weight:700;}}
.meta .v{{font-size:clamp(13px,3.6vw,17px);font-weight:800;margin-top:3px;line-height:1.15;}}
.corpo{{padding:clamp(20px,5vw,30px);}}
.sezione+.sezione{{margin-top:clamp(22px,5vw,28px);}}
.h{{display:flex;align-items:center;gap:10px;margin:0 0 14px;flex-wrap:wrap;}}
.h .n{{font-family:'Fraunces',serif;font-weight:700;font-size:15px;color:#fff;background:var(--salvia);width:27px;height:27px;border-radius:8px;display:grid;place-items:center;flex:none;}}
.h h2{{font-family:'Fraunces',serif;font-weight:700;font-size:clamp(18px,5vw,21px);margin:0;color:var(--verde);}}
.h .sotto{{font-size:12px;color:var(--muto);font-weight:500;margin-left:auto;}}
.ingr{{display:grid;grid-template-columns:1fr 1fr;gap:6px 24px;}}
.ig{{display:flex;align-items:baseline;justify-content:space-between;gap:10px;padding:9px 2px;border-bottom:1px dotted var(--linea);}}
.ig .nome{{font-weight:600;font-size:14px;}}
.ig .q{{font-weight:800;font-size:14px;color:var(--verde);white-space:nowrap;}}
.vuoto{{color:var(--muto);font-size:13px;}}
.passi{{display:grid;gap:11px;}}
.passo{{display:flex;gap:13px;align-items:flex-start;}}
.passo .num{{flex:none;width:27px;height:27px;border-radius:50%;background:var(--salvia);color:#fff;display:grid;place-items:center;font-weight:800;font-size:13px;}}
.passo .txt{{font-size:13.5px;line-height:1.5;padding-top:3px;}}
.passo .txt b{{color:var(--verde);}}
.critico{{background:#fbf2df;border-left:3px solid var(--ambra);border-radius:8px;padding:10px 14px;font-size:12.5px;font-weight:600;color:#7d5a1d;margin:6px 0 6px 40px;}}
.riposo{{background:var(--soft);border-left:3px solid var(--salvia);border-radius:8px;padding:11px 14px;font-size:12.5px;font-weight:600;color:var(--ink);margin-top:12px;}}
.tre{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;}}
.box{{border:1px solid var(--linea);border-radius:12px;padding:13px 14px;background:#fff;}}
.box .et{{font-size:10.5px;font-weight:800;letter-spacing:.8px;text-transform:uppercase;margin:0 0 8px;}}
.box ul{{margin:0;padding-left:15px;}}
.box li{{font-size:12px;line-height:1.5;margin-bottom:5px;}}
.box p{{margin:0;font-size:12px;line-height:1.5;}}
.et.ok{{color:var(--verde);}}.et.no{{color:var(--rosso);}}.et.dat{{color:var(--salvia);}}
.nutri{{display:flex;}}
.nutri div{{flex:1;text-align:center;padding:7px 2px;border-right:1px solid var(--linea);}}
.nutri div:last-child{{border-right:none;}}
.nutri .vv{{font-weight:800;font-size:16px;color:var(--verde);}}
.nutri .kk{{font-size:9px;text-transform:uppercase;letter-spacing:.4px;color:var(--muto);font-weight:700;margin-top:2px;}}
.varianti{{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;}}
.var{{display:flex;gap:10px;align-items:flex-start;background:var(--crema);border-radius:10px;padding:11px 13px;}}
.var .pall{{width:8px;height:8px;border-radius:50%;background:var(--verde);margin-top:6px;flex:none;}}
.var .nome{{font-weight:800;font-size:13px;color:var(--verde);}}
.var .desc{{font-size:11.5px;color:var(--muto);font-weight:500;margin-top:1px;}}
.allerg{{margin-top:14px;display:flex;align-items:center;gap:8px;flex-wrap:wrap;}}
.allerg .lab{{font-size:10.5px;font-weight:800;letter-spacing:.8px;text-transform:uppercase;color:var(--rosso);}}
.chip{{background:#fbeae7;color:#a23b2c;border:1px solid #f0cfc9;border-radius:999px;padding:3px 11px;font-size:11.5px;font-weight:700;}}
.pie{{margin-top:26px;border-top:2px solid var(--soft);padding-top:14px;display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;}}
.pie .firma{{font-family:'Fraunces',serif;font-style:italic;font-size:14px;color:var(--verde);}}
.pie .cod{{font-size:10px;color:var(--muto);font-weight:600;letter-spacing:.5px;}}
.barra{{position:sticky;top:0;z-index:9;background:var(--ink);color:#fff;display:flex;gap:12px;align-items:center;justify-content:space-between;padding:11px 16px;font-size:13px;border-radius:12px;margin-bottom:14px;}}
.barra button{{background:var(--verde);color:#fff;border:none;border-radius:9px;padding:10px 18px;font-weight:800;font-size:13px;cursor:pointer;font-family:inherit;flex:none;}}
@media (max-width:640px){{.tre{{grid-template-columns:1fr;}}}}
@media (max-width:480px){{.ingr{{grid-template-columns:1fr;}}.varianti{{grid-template-columns:1fr;}}}}
@media print{{.barra{{display:none;}}html,body{{background:#fff;}}.wrap{{max-width:none;padding:0;}}.foglio{{box-shadow:none;border-radius:0;}}@page{{size:A4;margin:12mm;}}}}
</style></head><body>
<div class="wrap">
  <div class="barra"><span>Scheda pronta per la stampa (A4)</span><button onclick="window.print()">Stampa / Salva PDF</button></div>
  <div class="foglio">
    {cover_html}
    <div class="testata">
      <div class="marchio"><div class="logo">C</div><div><div class="nome">CERALDI GROUP</div><div class="sub">Pasticceria · Schede ricette</div></div></div>
      {rep_html}
      <h1 class="titolo">{nome}</h1>
      {occhiello_html}
      <div class="meta">{meta_html}</div>
    </div>
    <div class="corpo">
      <section class="sezione"><div class="h"><span class="n">1</span><h2>Ingredienti</h2></div><div class="ingr">{ig_rows}</div>{extra_html}</section>
      {proc_html}
      {segreti_html}
      {impiatto_html}
      {var_html}
      <div class="pie"><div class="firma">Ceraldi Group · Napoli</div><div class="cod">Conforme Reg. CE 178/2002</div></div>
    </div>
  </div>
</div></body></html>"""


@router.get("/ricette/export/pdf", response_class=HTMLResponse)
async def export_pdf():
    ricette = await db.ricette.find({}, {"_id": 0}).sort("nome", 1).to_list(1000)
    idx = "".join(f'<div class="ii">{i+1}. {r.get("nome","")}</div>' for i, r in enumerate(ricette))
    cards = []
    for i, r in enumerate(ricette, 1):
        det = r.get("ingredienti_dettaglio", [])
        simp = r.get("ingredienti", [])
        por = r.get("porzioni", 0)
        note = r.get("note", "")
        if det:
            ing_html = (
                "<table class='t'><tr><th>Ingrediente</th><th>Qtà</th><th>U</th></tr>"
                + "".join(
                    f"<tr><td>{d.get('nome','')}</td><td>{d.get('quantita','')}</td><td>{d.get('unita','')}</td></tr>"
                    for d in det
                )
                + "</table>"
            )
        elif simp:
            ing_html = (
                "<div class='is'>" + "".join(f"<span class='i'>{s}</span>" for s in simp) + "</div>"
            )
        else:
            ing_html = "<p style='color:#999'>Nessun ingrediente</p>"
        por_html = f"<span class='p'>{por} porzioni</span>" if por else ""
        nota_html = f"<div class='note'>{note}</div>" if note else ""
        cards.append(
            f"<div class='r'><div class='rh'><h3>{i}. {r.get('nome','')}</h3>{por_html}</div><div class='rb'>{ing_html}{nota_html}</div></div>"
        )
    data_gen = datetime.now().strftime("%d/%m/%Y %H:%M")
    html = f"""<!DOCTYPE html><html lang="it"><head><meta charset="UTF-8"><title>Ricettario</title>
<style>@page{{size:A4;margin:15mm}}body{{font-family:Arial;font-size:11pt;color:#333}}
h1{{color:#2e7d32;text-align:center}}.r{{border:1px solid #ddd;border-radius:8px;margin:12px 0;page-break-inside:avoid}}
.rh{{background:#4caf50;color:white;padding:8px 12px;border-radius:8px 8px 0 0;display:flex;justify-content:space-between;align-items:center}}
.rh h3{{margin:0;font-size:13pt}}.p{{background:rgba(255,255,255,0.2);padding:2px 8px;border-radius:10px;font-size:9pt}}
.rb{{padding:12px}}.t{{width:100%;border-collapse:collapse}}.t th{{background:#f5f5f5;padding:6px;border-bottom:2px solid #4caf50;text-align:left}}
.t td{{padding:6px;border-bottom:1px solid #eee}}.is{{display:flex;flex-wrap:wrap;gap:6px}}.i{{background:#f5f5f5;padding:4px 10px;border-radius:12px;font-size:10pt}}
.ii{{padding:2px 0;border-bottom:1px dotted #ddd;font-size:10pt}}.note{{font-style:italic;color:#666;padding:8px;background:#fff8e1;border-radius:4px;margin-top:8px}}
#idx{{column-count:3;column-gap:20px}}@media print{{button{{display:none}}}}
</style></head><body>
<h1>RICETTARIO — Ceraldi Group S.R.L.</h1>
<p style="text-align:center;color:#666">Generato il {data_gen} | {len(ricette)} ricette</p>
<div style="text-align:center;margin:16px"><button onclick="window.print()" style="padding:10px 24px;background:#4caf50;color:white;border:none;border-radius:6px;font-size:13pt;cursor:pointer">Stampa / Salva PDF</button></div>
<h2>Indice</h2><div id="idx">{idx}</div>
<div style="page-break-before:always"></div><h2>Dettaglio</h2>
{"".join(cards)}
<p style="text-align:center;margin-top:24px;color:#999;font-size:9pt">Conforme Reg. CE 178/2002</p>
</body></html>"""
    return HTMLResponse(content=html)


@router.get("/ricette/export/csv")
async def export_csv():
    ricette = await db.ricette.find({}, {"_id": 0}).sort("nome", 1).to_list(1000)
    rows = ["ID;Nome;Porzioni;Ingrediente;Quantità;Unità;Data"]
    for r in ricette:
        nome = r.get("nome", "").replace(";", ",")
        rid = r.get("id", "")
        porzioni = r.get("porzioni", 1)
        created = r.get("created_at", "")[:10]
        det = r.get("ingredienti_dettaglio", [])
        simp = r.get("ingredienti", [])
        if det:
            for d in det:
                rows.append(
                    f'"{rid}";"{nome}";{porzioni};"{d.get("nome","")}";"{d.get("quantita","")}";"{d.get("unita","")}";"{created}"'
                )
        elif simp:
            for s in simp:
                rows.append(f'"{rid}";"{nome}";{porzioni};"{s}";"";"";":{created}"')
        else:
            rows.append(f'"{rid}";"{nome}";{porzioni};"";"";"";"{created}"')
    filename = f"ricettario_{datetime.now().strftime('%Y%m%d')}.csv"
    return Response(
        content="\n".join(rows).encode("utf-8-sig"),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/ricette/export/template-csv")
async def export_template_csv():
    """
    Esporta template CSV compilabile per importare nuove ricette o aggiornare quelle esistenti.
    Formato: AZIONE;ID;Nome;Porzioni;Reparto;Note;Ingrediente_1;Q1;UM1;Ingrediente_2;Q2;UM2;...
    AZIONE: NUOVA = crea nuova, AGGIORNA = aggiorna esistente, SALTA = ignora riga
    """
    import io, csv as _csv

    ricette = await db.ricette.find({}, {"_id": 0}).sort("nome", 1).to_list(1000)

    # Determina il numero massimo di ingredienti
    max_ing = max(
        (len(r.get("ingredienti_dettaglio") or r.get("ingredienti", [])) for r in ricette),
        default=0,
    )
    max_ing = max(max_ing, 5)  # minimo 5 colonne ingredienti per template

    output = io.StringIO()
    writer = _csv.writer(output, delimiter=";", quotechar='"', quoting=_csv.QUOTE_MINIMAL)

    # Riga intestazione
    intestazione = ["AZIONE", "ID", "Nome_Ricetta", "Porzioni", "Reparto", "Note", "Allergeni"]
    for i in range(1, max_ing + 1):
        intestazione += [f"Ingrediente_{i}", f"Quantita_{i}", f"Unita_{i}"]
    writer.writerow(intestazione)

    # Riga istruzioni (commentata)
    istruzioni = [
        "# ISTRUZIONI",
        "# (lascia vuoto per nuova)",
        "# Nome obbligatorio",
        "# Numero pezzi per ricetta",
        "# pasticceria/rosticceria/bar",
        "# Note libere",
        "# Es: Glutine|Latte|Uova",
    ]
    while len(istruzioni) < len(intestazione):
        istruzioni.append("")
    writer.writerow(istruzioni)

    # Riga esempio
    esempio = [
        "NUOVA",
        "",
        "Cornetto al Cioccolato",
        "12",
        "pasticceria",
        "Ricetta classica",
        "Glutine|Uova|Latte",
        "Farina 00",
        "500",
        "g",
        "Burro",
        "200",
        "g",
        "Uova",
        "3",
        "pz",
    ]
    while len(esempio) < len(intestazione):
        esempio.append("")
    writer.writerow(esempio)

    # Separatore
    writer.writerow(["---DATI ESISTENTI---"] + [""] * (len(intestazione) - 1))

    # Esporta ricette esistenti
    for r in ricette:
        det = r.get("ingredienti_dettaglio") or []
        simp = r.get("ingredienti") or []
        allergeni = "|".join(r.get("allergeni") or [])
        reparto = r.get("reparto") or ""

        riga = [
            "AGGIORNA",
            r.get("id", ""),
            r.get("nome", ""),
            str(r.get("porzioni", 1)),
            reparto,
            (r.get("note", "") or "").replace("\n", " ")[:100],
            allergeni,
        ]

        if det:
            for ing in det[:max_ing]:
                nome_ing = ing.get("nome", "")
                qty = ing.get("quantita", "") or ing.get("q", "")
                um = ing.get("unita_misura", "") or ing.get("unita", "") or ing.get("um", "")
                riga += [nome_ing, str(qty), um]
        elif simp:
            for s in simp[:max_ing]:
                riga += [s, "", ""]
        # Padding
        while len(riga) < len(intestazione):
            riga.append("")
        writer.writerow(riga)

    csv_content = output.getvalue()
    filename = f"ricettario_template_{datetime.now().strftime('%Y%m%d')}.csv"
    return Response(
        content=csv_content.encode("utf-8-sig"),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/ricette/import/csv")
async def import_csv_ricette(
    file: bytes = Body(..., media_type="application/octet-stream"),
    anteprima: bool = Query(False),
    nome_file: str = Query("ricette_import.csv"),
    aggiorna_omonime: bool = Query(False),
    _admin=Depends(require_admin),
):
    """
    Importa ricette da CSV con template. Supporta NUOVA e AGGIORNA.
    Se anteprima=True restituisce solo il piano di importazione senza salvare.
    """
    import io, csv as _csv

    try:
        testo = file.decode("utf-8-sig").strip()
    except Exception:
        raise HTTPException(400, "File non decodificabile. Usare UTF-8.")

    aggiorna_omonime_confermato = aggiorna_omonime is True

    reader = _csv.reader(io.StringIO(testo), delimiter=";")
    righe = list(reader)

    if not righe:
        return {"errore": "File vuoto"}

    # Trova intestazione (prima riga che inizia con AZIONE)
    header_idx = next(
        (i for i, r in enumerate(righe) if r and r[0].strip().upper() in ("AZIONE", "ACTION")), None
    )
    if header_idx is None:
        raise HTTPException(400, "Intestazione AZIONE non trovata nel file")

    header = [h.strip() for h in righe[header_idx]]
    dati = righe[header_idx + 1 :]

    def get_col(riga, nome):
        try:
            return riga[header.index(nome)].strip() if nome in header else ""
        except (ValueError, IndexError):
            return ""

    # Estrai colonne ingredienti dinamiche
    ing_cols = [h for h in header if h.startswith("Ingrediente_")]

    ricette_esistenti = await db.ricette.find(
        {}, {"_id": 0, "id": 1, "nome": 1}
    ).to_list(5000)
    esistenti_per_nome = {
        _chiave_ricetta(item.get("nome")): item
        for item in ricette_esistenti
        if _chiave_ricetta(item.get("nome"))
    }
    id_esistenti = {str(item.get("id")) for item in ricette_esistenti if item.get("id")}
    nomi_nuovi_nel_file = set()
    digest_file = hashlib.sha256(file).hexdigest()
    nome_file_sicuro = Path(nome_file or "ricette_import.csv").name

    plan = {"nuove": [], "aggiornate": [], "saltate": [], "errori": []}

    for i, riga in enumerate(dati):
        if not riga or not riga[0].strip():
            continue
        azione = riga[0].strip().upper()
        if azione.startswith("#") or azione.startswith("---"):
            continue
        if azione == "SALTA":
            plan["saltate"].append({
                "nome": get_col(riga, "Nome_Ricetta") or f"riga {i+1}",
                "motivo": "riga marcata SALTA nel file",
            })
            continue

        nome = get_col(riga, "Nome_Ricetta")
        if not nome:
            plan["errori"].append(f"Riga {i+1}: Nome_Ricetta mancante")
            continue

        porzioni = 1
        try:
            porzioni = int(float(get_col(riga, "Porzioni") or "1"))
        except Exception:
            _LOG_INIT.debug("[ricette] errore non bloccante ignorato")

        reparto = get_col(riga, "Reparto")
        note = get_col(riga, "Note")
        allergeni_str = get_col(riga, "Allergeni")
        allergeni = (
            [a.strip() for a in allergeni_str.split("|") if a.strip()] if allergeni_str else []
        )
        rid = get_col(riga, "ID")

        # Estrai ingredienti
        ingredienti_dettaglio = []
        for ic in ing_cols:
            n_idx = header.index(ic)
            num = int(ic.replace("Ingrediente_", ""))
            q_col = f"Quantita_{num}"
            u_col = f"Unita_{num}"
            nome_ing = riga[n_idx].strip() if n_idx < len(riga) else ""
            qty_raw = (
                riga[header.index(q_col)].strip()
                if q_col in header and header.index(q_col) < len(riga)
                else ""
            )
            um = (
                riga[header.index(u_col)].strip()
                if u_col in header and header.index(u_col) < len(riga)
                else ""
            )
            if nome_ing:
                try:
                    qty = float(qty_raw.replace(",", ".")) if qty_raw else None
                except Exception:
                    qty = None
                ingredienti_dettaglio.append(
                    {
                        "nome": nome_ing,
                        "quantita": qty,
                        "unita_misura": um,
                        "unita": um,
                    }
                )

        doc = {
            "nome": nome,
            "porzioni": porzioni,
            "reparto": reparto,
            "note": note,
            "allergeni": allergeni,
            "ingredienti": [i["nome"] for i in ingredienti_dettaglio],
            "ingredienti_dettaglio": ingredienti_dettaglio,
            "provenienza_importazione": {
                "tipo": "csv",
                "nome_file": nome_file_sicuro,
                "sha256": digest_file,
            },
        }

        if azione == "NUOVA" or (azione == "AGGIORNA" and not rid):
            chiave_nome = _chiave_ricetta(nome)
            if not chiave_nome:
                plan["errori"].append(f"Riga {i+1}: nome non utilizzabile")
                continue
            if chiave_nome in esistenti_per_nome:
                esistente = esistenti_per_nome[chiave_nome]
                if aggiorna_omonime_confermato and esistente.get("id"):
                    plan["aggiornate"].append({
                        "id": str(esistente["id"]),
                        "nome": nome,
                        "doc": doc,
                    })
                else:
                    plan["saltate"].append({
                        "nome": nome,
                        "motivo": "ricetta omonima già presente",
                        "id_esistente": esistente.get("id"),
                    })
                continue
            if chiave_nome in nomi_nuovi_nel_file:
                plan["saltate"].append({
                    "nome": nome,
                    "motivo": "ricetta duplicata nello stesso file",
                })
                continue
            nomi_nuovi_nel_file.add(chiave_nome)
            doc["id"] = str(uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"ceraldiapp:ricetta:csv:{chiave_nome}",
            ))
            plan["nuove"].append({"nome": nome, "doc": doc})
        elif azione == "AGGIORNA" and rid:
            if rid not in id_esistenti:
                plan["errori"].append(f"ID non trovato: {rid} ({nome})")
            else:
                plan["aggiornate"].append({"id": rid, "nome": nome, "doc": doc})
        else:
            plan["errori"].append(f"Azione sconosciuta '{azione}' riga {i+1}")

    if anteprima:
        return {
            "anteprima": True,
            "nuove": len(plan["nuove"]),
            "aggiornate": len(plan["aggiornate"]),
            "saltate": len(plan["saltate"]),
            "errori": plan["errori"],
            "dettaglio_nuove": [p["nome"] for p in plan["nuove"]],
            "dettaglio_aggiornate": [p["nome"] for p in plan["aggiornate"]],
            "dettaglio_saltate": plan["saltate"],
            "provenienza": {
                "nome_file": nome_file_sicuro,
                "sha256": digest_file,
            },
        }

    create_count, update_count, err_count = 0, 0, 0

    for item in plan["nuove"]:
        try:
            doc = item["doc"]
            doc["created_at"] = datetime.now(timezone.utc).isoformat()
            doc["approvata"] = False  # badge 🆕 NUOVA finché non approvata
            await db.ricette.insert_one({k: v for k, v in doc.items() if k != "_id"})
            create_count += 1
        except Exception as e:
            plan["errori"].append(f"Errore creazione '{item['nome']}': {e}")
            err_count += 1

    for item in plan["aggiornate"]:
        try:
            update_doc = {
                k: v for k, v in item["doc"].items() if k not in ("id", "created_at", "_id")
            }
            result = await db.ricette.update_one({"id": item["id"]}, {"$set": update_doc})
            if result.matched_count > 0:
                update_count += 1
            else:
                plan["errori"].append(f"ID non trovato: {item['id']} ({item['nome']})")
        except Exception as e:
            plan["errori"].append(f"Errore aggiornamento '{item['nome']}': {e}")
            err_count += 1

    return {
        "successo": True,
        "create": create_count,
        "aggiornate": update_count,
        "saltate": len(plan["saltate"]),
        "dettaglio_saltate": plan["saltate"],
        "errori": plan["errori"],
        "totale_errori": len(plan["errori"]),
        "provenienza": {
            "nome_file": nome_file_sicuro,
            "sha256": digest_file,
        },
    }


@router.get("/ricette/export/json")
async def export_json():
    import json as _j

    ricette = await db.ricette.find({}, {"_id": 0}).sort("nome", 1).to_list(1000)
    content = _j.dumps(
        {
            "azienda": "Ceraldi Group",
            "export_date": datetime.now().isoformat(),
            "totale": len(ricette),
            "ricette": ricette,
        },
        ensure_ascii=False,
        indent=2,
    )
    filename = f"ricettario_{datetime.now().strftime('%Y%m%d')}.json"
    return Response(
        content=content.encode("utf-8"),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/tablet/{reparto}")
async def get_tablet(reparto: str):
    REPARTI_VALIDI = ("pasticceria", "rosticceria", "altro", "bar", "magazzino", "vendita")
    if reparto not in REPARTI_VALIDI:
        raise HTTPException(400, "Reparto non valido")
    if reparto == "magazzino":
        return {"reparto": reparto, "totale": 0, "prodotti": []}

    # Le fonti dei fornitori restano consultabili nel ricettario, ma non sono
    # automaticamente prodotti Ceraldi. Compaiono qui soltanto dopo che
    # l'utente le ha aperte e salvate con «Usa in ricetta».
    tutte = await db.ricette.find({}, {"_id": 0}).sort("nome", 1).to_list(5000)
    ricette = []
    for ricetta in tutte:
        if not _ricetta_visibile_tablet(ricetta):
            continue
        reparto_effettivo = _reparto_operativo_ricetta(ricetta)
        if reparto_effettivo != reparto:
            continue
        # La risposta riflette subito la classificazione dolce/salato corretta;
        # la persistenza viene fatta dall'azione amministrativa con backup.
        ricetta["reparto"] = reparto_effettivo
        ricette.append(ricetta)

    # Giacenza prodotti già pronti in frigo/abbattitore, non ancora al banco:
    # l'operatore deve vederla PRIMA di produrre di nuovo (richiesta Enzo
    # 03/07/2026), non scoprirla dopo aver già rifatto il prodotto.
    from app.lotti.routers.lotti_produzione import giacenza_prodotti_finiti
    giacenza = await giacenza_prodotti_finiti([r["nome"] for r in ricette if r.get("nome")])
    for r in ricette:
        g = giacenza.get(r.get("nome"))
        r["giacenza_frigo"] = g["totale"] if g else 0
        r["giacenza_lotti"] = g["lotti"] if g else []

    return {"reparto": reparto, "totale": len(ricette), "prodotti": ricette}


@router.get("/ricette/{ricetta_id}", response_model=Ricetta)
async def get_ricetta(ricetta_id: str):
    item = await db.ricette.find_one({"id": ricetta_id}, {"_id": 0})
    if not item:
        raise HTTPException(404, "Ricetta non trovata")
    return item


@router.post("/ricette", response_model=Ricetta)
async def create_ricetta(item: RicettaCreate):
    from app.lotti.allergeni import estrai_nomi_ingredienti, normalizza_allergeni, rileva_allergeni

    # Calcola allergeni automaticamente dagli ingredienti se non arrivano dal frontend
    item_data = item.model_dump()
    nomi_ing = estrai_nomi_ingredienti(item_data)
    allergeni_calc, _ = rileva_allergeni(nomi_ing)
    allergeni_manuali = normalizza_allergeni(item.allergeni) if item.allergeni_confermati else []

    # Assegna reparto automatico se non fornito
    reparto = item.reparto or _categorizza_reparto(
        item.nome,
        ingredienti=nomi_ing,
        ricetta_base_nome=item.ricetta_base_nome,
    )

    obj = Ricetta(**item.model_dump())
    doc = obj.model_dump()
    doc.pop("allergeni_confermati", None)
    doc["created_at"] = doc["created_at"].isoformat()
    doc["allergeni_auto"] = allergeni_calc
    doc["allergeni"] = allergeni_manuali if item.allergeni_confermati else allergeni_calc
    # Distingue "controllato, zero allergeni trovati" da "mai controllato" (nessun
    # ingrediente presente): l'alert del Supervisore guarda questo flag, non se
    # "allergeni" è vuoto — altrimenti una ricetta senza allergeni REALI (es.
    # "Funghi trifolati") resterebbe segnalata per sempre come "mancante".
    doc["allergeni_verificato"] = bool(nomi_ing) or item.allergeni_confermati
    # Compilati dall'automatismo alla creazione: restano "da confermare" finché
    # Enzo non li salva dal tab allergeni (decisione 04/07/2026).
    doc["allergeni_da_confermare"] = bool(nomi_ing) and not item.allergeni_confermati
    doc["reparto"] = reparto
    doc.setdefault("visibile_tablet", True)
    doc.setdefault("ricetta_operativa", True)

    await db.ricette.insert_one(doc)
    doc.pop("_id", None)

    # Una variante riceve una COPIA autonoma della foto base. Non conserva mai
    # lo stesso foto_id: cambiando in seguito la base non cambiano anche tutte
    # le varianti. Se non esiste una foto interna, il frontend può ancora usare
    # il normale fallback visivo senza creare collegamenti persistenti.
    if item.ricetta_base_id and not doc.get("foto_url"):
        foto_variante = await _clona_foto_tra_ricette(
            item.ricetta_base_id,
            doc["id"],
            fonte="creazione_variante",
        )
        if foto_variante:
            doc["foto_url"] = foto_variante

    # Ritorna il doc completo (non obj che non ha i campi extra)
    return {**doc, "id": doc["id"]}


@router.put("/ricette/{ricetta_id}", response_model=Ricetta)
async def update_ricetta(ricetta_id: str, item: RicettaCreate, _admin=Depends(require_admin)):
    from app.lotti.allergeni import estrai_nomi_ingredienti, normalizza_allergeni, rileva_allergeni

    precedente = await db.ricette.find_one({"id": ricetta_id}, {"_id": 0})
    if not precedente:
        raise HTTPException(404, "Ricetta non trovata")

    payload = item.model_dump()
    allergeni_confermati = bool(payload.pop("allergeni_confermati", False))

    # Ricalcola SEMPRE gli allergeni dagli ingredienti (auto), salvo override manuale esplicito
    nomi_ing = estrai_nomi_ingredienti(payload)
    allergeni_calc, _ = rileva_allergeni(nomi_ing)
    payload["allergeni_auto"] = allergeni_calc
    if allergeni_confermati:
        payload["allergeni"] = normalizza_allergeni(payload.get("allergeni"))
    else:
        payload["allergeni"] = allergeni_calc
    # Vedi create_ricetta: distingue "verificato, zero trovati" da "mai verificato".
    payload["allergeni_verificato"] = bool(nomi_ing) or allergeni_confermati
    # Allergeni scritti a mano nel form = confermati da un umano; auto-derivati =
    # restano da confermare (decisione Enzo 04/07/2026).
    payload["allergeni_da_confermare"] = bool(nomi_ing) and not allergeni_confermati

    # Salvare dal form «Ricette» trasforma il riferimento ufficiale del
    # fornitore in una ricetta operativa Ceraldi, senza perdere la provenienza.
    if _riferimento_ricettario_fornitore(precedente):
        payload["visibile_tablet"] = True
        payload["ricetta_operativa"] = True
        payload["adattata_da_ricettario_fornitore_at"] = datetime.now(timezone.utc).isoformat()

    r = await db.ricette.update_one({"id": ricetta_id}, {"$set": payload})
    if r.matched_count == 0:
        raise HTTPException(404, "Ricetta non trovata")
    return await db.ricette.find_one({"id": ricetta_id}, {"_id": 0})


@router.post("/backfill-allergeni-verificato")
async def backfill_allergeni_verificato():
    """Una tantum: applica il rilevamento automatico allergeni (già usato da
    create/update) a tutte le ricette esistenti create prima di questo fix,
    e segna allergeni_verificato così l'alert del Supervisore smette di
    segnalarle come "mancanti" quando in realtà sono già state controllate."""
    from app.lotti.routers.utils import _rileva_allergeni

    ricette = await db.ricette.find(
        {"allergeni_verificato": {"$ne": True}},
        {"_id": 0, "id": 1, "ingredienti": 1, "ingredienti_dettaglio": 1, "allergeni": 1},
    ).to_list(5000)

    aggiornate = 0
    for r in ricette:
        nomi_ing = [
            i.get("nome", "") if isinstance(i, dict) else str(i)
            for i in (r.get("ingredienti_dettaglio") or r.get("ingredienti") or [])
        ]
        nomi_ing = [n for n in nomi_ing if n and n.strip()]
        set_fields = {"allergeni_verificato": bool(nomi_ing)}
        if nomi_ing and not r.get("allergeni"):
            # Solo se non c'era già una dichiarazione (manuale o auto precedente):
            # non sovrascrive mai un dato esistente, anche se corretto a mano.
            res = _rileva_allergeni(nomi_ing)
            allergeni_calc = res.get("allergeni_presenti", [])
            set_fields["allergeni"] = allergeni_calc
            set_fields["allergeni_auto"] = allergeni_calc
            set_fields["allergeni_da_confermare"] = True  # compilati dall'automatismo
        await db.ricette.update_one({"id": r["id"]}, {"$set": set_fields})
        aggiornate += 1

    return {"ok": True, "ricette_esaminate": len(ricette), "aggiornate": aggiornate}


@router.post("/ricette-importa-tracciabilita")
async def importa_tracciabilita(sostituisci: bool = Query(True), _admin=Depends(require_admin)):
    """Importa le ricette dal vecchio foglio Excel di tracciabilità
    (backend/data/ricette_tracciabilita.json): per ogni ricetta, se esiste già
    (match per nome) ne SOSTITUISCE gli ingredienti, altrimenti la CREA nuova.
    Reparto e allergeni vengono calcolati automaticamente."""
    import json as _json
    from app.lotti.routers.utils import _rileva_allergeni
    path = Path(__file__).resolve().parent.parent / "data" / "ricette_tracciabilita.json"
    if not path.exists():
        raise HTTPException(404, "File ricette_tracciabilita.json non trovato")
    try:
        ricette = _json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(500, f"JSON non leggibile: {e}")

    create = aggiornate = saltate = 0
    dettaglio = []
    for rc in ricette:
        nome = (rc.get("nome") or "").strip()
        if not nome:
            continue
        ings = rc.get("ingredienti") or []
        nomi = [str(i.get("nome")).strip() for i in ings if i.get("nome")]
        ing_dett = [{"nome": n, "quantita": 0, "unita_misura": "g"} for n in nomi]
        reparto = _categorizza_reparto(nome, ingredienti=nomi)
        allerg = _rileva_allergeni(nomi).get("allergeni_presenti", []) if nomi else []
        doc_set = {
            "nome": nome, "reparto": reparto,
            "ingredienti": nomi, "ingredienti_dettaglio": ing_dett,
            "allergeni": allerg, "allergeni_auto": allerg,
            "fonte": "tracciabilita_xlsm",
        }
        existing = await db.ricette.find_one(
            {"nome": {"$regex": f"^{re.escape(nome)}$", "$options": "i"}}, {"id": 1}
        )
        if existing:
            if sostituisci:
                await db.ricette.update_one({"id": existing["id"]}, {"$set": doc_set})
                aggiornate += 1
                dettaglio.append({"nome": nome, "azione": "aggiornata", "ingredienti": len(nomi)})
            else:
                saltate += 1
        else:
            doc = {"id": str(uuid.uuid4()), "created_at": datetime.now(timezone.utc),
                   "approvata": True, "porzioni": 1, **doc_set}
            await db.ricette.insert_one(doc)
            create += 1
            dettaglio.append({"nome": nome, "azione": "creata", "ingredienti": len(nomi)})

    return {"ok": True, "totale_nel_foglio": len(ricette),
            "create": create, "aggiornate": aggiornate, "saltate": saltate,
            "dettaglio": dettaglio[:200]}


def _chiave_cartel1(value: Any) -> str:
    """Chiave solo per confronti esatti e ripetibili; mai fuzzy in produzione."""
    normalized = unicodedata.normalize("NFKD", str(value or "").casefold().replace("’", "'"))
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _dettagli_cartel1(ingredienti: List[str], existing: Optional[dict]) -> List[dict]:
    """Sostituisce l'elenco ma conserva quantità, unità e mapping già compilati
    quando il nome dell'ingrediente coincide. Le nuove quantità restano vuote:
    non inventiamo dosi che il foglio non contiene."""
    per_nome: dict[str, list[dict]] = {}
    for dettaglio in (existing or {}).get("ingredienti_dettaglio") or []:
        if not isinstance(dettaglio, dict):
            continue
        key = _chiave_cartel1(dettaglio.get("nome"))
        if key:
            per_nome.setdefault(key, []).append(dict(dettaglio))

    result = []
    for nome in ingredienti:
        key = _chiave_cartel1(nome)
        precedenti = per_nome.get(key) or []
        if precedenti:
            dettaglio = precedenti.pop(0)
            dettaglio["nome"] = nome
        else:
            dettaglio = {"nome": nome, "quantita": None, "unita_misura": ""}
        result.append(dettaglio)
    return result


def _carica_cartel1() -> dict:
    path = ROOT_DIR / "data" / "ricette_cartel1.json"
    if not path.exists():
        raise HTTPException(404, "File ricette_cartel1.json non trovato")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(500, f"JSON Cartel1 non leggibile: {exc}") from exc

    ricette = payload.get("recipes") if isinstance(payload, dict) else None
    if not isinstance(ricette, list) or not ricette:
        raise HTTPException(500, "Il ricettario Cartel1 non contiene ricette")
    names = [_chiave_cartel1(item.get("nome")) for item in ricette]
    if any(not name for name in names) or len(names) != len(set(names)):
        raise HTTPException(500, "Il ricettario Cartel1 contiene nomi mancanti o duplicati")
    known = set(names)
    for item in ricette:
        base = item.get("ricetta_base_nome")
        if base and _chiave_cartel1(base) not in known:
            raise HTTPException(500, f"Ricetta base non trovata per {item.get('nome')}")
    return payload


@router.post("/ricette-importa-cartel1")
async def importa_cartel1(
    anteprima: bool = Query(True),
    _admin=Depends(require_admin),
):
    """Integra Cartel1 senza cancellare il resto del ricettario.

    - anteprima=true non scrive nulla;
    - match solo su nomi espliciti e normalizzati, mai per somiglianza;
    - ID, foto e metadati non inclusi nel foglio restano invariati;
    - una quantità già compilata resta associata allo stesso ingrediente;
    - basi e varianti vengono collegate in modo idempotente.
    """
    from app.lotti.routers.utils import _rileva_allergeni

    payload = _carica_cartel1()
    source_hash = payload.get("source", {}).get("sha256") or ""
    source_recipes = payload["recipes"]
    current = await db.ricette.find({}, {"_id": 0}).to_list(5000)
    current_groups: dict[str, list[dict]] = {}
    for current_recipe in current:
        current_groups.setdefault(_chiave_cartel1(current_recipe.get("nome")), []).append(current_recipe)
    source_names = {_chiave_cartel1(item["nome"]) for item in source_recipes}
    conflicts = {
        key: [item.get("id") for item in items]
        for key, items in current_groups.items()
        if key in source_names and len(items) > 1
    }
    if conflicts:
        raise HTTPException(409, {
            "message": "Importazione interrotta: esistono ricette duplicate da verificare",
            "conflitti": conflicts,
        })
    current_by_name = {key: items[0] for key, items in current_groups.items() if key}

    planned_ids: dict[str, str] = {}
    for item in source_recipes:
        key = _chiave_cartel1(item["nome"])
        existing = current_by_name.get(key)
        planned_ids[key] = (
            existing["id"] if existing else str(uuid.uuid5(
                uuid.NAMESPACE_URL, f"ceraldiapp:cartel1:{source_hash}:{key}"
            ))
        )

    operations = []
    now = datetime.now(timezone.utc).isoformat()
    for item in source_recipes:
        nome = str(item["nome"]).strip()
        key = _chiave_cartel1(nome)
        existing = current_by_name.get(key)
        ingredienti = [
            str(value).strip()
            for value in item.get("ingredienti") or []
            if str(value).strip()
        ]
        details = _dettagli_cartel1(ingredienti, existing)
        auto_allergens = _rileva_allergeni(ingredienti).get("allergeni_presenti", []) if ingredienti else []
        existing_allergens = (existing or {}).get("allergeni") or []
        allergens = list(dict.fromkeys([*existing_allergens, *auto_allergens]))
        old_ingredients = (existing or {}).get("ingredienti") or []
        ingredients_changed = (
            [_chiave_cartel1(value) for value in old_ingredients]
            != [_chiave_cartel1(value) for value in ingredienti]
        )

        base_name = item.get("ricetta_base_nome")
        base_id = planned_ids.get(_chiave_cartel1(base_name)) if base_name else None
        reparto_calcolato = _categorizza_reparto(
            nome,
            ingredienti=ingredienti,
            ricetta_base_nome=base_name,
        )
        # Corregge anche una classificazione automatica precedente sbagliata.
        # Se invece non ci sono segnali certi, conserva la scelta già presente e
        # lascia "altro" alle nuove ricette: mai più il fallback cieco che
        # trasformava ogni voce sconosciuta in rosticceria.
        reparto = (
            reparto_calcolato
            if reparto_calcolato != "altro"
            else ((existing or {}).get("reparto") or "altro")
        )

        doc_set = {
            "nome": nome,
            "reparto": reparto,
            "ingredienti": ingredienti,
            "ingredienti_dettaglio": details,
            "allergeni": allergens,
            "allergeni_auto": auto_allergens,
            "allergeni_verificato": bool(ingredienti),
            "allergeni_da_confermare": bool(ingredienti) and (
                ingredients_changed or (existing or {}).get("allergeni_da_confermare", True)
            ),
            "ricetta_base_id": base_id,
            "ricetta_base_nome": base_name,
            "fonte": "cartel1_xlsx",
            "fonte_sha256": source_hash,
            "cartel1_source_cell": item.get("origine", {}).get("cella"),
        }

        comparable = {field: (existing or {}).get(field) for field in doc_set}
        changed = comparable != doc_set
        action = "aggiornata" if existing else "creata"
        if existing and not changed:
            action = "invariata"
        operations.append({
            "nome": nome,
            "id": planned_ids[key],
            "azione": action,
            "ingredienti": len(ingredienti),
            "ricetta_base_nome": base_name,
            "existing": existing,
            "doc_set": doc_set,
        })

    summary = {
        "totale_nel_foglio": len(source_recipes),
        "create": sum(op["azione"] == "creata" for op in operations),
        "aggiornate": sum(op["azione"] == "aggiornata" for op in operations),
        "invariate": sum(op["azione"] == "invariata" for op in operations),
        "varianti_collegate": sum(bool(op["ricetta_base_nome"]) for op in operations),
    }
    public_detail = [
        {key: op[key] for key in ("nome", "id", "azione", "ingredienti", "ricetta_base_nome")}
        for op in operations
    ]
    if anteprima:
        return {"ok": True, "anteprima": True, "source_sha256": source_hash,
                **summary, "dettaglio": public_detail}

    changed_operations = [op for op in operations if op["azione"] != "invariata"]
    backup_id = None
    if changed_operations:
        backup_id = str(uuid.uuid4())
        await db.ricette_import_backup.insert_one({
            "id": backup_id,
            "tipo": "prima_import_cartel1",
            "source_sha256": source_hash,
            "created_at": now,
            "operatore": (_admin or {}).get("nome") or (_admin or {}).get("sub"),
            "ricette": current,
        })

    for op in changed_operations:
        doc_set = {**op["doc_set"], "cartel1_imported_at": now}
        if op["existing"]:
            await db.ricette.update_one({"id": op["id"]}, {"$set": doc_set})
        else:
            await db.ricette.insert_one({
                "id": op["id"],
                "created_at": now,
                "approvata": True,
                "porzioni": 1,
                **doc_set,
            })

    return {"ok": True, "anteprima": False, "source_sha256": source_hash,
            "backup_id": backup_id, **summary, "dettaglio": public_detail}


@router.delete("/ricette/{ricetta_id}")
async def delete_ricetta(ricetta_id: str, _admin=Depends(require_admin)):
    existing = await db.ricette.find_one({"id": ricetta_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Ricetta non trovata")
    # La × toglie la ricetta dall'app, ma prima ne conserva una copia
    # recuperabile: foto, ingredienti e riferimenti storici non vanno persi.
    await db.ricette_cestino.insert_one({
        "id": str(uuid.uuid4()),
        "ricetta_id": ricetta_id,
        "ricetta": existing,
        "eliminata_at": datetime.now(timezone.utc).isoformat(),
        "eliminata_da": (_admin or {}).get("nome") or (_admin or {}).get("sub"),
    })
    r = await db.ricette.delete_one({"id": ricetta_id})
    if r.deleted_count == 0:
        raise HTTPException(404, "Ricetta non trovata")
    return {"message": "Eliminata con successo", "recuperabile": True}


_BASE_NOME_RE = re.compile(r"\s*\(\s*base\s*\)\s*$", re.IGNORECASE)


def _chiave_nome_base(nome: str) -> str:
    """Rende equivalenti solo `Nome` e `Nome (Base)`.

    Non rimuove `variante di`, gusti o altre parentesi: una vera variante non
    deve mai essere fusa per somiglianza testuale.
    """
    senza_base = _BASE_NOME_RE.sub("", str(nome or "")).strip()
    ascii_name = unicodedata.normalize("NFKD", senza_base)
    ascii_name = "".join(c for c in ascii_name if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", ascii_name.casefold()).strip()


def _nomi_ingredienti_ricetta(ricetta: dict) -> list[str]:
    sorgente = ricetta.get("ingredienti_dettaglio") or ricetta.get("ingredienti") or []
    nomi = []
    for ingrediente in sorgente:
        nome = ingrediente.get("nome") if isinstance(ingrediente, dict) else ingrediente
        chiave = _chiave_nome_base(str(nome or ""))
        if chiave and chiave not in nomi:
            nomi.append(chiave)
    return nomi


def _completezza_ricetta(ricetta: dict) -> tuple:
    ingredienti = _nomi_ingredienti_ricetta(ricetta)
    procedimento = any(ricetta.get(k) for k in ("procedimento_testo", "procedimento", "preparazione", "metodo_preparazione"))
    foto = bool(ricetta.get("foto_url") or ricetta.get("foto_id"))
    altri = sum(bool(ricetta.get(k)) for k in ("note", "allergeni", "metodo_conservazione", "porzioni"))
    senza_etichetta_base = not bool(_BASE_NOME_RE.search(str(ricetta.get("nome") or "")))
    return (len(ingredienti), int(procedimento), int(foto), altri, int(senza_etichetta_base))


def _piano_deduplica_basi(ricette: list[dict]) -> tuple[list[dict], list[dict]]:
    gruppi: dict[str, list[dict]] = {}
    for ricetta in ricette:
        chiave = _chiave_nome_base(ricetta.get("nome"))
        if chiave:
            gruppi.setdefault(chiave, []).append(ricetta)

    piano = []
    da_verificare = []
    for chiave, gruppo in sorted(gruppi.items()):
        if len(gruppo) < 2 or not any(_BASE_NOME_RE.search(str(r.get("nome") or "")) for r in gruppo):
            continue
        ordinato = sorted(gruppo, key=lambda r: (_completezza_ricetta(r), str(r.get("id") or "")), reverse=True)
        vincitore = ordinato[0]
        vincitore_ingredienti = set(_nomi_ingredienti_ricetta(vincitore))
        eliminabili = []
        ambigui = []
        for candidato in ordinato[1:]:
            ingredienti = set(_nomi_ingredienti_ricetta(candidato))
            meno_ingredienti = len(vincitore_ingredienti) > len(ingredienti)
            stessi_ingredienti = bool(vincitore_ingredienti) and vincitore_ingredienti == ingredienti
            if meno_ingredienti or stessi_ingredienti:
                eliminabili.append(candidato)
            else:
                ambigui.append(candidato)
        if eliminabili:
            piano.append({
                "chiave": chiave,
                "vincitore": vincitore,
                "eliminabili": eliminabili,
                "foto_da_trasferire": not bool(vincitore.get("foto_url") or vincitore.get("foto_id"))
                    and any(r.get("foto_url") or r.get("foto_id") for r in eliminabili),
            })
        if ambigui:
            da_verificare.append({
                "chiave": chiave,
                "nomi": [r.get("nome") for r in [vincitore, *ambigui]],
                "motivo": "stesso numero di ingredienti ma composizione diversa",
            })
    return piano, da_verificare


def _campi_da_recuperare(vincitore: dict, eliminabili: list[dict]) -> dict:
    aggiornamenti = {}
    campi = (
        "foto_url", "foto_id", "foto_filename", "foto_content_type", "foto_sha256", "foto_source",
        "procedimento_testo", "procedimento", "preparazione", "metodo_preparazione",
        "note", "allergeni", "metodo_conservazione",
    )
    for campo in campi:
        if vincitore.get(campo):
            continue
        fonte = next((r.get(campo) for r in eliminabili if r.get(campo)), None)
        if fonte:
            aggiornamenti[campo] = fonte
    return aggiornamenti


@router.post("/ricette/deduplica-basi")
async def deduplica_ricette_base(
    applica: bool = Query(False),
    _actor=Depends(require_automation_or_admin),
):
    """Unisce esclusivamente duplicati `Nome` / `Nome (Base)` comprovati.

    Anteprima per default. In applicazione conserva un backup completo, copia
    i campi mancanti (prima di tutto la foto), ricollega le varianti e sposta
    ogni record eliminato nel cestino recuperabile.
    """
    ricette = await db.ricette.find({}, {"_id": 0}).to_list(5000)
    piano, da_verificare = _piano_deduplica_basi(ricette)
    dettagli = []
    for gruppo in piano:
        vincitore = gruppo["vincitore"]
        eliminabili = gruppo["eliminabili"]
        dettagli.append({
            "chiave": gruppo["chiave"],
            "mantieni": {
                "id": vincitore.get("id"), "nome": vincitore.get("nome"),
                "ingredienti": len(_nomi_ingredienti_ricetta(vincitore)),
                "ha_foto": bool(vincitore.get("foto_url") or vincitore.get("foto_id")),
            },
            "elimina": [{
                "id": r.get("id"), "nome": r.get("nome"),
                "ingredienti": len(_nomi_ingredienti_ricetta(r)),
                "ha_foto": bool(r.get("foto_url") or r.get("foto_id")),
            } for r in eliminabili],
            "trasferisce_foto": bool(gruppo["foto_da_trasferire"]),
        })

    if not applica:
        return {
            "ok": True, "applicato": False,
            "gruppi_da_unire": len(piano),
            "ricette_da_eliminare": sum(len(g["eliminabili"]) for g in piano),
            "da_verificare": da_verificare,
            "gruppi": dettagli,
        }

    now = datetime.now(timezone.utc).isoformat()
    backup_id = str(uuid.uuid4())
    await db.ricette_dedup_backup.insert_one({
        "id": backup_id,
        "creato_at": now,
        "creato_da": (_actor or {}).get("nome") or "amministratore",
        "tipo": "deduplica_nome_base",
        "gruppi": [{
            "chiave": g["chiave"],
            "vincitore": g["vincitore"],
            "eliminabili": g["eliminabili"],
        } for g in piano],
    })

    eliminate = 0
    foto_trasferite = 0
    varianti_ricollegate = 0
    for gruppo in piano:
        vincitore = gruppo["vincitore"]
        eliminabili = gruppo["eliminabili"]
        recupero = _campi_da_recuperare(vincitore, eliminabili)
        if recupero:
            await db.ricette.update_one({"id": vincitore["id"]}, {"$set": recupero})
            if any(k.startswith("foto_") for k in recupero):
                foto_trasferite += 1
        for record in eliminabili:
            loser_id = record.get("id")
            if not loser_id:
                continue
            risultato_varianti = await db.ricette.update_many(
                {"ricetta_base_id": loser_id},
                {"$set": {"ricetta_base_id": vincitore["id"], "ricetta_base_nome": vincitore.get("nome")}},
            )
            varianti_ricollegate += risultato_varianti.modified_count
            await db.ricette_cestino.insert_one({
                "id": str(uuid.uuid4()),
                "ricetta_id": loser_id,
                "ricetta": record,
                "eliminata_at": now,
                "eliminata_da": (_actor or {}).get("nome") or "amministratore",
                "motivo": "duplicato Nome / Nome (Base)",
                "unita_in": vincitore["id"],
                "backup_id": backup_id,
            })
            esito = await db.ricette.delete_one({"id": loser_id})
            eliminate += esito.deleted_count

    return {
        "ok": True, "applicato": True, "backup_id": backup_id,
        "gruppi_uniti": len(piano), "ricette_eliminate": eliminate,
        "foto_trasferite": foto_trasferite,
        "varianti_ricollegate": varianti_ricollegate,
        "da_verificare": da_verificare,
        "gruppi": dettagli,
    }


@router.put("/ricette/{ricetta_id}/prezzo-vendita")
async def set_prezzo_vendita(ricetta_id: str, prezzo: float = Query(...)):
    await db.ricette.update_one({"id": ricetta_id}, {"$set": {"prezzo_vendita": prezzo}})
    return {"ok": True, "prezzo_vendita": prezzo}


@router.put("/ricette/{ricetta_id}/reparto")
async def aggiorna_reparto(ricetta_id: str, reparto: str = Query(...)):
    if reparto not in ("pasticceria", "rosticceria", "altro"):
        raise HTTPException(400, "Reparto non valido")
    r = await db.ricette.update_one({"id": ricetta_id}, {"$set": {"reparto": reparto}})
    if r.matched_count == 0:
        raise HTTPException(404, "Ricetta non trovata")
    return await db.ricette.find_one({"id": ricetta_id}, {"_id": 0})


@router.put("/ricette/{ricetta_id}/foto")
async def aggiorna_foto(ricetta_id: str, foto_url: str = Query(...)):
    r = await db.ricette.update_one({"id": ricetta_id}, {"$set": {"foto_url": foto_url}})
    if r.matched_count == 0:
        raise HTTPException(404, "Ricetta non trovata")
    return {"success": True}


def _foto_id_da_url(foto_url: str) -> Optional[str]:
    """Estrae l'id solo dagli URL interni /api/foto/<id>[?v=...]."""
    if not foto_url:
        return None
    path = str(foto_url).split("?", 1)[0].rstrip("/")
    marker = "/api/foto/"
    if marker not in path:
        return None
    return path.split(marker, 1)[1] or None


async def _clona_foto_tra_ricette(
    ricetta_origine_id: str,
    ricetta_destinazione_id: str,
    fonte: str,
) -> Optional[str]:
    """Copia bytes e metadati in un foto_id nuovo, poi collega la destinazione."""
    origine = await db.ricette.find_one(
        {"id": ricetta_origine_id}, {"_id": 0, "foto_url": 1, "nome": 1}
    )
    foto_origine_id = _foto_id_da_url((origine or {}).get("foto_url"))
    if not foto_origine_id:
        return None
    foto = await db.foto_files.find_one({"_id": foto_origine_id})
    if not foto or not foto.get("data"):
        return None

    safe_dest = ricetta_destinazione_id.replace("/", "_")
    nuovo_foto_id = f"ricetta_{safe_dest}_{uuid.uuid4().hex[:12]}"
    versione = int(datetime.now(timezone.utc).timestamp())
    await db.foto_files.insert_one({
        "_id": nuovo_foto_id,
        "mime": foto.get("mime", "image/jpeg"),
        "data": bytes(foto["data"]),
        "ricetta_id": ricetta_destinazione_id,
        "versione": versione,
        "fonte": fonte,
        "copiata_da_ricetta_id": ricetta_origine_id,
        "copiata_da_foto_id": foto_origine_id,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    foto_url = f"/api/foto/{nuovo_foto_id}?v={versione}"
    await db.ricette.update_one(
        {"id": ricetta_destinazione_id}, {"$set": {"foto_url": foto_url}}
    )
    return foto_url


@router.post("/ricette/separa-foto-varianti")
async def separa_foto_varianti(
    applica: bool = False,
    _admin=Depends(require_admin),
):
    """Rende autonome le foto delle varianti che usano ancora la foto base.

    ``applica=false`` produce solo il piano. In applicazione salva prima una
    fotografia JSON dei collegamenti, così l'operazione resta reversibile.
    """
    ricette = await db.ricette.find(
        {}, {"_id": 0, "id": 1, "nome": 1, "foto_url": 1,
             "ricetta_base_id": 1, "ricetta_base_nome": 1}
    ).to_list(5000)
    per_id = {r.get("id"): r for r in ricette}
    piano = []
    non_clonabili = []
    for variante in ricette:
        base_id = variante.get("ricetta_base_id")
        if not base_id:
            continue
        base = per_id.get(base_id)
        if not base or not base.get("foto_url"):
            non_clonabili.append({
                "id": variante.get("id"), "nome": variante.get("nome"),
                "motivo": "ricetta base senza foto",
            })
            continue
        foto_variante_id = _foto_id_da_url(variante.get("foto_url"))
        foto_base_id = _foto_id_da_url(base.get("foto_url"))
        usa_base = not variante.get("foto_url") or (
            foto_base_id and foto_variante_id == foto_base_id
        )
        if not usa_base:
            continue
        if not foto_base_id:
            non_clonabili.append({
                "id": variante.get("id"), "nome": variante.get("nome"),
                "motivo": "foto base esterna, non clonabile",
            })
            continue
        piano.append({
            "id": variante["id"], "nome": variante.get("nome"),
            "ricetta_base_id": base_id, "ricetta_base_nome": base.get("nome"),
            "foto_prima": variante.get("foto_url"),
        })

    backup_id = None
    aggiornate = []
    if applica and piano:
        backup_id = str(uuid.uuid4())
        await db.ricette_foto_backup.insert_one({
            "id": backup_id,
            "tipo": "separa_foto_varianti",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "collegamenti": piano,
        })
        for voce in piano:
            nuova = await _clona_foto_tra_ricette(
                voce["ricetta_base_id"], voce["id"], fonte="separa_foto_varianti"
            )
            if nuova:
                aggiornate.append({**voce, "foto_dopo": nuova})
            else:
                non_clonabili.append({
                    "id": voce["id"], "nome": voce.get("nome"),
                    "motivo": "file della foto base non trovato",
                })

    return {
        "dry_run": not applica,
        "da_separare": len(piano),
        "aggiornate": len(aggiornate),
        "backup_id": backup_id,
        "dettaglio": aggiornate if applica else piano,
        "non_clonabili": non_clonabili,
    }


@router.post("/ricette/{ricetta_id}/upload-foto")
async def upload_foto(ricetta_id: str, file: UploadFile = File(...)):
    if not await db.ricette.find_one({"id": ricetta_id}, {"_id": 1}):
        raise HTTPException(404, "Ricetta non trovata")
    mime = file.content_type or ""
    if not mime.startswith("image/"):
        raise HTTPException(400, "File non è un'immagine")
    # Salvataggio su MongoDB (persiste ai restart di Render, niente disco effimero).
    contenuto = await file.read()
    if len(contenuto) > 15 * 1024 * 1024:
        raise HTTPException(400, "Immagine troppo grande (max 15MB)")
    safe_id = ricetta_id.replace("/", "_")
    # Versione = timestamp di questo upload. Bug corretto 01/07/2026: foto_url era
    # SEMPRE la stessa stringa per una data ricetta (solo /api/foto/{id}), quindi un
    # aggiornamento foto non cambiava l'URL — né il browser (Cache-Control 24h) né
    # React (stesso src = nessun nuovo fetch) si accorgevano del cambiamento e
    # continuavano a mostrare la foto vecchia. Ora l'URL include ?v=<versione>: cambia
    # ad ogni upload, quindi forza sempre un fetch fresco della nuova immagine.
    versione = int(datetime.now(timezone.utc).timestamp())
    # Ogni caricamento usa un id immutabile e specifico della ricetta. In
    # passato l'id era solo ``ricetta_id``: più schede che avevano ereditato lo
    # stesso URL vedevano cambiare insieme la foto. Il nuovo id elimina alla
    # radice quel collegamento condiviso.
    foto_id = f"ricetta_{safe_id}_{uuid.uuid4().hex[:12]}"
    await db.foto_files.insert_one({
        "_id": foto_id, "mime": mime, "data": contenuto,
        "ricetta_id": ricetta_id, "versione": versione,
        "fonte": "upload_manuale",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    # foto_url servito dall'endpoint GET /api/foto/{id} (legge da Mongo); ?v cambia
    # ad ogni upload per invalidare cache browser/React sulla stessa ricetta.
    foto_url = f"/api/foto/{foto_id}?v={versione}"
    await db.ricette.update_one({"id": ricetta_id}, {"$set": {"foto_url": foto_url}})
    return {"success": True, "foto_url": foto_url}


@router.get("/foto/{foto_id}")
async def leggi_foto(foto_id: str):
    """Serve l'immagine salvata su MongoDB. URL con ?v=<versione>: contenuto di una
    specifica versione è immutabile, quindi cache lunga e forte è sicura — un
    aggiornamento foto genera un nuovo ?v e quindi un URL (e una cache) diversi."""
    doc = await db.foto_files.find_one({"_id": foto_id})
    if not doc or not doc.get("data"):
        raise HTTPException(404, "Foto non trovata")
    from fastapi.responses import Response
    return Response(content=bytes(doc["data"]), media_type=doc.get("mime", "image/jpeg"),
                    headers={"Cache-Control": "public, max-age=31536000, immutable"})


@router.put("/ricette/{ricetta_id}/ingredienti-dettaglio")
async def aggiorna_ingredienti_dettaglio(ricetta_id: str, ingredienti_dettaglio: List[dict]):
    puliti = []
    nomi = []
    for voce in ingredienti_dettaglio:
        if not isinstance(voce, dict):
            continue
        nome = str(voce.get("nome") or "").strip()
        if not nome:
            continue
        puliti.append({**voce, "nome": nome})
        nomi.append(nome)
    esistente = await db.ricette.find_one(
        {"id": ricetta_id}, {"_id": 0, "allergeni": 1, "allergeni_auto": 1}
    )
    if not esistente:
        raise HTTPException(404, "Ricetta non trovata")
    from app.lotti.routers.utils import _rileva_allergeni
    allergeni_auto = _rileva_allergeni(nomi).get("allergeni_presenti", []) if nomi else []
    aggiornamento = {
        "ingredienti_dettaglio": puliti,
        "ingredienti": nomi,
        "origine_ingredienti": "manuale",
        "ingredienti_updated_at": datetime.now(timezone.utc).isoformat(),
        "allergeni_auto": allergeni_auto,
        "allergeni_verificato": bool(nomi),
        "allergeni_da_confermare": bool(nomi),
    }
    # Un override umano degli allergeni non viene perso.
    if not esistente.get("allergeni") or esistente.get("allergeni") == esistente.get("allergeni_auto"):
        aggiornamento["allergeni"] = allergeni_auto
    await db.ricette.update_one({"id": ricetta_id}, {"$set": aggiornamento})
    return await db.ricette.find_one({"id": ricetta_id}, {"_id": 0})


@router.patch("/ricette/{ricetta_id}")
async def aggiorna_campo_ricetta(ricetta_id: str, body: dict):
    """Aggiornamento parziale di una ricetta (pezzi_ricetta_base, note, ecc.).

    NOTA centralizzazione dati: `pezzi_ricetta_base` e `porzioni` sono storicamente
    due nomi per lo stesso valore (numero pezzi prodotti dalla ricetta base).
    Il frontend ha pagine che leggono uno o l'altro campo. Per evitare divergenze
    aggiorniamo SEMPRE entrambi i campi quando uno dei due viene passato.
    """
    campi_permessi = {
        "pezzi_ricetta_base",
        "porzioni",
        "note",
        "reparto",
        "prezzo_vendita",
        "componenti",
        "foto_url",
        "stagionale",
        "nome",
        "ricetta_base_nome",
        "ingredienti",
    }
    update = {k: v for k, v in body.items() if k in campi_permessi}
    if not update:
        raise HTTPException(400, "Nessun campo valido da aggiornare")
    # Sincronizza pezzi_ricetta_base ↔ porzioni
    if "pezzi_ricetta_base" in update and "porzioni" not in update:
        update["porzioni"] = update["pezzi_ricetta_base"]
    elif "porzioni" in update and "pezzi_ricetta_base" not in update:
        update["pezzi_ricetta_base"] = update["porzioni"]
    r = await db.ricette.update_one({"id": ricetta_id}, {"$set": update})
    if r.matched_count == 0:
        raise HTTPException(404, "Ricetta non trovata")
    return {"success": True, "aggiornato": update}


class SchedaEditoriale(BaseModel):
    """Sezioni editoriali della scheda stampabile (tutte opzionali).
    Le chiavi corrispondono ESATTAMENTE a quelle lette da _render_scheda_ceraldi:
    consigli / errore_da_evitare / nutrizione sono TOP-LEVEL (il renderer NON
    li annida sotto 'segreti')."""
    model_config = ConfigDict(extra="forbid")
    occhiello: Optional[str] = None
    procedimento: Optional[List[dict]] = None          # [{titolo, testo}]
    dettaglio_critico: Optional[str] = None
    consigli: Optional[List[str]] = None               # ["...", "..."]
    errore_da_evitare: Optional[str] = None
    nutrizione: Optional[dict] = None                  # {kcal: number}
    impiattamento: Optional[List[dict]] = None         # [{elemento, nota}]
    varianti: Optional[List[dict]] = None              # [{nome, descrizione}]


@router.put("/ricette/{ricetta_id}/scheda")
async def aggiorna_scheda_editoriale(ricetta_id: str, payload: SchedaEditoriale = Body(...)):
    """Salva le sezioni editoriali della scheda. Scrive solo i campi inviati
    (None = invariato; lista vuota / stringa vuota = azzerato)."""
    update = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
    if not update:
        raise HTTPException(400, "Nessuna sezione da salvare")
    res = await db.ricette.update_one({"id": ricetta_id}, {"$set": update})
    if res.matched_count == 0:
        raise HTTPException(404, "Ricetta non trovata")
    return {"success": True, "aggiornato": list(update.keys())}


@router.post("/ricette/auto-assegna-reparti")
async def auto_assegna_reparti(applica: bool = True, _admin=Depends(require_admin)):
    """Assegna il reparto in base al nome: i DOLCI in pasticceria, i SALATI in
    rosticceria. SICURO: quando il nome non è classificabile con certezza
    ('altro') NON tocca il reparto già impostato (così non svuota le card).
    Sposta solo i casi certi — incluse le contaminazioni incrociate (dolce in
    rosticceria / salato in pasticceria). applica=false → dry-run."""
    ricette = await db.ricette.find(
        {},
        {
            "_id": 0,
            "id": 1,
            "nome": 1,
            "reparto": 1,
            "ingredienti": 1,
            "ingredienti_dettaglio": 1,
            "ricetta_base_nome": 1,
            "origine": 1,
            "sola_lettura": 1,
            "visibile_tablet": 1,
            "ricettario_saima_id": 1,
            "ricettario_mepa_id": 1,
            "ricettario_acquaviva_id": 1,
            "ricettario_fornitore_id": 1,
        },
    ).to_list(5000)
    moves = []
    finale = {"pasticceria": 0, "rosticceria": 0, "altro": 0, "bar": 0}
    for r in ricette:
        if not _ricetta_visibile_tablet(r):
            continue
        cur = (r.get("reparto") or "").lower().strip()
        final = _reparto_operativo_ricetta(r)
        finale[final] = finale.get(final, 0) + 1
        if final in {"pasticceria", "rosticceria", "bar"} and final != cur:
            moves.append({
                "id": r["id"],
                "nome": r.get("nome", ""),
                "da": cur or "—",
                "reparto_precedente": r.get("reparto"),
                "a": final,
            })

    if applica and moves:
        await db.ricette_import_backup.insert_one({
            "id": str(uuid.uuid4()),
            "tipo": "riordino_reparti_operativi",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "operatore": (_admin or {}).get("nome") if isinstance(_admin, dict) else None,
            "reparti_precedenti": [
                {
                    "id": move["id"],
                    "nome": move["nome"],
                    "reparto": move["reparto_precedente"],
                }
                for move in moves
            ],
        })
        for m in moves:
            await db.ricette.update_one({"id": m["id"]}, {"$set": {"reparto": m["a"]}})

    return {
        "dry_run": not applica,
        "aggiornate": len(moves) if applica else 0,
        "spostate": len(moves),
        "pasticceria": finale.get("pasticceria", 0),
        "rosticceria": finale.get("rosticceria", 0),
        "altro": finale.get("altro", 0),
        "bar": finale.get("bar", 0),
        "dettaglio": moves,
    }


@router.post("/ricette/pulisci-ingredienti")
async def pulisci_ingredienti(_admin=Depends(require_admin)):
    ricette = await db.ricette.find({}, {"_id": 0}).to_list(1000)
    risultato = {"ricette_processate": 0, "ingredienti_puliti": 0, "esempi": []}
    for r in ricette:
        originali = r.get("ingredienti", [])
        puliti = []
        modificato = False
        for ing in originali:
            p = _pulisci_nome_ing(ing)
            if p and not any(x.lower() == p.lower() for x in puliti):
                puliti.append(p)
            if ing != p:
                modificato = True
                if len(risultato["esempi"]) < 10:
                    risultato["esempi"].append({"originale": ing, "pulito": p})
        if modificato:
            await db.ricette.update_one({"id": r["id"]}, {"$set": {"ingredienti": puliti}})
            risultato["ingredienti_puliti"] += len(originali)
        risultato["ricette_processate"] += 1
    return risultato


@router.post("/ricette/collega-ingredienti-canonico")
async def collega_ingredienti_canonico():
    """Collega ogni ingrediente di ogni ricetta (ingredienti_dettaglio[].nome) a un
    nome_canonico riconosciuto, riusando lo STESSO matcher già testato per le
    fatture (match_livello1 = nome_mapping esatto, match_livello2 =
    INGREDIENTI_CANONICI per parola chiave) — non re-inventa una fuzzy-match
    nuova apposta per non ripetere il bug trovato oggi in prodotti_master
    (match troppo permissivo che agganciava ingredienti sbagliati).
    Non tocca chi ha già un link (prodotto_dizionario_id/nome_canonico/ecc.).
    Bulk e idempotente."""
    from app.lotti.routers.ingredienti import match_livello1, match_livello2
    from pymongo import UpdateOne

    LINK_FIELDS = (
        "prodotto_master_id", "master_id", "prodotto_id", "prodotto_key",
        "prodotto_dizionario_id", "nome_canonico", "nome_canc",
    )

    def _gia_collegato(ing: dict) -> bool:
        return any(ing.get(f) for f in LINK_FIELDS)

    docs = await db.ricette.find({}, {"id": 1, "ingredienti_dettaglio": 1}).to_list(2000)
    ops = []
    ricette_agg = 0
    ingredienti_collegati = 0
    ingredienti_non_trovati = 0
    esempi = []
    for r in docs:
        det = r.get("ingredienti_dettaglio") or []
        if not det:
            continue
        changed = False
        for ing in det:
            if not isinstance(ing, dict) or _gia_collegato(ing):
                continue
            nome = (ing.get("nome") or "").strip()
            if not nome:
                continue
            canonico = (await match_livello1(nome)) or match_livello2(nome) or ""
            if canonico:
                ing["nome_canonico"] = canonico
                changed = True
                ingredienti_collegati += 1
                if len(esempi) < 20:
                    esempi.append({"ingrediente": nome, "canonico": canonico})
            else:
                ingredienti_non_trovati += 1
        if changed:
            ops.append(UpdateOne({"id": r["id"]}, {"$set": {"ingredienti_dettaglio": det}}))
    if ops:
        await db.ricette.bulk_write(ops, ordered=False)
        ricette_agg = len(ops)
    return {
        "ok": True,
        "ricette_totali": len(docs),
        "ricette_aggiornate": ricette_agg,
        "ingredienti_collegati": ingredienti_collegati,
        "ingredienti_non_trovati": ingredienti_non_trovati,
        "esempi": esempi,
    }


@router.post("/ricette/popola-quantita-esempio")
async def popola_quantita_esempio():
    _QS = {
        "farina": {"quantita": 500, "unita": "g"},
        "uova": {"quantita": 4, "unita": "pz"},
        "burro": {"quantita": 150, "unita": "g"},
        "zucchero": {"quantita": 200, "unita": "g"},
        "latte": {"quantita": 250, "unita": "ml"},
        "panna": {"quantita": 200, "unita": "ml"},
        "olio": {"quantita": 100, "unita": "ml"},
        "sale": {"quantita": 10, "unita": "g"},
        "lievito": {"quantita": 15, "unita": "g"},
        "cacao": {"quantita": 30, "unita": "g"},
        "cioccolato": {"quantita": 100, "unita": "g"},
        "ricotta": {"quantita": 250, "unita": "g"},
        "mascarpone": {"quantita": 250, "unita": "g"},
        "mozzarella": {"quantita": 200, "unita": "g"},
        "tuorlo": {"quantita": 6, "unita": "pz"},
        "albume": {"quantita": 4, "unita": "pz"},
        "miele": {"quantita": 50, "unita": "g"},
        "vaniglia": {"quantita": 1, "unita": "bustina"},
    }
    ricette = await db.ricette.find({}, {"_id": 0}).to_list(1000)
    aggiornate = 0
    for r in ricette:
        det = [
            {
                "nome": ing,
                **(
                    next(
                        (v for k, v in _QS.items() if k in ing.lower()),
                        {"quantita": "q.b.", "unita": ""},
                    )
                ),
            }
            for ing in r.get("ingredienti", [])
        ]
        if det:
            await db.ricette.update_one(
                {"id": r["id"]}, {"$set": {"ingredienti_dettaglio": det, "porzioni": 10}}
            )
            aggiornate += 1
    return {"success": True, "aggiornate": aggiornate}


# ─── BOM (Bill of Materials) esploso ─────────────────────────────────────────


async def _esplodi_componente(
    comp: dict, porzioni_target: float, porzioni_ricetta: float, visitati: set, profondita: int = 0
) -> tuple[list, list]:
    """
    Ricorsivamente esplode un componente BOM.
    Ritorna (ingredienti_flat, struttura).
    Anti-loop: interrompe se ref_id già visitato.
    """
    tipo = comp.get("tipo", "ingrediente")
    nome = comp.get("nome", "")
    qt_raw = float(comp.get("quantita", 0) or 0)
    um = comp.get("unita_misura", "g")

    if tipo != "sotto_ricetta":
        # Ingrediente diretto — scala proporzionalmente
        fattore = (porzioni_target / porzioni_ricetta) if porzioni_ricetta > 0 else 1
        qt_scalata = round(qt_raw * fattore, 3)
        item = {"nome": nome, "quantita": qt_scalata, "unita_misura": um}
        return [item], [
            {"nome": nome, "tipo": "ingrediente", "quantita": qt_scalata, "unita_misura": um}
        ]

    ref_id = comp.get("ref_id", "")
    if ref_id in visitati:
        # Anti-loop
        return [], [{"nome": nome, "tipo": "sotto_ricetta", "warning": "loop rilevato, saltato"}]
    visitati.add(ref_id)

    sotto = await db.ricette.find_one({"id": ref_id}, {"_id": 0})
    if not sotto:
        # Prova per nome
        sotto = await db.ricette.find_one(
            {"nome": {"$regex": f"^{nome}$", "$options": "i"}}, {"_id": 0}
        )
    if not sotto:
        return [], [{"nome": nome, "tipo": "sotto_ricetta", "warning": "ricetta non trovata"}]

    porz_sotto = float(sotto.get("porzioni", 1) or 1)
    # Quante porzioni della sotto-ricetta servono?
    # qt_raw è la quantità della sotto-ricetta espressa nella sua UM.
    # Per semplificare: fattore_scala = (porzioni_target / porzioni_ricetta) * 1
    fattore_globale = (porzioni_target / porzioni_ricetta) if porzioni_ricetta > 0 else 1
    # porzioni della sotto-ricetta da produrre = fattore_globale * qt_raw (trattato come porzioni già scalate)
    porz_target_sotto = qt_raw * fattore_globale

    ing_flat = []
    struttura_figli = []

    componenti_sotto = sotto.get("componenti") or []
    sorgente = (
        componenti_sotto
        if componenti_sotto
        else [
            {
                "tipo": "ingrediente",
                "nome": i.get("nome", ""),
                "quantita": float(i.get("quantita", 0) or 0),
                "unita_misura": i.get("unita_misura", "g"),
            }
            for i in sotto.get("ingredienti_dettaglio", [])
        ]
    )

    for figlio in sorgente:
        flat_f, strutt_f = await _esplodi_componente(
            figlio, porz_target_sotto, porz_sotto, visitati, profondita + 1
        )
        ing_flat.extend(flat_f)
        struttura_figli.extend(strutt_f)

    struttura_nodo = {
        "nome": nome,
        "tipo": "sotto_ricetta",
        "ricetta_id": ref_id,
        "porzioni_usate": round(porz_target_sotto, 2),
        "ingredienti": struttura_figli,
    }
    return ing_flat, [struttura_nodo]


@router.get("/ricette/{ricetta_id}/bom")
async def get_bom_ricetta(ricetta_id: str, porzioni: float = Query(None)):
    """
    Calcola e restituisce il BOM esploso della ricetta, scalato per N porzioni.
    Supporta ricette composite (con componenti[]) e semplici (ingredienti_dettaglio).
    Anti-loop incluso. Raggruppa ingredienti duplicati sommando le quantità (stessa UM).
    """
    ricetta = await db.ricette.find_one({"id": ricetta_id}, {"_id": 0})
    if not ricetta:
        raise HTTPException(404, "Ricetta non trovata")

    porzioni_base = float(ricetta.get("porzioni", 1) or 1)
    porzioni_target = porzioni if porzioni is not None else porzioni_base
    moltiplicatore = round(porzioni_target / porzioni_base, 4) if porzioni_base > 0 else 1.0

    componenti = ricetta.get("componenti") or []
    if not componenti:
        # Ricetta semplice — usa ingredienti_dettaglio come lista piatta
        componenti = [
            {
                "tipo": "ingrediente",
                "nome": i.get("nome", ""),
                "quantita": float(i.get("quantita", 0) or 0),
                "unita_misura": i.get("unita_misura", "g"),
            }
            for i in ricetta.get("ingredienti_dettaglio", [])
        ]

    visitati = {ricetta_id}  # anti-loop: include la ricetta stessa
    ing_flat_totale = []
    struttura_totale = []

    for comp in componenti:
        flat, strutt = await _esplodi_componente(comp, porzioni_target, porzioni_base, visitati)
        ing_flat_totale.extend(flat)
        struttura_totale.extend(strutt)

    # Raggruppa per (nome, unita_misura)
    raggruppati: dict[tuple, float] = {}
    for ing in ing_flat_totale:
        chiave = (ing["nome"], ing["unita_misura"])
        raggruppati[chiave] = raggruppati.get(chiave, 0.0) + ing["quantita"]

    ingredienti_esplosi = [
        {"nome": nome, "quantita": round(qt, 3), "unita_misura": um}
        for (nome, um), qt in raggruppati.items()
    ]

    return {
        "ricetta_id": ricetta_id,
        "ricetta_nome": ricetta.get("nome", ""),
        "porzioni_richieste": porzioni_target,
        "porzioni_base": porzioni_base,
        "moltiplicatore": moltiplicatore,
        "ingredienti_esplosi": ingredienti_esplosi,
        "struttura": struttura_totale,
        "e_composita": bool(ricetta.get("componenti")),
    }


# ── APPROVAZIONE ─────────────────────────────────────────────────────────────
@router.patch("/ricette/{ricetta_id}/approva")
async def approva_ricetta(ricetta_id: str):
    """Imposta approvata=True sulla ricetta. Rimuove il badge 'NUOVA'."""
    r = await db.ricette.find_one({"id": ricetta_id}, {"_id": 0, "id": 1})
    if not r:
        raise HTTPException(404, "Ricetta non trovata")
    await db.ricette.update_one({"id": ricetta_id}, {"$set": {"approvata": True}})
    return {"success": True, "approvata": True}


# ── VALORI NUTRIZIONALI ───────────────────────────────────────────────────────
# Tabella nutrizionale per 100g (stime ragionevoli — non da laboratorio)
_NUTRI: dict = {
    # Cereali e derivati
    "farina": {"kcal": 364, "prot": 10.5, "carb": 74.0, "grassi": 0.9},
    "semola": {"kcal": 362, "prot": 12.5, "carb": 70.0, "grassi": 1.5},
    "pasta": {"kcal": 360, "prot": 13.0, "carb": 71.0, "grassi": 1.5},
    "pangrattato": {"kcal": 350, "prot": 10.0, "carb": 70.0, "grassi": 2.5},
    # Latticini
    "latte": {"kcal": 66, "prot": 3.2, "carb": 4.9, "grassi": 3.9},
    "panna": {"kcal": 337, "prot": 2.2, "carb": 3.2, "grassi": 36.0},
    "burro": {"kcal": 750, "prot": 0.9, "carb": 0.8, "grassi": 83.0},
    "ricotta": {"kcal": 174, "prot": 9.5, "carb": 2.7, "grassi": 13.7},
    "mozzarella": {"kcal": 280, "prot": 18.7, "carb": 0.7, "grassi": 22.4},
    "formaggio": {"kcal": 380, "prot": 26.0, "carb": 1.0, "grassi": 30.0},
    "parmigiano": {"kcal": 431, "prot": 33.0, "carb": 0.0, "grassi": 33.0},
    "mascarpone": {"kcal": 450, "prot": 5.8, "carb": 4.5, "grassi": 44.0},
    "caciocavallo": {"kcal": 398, "prot": 28.2, "carb": 0.5, "grassi": 32.0},
    "yogurt": {"kcal": 65, "prot": 3.9, "carb": 4.8, "grassi": 3.1},
    # Uova
    "uov": {"kcal": 143, "prot": 12.4, "carb": 0.9, "grassi": 10.6},
    "tuorlo": {"kcal": 352, "prot": 15.5, "carb": 0.7, "grassi": 31.0},
    "albume": {"kcal": 52, "prot": 10.9, "carb": 0.7, "grassi": 0.2},
    # Dolcificanti
    "zucchero": {"kcal": 387, "prot": 0.0, "carb": 99.9, "grassi": 0.0},
    "miele": {"kcal": 304, "prot": 0.4, "carb": 80.0, "grassi": 0.0},
    "sciroppo": {"kcal": 256, "prot": 0.0, "carb": 67.0, "grassi": 0.0},
    # Oli e grassi
    "olio": {"kcal": 884, "prot": 0.0, "carb": 0.0, "grassi": 100.0},
    "lardo": {"kcal": 820, "prot": 2.2, "carb": 0.0, "grassi": 90.0},
    "strutto": {"kcal": 892, "prot": 0.0, "carb": 0.0, "grassi": 99.5},
    # Carni
    "carne": {"kcal": 215, "prot": 19.0, "carb": 0.0, "grassi": 14.5},
    "maiale": {"kcal": 215, "prot": 19.0, "carb": 0.0, "grassi": 14.5},
    "manzo": {"kcal": 190, "prot": 21.0, "carb": 0.0, "grassi": 11.5},
    "pollo": {"kcal": 190, "prot": 22.0, "carb": 0.0, "grassi": 11.0},
    "salsiccia": {"kcal": 285, "prot": 15.0, "carb": 3.0, "grassi": 24.0},
    "salame": {"kcal": 430, "prot": 25.0, "carb": 0.0, "grassi": 37.0},
    "prosciutto": {"kcal": 268, "prot": 25.7, "carb": 0.5, "grassi": 17.8},
    "pancetta": {"kcal": 358, "prot": 17.5, "carb": 0.0, "grassi": 31.5},
    "ragù": {"kcal": 180, "prot": 14.0, "carb": 5.0, "grassi": 11.0},
    # Pesce
    "baccal": {"kcal": 105, "prot": 24.0, "carb": 0.0, "grassi": 0.5},
    "polpo": {"kcal": 82, "prot": 14.9, "carb": 2.2, "grassi": 1.0},
    "cozze": {"kcal": 84, "prot": 12.0, "carb": 3.3, "grassi": 2.4},
    "vongole": {"kcal": 72, "prot": 10.0, "carb": 2.5, "grassi": 1.6},
    "alici": {"kcal": 96, "prot": 17.0, "carb": 0.0, "grassi": 3.5},
    "gamberi": {"kcal": 71, "prot": 13.6, "carb": 0.5, "grassi": 1.1},
    "pesce": {"kcal": 120, "prot": 20.0, "carb": 0.0, "grassi": 4.0},
    # Verdure
    "pomodoro": {"kcal": 20, "prot": 1.0, "carb": 3.5, "grassi": 0.2},
    "cipolla": {"kcal": 40, "prot": 1.0, "carb": 9.0, "grassi": 0.1},
    "aglio": {"kcal": 149, "prot": 6.4, "carb": 33.0, "grassi": 0.5},
    "patate": {"kcal": 86, "prot": 2.0, "carb": 19.0, "grassi": 0.1},
    "peperone": {"kcal": 31, "prot": 1.0, "carb": 6.6, "grassi": 0.4},
    "melanzane": {"kcal": 25, "prot": 1.1, "carb": 5.1, "grassi": 0.1},
    "zucchine": {"kcal": 17, "prot": 1.3, "carb": 2.6, "grassi": 0.1},
    "carciofi": {"kcal": 50, "prot": 3.5, "carb": 7.5, "grassi": 0.2},
    "spinaci": {"kcal": 31, "prot": 3.4, "carb": 3.5, "grassi": 0.3},
    "friariell": {"kcal": 35, "prot": 2.9, "carb": 3.1, "grassi": 0.7},
    "insalata": {"kcal": 15, "prot": 1.4, "carb": 2.0, "grassi": 0.2},
    "verdure": {"kcal": 30, "prot": 2.0, "carb": 5.0, "grassi": 0.2},
    # Frutta
    "limone": {"kcal": 29, "prot": 1.1, "carb": 6.5, "grassi": 0.6},
    "arancia": {"kcal": 47, "prot": 0.9, "carb": 12.0, "grassi": 0.1},
    "uvetta": {"kcal": 290, "prot": 2.5, "carb": 76.0, "grassi": 0.5},
    # Frutta secca
    "mandorla": {"kcal": 604, "prot": 22.0, "carb": 19.0, "grassi": 53.0},
    "pistacchio": {"kcal": 562, "prot": 20.0, "carb": 27.0, "grassi": 45.0},
    "nocciola": {"kcal": 628, "prot": 15.0, "carb": 17.0, "grassi": 61.0},
    "pinoli": {"kcal": 688, "prot": 14.0, "carb": 13.0, "grassi": 68.0},
    "noci": {"kcal": 654, "prot": 15.0, "carb": 14.0, "grassi": 65.0},
    # Cioccolato
    "cioccolat": {"kcal": 545, "prot": 7.0, "carb": 56.0, "grassi": 34.0},
    "cacao": {"kcal": 384, "prot": 20.0, "carb": 46.0, "grassi": 20.0},
    # Altro
    "acqua": {"kcal": 0, "prot": 0.0, "carb": 0.0, "grassi": 0.0},
    "sale": {"kcal": 0, "prot": 0.0, "carb": 0.0, "grassi": 0.0},
    "aceto": {"kcal": 25, "prot": 0.0, "carb": 5.0, "grassi": 0.0},
    "vino": {"kcal": 85, "prot": 0.1, "carb": 2.6, "grassi": 0.0},
    "brodo": {"kcal": 12, "prot": 1.0, "carb": 0.8, "grassi": 0.4},
    "passata": {"kcal": 28, "prot": 1.5, "carb": 5.8, "grassi": 0.2},
    "concentrato": {"kcal": 82, "prot": 4.6, "carb": 16.0, "grassi": 0.5},
    "cannella": {"kcal": 261, "prot": 4.0, "carb": 68.0, "grassi": 3.2},
    "vaniglia": {"kcal": 288, "prot": 0.1, "carb": 13.0, "grassi": 0.1},
    "rum": {"kcal": 230, "prot": 0.0, "carb": 0.0, "grassi": 0.0},
    "zafferano": {"kcal": 310, "prot": 11.4, "carb": 65.4, "grassi": 5.9},
    # Pasticceria
    "margarina": {"kcal": 720, "prot": 0.8, "carb": 0.4, "grassi": 80.0},
    "lievito": {"kcal": 296, "prot": 38.0, "carb": 38.0, "grassi": 1.7},
    "amido": {"kcal": 356, "prot": 0.3, "carb": 88.0, "grassi": 0.1},
    "aroma": {"kcal": 0, "prot": 0.0, "carb": 0.0, "grassi": 0.0},
    "miglioratore": {"kcal": 350, "prot": 8.0, "carb": 75.0, "grassi": 1.5},
    "crema": {"kcal": 230, "prot": 4.5, "carb": 26.0, "grassi": 12.0},
    "nuppy": {"kcal": 550, "prot": 6.0, "carb": 55.0, "grassi": 33.0},
    "gocce": {"kcal": 545, "prot": 7.0, "carb": 56.0, "grassi": 34.0},
    "mix cake": {"kcal": 400, "prot": 5.0, "carb": 65.0, "grassi": 12.0},
    "piselli": {"kcal": 81, "prot": 5.4, "carb": 14.5, "grassi": 0.4},
    "riso": {"kcal": 360, "prot": 6.7, "carb": 80.0, "grassi": 0.6},
    "provola": {"kcal": 334, "prot": 25.0, "carb": 0.5, "grassi": 26.0},
    "prosciutto cotto": {"kcal": 138, "prot": 19.8, "carb": 0.0, "grassi": 6.5},
    "pepe": {"kcal": 251, "prot": 10.4, "carb": 64.0, "grassi": 3.3},
    "scarola": {"kcal": 17, "prot": 1.0, "carb": 2.4, "grassi": 0.2},
    "amarena": {"kcal": 265, "prot": 0.5, "carb": 66.0, "grassi": 0.1},
    "wrustel": {"kcal": 248, "prot": 12.0, "carb": 2.0, "grassi": 21.5},
    "polpett": {"kcal": 224, "prot": 16.0, "carb": 8.0, "grassi": 14.0},
    "carota": {"kcal": 41, "prot": 0.9, "carb": 9.6, "grassi": 0.2},
    "carote": {"kcal": 41, "prot": 0.9, "carb": 9.6, "grassi": 0.2},
    "fungi": {"kcal": 22, "prot": 3.1, "carb": 3.3, "grassi": 0.3},
    "fungo": {"kcal": 22, "prot": 3.1, "carb": 3.3, "grassi": 0.3},
    "cappero": {"kcal": 23, "prot": 2.4, "carb": 4.9, "grassi": 0.9},
    "olive": {"kcal": 145, "prot": 1.0, "carb": 3.8, "grassi": 15.3},
    "oliva": {"kcal": 145, "prot": 1.0, "carb": 3.8, "grassi": 15.3},
    "pane": {"kcal": 265, "prot": 9.0, "carb": 49.0, "grassi": 3.2},
    "wienercreme": {"kcal": 720, "prot": 0.8, "carb": 0.4, "grassi": 80.0},
    "plunder": {"kcal": 720, "prot": 0.8, "carb": 0.4, "grassi": 80.0},
    "caputo": {"kcal": 340, "prot": 11.5, "carb": 70.0, "grassi": 1.5},
    "naturvi": {"kcal": 296, "prot": 38.0, "carb": 38.0, "grassi": 1.7},
    "visciola": {"kcal": 265, "prot": 0.5, "carb": 66.0, "grassi": 0.1},
    "cannoli": {"kcal": 400, "prot": 7.0, "carb": 50.0, "grassi": 18.0},
}

_UNITA_A_GRAMMI = {
    "g": 1.0,
    "gr": 1.0,
    "kg": 1000.0,
    "ml": 1.0,
    "l": 1000.0,
    "cl": 10.0,
    "pz": 50.0,
    "n": 50.0,
    "uova": 55.0,
    "fette": 30.0,
    "cucchiaio": 15.0,
    "cucchiai": 15.0,
    "cucchiaino": 5.0,
    "cucchiaini": 5.0,
    "spicchio": 8.0,
    "rametto": 5.0,
}


def _cerca_nutri(nome: str) -> dict | None:
    n = nome.lower().strip()
    for chiave, valori in _NUTRI.items():
        if chiave in n:
            return valori
    return None


def _converti_grammi(quantita: float, unita: str) -> float:
    u = (unita or "g").lower().strip()
    return quantita * _UNITA_A_GRAMMI.get(u, 1.0)


# ── Database USDA completo (7 valori per 100g) usato per la dichiarazione nutrizionale ──
_USDA_CACHE: list | None = None

def _usda_db() -> list:
    global _USDA_CACHE
    if _USDA_CACHE is None:
        try:
            import json as _json
            p = ROOT_DIR / "data" / "usda_nutrizionale.json"
            _USDA_CACHE = _json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            _USDA_CACHE = []
    return _USDA_CACHE

# campi della dichiarazione (per 100g)
_CAMPI_DICH = ["kcal", "grassi", "saturi", "carboidrati", "zuccheri", "proteine", "sale"]

def _nutri_completo(nome: str) -> dict | None:
    """Ritorna i 7 valori per 100g per la dichiarazione. Prima cerca nel DB USDA
    (nome + alias), poi ripiega sul dizionario interno _NUTRI (solo 4 macro)."""
    n = (nome or "").lower().strip()
    if not n:
        return None
    # USDA: match su nome o alias contenuti nel nome ingrediente
    for voce in _usda_db():
        chiavi = [str(voce.get("nome", "")).lower()] + [str(a).lower() for a in (voce.get("aliases") or [])]
        if any(c and c in n for c in chiavi):
            p100 = voce.get("per_100g") or {}
            return {k: float(p100.get(k, 0) or 0) for k in _CAMPI_DICH}
    # fallback su _NUTRI (kcal/prot/carb/grassi)
    base = _cerca_nutri(nome)
    if base:
        return {
            "kcal": float(base.get("kcal", 0) or 0),
            "grassi": float(base.get("grassi", 0) or 0),
            "saturi": 0.0,
            "carboidrati": float(base.get("carb", 0) or 0),
            "zuccheri": 0.0,
            "proteine": float(base.get("prot", 0) or 0),
            "sale": 0.0,
        }
    return None


@router.get("/ricette/{ricetta_id}/nutrizionali")
async def get_nutrizionali(ricetta_id: str):
    """
    Calcola valori nutrizionali per porzione della ricetta.
    Usa una tabella di stima per 100g degli ingredienti comuni.
    Non è un'analisi da laboratorio — è una stima ragionevole.
    """
    r = await db.ricette.find_one({"id": ricetta_id}, {"_id": 0})
    if not r:
        raise HTTPException(404, "Ricetta non trovata")

    porzioni = float(r.get("porzioni", 1) or 1)
    ingredienti = r.get("ingredienti_dettaglio") or []

    tot = {"kcal": 0.0, "prot": 0.0, "carb": 0.0, "grassi": 0.0}
    tot_dich = {k: 0.0 for k in _CAMPI_DICH}   # per la dichiarazione (7 valori)
    grammi_totali = 0.0
    copertura = 0
    ingredienti_calcolati = []

    for ing in ingredienti:
        nome = ing.get("nome", "")
        q_str = str(ing.get("quantita") or "").strip().lower()
        # Salta ingredienti con "q.b." o quantità non numeriche
        try:
            q_raw = float(q_str)
        except (ValueError, TypeError):
            continue
        unita = ing.get("unita_misura") or ing.get("unita") or "g"
        if q_raw <= 0:
            continue
        grammi = _converti_grammi(q_raw, unita)
        grammi_totali += grammi
        nutri7 = _nutri_completo(nome)
        if nutri7:
            f7 = grammi / 100.0
            for k in _CAMPI_DICH:
                tot_dich[k] += nutri7[k] * f7
        nutri = _cerca_nutri(nome)
        if nutri:
            fattore = grammi / 100.0
            for k in tot:
                tot[k] += nutri[k] * fattore
            copertura += 1
            ingredienti_calcolati.append(
                {
                    "nome": nome,
                    "grammi": round(grammi, 1),
                    "kcal": round(nutri["kcal"] * fattore, 1),
                }
            )

    per_porzione = {k: round(v / porzioni, 1) for k, v in tot.items()}

    per_100g = (
        {k: round(tot_dich[k] / grammi_totali * 100.0, 1) for k in _CAMPI_DICH}
        if grammi_totali > 0 else {k: 0.0 for k in _CAMPI_DICH}
    )

    return {
        "ricetta_id": ricetta_id,
        "ricetta_nome": r.get("nome", ""),
        "porzioni": porzioni,
        "ingredienti_coperti": copertura,
        "ingredienti_totali": len(ingredienti),
        "per_porzione": per_porzione,
        "totale_ricetta": {k: round(v, 1) for k, v in tot.items()},
        "grammi_totali": round(grammi_totali, 1),
        "per_100g": per_100g,
        "dettaglio": ingredienti_calcolati,
        "nota": "Valori stimati non certificati — Fonte: tabelle nutrizionali standard",
    }
