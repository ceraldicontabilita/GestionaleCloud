"""
aggiornamento_ricette.py
═══════════════════════════════════════════════════════════════════
Motore di aggiornamento automatico ricette da fatture ricevute.

LOGICA CENTRALE:
  Quando arriva una fattura (es. Fiorentino con "Farina Caputo 00"),
  questo modulo:
  1. Trova tutte le ricette che usano un ingrediente simile ("farina 00")
  2. Aggiorna l'ingrediente nella ricetta con i dati reali dell'ultima
     merce ricevuta: fornitore, n° fattura, data, data scadenza
  3. Così stampando la ricetta oggi vedrai:
     "Farina Caputo 00 — Fiorentino — fatt.2024/1234 — scad.30/06/2026"

Chiamato automaticamente dopo ogni import fattura.
Espone anche endpoint manuali per forzare l'aggiornamento.

TERMINOLOGIA CORRETTA (uniformata):
  materia_prima  = prodotto ricevuto dal fornitore (da fattura/DDT)
  lotto_produzione = lotto che Ceraldi produce (Torta Margherita 23/04)
  ingrediente_ricetta = riga ingrediente dentro una ricetta
═══════════════════════════════════════════════════════════════════
"""

import re
import logging
from datetime import datetime, timezone

from fastapi import APIRouter
from app.lotti.db import database as db

try:
    from rapidfuzz import fuzz as _fuzz

    def _fuzzy_ratio(a, b):
        return _fuzz.token_sort_ratio(a, b)

except ImportError:
    from fuzzywuzzy import fuzz as _fuzz_legacy

    def _fuzzy_ratio(a, b):
        return _fuzz_legacy.token_sort_ratio(a, b)


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/aggiornamento-ricette", tags=["Aggiornamento Ricette"])

# ── Dizionario sinonimi ingredienti ────────────────────────────────────────
# Mappa: parola chiave → varianti che potrebbero arrivare in fattura
SINONIMI_INGREDIENTI: dict[str, list[str]] = {
    "farina": ["farina", "flour", "tipo 00", "tipo0", "tipo 1", "tipo 2", "semola"],
    "zucchero": ["zucchero", "saccarosio", "sugar", "zucch"],
    "burro": ["burro", "butter", "grasso butirrico"],
    "uova": ["uova", "uovo", "egg", "tuorlo", "albume"],
    "latte": ["latte", "milk", "latte intero", "latte parz"],
    "panna": ["panna", "cream", "panna fresca", "panna uht"],
    "olio": ["olio", "oil", "olio evo", "olio oliva", "olio semi"],
    "sale": ["sale", "sal", "sodium chloride"],
    "lievito": ["lievito", "yeast", "lievito madre", "liev. chimico"],
    "cacao": ["cacao", "cocoa", "cioccolato", "chocolate"],
    "vaniglia": ["vaniglia", "vanilla", "vanillina", "bacca vaniglia"],
    "limone": ["limone", "lemon", "scorza limone", "succo limone"],
    "amarene": ["amarene", "ciliegia", "cherry", "marasche"],
    "nocciole": ["nocciola", "nocciole", "hazelnut", "granella nocciole"],
    "mandorle": ["mandorla", "mandorle", "almond"],
    "pistacchio": ["pistacchio", "pistachio"],
    "ricotta": ["ricotta", "ricott"],
    "mozzarella": ["mozzarella", "fior di latte"],
    "formaggio": ["formaggio", "cheese", "grana", "parmigiano", "pecorino"],
}


def _normalizza(s: str) -> str:
    """Normalizza una stringa per il confronto."""
    s = s.lower().strip()
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s)
    # Rimuovi unità di misura comuni dalla descrizione fattura
    s = re.sub(r"\b\d+[.,]?\d*\s*(?:kg|g|gr|lt|l|ml|cl|pz|pezzi|conf|crt|cartoni?)\b", "", s)
    return s.strip()


def _calcola_similarita(a: str, b: str) -> float:
    """Calcola similarità 0.0–1.0 usando rapidfuzz (o fuzzywuzzy fallback)."""
    a_norm = _normalizza(a)
    b_norm = _normalizza(b)
    if not a_norm or not b_norm:
        return 0.0
    if a_norm == b_norm:
        return 1.0
    if a_norm in b_norm or b_norm in a_norm:
        return 0.9
    # Usa rapidfuzz per un confronto più accurato
    score = _fuzzy_ratio(a_norm, b_norm) / 100.0
    if score >= 0.6:
        return score
    # Fallback sinonimi — match a PAROLA INTERA (evita "uova" dentro "nuova",
    # "sale" dentro "salame", ecc.: erano falsi positivi che inquinavano le ricette)
    def _ha(testo: str, varianti: list[str]) -> bool:
        return any(re.search(r"\b" + re.escape(v) + r"\b", testo) for v in varianti)

    for chiave, varianti in SINONIMI_INGREDIENTI.items():
        if _ha(a_norm, varianti) and _ha(b_norm, varianti):
            return 0.75
    return score


