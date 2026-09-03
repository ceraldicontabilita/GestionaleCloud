import logging

"""
Router per normalizzazione intelligente dei nomi prodotto.
Usa AI per classificare descrizioni fattura → nome canonico + categoria.
Il mapping viene salvato in MongoDB (collezione `nome_mapping`) e riutilizzato.
Nuove fatture vengono processate solo per i prodotti ancora sconosciuti.
"""

import os
import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Body, HTTPException, Query, BackgroundTasks, Depends

from app.lotti.db import database as db
from app.lotti.auth import require_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/normalizzazione", tags=["Normalizzazione"])

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# ─── Mappa statica rapida (senza AI) ─────────────────────────────────────────
SINONIMI_STATICI: dict[str, dict] = {
    # Oli
    "olio extravergine oliva": {
        "nome_canc": "Olio Extravergine di Oliva",
        "categoria": "Condimenti",
    },
    "olio evo": {"nome_canc": "Olio Extravergine di Oliva", "categoria": "Condimenti"},
    "olio extra vergine": {"nome_canc": "Olio Extravergine di Oliva", "categoria": "Condimenti"},
    "olio di oliva": {"nome_canc": "Olio di Oliva", "categoria": "Condimenti"},
    "olio di semi": {"nome_canc": "Olio di Semi", "categoria": "Condimenti"},
    # Farine
    "farina 00": {"nome_canc": "Farina 00", "categoria": "Farine e Cereali"},
    "farina 0": {"nome_canc": "Farina 0", "categoria": "Farine e Cereali"},
    "farina tipo 1": {"nome_canc": "Farina Tipo 1", "categoria": "Farine e Cereali"},
    "farina di grano": {"nome_canc": "Farina di Grano", "categoria": "Farine e Cereali"},
    "semola": {"nome_canc": "Semola", "categoria": "Farine e Cereali"},
    # Zuccheri
    "zucchero semolato": {"nome_canc": "Zucchero Semolato", "categoria": "Dolcificanti"},
    "zucchero bianco": {"nome_canc": "Zucchero Semolato", "categoria": "Dolcificanti"},
    "zucchero a velo": {"nome_canc": "Zucchero a Velo", "categoria": "Dolcificanti"},
    "zucchero impalpabile": {"nome_canc": "Zucchero a Velo", "categoria": "Dolcificanti"},
    "zucchero di canna": {"nome_canc": "Zucchero di Canna", "categoria": "Dolcificanti"},
    # Grassi
    "burro": {"nome_canc": "Burro", "categoria": "Latticini e Grassi"},
    "strutto": {"nome_canc": "Strutto", "categoria": "Latticini e Grassi"},
    "margarina": {"nome_canc": "Margarina", "categoria": "Latticini e Grassi"},
    # Uova
    "uova fresche": {"nome_canc": "Uova Fresche", "categoria": "Uova"},
    "uova": {"nome_canc": "Uova", "categoria": "Uova"},
    "tuorlo": {"nome_canc": "Tuorlo d'Uovo", "categoria": "Uova"},
    "albume": {"nome_canc": "Albume d'Uovo", "categoria": "Uova"},
    # Latticini
    "latte": {"nome_canc": "Latte Fresco", "categoria": "Latticini e Grassi"},
    "panna fresca": {"nome_canc": "Panna Fresca", "categoria": "Latticini e Grassi"},
    "panna": {"nome_canc": "Panna", "categoria": "Latticini e Grassi"},
    "ricotta": {"nome_canc": "Ricotta", "categoria": "Formaggi"},
    "mozzarella": {"nome_canc": "Mozzarella", "categoria": "Formaggi"},
    "fior di latte": {"nome_canc": "Fior di Latte", "categoria": "Formaggi"},
    "fiordilatte": {"nome_canc": "Fior di Latte", "categoria": "Formaggi"},
    "provola": {"nome_canc": "Provola", "categoria": "Formaggi"},
    # Lieviti e addensanti
    "lievito di birra": {"nome_canc": "Lievito di Birra", "categoria": "Lieviti e Addensanti"},
    "lievito per dolci": {"nome_canc": "Lievito per Dolci", "categoria": "Lieviti e Addensanti"},
    "lievito": {"nome_canc": "Lievito", "categoria": "Lieviti e Addensanti"},
    # Frutta e verdura
    "pomodori": {"nome_canc": "Pomodori", "categoria": "Frutta e Verdura"},
    "pomodori pelati": {"nome_canc": "Pomodori Pelati", "categoria": "Conserve e Condimenti"},
    "passata di pomodoro": {
        "nome_canc": "Passata di Pomodoro",
        "categoria": "Conserve e Condimenti",
    },
    "arance": {"nome_canc": "Arance", "categoria": "Frutta e Verdura"},
    "limoni": {"nome_canc": "Limoni", "categoria": "Frutta e Verdura"},
    "mele": {"nome_canc": "Mele", "categoria": "Frutta e Verdura"},
    "fragole": {"nome_canc": "Fragole", "categoria": "Frutta e Verdura"},
    # Cioccolato e cacao
    "cacao": {"nome_canc": "Cacao in Polvere", "categoria": "Cioccolato e Cacao"},
    "cioccolato fondente": {"nome_canc": "Cioccolato Fondente", "categoria": "Cioccolato e Cacao"},
    "cioccolato al latte": {"nome_canc": "Cioccolato al Latte", "categoria": "Cioccolato e Cacao"},
    "pasta di cacao": {"nome_canc": "Pasta di Cacao", "categoria": "Cioccolato e Cacao"},
    # Pasta e cereali
    "pasta di mandorle": {
        "nome_canc": "Pasta di Mandorle",
        "categoria": "Semilavorati Pasticceria",
    },
    "pan di spagna": {"nome_canc": "Pan di Spagna", "categoria": "Semilavorati Pasticceria"},
    "crema pasticciera": {
        "nome_canc": "Crema Pasticciera",
        "categoria": "Semilavorati Pasticceria",
    },
    # Bevande
    "rum": {"nome_canc": "Rum", "categoria": "Alcolici e Liquori"},
    "limoncello": {"nome_canc": "Limoncello", "categoria": "Alcolici e Liquori"},
    # Marche commerciali comuni → nome usuale
    "olva": {"nome_canc": "Margarina", "categoria": "Latticini e Grassi"},
    "margarina olva": {"nome_canc": "Margarina", "categoria": "Latticini e Grassi"},
    "ilva": {"nome_canc": "Burro", "categoria": "Latticini e Grassi"},
    "burro ilva": {"nome_canc": "Burro", "categoria": "Latticini e Grassi"},
    "gateaux": {"nome_canc": "Margarina Sfoglia", "categoria": "Latticini e Grassi"},
    "wiener": {"nome_canc": "Margarina Crema", "categoria": "Latticini e Grassi"},
    "wienercreme": {"nome_canc": "Margarina Crema", "categoria": "Latticini e Grassi"},
    "melange": {"nome_canc": "Margarina", "categoria": "Latticini e Grassi"},
    "green valley": {"nome_canc": "Margarina", "categoria": "Latticini e Grassi"},
    "green platte": {"nome_canc": "Margarina", "categoria": "Latticini e Grassi"},
    "homillina": {"nome_canc": "Margarina", "categoria": "Latticini e Grassi"},
    "plunderplat": {"nome_canc": "Margarina", "categoria": "Latticini e Grassi"},
    "manitoba": {"nome_canc": "Farina Manitoba", "categoria": "Farine e Cereali"},
    "caputo": {"nome_canc": "Farina 00", "categoria": "Farine e Cereali"},
    "mandorle pelate": {"nome_canc": "Mandorle Pelate", "categoria": "Frutta Secca"},
    "mandorle": {"nome_canc": "Mandorle", "categoria": "Frutta Secca"},
    "nocciole": {"nome_canc": "Nocciole", "categoria": "Frutta Secca"},
    "pistacchio": {"nome_canc": "Pistacchio", "categoria": "Frutta Secca"},
    "pistacchi": {"nome_canc": "Pistacchio", "categoria": "Frutta Secca"},
    "amarena": {"nome_canc": "Amarene", "categoria": "Conserve e Condimenti"},
    "amarene": {"nome_canc": "Amarene", "categoria": "Conserve e Condimenti"},
    "canditi": {"nome_canc": "Canditi", "categoria": "Conserve e Condimenti"},
    "miele": {"nome_canc": "Miele", "categoria": "Dolcificanti"},
    "vaniglia": {"nome_canc": "Vaniglia", "categoria": "Aromi"},
    "vanillina": {"nome_canc": "Vanillina", "categoria": "Aromi"},
    "cannella": {"nome_canc": "Cannella", "categoria": "Aromi"},
    "sale": {"nome_canc": "Sale", "categoria": "Condimenti"},
    "sale fino": {"nome_canc": "Sale Fino", "categoria": "Condimenti"},
    # ── Decorazioni di zucchero (codette, diavolini, ecc.) ──
    "codette": {"nome_canc": "Codette di Zucchero", "categoria": "Decorazioni"},
    "diavolini": {"nome_canc": "Diavolini di Zucchero", "categoria": "Decorazioni"},
    "granella di zucchero": {"nome_canc": "Granella di Zucchero", "categoria": "Decorazioni"},
    "perle di zucchero": {"nome_canc": "Perle di Zucchero", "categoria": "Decorazioni"},
    "gocce di meringa": {"nome_canc": "Gocce di Meringa", "categoria": "Decorazioni"},
    "dischi di cioccolato": {"nome_canc": "Dischi di Cioccolato", "categoria": "Decorazioni"},
    # ── Bagne per dolci (babà, pan di spagna) ──
    "bagna alla strega": {"nome_canc": "Bagna alla Strega", "categoria": "Bagne e Aromi"},
    "bagna strega": {"nome_canc": "Bagna alla Strega", "categoria": "Bagne e Aromi"},
    "bagna benevento": {"nome_canc": "Bagna alla Strega", "categoria": "Bagne e Aromi"},
    "aroma benevento": {"nome_canc": "Bagna alla Strega", "categoria": "Bagne e Aromi"},
    "bagna al rum": {"nome_canc": "Bagna al Rum", "categoria": "Bagne e Aromi"},
    "bagna rum": {"nome_canc": "Bagna al Rum", "categoria": "Bagne e Aromi"},
    "liquore strega": {"nome_canc": "Liquore Strega", "categoria": "Alcolici e Liquori"},
    # ── Aromi, essenze ed emulsioni ──
    "aroma vaniglia": {"nome_canc": "Aroma Vaniglia", "categoria": "Bagne e Aromi"},
    "aroma vanigliato": {"nome_canc": "Aroma Vaniglia", "categoria": "Bagne e Aromi"},
    "aroma cannella": {"nome_canc": "Aroma Cannella", "categoria": "Bagne e Aromi"},
    "essenza cannella": {"nome_canc": "Aroma Cannella", "categoria": "Bagne e Aromi"},
    "aroma brioche": {"nome_canc": "Aroma Brioche", "categoria": "Bagne e Aromi"},
    "essenza brioche": {"nome_canc": "Aroma Brioche", "categoria": "Bagne e Aromi"},
    "aroma panettone": {"nome_canc": "Aroma Panettone", "categoria": "Bagne e Aromi"},
    "essenza panettone": {"nome_canc": "Aroma Panettone", "categoria": "Bagne e Aromi"},
    "aroma croissant": {"nome_canc": "Aroma Croissant", "categoria": "Bagne e Aromi"},
    "essenza burro": {"nome_canc": "Aroma Burro", "categoria": "Bagne e Aromi"},
    "emulsione burro": {"nome_canc": "Aroma Burro", "categoria": "Bagne e Aromi"},
    "aroma fragola": {"nome_canc": "Aroma Fragola", "categoria": "Bagne e Aromi"},
    # ── Amidi e agenti lievitanti ──
    "amido": {"nome_canc": "Amido", "categoria": "Farine e Cereali"},
    "amido di riso": {"nome_canc": "Amido di Riso", "categoria": "Farine e Cereali"},
    "ammoniaca": {"nome_canc": "Ammoniaca per Dolci", "categoria": "Lieviti e Addensanti"},
    "bicarbonato di ammonio": {"nome_canc": "Ammoniaca per Dolci", "categoria": "Lieviti e Addensanti"},
    "gelatina": {"nome_canc": "Gelatina", "categoria": "Lieviti e Addensanti"},
    "lievito naturale": {"nome_canc": "Lievito", "categoria": "Lieviti e Addensanti"},
    # ── Cioccolato, gocce, coperture, creme da farcitura ──
    "surrogato fondente": {"nome_canc": "Surrogato Fondente", "categoria": "Cioccolato e Cacao"},
    "surrogato": {"nome_canc": "Surrogato Fondente", "categoria": "Cioccolato e Cacao"},
    "gocce di cioccolato": {"nome_canc": "Gocce di Cioccolato", "categoria": "Cioccolato e Cacao"},
    "cubetti di cioccolato": {"nome_canc": "Cubetti di Cioccolato", "categoria": "Cioccolato e Cacao"},
    "pasta cacao": {"nome_canc": "Pasta di Cacao", "categoria": "Cioccolato e Cacao"},
    "crema al cacao": {"nome_canc": "Crema al Cacao", "categoria": "Semilavorati Pasticceria"},
    "crema nocciola": {"nome_canc": "Crema alla Nocciola", "categoria": "Semilavorati Pasticceria"},
    "crema alla nocciola": {"nome_canc": "Crema alla Nocciola", "categoria": "Semilavorati Pasticceria"},
    "crema pistacchio": {"nome_canc": "Crema al Pistacchio", "categoria": "Semilavorati Pasticceria"},
    "cover pistacchio": {"nome_canc": "Copertura Pistacchio", "categoria": "Cioccolato e Cacao"},
    "crema pan di stelle": {"nome_canc": "Crema Pan di Stelle", "categoria": "Semilavorati Pasticceria"},
    # ── Frutta secca in granella e farine ──
    "granella di nocciole": {"nome_canc": "Granella di Nocciole", "categoria": "Frutta Secca"},
    "granella di pistacchi": {"nome_canc": "Granella di Pistacchio", "categoria": "Frutta Secca"},
    "granella pistacchio": {"nome_canc": "Granella di Pistacchio", "categoria": "Frutta Secca"},
    "farina di mandorle": {"nome_canc": "Farina di Mandorle", "categoria": "Frutta Secca"},
    # ── Canditi, amarene, confetture, grano cotto ──
    "scorza arancia": {"nome_canc": "Scorza d'Arancia Candita", "categoria": "Conserve e Condimenti"},
    "arancia candita": {"nome_canc": "Scorza d'Arancia Candita", "categoria": "Conserve e Condimenti"},
    "ciliegie candite": {"nome_canc": "Ciliegie Candite", "categoria": "Conserve e Condimenti"},
    "albicocche candite": {"nome_canc": "Albicocche Candite", "categoria": "Conserve e Condimenti"},
    "cubetti misti": {"nome_canc": "Canditi Misti", "categoria": "Conserve e Condimenti"},
    "confettura albicocca": {"nome_canc": "Confettura di Albicocche", "categoria": "Conserve e Condimenti"},
    "confettura di albicocca": {"nome_canc": "Confettura di Albicocche", "categoria": "Conserve e Condimenti"},
    "grano cotto": {"nome_canc": "Grano Cotto", "categoria": "Semilavorati Pasticceria"},
    # ── Coloranti ──
    "colorante": {"nome_canc": "Colorante Alimentare", "categoria": "Decorazioni"},
    "colore idrosolubile": {"nome_canc": "Colorante Alimentare", "categoria": "Decorazioni"},
    "colore spray": {"nome_canc": "Colorante Alimentare", "categoria": "Decorazioni"},
}

