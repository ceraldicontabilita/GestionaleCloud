"""
Router per la gestione dei Fornitori.
Include scheda anagrafica, stati (attivo/escluso/in_attesa) e gestione nuovi fornitori.
"""

from fastapi import APIRouter, Query, HTTPException
from datetime import datetime, timezone
from typing import Optional
import uuid
import logging
_LOG_INIT = logging.getLogger("uvicorn.error")
import re
from app.lotti.routers.unita_misura import normalizza_unita_display

from app.lotti.db import database as db

router = APIRouter(prefix="/fornitori", tags=["Fornitori"])

# ── Keywords per auto-riconoscimento HORECA (alimentari/bevande) ──
HORECA_KEYWORDS = [
    "food",
    "alimentar",
    "dolciari",
    "pasticc",
    "panific",
    "forno",
    "carne",
    "maceller",
    "salum",
    "lattier",
    "casear",
    "formagg",
    "frutta",
    "verdur",
    "ortofrutt",
    "surgelat",
    "congel",
    "bevand",
    "bibite",
    "acqua",
    "vino",
    "birr",
    "liquor",
    "distiller",
    "olio",
    "farina",
    "zuccher",
    "caffè",
    "caffe",
    "café",
    "ingrosso alimentar",
    "ingrosso",
    "gial",
    "grossist",
    "conserv",
    "pomodor",
    "pesce",
    "ittic",
    "gastrono",
    "gelat",
    "cioccolat",
    "cacao",
    "spezie",
    "condiment",
    "mozzarell",
    "ricott",
    "provol",
    "yogurt",
    "panna",
    "rosticc",
    "pizz",
    "ristora",
    "hotel",
    "bar ",
    "trattoria",
    "oleifici",
    "caseifici",
    "salumifico",
    "pastificio",
    "napoli group",
    "gb food",
    "big food",
    "acquaviva",
    "vandemoortele",
    "rondinella",
    "fiorentino",
    "cilatte",
    "eurouova",
    "nasti",
    "baldassarre",
    "di cosmo",
    "cozzolino",
    "sommella",
    "collefasani",
    "cofrut",
    "scaramuzza",
    "saima",
    "mepa",
    "pick solution",
]

NON_HORECA_KEYWORDS = [
    "telecom",
    "telefon",
    "tim ",
    "vodafone",
    "wind",
    "fastweb",
    "enel",
    "eni ",
    "edison",
    "a2a",
    "sorgenia",
    "energia",
    "assicuraz",
    "insurance",
    "generali",
    "unipol",
    "allianz",
    "arval",
    "leasys",
    "leaseplan",
    "noleggi",
    "autonoleg",
    "amazon",
    "hp ",
    "lenovo",
    "apple",
    "microsoft",
    "google",
    "aruba",
    "register",
    "hosting",
    "cloud",
    "server",
    "banca",
    "unicredit",
    "intesa",
    "bnl",
    "monte paschi",
    "posta",
    "corriere",
    "sda",
    "dhl",
    "ups",
    "fedex",
    "ceramich",
    "edil",
    "impiant",
    "elettric",
    "idraulic",
    "avvocat",
    "notai",
    "commercialist",
    "consulen",
    "tipograf",
    "stamp",
    "pubblicit",
    "pulizia",
    "disinfest",
    "sanific",
]


def is_horeca(nome_fornitore: str) -> bool:
    """Auto-rileva se un fornitore è del canale HORECA (alimentari/bevande)."""
    nome_lower = nome_fornitore.lower()
    # Prima controlla se è sicuramente NON-HORECA
    for kw in NON_HORECA_KEYWORDS:
        if kw in nome_lower:
            return False
    # Poi controlla se è HORECA
    for kw in HORECA_KEYWORDS:
        if kw in nome_lower:
            return True
    # Default: non classificato → in_attesa
    return False


# ==================== ENDPOINTS ====================

# Gli endpoint Registro/Schede Ricevimento/Note sono stati estratti in
# `routers/fornitori_schede.py` (vedi server.py per registrazione).

# Gli endpoint Qualifica HACCP (in-attesa, approva, batch, auto-qualifica,
# scadenze-rinnovo, rinnova) sono stati estratti in
# `routers/fornitori_qualifica.py`.

# Gli endpoint Deduplica (duplicati-per-piva, merge, dedup-record-identici,
# auto-merge-normalizzati) sono in `routers/fornitori_dedup.py`.


from time import monotonic as _monotonic

# Cache 60s della lista fornitori SENZA filtri (la chiamata fatta ad ogni
# apertura dell'app): il calcolo completo (distinct fatture + merge + overlay
# decisioni) pesa, e per un minuto il risultato non cambia. Invalidatta da
# ogni decisione di Enzo (_salva_decisione).
_CACHE_FORNITORI = {"dati": None, "scade": 0.0}


def _chiave_fornitore(nome: str) -> str:
    """Chiave di confronto robusta per i nomi fornitore: minuscolo, senza
    virgolette, spazi multipli collassati, punti finali via. Serve perché lo
    STESSO fornitore arriva scritto in modi diversi da fatture diverse
    ("ALFA SERVICE S.R.L." / "ALFA  SERVICE S.R.L") e la decisione di Enzo
    deve valere per tutte le varianti."""
    n = (nome or "").strip().strip('"').strip("'").strip().lower()
    n = re.sub(r"\s+", " ", n)
    return n.rstrip(".")


async def _salva_decisione(nome_norm: str, *, escluso: bool, piva: str = "",
                           tipo_fornitura: str = ""):
    """Registra la decisione di Enzo su un fornitore in `fornitori_decisioni`,
    collection DI SOLA PROPRIETÀ DI LOTTI. Il DB `fornitori` è condiviso con
    il gestionale Cloud, che può risovrascrivere i record (era la causa dei
    fornitori esclusi che "ricomparivano" in attesa, 23/07/2026): la decisione
    qui invece non la tocca nessuno, e la lista la ri-applica sempre,
    auto-riparando db.fornitori quando trova divergenze."""
    doc = {
        "chiave": _chiave_fornitore(nome_norm),
        "nome": nome_norm,
        "escluso": escluso,
        "in_attesa": False,
        "deciso_il": datetime.now(timezone.utc).isoformat(),
    }
    if piva:
        doc["piva"] = piva.strip()
    if tipo_fornitura:
        doc["tipo_fornitura"] = tipo_fornitura
    await db.fornitori_decisioni.update_one(
        {"chiave": doc["chiave"]}, {"$set": doc}, upsert=True
    )
    # una decisione cambia la lista: via la cache, la prossima GET ricalcola
    _CACHE_FORNITORI["dati"] = None