def _match_ingrediente_prodotto(
    nome_ingrediente: str, nome_prodotto_fattura: str, soglia: float = 0.6
) -> bool:
    """
    Ritorna True se l'ingrediente della ricetta corrisponde
    al prodotto nella fattura.
    """
    score = _calcola_similarita(nome_ingrediente, nome_prodotto_fattura)
    return score >= soglia


# ── Funzione principale ─────────────────────────────────────────────────────


async def aggiorna_ricette_da_fattura(fattura_doc: dict) -> dict:
    """
    Aggiorna gli ingredienti di tutte le ricette interessate
    dai prodotti di questa fattura.

    Per ogni prodotto della fattura:
      1. Cerca ricette con ingrediente simile
      2. Aggiorna l'ingrediente_dettaglio con i dati della merce reale
      3. Salva la mappatura per i prossimi aggiornamenti automatici

    Ritorna un report: quante ricette aggiornate, quali ingredienti matchati.
    """
    fornitore = fattura_doc.get("fornitore", "")
    num_fattura = fattura_doc.get("numero_fattura", "")
    data_fatt = fattura_doc.get("data_fattura", "")
    prodotti = fattura_doc.get("prodotti", [])

    if not prodotti:
        return {"aggiornate": 0, "match": []}

    # Carica tutte le ricette con i loro ingredienti
    ricette = await db.ricette.find(
        {}, {"_id": 0, "id": 1, "nome": 1, "ingredienti": 1, "ingredienti_dettaglio": 1}
    ).to_list(2000)

    # Carica mappature manuali già confermate
    mappature_salvate = await db.mappature_ingredienti.find(
        {}, {"_id": 0, "nome_fattura": 1, "nome_ricetta": 1, "confermata": 1}
    ).to_list(5000)
    mappa_confermata: dict[str, str] = {
        m["nome_fattura"].lower(): m["nome_ricetta"]
        for m in mappature_salvate
        if m.get("confermata", True)
    }
    mappa_confermata_inversa: dict[str, str] = {
        m["nome_ricetta"].lower(): m["nome_fattura"]
        for m in mappature_salvate
        if m.get("confermata", True)
    }

    ricette_aggiornate = 0
    match_log = []
    oggi = datetime.now(timezone.utc).strftime("%d/%m/%Y")

    for prodotto in prodotti:
        desc_fattura = (prodotto.get("descrizione") or "").strip()
        if not desc_fattura:
            continue

        desc_lower = desc_fattura.lower()
        nome_ingrediente_forzato = mappa_confermata.get(desc_lower)

        for ricetta in ricette:
            ricetta_id = ricetta.get("id", "")
            ricetta_nome = ricetta.get("nome", "")
            ingredienti_semplici = ricetta.get("ingredienti", [])  # lista stringhe
            ingredienti_dettaglio = ricetta.get("ingredienti_dettaglio", [])  # lista dict

            # Normalizza: se ingredienti_dettaglio è vuoto ma ingredienti ha dati
            if not ingredienti_dettaglio and ingredienti_semplici:
                ingredienti_dettaglio = [
                    {"nome": ing, "quantita": None, "unita_misura": ""}
                    for ing in ingredienti_semplici
                    if isinstance(ing, str) and ing.strip()
                ]

            ha_match = False

            for ing_det in ingredienti_dettaglio:
                nome_ing = ""
                if isinstance(ing_det, dict):
                    nome_ing = (ing_det.get("nome") or "").strip()
                elif isinstance(ing_det, str):
                    nome_ing = ing_det.strip()
                if not nome_ing:
                    continue

                # Verifica match: mappatura manuale o automatica
                match_trovato = False
                if (
                    nome_ingrediente_forzato
                    and nome_ingrediente_forzato.lower() == nome_ing.lower()
                ):
                    match_trovato = True
                elif not nome_ingrediente_forzato:
                    # Controlla mappatura inversa (ingrediente ricetta → prodotto fattura)
                    prodotto_mappato = mappa_confermata_inversa.get(nome_ing.lower())
                    if prodotto_mappato and prodotto_mappato.lower() == desc_lower:
                        match_trovato = True
                    else:
                        match_trovato = _match_ingrediente_prodotto(nome_ing, desc_fattura)

                if not match_trovato:
                    continue
                ha_match = True

                # NB: la provenienza (fornitore/numero_fattura/data_fattura/data_scadenza/
                # lotto) NON viene piu' scritta sull'ingrediente. Veniva sovrascritta a
                # ogni import (last-wins) e la mostrava sull'ULTIMA fattura ricevuta invece
                # che sul lotto piu' vecchio. Ora la provenienza e' DERIVATA al volo dal
                # lotto FIFO-attivo (peek_lotto_fifo_attivo): un solo sistema, single source.
                # Qui resta solo l'apprendimento del dizionario nome_fattura <-> ingrediente.
                await db.mappature_ingredienti.update_one(
                    {"nome_fattura": desc_fattura, "nome_ricetta": nome_ing},
                    {
                        "$set": {
                            "nome_fattura": desc_fattura,
                            "nome_ricetta": nome_ing,
                            "fornitore": fornitore,
                            "confermata": True,
                            "auto_rilevata": True,
                            "aggiornata_il": oggi,
                        }
                    },
                    upsert=True,
                )

                match_log.append(
                    {
                        "ricetta": ricetta_nome,
                        "ingrediente": nome_ing,
                        "prodotto_fattura": desc_fattura,
                        "fornitore": fornitore,
                    }
                )

            if ha_match:
                ricette_aggiornate += 1

    logger.info(
        f"[AggiornamentoRicette] Fattura {num_fattura} ({fornitore}): "
        f"{ricette_aggiornate} ricette aggiornate, {len(match_log)} match"
    )

    return {
        "aggiornate": ricette_aggiornate,
        "match": match_log,
        "fattura": num_fattura,
        "fornitore": fornitore,
    }


