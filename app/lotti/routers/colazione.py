"""
Router per Colazione Acquaviva.
Gestisce il template giornaliero dei prodotti che escono al banco mattina.
"""

from fastapi import APIRouter, HTTPException, Body, Depends
from datetime import datetime, timezone
from typing import List, Optional
from pydantic import BaseModel
import re
import uuid
import logging
_LOG_INIT = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/colazione-acquaviva", tags=["colazione"])
from app.lotti.db import database as db
from app.lotti.auth import require_admin


class ColazioneItem(BaseModel):
    prodotto_id: str
    prodotto_nome: str
    pezzi: int
    foto_url: Optional[str] = None
    categoria: Optional[str] = None
    prezzo_vendita: Optional[float] = 0.0
    attivo: bool = True  # spuntato per la registrazione


class ColazioneTemplate(BaseModel):
    nome: str = "Colazione Acquaviva"
    items: List[ColazioneItem] = []
    note: Optional[str] = None
    data_inizio: Optional[str] = None  # "MM-DD", ricorrente ogni anno (es. "03-21")
    data_fine: Optional[str] = None    # "MM-DD"


_STAGIONI_DEFAULT = ["Primavera", "Estiva", "Autunnale", "Invernale"]

# Date di riferimento equinozi/solstizi (richiesta Enzo 03/07/2026): la
# stagione entra in vigore da sola alla data giusta, invece di doverla
# scegliere a mano ogni mattina. Modificabili da Enzo (PUT), non fisse nel
# codice: qui sono solo il SEED iniziale. Invernale attraversa il capodanno.
_DATE_STAGIONI_DEFAULT = {
    "Primavera": ("03-21", "06-20"),
    "Estiva": ("06-21", "09-22"),
    "Autunnale": ("09-23", "12-20"),
    "Invernale": ("12-21", "03-20"),
}


# Keyword SALATE (Enzo 23/07/2026: "non farmi uscire i prodotti salati nella
# colazione di pasticceria") — su categoria+nome, catalogo E fatti in casa.
# Due liste: sottostringhe SICURE (nessun dolce le contiene) e PAROLE INTERE
# per i termini ambigui — "pane" a parola intera, altrimenti mangerebbe
# "panettone"; "olive" intero per non toccare eventuali "olivette di zucchero".
_SALATO_KW = (
    "salat", "rustic", "gastronom", "pizz", "tramezz", "panin", "toast",
    "focacc", "wurstel", "wurst", "hot dog", "salsicc", "prosciutt", "salam",
    "speck", "friariell", "arancin", "crocch", "frittatin", "calzon",
    "parigin", "panzerott", "mozzarell", "pomodor", "tonno", "formagg",
    "patatin", "quiche", "hamburg", "cotolett", "kebab", "bacon", "wudy",
    "melanzan", "zucchin", "spinac", "baguett", "ciabatt", "sfilatin",
    "medaglion", "snack sal",
)
_SALATO_PAROLE = ("pane", "olive", "verdure", "verdura", "patate", "uovo sodo")
# cache degli acquisti colazione (nomi dizionario + codici articolo fattura)
_CACHE_ACQUISTI = {"nomi": set(), "codici": set(), "scade": 0.0}
_RX_SALATO_PAROLE = re.compile(
    r"\b(" + "|".join(re.escape(p) for p in _SALATO_PAROLE) + r")\b")


def _e_salato(categoria: str, nome: str) -> bool:
    t = f"{categoria or ''} {nome or ''}".lower()
    if any(k in t for k in _SALATO_KW):
        return True
    return bool(_RX_SALATO_PAROLE.search(t))


def _data_in_periodo(oggi_mmdd: str, inizio: str, fine: str) -> bool:
    """True se oggi_mmdd cade nel periodo [inizio, fine] (formato MM-DD).
    Gestisce il periodo che attraversa il capodanno (es. Invernale
    12-21..03-20): se inizio > fine, il periodo "avvolge" l'anno."""
    if not inizio or not fine:
        return False
    if inizio <= fine:
        return inizio <= oggi_mmdd <= fine
    return oggi_mmdd >= inizio or oggi_mmdd <= fine