# Pre-ordinati per lunghezza chiave decrescente (evita sorted() ad ogni chiamata)
_SINONIMI_ORDINATI = sorted(SINONIMI_STATICI.items(), key=lambda x: -len(x[0]))


def _kw_match(chiave: str, testo: str) -> bool:
    """True se 'chiave' compare in 'testo' come parola/frase INTERA (confini unicode),
    non come sottostringa annidata. Evita i falsi positivi del vecchio match nudo:
    'aglio' dentro 'tovaglioli', 'rum' dentro 'frumento', 'te' dentro 'stella'."""
    if not chiave or not testo:
        return False
    return re.search(rf"(?<!\w){re.escape(chiave)}(?!\w)", testo) is not None


def cerca_in_sinonimi_statici(descrizione: str) -> Optional[dict]:
    """Cerca un match nei sinonimi statici. Ritorna None se non trovato."""
    desc = descrizione.lower().strip()
    # Rimuovi peso e codici dalla descrizione
    desc_clean = re.sub(r"\b\d+[\.,]?\d*\s*(kg|g|gr|ml|lt|l|pz|cl)?\b", "", desc).strip()
    desc_clean = re.sub(r"\b[A-Z0-9]{4,}\b", "", desc_clean).strip()  # codici prodotto
    desc_clean = re.sub(r"\s+", " ", desc_clean).strip()

    # Match esatto
    if desc_clean in SINONIMI_STATICI:
        return SINONIMI_STATICI[desc_clean]

    # Match come PAROLA/FRASE INTERA (mai sottostringa annidata).
    # Lista pre-ordinata per lunghezza decrescente così "cioccolato fondente" batte "cioccolato".
    for chiave, valore in _SINONIMI_ORDINATI:
        if _kw_match(chiave, desc_clean) or _kw_match(chiave, desc):
            return valore

    return None