@router.get("")
async def get_fornitori(stato: Optional[str] = None, search: Optional[str] = None):
    """Lista fornitori con scheda anagrafica e statistiche"""
    if not stato and not search and _CACHE_FORNITORI["dati"] is not None \
            and _monotonic() < _CACHE_FORNITORI["scade"]:
        return _CACHE_FORNITORI["dati"]
    # Una sola query per tutti i fornitori unici
    fornitori_fatture_raw = await db.fatture.distinct("fornitore")
    # Normalizza nomi (rimuovi spazi, virgolette, dedup case-insensitive)
    seen_names = {}
    for nome in fornitori_fatture_raw:
        if not nome:
            continue
        nome_norm = nome.strip().strip('"').strip("'").strip()
        nome_lower = _chiave_fornitore(nome_norm)
        if nome_lower not in seen_names:
            seen_names[nome_lower] = nome_norm
    fornitori_fatture = list(seen_names.values())

    # Una sola query per tutte le info fornitori
    fornitori_db = await db.fornitori.find({}, {"_id": 0}).to_list(2000)

    def _nome_f(f):
        """Fallback: nome HACCP → ragione_sociale → denominazione (schema ERP)"""
        return (
            (f.get("nome") or f.get("ragione_sociale") or f.get("denominazione") or "")
            .strip()
            .strip('"')
            .strip("'")
            .strip()
        )

    # Mappa con chiave normalizzata (lowercase, senza virgolette) per matching robusto
    # FIX: in caso di duplicati (es. 1 doc con `nome` HACCP + 1 doc con `denominazione` ERP),
    # priorità al doc che ha campi gestionali (escluso / in_attesa / approvato_il) settati.
    fornitori_map = {}
    for f in fornitori_db:
        n = _nome_f(f)
        if not n:
            continue
        key = _chiave_fornitore(n)
        existing = fornitori_map.get(key)
        if existing is None:
            fornitori_map[key] = f
            continue

        # Preferisci il doc "ricco" (con stato approvazione esplicito)
        def _score(doc):
            s = 0
            if "escluso" in doc:
                s += 2
            if "in_attesa" in doc:
                s += 2
            if "approvato_il" in doc:
                s += 2
            if doc.get("piva"):
                s += 1
            if doc.get("nome"):
                s += 1  # preferisci schema HACCP a ERP
            return s

        if _score(f) > _score(existing):
            fornitori_map[key] = f

    # Una sola query per tutte le fatture (data + fornitore) — evita N+1 su Atlas
    tutte_fatture = await db.fatture.find(
        {}, {"fornitore": 1, "data_fattura": 1, "_id": 0}
    ).to_list(5000)

    # Raggruppa in memoria per fornitore (chiave normalizzata, senza virgolette)
    fatture_per_fornitore: dict = {}
    for f in tutte_fatture:
        nome_f = (f.get("fornitore", "") or "").strip().strip('"').strip("'").strip()
        if nome_f:
            key = _chiave_fornitore(nome_f)
            fatture_per_fornitore.setdefault(key, []).append(f.get("data_fattura", ""))

    def _parse_it(d):
        try:
            dd, mm, yyyy = d.strip().split("/")
            return (int(yyyy), int(mm), int(dd))
        except Exception:
            return (0, 0, 0)

    # Decisioni di Enzo (collection di sola proprietà di Lotti): vincono sempre
    # su ciò che il gestionale Cloud può aver risovrascritto in db.fornitori.
    decisioni = await db.fornitori_decisioni.find({}, {"_id": 0}).to_list(3000)
    dec_per_chiave = {d.get("chiave"): d for d in decisioni if d.get("chiave")}
    dec_per_piva = {d.get("piva"): d for d in decisioni if d.get("piva")}
    riparazioni = []  # (nome, escluso, tipo_fornitura, deciso_il)

    result = []
    for nome in fornitori_fatture:
        if not nome:
            continue
        nome_lower = _chiave_fornitore(nome)
        info = fornitori_map.get(nome_lower, None)

        if info is None:
            # Fornitore senza record → in_attesa (mai approvato)
            escluso = False
            in_attesa = True
        else:
            escluso = info.get("escluso", False)
            # Se non ha mai avuto approvazione esplicita → in_attesa
            ha_approvazione = "approvato_il" in info or "escluso" in info
            in_attesa = info.get("in_attesa", not ha_approvazione)

        # Tri-stato: completo (magazzino+lotti+ricette) | solo_magazzino | escluso.
        # Retro-compat: se manca il campo, derivo da `escluso`.
        tipo_fornitura = (info or {}).get("tipo_fornitura") or ("escluso" if escluso else "completo")

        # OVERLAY decisione (23/07/2026): se Enzo ha già deciso per questo
        # fornitore (per chiave-nome o P.IVA), la decisione vale comunque —
        # e se db.fornitori è stato risovrascritto, lo si auto-ripara.
        dec = dec_per_chiave.get(nome_lower) or dec_per_piva.get((info or {}).get("piva") or "—mai—")
        if dec:
            escluso_dec = bool(dec.get("escluso", False))
            tipo_dec = dec.get("tipo_fornitura") or ""
            diverge = (info is None or bool(info.get("escluso", False)) != escluso_dec
                       or info.get("in_attesa", True)
                       or (tipo_dec and info.get("tipo_fornitura") != tipo_dec))
            escluso = escluso_dec
            in_attesa = False
            if tipo_dec:
                tipo_fornitura = tipo_dec
            elif escluso:
                tipo_fornitura = "escluso"
            if diverge:
                riparazioni.append((nome, escluso, tipo_fornitura, dec.get("deciso_il") or ""))

        stato_fornitore = "escluso" if escluso else ("in_attesa" if in_attesa else "attivo")

        if stato and stato_fornitore != stato:
            continue
        if search and search.lower() not in nome.lower():
            continue

        date_fornitore = fatture_per_fornitore.get(nome_lower, [])
        date_fornitore.sort(key=_parse_it, reverse=True)
        ultima_data = date_fornitore[0] if date_fornitore else ""

        result.append(
            {
                "nome": nome,
                "stato": stato_fornitore,
                "escluso": escluso,
                "tipo_fornitura": tipo_fornitura,
                "in_attesa": in_attesa,
                "piva": (info or {}).get("piva", ""),
                "indirizzo": (info or {}).get("indirizzo", ""),
                "telefono": (info or {}).get("telefono", ""),
                "email": (info or {}).get("email", ""),
                "note": (info or {}).get("note", ""),
                "num_fatture": len(date_fornitore),
                "ultima_fattura": ultima_data,
                "first_seen": (info or {}).get("first_seen", ""),
                "updated_at": (info or {}).get("updated_at", ""),
            }
        )

    # AUTO-RIPARAZIONE: riallinea db.fornitori alle decisioni di Enzo dove il
    # gestionale Cloud le ha sovrascritte. Così anche tutti gli ALTRI punti
    # dell'app che leggono db.fornitori.escluso (import fatture, dizionario,
    # liste) tornano corretti senza doverli cambiare uno a uno.
    # IN BACKGROUND (fix lentezza 23/07/2026): fino a 200 update sequenziali
    # dentro la richiesta rallentavano OGNI apertura dell'app — la risposta
    # ora parte subito, le riparazioni corrono per conto loro.
    if riparazioni:
        import asyncio as _asyncio
        _asyncio.create_task(_ripara_fornitori_in_background(riparazioni[:200]))

    order = {"in_attesa": 0, "attivo": 1, "escluso": 2}
    result.sort(key=lambda x: (order.get(x["stato"], 1), x["nome"]))
    if not stato and not search:
        _CACHE_FORNITORI["dati"] = result
        _CACHE_FORNITORI["scade"] = _monotonic() + 60
    return result


async def _ripara_fornitori_in_background(riparazioni: list):
    _adesso = datetime.now(timezone.utc).isoformat()
    for _nome, _escl, _tipo, _quando in riparazioni:
        try:
            await db.fornitori.update_one(
                {"nome": {"$regex": f"^{re.escape(_nome)}$", "$options": "i"}},
                {"$set": {"escluso": _escl, "in_attesa": False,
                           "tipo_fornitura": _tipo,
                           "approvato_il": _quando or _adesso, "updated_at": _adesso},
                 "$setOnInsert": {"nome": _nome, "id": str(uuid.uuid4())}},
                upsert=True,
            )
        except Exception:
            logging.getLogger(__name__).debug(
                "[fornitori] auto-riparazione non bloccante fallita per %s", _nome)