# ── GET elenco preset (stagionali) ─────────────────────────────────────────────
@router.get("/preset")
async def lista_preset():
    """Elenco dei preset colazione (stagionali). Garantisce sempre le 4 stagioni
    coi periodi solstizi/equinozi di default (solo al primo avvio, non
    sovrascrive periodi già modificati da Enzo)."""
    now = datetime.now(timezone.utc).isoformat()
    for nome in _STAGIONI_DEFAULT:
        inizio, fine = _DATE_STAGIONI_DEFAULT[nome]
        await db.colazione_template.update_one(
            {"nome": nome},
            {"$setOnInsert": {
                "nome": nome, "items": [], "note": None, "ultima_modifica": now,
                "data_inizio": inizio, "data_fine": fine,
            }},
            upsert=True,
        )
        # BACKFILL (Enzo 23/07/2026: "imposta i solstizi automaticamente"): i
        # preset creati PRIMA dell'introduzione dei periodi restavano senza
        # date ($setOnInsert non tocca i doc esistenti). Qui si riempiono i
        # periodi mancanti coi solstizi/equinozi standard — MAI sovrascrivendo
        # date già personalizzate da Enzo (si tocca solo se vuoto/assente).
        await db.colazione_template.update_one(
            {"nome": nome, "$or": [{"data_inizio": {"$in": [None, ""]}},
                                    {"data_inizio": {"$exists": False}}]},
            {"$set": {"data_inizio": inizio, "data_fine": fine}},
        )
    docs = await db.colazione_template.find(
        {}, {"_id": 0, "nome": 1, "items": 1, "ultima_modifica": 1, "data_inizio": 1, "data_fine": 1}
    ).to_list(100)

    def _ord(d):
        n = d.get("nome", "")
        return (_STAGIONI_DEFAULT.index(n) if n in _STAGIONI_DEFAULT else len(_STAGIONI_DEFAULT), n)

    docs.sort(key=_ord)
    return [
        {
            "nome": d["nome"], "n_prodotti": len(d.get("items", [])),
            "ultima_modifica": d.get("ultima_modifica"),
            "data_inizio": d.get("data_inizio"), "data_fine": d.get("data_fine"),
        }
        for d in docs
    ]


# ── GET: stagione attiva OGGI in base al periodo configurato ───────────────────
@router.get("/stagione-attiva")
async def stagione_attiva():
    """Trova la stagione il cui periodo (data_inizio..data_fine) contiene
    oggi. Il frontend la usa per pre-selezionare la stagione giusta invece
    di richiedere la scelta manuale ogni mattina."""
    oggi = datetime.now(timezone.utc).strftime("%m-%d")
    docs = await db.colazione_template.find(
        {"data_inizio": {"$nin": [None, ""]}, "data_fine": {"$nin": [None, ""]}},
        {"_id": 0, "nome": 1, "data_inizio": 1, "data_fine": 1},
    ).to_list(100)
    for d in docs:
        if _data_in_periodo(oggi, d.get("data_inizio"), d.get("data_fine")):
            return {"stagione": d["nome"], "oggi": oggi}
    return {"stagione": _STAGIONI_DEFAULT[0], "oggi": oggi}


# ── PUT: aggiorna il periodo (date) di una stagione ─────────────────────────────
@router.put("/preset/{nome}/periodo")
async def aggiorna_periodo_stagione(nome: str, data: dict = Body(...)):
    """Enzo può correggere le date standard (equinozi/solstizi) se il suo
    'periodo estivo' reale non coincide con quello astronomico."""
    inizio, fine = data.get("data_inizio"), data.get("data_fine")
    if not inizio or not fine:
        raise HTTPException(400, "data_inizio e data_fine obbligatori (formato MM-DD)")
    if not re.match(r"^\d{2}-\d{2}$", inizio) or not re.match(r"^\d{2}-\d{2}$", fine):
        raise HTTPException(400, "formato atteso MM-DD, es. 03-21")
    now = datetime.now(timezone.utc).isoformat()
    r = await db.colazione_template.update_one(
        {"nome": nome},
        {"$set": {"data_inizio": inizio, "data_fine": fine, "ultima_modifica": now}},
    )
    if r.matched_count == 0:
        raise HTTPException(404, "Preset non trovato")
    return {"success": True, "nome": nome, "data_inizio": inizio, "data_fine": fine}


