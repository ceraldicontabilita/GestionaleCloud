"""
Router Materie Prime — fonte unica: collection lotti_fornitori
(la vecchia collection materie_prime è stata unificata il 03/07/2026,
vedi POST /migra-in-lotti-fornitori).

GET  /api/materie-prime/da-fatture            — prodotti per fornitore (pagina Materie Prime)
POST /api/materie-prime/migra-in-lotti-fornitori — migrazione una tantum
POST /api/materie-prime/rebuild-lotti-fornitori  — ricostruzione da fatture (manuale)
POST /api/materie-prime/normalizza-unita         — bonifica unità (manuale)
"""

from fastapi import APIRouter
from datetime import datetime, timezone, timedelta
import re, uuid

from app.lotti.db import database as db

router = APIRouter(prefix="/materie-prime", tags=["Materie Prime"])


_ALLERGENI_KW = {
    "Latte e derivati": [
        "latte",
        "lattosio",
        "caseina",
        "panna",
        "burro",
        "formaggio",
        "mozzarella",
        "ricotta",
        "yogurt",
        "siero di latte",
        "whey",
    ],
    "Cereali/glutine": [
        "farina",
        "semola",
        "grano",
        "frumento",
        "orzo",
        "segale",
        "avena",
        "farro",
        "kamut",
        "glutine",
        "pasta ",
        "pizza",
        "brioche",
        "croissant",
        "pangrattato",
        "biscotto",
        "torta",
    ],
    "Uova": ["uova", "tuorlo", "albume", "ovoprodotti", "maionese"],
    "Soia": ["soia", "soy", "lecitina di soia"],
    "Frutta a guscio": [
        "noci ",
        "nocciola",
        "nocciole",
        "mandorle",
        "pistacchio",
        "pinoli",
        "anacardi",
        "pecan",
        "macadamia",
    ],
    "Arachidi": ["arachidi", "arachide"],
    "Sedano": ["sedano"],
    "Senape": ["senape", "mostarda"],
    "Sesamo": ["sesamo", "tahini"],
    "Pesce": ["acciughe", "alici", "tonno", "salmone", "baccalà"],
    "Crostacei": ["gamberi", "aragoste", "granchi", "scampi"],
    "Molluschi": ["cozze", "vongole", "polpo", "calamari", "seppie"],
    "Lupino": ["lupino", "lupini"],
    "Solfiti": ["solfiti", "anidride solforosa"],
}

_FORNITORI_SCONOSCIUTI = {
    "",
    "sconosciuto",
    "sconosciuta",
    "unknown",
    "n/d",
    "nd",
    "non disponibile",
    "fornitore sconosciuto",
}

# Pattern per escludere righe "non-materie-prime" dalle fatture (spese accessorie, bolli, etc.)
_NON_MATERIA_PRIMA_PATTERNS = [
    r"\bspes[ae]\b",  # "spese trasporto", "spese cancelleria"
    r"\btrasport",  # "trasporto", "spese di trasporto"
    r"\bcancelleri",  # "cancelleria"
    r"\bimballaggi?\b",  # "imballaggi"
    r"\bbollo\b",  # "bollo"
    r"\bdiritt[io]\b",  # "diritto fisso"
    r"\bcontribut[io]\b",  # "contributi"
    r"\bsovrappr(e|i)zz",  # "sovrapprezzo"
    r"\bsconto\b",  # righe di sconto pure
    r"\babbuoni\b",  # "abbuoni"
    r"\barrotondamen",  # "arrotondamento"
    r"^\s*ritenut",  # "ritenuta"
    r"^\s*iva\s",  # righe IVA
    r"\binteressi\b",  # "interessi"
]
_NON_MATERIA_RE = re.compile("|".join(_NON_MATERIA_PRIMA_PATTERNS), re.IGNORECASE)


def _is_spesa_accessoria(descrizione: str) -> bool:
    """Restituisce True se la descrizione è una voce di spesa/accessorio, NON una materia prima."""
    desc = (descrizione or "").strip()
    if not desc:
        return True
    return bool(_NON_MATERIA_RE.search(desc))


def _norm_nome(v: str) -> str:
    v = (v or "").strip().strip('"').strip("'").lower()
    return re.sub(r"\s+", " ", v)


def _is_sconosciuto(v: str) -> bool:
    return _norm_nome(v) in _FORNITORI_SCONOSCIUTI