# ── Endpoint REST ───────────────────────────────────────────────────────────


@router.post("/da-fattura/{fattura_id}")
async def aggiorna_da_fattura(fattura_id: str):
    """
    Forza l'aggiornamento degli ingredienti delle ricette
    a partire da una fattura già importata.
    Utile per ri-processare una fattura manualmente.
    """
    fattura = await db.fatture.find_one({"id": fattura_id}, {"_id": 0})
    if not fattura:
        from fastapi import HTTPException

        raise HTTPException(404, "Fattura non trovata")
    result = await aggiorna_ricette_da_fattura(fattura)
    return result


@router.post("/rielabora-tutte")
async def rielabora_tutte(giorni: int = 30):
    """
    Rielabora tutte le fatture degli ultimi N giorni
    e aggiorna gli ingredienti delle ricette.
    Da usare dopo aver configurato nuove mappature manuali.
    """
    from datetime import timedelta

    da = (datetime.now(timezone.utc) - timedelta(days=giorni)).strftime("%d/%m/%Y")

    fatture = await db.fatture.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)

    totale_ricette = 0
    totale_match = 0
    for f in fatture:
        res = await aggiorna_ricette_da_fattura(f)
        totale_ricette += res.get("aggiornate", 0)
        totale_match += len(res.get("match", []))

    return {
        "fatture_processate": len(fatture),
        "ricette_aggiornate": totale_ricette,
        "match_trovati": totale_match,
    }


@router.get("/mappature")
async def get_mappature(solo_auto: bool = False):
    """
    Lista le mappature ingrediente ricetta ↔ prodotto fattura.
    Mostra anche quelle non ancora confermate manualmente.
    """
    filtro = {}
    if solo_auto:
        filtro["auto_rilevata"] = True
    docs = await db.mappature_ingredienti.find(filtro, {"_id": 0}).to_list(2000)
    return docs


@router.put("/mappature/conferma")
async def conferma_mappatura(payload: dict):
    """
    Conferma o corregge una mappatura manualmente.
    Payload: { nome_fattura, nome_ricetta, confermata: true/false }
    Dopo la conferma il sistema userà questa mappatura in futuro.
    """
    nome_f = payload.get("nome_fattura", "").strip()
    nome_r = payload.get("nome_ricetta", "").strip()
    ok = payload.get("confermata", True)

    if not nome_f or not nome_r:
        from fastapi import HTTPException

        raise HTTPException(400, "nome_fattura e nome_ricetta sono obbligatori")

    await db.mappature_ingredienti.update_one(
        {"nome_fattura": nome_f, "nome_ricetta": nome_r},
        {
            "$set": {
                "confermata": ok,
                "confermata_il": datetime.now(timezone.utc).strftime("%d/%m/%Y"),
            }
        },
        upsert=True,
    )
    return {"success": True, "mappatura": f"{nome_f} → {nome_r}", "confermata": ok}


@router.get("/ingredienti-ricette-senza-fornitore")
async def ingredienti_senza_fornitore():
    """
    Lista tutti gli ingredienti nelle ricette che NON hanno ancora
    un fornitore associato dall'ultima fattura ricevuta.
    Utile per capire quali ingredienti mancano di mappatura.
    """
    ricette = await db.ricette.find({}, {"_id": 0, "nome": 1, "ingredienti_dettaglio": 1}).to_list(
        2000
    )

    mancanti = []
    for r in ricette:
        for ing in r.get("ingredienti_dettaglio") or []:
            if isinstance(ing, dict):
                if not ing.get("fornitore"):
                    mancanti.append(
                        {
                            "ricetta": r.get("nome", ""),
                            "ingrediente": ing.get("nome", ""),
                        }
                    )
    return mancanti
