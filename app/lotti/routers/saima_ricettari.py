"""
Router per ricettari SAIMA S.p.a.
Fornisce i link ai PDF ricettari scaricabili dal sito SAIMA.
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks, Query, Depends
from pydantic import BaseModel
import httpx
import logging
import json
import re
import unicodedata
import uuid
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional
_LOG_INIT = logging.getLogger("uvicorn.error")
from bs4 import BeautifulSoup
from app.lotti.db import database as db
from datetime import datetime, timezone
from pymongo import UpdateOne
from app.lotti.auth import require_admin

router = APIRouter(prefix="/saima/ricettari", tags=["saima"])

# Ricettari SAIMA — dati statici + link PDF
# Sezione Ricorrenze (6 ricettari)
RICETTARI_RICORRENZE = [
    {
        "id": "carnevale",
        "nome": "Carnevale",
        "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2023/01/Ricettario-Carnevale.pdf",
        "url_pagina": "https://www.saimaspa.com/default-item/carnevale-ricettario/",
        "sezione": "Ricorrenze",
    },
    {
        "id": "prima-colazione",
        "nome": "Prima Colazione",
        "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2022/10/Ricettario-prima-colazione.pdf",
        "url_pagina": "https://www.saimaspa.com/default-item/prima-colazione-ricettario/",
        "sezione": "Ricorrenze",
    },
    {
        "id": "dolci-easy",
        "nome": "Dolci Easy",
        "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2022/10/ricettario-dolci-easy.pdf",
        "url_pagina": "https://www.saimaspa.com/default-item/dolci-easy-ricettario/",
        "sezione": "Ricorrenze",
    },
    {
        "id": "snack-take-away",
        "nome": "Snack Take Away",
        "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2022/10/Ricettario-snack-take-away.pdf",
        "url_pagina": "https://www.saimaspa.com/default-item/snack-take-away-ricettario/",
        "sezione": "Ricorrenze",
    },
    {
        "id": "torroni",
        "nome": "Torroni",
        "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2022/09/Ricettario-Torroni.pdf",
        "url_pagina": "https://www.saimaspa.com/default-item/torroni-ricettario/",
        "sezione": "Ricorrenze",
    },
    {
        "id": "halloween",
        "nome": "Halloween",
        "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2023/09/Ricettario-halloween_2023.pdf",
        "url_pagina": "https://www.saimaspa.com/default-item/halloween-ricettario/",
        "sezione": "Ricorrenze",
    },
]

# Sezione Applicazioni Prodotto (19 ricettari)
RICETTARI_APPLICAZIONI = [
    {
        "id": "cometa-ricettario-natale",
        "nome": "Cometa Ricettario Natale",
        "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2024/11/Cometa-sestino-SAIMA.pdf",
        "url_pagina": "https://www.saimaspa.com/default-item/cometa-ricettario-natale/",
        "sezione": "Applicazioni Prodotto",
    },
    {
        "id": "ricettario-jolly-zelandia",
        "nome": "Ricettario Jolly Zelandia",
        "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2024/11/Jolly-Saima.pdf",
        "url_pagina": "https://www.saimaspa.com/default-item/ricettario-jolly-zelandia/",
        "sezione": "Applicazioni Prodotto",
    },
    {
        "id": "ricettario-bs-komplet",
        "nome": "Ricettario b+s Komplet",
        "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2024/11/ricettario-bs.pdf",
        "url_pagina": "https://www.saimaspa.com/default-item/ricettario-bs-komplet/",
        "sezione": "Applicazioni Prodotto",
    },
    {
        "id": "waldkorn-ricettario",
        "nome": "Waldkorn",
        "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2024/11/Ricettario-Waldkorn.pdf",
        "url_pagina": "https://www.saimaspa.com/default-item/waldkorn-ricettario/",
        "sezione": "Applicazioni Prodotto",
    },
    {
        "id": "pan-della-vigna-ricettario",
        "nome": "Pan della Vigna",
        "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2023/09/Ricettario-Pan-della-Vigna.pdf",
        "url_pagina": "https://www.saimaspa.com/default-item/pan-della-vigna-ricettario/",
        "sezione": "Applicazioni Prodotto",
    },
    {
        "id": "croissant-ricettario",
        "nome": "Croissant",
        "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2023/07/Ricettario-Croissant.pdf",
        "url_pagina": "https://www.saimaspa.com/default-item/croissant-ricettario/",
        "sezione": "Applicazioni Prodotto",
    },
    {
        "id": "pancampagna-rustico-ricettario",
        "nome": "Pancampagna Rustico",
        "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2023/06/Ricettario-pancampagna.pdf",
        "url_pagina": "https://www.saimaspa.com/default-item/pancampagna-rustico-ricettario/",
        "sezione": "Applicazioni Prodotto",
    },
    {
        "id": "rex-bucheron-ricettario",
        "nome": "Rex Bucheron",
        "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2023/05/Ricettario-Bucheron.pdf",
        "url_pagina": "https://www.saimaspa.com/default-item/rex-bucheron-ricettario/",
        "sezione": "Applicazioni Prodotto",
    },
    {
        "id": "craft-malz-ricettario-2",
        "nome": "Craft Malz",
        "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2023/05/Ricettario-Craft-Malz.pdf",
        "url_pagina": "https://www.saimaspa.com/default-item/craft-malz-ricettario-2/",
        "sezione": "Applicazioni Prodotto",
    },
    {
        "id": "soft-break-ricettario",
        "nome": "Soft Break",
        "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2023/02/Ricettario-Soft-Break.pdf",
        "url_pagina": "https://www.saimaspa.com/default-item/soft-break-ricettario/",
        "sezione": "Applicazioni Prodotto",
    },
    {
        "id": "cake-nature-ricettario",
        "nome": "Cake Nature",
        "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2023/02/Ricettario-Cake-Nature-Braims-mod.pdf",
        "url_pagina": "https://www.saimaspa.com/default-item/cake-nature-ricettario/",
        "sezione": "Applicazioni Prodotto",
    },
    {
        "id": "chocospalmabili-bonfritto-e-forno",
        "nome": "Bonfritto e Forno (Choco Spalmabili)",
        "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2022/12/Ricettario-Bonfritto-2.pdf",
        "url_pagina": "https://www.saimaspa.com/default-item/chocospalmabili-bonfritto-e-forno/",
        "sezione": "Applicazioni Prodotto",
    },
    {
        "id": "5-ricette-in-5-minuti-ricettario",
        "nome": "5 Ricette in 5 Minuti",
        "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2022/10/ricettario-5-ricette-in-5-minuti.pdf",
        "url_pagina": "https://www.saimaspa.com/default-item/5-ricette-in-5-minuti-ricettario/",
        "sezione": "Applicazioni Prodotto",
    },
    {
        "id": "choquit-ricettario",
        "nome": "Choquit",
        "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2022/10/Ricettario-Choquit.pdf",
        "url_pagina": "https://www.saimaspa.com/default-item/choquit-ricettario/",
        "sezione": "Applicazioni Prodotto",
    },
    {
        "id": "pasticceria-mignon-ricettario",
        "nome": "Pasticceria Mignon",
        "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2022/10/Ricettario-pasticceria-mignon-debic.pdf",
        "url_pagina": "https://www.saimaspa.com/default-item/pasticceria-mignon-ricettario/",
        "sezione": "Applicazioni Prodotto",
    },
    {
        "id": "creme-con-cioccolato-callebaut-ricettario",
        "nome": "Creme con Cioccolato Callebaut",
        "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2022/08/Ricettario-creme-con-cioccolato-callebaut.pdf",
        "url_pagina": "https://www.saimaspa.com/default-item/creme-con-cioccolato-callebaut-ricettario/",
        "sezione": "Applicazioni Prodotto",
    },
    {
        "id": "mix-savoiardo-ricettario",
        "nome": "Mix Savoiardo",
        "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2022/08/Ricettario-italmill-mix-savoiardo.pdf",
        "url_pagina": "https://www.saimaspa.com/default-item/mix-savoiardo-ricettario/",
        "sezione": "Applicazioni Prodotto",
    },
    {
        "id": "scrocchiarella-ricettario",
        "nome": "Scrocchiarella",
        "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2022/10/Ricettario-Scrocchiarella-new.pdf",
        "url_pagina": "https://www.saimaspa.com/default-item/scrocchiarella-ricettario/",
        "sezione": "Applicazioni Prodotto",
    },
    {
        "id": "mix-muffin-ricettario",
        "nome": "Mix Muffin",
        "url_pdf": "https://www.saimaspa.com/wp-content/uploads/2022/10/Ricettario-Mix-muffin.pdf",
        "url_pagina": "https://www.saimaspa.com/default-item/mix-muffin-ricettario/",
        "sezione": "Applicazioni Prodotto",
    },
]

# La pagina ufficiale corrente espone 19 applicazioni. I sei vecchi link
# "Ricorrenze" sono mantenuti sopra come memoria di migrazione ma non vengono
# più mostrati: alcuni restituiscono 404 e confondevano l'operatore.
RICETTARI_STATICI = RICETTARI_APPLICAZIONI
ALL_RICETTARI_STATICI = RICETTARI_STATICI

_BUNDLE_RICETTE = Path(__file__).resolve().parent.parent / "data" / "ricette_saima.json"


def _bundle_saima() -> dict:
    if not _BUNDLE_RICETTE.exists():
        return {"meta": {}, "ricette": []}
    try:
        return json.loads(_BUNDLE_RICETTE.read_text(encoding="utf-8"))
    except Exception:
        _LOG_INIT.exception("[saima_ricettari] bundle ricette non leggibile")
        return {"meta": {}, "ricette": []}


async def _importa_bundle_saima() -> dict:
    """Upsert idempotente: crea le ricette mancanti e preserva le modifiche utente."""
    payload = _bundle_saima()
    ricette = payload.get("ricette") or []
    if not ricette:
        return {"totale_bundle": 0, "inserite": 0, "gia_presenti": 0}
    ids = [item["id"] for item in ricette]
    esistenti = set(await db.ricette.distinct("id", {"id": {"$in": ids}}))
    now = datetime.now(timezone.utc).isoformat()
    ops = []
    for item in ricette:
        source_fields = {
            "fonte_archivio": item.get("fonte_archivio"),
            "ricettario_saima_id": item.get("ricettario_saima_id"),
            "ricettario_saima_nome": item.get("ricettario_saima_nome"),
            "url_pdf": item.get("url_pdf"),
            "url_pagina": item.get("url_pagina"),
            "pagina_fonte": item.get("pagina_fonte"),
            "sha256_fonte": item.get("sha256_fonte"),
        }
        insert_only = {key: value for key, value in item.items() if key not in source_fields}
        # Il bundle e un riferimento professionale consultabile: non diventa
        # automaticamente una card di produzione. L'utente lo attiva salvando
        # la ricetta dal form «Usa in ricetta».
        insert_only.setdefault("visibile_tablet", False)
        insert_only.setdefault("ricetta_operativa", False)
        ops.append(
            UpdateOne(
                {"id": item["id"]},
                {
                    "$setOnInsert": {**insert_only, "created_at": now},
                    "$set": {**source_fields, "updated_source_at": now},
                },
                upsert=True,
            )
        )
    if ops:
        await db.ricette.bulk_write(ops, ordered=False)
    return {
        "totale_bundle": len(ricette),
        "inserite": len(set(ids) - esistenti),
        "gia_presenti": len(esistenti),
        "ricettari": payload.get("meta", {}).get("totale_ricettari", 0),
    }

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "it-IT,it;q=0.9",
}


@router.get("")
async def get_ricettari():
    """Restituisce i soli ricettari SAIMA con link PDF e numero ricette estratte."""
    # Prima controlla se ci sono ricettari extra in DB
    db_extra = await db.saima_ricettari.find({}, {"_id": 0}).to_list(100)

    # Prende solo quelli non già presenti nella lista statica
    ids_statici = {r["id"] for r in ALL_RICETTARI_STATICI}
    nuovi = [extra for extra in db_extra if extra.get("id") not in ids_statici]

    counts = {}
    for item in (_bundle_saima().get("ricette") or []):
        book_id = item.get("ricettario_saima_id")
        counts[book_id] = counts.get(book_id, 0) + 1
    return [
        {**item, "ricette_importabili": counts.get(item.get("id"), 0)}
        for item in (list(ALL_RICETTARI_STATICI) + nuovi)
    ]


@router.post("/importa-ricette")
async def importa_ricette_saima(_admin=Depends(require_admin)):
    """Inserisce idempotentemente le ricette SAIMA nel ricettario Ceraldi unico."""
    return {"success": True, **(await _importa_bundle_saima())}


def _norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(ch for ch in value if not unicodedata.combining(ch)).lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value).split())


_STOP = {"di", "del", "della", "al", "alla", "con", "per", "in", "e", "o", "fresco", "classico"}


def _tokens(value: str) -> set[str]:
    return {x for x in _norm(value).split() if len(x) > 2 and x not in _STOP}


def _famiglia(value: str) -> str:
    text = _norm(value)
    rules = (
        ("acqua", ("acqua",)),
        ("lieviti", ("lievito", "levain", "starter")),
        ("grassi", ("burro", "margarina", "melange", "grasso", "strutto")),
        ("aromi", ("aroma", "emulsione", "pasta mandarino", "pasta arancia", "pasta limone", "vaniglia")),
        ("farine", ("farina", "semola", "amido", "fecola")),
        ("zuccheri", ("zucchero", "destrosio", "saccarosio", "glucosio", "miele")),
        ("cioccolato", ("cioccolato", "copertura", "cacao")),
        ("latticini", ("latte", "panna", "ricotta", "mascarpone")),
        ("uova", ("uova", "uovo", "tuorlo", "albume")),
        ("frutta", ("amarena", "mandarino", "arancia", "limone", "fragola", "mango", "frutta")),
        ("creme", ("crema", "farcitura", "variegato")),
    )
    for family, words in rules:
        if any(word in text for word in words):
            return family
    return "specifico"


def _similarita(a: str, b: str) -> float:
    na, nb = _norm(a), _norm(b)
    ta, tb = _tokens(a), _tokens(b)
    overlap = len(ta & tb) / max(1, len(ta | tb))
    return round(100 * (0.62 * SequenceMatcher(None, na, nb).ratio() + 0.38 * overlap), 1)


def _quantita_richiesta(ingredient: dict, factor: float) -> dict:
    return {
        "valore": round(float(ingredient.get("quantita") or 0) * factor, 3),
        "unita": ingredient.get("unita_misura") or "",
    }


def _quantita_base(value: float, unit: str) -> tuple[float, str]:
    normalized = str(unit or "").strip().lower().replace(".", "")
    number = float(value or 0)
    if normalized in {"kg"}:
        return number * 1000, "g"
    if normalized in {"g", "gr", "mg"}:
        return (number / 1000 if normalized == "mg" else number), "g"
    if normalized in {"l", "lt"}:
        return number * 1000, "ml"
    if normalized in {"ml", "cl"}:
        return (number * 10 if normalized == "cl" else number), "ml"
    if normalized in {"pz", "pze", "nr", "n", "conf", "cf"}:
        return number, "pz"
    return number, normalized


class VerificaDisponibilitaPayload(BaseModel):
    pezzi: Optional[float] = None


@router.post("/ricette/{ricetta_id}/verifica-disponibilita")
async def verifica_disponibilita_ricetta(ricetta_id: str, body: VerificaDisponibilitaPayload):
    """Confronta la ricetta con giacenze da fatture e propone sostituti prudenti.

    Le alternative non vengono mai applicate automaticamente: sono suggerimenti
    della stessa famiglia merceologica e richiedono conferma dell'operatore.
    """
    ricetta = await db.ricette.find_one({"id": ricetta_id}, {"_id": 0})
    if not ricetta:
        raise HTTPException(404, "Ricetta non trovata")
    base = float(ricetta.get("porzioni") or ricetta.get("pezzi_ricetta_base") or 0)
    pezzi = float(body.pezzi or base or 0)
    factor = (pezzi / base) if base > 0 and pezzi > 0 else 1.0

    lotti = await db.lotti_fornitori.find(
        {"esaurito": {"$ne": True}, "quantita_disponibile": {"$gt": 0}},
        {"_id": 0, "id": 1, "prodotto_nome": 1, "prodotto_nome_norm": 1,
         "quantita_disponibile": 1, "unita_misura": 1, "fornitore": 1,
         "fattura_ref": 1, "data_fattura": 1},
    ).to_list(12000)

    # Una sola voce per nome, sommando i residui reali delle fatture.
    disponibili = {}
    for lotto in lotti:
        name = lotto.get("prodotto_nome") or lotto.get("prodotto_nome_norm") or ""
        key = _norm(name)
        if not key:
            continue
        value, base_unit = _quantita_base(lotto.get("quantita_disponibile") or 0, lotto.get("unita_misura") or "")
        if key not in disponibili:
            disponibili[key] = {**lotto, "prodotto_nome": name, "quantita_disponibile": 0.0, "quantita_base": 0.0, "unita_base": base_unit, "fatture": []}
        if disponibili[key].get("unita_base") == base_unit:
            disponibili[key]["quantita_base"] += value
            disponibili[key]["quantita_disponibile"] += float(lotto.get("quantita_disponibile") or 0)
        ref = lotto.get("fattura_ref")
        if ref and ref not in disponibili[key]["fatture"]:
            disponibili[key]["fatture"].append(ref)

    righe = []
    for ingredient in ricetta.get("ingredienti_dettaglio") or []:
        name = (ingredient.get("nome") or "").strip()
        if not name:
            continue
        family = _famiglia(name)
        required = _quantita_richiesta(ingredient, factor)
        if family == "acqua":
            righe.append({
                "ingrediente": name, "stato": "disponibile", "famiglia": family,
                "richiesta": required, "prodotto": {"nome": "Acqua di laboratorio", "fonte": "disponibilità interna"},
                "alternative": [],
            })
            continue

        scored = sorted(
            ((_similarita(name, item["prodotto_nome"]), item) for item in disponibili.values()),
            key=lambda row: row[0], reverse=True,
        )
        exact = next((item for score, item in scored if score >= 66 and (_tokens(name) & _tokens(item["prodotto_nome"]))), None)
        required_base, required_unit = _quantita_base(required["valore"], required["unita"])
        enough = bool(exact) and (
            required_base <= 0
            or not required_unit
            or (
                required_unit == exact.get("unita_base")
                and float(exact.get("quantita_base") or 0) >= required_base
            )
        )
        if exact and enough:
            righe.append({
                "ingrediente": name, "stato": "disponibile", "famiglia": family, "richiesta": required,
                "prodotto": {
                    "id": exact.get("id"), "nome": exact.get("prodotto_nome"),
                    "quantita_disponibile": round(exact.get("quantita_disponibile", 0), 3),
                    "unita": exact.get("unita_misura", ""), "fornitore": exact.get("fornitore", ""),
                    "fatture": exact.get("fatture", [])[:5],
                },
                "alternative": [],
            })
            continue

        if exact and not enough:
            righe.append({
                "ingrediente": name, "stato": "da_acquistare", "famiglia": family, "richiesta": required,
                "prodotto": {
                    "id": exact.get("id"), "nome": exact.get("prodotto_nome"),
                    "quantita_disponibile": round(exact.get("quantita_base", 0), 3),
                    "unita": exact.get("unita_base", ""), "fornitore": exact.get("fornitore", ""),
                    "fatture": exact.get("fatture", [])[:5], "insufficiente": True,
                },
                "motivo": "Giacenza insufficiente per la quantità richiesta.",
                "mancante": {
                    "valore": round(max(0, required_base - float(exact.get("quantita_base") or 0)), 3),
                    "unita": required_unit,
                },
                "alternative": [],
            })
            continue

        alternatives = []
        if family != "specifico":
            for score, item in scored:
                if _famiglia(item["prodotto_nome"]) != family:
                    continue
                if any(a["nome"] == item["prodotto_nome"] for a in alternatives):
                    continue
                alternatives.append({
                    "id": item.get("id"), "nome": item.get("prodotto_nome"),
                    "quantita_disponibile": round(item.get("quantita_disponibile", 0), 3),
                    "unita": item.get("unita_misura", ""), "fornitore": item.get("fornitore", ""),
                    "compatibilita": score,
                    "motivo": f"Stessa famiglia: {family}. Verificare resa e gusto prima dell'uso.",
                })
                if len(alternatives) >= 3:
                    break
        righe.append({
            "ingrediente": name,
            "stato": "sostituibile" if alternatives else "da_acquistare",
            "famiglia": family,
            "richiesta": required,
            "prodotto": None,
            "alternative": alternatives,
        })

    da_acquistare = [row for row in righe if row["stato"] == "da_acquistare"]
    sostituibili = [row for row in righe if row["stato"] == "sostituibile"]
    return {
        "ricetta_id": ricetta_id,
        "ricetta_nome": ricetta.get("nome"),
        "pezzi_richiesti": pezzi or None,
        "resa_base": base or None,
        "resa_da_impostare": base <= 0,
        "moltiplicatore": round(factor, 4),
        "realizzabile_subito": not da_acquistare and not sostituibili,
        "realizzabile_con_sostituzioni": not da_acquistare and bool(sostituibili),
        "righe": righe,
        "totali": {
            "disponibili": len([row for row in righe if row["stato"] == "disponibile"]),
            "sostituibili": len(sostituibili),
            "da_acquistare": len(da_acquistare),
        },
    }


class ListaSpesaPayload(BaseModel):
    pezzi: Optional[float] = None


@router.post("/ricette/{ricetta_id}/aggiungi-mancanti-carrello")
async def aggiungi_mancanti_carrello(
    ricetta_id: str,
    body: ListaSpesaPayload,
    _admin=Depends(require_admin),
):
    verifica = await verifica_disponibilita_ricetta(
        ricetta_id, VerificaDisponibilitaPayload(pezzi=body.pezzi)
    )
    mancanti = [row for row in verifica["righe"] if row["stato"] == "da_acquistare"]
    doc = await db.carrello_sospesi.find_one({"_id": "default"}, {"_id": 0}) or {}
    current = list(doc.get("righe") or [])
    existing = {_norm(item.get("nome")) for item in current}
    added = []
    for row in mancanti:
        if _norm(row["ingrediente"]) in existing:
            continue
        da_comprare = row.get("mancante") or row["richiesta"]
        item = {
            "id": f"ricetta-saima-{uuid.uuid4()}",
            "nome": row["ingrediente"],
            "quantita": max(1, da_comprare["valore"] or 1),
            "unita": da_comprare["unita"] or "conf",
            "prezzo": 0,
            "fornitore": "SAIMA",
            "fonte": "ricetta_saima",
            "ricetta_id": ricetta_id,
            "nota": "Ingrediente mancante rilevato dalla verifica della ricetta; prezzo da confermare.",
        }
        current.append(item)
        existing.add(_norm(row["ingrediente"]))
        added.append(item)
    await db.carrello_sospesi.update_one(
        {"_id": "default"},
        {"$set": {"righe": current, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    return {"success": True, "aggiunti": len(added), "gia_presenti": len(mancanti) - len(added), "righe": added}


@router.get("/pdf-proxy")
async def proxy_pdf(url: str = Query(..., description="URL del PDF da proxare")):
    """
    Proxy backend per visualizzare PDF SAIMA inline nell'app.
    Scarica il PDF da SAIMA e lo restituisce con gli header corretti per l'embedding.
    """
    import urllib.parse

    # Whitelist: domini autorizzati
    DOMINI_AUTORIZZATI = {
        "saimaspa.com",
        "www.saimaspa.com",
        "mepaalimentari.com",
        "www.mepaalimentari.com",
    }
    parsed = urllib.parse.urlparse(url)
    if parsed.netloc not in DOMINI_AUTORIZZATI:
        raise HTTPException(status_code=403, detail=f"URL non autorizzato: {parsed.netloc}")

    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            r = await client.get(url, headers=HEADERS)
            if r.status_code != 200:
                raise HTTPException(
                    status_code=502, detail=f"PDF non disponibile: HTTP {r.status_code}"
                )
            content_type = r.headers.get("content-type", "application/pdf")
            if "html" in content_type.lower():
                raise HTTPException(
                    status_code=502, detail="Il server ha restituito HTML invece del PDF"
                )
            from fastapi.responses import Response

            return Response(
                content=r.content,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": "inline",
                    "Cache-Control": "public, max-age=3600",
                },
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
            "https://www.saimaspa.com/applicazioni-prodotto/",
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
                            if (
                                ".pdf" in a["href"].lower()
                                and "Privacy" not in a.get_text()
                                and "Cookie" not in a.get_text()
                            ):
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
                        _LOG_INIT.debug("[saima_ricettari] errore non bloccante ignorato")
        except Exception as e:
            print(f"[SAIMA Ricettari] Errore aggiornamento: {e}")

    background_tasks.add_task(esegui)
    return {"message": "Aggiornamento ricettari avviato in background"}


class NuovoRicettario(BaseModel):
    nome: str
    url_pdf: str
    sezione: str = "Altro"
    fornitore: str = ""


@router.post("/aggiungi")
async def aggiungi_ricettario(body: NuovoRicettario):
    """Aggiunge un ricettario SAIMA custom tramite URL PDF diretto."""
    import re, urllib.parse

    # Genera ID univoco dal nome
    rid = re.sub(r"[^a-z0-9]+", "-", body.nome.lower()).strip("-")
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
