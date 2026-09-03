"""
magazzino_unificato.py
Endpoint per il magazzino unificato:
- magazzino_bar_prodotti (bar: caffè, bibite, monouso…)
- lotti_fornitori (materie prime da import XML: farine, latticini…)
Permette scarico da entrambe le fonti con tracciabilità operatore.
"""

import uuid
from datetime import datetime, timezone, date
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.lotti.db import database as db

import unicodedata as _ud
import re as _re
from app.lotti.routers.unita_misura import normalizza_unita_display

from app.lotti.routers.classificatore_alimenti import (
    e_alimento as _e_alimento,
    strip_accents as _strip_accents,
)

router = APIRouter(prefix="/magazzino", tags=["Magazzino Unificato"])

# ── Categorizzazione automatica prodotti fornitore ────────────────────────────
CATEGORIE_FORNITORI = {
    "Farine/Cereali": [
        "farin",
        "semola",
        "grano",
        "frumento",
        "cereali",
        "orzo",
        "segale",
        "amido",
    ],
    "Latticini": [
        "burro",
        "latte",
        "panna",
        "formaggio",
        "mozzarella",
        "ricotta",
        "mascarpone",
        "lattosio",
    ],
    "Creme/Paste": [
        "crema",
        "pasta pistacchi",
        "pasta nocc",
        "nuppy",
        "ripieno",
        "farcia",
        "confettura",
        "marmellata",
    ],
    "Cioccolato": ["cioccolato", "cacao", "glassa", "copertura", "fondente", "ganache"],
    "Zuccheri": ["zucchero", "glucosio", "fruttosio", "sciroppo", "destrosio", "maltosio"],
    "Lieviti": ["lievito", "bicarbonato", "cremortartaro", "agente lievit"],
    "Oli/Grassi": ["olio", "margarina", "strutto", "grasso vegetale", "shortening"],
    "Uova": ["uov", "tuorlo", "albume", "ovoprodot"],
    "Frutta/Noci": ["nocciola", "mandorla", "pistacchio", "noce", "pinoli", "uvetta", "canditi"],
    "Carni/Salumi": [
        "carne",
        "salume",
        "prosciutto",
        "speck",
        "salsiccia",
        "mortadella",
        "pancetta",
    ],
    "Verdure": ["pomodoro", "cipolla", "aglio", "basilico", "funghi", "carciofo"],
    "Beveraggi": ["coca", "acqua", "succo", "birra", "vino", "prosecco", "sprite", "fanta"],
    "Pulizia": ["detersivo", "detergente", "sanificante", "disinfettante", "candeggina"],
    "Imballaggi": [
        "vaschett",
        "scatol",
        "involucr",
        "sacchetto",
        "contenitor",
        "pellicola",
        "carta",
    ],
}


async def _carica_soglie() -> dict:
    """Scorte minime materie prime, per nome normalizzato. FONTE UNICA:
    dizionario_prodotti.scorta_minima — lo stesso campo usato dai riordini §7
    (/ordini-fornitori/prodotti-suggeriti). Così display magazzino e riordini
    condividono un solo dato (§0/§2/§7), senza store soglie paralleli."""
    docs = await db.dizionario_prodotti.find(
        {"scorta_minima": {"$gt": 0}}, {"_id": 0, "nome_normalizzato": 1, "scorta_minima": 1}
    ).to_list(5000)
    return {
        (d.get("nome_normalizzato") or "").strip(): float(d.get("scorta_minima") or 0)
        for d in docs
        if d.get("nome_normalizzato")
    }


def _categoria_da_nome(nome: str) -> str:
    n = nome.lower()
    for cat, keywords in CATEGORIE_FORNITORI.items():
        if any(k in n for k in keywords):
            return cat
    return "Altro"