# ── GET: prodotti più usati (in quanti preset compaiono) ───────────────────────
# Richiesta Enzo 03/07/2026: nella ricerca "Aggiungi prodotti" doveva
# scorrere tutto il catalogo — quelli già scelti in più stagioni sono i più
# probabili da riusare, mostrarli come scorciatoia in cima.
@router.get("/prodotti-piu-usati")
async def prodotti_piu_usati(limit: int = 10):
    docs = await db.colazione_template.find({}, {"_id": 0, "items": 1}).to_list(100)
    conteggio: dict = {}
    for d in docs:
        for it in d.get("items") or []:
            pid = it.get("prodotto_id")
            if not pid:
                continue
            voce = conteggio.setdefault(pid, {"count": 0, "item": it})
            voce["count"] += 1
            voce["item"] = it  # tiene l'ultima versione vista (nome/foto aggiornati)
    piu_usati = sorted(conteggio.values(), key=lambda v: -v["count"])
    # niente salati nemmeno nella scorciatoia «Più usati» (23/07/2026)
    piu_usati = [v for v in piu_usati
                 if not _e_salato(v["item"].get("categoria"), v["item"].get("prodotto_nome"))][:limit]
    return [
        {
            "id": v["item"].get("prodotto_id"),
            "nome": v["item"].get("prodotto_nome"),
            "foto_url": v["item"].get("foto_url"),
            "categoria": v["item"].get("categoria"),
            "prezzo_vendita": v["item"].get("prezzo_vendita") or 0,
            "n_preset": v["count"],
        }
        for v in piu_usati
    ]


# ── POST: copia un preset nelle altre stagioni ────────────────────────────────
@router.post("/copia-preset")
async def copia_preset(data: dict = Body(...)):
    """Copia il menù di una stagione nelle altre (Enzo 23/07/2026: "copia
    colazione primavera in tutte le stagioni"). SOSTITUISCE gli items delle
    stagioni di destinazione con quelli della sorgente (periodi e note dei
    destinatari restano i loro)."""
    da = (data.get("da") or "").strip()
    if not da:
        raise HTTPException(400, "campo 'da' obbligatorio (nome stagione sorgente)")
    sorgente = await db.colazione_template.find_one({"nome": da}, {"_id": 0, "items": 1})
    if sorgente is None:
        raise HTTPException(404, f"Stagione '{da}' non trovata")
    items = sorgente.get("items") or []
    destinazioni = data.get("a")
    if not destinazioni:
        tutti = await db.colazione_template.find({}, {"_id": 0, "nome": 1}).to_list(100)
        destinazioni = [d["nome"] for d in tutti if d.get("nome") and d["nome"] != da]
    now = datetime.now(timezone.utc).isoformat()
    copiate = []
    for nome in destinazioni:
        if not nome or nome == da:
            continue
        r = await db.colazione_template.update_one(
            {"nome": nome},
            {"$set": {"items": [dict(i) for i in items], "ultima_modifica": now}},
        )
        if r.matched_count:
            copiate.append(nome)
    return {"ok": True, "da": da, "copiate_in": copiate, "n_prodotti": len(items)}


# ── Preferiti colazione ("l'asterisco", richiesta Enzo 03/07/2026) ─────────────
# Marcare un prodotto come preferito lo aggiunge SUBITO a tutte e 4 le
# stagioni standard (pezzi di default 6, poi si aggiusta stagione per
# stagione con lo stepper già esistente) — non serve più cercarlo a mano
# nel modale colazione ogni volta che torna la stagione.
@router.get("/preferiti")
async def lista_preferiti():
    """Elenco degli id prodotto marcati preferito colazione (per disegnare
    la stella piena/vuota nelle liste prodotto)."""
    docs = await db.colazione_preferiti.find({}, {"_id": 0, "prodotto_id": 1}).to_list(5000)
    return [d["prodotto_id"] for d in docs if d.get("prodotto_id")]


@router.post("/preferito")
async def toggle_preferito(data: dict = Body(...)):
    pid = data.get("prodotto_id")
    if not pid:
        raise HTTPException(400, "prodotto_id obbligatorio")
    now = datetime.now(timezone.utc).isoformat()

    esiste = await db.colazione_preferiti.find_one({"prodotto_id": pid})
    if esiste:
        await db.colazione_preferiti.delete_one({"prodotto_id": pid})
        # Toglie il preferito, ma NON rimuove il prodotto dalle stagioni già
        # configurate (potrebbe essere stato tarato a mano) — la rimozione
        # da una singola stagione resta il bottone ✕ già esistente lì.
        return {"preferito": False, "prodotto_id": pid}

    nome_prodotto = data.get("prodotto_nome")
    foto_url = data.get("foto_url")
    categoria = data.get("categoria")
    prezzo_vendita = data.get("prezzo_vendita") or 0
    await db.colazione_preferiti.insert_one({
        "prodotto_id": pid,
        "prodotto_nome": nome_prodotto,
        "foto_url": foto_url,
        "categoria": categoria,
        "prezzo_vendita": prezzo_vendita,
        "fonte": data.get("fonte"),
        "creato_il": now,
    })

    aggiunto_a = []
    for nome_stagione in _STAGIONI_DEFAULT:
        preset = await db.colazione_template.find_one({"nome": nome_stagione})
        items = list((preset or {}).get("items", []))
        if any(it.get("prodotto_id") == pid for it in items):
            continue  # già presente in questa stagione (magari tarato a mano): non tocco
        items.append({
            "prodotto_id": pid,
            "prodotto_nome": nome_prodotto,
            "pezzi": 6,
            "foto_url": foto_url,
            "categoria": categoria,
            "prezzo_vendita": prezzo_vendita,
            "attivo": True,
        })
        await db.colazione_template.update_one(
            {"nome": nome_stagione},
            {"$set": {"nome": nome_stagione, "items": items, "ultima_modifica": now}},
            upsert=True,
        )
        aggiunto_a.append(nome_stagione)

    return {"preferito": True, "prodotto_id": pid, "aggiunto_a_stagioni": aggiunto_a}