@router.get("/{nome}/ricette-prodotte")
async def ricette_prodotte_con_fornitore(nome: str):
    """PROCESSO INVERSO della tracciabilità (richiesta Enzo 23/07/2026): il
    registro del fornitore con tutte le ricette/produzioni fatte coi suoi
    prodotti. Legge i lotti di produzione il cui scarico FIFO ha consumato
    almeno un lotto di questo fornitore (lotti_fornitori.lotti_scalati)."""
    from app.lotti.routers.utils import parse_data_flessibile
    n = (nome or "").strip()
    if not n:
        raise HTTPException(400, "nome fornitore mancante")
    rx = {"$regex": f"^\\s*{re.escape(n)}\\s*$", "$options": "i"}
    docs = await db.lotti.find(
        {"lotti_fornitori.lotti_scalati.fornitore": rx},
        {"_id": 0, "prodotto": 1, "numero_lotto": 1, "data_produzione": 1,
         "lotti_fornitori.lotti_scalati": 1},
    ).to_list(3000)

    n_low = n.lower()
    per_ricetta: dict = {}
    for d in docs:
        scal = (d.get("lotti_fornitori") or {}).get("lotti_scalati") or []
        ingredienti = sorted({
            (s.get("prodotto") or s.get("ingrediente") or "").strip()
            for s in scal
            if (s.get("fornitore") or "").strip().lower() == n_low
        } - {""})
        if not ingredienti:
            continue
        ricetta = (d.get("prodotto") or "?").strip()
        g = per_ricetta.setdefault(ricetta, {
            "ricetta": ricetta, "volte": 0, "ingredienti": set(),
            "ultimo_lotto": "", "ultima_data": "", "_ultima_key": None,
        })
        g["volte"] += 1
        g["ingredienti"].update(ingredienti)
        dp = parse_data_flessibile(d.get("data_produzione") or "")
        if dp and (g["_ultima_key"] is None or dp > g["_ultima_key"]):
            g["_ultima_key"] = dp
            g["ultima_data"] = d.get("data_produzione") or ""
            g["ultimo_lotto"] = d.get("numero_lotto") or ""

    out = []
    for g in per_ricetta.values():
        g["ingredienti"] = sorted(g["ingredienti"])
        g.pop("_ultima_key", None)
        out.append(g)
    out.sort(key=lambda g: -g["volte"])
    return {"fornitore": n, "ricette": out, "totale_ricette": len(out),
            "totale_produzioni": sum(g["volte"] for g in out)}


@router.get("/count")
async def get_fornitori_count():
    """Conta totale fornitori — endpoint leggero per health check"""
    total = await db.fornitori.count_documents({})
    attivi = await db.fornitori.count_documents(
        {"escluso": {"$ne": True}, "in_attesa": {"$ne": True}}
    )
    return {"total": total, "attivi": attivi}


@router.get("/in-attesa/count")
async def get_fornitori_in_attesa_count():
    """Conta fornitori in attesa di approvazione (per notifiche)"""
    count = await db.fornitori.count_documents({"in_attesa": True})
    return {"count": count}


@router.get("/in-attesa")
async def get_fornitori_in_attesa():
    """Lista fornitori in attesa di approvazione"""
    fornitori = await db.fornitori.find({"in_attesa": True}, {"_id": 0}).to_list(100)
    return fornitori