# ── Cartoni → pezzi (richiesta Enzo 23/07/2026) ───────────────────────────────
# In fattura le bevande arrivano a CARTONI ("1 CT di COCA COLA VAP CL 33 X 24"):
# il numero di pezzi per cartone è già scritto NEL NOME (X 24, CTX24, 24X33CL).
# In magazzino la giacenza va mostrata in PEZZI (cartoni × pezzi/cartone), non
# in cartoni. Nel DB i lotti restano in cartoni (nessuna migrazione dati): la
# conversione è simmetrica in lettura (qui) e in scarico (più sotto).
_UNITA_COLLO = {"CT", "CARTONE", "CARTONI", "COLLO", "COLLI", "CF", "CONF",
                "CS", "CASSA", "CASSE", "BOX", "FARDELLO", "FD"}
_RX_PPC_DOPO_MISURA = _re.compile(
    r"(?:CL|LT|ML|GR|KG|L|G)\s*\.?\s*\d+(?:[.,]\d+)?\s*(?:CT|CF|CS)?\s*X\s*(\d{1,3})\b", _re.I)
_RX_PPC_PRIMA_MISURA = _re.compile(
    r"\b(\d{1,3})\s*X\s*\d+(?:[.,]\d+)?\s*(?:CL|LT|ML|GR|KG|L|G)\b", _re.I)
_RX_PPC_FINE = _re.compile(r"\bX\s*(\d{1,3})\s*$")


def pezzi_per_collo(nome: str) -> int:
    """Pezzi per cartone letti dal nome prodotto: 'CL 33 X 24'→24,
    'PET CL.50 CTX24'→24, '24X33CL'→24. 0 se non deducibile."""
    n = (nome or "").upper()
    for rx in (_RX_PPC_DOPO_MISURA, _RX_PPC_PRIMA_MISURA, _RX_PPC_FINE):
        m = rx.search(n)
        if m:
            try:
                v = int(m.group(1))
                if 2 <= v <= 200:
                    return v
            except ValueError:
                pass
    return 0


def _fattore_collo(doc: dict) -> int:
    """Fattore di conversione cartoni→pezzi per un lotto fornitore (0 = nessuna
    conversione: unità non a collo o pezzi/cartone non deducibile dal nome)."""
    raw_u = str(doc.get("unita_misura") or "").upper().strip().rstrip(".")
    if raw_u not in _UNITA_COLLO:
        return 0
    return pezzi_per_collo(doc.get("prodotto_nome") or doc.get("prodotto_nome_norm") or "")


# Il nome prodotto in fattura a volte porta appesi PREZZI e sconti
# ("... | -Prezzo: 28.80 Sconti: 33.50 22.00 #DE#"): in magazzino i prezzi
# d'acquisto NON devono vedersi (richiesta Enzo 23/07/2026: il dipendente non
# deve saperli). Si pulisce SOLO il nome mostrato, i dati restano intatti.
_RX_NOME_PREZZI = _re.compile(
    r"\s*[|·]?\s*-?\s*(prezzo|sconti|sconto|listino)\s*:.*$", _re.I)
_RX_NOME_MARKER = _re.compile(r"\s*#[A-Z0-9]{1,6}#\s*$")


def _pulisci_nome_display(nome: str) -> str:
    n = _RX_NOME_PREZZI.sub("", str(nome or ""))
    n = _RX_NOME_MARKER.sub("", n)
    return n.strip(" |·-") or str(nome or "—")


def _unifica_lotto(doc: dict) -> dict:
    """Converte un doc lotti_fornitori nel formato unificato."""
    nome = _pulisci_nome_display(doc.get("prodotto_nome") or doc.get("prodotto_nome_norm") or "—")
    stock = float(doc.get("quantita_disponibile") or 0)
    unita = normalizza_unita_display(doc.get("unita_misura"), "KG")
    ppc = _fattore_collo(doc)
    colli = None
    if ppc > 0:
        colli = stock
        stock = round(stock * ppc, 3)
        unita = "PZ"
    return {
        "id": doc.get("id", ""),
        "source": "fornitori",
        "nome": nome,
        "categoria": _categoria_da_nome(nome),
        "stock": stock,
        "unita": unita,
        "colli": colli,
        "pezzi_per_collo": ppc or None,
        "fornitore": doc.get("fornitore", ""),
        "data_scadenza": doc.get("data_scadenza", ""),
        "giorni_alla_scadenza": doc.get("giorni_alla_scadenza"),
        "scaduto": doc.get("scaduto", False),
        "lotto_id": doc.get("lotto_id_fornitore", ""),
        "allergeni_testo": doc.get("allergeni_testo", ""),
        "soglia_minima": 0,
    }