# ── GET template (per nome; default primo preset) ──────────────────────────────
@router.get("")
async def get_colazione(nome: Optional[str] = None):
    if nome:
        doc = await db.colazione_template.find_one({"nome": nome}, {"_id": 0})
        if not doc:
            return {"nome": nome, "items": [], "note": None, "ultima_modifica": None}
        return doc
    # back-compat: se nessun nome, ritorna il primo preset disponibile (o vuoto)
    doc = await db.colazione_template.find_one({}, {"_id": 0})
    if not doc:
        return {"nome": "Colazione Acquaviva", "items": [], "note": None, "ultima_modifica": None}
    return doc


# ── PUT: salva/aggiorna un preset (chiave = template.nome) ─────────────────────
@router.put("")
async def salva_colazione(template: ColazioneTemplate):
    now = datetime.now(timezone.utc).isoformat()
    doc = template.dict()
    doc["ultima_modifica"] = now
    await db.colazione_template.update_one(
        {"nome": template.nome}, {"$set": doc}, upsert=True
    )
    return {"success": True, "nome": template.nome, "ultima_modifica": now}


# ── DELETE: elimina un preset ──────────────────────────────────────────────────
@router.delete("/preset/{nome}")
async def elimina_preset(nome: str):
    r = await db.colazione_template.delete_one({"nome": nome})
    if r.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Preset non trovato")
    return {"success": True, "eliminato": nome}


# ── POST: aggiungi (o aggiorna qty) un prodotto in un preset ───────────────────
@router.post("/aggiungi-prodotto")
async def aggiungi_prodotto_a_preset(data: dict = Body(...)):
    preset = (data.get("preset") or "").strip()
    pid = data.get("prodotto_id")
    nome = data.get("prodotto_nome")
    pezzi = int(data.get("pezzi") or 1)
    if not preset or not pid:
        raise HTTPException(status_code=400, detail="preset e prodotto_id obbligatori")
    doc = await db.colazione_template.find_one({"nome": preset})
    items = list((doc or {}).get("items", []))
    aggiornato = False
    for it in items:
        if it.get("prodotto_id") == pid:
            it["pezzi"] = pezzi
            it["attivo"] = True
            aggiornato = True
            break
    if not aggiornato:
        items.append({
            "prodotto_id": pid,
            "prodotto_nome": nome,
            "pezzi": pezzi,
            "foto_url": data.get("foto_url"),
            "categoria": data.get("categoria"),
            "prezzo_vendita": data.get("prezzo_vendita") or 0,
            "attivo": True,
        })
    now = datetime.now(timezone.utc).isoformat()
    await db.colazione_template.update_one(
        {"nome": preset},
        {"$set": {"nome": preset, "items": items, "ultima_modifica": now}},
        upsert=True,
    )
    return {"success": True, "preset": preset, "totale_items": len(items), "aggiornato": aggiornato}