def _rileva(nome: str) -> str:
    nl = (nome or "").lower()
    trovati = []
    for allergene, kws in _ALLERGENI_KW.items():
        if any(kw in nl for kw in kws):
            trovati.append(allergene)
    return ("Contiene: " + ", ".join(trovati)) if trovati else "non contiene allergeni"


async def _upsert_fornitore(nome: str, piva: str = ""):
    nome = (nome or "").strip().strip('"').strip("'").strip()
    if not nome or _is_sconosciuto(nome):
        return
    nome_norm = _norm_nome(nome)
    existing = await db.fornitori.find_one({"nome_norm": nome_norm})
    if not existing:
        existing = await db.fornitori.find_one(
            {"nome": {"$regex": f"^{re.escape(nome)}$", "$options": "i"}}
        )
    filtro = (
        {"id": existing.get("id")} if existing and existing.get("id") else {"nome_norm": nome_norm}
    )
    set_doc = {
        "nome": nome,
        "nome_norm": nome_norm,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if piva:
        set_doc["piva"] = piva
    await db.fornitori.update_one(
        filtro,
        {
            "$set": set_doc,
            "$setOnInsert": {
                "id": str(uuid.uuid4()),
                "escluso": False,
                "in_attesa": False,
                "first_seen": datetime.now(timezone.utc).isoformat(),
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        },
        upsert=True,
    )


async def _correggi_fornitori_sconosciuti() -> int:
    """Backfill automatico: se un lotto/prodotto ha fornitore vuoto o Sconosciuto,
    recupera il fornitore dalla fattura collegata tramite numero fattura e prodotto.
    """
    query = {
        "$or": [
            {"fornitore": {"$exists": False}},
            {"fornitore": None},
            {"fornitore": ""},
            {
                "fornitore": {
                    "$regex": r"^\s*(sconosciuto|sconosciuta|unknown|n/d|nd|non disponibile|fornitore sconosciuto)\s*$",
                    "$options": "i",
                }
            },
        ]
    }
    items = await db.lotti_fornitori.find(query, {"_id": 0}).to_list(5000)
    corretti = 0
    for item in items:
        fattura_ref = (item.get("fattura_ref") or item.get("numero_fattura") or "").strip()
        prodotto = (item.get("prodotto_nome") or item.get("materia_prima") or "").strip()
        data_fattura = (item.get("data_fattura") or "").strip()
        fattura = None
        criteri = []
        if fattura_ref:
            criteri.append({"numero_fattura": fattura_ref})
        if fattura_ref and prodotto:
            criteri.append(
                {
                    "numero_fattura": fattura_ref,
                    "prodotti.descrizione": {"$regex": re.escape(prodotto[:40]), "$options": "i"},
                }
            )
        if data_fattura and prodotto:
            criteri.append(
                {
                    "data_fattura": data_fattura,
                    "prodotti.descrizione": {"$regex": re.escape(prodotto[:40]), "$options": "i"},
                }
            )
        if criteri:
            fattura = await db.fatture.find_one({"$or": criteri}, {"_id": 0})
        if not fattura:
            continue
        fornitore = (fattura.get("fornitore") or "").strip()
        if not fornitore or _is_sconosciuto(fornitore):
            continue
        update = {
            "fornitore": fornitore,
            "fornitore_norm": _norm_nome(fornitore),
            "fornitore_corretto_auto": True,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if item.get("id"):
            await db.lotti_fornitori.update_one({"id": item["id"]}, {"$set": update})
        else:
            filtro = {"fattura_ref": fattura_ref, "prodotto_nome": prodotto}
            await db.lotti_fornitori.update_many(filtro, {"$set": update})
        await _upsert_fornitore(fornitore, fattura.get("piva", ""))
        corretti += 1
    return corretti


@router.get("/da-fatture")
async def get_materie_prime_da_fatture(mesi: int = 12):
    """Raggruppa i prodotti delle fatture per fornitore negli ultimi N mesi."""
    await _correggi_fornitori_sconosciuti()

    esclusi_docs = await db.fornitori.find(
        {"escluso": True}, {"nome": 1, "nome_norm": 1, "_id": 0}
    ).to_list(500)
    esclusi = {f.get("nome_norm") or _norm_nome(f.get("nome", "")) for f in esclusi_docs}
    # data_fattura in lotti_fornitori è in formato misto (dd/mm/yyyy e ISO):
    # il filtro "ultimi N mesi" va fatto su date vere, non con $gte tra stringhe
    from app.lotti.routers.utils import parse_data_flessibile
    data_limite = (datetime.now() - timedelta(days=mesi * 30)).date()
    items = (
        await db.lotti_fornitori.find(
            {"solo_magazzino": {"$ne": True}}, {"_id": 0}  # solo_magazzino: fuori da Materie Prime
        )
        .sort([("fornitore", 1), ("data_fattura", -1)])
        .to_list(10000)
    )
    if mesi < 999:
        items = [i for i in items
                 if (d := parse_data_flessibile(i.get("data_fattura"))) and d >= data_limite]

    gruppi = {}
    for item in items:
        az = (item.get("fornitore") or "").strip()
        if not az or _is_sconosciuto(az):
            continue
        if (item.get("fornitore_norm") or _norm_nome(az)) in esclusi:
            continue
        # Filtra voci accessorie (spese trasporto/cancelleria, bolli, ecc.)
        if _is_spesa_accessoria(item.get("prodotto_nome", "")):
            continue
        if az not in gruppi:
            gruppi[az] = {"fornitore": az, "totale_prodotti": 0, "prodotti": []}
        gruppi[az]["totale_prodotti"] += 1
        gruppi[az]["prodotti"].append(
            {
                "descrizione": item.get("prodotto_nome", ""),
                "data_fattura": item.get("data_fattura", ""),
                "numero_fattura": item.get("fattura_ref", ""),
                "allergeni": item.get("allergeni_testo", ""),
                "quantita": item.get("quantita_disponibile", ""),
                "unita": item.get("unita_misura", ""),
                "unita_misura": item.get("unita_misura", ""),
                "prezzo": item.get("prezzo_unitario", 0),
            }
        )
    return sorted(gruppi.values(), key=lambda g: g["fornitore"])


@router.post("/migra-in-lotti-fornitori")
async def migra_materie_prime_in_lotti_fornitori(elimina_dopo: bool = False):
    """MIGRAZIONE UNA TANTUM (unificazione 03/07/2026): copia i documenti
    storici della vecchia collection `materie_prime` dentro `lotti_fornitori`
    (fonte unica delle materie prime). Idempotente: salta i doc già presenti
    (stessa chiave fattura+prodotto+fornitore). Con elimina_dopo=True svuota
    la vecchia collection al termine. Dopo la migrazione la collection
    materie_prime non viene più scritta da nessun codice."""
    esistenti = set()
    async for lf in db.lotti_fornitori.find(
        {}, {"_id": 0, "fattura_ref": 1, "prodotto_nome": 1, "fornitore": 1}
    ):
        esistenti.add((
            lf.get("fattura_ref", ""),
            (lf.get("prodotto_nome") or "").strip().lower(),
            (lf.get("fornitore") or "").strip().lower(),
        ))
    migrati = 0
    gia_presenti = 0
    async for m in db.materie_prime.find({}, {"_id": 0}):
        nome = (m.get("materia_prima") or "").strip()
        fornitore = (m.get("azienda") or "").strip()
        if not nome:
            continue
        key = (m.get("numero_fattura", ""), nome.lower(), fornitore.lower())
        if key in esistenti:
            gia_presenti += 1
            continue
        created = m.get("created_at")
        if hasattr(created, "isoformat"):
            created = created.isoformat()
        await db.lotti_fornitori.insert_one({
            "id": m.get("id") or str(uuid.uuid4()),
            "fornitore": fornitore,
            "fornitore_norm": _norm_nome(fornitore),
            "piva": "",
            "fattura_ref": m.get("numero_fattura", ""),
            "data_fattura": m.get("data_fattura", ""),
            "prodotto_nome": nome,
            "descrizione_completa": m.get("descrizione_completa") or nome,
            "quantita_disponibile": 0,
            "unita_misura": "",
            "prezzo_unitario": 0,
            "allergeni_testo": m.get("allergeni") or _rileva(nome),
            "allergeni_lista": m.get("allergeni_lista") or [],
            "migrato_da_materie_prime": True,
            "created_at": created or datetime.now(timezone.utc).isoformat(),
        })
        esistenti.add(key)
        migrati += 1
    out = {"ok": True, "migrati": migrati, "gia_presenti": gia_presenti}
    if elimina_dopo:
        res = await db.materie_prime.delete_many({})
        out["eliminati_da_materie_prime"] = res.deleted_count
    return out


@router.post("/rebuild-lotti-fornitori")
async def rebuild_lotti_fornitori_da_fatture(solo_nuove: bool = True):
    """Ricostruisce la collezione `lotti_fornitori` dalle fatture.
    - solo_nuove=True (default): aggiunge solo le righe fattura non ancora presenti
    - solo_nuove=False: cancella tutto e ripopola (full rebuild)
    Esclude automaticamente righe accessorie (spese, bolli, trasporti, ecc.).
    Viene chiamato anche dopo ogni sync Gestionale.
    """
    if not solo_nuove:
        await db.lotti_fornitori.delete_many({})

    # Carica fatture
    fatture = await db.fatture.find(
        {},
        {
            "_id": 0,
            "id": 1,
            "fornitore": 1,
            "piva": 1,
            "data_fattura": 1,
            "numero_fattura": 1,
            "prodotti": 1,
        },
    ).to_list(5000)

    # Set di chiavi già presenti per evitare duplicati
    esistenti = set()
    if solo_nuove:
        async for lf in db.lotti_fornitori.find(
            {}, {"_id": 0, "fattura_ref": 1, "prodotto_nome": 1, "fornitore": 1}
        ):
            esistenti.add(
                (lf.get("fattura_ref", ""), lf.get("prodotto_nome", ""), lf.get("fornitore", ""))
            )

    esclusi_docs = await db.fornitori.find({"escluso": True}, {"_id": 0, "nome": 1}).to_list(2000)
    esclusi = {(d.get("nome") or "").strip().lower() for d in esclusi_docs if d.get("nome")}

    nuove = 0
    saltate = 0
    docs = []
    for f in fatture:
        fornitore = (f.get("fornitore") or "").strip()
        if not fornitore or _is_sconosciuto(fornitore):
            continue
        if fornitore.lower() in esclusi:
            continue
        fornitore_norm = _norm_nome(fornitore)
        numero_fattura = f.get("numero_fattura", "")
        data_fattura = f.get("data_fattura", "")
        piva = f.get("piva", "")

        for p in f.get("prodotti", []):
            desc = (p.get("descrizione") or p.get("nome") or "").strip()
            if not desc or _is_spesa_accessoria(desc):
                saltate += 1
                continue
            key = (numero_fattura, desc, fornitore)
            if key in esistenti:
                continue
            try:
                prezzo = float(str(p.get("prezzo", 0) or 0))
                qty = float(str(p.get("quantita", 0) or 0))
            except Exception:
                prezzo, qty = 0, 0

            allergeni_testo = _rileva(desc)
            trovati_lista = [
                a for a in _ALLERGENI_KW if any(kw in desc.lower() for kw in _ALLERGENI_KW[a])
            ]

            docs.append(
                {
                    "id": str(uuid.uuid4()),
                    "fornitore": fornitore,
                    "fornitore_norm": fornitore_norm,
                    "piva": piva,
                    "fattura_ref": numero_fattura,
                    "data_fattura": data_fattura,
                    "prodotto_nome": desc,
                    "descrizione_completa": desc,
                    "quantita_disponibile": qty,
                    "unita_misura": p.get("unita_misura", ""),
                    "prezzo_unitario": prezzo,
                    "allergeni_testo": allergeni_testo,
                    "allergeni_lista": trovati_lista,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            esistenti.add(key)
            nuove += 1

            # Batch insert ogni 500
            if len(docs) >= 500:
                await db.lotti_fornitori.insert_many(docs)
                docs = []

    if docs:
        await db.lotti_fornitori.insert_many(docs)

    tot = await db.lotti_fornitori.count_documents({})
    return {
        "ok": True,
        "nuove_inserite": nuove,
        "righe_accessorie_saltate": saltate,
        "totale_lotti_fornitori": tot,
    }


@router.post("/normalizza-unita")
async def normalizza_unita_lotti():
    """Normalizza le unità di misura sporche in lotti_fornitori (LT→L, NR/NR./N.→PZ,
    kg→KG, Pezzi→PZ, ecc.). Mapping sicuro: le sigle ambigue restano invariate.
    Idempotente e veloce: usa distinct + update_many (poche operazioni bulk)."""
    from .xml_helpers import normalizza_unita_misura

    valori = await db.lotti_fornitori.distinct("unita_misura")
    cambi = {}
    aggiornati = 0
    for v in valori:
        if v is None:
            continue
        n = normalizza_unita_misura(v)
        if n != v:
            res = await db.lotti_fornitori.update_many(
                {"unita_misura": v}, {"$set": {"unita_misura": n}}
            )
            cambi[f"{v or '∅'}→{n or '∅'}"] = res.modified_count
            aggiornati += res.modified_count
    return {"ok": True, "valori_distinti": len(valori), "aggiornati": aggiornati, "cambi": cambi}