def _unifica_bar(doc: dict) -> dict:
    """Converte un doc magazzino_bar_prodotti nel formato unificato."""
    return {
        "id": doc.get("id", ""),
        "source": "bar",
        "nome": doc.get("nome", ""),
        "categoria": doc.get("categoria", "Bar"),
        "stock": float(doc.get("stock") or 0),
        "unita": normalizza_unita_display(doc.get("unita")),
        "fornitore": doc.get("fornitore", ""),
        "data_scadenza": "",
        "giorni_alla_scadenza": None,
        "scaduto": False,
        "lotto_id": "",
        "allergeni_testo": "",
        "soglia_minima": float(doc.get("soglia_minima") or 0),
    }


# ── GET prodotti unificati ─────────────────────────────────────────────────────
CATEGORIE_SELEZIONABILI = [
    "Farine/Cereali", "Latticini", "Uova", "Oli/Grassi", "Zuccheri", "Cioccolato",
    "Creme/Paste", "Frutta/Noci", "Verdure", "Carni/Salumi", "Lieviti", "Beveraggi",
    "Imballaggi", "Pulizia", "Altro",
]

async def _overrides_map():
    """Mappa key -> override {visualizza, categoria, nome_norm}."""
    docs = await db.magazzino_overrides.find({}, {"_id": 0}).to_list(5000)
    return {d["key"]: d for d in docs if d.get("key")}

def _applica_override(u: dict, ov: dict):
    """Applica nome normalizzato e categoria scelti manualmente."""
    if ov:
        if ov.get("nome_norm"):
            u["nome"] = ov["nome_norm"]
        if ov.get("categoria"):
            u["categoria"] = ov["categoria"]
    return u

def _visibile(u: dict, ov: dict) -> bool:
    """Il flag manuale ha priorità sul rilevamento automatico alimenti."""
    if ov and ov.get("visualizza") is not None:
        return bool(ov["visualizza"])
    return _e_alimento(u["nome"], u.get("categoria", ""))