# ── POST: registra tutti gli item attivi come vendita al banco ────────────────
@router.post("/registra")
async def registra_colazione(data: dict = None):
    """
    Registra tutti gli item attivi del template come:
    1. Vendita al banco (vendite_banco)
    2. Produzione giornaliera (produzioni) — per storico e food cost
    3. Lotto tracciabilità (lotti) — per la tracciabilità HACCP
    """

    nome_preset = (data or {}).get("nome")
    query = {"nome": nome_preset} if nome_preset else {}
    doc = await db.colazione_template.find_one(query, {"_id": 0})
    if not doc or not doc.get("items"):
        raise HTTPException(status_code=404, detail="Nessun template colazione trovato")

    items_attivi = [i for i in doc["items"] if i.get("attivo", True) and i.get("pezzi", 0) > 0]
    if not items_attivi:
        raise HTTPException(status_code=400, detail="Nessun prodotto attivo nel template")

    oggi = datetime.now(timezone.utc).isoformat().split("T")[0]
    ora_now = datetime.now(timezone.utc).isoformat()
    registrati = []
    errori = []

    for item in items_attivi:
        try:
            prod_id = item["prodotto_id"]
            prod_nome = item["prodotto_nome"]
            pezzi = item["pezzi"]
            prezzo = item.get("prezzo_vendita", 0) or 0

            # ── 1. Vendita al banco ────────────────────────────────────────────
            record_banco = {
                "id": str(uuid.uuid4()),
                "prodotto_id": prod_id,
                "prodotto_nome": prod_nome,
                "reparto": "pasticceria",
                "pezzi_prodotti": pezzi,
                "pezzi_venduti": 0,
                "foto_url": item.get("foto_url"),
                "data": oggi,
                "fonte": "colazione",
                "stato": "aperto",
                "created_at": ora_now,
            }
            await db.vendite_banco.insert_one(record_banco)
            record_banco.pop("_id", None)

            # ── 2. Produzione (storico produzioni) ─────────────────────────────
            # Cerca la ricetta collegata per food cost
            ricetta = await db.ricette.find_one(
                {"nome": {"$regex": prod_nome, "$options": "i"}},
                {"_id": 0, "id": 1, "costo_totale": 1, "pezzi_produzione": 1},
            )
            costo_totale_prod = 0.0
            if ricetta:
                ct = ricetta.get("costo_totale") or 0
                pzr = ricetta.get("pezzi_produzione") or 1
                costo_totale_prod = round((ct / pzr) * pezzi, 2)

            produzione_id = str(uuid.uuid4())
            await db.produzioni.insert_one(
                {
                    "id": produzione_id,
                    "ricetta_nome": prod_nome,
                    "ricetta_id": (ricetta or {}).get("id", prod_id),
                    "quantita": pezzi,
                    "unita": "pz",
                    "costo_produzione": costo_totale_prod,
                    "data": oggi,
                    "fonte": "colazione",
                    "reparto": "pasticceria",
                    "created_at": ora_now,
                }
            )

            # ── 3. Lotto tracciabilità ─────────────────────────────────────────
            lotto_id = f"COL-{oggi.replace('-','')}-{prod_nome[:6].upper().replace(' ','')}"
            await db.lotti.update_one(
                {"lotto_id": lotto_id},
                {
                    "$set": {
                        "lotto_id": lotto_id,
                        "prodotto_nome": prod_nome,
                        "prodotto_id": prod_id,
                        "quantita": pezzi,
                        "unita": "pz",
                        "data_produzione": oggi,
                        "reparto": "pasticceria",
                        "fonte": "colazione",
                        "produzione_id": produzione_id,
                        "created_at": ora_now,
                    }
                },
                upsert=True,
            )

            # ── 4. Aggiorna contatore Acquaviva ────────────────────────────────
            await db.acquaviva_prodotti.update_one(
                {"id": prod_id}, {"$inc": {"pezzi_messi_in_vendita_totale": pezzi}}
            )

            registrati.append(
                {
                    "nome": prod_nome,
                    "pezzi": pezzi,
                    "prezzo_unitario": prezzo,
                    "valore_totale": round(prezzo * pezzi, 2),
                    "lotto_id": lotto_id,
                }
            )
        except Exception as e:
            errori.append({"nome": item.get("prodotto_nome"), "errore": str(e)})

    valore_totale = sum(r["valore_totale"] for r in registrati)
    pezzi_totali = sum(r["pezzi"] for r in registrati)

    # ── "Sta per finire" → sezione ordini centralizzata (richiesta Enzo 02/07) ──
    # Dopo aver mandato la colazione al banco, per ogni prodotto registrato si
    # calcola il residuo VERO in congelatore (consegne Vandemoortele − pezzi
    # mandati al banco, stesso motore del report /acquaviva/magazzino-congelatore).
    # Se resta MENO DI UN CARTONE (o è finito) parte la bozza riordino col
    # motore unico (per fornitore, dedup incrociata): l'admin la trova in
    # "Da inviare" per l'approvazione.
    riordini_colazione = []
    try:
        import math as _math
        from app.lotti.routers.acquaviva import calcola_magazzino_congelatore, _match_desc_banco
        from app.lotti.routers.ordini_fornitori import aggiungi_a_bozza_riordino
        cong = await calcola_magazzino_congelatore()
        for r in registrati:
            nome_b = r.get("nome") or ""
            righe = [pr for pr in cong.get("prodotti", [])
                     if _match_desc_banco(nome_b, pr.get("descrizione_fattura", ""))]
            if not righe:
                continue
            saldo = sum(int(pr.get("saldo") or 0) for pr in righe)
            pz_cart = max((int(pr.get("pz_cartone") or 0) for pr in righe), default=0)
            soglia = pz_cart if pz_cart > 0 else 10  # "sta per finire" = meno di un cartone
            if saldo > soglia:
                continue
            cartoni = max(1, _math.ceil((soglia * 2 - saldo) / pz_cart)) if pz_cart else 1
            esito = await aggiungi_a_bozza_riordino(
                nome=nome_b, prodotto_id="",
                quantita=cartoni, unita="cartone",
                richiesto_da="colazione (banco)",
                nota=(f"colazione: {'TERMINATO' if saldo <= 0 else 'sta per finire'} — "
                      f"restano {saldo} pz in congelatore"),
            )
            riordini_colazione.append({"nome": nome_b, "residuo_pezzi": saldo,
                                       "cartoni_in_bozza": cartoni,
                                       "gia_in_ordine": bool(esito.get("gia_in_ordine"))})
    except Exception:
        _LOG_INIT.debug("[colazione] check congelatore non bloccante")

    # Log colazione
    await db.colazione_log.insert_one(
        {
            "id": str(uuid.uuid4()),
            "data": oggi,
            "registrati": registrati,
            "errori": errori,
            "valore_totale": valore_totale,
            "pezzi_totali": pezzi_totali,
            "created_at": ora_now,
        }
    )

    return {
        "success": True,
        "data": oggi,
        "prodotti_registrati": len(registrati),
        "pezzi_totali": pezzi_totali,
        "valore_totale": valore_totale,
        "riordini_colazione": riordini_colazione,
        "registrati": registrati,
        "errori": errori,
    }