@router.post("/approva")
async def approva_fornitore(nome: str = Query(...), includi: bool = Query(...),
                            piva: str = Query("")):
    """
    Approva un fornitore: includilo (attivo) o escludilo.
    Cerca per nome esatto, poi normalizzato, poi case-insensitive. Se non esiste, lo crea.
    La decisione viene registrata ANCHE in `fornitori_decisioni` (collection di
    Lotti, mai toccata dal gestionale Cloud) così sopravvive alle riscritture
    del DB condiviso e la lista la ri-applica sempre (fix 23/07/2026).
    """
    nome_norm = nome.strip().strip('"').strip("'").strip()

    existing = (
        await db.fornitori.find_one({"nome": nome})
        or await db.fornitori.find_one({"nome": nome_norm})
        or await db.fornitori.find_one(
            {"nome": {"$regex": f"^{re.escape(nome_norm)}$", "$options": "i"}}
        )
    )

    update_data = {
        "in_attesa": False,
        "escluso": not includi,
        "approvato_il": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    if existing:
        await db.fornitori.update_one({"_id": existing["_id"]}, {"$set": update_data})
    else:
        # Crea nuovo record
        await db.fornitori.insert_one({"id": str(uuid.uuid4()), "nome": nome_norm, **update_data})

    await _salva_decisione(nome_norm, escluso=not includi,
                           piva=piva or (existing or {}).get("piva") or "")

    stato = "attivo" if includi else "escluso"
    return {"success": True, "nome": nome_norm or nome, "stato": stato}


@router.post("/escludi")
async def toggle_esclusione_fornitore(nome: str = Query(...), escludi: bool = Query(...)):
    """Attiva/disattiva esclusione fornitore — cerca per nome normalizzato (senza virgolette, case-insensitive)"""
    # Normalizza il nome: rimuovi virgolette esterne e spazi
    nome_norm = nome.strip().strip('"').strip("'").strip()

    # Prima prova match esatto, poi con virgolette, poi case-insensitive
    existing = (
        await db.fornitori.find_one({"nome": nome})
        or await db.fornitori.find_one({"nome": f'"{nome_norm}"'})
        or await db.fornitori.find_one({"nome": nome_norm})
        or await db.fornitori.find_one(
            {"nome": {"$regex": f"^{re.escape(nome_norm)}$", "$options": "i"}}
        )
    )

    if existing:
        await db.fornitori.update_one(
            {"_id": existing["_id"]},
            {
                "$set": {
                    "escluso": escludi,
                    "tipo_fornitura": "escluso" if escludi else "completo",
                    "in_attesa": False,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            },
        )
    else:
        # Crea nuovo record con nome normalizzato
        await db.fornitori.insert_one(
            {
                "nome": nome_norm,
                "escluso": escludi,
                "tipo_fornitura": "escluso" if escludi else "completo",
                "in_attesa": False,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    return {
        "success": True,
        "escluso": escludi,
        "nome_trovato": existing["nome"] if existing else nome_norm,
    }


@router.post("/tipo-fornitura")
async def set_tipo_fornitura(nome: str = Query(...), tipo: str = Query(...)):
    """Imposta il tri-stato di un fornitore:
    - "completo": popola magazzino + lotti tracciabilita + ricette
    - "solo_magazzino": popola magazzino/ordini ma NON lotti ne ricette
    - "escluso": non popola nulla (l'import salta le sue fatture)
    Tiene `escluso` sincronizzato (True solo se tipo=="escluso") per retro-compat."""
    if tipo not in ("completo", "solo_magazzino", "escluso"):
        raise HTTPException(400, "tipo non valido (completo | solo_magazzino | escluso)")
    nome_norm = nome.strip().strip('"').strip("'").strip()
    existing = (
        await db.fornitori.find_one({"nome": nome})
        or await db.fornitori.find_one({"nome": f'"{nome_norm}"'})
        or await db.fornitori.find_one({"nome": nome_norm})
        or await db.fornitori.find_one(
            {"nome": {"$regex": f"^{re.escape(nome_norm)}$", "$options": "i"}}
        )
    )
    set_doc = {
        "tipo_fornitura": tipo,
        "escluso": (tipo == "escluso"),
        "in_attesa": False,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if existing:
        await db.fornitori.update_one({"_id": existing["_id"]}, {"$set": set_doc})
    else:
        await db.fornitori.insert_one({"nome": nome_norm, **set_doc})
    # Decisione persistente anti-sovrascrittura (vedi approva_fornitore)
    await _salva_decisione(nome_norm, escluso=(tipo == "escluso"),
                           piva=(existing or {}).get("piva") or "",
                           tipo_fornitura=tipo)
    return {
        "success": True,
        "nome_trovato": existing["nome"] if existing else nome_norm,
        "tipo_fornitura": tipo,
    }


@router.post("/monitora-sconti")
async def toggle_monitora_sconti(nome: str = Query(...), monitora: bool = Query(...)):
    """Attiva/disattiva il monitoraggio sconti di un fornitore.
    Flag INDIPENDENTE da 'escluso' (che riguarda l'import magazzino)."""
    nome_norm = nome.strip().strip('"').strip("'").strip()
    existing = (
        await db.fornitori.find_one({"nome": nome})
        or await db.fornitori.find_one({"nome": f'"{nome_norm}"'})
        or await db.fornitori.find_one({"nome": nome_norm})
        or await db.fornitori.find_one(
            {"nome": {"$regex": f"^{re.escape(nome_norm)}$", "$options": "i"}}
        )
    )
    if existing:
        await db.fornitori.update_one(
            {"_id": existing["_id"]},
            {"$set": {"monitora_sconti": monitora,
                      "updated_at": datetime.now(timezone.utc).isoformat()}},
        )
    else:
        await db.fornitori.insert_one(
            {"nome": nome_norm, "monitora_sconti": monitora,
             "updated_at": datetime.now(timezone.utc).isoformat()}
        )
    return {"success": True, "monitora_sconti": monitora,
            "nome_trovato": existing["nome"] if existing else nome_norm}


@router.get("/sconti-monitorati")
async def lista_fornitori_monitora_sconti():
    """Elenco fornitori con flag monitora_sconti attivo (per l'interruttore UI)."""
    docs = await db.fornitori.find(
        {"monitora_sconti": True}, {"_id": 0, "nome": 1, "partita_iva": 1}
    ).to_list(1000)
    return docs


@router.get("/esclusi")
async def get_fornitori_esclusi():
    """Lista nomi fornitori esclusi"""
    fornitori = await db.fornitori.find({"escluso": True}, {"_id": 0, "nome": 1}).to_list(500)
    return [f["nome"] for f in fornitori]


@router.post("/auto-classifica-horeca")
async def auto_classifica_fornitori():
    """
    Auto-classifica TUTTI i fornitori in attesa:
    - HORECA (alimentari/bevande) → inclusi automaticamente
    - NON-HORECA (utilities, noleggi, IT, ecc.) → esclusi automaticamente
    - Non riconosciuti → restano in attesa
    """
    fornitori = await db.fornitori.find({"in_attesa": True}, {"_id": 0}).to_list(5000)

    # Anche quelli senza record esplicito (da fatture)
    nomi_fatture = await db.fatture.distinct("fornitore")
    nomi_db = set()
    async for f in db.fornitori.find({}, {"nome": 1}):
        nomi_db.add((f.get("nome", "") or "").strip().lower())

    inclusi = 0
    esclusi = 0
    non_classificati = 0
    dettaglio = []

    # Classifica fornitori con record in_attesa
    for f in fornitori:
        nome = f.get("nome", "")
        if not nome:
            continue

        if is_horeca(nome):
            await db.fornitori.update_one(
                {"nome": nome},
                {
                    "$set": {
                        "in_attesa": False,
                        "escluso": False,
                        "horeca": True,
                        "approvato_il": datetime.now(timezone.utc).isoformat(),
                    }
                },
            )
            inclusi += 1
            dettaglio.append({"nome": nome, "stato": "incluso_horeca"})
        else:
            # Controlla se è sicuramente NON-HORECA
            nome_lower = nome.lower()
            is_non_horeca = any(kw in nome_lower for kw in NON_HORECA_KEYWORDS)
            if is_non_horeca:
                await db.fornitori.update_one(
                    {"nome": nome},
                    {
                        "$set": {
                            "in_attesa": False,
                            "escluso": True,
                            "horeca": False,
                            "approvato_il": datetime.now(timezone.utc).isoformat(),
                        }
                    },
                )
                esclusi += 1
                dettaglio.append({"nome": nome, "stato": "escluso_non_horeca"})
            else:
                non_classificati += 1

    return {
        "inclusi_horeca": inclusi,
        "esclusi_non_horeca": esclusi,
        "non_classificati": non_classificati,
        "dettaglio": dettaglio[:20],  # Max 20 per risposta
    }


@router.get("/{nome_fornitore}/qualita-ricette")
async def get_qualita_ricette_fornitore(nome_fornitore: str):
    """Pannello 'qualità dati per le ricette' della scheda fornitore: misura
    quanto i prodotti comprati da questo fornitore sono UTILIZZABILI dalle
    ricette (catena: riga fattura → codice articolo → dizionario ingredienti →
    nome canonico → usato in ricetta) e elenca i buchi da sistemare. Più la
    catena è completa, più food cost/allergeni/FIFO delle ricette sono
    affidabili."""
    import re as _re
    fornitore = await db.fornitori.find_one({"nome": nome_fornitore}, {"_id": 0, "piva": 1})
    nome_clean = nome_fornitore.strip()
    or_clauses = [{"fornitore": {"$regex": f"^\\s*{_re.escape(nome_clean)}\\s*$", "$options": "i"}}]
    piva_forn = ((fornitore or {}).get("piva") or "").strip()
    if piva_forn and len(piva_forn) >= 8:
        or_clauses.append({"piva": piva_forn})

    # 1) prodotti distinti acquistati in fattura (con/senza codice articolo)
    prodotti = {}
    async for f in db.fatture.find({"$or": or_clauses}, {"_id": 0, "prodotti": 1}):
        for p in f.get("prodotti", []):
            desc = (p.get("descrizione") or "").strip()
            if not desc:
                continue
            k = desc.lower()
            e = prodotti.setdefault(k, {"descrizione": desc, "con_codice": False})
            if p.get("codice_articolo"):
                e["con_codice"] = True

    # 2) indice dizionario ingredienti: nome_normalizzato + aliases → {id, canonico}
    dizionario = {}
    async for d in db.dizionario_prodotti.find(
        {}, {"_id": 0, "id": 1, "nome_normalizzato": 1, "aliases": 1, "nome_canonico": 1}
    ):
        info = {"id": d.get("id"), "nome_canonico": (d.get("nome_canonico") or "").strip()}
        chiavi = [d.get("nome_normalizzato") or ""] + list(d.get("aliases") or [])
        for c in chiavi:
            c = (c or "").strip().lower()
            if c:
                dizionario.setdefault(c, info)

    # 3) quali voci del dizionario sono usate nelle ricette (ingredienti_dettaglio)
    ricette_per_id = {}
    async for r in db.ricette.find({}, {"_id": 0, "nome": 1, "ingredienti_dettaglio": 1}):
        for ing in r.get("ingredienti_dettaglio") or []:
            pid = ing.get("prodotto_dizionario_id")
            if pid:
                ricette_per_id.setdefault(pid, set()).add(r.get("nome") or "")

    con_codice = collegati = con_canonico = usati = 0
    ricette_coinvolte = set()
    da_sistemare = []
    for k, e in prodotti.items():
        if e["con_codice"]:
            con_codice += 1
        info = dizionario.get(k)
        if info:
            collegati += 1
            if info["nome_canonico"]:
                con_canonico += 1
            else:
                da_sistemare.append({"descrizione": e["descrizione"],
                                     "problema": "senza nome canonico (Dizionario Ingredienti)"})
            if info["id"] in ricette_per_id:
                usati += 1
                ricette_coinvolte |= ricette_per_id[info["id"]]
        else:
            da_sistemare.append({"descrizione": e["descrizione"],
                                 "problema": "non collegato al dizionario ingredienti"})

    return {
        "fornitore": nome_fornitore,
        "prodotti_acquistati": len(prodotti),
        "con_codice_articolo": con_codice,
        "collegati_dizionario": collegati,
        "con_nome_canonico": con_canonico,
        "usati_in_ricette": usati,
        "ricette_coinvolte": sorted(x for x in ricette_coinvolte if x)[:30],
        "da_sistemare": da_sistemare[:25],
        "da_sistemare_totale": len(da_sistemare),
    }


@router.get("/{nome_fornitore}/anagrafica")
async def get_anagrafica_fornitore(nome_fornitore: str, anno: str = None):
    """Scheda anagrafica completa. Se `anno` è specificato, KPI e colli vengono filtrati per quell'anno.
    Passare anno='tutti' per ottenere solo anni_disponibili senza filtro."""
    fornitore = await db.fornitori.find_one({"nome": nome_fornitore}, {"_id": 0})
    if not fornitore:
        fornitore = {"nome": nome_fornitore, "stato": "attivo"}

    import re as _re

    # Match strategia:
    # 1) Match ESATTO sul nome (case-insensitive, trim) — evita match parziali su parole comuni
    # 2) Se il fornitore ha P.IVA registrata, includi anche fatture con stessa P.IVA
    #    (cattura varianti del nome es. "ROSSI SRL" vs "Rossi S.r.l.")
    nome_clean = nome_fornitore.strip()
    or_clauses = [{"fornitore": {"$regex": f"^\\s*{_re.escape(nome_clean)}\\s*$", "$options": "i"}}]
    piva_forn = (fornitore.get("piva") or "").strip() if fornitore else ""
    if piva_forn and len(piva_forn) >= 8:
        or_clauses.append({"piva": piva_forn})

    fatture_all = await db.fatture.find(
        {"$or": or_clauses},
        {
            "_id": 0,
            "id": 1,
            "numero_fattura": 1,
            "data_fattura": 1,
            "prodotti": 1,
            "piva": 1,
            "fornitore": 1,
        },
    ).to_list(2000)
    # serve solo sapere SE la fattura ha l'XML, non l'XML stesso: proiettarlo
    # scaricava megabyte da Atlas per un booleano
    ids_con_xml = {
        f["id"] for f in await db.fatture.find(
            {"$or": or_clauses, "xml_raw": {"$exists": True, "$nin": [None, ""]}},
            {"_id": 0, "id": 1},
        ).to_list(2000)
    }

    # Deduplica su (numero_fattura, data_fattura) per gestire eventuali doppioni
    seen_fk = set()
    fatture_dedup = []
    for f in fatture_all:
        fk = (f.get("numero_fattura", ""), f.get("data_fattura", ""))
        if fk in seen_fk and fk[0]:
            continue
        seen_fk.add(fk)
        fatture_dedup.append(f)
    fatture_all = fatture_dedup

    def anno_da_data(d: str) -> int:
        try:
            if "/" in d:
                return int(d.strip().split("/")[-1])
            return int(d[:4])
        except Exception:
            return 0

    # Calcola anni disponibili (anni reali con fatture)
    anni_set = sorted(
        set(
            anno_da_data(f.get("data_fattura", ""))
            for f in fatture_all
            if anno_da_data(f.get("data_fattura", "")) > 2000
        ),
        reverse=True,
    )

    # Se anno='tutti' o nessun anno specificato, usa l'anno più recente disponibile
    anno_int = None
    if anno and anno != "tutti":
        try:
            anno_int = int(anno)
        except ValueError:
            anno_int = None

    if anno_int is None and anni_set:
        anno_int = anni_set[0]  # anno più recente

    # Filtra per anno
    fatture = [
        f
        for f in fatture_all
        if anno_int is None or anno_da_data(f.get("data_fattura", "")) == anno_int
    ]

    # Ordina per data dal più recente al più vecchio
    def parse_data_it(d: str):
        try:
            d = d.strip()
            if "/" in d:
                parts = d.split("/")
                if len(parts) == 3:
                    day, month, year = parts
                    return (int(year), int(month), int(day))
            elif "-" in d:
                parts = d.split("-")
                if len(parts) == 3:
                    year, month, day = parts
                    return (int(year), int(month), int(day))
        except Exception:
            _LOG_INIT.debug("[fornitori] errore non bloccante ignorato")
        return (0, 0, 0)

    fatture.sort(key=lambda f: parse_data_it(f.get("data_fattura", "")), reverse=True)

    # Calcola totale acquistato, prodotti distinti E conteggio colli (KAR)
    totale_acquistato = 0
    num_prodotti_diversi = set()
    colli_pagati = 0.0
    colli_omaggio = 0.0
    colli_per_fattura = []

    for f in fatture:
        cp_fat = 0.0  # colli pagati in questa fattura
        co_fat = 0.0  # colli omaggio/SC in questa fattura
        for p in f.get("prodotti", []):
            um = (p.get("unita_misura", "") or "").strip().upper()
            try:
                prezzo = float(str(p.get("prezzo", 0)).strip())
                qty = float(str(p.get("quantita", 1) or 0).strip())
            except Exception:
                prezzo, qty = 0.0, 0.0
            # Totale acquistato (solo righe pagate)
            if prezzo > 0:
                totale_acquistato += prezzo * qty
            # Conteggio colli: unità KAR, CF, CTN, o unità vuota (default = collo)
            is_collo = um in ("KAR", "CF", "CTN", "COLI", "COLL", "")
            if is_collo and qty > 0:
                if prezzo > 0:
                    cp_fat += qty
                else:
                    co_fat += qty
            desc = p.get("descrizione", "").strip().lower()
            if desc:
                num_prodotti_diversi.add(desc[:50])
        if f.get("piva") and not fornitore.get("piva"):
            fornitore["piva"] = f["piva"]
        if cp_fat > 0 or co_fat > 0:
            colli_per_fattura.append(
                {
                    "numero": f.get("numero_fattura", ""),
                    "data": f.get("data_fattura", ""),
                    "pagati": int(cp_fat),
                    "omaggio": int(co_fat),
                }
            )
        colli_pagati += cp_fat
        colli_omaggio += co_fat

    # Calcola diritti omaggio (ogni 10 colli pagati → 1 omaggio)
    soglia_omaggio = 10
    omaggi_maturati = int(colli_pagati // soglia_omaggio)
    omaggi_ricevuti = int(colli_omaggio)
    # Differenza: positivo = omaggi in credito (da ricevere), negativo = anticipo già ricevuto
    omaggi_credito = omaggi_maturati - omaggi_ricevuti

    # Colli mancanti al prossimo omaggio:
    # Se ho ricevuto più omaggi di quanti ne ho maturati (anticipo),
    # devo prima "azzerare" l'anticipo e poi completare il ciclo successivo.
    # Esempio: 87 pagati, 8 maturati, 9 ricevuti → anticipo = 1
    #   - Per maturare il 9° omaggio mancano: 90 - 87 = 3 colli
    #   - Ma ne ho già ricevuto 1 di anticipo → il prossimo libero sarà il 10°
    #   - Serve: (90 - 87) + 10 = 13 colli
    colli_nel_ciclo = int(colli_pagati % soglia_omaggio)  # quanti ne ho nel ciclo corrente
    colli_per_completare_ciclo = (soglia_omaggio - colli_nel_ciclo) % soglia_omaggio

    if omaggi_credito >= 0:
        # Caso normale: non ho anticipi → mancano solo i colli del ciclo corrente
        colli_al_prossimo = colli_per_completare_ciclo
        if colli_al_prossimo == 0:
            colli_al_prossimo = 0  # omaggio già maturato!
    else:
        # Ho ricevuto più omaggi di quanti ne ho guadagnati (anticipo)
        # anticipo = abs(omaggi_credito) omaggi già "consumati in anticipo"
        # Devo completare il ciclo corrente + (anticipo × soglia) colli extra
        anticipo = abs(omaggi_credito)
        colli_al_prossimo = colli_per_completare_ciclo + (anticipo * soglia_omaggio)

    # ── Calcola VALORE ECONOMICO degli omaggi ricevuti ─────────────────────────
    # Tipo "prodotto_finito"    → in prodotti_vendita con prezzo > 0
    #                              valore = prezzo_vendita × pezzi ricevuti
    # Tipo "ingrediente_ricetta"→ usato come ingrediente in una ricetta
    #                              valore = risparmio food cost = costo_acquisto × cartoni
    # Tipo "sconosciuto"        → non trovato → stima = costo_acquisto × cartoni
    valore_omaggi = 0.0
    incasso_omaggi = 0.0
    pezzi_omaggio_totali = 0
    omaggi_dettaglio = []

    # ── Costruisci mappa prezzi acquisto (media su tutte le fatture del fornitore) ──
    prezzi_globali: dict = {}
    for fat in fatture:
        for p in fat.get("prodotti", []):
            try:
                pr = float(str(p.get("prezzo", 0) or 0).strip())
            except Exception:
                pr = 0.0
            if pr <= 0:
                continue
            desc = (p.get("descrizione", "") or "").strip().upper()
            if desc:
                prezzi_globali.setdefault(desc, []).append(pr)
    prezzi_medi: dict = {d: sum(v) / len(v) for d, v in prezzi_globali.items()}

    # ── Carica prodotti_vendita (prodotti finiti) ─────────────────────────────
    prodotti_vendita_list = await db.prodotti_vendita.find(
        {"prezzo_vendita": {"$gt": 0}},
        {"_id": 0, "nome": 1, "prezzo_vendita": 1, "pezzi_cartone": 1, "codice_prodotto": 1},
    ).to_list(2000)
    pv_map: dict = {p["nome"].lower().strip(): p for p in prodotti_vendita_list}
    pv_cod_map: dict = {
        str(p.get("codice_prodotto", "")): p
        for p in prodotti_vendita_list
        if p.get("codice_prodotto")
    }

    # ── Carica catalogo acquaviva per matching codice ──────────────────────────
    acq_prods = await db.acquaviva_prodotti.find(
        {}, {"_id": 0, "nome": 1, "codice": 1, "grammi": 1, "pz_confezione": 1}
    ).to_list(2000)
    acq_nome_map: list = [
        (p["nome"].lower().strip(), str(p.get("codice", "")).strip())
        for p in acq_prods
        if p.get("codice")
    ]

    # ── Carica prezzi medi per tipo (fallback quando match esatto fallisce) ────
    # Raggruppa prodotti_vendita per prima parola significativa
    prezzi_per_tipo: dict = {}
    for pv_item in prodotti_vendita_list:
        nome_pv = pv_item.get("nome", "").lower().strip()
        parole = [w for w in nome_pv.split() if len(w) > 3][:2]
        if parole and float(pv_item.get("prezzo_vendita", 0) or 0) > 0:
            key = parole[0]
            prezzi_per_tipo.setdefault(key, []).append(
                {
                    "prezzo": float(pv_item["prezzo_vendita"]),
                    "pezzi_cartone": int(pv_item.get("pezzi_cartone") or 0),
                }
            )
    prezzi_medi_tipo: dict = {
        k: {
            "prezzo_medio": round(sum(v["prezzo"] for v in vals) / len(vals), 2),
            "pezzi_cartone_medio": round(sum(v["pezzi_cartone"] for v in vals) / len(vals)),
        }
        for k, vals in prezzi_per_tipo.items()
        if vals
    }

    ricette_docs = await db.ricette.find(
        {}, {"_id": 0, "nome": 1, "prezzo_vendita": 1, "ingredienti_dettaglio": 1}
    ).to_list(500)

    # Mappa: parola_chiave_ingrediente → lista di ricette che lo contengono
    ingrediente_ricette_map: dict = {}  # parola → [{"nome_ricetta": ..., "prezzo_vendita": ...}]
    for ric in ricette_docs:
        for ing in ric.get("ingredienti_dettaglio") or []:
            nome_ing = (ing.get("nome") or "").lower().strip()
            # Indicizza per ogni parola significativa dell'ingrediente
            for w in nome_ing.split():
                if len(w) > 3:
                    ingrediente_ricette_map.setdefault(w, []).append(
                        {
                            "nome_ricetta": ric.get("nome", ""),
                            "prezzo_vendita": ric.get("prezzo_vendita") or 0.0,
                            "nome_ingrediente": nome_ing,
                        }
                    )

    # ── Helper: calcola pezzi da spec peso sul nome (90G 4.95KG → ~55 pz) ─────
    import re as _re2

    def pz_da_nome(nome: str):
        m = _re2.search(r"(\d+(?:[,\.]\d+)?)\s*G\s+(\d+(?:[,\.]\d+)?)\s*KG", nome.upper())
        if m:
            try:
                peso_pz = float(m.group(1).replace(",", "."))
                peso_kg = float(m.group(2).replace(",", "."))
                if peso_pz > 0:
                    return round(peso_kg * 1000 / peso_pz)
            except Exception:
                _LOG_INIT.debug("[fornitori] errore non bloccante ignorato")
        return None

    # ── Helper: classifica il prodotto omaggio ────────────────────────────────
    ABBR_MAP = {
        "cmbll": "ciambella",
        "crnt": "croissant",
        "broch": "brioche",
        "plmt": "palmito",
        "krans": "krans",
        "tappi": "tappi",
        "caruso": "caruso",
        "sfogliat": "sfogliatella",
        "calise": "calise",
        "doram": "doramì",
        "muffin": "muffin",
        "donuts": "donuts",
        "babà": "babà",
        "baba": "babà",
        "pizza": "pizza",
        "focac": "focaccia",
        "vgn": "vegan",
        "str": "dritto",
        "cali": "california",
        "stra": "arancia",
        "crea": "crema",
        "curved": "curvo",
        "mltcer": "multicereale",
        "ber": "berlinese",
        "sugared": "zuccherata",
        "maxi": "maxi",
        "mini": "mini",
        "sicilian": "sicilian",
        "lmn": "limone",
        "orange": "arancia",
        "grandi": "grandi",
        "piccoli": "piccoli",
    }

    def classifica_omaggio(desc: str) -> dict:
        """
        Classifica il prodotto omaggio e restituisce:
        {
            "tipo": "prodotto_finito" | "ingrediente_ricetta" | "sconosciuto",
            "prezzo_vendita_pezzo": float,   # solo per prodotto_finito
            "pezzi_cartone": int,
            "ricette_collegate": [],         # solo per ingrediente_ricetta
        }
        """
        desc_lower = desc.lower().strip()
        desc_clean = _re2.sub(r"^aqv\s+", "", desc_lower).strip()
        desc_nospecs = _re2.sub(
            r"\s*\d+\.?\d*\s*[Gg]\s+\d+\.?\d*\s*[Kk][Gg].*$", "", desc_clean
        ).strip()
        desc_nospecs = _re2.sub(r"\s+\d+\.?\d*\s*[Gg][A-Z]*\s*$", "", desc_nospecs).strip()
        desc_nonum = desc_nospecs

        parole_desc = [w for w in desc_nonum.split() if len(w) > 3 and not w.isdigit()][:4]
        # Versione espansa abbreviazioni
        parole_espanse = [ABBR_MAP.get(w, w) for w in desc_nonum.split()]
        desc_espansa = " ".join(parole_espanse)
        parole_esp = [w for w in desc_espansa.split() if len(w) > 3 and not w.isdigit()][:4]

        # ── 1. Cerca in prodotti_vendita (prodotto finito) ────────────────────
        def _cerca_in_pv(parole: list):
            for key, pv_item in pv_map.items():
                parole_key = [w for w in key.split() if len(w) > 3 and not w.isdigit()][:4]
                if parole[:2] and parole_key[:2] and parole[:2] == parole_key[:2]:
                    return pv_item
            return None

        for variant_parole in [parole_desc, parole_esp]:
            match = _cerca_in_pv(variant_parole)
            if match and float(match.get("prezzo_vendita", 0) or 0) > 0:
                return {
                    "tipo": "prodotto_finito",
                    "prezzo_vendita_pezzo": float(match["prezzo_vendita"]),
                    "pezzi_cartone": int(match.get("pezzi_cartone") or 0),
                    "ricette_collegate": [],
                }

        # Anche via codice acquaviva
        for acq_nome, acq_cod in acq_nome_map:
            acq_clean = _re2.sub(r"\s+g\.\s*\d+.*$", "", acq_nome).strip()
            acq_clean = _re2.sub(r"\s+\d[\d\.\,]*\s*[gk].*$", "", acq_clean).strip()
            parole_acq = [w for w in acq_clean.split() if len(w) > 3 and not w.isdigit()][:2]
            if parole_acq and parole_desc[:2] == parole_acq[:2]:
                if acq_cod in pv_cod_map:
                    pv_item = pv_cod_map[acq_cod]
                    if float(pv_item.get("prezzo_vendita", 0) or 0) > 0:
                        return {
                            "tipo": "prodotto_finito",
                            "prezzo_vendita_pezzo": float(pv_item["prezzo_vendita"]),
                            "pezzi_cartone": int(pv_item.get("pezzi_cartone") or 0),
                            "ricette_collegate": [],
                        }

        # ── 2. Cerca in ricette come ingrediente (serve almeno 2 parole in comune) ──
        ricette_trovate = []
        # Conta quante parole significative matchano per ogni ricetta
        match_counter: dict = {}  # nome_ricetta → {"count": int, "info": dict}
        tutte_parole_desc = set(parole_desc + parole_esp)

        for parola in tutte_parole_desc:
            if parola in ingrediente_ricette_map:
                for ric_info in ingrediente_ricette_map[parola]:
                    k = ric_info["nome_ricetta"]
                    if k not in match_counter:
                        match_counter[k] = {"count": 0, "info": ric_info}
                    match_counter[k]["count"] += 1

        # Accetta solo se almeno 2 parole matchano (per evitare falsi positivi generici)
        for nome_ric, mc in match_counter.items():
            if mc["count"] >= 2:
                if not any(r["nome_ricetta"] == nome_ric for r in ricette_trovate):
                    ricette_trovate.append(mc["info"])

        if ricette_trovate:
            return {
                "tipo": "ingrediente_ricetta",
                "prezzo_vendita_pezzo": 0.0,
                "pezzi_cartone": 0,
                "ricette_collegate": ricette_trovate[:3],  # max 3 ricette
            }

        # ── 3b. Fallback: usa prezzo medio per tipo (es. "croissant" → €1.81) ──
        # Prendi la prima parola espansa significativa e cerca nei prezzi_medi_tipo
        for parola in parole_esp[:2]:
            if parola in prezzi_medi_tipo:
                tipo_data = prezzi_medi_tipo[parola]
                return {
                    "tipo": "prodotto_finito",  # stimato da categoria
                    "prezzo_vendita_pezzo": tipo_data["prezzo_medio"],
                    "pezzi_cartone": tipo_data["pezzi_cartone_medio"],
                    "ricette_collegate": [],
                    "stima": True,  # flag per UI: valore stimato non esatto
                }

        # ── 4. Sconosciuto ────────────────────────────────────────────────────
        return {
            "tipo": "sconosciuto",
            "prezzo_vendita_pezzo": 0.0,
            "pezzi_cartone": 0,
            "ricette_collegate": [],
            "stima": False,
        }

    # ── Loop principale: calcola valore per ogni riga omaggio ────────────────
    for fat in fatture:
        prods = fat.get("prodotti", [])
        prezzi_locali: dict = {}
        for p in prods:
            try:
                pr = float(str(p.get("prezzo", 0) or 0).strip())
            except Exception:
                pr = 0.0
            desc = (p.get("descrizione", "") or "").strip().upper()
            if pr > 0 and desc:
                prezzi_locali[desc] = pr

        for p in prods:
            try:
                pr = float(str(p.get("prezzo", 0) or 0).strip())
                qty = float(str(p.get("quantita", 0) or 0).strip())
            except Exception:
                continue
            if pr > 0 or qty <= 0:
                continue

            desc = (p.get("descrizione", "") or "").strip().upper()
            um = (p.get("unita_misura", "") or "").strip().upper()

            # Costo acquisto: locale → globale → prime 2 parole
            prezzo_acquisto = 0.0
            for src in [prezzi_locali, prezzi_medi]:
                if desc in src:
                    prezzo_acquisto = src[desc]
                    break
                parole_sc = desc.split()[:2]
                for d2, pr2 in src.items():
                    if d2.split()[:2] == parole_sc:
                        prezzo_acquisto = pr2
                        break
                if prezzo_acquisto:
                    break

            # Pezzi totali (da peso-spec nel nome o da pzc_vendita)
            pezzi = int(qty)
            ppc = pz_da_nome(desc)
            if um in ("KAR", "CF", "CTN") and ppc:
                pezzi = int(qty * ppc)

            # Classifica il prodotto
            cls = classifica_omaggio(desc)
            tipo = cls["tipo"]
            pv_pezzo = cls["prezzo_vendita_pezzo"]
            pzc_vendita = cls["pezzi_cartone"]
            ricette_collegate = cls["ricette_collegate"]

            # Aggiusta pezzi se catalogo ha pezzi_cartone
            if pzc_vendita > 0 and pezzi == int(qty):
                pezzi = int(qty * pzc_vendita)

            pezzi_eff = pezzi

            # Calcola valore economico in base al tipo
            valore_acquisto_riga = round(prezzo_acquisto * qty, 2) if prezzo_acquisto else 0.0

            if tipo == "prodotto_finito":
                # Incasso reale dalla vendita
                valore_riga = (
                    round(pv_pezzo * pezzi_eff, 2) if pv_pezzo > 0 else valore_acquisto_riga
                )
                incasso_omaggi += valore_riga
            elif tipo == "ingrediente_ricetta":
                # Risparmio sul food cost = costo acquisto (quanto non ho pagato)
                valore_riga = valore_acquisto_riga
                incasso_omaggi += valore_riga
            else:
                # Sconosciuto: stima dal costo acquisto
                valore_riga = valore_acquisto_riga
                incasso_omaggi += valore_riga

            valore_omaggi += valore_acquisto_riga
            pezzi_omaggio_totali += pezzi_eff

            # Raggruppa per prodotto
            trovato_esistente = False
            for od in omaggi_dettaglio:
                if od["prodotto"] == desc:
                    od["qty_cartoni"] += qty
                    od["pezzi_totali"] += pezzi_eff
                    od["valore_acquisto"] += valore_acquisto_riga
                    od["valore_totale"] += valore_acquisto_riga
                    od["valore_economico"] += valore_riga
                    od["incasso_vendita"] += valore_riga if tipo == "prodotto_finito" else 0.0
                    trovato_esistente = True
                    break
            if not trovato_esistente:
                omaggi_dettaglio.append(
                    {
                        "prodotto": desc,
                        "tipo": tipo,
                        "stima": cls.get("stima", False),  # NUOVO: True se stima per categoria
                        "ricette_collegate": ricette_collegate,
                        "qty_cartoni": qty,
                        "pezzi_totali": pezzi_eff,
                        "prezzo_unitario": round(prezzo_acquisto, 2),
                        "prezzo_vendita_pezzo": round(pv_pezzo, 2),
                        "valore_acquisto": valore_acquisto_riga,
                        "valore_totale": valore_acquisto_riga,
                        "valore_economico": valore_riga,
                        "incasso_vendita": valore_riga if tipo == "prodotto_finito" else 0.0,
                        "pezzi_per_cartone": ppc or pzc_vendita or 0,
                    }
                )

    # Ordina per valore_economico decrescente
    omaggi_dettaglio.sort(
        key=lambda x: -(x.get("valore_economico", 0) or x.get("valore_totale", 0))
    )

    # Percentuale recupero
    perc_recupero = (
        round((incasso_omaggi / totale_acquistato * 100), 1) if totale_acquistato > 0 else 0.0
    )

    ultima_fattura = fatture[0].get("data_fattura", "") if fatture else ""

    # ── Rimanenze: giacenza FIFO attuale dei prodotti di QUESTO fornitore ──────
    # Legge lotti_fornitori (quantita_disponibile residua), raggruppa per prodotto.
    # Solo lotti non esauriti e con giacenza > 0. Niente valori inventati.
    rim_q = {
        "fornitore": {"$regex": f"^\\s*{_re.escape(nome_clean)}\\s*$", "$options": "i"},
        "esaurito": {"$ne": True},
    }
    rimanenze_map = {}
    async for lf in db.lotti_fornitori.find(
        rim_q,
        {"_id": 0, "prodotto_nome": 1, "prodotto_nome_norm": 1, "quantita_disponibile": 1,
         "unita_misura": 1, "data_scadenza": 1, "giorni_alla_scadenza": 1, "scaduto": 1},
    ):
        qta = float(lf.get("quantita_disponibile") or 0)
        if qta <= 0:
            continue
        nome_p = (lf.get("prodotto_nome") or lf.get("prodotto_nome_norm") or "—").strip()
        k = nome_p.lower()
        g = rimanenze_map.get(k)
        if g is None:
            rimanenze_map[k] = {
                "prodotto": nome_p,
                "quantita": round(qta, 3),
                "unita": normalizza_unita_display(lf.get("unita_misura"), "KG"),
                "n_lotti": 1,
                "data_scadenza": lf.get("data_scadenza") or "",
                "giorni_alla_scadenza": lf.get("giorni_alla_scadenza"),
                "scaduto": bool(lf.get("scaduto")),
            }
        else:
            g["quantita"] = round(g["quantita"] + qta, 3)
            g["n_lotti"] += 1
            gd = g.get("giorni_alla_scadenza"); ud = lf.get("giorni_alla_scadenza")
            if ud is not None and (gd is None or ud < gd):
                g["giorni_alla_scadenza"] = ud
                g["data_scadenza"] = lf.get("data_scadenza") or ""
            if lf.get("scaduto"):
                g["scaduto"] = True
    rimanenze = sorted(rimanenze_map.values(), key=lambda x: -x["quantita"])

    return {
        **fornitore,
        "anno_filtro": anno_int,
        "anni_disponibili": anni_set,
        "num_fatture": len(fatture),
        "num_fatture_totali": len(fatture_all),
        "ultima_fattura": ultima_fattura,
        "rimanenze": rimanenze,
        "num_prodotti_in_giacenza": len(rimanenze),
        "totale_acquistato": round(totale_acquistato, 2),
        "num_prodotti_diversi": len(num_prodotti_diversi),
        "colli_pagati": int(colli_pagati),
        "colli_omaggio_ricevuti": omaggi_ricevuti,
        "colli_omaggio_maturati": omaggi_maturati,
        "colli_credito": omaggi_credito,
        "colli_al_prossimo_omaggio": colli_al_prossimo,
        "soglia_omaggio": soglia_omaggio,
        "colli_per_fattura": sorted(colli_per_fattura, key=lambda x: x["data"], reverse=True),
        "valore_omaggi_ricevuti": round(valore_omaggi, 2),
        "incasso_omaggi_vendita": round(incasso_omaggi, 2),
        "pezzi_omaggio_totali": pezzi_omaggio_totali,
        "perc_recupero_su_fatture": perc_recupero,
        "omaggi_dettaglio": omaggi_dettaglio,
        "storico_fatture": [
            {
                "id": f.get("id", ""),
                "numero": f.get("numero_fattura", ""),
                "data": f.get("data_fattura", ""),
                "anno": anno_da_data(f.get("data_fattura", "")),
                "num_prodotti": len(f.get("prodotti", [])),
                "has_xml": f.get("id") in ids_con_xml,
            }
            for f in fatture_all
        ],
    }


@router.put("/{nome_fornitore}/anagrafica")
async def aggiorna_anagrafica_fornitore(nome_fornitore: str, dati: dict):
    """Aggiorna scheda anagrafica fornitore"""
    dati_clean = {k: v for k, v in dati.items() if k not in ["_id", "nome"]}
    dati_clean["nome"] = nome_fornitore
    dati_clean["updated_at"] = datetime.now(timezone.utc).isoformat()

    await db.fornitori.update_one({"nome": nome_fornitore}, {"$set": dati_clean}, upsert=True)
    return {"success": True}


@router.post("/note")
async def aggiorna_note_fornitore(nome: str = Query(...), note: str = Query("")):
    """Aggiorna note di un fornitore"""
    await db.fornitori.update_one(
        {"nome": nome},
        {
            "$set": {
                "nome": nome,
                "note": note,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        },
        upsert=True,
    )
    return {"success": True}


# ── DEDUPLICA FORNITORI ─────────────────────────────────────────────────────
# Gli endpoint di deduplica (duplicati-per-piva, merge, dedup-record-identici)
# sono stati spostati in `routers/fornitori_dedup.py` per ridurre la dimensione
# di questo file (mantenuto sotto 1300 righe). Il router è incluso in server.py.