@router.get("/prodotti-unificati")
async def prodotti_unificati(
    categoria: Optional[str] = None,
    source: Optional[str] = None,
    search: Optional[str] = None,
    solo_disponibili: bool = False,  # default false: mostra anche stock zero
    gestione: bool = False,          # True = vista gestione admin: mostra TUTTO (anche non-food) per poterlo flaggare
    anno: Optional[int] = None,      # giacenze per anno di fatturazione (23/07/2026): solo lotti da fatture di quell'anno
):
    items = []
    ov_map = await _overrides_map()

    # ── Bar — se vuota esegui seed automatico ────────────────────────────────
    # Con `anno` impostato il bar si salta: lo stock bar non ha un anno di
    # fatturazione, la vista per anno riguarda solo i lotti da fattura.
    if source in (None, "bar") and not anno:
        bar_count = await db.magazzino_bar_prodotti.count_documents({})
        if bar_count == 0:
            from app.lotti.routers.magazzino_bar import seed_magazzino_bar

            await seed_magazzino_bar()

        bar_docs = await db.magazzino_bar_prodotti.find({}, {"_id": 0}).to_list(500)
        for d in bar_docs:
            u = _unifica_bar(d)
            k = _strip_accents(u["nome"])
            ov = ov_map.get(k)
            u = _applica_override(u, ov)
            u["key"] = k
            if not gestione:
                if solo_disponibili and u["stock"] <= 0:
                    continue
                if not _visibile(u, ov):
                    continue
            items.append(u)

    # ── Fornitori (lotti_fornitori) — tutti, non solo stock > 0 ──────────────
    if source in (None, "fornitori"):
        q = {"esaurito": {"$ne": True}}
        if anno and anno > 0:
            # data_fattura in formati misti: ISO (anno in testa) o dd/mm/yyyy
            y = str(int(anno))
            q["$or"] = [
                {"data_fattura": {"$regex": f"^{y}[-/]"}},
                {"data_fattura": {"$regex": f"[-/]{y}"}},
            ]
        # PROIEZIONE (fix timeout 23/07/2026): i doc lotti_fornitori portano
        # anche storico_utilizzi e campi pesanti — scaricarli TUTTI interi
        # (fino a 5000) mandava la richiesta oltre i 15s. Qui servono solo
        # questi campi.
        _proj = {"_id": 0, "id": 1, "prodotto_nome": 1, "prodotto_nome_norm": 1,
                 "quantita_disponibile": 1, "unita_misura": 1, "fornitore": 1,
                 "data_scadenza": 1, "giorni_alla_scadenza": 1, "scaduto": 1,
                 "lotto_id_fornitore": 1, "allergeni_testo": 1, "data_fattura": 1}
        lotti = await db.lotti_fornitori.find(q, _proj).to_list(8000)
        # Raggruppa per prodotto (nome normalizzato): un prodotto = una riga, non un lotto = una riga.
        gruppi = {}
        for d in lotti:
            u = _unifica_lotto(d)
            k = (d.get("prodotto_nome_norm") or _strip_accents(u["nome"])).strip()
            ov = ov_map.get(k)
            u = _applica_override(u, ov)
            u["key"] = k
            if not gestione:
                if not _visibile(u, ov):   # flag manuale o auto-alimenti
                    continue
                if solo_disponibili and u["stock"] <= 0:
                    continue
            g = gruppi.get(k)
            dfatt = str(d.get("data_fattura") or "")
            if g is None:
                u = dict(u)
                u["n_lotti"] = 1
                u["_fifo_data"] = dfatt
                u["_fifo_id"] = u["id"]
                u["_fifo_lotto"] = u["lotto_id"]
                gruppi[k] = u
            else:
                g["stock"] = round(g["stock"] + u["stock"], 3)
                if u.get("colli") is not None:
                    g["colli"] = round((g.get("colli") or 0) + u["colli"], 3)
                    g["pezzi_per_collo"] = g.get("pezzi_per_collo") or u.get("pezzi_per_collo")
                g["n_lotti"] += 1
                # scadenza: tieni la più vicina
                gd = g.get("giorni_alla_scadenza")
                ud = u.get("giorni_alla_scadenza")
                if ud is not None and (gd is None or ud < gd):
                    g["giorni_alla_scadenza"] = ud
                    g["data_scadenza"] = u["data_scadenza"]
                # FIFO: lotto/id con data_fattura più vecchia (per lo scarico)
                if dfatt and (not g["_fifo_data"] or dfatt < g["_fifo_data"]):
                    g["_fifo_data"] = dfatt
                    g["_fifo_id"] = u["id"]
                    g["_fifo_lotto"] = u["lotto_id"]
        soglie = await _carica_soglie()
        for g in gruppi.values():
            # lo scarico FIFO consuma il lotto più vecchio
            g["id"] = g.get("_fifo_id", g["id"])
            g["lotto_id"] = g.get("_fifo_lotto", g.get("lotto_id", ""))
            g["key"] = g.get("key") or _strip_accents(g["nome"])
            # §4/§7: scorta minima per materia prima (fonte unica dizionario_prodotti)
            g["soglia_minima"] = float(soglie.get(g["key"], 0) or 0)
            g.pop("_fifo_data", None); g.pop("_fifo_id", None); g.pop("_fifo_lotto", None)
            items.append(g)

    # ── Filtri ────────────────────────────────────────────────────────────────
    if search:
        sa = _strip_accents(search)
        items = [
            i for i in items
            if sa in _strip_accents(i["nome"])
            or sa in _strip_accents(i["fornitore"])
            or sa in _strip_accents(i["categoria"])
        ]
    if categoria and categoria != "tutti":
        items = [i for i in items if i["categoria"] == categoria]

    # Ordina: sotto soglia prima (bar e materie prime), poi categoria, poi nome
    items.sort(
        key=lambda x: (
            (0 if (x["soglia_minima"] > 0 and x["stock"] < x["soglia_minima"]) else 1),
            0 if (x["giorni_alla_scadenza"] is not None and x["giorni_alla_scadenza"] < 14) else 1,
            x["categoria"],
            x["nome"],
        )
    )
    return items