# ── GET: storico colazioni registrate ─────────────────────────────────────────
@router.get("/storico")
async def get_storico_colazioni(limit: int = 30):
    docs = (
        await db.colazione_log.find({}, {"_id": 0})
        .sort("created_at", -1)
        .limit(limit)
        .to_list(limit)
    )
    return docs


# ── GET: prodotti disponibili per colazione (tutti Acquaviva visibili) ─────────
@router.get("/prodotti-disponibili")
async def get_prodotti_disponibili(catalogo: bool = False, solo_acquistati: bool = True):
    from app.lotti.routers.fornitori_rivendita import fonti_attive, regex_fatture_attive
    fonti = await fonti_attive("colazione") or ["acquaviva", "vandemoortele"]
    fonti_regex = "|".join(fonti)

    # Mappa codice -> dati prodotti_vendita (id stabile, prezzo, foto, visibilità)
    pv = await db.prodotti_vendita.find(
        {"fonte": {"$regex": fonti_regex, "$options": "i"}},
        {"_id": 0, "id": 1, "nome": 1, "foto_url": 1, "categoria": 1,
         "prezzo_vendita": 1, "pezzi_cartone": 1, "codice_prodotto": 1, "visibile_tablet": 1},
    ).to_list(5000)
    pv_by_cod = {p.get("codice_prodotto"): p for p in pv if p.get("codice_prodotto")}

    # Insieme dei codici già acquistati via fattura (per il flag/filtro)
    acquistati = set()
    try:
        from app.lotti.routers.utils import prezzi_fatture_per_fornitore, applica_prezzo_da_fatture
        acq_all = await db.acquaviva_prodotti.find(
            {"fonte": {"$in": fonti}}, {"_id": 0, "codice": 1, "nome": 1}).to_list(5000)
        prezzi = await prezzi_fatture_per_fornitore(db, await regex_fatture_attive("colazione"))
        acq_all = applica_prezzo_da_fatture(acq_all, prezzi)
        acquistati = {p["codice"] for p in acq_all if p.get("gia_acquistato") and p.get("codice")}
    except Exception:
        _LOG_INIT.debug("[colazione] calcolo acquistati non bloccante")

    if catalogo:
        # MODO COMPOSIZIONE PRESET (regole Enzo 23/07/2026):
        #  - PRIMA i prodotti FATTI IN CASA, poi la scheda Acquaviva;
        #  - niente prodotti SALATI nella colazione di pasticceria (via le
        #    ricette di rosticceria e le categorie salate del catalogo);
        #  - di Acquaviva compaiono SOLO i prodotti già acquistati in fattura
        #    ("quelli non acquistati non farli comparire: tanto non potrei
        #    aggiungerli alla colazione").
        # ACQUISTI: oltre al motore prezzi (match per nome catalogo), si
        # riconoscono acquistati anche i prodotti presenti nelle RIGHE FATTURA
        # vere del Dizionario per i fornitori colazione (Enzo 23/07/2026:
        # "mancano molti prodotti Acquaviva che abbiamo comprato" — il match
        # per nome del motore ne perdeva parecchi). Chiave = prime 2 parole
        # significative del nome normalizzato.
        def _chiave2(nome: str) -> str:
            import unicodedata
            n = unicodedata.normalize("NFD", (nome or "").lower())
            n = n.encode("ascii", "ignore").decode()
            parole = [p for p in re.split(r"[^a-z0-9]+", n) if len(p) > 2]
            return " ".join(parole[:2])

        # CACHE 10 min (fix lentezza 23/07/2026): queste due scansioni (righe
        # dizionario + codici articolo di TUTTE le fatture colazione) pesano e
        # cambiano solo quando arrivano fatture nuove.
        import time as _time
        acquistati_nomi, codici_fattura = set(), set()
        if _CACHE_ACQUISTI["scade"] > _time.monotonic():
            acquistati_nomi = _CACHE_ACQUISTI["nomi"]
            codici_fattura = _CACHE_ACQUISTI["codici"]
        else:
            try:
                rx_forn = await regex_fatture_attive("colazione")
                async for d in db.dizionario_prodotti.find(
                    {"fornitore": {"$regex": rx_forn, "$options": "i"}},
                    {"_id": 0, "nome_originale": 1, "nome_normalizzato": 1},
                ):
                    k = _chiave2(d.get("nome_originale") or d.get("nome_normalizzato") or "")
                    if k:
                        acquistati_nomi.add(k)
                # MATCH PER CODICE ARTICOLO (23/07/2026, "mancano ancora molti
                # Acquaviva comprati"): il confronto per nome perde i prodotti
                # scritti diversamente tra listino e fattura — il codice
                # articolo delle righe fattura invece è esatto.
                async for f in db.fatture.find(
                    {"fornitore": {"$regex": rx_forn, "$options": "i"}},
                    {"_id": 0, "prodotti.codice_articolo": 1},
                ):
                    for p in f.get("prodotti") or []:
                        c = str(p.get("codice_articolo") or "").strip()
                        if c:
                            codici_fattura.add(c)
                _CACHE_ACQUISTI.update(nomi=acquistati_nomi, codici=codici_fattura,
                                       scade=_time.monotonic() + 600)
            except Exception:
                _LOG_INIT.debug("[colazione] match acquisti da dizionario/codici non bloccante")

        cat = await db.acquaviva_prodotti.find(
            {"fonte": {"$in": fonti}},
            {"_id": 0, "codice": 1, "nome": 1, "foto_url": 1, "categoria": 1},
        ).sort("nome", 1).to_list(5000)
        out = []
        for c in cat:
            cod = c.get("codice")
            pvp = pv_by_cod.get(cod) or {}
            nome_p = c.get("nome") or pvp.get("nome")
            comprato = (cod in acquistati or str(cod or "").strip() in codici_fattura
                        or _chiave2(nome_p) in acquistati_nomi)
            if solo_acquistati and not comprato:
                continue  # mai acquistato → fuori dalla composizione colazione
            categoria_p = c.get("categoria") or pvp.get("categoria")
            if _e_salato(categoria_p, nome_p):
                continue
            out.append({
                "id": pvp.get("id") or cod,  # id stabile: riusa quello di prodotti_vendita se esiste
                "nome": nome_p,
                "codice_prodotto": cod,
                "foto_url": c.get("foto_url") or pvp.get("foto_url"),
                "categoria": categoria_p,
                "prezzo_vendita": pvp.get("prezzo_vendita") or 0,
                "pezzi_cartone": pvp.get("pezzi_cartone"),
                "gia_acquistato": comprato,
                "fonte": "rivendita",
            })

        # Prodotti FATTI IN CASA — SOLO pasticceria (23/07/2026: i salati di
        # rosticceria non c'entrano con la colazione). "gia_acquistato": True
        # per non mostrare il fuorviante "mai acquistato" sui nostri prodotti.
        ricette_casa = await db.ricette.find(
            {"reparto": "pasticceria"},
            {"_id": 0, "id": 1, "nome": 1, "foto_url": 1, "reparto": 1, "prezzo_vendita": 1},
        ).to_list(2000)
        for r in ricette_casa:
            if _e_salato("", r.get("nome")):
                continue
            out.append({
                "id": r["id"],
                "nome": r.get("nome"),
                "codice_prodotto": None,
                "foto_url": r.get("foto_url"),
                "categoria": r.get("reparto"),
                "prezzo_vendita": r.get("prezzo_vendita") or 0,
                "pezzi_cartone": None,
                "gia_acquistato": True,
                "fonte": "casa",
            })

        # Ordine: prima i fatti in casa, poi Acquaviva; dentro ogni gruppo per nome
        out.sort(key=lambda p: (0 if p.get("fonte") == "casa" else 1,
                                (p.get("nome") or "").lower()))
        return out

    # MODO OPERATORE (default): solo prodotti visibili e già acquistati via XML.
    prodotti = [
        {k: p.get(k) for k in ("id", "nome", "foto_url", "categoria",
                               "prezzo_vendita", "pezzi_cartone", "codice_prodotto")}
        for p in pv if p.get("visibile_tablet") and p.get("codice_prodotto") in acquistati
    ]
    prodotti.sort(key=lambda x: (x.get("nome") or ""))

    # Arricchisci con foto/categoria da acquaviva_prodotti
    if prodotti:
        codici = [p.get("codice_prodotto") for p in prodotti if p.get("codice_prodotto")]
        acq_prods = await db.acquaviva_prodotti.find(
            {"codice": {"$in": codici}},
            {"_id": 0, "codice": 1, "foto_url": 1, "categoria": 1},
        ).to_list(5000)
        foto_map = {ap["codice"]: ap.get("foto_url") for ap in acq_prods if ap.get("foto_url")}
        cat_map = {ap["codice"]: ap.get("categoria") for ap in acq_prods if ap.get("categoria")}
        for p in prodotti:
            cod = p.get("codice_prodotto")
            if cod and not p.get("foto_url") and cod in foto_map:
                p["foto_url"] = foto_map[cod]
            if cod and not p.get("categoria") and cod in cat_map:
                p["categoria"] = cat_map[cod]

    return prodotti