# ── Guardia "prodotto finito ≠ ingrediente madre" (regola di dominio Enzo) ───────
# Un prodotto FINITO da banco (croissant, tartelletta, ...) o un AROMA (essenza,
# emulsione) NON è mai una materia prima madre, anche se il suo nome contiene la
# parola dell'ingrediente: "CROISSANT ... BURRO" non è Burro, "ESSENZA BURRO" è un
# aroma, non burro. Senza questa guardia il FIFO scaricherebbe un croissant come burro.
_TOKEN_FINITO = re.compile(
    r"\b(croissant|cornett\w*|brioche|tartellett\w*|girell\w*|sfogliat\w*|"
    r"plumcake|plum\s*cake|muffin|donut|bombolon\w*|krapfen|maritozz\w*|"
    r"pandoro|panettone|biscott\w*|wafer|snack|merendin\w*|fagottin\w*|"
    r"saccottin\w*|treccia|veneziana|strudel|crostatin\w*|babà|baba)\b",
    re.IGNORECASE,
)
_TOKEN_AROMA = re.compile(r"\b(essenz\w*|emulsion\w*|aroma)\b", re.IGNORECASE)

# Ingredienti madre "grezzi": non vanno MAI assegnati a un prodotto finito/aroma.
INGREDIENTI_MADRE_RAW = {
    "burro", "margarina", "latte fresco", "latte", "panna", "uova", "uovo",
    "zucchero", "farina", "cacao", "sale", "lievito", "cioccolato", "miele",
    "olio", "ricotta", "mascarpone",
}


def _prima_parola_significativa(descrizione: str) -> str:
    """Prima parola 'vera' della descrizione (saltati codici tra parentesi, numeri,
    punteggiatura e token < 3 lettere). È il NOME-TESTA del prodotto."""
    s = re.sub(r"\([^)]*\)", " ", descrizione or "")
    for tok in re.findall(r"[a-zàèéìòùç']+", s.lower()):
        if len(tok) >= 3:
            return tok
    return ""


def canonico_incoerente_con_finito(descrizione: str, canonico: str) -> bool:
    """True se il `canonico` è un ingrediente madre grezzo ma la `descrizione` è in
    realtà un prodotto FINITO da banco o un AROMA — riconosciuto dal NOME-TESTA
    (prima parola). Così "CROISSANT ... BURRO" (testa=croissant) e "ESSENZA BURRO"
    (testa=essenza) vengono scartati, mentre "MARGARINA GREEN VALLEY CROISSANT"
    (testa=margarina, 'croissant' è solo l'impiego) resta correttamente Margarina.
    Conservativa: scatta solo quando il canonico è un ingrediente madre grezzo E la
    testa è un prodotto finito/aroma."""
    if not canonico:
        return False
    if canonico.strip().lower() not in INGREDIENTI_MADRE_RAW:
        return False
    testa = _prima_parola_significativa(descrizione)
    if not testa:
        return False
    return bool(_TOKEN_FINITO.search(testa) or _TOKEN_AROMA.search(testa))