# ── GET categorie ──────────────────────────────────────────────────────────────
@router.get("/categorie")
async def categorie_magazzino():
    bar_cats = await db.magazzino_bar_prodotti.distinct("categoria")
    forn_cats = list(CATEGORIE_FORNITORI.keys()) + ["Altro"]
    all_cats = sorted(set(bar_cats + forn_cats))
    return {"categorie": all_cats}


# ── GET movimenti oggi ─────────────────────────────────────────────────────────
@router.get("/movimenti-oggi")
async def movimenti_oggi():
    oggi = date.today().isoformat()
    # Movimenti bar
    bar_movs = (
        await db.magazzino_bar_movimenti.find({"data": {"$regex": f"^{oggi}"}}, {"_id": 0})
        .sort("data", -1)
        .to_list(300)
    )
    # Movimenti fornitori
    forn_movs = (
        await db.magazzino_movimenti_fornitori.find({"data": {"$regex": f"^{oggi}"}}, {"_id": 0})
        .sort("data", -1)
        .to_list(300)
    )

    tutti = [{"source_tipo": "bar", **m} for m in bar_movs] + [
        {"source_tipo": "fornitori", **m} for m in forn_movs
    ]
    tutti.sort(key=lambda x: x.get("data", ""), reverse=True)
    return tutti