@router.post("/popola-quattro-stagioni")
async def popola_quattro_stagioni(_admin=Depends(require_admin)):
    """Aggiunge a tutte le stagioni ogni prodotto dolce realmente acquistato.

    L'operazione e idempotente: non cambia quantita, stato o metadati degli
    elementi gia regolati manualmente. I prodotti fatti in casa non vengono
    inseriti automaticamente, perche la richiesta riguarda gli acquisti da
    fattura/catalogo. Una successiva esecuzione aggiunge solo nuovi acquisti.
    """
    await lista_preset()
    disponibili = await get_prodotti_disponibili(catalogo=True, solo_acquistati=True)
    acquistati_per_id = {
        str(p["id"]): p for p in disponibili
        if p.get("fonte") == "rivendita" and p.get("gia_acquistato") is True and p.get("id")
    }
    acquistati = list(acquistati_per_id.values())
    now = datetime.now(timezone.utc).isoformat()
    aggiunti_per_stagione = {}
    for stagione in _STAGIONI_DEFAULT:
        preset = await db.colazione_template.find_one({"nome": stagione}) or {}
        items = list(preset.get("items") or [])
        presenti = {str(x.get("prodotto_id")) for x in items if x.get("prodotto_id")}
        aggiunti = 0
        for prodotto in acquistati:
            pid = str(prodotto["id"])
            if pid in presenti:
                continue
            items.append({
                "prodotto_id": pid,
                "prodotto_nome": prodotto.get("nome") or "Prodotto acquistato",
                "pezzi": 6,
                "foto_url": prodotto.get("foto_url"),
                "categoria": prodotto.get("categoria"),
                "prezzo_vendita": prodotto.get("prezzo_vendita") or 0,
                "attivo": True,
                "fonte": "fatture_cataloghi",
            })
            presenti.add(pid)
            aggiunti += 1
            await db.colazione_preferiti.update_one(
                {"prodotto_id": pid},
                {"$setOnInsert": {
                    "prodotto_id": pid,
                    "prodotto_nome": prodotto.get("nome"),
                    "created_at": now,
                    "origine": "popolamento_acquisti",
                }},
                upsert=True,
            )
        if aggiunti:
            await db.colazione_template.update_one(
                {"nome": stagione},
                {"$set": {"items": items, "ultima_modifica": now}},
            )
        aggiunti_per_stagione[stagione] = aggiunti

    return {
        "ok": True,
        "prodotti_acquistati": len(acquistati),
        "aggiunti_per_stagione": aggiunti_per_stagione,
        "totale_aggiunte": sum(aggiunti_per_stagione.values()),
        "quantita_predefinita": 6,
    }