async def normalizza_batch_con_ai(descrizioni: list) -> dict:
    """
    Classifica fino a 20 descrizioni in una sola chiamata AI.
    Ritorna {descrizione: {"nome_canc": str, "categoria": str}} per quelle classificate.
    """
    if not ANTHROPIC_API_KEY or not descrizioni:
        return {}

    batch = descrizioni[:20]
    try:
        import httpx, json as _json

        lista = "\n".join(f"{i+1}. {d}" for i, d in enumerate(batch))
        async with httpx.AsyncClient(timeout=30) as hclient:
            r = await hclient.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-haiku-4-5",
                    "max_tokens": 800,
                    "system": (
                        "Sei un esperto di prodotti alimentari per ristorazione italiana. "
                        "Dato un elenco numerato di descrizioni da fatture fornitore, "
                        "rispondi SOLO con un JSON array: "
                        '[{"i":1,"nome_canc":"Nome Breve","categoria":"Categoria"}, ...] '
                        "Nessuna spiegazione. Il nome canonico: breve (2-4 parole), in italiano. "
                        "Categorie valide: Farine e Cereali, Dolcificanti, Latticini e Grassi, "
                        "Uova, Formaggi, Frutta e Verdura, Conserve e Condimenti, Cioccolato e Cacao, "
                        "Lieviti e Addensanti, Semilavorati Pasticceria, Alcolici e Liquori, "
                        "Carni e Salumi, Pesce, Condimenti, Bevande, Varie Alimentari, Non Alimentare."
                    ),
                    "messages": [
                        {
                            "role": "user",
                            "content": f"Classifica questi {len(batch)} prodotti:\n{lista}",
                        }
                    ],
                },
            )
            risposta = r.json().get("content", [{}])[0].get("text", "")

        # Parse JSON array dalla risposta
        match = re.search(r"\[.*\]", risposta, re.DOTALL)
        if not match:
            return {}
        items = _json.loads(match.group())
        result = {}
        for item in items:
            idx = int(item.get("i", 0)) - 1
            if 0 <= idx < len(batch) and item.get("nome_canc") and item.get("categoria"):
                result[batch[idx]] = {
                    "nome_canc": item["nome_canc"],
                    "categoria": item["categoria"],
                }
        return result
    except Exception as e:
        logger.warning(f"[normalizzazione] Batch AI fallito: {e}")
        return {}


async def normalizza_con_ai(descrizione: str) -> Optional[dict]:
    """
    Chiama l'AI per classificare una descrizione fattura.
    Ritorna {"nome_canc": str, "categoria": str} o None se fallisce.
    """
    if not ANTHROPIC_API_KEY:
        return None

    try:
        import httpx

        async with httpx.AsyncClient(timeout=15) as hclient:
            r = await hclient.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-haiku-4-5",
                    "max_tokens": 150,
                    "system": (
                        "Sei un esperto di prodotti alimentari per la ristorazione italiana. "
                        "Dato una descrizione di un prodotto da una fattura fornitore, rispondi SOLO con un JSON "
                        'nel formato: {"nome_canc": "Nome Canonico Italiano", "categoria": "Categoria"} '
                        "senza spiegazioni. Il nome canonico deve essere breve (2-4 parole), in italiano. "
                        "La categoria deve essere una di: Farine e Cereali, Dolcificanti, Latticini e Grassi, "
                        "Uova, Formaggi, Frutta e Verdura, Conserve e Condimenti, Cioccolato e Cacao, "
                        "Lieviti e Addensanti, Semilavorati Pasticceria, Alcolici e Liquori, "
                        "Carni e Salumi, Pesce, Condimenti, Bevande, Varie Alimentari, Non Alimentare."
                    ),
                    "messages": [
                        {
                            "role": "user",
                            "content": f"Classifica questo prodotto da fattura: '{descrizione}'",
                        }
                    ],
                },
            )
            risposta = r.json().get("content", [{}])[0].get("text", "")

        # Parse JSON dalla risposta
        match = re.search(r"\{[^}]+\}", risposta)
        if match:
            import json

            data = json.loads(match.group())
            if "nome_canc" in data and "categoria" in data:
                return data
    except Exception:
        logger.debug("[normalizzazione] errore non bloccante ignorato")

    return None