# ── Modelli ────────────────────────────────────────────────────────────────────
def _norm_txt(s):
    s = _ud.normalize("NFD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return _re.sub(r"[^a-z0-9]+", " ", s).strip()


@router.get("/movimenti")
async def movimenti_storico(
    q: Optional[str] = None,
    operatore: Optional[str] = None,
    tipo: Optional[str] = None,
    dal: Optional[str] = None,
    al: Optional[str] = None,
    limit: int = 400,
):
    """Storico movimenti del magazzino unificato (bar + materie prime) per il
    controllo: chi ha preso cosa e quando. Filtri: nome prodotto (q),
    operatore, tipo (carico/scarico), periodo (dal/al in formato YYYY-MM-DD)."""
    base = {}
    if tipo in ("carico", "scarico"):
        base["tipo"] = tipo
    if dal or al:
        rng = {}
        if dal:
            rng["$gte"] = f"{dal}T00:00:00"
        if al:
            rng["$lte"] = f"{al}T23:59:59.999999"
        base["data"] = rng
    bar = await db.magazzino_bar_movimenti.find(base, {"_id": 0}).sort("data", -1).to_list(3000)
    forn = await db.magazzino_movimenti_fornitori.find(base, {"_id": 0}).sort("data", -1).to_list(3000)
    for m in bar:
        m["fonte"] = "bar"
    for m in forn:
        m["fonte"] = "fornitori"
    tutti = bar + forn

    nq = _norm_txt(q) if q else ""
    no = _norm_txt(operatore) if operatore else ""

    def _keep(m):
        if nq and nq not in _norm_txt(m.get("prodotto_nome", "")):
            return False
        if no and no not in _norm_txt(m.get("operatore_nome", "")):
            return False
        return True

    movs = [m for m in tutti if _keep(m)]
    movs.sort(key=lambda m: m.get("data", ""), reverse=True)

    operatori = sorted({m.get("operatore_nome", "") for m in tutti if m.get("operatore_nome")})
    n_scarico = sum(1 for m in movs if m.get("tipo") == "scarico")
    n_carico = sum(1 for m in movs if m.get("tipo") == "carico")
    return {
        "movimenti": movs[:limit],
        "totale": len(movs),
        "n_scarico": n_scarico,
        "n_carico": n_carico,
        "operatori": operatori,
    }


class ScaricoPayload(BaseModel):
    prodotto_id: str
    source: str  # "bar" | "fornitori"
    quantita: float
    operatore_nome: str
    nota: Optional[str] = ""


# ── POST scarico unificato ─────────────────────────────────────────────────────
@router.post("/scarico")
async def scarico_unificato(payload: ScaricoPayload):
    now = datetime.now(timezone.utc).isoformat()
    mov_id = str(uuid.uuid4())

    if payload.source == "bar":
        # UNICA logica di scarico bar: delega a magazzino_bar.scarico
        from app.lotti.routers.magazzino_bar import scarico as scarico_bar, MovimentoScarico
        return await scarico_bar(MovimentoScarico(
            prodotto_id=payload.prodotto_id,
            quantita=payload.quantita,
            unita_movimento="pezzo",
            operatore_nome=payload.operatore_nome,
            nota=payload.nota or "",
        ))

    elif payload.source == "fornitori":
        lotto = await db.lotti_fornitori.find_one({"id": payload.prodotto_id}, {"_id": 0})
        if not lotto:
            raise HTTPException(404, "Lotto fornitore non trovato")

        # Conversione SIMMETRICA cartoni→pezzi (23/07/2026): la lista mostra i
        # PEZZI (cartoni × pezzi/cartone dal nome), quindi l'operatore scarica
        # in pezzi — ma nel DB i lotti restano in cartoni. Qui si riconverte.
        def _fatt_di(c: dict) -> float:
            """Pezzi per collo del SINGOLO lotto (dal nome riga fattura)."""
            f = _fattore_collo(c)
            return f if f > 0 else 1

        _fatt = _fatt_di(lotto)
        _unita_mov = "PZ" if _fatt > 1 else normalizza_unita_display(lotto.get("unita_misura"), "KG")

        # §4 FIFO a cascata: la lista raggruppa i lotti per prodotto_nome_norm e
        # mostra lo stock TOTALE. Lo scarico deve poter consumare oltre il singolo
        # lotto più vecchio, scalando in ordine di data_fattura (più vecchia prima)
        # tutti i lotti dello stesso prodotto, a prescindere dal fornitore.
        from app.lotti.routers.lotti_produzione import _parse_data_fattura

        nome_norm = (lotto.get("prodotto_nome_norm") or "").strip()
        if nome_norm:
            candidati = await db.lotti_fornitori.find(
                {
                    "prodotto_nome_norm": nome_norm,
                    "esaurito": {"$ne": True},
                    "quantita_disponibile": {"$gt": 0},
                },
                {"_id": 0},
            ).to_list(1000)
        else:
            candidati = [lotto]
        if not candidati:
            candidati = [lotto]

        # FIX 25/07/2026 (audit quantità/unità §2): la cascata usava il fattore
        # collo del SOLO lotto cliccato anche sui fratelli. Con lotti dello
        # stesso prodotto a confezionamento diverso (X24 e X12) si scaricava la
        # quantità sbagliata dai fratelli. Ora ogni lotto usa il PROPRIO fattore
        # e i lotti non confrontabili (es. sfuso a kg quando la lista mostra
        # pezzi) restano fuori dalla cascata invece di essere mal convertiti.
        if _fatt > 1:
            candidati = [c for c in candidati if _fatt_di(c) > 1]
        else:
            candidati = [
                c for c in candidati
                if _fatt_di(c) == 1
                and normalizza_unita_display(c.get("unita_misura"), "KG") == _unita_mov
            ]
        if not candidati:
            candidati = [lotto]

        # Si ragiona SEMPRE nell'unità mostrata all'operatore (pezzi, oppure
        # kg/lt per lo sfuso): ogni lotto ci arriva con il suo fattore.
        disponibile_totale = sum(
            float(c.get("quantita_disponibile") or 0) * _fatt_di(c) for c in candidati
        )
        if payload.quantita > disponibile_totale + 0.001:
            raise HTTPException(
                400,
                f"Quantità disponibile: {round(disponibile_totale, 3)} {_unita_mov}",
            )

        candidati.sort(
            key=lambda c: (_parse_data_fattura(c.get("data_fattura")), c.get("data_scadenza") or "9999")
        )

        rimasta = payload.quantita
        consumati = []
        for c in candidati:
            if rimasta <= 0.0001:
                break
            fatt_c = _fatt_di(c)
            disp = float(c.get("quantita_disponibile") or 0) * fatt_c
            da_consumare = min(disp, rimasta)
            nuovo = round((disp - da_consumare) / fatt_c, 4)
            esaurito = nuovo <= 0.0001
            await db.lotti_fornitori.update_one(
                {"id": c["id"]},
                {"$set": {"quantita_disponibile": nuovo, "esaurito": esaurito, "updated_at": now}},
            )
            rimasta = round(rimasta - da_consumare, 4)
            m = {
                "id": str(uuid.uuid4()),
                "prodotto_id": c.get("id", ""),
                "prodotto_nome": c.get("prodotto_nome", ""),
                "prodotto_nome_norm": nome_norm,
                # il movimento si registra in PEZZI quando la lista mostra pezzi
                "unita": _unita_mov,
                "tipo": "scarico",
                # da_consumare è GIÀ nell'unità mostrata (pezzi o kg): niente
                # secondo passaggio col fattore del lotto cliccato.
                "quantita": round(da_consumare, 3),
                "operatore_nome": payload.operatore_nome,
                "nota": payload.nota or "",
                "fornitore": c.get("fornitore", ""),
                "lotto_id": c.get("lotto_id_fornitore", ""),
                "metodo": "fifo",
                "data": now,
            }
            await db.magazzino_movimenti_fornitori.insert_one({**m})
            m.pop("_id", None)
            consumati.append(m)

        stock_residuo = round(disponibile_totale - payload.quantita, 3)
        return {
            "ok": True,
            "stock_nuovo": stock_residuo,
            "esaurito": stock_residuo <= 0.001,
            "lotti_consumati": consumati,
            "movimento": consumati[0] if consumati else None,
        }

    raise HTTPException(400, "source deve essere 'bar' o 'fornitori'")


# ── GESTIONE PRODOTTI (sezione centralizzata admin) ─────────────────────────────
_GESTIONE_CACHE = {"dati": None, "scade": 0.0}


@router.get("/gestione-prodotti")
async def gestione_prodotti(search: Optional[str] = None):
    import time as _time
    if not search and _GESTIONE_CACHE["dati"] is not None and _time.monotonic() < _GESTIONE_CACHE["scade"]:
        return _GESTIONE_CACHE["dati"]
    """Lista COMPLETA dei prodotti (bar + fornitori), anche non alimentari, per la sezione
    di gestione: ogni riga mostra nome originale, nome normalizzato (override), categoria,
    e se è visibile in magazzino. Raggruppata per prodotto."""
    base = await prodotti_unificati(gestione=True)
    ov_map = await _overrides_map()
    out = []
    visti = set()
    for u in base:
        k = u.get("key") or _strip_accents(u["nome"])
        if k in visti:
            continue
        visti.add(k)
        ov = ov_map.get(k, {})
        auto_food = _e_alimento(u.get("nome", ""), u.get("categoria", ""))
        out.append({
            "key": k,
            "nome_originale": ov.get("nome_originale") or u["nome"],
            "nome_norm": ov.get("nome_norm") or "",
            "nome_visualizzato": ov.get("nome_norm") or u["nome"],
            "categoria": u.get("categoria", "Altro"),
            "categoria_auto": _categoria_da_nome(u["nome"]) if u.get("source") == "fornitori" else u.get("categoria", "Altro"),
            "source": u.get("source", ""),
            "fornitore": u.get("fornitore", ""),
            "stock": u.get("stock", 0),
            "unita": normalizza_unita_display(u.get("unita")),
            "visualizza": (ov.get("visualizza") if ov.get("visualizza") is not None else auto_food),
            "override_manuale": bool(ov),
        })
    if search:
        sa = _strip_accents(search)
        out = [o for o in out if sa in _strip_accents(o["nome_originale"]) or sa in _strip_accents(o["nome_visualizzato"]) or sa in _strip_accents(o["fornitore"]) or sa in _strip_accents(o["categoria"])]
    out.sort(key=lambda o: (0 if o["visualizza"] else 1, o["categoria"], o["nome_visualizzato"].lower()))
    risultato = {"prodotti": out, "totale": len(out), "categorie": CATEGORIE_SELEZIONABILI}
    if not search:
        _GESTIONE_CACHE["dati"] = risultato
        _GESTIONE_CACHE["scade"] = _time.monotonic() + 120
    return risultato


class OverridePayload(BaseModel):
    key: str
    nome_originale: Optional[str] = None
    visualizza: Optional[bool] = None
    categoria: Optional[str] = None
    nome_norm: Optional[str] = None


@router.post("/override-prodotto")
async def salva_override(payload: OverridePayload):
    """Salva (upsert) il flag visualizza/categoria/nome normalizzato per un prodotto del magazzino."""
    key = (payload.key or "").strip()
    if not key:
        raise HTTPException(400, "key mancante")
    campi = {"key": key, "updated_at": datetime.now(timezone.utc).isoformat()}
    if payload.nome_originale is not None:
        campi["nome_originale"] = payload.nome_originale
    if payload.visualizza is not None:
        campi["visualizza"] = bool(payload.visualizza)
    if payload.categoria is not None:
        campi["categoria"] = payload.categoria or None
    if payload.nome_norm is not None:
        campi["nome_norm"] = payload.nome_norm.strip() or None
    await db.magazzino_overrides.update_one({"key": key}, {"$set": campi}, upsert=True)
    doc = await db.magazzino_overrides.find_one({"key": key}, {"_id": 0})
    return {"ok": True, "override": doc}


class ResetPayload(BaseModel):
    key: str


@router.post("/reset-override")
async def reset_override(payload: ResetPayload):
    """Rimuove l'override (robusto anche con key che contengono / o caratteri speciali)."""
    r = await db.magazzino_overrides.delete_one({"key": payload.key})
    return {"ok": True, "rimossi": r.deleted_count}


@router.get("/lista-override")
async def lista_override():
    docs = await db.magazzino_overrides.find({}, {"_id": 0}).to_list(5000)
    return {"override": docs, "totale": len(docs)}


@router.delete("/override-prodotto/{key}")
async def azzera_override(key: str):
    """Rimuove l'override: il prodotto torna alla classificazione automatica."""
    r = await db.magazzino_overrides.delete_one({"key": key})
    return {"ok": True, "rimossi": r.deleted_count}


# ── Soglie di scorta materie prime (§4/§7) ─────────────────────────────────────
# Fonte unica: dizionario_prodotti.scorta_minima (condivisa con i riordini §7).
class SogliaPayload(BaseModel):
    prodotto_nome_norm: str
    soglia_minima: float


@router.get("/soglie")
async def get_soglie():
    """Elenco delle scorte minime impostate (da dizionario_prodotti)."""
    docs = await db.dizionario_prodotti.find(
        {"scorta_minima": {"$gt": 0}},
        {"_id": 0, "nome_normalizzato": 1, "nome_canonico": 1, "scorta_minima": 1},
    ).sort("nome_normalizzato", 1).to_list(5000)
    return [
        {
            "prodotto_nome_norm": d.get("nome_normalizzato", ""),
            "nome": d.get("nome_canonico") or d.get("nome_normalizzato", ""),
            "soglia_minima": float(d.get("scorta_minima") or 0),
        }
        for d in docs
    ]


@router.put("/soglia")
async def set_soglia(payload: SogliaPayload):
    """Imposta (o azzera con <=0) la scorta minima di una materia prima per nome
    normalizzato, su dizionario_prodotti.scorta_minima (fonte unica §4/§7)."""
    nome_norm = (payload.prodotto_nome_norm or "").strip()
    if not nome_norm:
        raise HTTPException(400, "prodotto_nome_norm obbligatorio")
    valore = max(0.0, float(payload.soglia_minima))
    await db.dizionario_prodotti.update_one(
        {"nome_normalizzato": nome_norm},
        {
            "$set": {
                "scorta_minima": valore,
                "scorta_minima_updated_at": datetime.now(timezone.utc).isoformat(),
            }
        },
        upsert=True,
    )
    return {"ok": True, "prodotto_nome_norm": nome_norm, "soglia_minima": valore}