async def get_o_crea_mapping(descrizione: str) -> dict:
    """
    Cerca o crea un mapping per la descrizione.
    Priorità: DB → Sinonimi statici → AI
    """
    desc_key = descrizione.lower().strip()[:200]

    # 1. Cerca nel DB
    esistente = await db.nome_mapping.find_one({"descrizione_key": desc_key}, {"_id": 0})
    if esistente:
        return esistente

    # 2. Cerca nei sinonimi statici
    mapping_statico = cerca_in_sinonimi_statici(descrizione)
    if mapping_statico:
        doc = {
            "descrizione_originale": descrizione,
            "descrizione_key": desc_key,
            "nome_canc": mapping_statico["nome_canc"],
            "categoria": mapping_statico["categoria"],
            "fonte": "statico",
            "creato_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.nome_mapping.update_one({"descrizione_key": desc_key}, {"$set": doc}, upsert=True)
        # MODIFICA 5: Propaga nome_canonico al dizionario_prodotti
        if doc.get("nome_canc"):
            try:
                await db.dizionario_prodotti.update_many(
                    {
                        "nome_normalizzato": {"$regex": re.escape(desc_key[:15]), "$options": "i"},
                        "nome_canonico": {"$exists": False},
                    },
                    {"$set": {"nome_canonico": doc["nome_canc"]}},
                )
            except Exception as e:
                logger.debug(f"[normalizzazione] Propagazione nome_canonico: {e}")
        return doc

    # 3. AI (solo se key disponibile)
    mapping_ai = await normalizza_con_ai(descrizione)
    if mapping_ai:
        doc = {
            "descrizione_originale": descrizione,
            "descrizione_key": desc_key,
            "nome_canc": mapping_ai["nome_canc"],
            "categoria": mapping_ai["categoria"],
            "fonte": "ai",
            "creato_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.nome_mapping.update_one({"descrizione_key": desc_key}, {"$set": doc}, upsert=True)
        # MODIFICA 5: Propaga nome_canonico al dizionario_prodotti
        if doc.get("nome_canc"):
            try:
                await db.dizionario_prodotti.update_many(
                    {
                        "nome_normalizzato": {"$regex": re.escape(desc_key[:15]), "$options": "i"},
                        "nome_canonico": {"$exists": False},
                    },
                    {"$set": {"nome_canonico": doc["nome_canc"]}},
                )
            except Exception:
                logger.debug("[normalizzazione] errore non bloccante ignorato")
        return doc

    return {}


@router.post("/processa-nuovi-prodotti")
async def processa_nuovi_prodotti(limit: int = 50):
    """
    Normalizza i prodotti del dizionario che non hanno ancora un nome canonico.
    Processa solo i NUOVI (non ancora presenti nel nome_mapping).
    """
    # Prendi tutti i prodotti del dizionario
    prodotti = await db.dizionario_prodotti.find(
        {}, {"_id": 0, "nome_originale": 1, "nome_normalizzato": 1, "fornitore": 1, "prezzo_kg": 1}
    ).to_list(10000)

    # Prendi i mapping già esistenti
    mapping_esistenti_keys = set()
    async for m in db.nome_mapping.find({}, {"descrizione_key": 1, "_id": 0}):
        mapping_esistenti_keys.add(m["descrizione_key"])

    nuovi = [
        p
        for p in prodotti
        if p.get("nome_originale", "").lower()[:200] not in mapping_esistenti_keys
    ]
    nuovi = nuovi[:limit]

    processati = 0
    statici = 0
    ai = 0
    errori = 0

    if nuovi:
        # ── Batch AI: una sola chiamata per tutti i nuovi ──────────────
        desc_list = [
            p.get("nome_originale", p.get("nome_normalizzato", ""))
            for p in nuovi
            if p.get("nome_originale") or p.get("nome_normalizzato")
        ]
        batch_results = await normalizza_batch_con_ai(desc_list)

        for prod in nuovi:
            desc = prod.get("nome_originale", prod.get("nome_normalizzato", ""))
            if not desc:
                continue
            desc_key = desc.lower().strip()[:200]
            try:
                mapping_statico = cerca_in_sinonimi_statici(desc)
                if mapping_statico:
                    doc = {
                        "descrizione_originale": desc,
                        "descrizione_key": desc_key,
                        "nome_canc": mapping_statico["nome_canc"],
                        "categoria": mapping_statico["categoria"],
                        "fonte": "statico",
                        "creato_at": datetime.now(timezone.utc).isoformat(),
                    }
                    await db.nome_mapping.update_one(
                        {"descrizione_key": desc_key}, {"$set": doc}, upsert=True
                    )
                    statici += 1
                    processati += 1
                elif desc in batch_results:
                    br = batch_results[desc]
                    doc = {
                        "descrizione_originale": desc,
                        "descrizione_key": desc_key,
                        "nome_canc": br["nome_canc"],
                        "categoria": br["categoria"],
                        "fonte": "ai",
                        "creato_at": datetime.now(timezone.utc).isoformat(),
                    }
                    await db.nome_mapping.update_one(
                        {"descrizione_key": desc_key}, {"$set": doc}, upsert=True
                    )
                    ai += 1
                    processati += 1
                else:
                    errori += 1
            except Exception:
                errori += 1

    # Aggiorna nome_canonico nel dizionario SOLO per i mapping appena creati
    aggiornati_diz = 0
    nuovi_desc_keys = [
        p.get("nome_originale", p.get("nome_normalizzato", "")).lower().strip()[:200]
        for p in nuovi
        if p.get("nome_originale") or p.get("nome_normalizzato")
    ]
    if nuovi_desc_keys:
        async for m in db.nome_mapping.find(
            {"descrizione_key": {"$in": nuovi_desc_keys}, "nome_canc": {"$exists": True}},
            {"_id": 0, "descrizione_key": 1, "nome_canc": 1, "categoria": 1},
        ):
            nome_canc = m.get("nome_canc")
            desc_key = m.get("descrizione_key", "")
            if nome_canc and desc_key:
                res = await db.dizionario_prodotti.update_many(
                    {"nome_originale": {"$regex": f"^{re.escape(desc_key[:30])}", "$options": "i"}},
                    {
                        "$set": {
                            "nome_canonico": nome_canc,
                            "categoria_canonica": m.get("categoria", ""),
                        }
                    },
                )
                aggiornati_diz += res.modified_count

    return {
        "processati": processati,
        "via_sinonimi_statici": statici,
        "via_ai": ai,
        "errori": errori,
        "nuovi_trovati": len(nuovi),
        "aggiornati_dizionario": aggiornati_diz,
    }


@router.post("/processa-tutti-aliases")
async def processa_tutti_aliases(limit: int = 200):
    """
    One-shot: per ogni voce dizionario_prodotti, cerca il mapping in nome_mapping
    e propaga nome_canonico + popola aliases[] con nome_normalizzato come alias.
    Processa fino a `limit` voci per chiamata (chiamare più volte se necessario).
    """
    prodotti = (
        await db.dizionario_prodotti.find(
            {"$or": [{"aliases": {"$exists": False}}, {"aliases": {"$size": 0}}]},
            {"_id": 0, "id": 1, "nome_normalizzato": 1, "nome_originale": 1, "nome_canonico": 1},
        )
        .limit(limit)
        .to_list(limit)
    )

    aggiornati = 0
    for p in prodotti:
        nome_norm = p.get("nome_normalizzato", "").strip()
        nome_orig = p.get("nome_originale", nome_norm).strip()

        mapping = await db.nome_mapping.find_one(
            {
                "$or": [
                    {"descrizione_key": nome_norm[:200]},
                    {"descrizione_key": nome_orig.lower()[:200]},
                ]
            },
            {"_id": 0, "nome_canc": 1},
        )

        alias_set = [nome_norm]
        if nome_orig.lower() != nome_norm:
            alias_set.append(nome_orig.lower())

        update: dict = {"$addToSet": {"aliases": {"$each": alias_set}}}
        if mapping and mapping.get("nome_canc"):
            update["$set"] = {"nome_canonico": mapping["nome_canc"]}

        try:
            await db.dizionario_prodotti.update_one({"id": p["id"]}, update)
            aggiornati += 1
        except Exception as e:
            logger.warning(f"[normalizzazione] Update dizionario fallito id={p.get('id')}: {e}")

    rimanenti = await db.dizionario_prodotti.count_documents({"nome_canonico": {"$exists": False}})
    return {
        "processati": len(prodotti),
        "aggiornati": aggiornati,
        "rimanenti_senza_canonico": rimanenti,
    }


@router.get("/da-revisionare")
async def mapping_da_revisionare(limit: int = 100):
    """
    Lista dei mapping incerti (fonte 'ai' o senza categoria) che l'utente può confermare/correggere.
    """
    docs = (
        await db.nome_mapping.find(
            {
                "$or": [
                    {"fonte": "ai"},
                    {"categoria": {"$in": [None, "", "Varie Alimentari", "Non Alimentare"]}},
                    {"confermato": {"$ne": True}},
                ]
            },
            {"_id": 0},
        )
        .limit(limit)
        .to_list(limit)
    )
    return {"totale": len(docs), "mapping": docs}


@router.post("/correggi-mapping")
async def correggi_mapping(payload: dict = Body(...)):
    """
    Correzione manuale di un mapping commerciale → nome usuale.
    Body: {descrizione_key, nome_canc, categoria}
    Aggiorna anche tutti i prodotti del dizionario collegati.
    """
    desc_key = (payload.get("descrizione_key") or "").lower().strip()
    nome_canc = (payload.get("nome_canc") or "").strip()
    categoria = (payload.get("categoria") or "").strip()
    if not desc_key or not nome_canc:
        raise HTTPException(status_code=400, detail="descrizione_key e nome_canc obbligatori")

    await db.nome_mapping.update_one(
        {"descrizione_key": desc_key},
        {
            "$set": {
                "nome_canc": nome_canc,
                "categoria": categoria or "Varie Alimentari",
                "fonte": "manuale",
                "confermato": True,
                "aggiornato_at": datetime.now(timezone.utc).isoformat(),
            }
        },
        upsert=True,
    )
    # Propaga al dizionario prodotti
    res = await db.dizionario_prodotti.update_many(
        {"nome_normalizzato": {"$regex": re.escape(desc_key[:15]), "$options": "i"}},
        {"$set": {"nome_canonico": nome_canc, "ingrediente_canonico": nome_canc}},
    )
    return {"success": True, "prodotti_aggiornati": res.modified_count}


@router.get("/nomi-usuali")
async def nomi_usuali_disponibili():
    """
    Elenco dei nomi usuali (canonici) noti, con quanti prodotti commerciali mappano su ciascuno.
    Usato per il cambio ingrediente di massa.
    """
    pipeline = [
        {"$match": {"nome_canc": {"$nin": [None, ""]}}},
        {
            "$group": {
                "_id": "$nome_canc",
                "count": {"$sum": 1},
                "categoria": {"$first": "$categoria"},
            }
        },
        {"$sort": {"_id": 1}},
    ]
    rows = await db.nome_mapping.aggregate(pipeline).to_list(1000)
    return [
        {
            "nome_usuale": r["_id"],
            "prodotti_mappati": r["count"],
            "categoria": r.get("categoria", ""),
        }
        for r in rows
    ]


@router.post("/cambia-ingrediente-massa")
async def cambia_ingrediente_massa(payload: dict = Body(...)):
    """
    Sostituisce un ingrediente in più ricette selezionate (flag).
    Body: {
        ricette_ids: [id, ...],   # ricette su cui applicare (vuoto = tutte quelle che contengono il vecchio)
        nome_vecchio: "farina 00",
        nome_nuovo: "Farina Manitoba",
        prodotto_dizionario_id: "..." (opzionale, per agganciare prezzo)
    }
    """
    ricette_ids = payload.get("ricette_ids") or []
    nome_vecchio = (payload.get("nome_vecchio") or "").strip().lower()
    nome_nuovo = (payload.get("nome_nuovo") or "").strip()
    nuovo_id = payload.get("prodotto_dizionario_id")
    if not nome_vecchio or not nome_nuovo:
        raise HTTPException(status_code=400, detail="nome_vecchio e nome_nuovo obbligatori")

    # Prezzo del nuovo prodotto (se fornito)
    nuovo_prezzo = None
    if nuovo_id:
        prod = await db.dizionario_prodotti.find_one({"id": nuovo_id}, {"_id": 0, "prezzo_kg": 1})
        if prod:
            nuovo_prezzo = float(prod.get("prezzo_kg", 0) or 0)

    # Query ricette: quelle selezionate, oppure tutte quelle che contengono il vecchio ingrediente
    if ricette_ids:
        query = {"id": {"$in": ricette_ids}}
    else:
        query = {
            "ingredienti_dettaglio": {
                "$elemMatch": {"nome": {"$regex": re.escape(nome_vecchio), "$options": "i"}}
            }
        }

    ricette = await db.ricette.find(query, {"_id": 0}).to_list(2000)
    modificate = 0
    for r in ricette:
        cambiato = False
        for ing in r.get("ingredienti_dettaglio", []):
            if nome_vecchio in (ing.get("nome") or "").lower():
                ing["nome"] = nome_nuovo
                if nuovo_id:
                    ing["prodotto_dizionario_id"] = nuovo_id
                if nuovo_prezzo is not None:
                    ing["prezzo_kg"] = nuovo_prezzo
                cambiato = True
        if cambiato:
            await db.ricette.update_one(
                {"id": r["id"]},
                {
                    "$set": {
                        "ingredienti_dettaglio": r["ingredienti_dettaglio"],
                        "ingredienti_aggiornati_il": datetime.now(timezone.utc).isoformat(),
                    }
                },
            )
            modificate += 1

    return {
        "success": True,
        "ricette_modificate": modificate,
        "nome_vecchio": nome_vecchio,
        "nome_nuovo": nome_nuovo,
    }


@router.get("/ricette-con-ingrediente")
async def ricette_con_ingrediente(nome: str = Query(...)):
    """
    Lista ricette che contengono un dato ingrediente — per il cambio di massa con flag.
    """
    pattern = re.escape(nome.strip())
    ricette = await db.ricette.find(
        {"ingredienti_dettaglio": {"$elemMatch": {"nome": {"$regex": pattern, "$options": "i"}}}},
        {"_id": 0, "id": 1, "nome": 1, "reparto": 1},
    ).to_list(2000)
    return [
        {"id": r["id"], "nome": r.get("nome"), "reparto": r.get("reparto", "")} for r in ricette
    ]


@router.get("/mapping")
async def lista_mapping(skip: int = 0, limit: int = 100, fonte: str = ""):
    """Lista tutti i mapping salvati"""
    query = {}
    if fonte:
        query["fonte"] = fonte
    mapping = await db.nome_mapping.find(query, {"_id": 0}).skip(skip).limit(limit).to_list(limit)
    total = await db.nome_mapping.count_documents(query)
    return {"mapping": mapping, "total": total}


@router.get("/prodotti-senza-peso")
async def prodotti_senza_peso(limit: int = 200):
    """
    Prodotti nel dizionario senza peso confezione estratto (peso_confezione = 0 o assente).
    Questi hanno prezzo/kg potenzialmente approssimativo.
    """
    # Considera "senza peso" SOLO prodotti con:
    # - peso mancante
    # - peso ≤ 0.001 kg (praticamente zero, non un valore reale estratto)
    # - unita = "pz" (fallback esplicito senza peso estratto)
    # NON include monoporzioni legittime (es. 9g pesto = 0.009kg, 10g wurstel = 0.01kg)
    prodotti = (
        await db.dizionario_prodotti.find(
            {
                "$or": [
                    {"peso_confezione": {"$exists": False}},
                    {"peso_confezione": {"$lte": 0.001}},
                    {"unita_confezione": "pz"},
                ],
                "prezzo_kg": {"$gt": 0},
            },
            {
                "_id": 0,
                "nome_originale": 1,
                "nome_normalizzato": 1,
                "fornitore": 1,
                "prezzo_kg": 1,
                "unita_confezione": 1,
                "prezzo_confezione": 1,
            },
        )
        .sort("fornitore", 1)
        .limit(limit)
        .to_list(limit)
    )

    total = await db.dizionario_prodotti.count_documents(
        {
            "$or": [
                {"peso_confezione": {"$exists": False}},
                {"peso_confezione": {"$lte": 0.001}},
                {"unita_confezione": "pz"},
            ],
            "prezzo_kg": {"$gt": 0},
        }
    )

    return {"prodotti": prodotti, "total": total}


@router.post("/correggi-peso")
async def correggi_peso_prodotto(
    nome_normalizzato: str,
    peso_kg: float,
    unita: str = "kg",
    tipo_quantita: str = "totale",
):
    """Corregge manualmente il peso di un prodotto nel dizionario — è la regola
    permanente per fornitore+prodotto: da qui in poi ogni fattura futura con questo
    stesso prodotto la userà in automatico (vedi aggiorna_dizionario_prodotto in
    fatture.py e extract_and_save_lotti_from_fattura in lotti_fornitori.py).

    tipo_quantita:
    - "totale": il campo Quantità della fattura È GIÀ il peso/volume reale
      (es. farina KG.25, quantita=250 = 250 kg veri — verificato che alcuni
      fornitori pesano/fatturano così).
    - "confezioni": il campo Quantità conta CONFEZIONI/CARTONI, peso_kg è il peso
      di UNA confezione (es. olio "L.5", quantita=2 bottiglie da 5L ciascuna —
      il peso reale totale è quantita × peso_kg, non quantita da solo).

    nome_normalizzato passato come query param (non nel path) perché può contenere '/'
    (es. lotti tipo 'L.041/2026') che romperebbe il routing basato su path.
    """
    result = await db.dizionario_prodotti.update_many(
        {"nome_normalizzato": nome_normalizzato},
        {
            "$set": {
                "peso_confezione": peso_kg,
                "unita_confezione": unita,
                "tipo_quantita": tipo_quantita,
                "peso_corretto_manualmente": True,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        },
    )
    return {"aggiornati": result.modified_count}


@router.post("/aggiungi-fornitore-speciale")
async def aggiungi_fornitore_speciale(fornitore: str, tipo: str = "prezzo_per_kg"):
    """
    Aggiunge un fornitore alla configurazione speciale salvata in MongoDB.
    tipo: 'prezzo_per_kg' = Qt=confezioni, Prezzo=€/kg
          'prezzo_per_confezione' = Qt=confezioni, Prezzo=€/confezione (standard)
    """
    doc = {
        "fornitore_lower": fornitore.lower().strip(),
        "fornitore_originale": fornitore.strip(),
        "tipo": tipo,
        "aggiunto_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.fornitori_config.update_one(
        {"fornitore_lower": doc["fornitore_lower"]}, {"$set": doc}, upsert=True
    )
    return {"success": True, "fornitore": fornitore, "tipo": tipo}


@router.get("/fornitori-config")
async def get_fornitori_config():
    """Lista fornitori con configurazione speciale"""
    config = await db.fornitori_config.find({}, {"_id": 0}).to_list(200)
    return config


@router.delete("/fornitori-config/{fornitore_lower}")
async def rimuovi_fornitore_config(fornitore_lower: str, _admin=Depends(require_admin)):
    """Rimuove un fornitore dalla configurazione speciale"""
    result = await db.fornitori_config.delete_one({"fornitore_lower": fornitore_lower})
    return {"eliminato": result.deleted_count > 0}


# ── DIZIONARIO UNIVERSALE da fatture XML (richiesta Enzo) ────────────────────────
# Legge OGNI riga-prodotto di TUTTE le fatture, capisce l'ingrediente madre di ogni
# descrizione e popola db.nome_mapping (single source della canonicalizzazione, usato
# da calcola_nome_canonico). Deterministico (sinonimi statici + matcher keyword) e, sui
# residui, AI a batch se è configurata ANTHROPIC_API_KEY. La guardia finito≠madre evita
# di promuovere prodotti da banco/aromi a ingrediente madre.
async def _costruisci_dizionario_da_fatture(usa_ai: bool = True):
    from app.lotti.routers.ingredienti import match_livello2, _consolida_canonico
    now = lambda: datetime.now(timezone.utc).isoformat()

    async def _set(**kw):
        await db.sistema_stato.update_one(
            {"chiave": "dizionario_universale"}, {"$set": {"chiave": "dizionario_universale", **kw}}, upsert=True
        )

    await _set(stato="in_corso", avviata=now(), fatte=0, totali=0, risolti=0, ai=0, finiti=0, ignoti=0, esito=None)

    # 1) descrizioni distinte da TUTTE le fatture (ogni riga)
    seen, descr = set(), []
    async for f in db.fatture.find({}, {"_id": 0, "prodotti": 1}):
        for p in (f.get("prodotti") or []):
            d = (p.get("descrizione") or "").strip()
            k = d.lower()[:200]
            if d and k not in seen:
                seen.add(k); descr.append(d)
    totali = len(descr)

    # 2) mapping già esistenti
    mapped = set()
    async for m in db.nome_mapping.find({}, {"descrizione_key": 1, "_id": 0}):
        if m.get("descrizione_key"):
            mapped.add(m["descrizione_key"])

    fatte = risolti = ai_usati = finiti = 0
    residui = []
    sample_ignoti = []

    async def _salva(d, c, fonte):
        k = d.lower()[:200]
        await db.nome_mapping.update_one(
            {"descrizione_key": k},
            {"$set": {"descrizione_originale": d, "descrizione_key": k,
                      "nome_canc": c, "fonte": fonte, "creato_at": now()}},
            upsert=True,
        )
        mapped.add(k)

    # 3) passata deterministica (veloce)
    for d in descr:
        k = d.lower()[:200]
        fatte += 1
        if k in mapped:
            continue
        c = None
        mm = cerca_in_sinonimi_statici(d)
        if mm and mm.get("nome_canc"):
            c = mm["nome_canc"]
        if not c:
            c = match_livello2(d)
        c = _consolida_canonico(c) if c else None
        if c and canonico_incoerente_con_finito(d, c):
            finiti += 1; c = None
        if c:
            await _salva(d, c, "auto"); risolti += 1
        else:
            residui.append(d)
        if fatte % 200 == 0:
            await _set(stato="in_corso", fatte=fatte, totali=totali, risolti=risolti, ai=ai_usati, finiti=finiti, ignoti=len(residui))

    # 4) AI a batch sui residui (se disponibile)
    if usa_ai and ANTHROPIC_API_KEY and residui:
        for i in range(0, len(residui), 20):
            chunk = residui[i:i + 20]
            try:
                res = await normalizza_batch_con_ai(chunk)
            except Exception:
                res = {}
            for d, info in (res or {}).items():
                c = _consolida_canonico(info.get("nome_canc"))
                if c and canonico_incoerente_con_finito(d, c):
                    finiti += 1; continue
                if c:
                    await _salva(d, c, "ai"); risolti += 1; ai_usati += 1
            await _set(stato="in_corso", fatte=fatte, totali=totali, risolti=risolti, ai=ai_usati, finiti=finiti,
                       ignoti=max(0, totali - risolti - finiti - (totali - len(residui))))
        # ricalcola ignoti reali
    ignoti_finali = [d for d in residui if d.lower()[:200] not in mapped]
    sample_ignoti = ignoti_finali[:40]

    await _set(
        stato="completata", completata=now(), fatte=fatte, totali=totali,
        risolti=risolti, ai=ai_usati, finiti=finiti, ignoti=len(ignoti_finali),
        ai_disponibile=bool(ANTHROPIC_API_KEY),
        esito={"descrizioni_distinte": totali, "mappature_risolte": risolti,
               "via_ai": ai_usati, "prodotti_finiti_scartati": finiti,
               "ancora_ignoti": len(ignoti_finali)},
        esempi_ignoti=sample_ignoti,
    )


@router.post("/costruisci-da-fatture")
async def costruisci_dizionario_da_fatture(background: BackgroundTasks, usa_ai: bool = True):
    """Costruisce/aggiorna il DIZIONARIO UNIVERSALE leggendo ogni riga-prodotto di tutte
    le fatture e mappando ciascuna descrizione all'ingrediente madre (db.nome_mapping).
    Avvio in background; stato live su GET /normalizzazione/costruisci-da-fatture/stato."""
    st = await db.sistema_stato.find_one({"chiave": "dizionario_universale"}, {"_id": 0})
    if st and st.get("stato") == "in_corso":
        return {"ok": True, "gia_in_corso": True, "stato": st}
    background.add_task(_costruisci_dizionario_da_fatture, usa_ai)
    return {"ok": True, "avviata": True, "nota": "Stato: GET /normalizzazione/costruisci-da-fatture/stato"}


@router.get("/costruisci-da-fatture/stato")
async def stato_dizionario_universale():
    st = await db.sistema_stato.find_one({"chiave": "dizionario_universale"}, {"_id": 0})
    return st or {"stato": "mai_eseguita"}


@router.post("/ripulisci-dizionario-canonici")
async def ripulisci_dizionario_canonici(_admin=Depends(require_admin)):
    """Pulizia chirurgica di db.dizionario_prodotti.nome_canonico (regole Enzo):
    (1) FINITO≠MADRE: se il prodotto è un finito (croissant/cornetto/tartelletta/aroma…) ma
        ha un canonico = ingrediente-madre grezzo (es. 'Burro'), lo si RIMUOVE (Burro inquinato).
    (2) MARGARINE → 'Margarina': i prodotti margarina (Melange, Wiener, Green Valley/Platte,
        Homillina, Plunderplat, o 'margarina …') vengono unificati al canonico madre 'Margarina'.
    Non tocca gli altri canonici (intervento mirato, basso rischio)."""
    from app.lotti.routers.ingredienti import match_livello2, _consolida_canonico
    MARG = ("melange", "wiener", "green valley", "green platte", "homillina", "plunderplat", "margarina")
    tot = finiti_ripuliti = margarine_unificate = 0
    esempi = {"finiti": [], "margarine": []}
    # Carica TUTTO in memoria prima di scrivere: leggere e scrivere sulla stessa
    # collection dentro un cursore attivo lo destabilizza (documenti saltati).
    docs = await db.dizionario_prodotti.find(
        {}, {"_id": 1, "nome_originale": 1, "nome_normalizzato": 1, "nome_canonico": 1}
    ).to_list(100000)
    for p in docs:
        tot += 1
        raw = (p.get("nome_originale") or p.get("nome_normalizzato") or "").strip()
        if not raw:
            continue
        attuale = p.get("nome_canonico")
        raw_low = raw.lower()
        # (1) Burro/madre inquinato da finito
        if attuale and canonico_incoerente_con_finito(raw, attuale):
            await db.dizionario_prodotti.update_one({"_id": p["_id"]}, {"$unset": {"nome_canonico": ""}})
            finiti_ripuliti += 1
            if len(esempi["finiti"]) < 15:
                esempi["finiti"].append({"prodotto": raw[:50], "era": attuale})
            continue
        # (2) Margarine → 'Margarina'
        if any(t in raw_low for t in MARG):
            c = None
            mm = cerca_in_sinonimi_statici(raw)
            if mm and mm.get("nome_canc"):
                c = mm["nome_canc"]
            if not c:
                c = match_livello2(raw)
            c = _consolida_canonico(c) if c else None
            if c == "Margarina" and attuale != "Margarina" and not canonico_incoerente_con_finito(raw, "Margarina"):
                await db.dizionario_prodotti.update_one({"_id": p["_id"]}, {"$set": {"nome_canonico": "Margarina"}})
                margarine_unificate += 1
                if len(esempi["margarine"]) < 15:
                    esempi["margarine"].append({"prodotto": raw[:50], "era": attuale or "—"})
        # (3) Stesso fix sul campo separato ingrediente_canonico (se inquinato da finito)
        ic = p.get("ingrediente_canonico")
        if ic and canonico_incoerente_con_finito(raw, ic):
            await db.dizionario_prodotti.update_one({"_id": p["_id"]}, {"$unset": {"ingrediente_canonico": ""}})

    # (4) Pulizia db.nome_mapping (single source usato anche dall'arricchimento del dizionario):
    # rimuove le voci LEGACY dove la descrizione è un prodotto FINITO ma il canonico è una
    # madre grezza (es. "croissant … burro" → Burro), e unifica le margarine a 'Margarina'.
    map_finiti = map_marg = 0
    maps = await db.nome_mapping.find(
        {}, {"_id": 1, "descrizione_originale": 1, "descrizione_key": 1, "nome_canc": 1}
    ).to_list(100000)
    for m in maps:
        raw = (m.get("descrizione_originale") or m.get("descrizione_key") or "").strip()
        c = m.get("nome_canc")
        if not raw or not c:
            continue
        if canonico_incoerente_con_finito(raw, c):
            await db.nome_mapping.delete_one({"_id": m["_id"]})
            map_finiti += 1
            if len(esempi["finiti"]) < 30:
                esempi["finiti"].append({"prodotto": raw[:50], "era": c, "fonte": "nome_mapping"})
            continue
        if c != "Margarina" and any(t in raw.lower() for t in MARG):
            cc = cerca_in_sinonimi_statici(raw)
            cc = (cc or {}).get("nome_canc") or match_livello2(raw)
            cc = _consolida_canonico(cc) if cc else None
            if cc == "Margarina" and not canonico_incoerente_con_finito(raw, "Margarina"):
                await db.nome_mapping.update_one({"_id": m["_id"]}, {"$set": {"nome_canc": "Margarina"}})
                map_marg += 1

    return {
        "ok": True,
        "dizionario_prodotti": tot,
        "finiti_ripuliti_da_madre": finiti_ripuliti,
        "margarine_unificate": margarine_unificate,
        "nome_mapping_finiti_rimossi": map_finiti,
        "nome_mapping_margarine_unificate": map_marg,
        "esempi": esempi,
    }


@router.post("/pulisci-falsi-positivi-sottostringa")
async def pulisci_falsi_positivi_sottostringa(applica: bool = False, _admin=Depends(require_admin)):
    """Rimuove dal dizionario (nome_mapping) i canonici creati dal VECCHIO match
    per sottostringa nuda (bug: 'telo protettivo'→Tè, 'tovaglioli'→Aglio,
    'frumento'→Rum). Criterio sicuro e chirurgico: un mapping è falso positivo
    SOLO se esiste una chiave dei sinonimi statici con lo stesso nome_canc che
    compare nella descrizione come SOTTOSTRINGA ma NON come parola intera, e il
    matcher corretto NON riproduce quel canonico. NON tocca i mapping
    manuali/confermati. applica=false → dry-run (mostra cosa rimuoverebbe)."""
    canc2keys: dict[str, list] = {}
    for k, v in SINONIMI_STATICI.items():
        nc = (v.get("nome_canc") or "").strip()
        if nc:
            canc2keys.setdefault(nc, []).append(k)

    maps = await db.nome_mapping.find(
        {}, {"_id": 1, "descrizione_originale": 1, "descrizione_key": 1,
             "nome_canc": 1, "fonte": 1, "confermato": 1}
    ).to_list(100000)

    ids_del, preview = [], []
    for m in maps:
        if m.get("confermato") or (m.get("fonte") == "manuale"):
            continue
        c = (m.get("nome_canc") or "").strip()
        if not c or c not in canc2keys:
            continue
        raw = (m.get("descrizione_originale") or m.get("descrizione_key") or "").lower().strip()
        if not raw:
            continue
        # una chiave di QUESTO canonico compare come sottostringa ma non come parola intera?
        falso = any(k and (k in raw) and not _kw_match(k, raw) for k in canc2keys[c])
        if not falso:
            continue
        # e il matcher CORRETTO non riproduce questo canonico → artefatto del bug
        fixed = cerca_in_sinonimi_statici(raw)
        if not fixed or (fixed.get("nome_canc") or "").strip() != c:
            ids_del.append(m["_id"])
            if len(preview) < 60:
                preview.append({"descrizione": raw[:60], "era": c})

    if applica and ids_del:
        await db.nome_mapping.delete_many({"_id": {"$in": ids_del}})

    return {
        "dry_run": not applica,
        "totale_mapping": len(maps),
        "falsi_positivi": len(ids_del),
        "rimossi": len(ids_del) if applica else 0,
        "esempi": preview,
    }
