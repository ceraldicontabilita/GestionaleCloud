"""
prodotti_master.py — Catalogo prodotti UNIFICATO

Aggrega 6 fonti dati in una sola collezione (`prodotti_master`):
  - fatture.prodotti (descrizione + prezzo + codice + fornitore)
  - acquaviva_prodotti (codice + prezzo_singolo)
  - prodotti_vendita (catalogo banco)
  - magazzino_bar_prodotti (bevande/caffè)
  - listino_prodotti (listini ricevuti)
  - prodotti_canonici (categoria + unità misura)

Ogni prodotto ha:
  - nome_canonico       : nome leggibile principale
  - key                 : chiave normalizzata (lowercase, no numeri/unità)
  - aliases[]           : tutti i nomi raw incontrati
  - codici[]            : codici prodotto/articolo
  - fornitori[]         : fornitori che lo vendono
  - categorie[]         : tassonomie
  - fonti[]             : ["fattura","acquaviva",...]
  - prezzi_storici[]    : ultimi 5 prezzi con data e fonte
  - ultimo_prezzo       : prezzo più recente
  - totale_apparizioni  : count complessivo

ENDPOINT:
  GET  /api/prodotti-master                        — lista paginata + filtri
  GET  /api/prodotti-master/{id}                   — singolo
  GET  /api/prodotti-master/cerca?q=               — fuzzy search
  POST /api/prodotti-master/rebuild                — ricostruisce la collezione (admin)
  GET  /api/prodotti-master/stats                  — distribuzione per fonte
"""

import re
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Query, HTTPException, BackgroundTasks, Body
from app.lotti.db import database as db
from app.lotti.dizionario_categorie import classifica

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/prodotti-master", tags=["Prodotti Master"])

# Prodotti NON ordinabili dal libro ordini: non-alimentari, carburanti, imballaggi,
# attrezzature. Match come parola intera (\b) per non escludere alimenti per errore.
_PAROLE_NON_ORDINABILI = [
    "gasolio", "gpl", "benzina", "carburante", "diesel", "metano",
    # Ferramenta / materiale elettrico / utenze / manutenzione (non commestibili,
    # non da catalogo ordini: restano in DB per le statistiche di spesa)
    "cavo elettrico", "cavo fs", "presa elettrica", "spina elettrica", "prolunga",
    "nastro isolante", "nastro sigillante", "nastro scotch", "nastro telato", "nastro vkp",
    "nastro adesivo", "nastro avana", "silicone", "sigillante", "guarnizione",
    "diluente", "vernice", "smalto", "solvente", "acquaragia",
    "accisa", "accise", "imposte e iva", "energia elettrica", "fornitura energia",
    "lampadina", "neon", "faretto", "interruttore", "morsetto", "fascetta",
    "vite ", "viti ", "tassello", "trapano", "punta sds", "guanti da lavoro",
    "lattine per", "lattina per", "barattoli per", "vasetti per", "imballaggi", "imballo",
    "sacchetti", "shopper", "tovaglioli", "tovagliolo", "carta forno", "pellicola",
    "detersivo", "detergente", "sgrassatore", "disinfettante", "sapone",
    "ruoto", "teglia", "stampo", "coltello", "vassoio", "cartone pizza", "scatola",
    # Servizi / fatture che non sono prodotti acquistabili
    "vi rimettiamo", "anticipazione contrattuale", "lavori di manutenzione",
    "manutenzione ordinaria", "manutenzione straordinaria", "prestazione",
    "consulenza", "canone", "noleggio", "competenze", "compenso", "onorari",
    "fattura di", "saldo fattura", "acconto fattura", "nota di credito",
    "nota credito", "modalità pagamento", "modalita pagamento",
    "destinazione merce", "per degustazione", "intervento lavori",
    "ns. rif", "ns rif", "vs. rif", "vs rif",
    # Righe amministrative isolate (nessun contenuto prodotto reale, trovate
    # come nome_canonico spazzatura nel rebuild 01/07/2026)
    "documento", "ordine",
    # Righe-riferimento delle fatture (NON prodotti)
    "rif. conferma", "rif.conferma", "rif. ordine", "rif.ordine", "rif. doc",
    "rif.doc", "rif. preventivo", "rif.preventivo", "rif. ddt", "rif.ddt",
    "rif. scontrino", "rif.scontrino", "rif. nostro", "rif. vostro",
    "documento di trasporto", "doc. di trasporto", "ddt n", "ns. ddt", "vs. ordine",
    "numero ordine", "n. ordine", "ordine n", "preventivo n", "preventivo nr",
    "omaggio", "sconto", "abbuono", "arrotondamento", "spese di trasporto",
    "spedizione", "spese di spedizione", "spese spedizione", "costi di spedizione",
    "spese trasporto", "contributo conai", "bollo", "imposta di bollo",
    "trasporto a mezzo", "porto franco", "porto assegnato", "cauzione",
    # Materiale edile/elettrico/ferramenta (fornitori non alimentari)
    "cavo h07", "cavo fg", "barra filettata", "fascetta", "curva 90", "curva ø",
    "termopack", "fonoass", "griglia t/", "brugola", "brugole", "viti", "tassello",
    "guaina", "tubo corrugato", "morsetto", "interruttore", "presa schuko",
    # Stoviglie / attrezzature / utensili (non sono prodotti alimentari ordinabili)
    "calice", "bicchiere", "bicchieri", "tazzina", "tazzine", "tazza", "piatto",
    "piattino", "cucchiaino", "cucchiaio", "forchetta", "posate", "tovaglia",
    "tostapane", "cassaforte", "monomateriale", "biodegradabile", "cadauna",
    "prontotimas", "set 9", "set 6", "set 3",
    # Righe amministrative/servizio viste nelle fatture reali (non prodotti):
    # falsavano "senza prezzo"/"senza fornitore" come fossero prodotti veri.
    "documento trasporto", "ddt", "maggiorazione", "maggiorazioni",
    "spese gestione incasso", "gestione incasso", "spese incasso",
    "spese di gestione", "spese accessorie", "spese amministrative",
    "documentazione", "confezioni assortite", "confezione assortita",
    # Imballaggi/stoviglie al plurale + righe contabili viste come "prodotti"
    # con nome_canonico spazzatura (vassoi/tondi alluminio/bilancio/conai):
    # il rebuild li aveva promossi a prodotto. Sono non-food.
    "vassoi", "tondi alluminio", "tondi allum", "tondi cart",
    "bilancio", "corrispettivo", "conai", "contributo ambientale",
    # Righe amministrative/legali isolate viste nel controllo-dati 01/07/2026
    # (testi di legge, storni, acconti): promosse a "prodotto" per errore.
    "assolve gli obblighi", "decreto legge", "a detrarre", "storno",
    "colli peso", "omaggi",
]


def _rx_parola(parola: str) -> str:
    """Costruisce il frammento regex per una parola/frase spazzatura.
    Gli spazi INTERNI (tra due parole) diventano separatore flessibile
    (spazio/trattino/underscore/slash), cosi' 'spese gestione incasso'
    matcha anche 'Spese-Gestione-Incasso' (visto in prodotti_master reale,
    nome_canonico con trattini al posto degli spazi). Gli spazi in coda
    (es. 'vite ') restano letterali: servono a delimitare la parola
    (altrimenti 'vite' matcherebbe anche 'vitello')."""
    escaped = re.escape(parola).replace("\\ ", " ")
    return r"\b" + re.sub(r"(?<=\S) (?=\S)", lambda _m: r"[\s\-_/]+", escaped)


_RX_NON_ORDINABILI = "|".join(_rx_parola(p) for p in _PAROLE_NON_ORDINABILI)

# Righe-spazzatura tipiche dei corrispettivi/descrizioni mal importate, NON prodotti:
# es. "2 Persone * 2,50 Euro * 7 Gironi", voci con euro+persone/giorni, "corrispettivo".
_RX_SPAZZATURA = re.compile(
    r"(euro).{0,20}(person|giorn|giron)|(person|giorn|giron).{0,20}(euro)|"
    r"\d+\s*person|\bcorrispettiv|\bscontrin",
    re.IGNORECASE,
)

# ── Classificazione merceologica (la collezione non ha categorie: le deduciamo) ──
_CATEGORIE_KW = {
    "Bevande e Bottiglie": [
        "acqua", "bibita", "bibite", "coca cola", "fanta", "sprite", "succo",
        "birra", "vino", "spumante", "prosecco", "champagne", "liquore", "amaro", "gin",
        "vodka", "rum", "whisky", "grappa", "aperol", "campari", "bitter", "acqua tonica",
        "cl33", "cl70", "cl75", "fusto", "spina", "lattina", "bottiglia di",
    ],
    "Caffetteria": [
        "caffè", "caffe", "kimbo", "lavazza", "miscela bar", "cialde", "capsule",
        "ginseng", "orzo solubile", "decaffeinato", "cappuccino",
        "tè caldo", "camomilla", "infuso", "cacao solubile",
    ],
    "Pasticceria": [
        "farina", "zucchero", "burro", "uova", "uovo", "lievito", "cioccolato",
        "cacao", "panna", "crema pasticcera", "vaniglia", "mandorl", "nocciol", "pistacchio",
        "canditi", "candito", "marmellata", "confettura", "glassa", "pasta di",
        "amido", "gelatina", "colorante", "aroma", "savoiardi", "pan di spagna",
        "croissant", "cornetto", "brioche", "sfoglia", "babà", "baba", "ricotta",
        "scorzone", "scorza", "albicocch", "ciliegi", "frutta candita", "marron",
        "lievito naturale", "miglioratore",
    ],
    "Salato / Gastronomia": [
        "prosciutto", "mozzarella", "formaggio", "salame", "mortadella", "wurstel",
        "pollo", "carne", "ragù", "ragu", "pomodoro", "passata", "sugo", "olio",
        "sale", "pepe", "spezie", "pancetta", "speck", "tonno", "acciugh", "arancin",
        "supplì", "suppli", "pizza margherita", "pane", "rosetta", "ciabatta", "panino",
        "patate", "besciamella", "parmigiano", "grana padano", "provola", "semola",
    ],
}


def _e_spazzatura(nome: str) -> bool:
    """True se la voce non è un prodotto ordinabile (righe-riferimento, materiale
    non alimentare, servizi). Esclude anche lotti/omaggi e descrizioni numeriche."""
    n = (nome or "").strip().lower()
    if not n or len(n) < 3:
        return True
    from app.lotti.routers.classificatore_alimenti import e_non_food_certo
    if e_non_food_certo(nome):
        return True  # cavi, diluenti, candeggina, monitor... non sono ordinabili
    if re.search(_RX_NON_ORDINABILI, n):
        return True
    # descrizioni che sono solo riferimenti/lotti/numeri
    if re.match(r"^[\*\#\-\.\s]", nome or ""):  # iniziano con */#/-/. → di solito righe-rif
        if re.search(r"rif\.|lotto|conferma|trasporto|preventivo|ordine|omaggio", n):
            return True
    if "lotto" in n and re.search(r"lotto\s*[\d.]", n):
        return True
    # nessuna lettera (solo numeri/punteggiatura)
    if not re.search(r"[a-zàèéìòù]", n):
        return True
    return False


_CATEGORIE_FORNITORE_SALATO = (
    "rosticceria", "gastronomia", "snack", "pani e focacce", "pani speciali",
    "focacce", "baguette", "cornetti salati", "verdura surgelata", "pomodori",
    "da scaldare", "da friggere", "da cuocere", "già fritti", "gia fritti",
)

_CATEGORIE_FORNITORE_PASTICCERIA = (
    "amidi", "aromi", "bagne", "biscotteria", "cioccolato", "coadiuvanti",
    "coloranti", "confetture", "creme", "crunch", "decorazioni", "farine",
    "frutta", "gelateria", "glasse", "grassi", "latte", "lievito", "mix e",
    "ovoprodotti", "panna", "pasta di mandorle", "paste da decorazione",
    "pasticceria", "semifreddi", "dessert", "zucchero", "prelievitati",
    "sfoglie", "semilavorati", "da lievitare", "già cotti", "gia cotti",
    "tipici", "biscotti", "monoporzioni", "baby & mini", "donuts", "roundy",
)

_CATEGORIE_FORNITORE_ATTREZZATURE = (
    "attrezzature", "carta & plastica", "carta e plastica", "detergenza",
)


def _categoria_merce(nome: str, categorie_fonte: Optional[list] = None) -> str:
    """Classifica il prodotto in una categoria merceologica.
    1) Dizionario (vetreria/attrezzature con priorità, marchi bevande);
    2) parole-chiave base (Bevande, Caffetteria, Pasticceria, Salato);
    3) fallback 'Altro'.
    """
    # 0) Le categorie pubblicate dal fornitore sono più affidabili del nome.
    # Evita, per esempio, che un croissant salato finisca in Pasticceria solo
    # perché contiene la parola "croissant".
    fonte = " | ".join(str(c or "").lower() for c in (categorie_fonte or []))
    if fonte:
        if any(kw in fonte for kw in _CATEGORIE_FORNITORE_SALATO):
            return "Salato / Gastronomia"
        if any(kw in fonte for kw in _CATEGORIE_FORNITORE_ATTREZZATURE):
            return "Attrezzature"
        if any(kw in fonte for kw in _CATEGORIE_FORNITORE_PASTICCERIA):
            return "Pasticceria"

    # 1) dizionario sinonimi/marchi — la vetreria ha la priorità
    diz = classifica(nome)
    if diz:
        return diz[0]
    n = (nome or "").lower()
    # 2) parole-chiave base: bevande e caffetteria sono più distintive
    for cat in ["Bevande e Bottiglie", "Caffetteria", "Salato / Gastronomia", "Pasticceria"]:
        for kw in _CATEGORIE_KW[cat]:
            if kw in n:
                return cat
    return "Altro"



async def _carica_dizionario_canonico() -> dict:
    """Carica in memoria la mappa descrizione→nome_canonico dal dizionario condiviso
    (collezione nome_mapping). Una sola lettura, riusata per tutti i prodotti del
    rebuild, così master e lotti fornitori condividono gli stessi nomi canonici."""
    diz = {}
    try:
        async for d in db.nome_mapping.find({}, {"_id": 0, "descrizione_key": 1, "nome_canc": 1}):
            k = (d.get("descrizione_key") or "").strip().lower()
            v = (d.get("nome_canc") or "").strip()
            if k and v:
                diz[k] = v
    except Exception:
        logger.debug("[prodotti_master] errore non bloccante ignorato")
    return diz


def _canonico_da_dizionario(nome_raw: str, diz: dict) -> str:
    """Ritorna il nome canonico per una descrizione grezza usando il dizionario
    condiviso (match esatto, pulito, poi sinonimi statici). '' se ignoto."""
    if not nome_raw:
        return ""
    low = nome_raw.strip().lower()
    if low in diz:
        return diz[low]
    # descrizione ripulita da codici/pesi
    clean = re.sub(r"\b\d+[\.,]?\d*\s*(kg|g|gr|ml|lt|l|pz|cl|x\d+)?\b", " ", low)
    clean = re.sub(r"\b[a-z0-9]{5,}\b", " ", clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    if clean in diz:
        return diz[clean]
    # sinonimi statici condivisi (stessa fonte dell'import prodotti)
    try:
        from app.lotti.routers.normalizzazione import cerca_in_sinonimi_statici
        m = cerca_in_sinonimi_statici(nome_raw)
        if m and m.get("nome_canc"):
            return m["nome_canc"]
    except Exception:
        logger.debug("[prodotti_master] errore non bloccante ignorato")
    return ""


# ── Utility normalizzazione ──────────────────────────────────────────────────
def normalize_nome(s: str) -> str:
    if not s:
        return ""
    # Taglia il blocco-codice spazzatura dopo "|" (es. "Ricotta | 99SEA0024..-..")
    # che inquina nome/chiave e impedisce il match con i prodotti da fattura.
    s = s.split("|")[0]
    s = re.sub(r"[\"'`]", " ", s)
    s = re.sub(r"\s+", " ", s).strip().lower()
    # Sinonimi/abbreviazioni → forma estesa per ridurre duplicati semantici
    sinonimi = {
        r"\bextrav\b": "extravergine",
        r"\boliv\b": "oliva",
        r"\bmozz\b": "mozzarella",
        r"\bbufal\b": "bufala",
        r"\bdolc\b": "dolce",
        r"\bvergine\b": "extravergine",
        r"\bnaz\b": "nazionale",
        r"\bsurg\b": "surgelato",
        r"\bsott\b": "sotto",
    }
    for k, v in sinonimi.items():
        s = re.sub(k, v, s)
    s = re.sub(r"\b(kg|gr|g|lt|l|ml|cl|pz|x\d+)\b", "", s)
    s = re.sub(r"\b\d+(?:[,.]\d+)?\b", "", s)
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    # Ordina parole per match indipendente da ordine
    return " ".join(sorted(s.split()))


def key_canonica(s: str) -> str:
    n = normalize_nome(s or "")
    return n[:80] if n else None



def _comparatore_60gg(prezzi_storici: list) -> list:
    """Comparatore fornitori: per OGNI fornitore che ha fatturato il prodotto,
    il suo prezzo più RECENTE, ordinato dal più economico al più caro.

    Regola (Enzo 14/06/2026): il carrello deve SEMPRE avere un prezzo. Quindi
    NON si taglia a 60 giorni: si tengono tutti i fornitori, ognuno marcato con
    `giorni_fa` e `recente` (<=60gg). Il frontend mette in cima il migliore e
    segnala se il prezzo è recente o vecchio. Un prodotto comprato a marzo (90gg)
    deve comunque mostrare il suo prezzo, non sparire dal carrello."""
    from app.lotti.routers.utils import parse_data_flessibile
    from datetime import datetime as _dt, timezone as _tz
    oggi = _dt.now(_tz.utc).date()
    vecchissimo = oggi.replace(year=oggi.year - 10)
    per_fornitore: dict = {}
    for ps in (prezzi_storici or []):
        # REGOLA ENZO: il miglior prezzo è quello VERAMENTE PAGATO. Solo fatture.
        # Listino/Acquaviva/Saima sono prezzi di catalogo, non vanno spacciati
        # per prezzi d'acquisto. Restano nel master per altri usi, non qui.
        if (ps.get("fonte") or "") != "fattura":
            continue
        prezzo = ps.get("prezzo") or 0
        forn = (ps.get("fornitore") or "").strip()
        if prezzo <= 0 or not forn:
            continue
        d = parse_data_flessibile(ps.get("data"))
        chiave = d or vecchissimo
        cur = per_fornitore.get(forn)
        if cur is None or chiave > cur["_data"]:
            giorni = (oggi - d).days if d else None
            per_fornitore[forn] = {
                "fornitore": forn,
                "prezzo": round(float(prezzo), 4),
                "data": ps.get("data", ""),
                "giorni_fa": giorni,
                "recente": (giorni is not None and giorni <= 60),
                "_data": chiave,
            }
    # prima i recenti (<=60gg), poi per prezzo crescente
    out = sorted(per_fornitore.values(), key=lambda x: (not x["recente"], x["prezzo"]))
    for o in out:
        o.pop("_data", None)
    return out


# ── GET lista ─────────────────────────────────────────────────────────────────
@router.get("")
async def lista(
    q: str = Query("", description="ricerca su nome/aliases/codici"),
    fonte: str = Query("", description="filtra per fonte (fattura, acquaviva, ...)"),
    categoria: str = Query("", description="categoria merceologica"),
    fornitore: str = Query(""),
    solo_con_prezzo: bool = False,
    includi_non_ordinabili: bool = False,
    escludi_fornitori: bool = Query(True, description="Escludi prodotti dei fornitori flaggati 'escluso'"),
    limit: int = Query(200, le=2000),
    skip: int = 0,
):
    """Lista paginata del catalogo unificato. Di default mostra solo i prodotti
    ordinabili (esclude righe-riferimento, materiale non alimentare, servizi)."""
    filtro = {}
    if not includi_non_ordinabili:
        filtro["escluso"] = {"$ne": True}
    if q:
        rx = {"$regex": re.escape(q), "$options": "i"}
        filtro["$or"] = [
            {"nome_canonico": rx},
            {"aliases": rx},
            {"codici": rx},
        ]
    if fonte:
        filtro["fonti"] = fonte
    if categoria:
        filtro["categoria_merce"] = categoria
    if fornitore:
        filtro["fornitori"] = fornitore
    if solo_con_prezzo:
        filtro["ultimo_prezzo"] = {"$gt": 0}
    # Di default solo prodotti ordinabili (flag calcolato nel rebuild). Fallback al
    # vecchio filtro regex per i documenti non ancora ribaccati.
    if not includi_non_ordinabili:
        filtro["$and"] = [
            {"$or": [{"ordinabile": True}, {"ordinabile": {"$exists": False}}]},
            {"nome_canonico": {"$not": {"$regex": f"(?i){_RX_NON_ORDINABILI}"}}},
        ]

    cursor = (
        db.prodotti_master.find(filtro, {"_id": 0}).sort("nome_canonico", 1).skip(skip).limit(limit)
    )
    items = await cursor.to_list(limit)
    if not includi_non_ordinabili:
        # Cintura in lettura: il flag `ordinabile` in DB puo' essere stantio
        # (calcolato col vecchio classificatore). Il classificatore unico
        # decide SEMPRE: cavi, diluenti, candeggina... fuori dal catalogo.
        from app.lotti.routers.classificatore_alimenti import e_non_food_certo
        items = [
            i for i in items
            if not e_non_food_certo(i.get("nome_canonico", ""))
            and not _RX_SPAZZATURA.search(i.get("nome_canonico", "") or "")
        ]

    # Fornitori esclusi (flag 'escluso' in anagrafica): i loro prodotti escono dal catalogo.
    esclusi = set()
    if escludi_fornitori:
        try:
            docs = await db.fornitori.find({"escluso": True}, {"nome": 1, "_id": 0}).to_list(500)
            esclusi = {(d.get("nome") or "").strip().lower() for d in docs if d.get("nome")}
        except Exception:
            esclusi = set()

    def _is_escluso(nome):
        n = (nome or "").strip().lower()
        return bool(n) and any(e and (e == n or e in n or n in e) for e in esclusi)

    # COMPARATORE 60 GIORNI: per ogni prodotto, miglior fornitore (prezzo più basso)
    # tra quelli che l'hanno fatturato negli ultimi 60 giorni, più l'elenco completo.
    risultato = []
    for it in items:
        forn60 = _comparatore_60gg(it.get("prezzi_storici", []))
        if esclusi:
            forn60 = [f for f in forn60 if not _is_escluso(f.get("fornitore"))]
        it["fornitori_60gg"] = forn60
        if forn60:
            best = forn60[0]  # recenti prima, poi prezzo crescente — solo fatture
            it["miglior_prezzo_60gg"] = best["prezzo"]
            it["miglior_fornitore_60gg"] = best["fornitore"]
            it["prezzo_recente"] = best["recente"]
            it["prezzo_giorni_fa"] = best["giorni_fa"]
        else:
            # Nessun fornitore valido con prezzo. Se TUTTI i fornitori del prodotto
            # sono esclusi (es. ferramenta), il prodotto esce dal catalogo.
            forn_prod = it.get("fornitori") or []
            if esclusi and forn_prod and all(_is_escluso(f) for f in forn_prod):
                continue
            it["miglior_prezzo_60gg"] = None
            it["miglior_fornitore_60gg"] = ""
            it["prezzo_recente"] = False
            it["prezzo_giorni_fa"] = None
        it.pop("prezzi_storici", None)  # alleggerisce il payload
        risultato.append(it)
    items = risultato
    return {"total": len(items), "items": items, "limit": limit, "skip": skip}


_ORDINE_CATEGORIE = ["Pasticceria", "Salato / Gastronomia", "Bevande e Bottiglie", "Caffetteria", "Attrezzature", "Altro"]
_CATALOGO_MAX_PRODOTTI = 10_000


@router.get("/per-categoria")
async def per_categoria(solo_con_prezzo: bool = False, fornitore: str = Query("")):
    """Catalogo ordinabile raggruppato per categoria merceologica, pronto per la
    pagina Ordini. Ogni prodotto include i campi utili all'ordine (prezzo a 90gg,
    unità, fornitore migliore, codici)."""
    filtro = {
        "$or": [{"ordinabile": True}, {"ordinabile": {"$exists": False}}],
        "nome_canonico": {"$not": {"$regex": f"(?i){_RX_NON_ORDINABILI}"}},
        "escluso": {"$ne": True},
    }
    if solo_con_prezzo:
        filtro["ultimo_prezzo"] = {"$gt": 0}
    if fornitore:
        filtro["fornitori"] = fornitore

    proj = {
        "_id": 0, "id": 1, "nome_canonico": 1, "categoria_merce": 1, "unita_misura": 1,
        "codici": 1, "fornitori": 1, "ultimo_prezzo": 1, "miglior_prezzo_90gg": 1,
        "miglior_fornitore_90gg": 1, "miglior_fornitore": 1, "aliquota_iva": 1,
        "immagine_url": 1, "link_prodotto": 1,
    }
    items = await db.prodotti_master.find(filtro, proj).sort("nome_canonico", 1).to_list(_CATALOGO_MAX_PRODOTTI)

    gruppi = {c: [] for c in _ORDINE_CATEGORIE}
    for it in items:
        cat = it.get("categoria_merce") or "Altro"
        if cat not in gruppi:
            cat = "Altro"
        prezzo = it.get("miglior_prezzo_90gg") or it.get("ultimo_prezzo") or 0
        gruppi[cat].append({
            "id": it.get("id"),
            "nome": it.get("nome_canonico", ""),
            "categoria": cat,
            "unita_misura": it.get("unita_misura", ""),
            "codici": it.get("codici", []),
            "fornitore": it.get("miglior_fornitore_90gg") or it.get("miglior_fornitore") or "",
            "prezzo": round(float(prezzo), 4) if prezzo else 0,
            "prezzo_90gg": it.get("miglior_prezzo_90gg") or 0,
            "aliquota_iva": it.get("aliquota_iva") or 0,
            "gia_acquistato": bool(prezzo),
            "immagine_url": it.get("immagine_url") or "",
            "link_prodotto": it.get("link_prodotto") or "",
        })

    return {
        "categorie": [
            {"nome": c, "prodotti": gruppi[c], "totale": len(gruppi[c])}
            for c in _ORDINE_CATEGORIE if gruppi[c]
        ],
        "totale_prodotti": sum(len(v) for v in gruppi.values()),
    }


# Mappa categoria merceologica Lotti → (settore app, cat app)
_MAP_SETTORE_APP = {
    "Pasticceria": ("Pasticceria", "PASTICCERIA"),
    "Salato / Gastronomia": ("Cucina", "CUCINA"),
    "Bevande e Bottiglie": ("Bar", "BEVANDE"),
    "Caffetteria": ("Bar", "CAFFETTERIA"),
    "Attrezzature": ("Attrezzature", "BICCHIERI"),
    "Altro": ("Bar", "VARIE"),
}


@router.get("/catalogo-app")
async def catalogo_app():
    """Restituisce il catalogo unificato ordinabile nel formato della web-app Ordini
    (id, name, conf, cat, sector, prices{fornitore:prezzo}, best, iva). Gli id partono
    da 1000 per non collidere con i prodotti seed dell'app (0-433). L'app concatena
    questi ai suoi seed: così si vedono insieme catalogo reale + listino base."""
    filtro = {
        "$or": [{"ordinabile": True}, {"ordinabile": {"$exists": False}}],
        "nome_canonico": {"$not": {"$regex": f"(?i){_RX_NON_ORDINABILI}"}},
        # Escludi "Altro": è il non-classificato, contiene materiale non alimentare
        # (ferramenta, edile, chimici) che non va nel catalogo ordini.
        "categoria_merce": {"$in": ["Pasticceria", "Salato / Gastronomia", "Bevande e Bottiglie", "Caffetteria", "Attrezzature"]},
        "escluso": {"$ne": True},
    }
    proj = {
        "_id": 0, "nome_canonico": 1, "categoria_merce": 1, "unita_misura": 1,
        "codici": 1, "miglior_prezzo_90gg": 1, "miglior_fornitore_90gg": 1,
        "ultimo_prezzo": 1, "miglior_fornitore": 1, "aliquota_iva": 1,
        "immagine_url": 1, "link_prodotto": 1,
    }
    docs = await db.prodotti_master.find(filtro, proj).sort("nome_canonico", 1).to_list(_CATALOGO_MAX_PRODOTTI)

    out = []
    nid = 1000
    for d in docs:
        cat_merce = d.get("categoria_merce") or "Altro"
        sector, cat_app = _MAP_SETTORE_APP.get(cat_merce, ("Bar", "VARIE"))
        prezzo = d.get("miglior_prezzo_90gg") or d.get("ultimo_prezzo") or 0
        forn = d.get("miglior_fornitore_90gg") or d.get("miglior_fornitore") or ""
        prices = {}
        if forn and prezzo:
            prices[forn] = round(float(prezzo), 4)
        iva = d.get("aliquota_iva") or 0
        out.append({
            "id": nid,
            "name": d.get("nome_canonico", ""),
            "conf": d.get("unita_misura", "") or "PZ",
            "cat": cat_app,
            "sector": sector,
            "prices": prices,
            "best": forn if prices else "",
            "iva": (f"{int(iva)}%" if iva else ""),
            "codici": d.get("codici", []),
            "origine": "catalogo",
            "immagine_url": d.get("immagine_url") or "",
            "link_prodotto": d.get("link_prodotto") or "",
        })
        nid += 1
    return {"prodotti": out, "totale": len(out)}


# ── GET singolo ──────────────────────────────────────────────────────────────
@router.get("/cerca")
async def cerca(q: str, limit: int = 30):
    """Fuzzy search rapida (ritorna solo nome+codici+ultimo_prezzo)."""
    if not q or len(q) < 2:
        return []
    from app.lotti.routers.utils import stems_ricerca
    stems = stems_ricerca(q) or [q.lower()]
    clausole = [{"$or": [
        {"nome_canonico": {"$regex": re.escape(s), "$options": "i"}},
        {"aliases": {"$regex": re.escape(s), "$options": "i"}},
        {"codici": {"$regex": re.escape(s), "$options": "i"}},
    ]} for s in stems]
    cursor = db.prodotti_master.find(
        {
            "$and": clausole,
            "nome_canonico": {"$not": {"$regex": f"(?i){_RX_NON_ORDINABILI}"}},
        },
        {
            "_id": 0,
            "id": 1,
            "nome_canonico": 1,
            "codici": 1,
            "ultimo_prezzo": 1,
            "fonti": 1,
            "fornitori": 1,
        },
    ).limit(limit)
    return await cursor.to_list(limit)


@router.get("/stats")
async def stats():
    """Distribuzione per fonte e per categoria."""
    pipe_fonti = [
        {"$unwind": "$fonti"},
        {"$group": {"_id": "$fonti", "n": {"$sum": 1}}},
        {"$sort": {"n": -1}},
    ]
    pipe_cat = [
        {"$unwind": "$categorie"},
        {"$group": {"_id": "$categorie", "n": {"$sum": 1}}},
        {"$sort": {"n": -1}},
        {"$limit": 20},
    ]
    fonti = await db.prodotti_master.aggregate(pipe_fonti).to_list(20)
    categorie = await db.prodotti_master.aggregate(pipe_cat).to_list(20)
    totale = await db.prodotti_master.count_documents({})
    con_prezzo = await db.prodotti_master.count_documents({"ultimo_prezzo": {"$gt": 0}})
    canonici_dizionario = await db.prodotti_master.count_documents({"canonico_da_dizionario": True})
    return {
        "totale": totale,
        "con_prezzo": con_prezzo,
        "canonici_dizionario": canonici_dizionario,
        "fonti": fonti,
        "top_categorie": categorie,
    }


@router.post("/riclassifica")
async def riclassifica():
    """Ri-applica il dizionario di classificazione a tutti i prodotti master.
    Es. sposta i set di calici da 'Bevande e Bottiglie' a 'Attrezzature'."""
    cursor = db.prodotti_master.find(
        {}, {"_id": 0, "id": 1, "nome_canonico": 1, "categoria_merce": 1, "categorie": 1}
    )
    aggiornati, per_categoria = 0, {}
    async for d in cursor:
        nuova = _categoria_merce(d.get("nome_canonico") or "", d.get("categorie") or [])
        if nuova != (d.get("categoria_merce") or "Altro"):
            await db.prodotti_master.update_one({"id": d["id"]}, {"$set": {"categoria_merce": nuova}})
            aggiornati += 1
            per_categoria[nuova] = per_categoria.get(nuova, 0) + 1
    return {"aggiornati": aggiornati, "per_categoria": per_categoria}


@router.post("/escludi")
async def escludi(payload: dict = Body(...)):
    """Escludi (o ripristina) un prodotto dalla visualizzazione del catalogo.
    Aggancio per nome_canonico: gli id di /catalogo-app non sono stabili.
    Body: {"nome": "...", "escluso": true|false}."""
    nome = (payload.get("nome") or payload.get("nome_canonico") or "").strip()
    if not nome:
        raise HTTPException(400, "nome mancante")
    escluso = bool(payload.get("escluso", True))
    r = await db.prodotti_master.update_many({"nome_canonico": nome}, {"$set": {"escluso": escluso}})
    return {"nome": nome, "escluso": escluso, "modificati": r.modified_count}


@router.get("/stato-rebuild")
async def stato_rebuild():
    """Stato dell'ultimo rebuild del catalogo."""
    st = await db.sync_status.find_one({"_id": "rebuild_master"}, {"_id": 0})
    return st or {"stato": "mai_eseguito"}


@router.get("/{master_id}")
async def get_one(master_id: str):
    doc = await db.prodotti_master.find_one({"id": master_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Prodotto master non trovato")
    return doc


# ── POST rebuild ──────────────────────────────────────────────────────────────
async def _esegui_rebuild():
    """Ricostruisce la collezione `prodotti_master` da zero aggregando tutte le fonti.

    Usa 2 strategie di matching combinate per ridurre i duplicati:
    1) chiave normalizzata (nome senza unità/numeri, sinonimi espansi, parole ordinate)
    2) merge cross-key per `codice` articolo → se due chiavi diverse hanno lo stesso
       codice (es. "OLIO EXTRAV OLIVA" e "OLIO EXTRAVERGINE OLIVA" entrambe cod 064),
       vengono fuse in un'unica voce.

    Idempotente. Da eseguire dopo importi grossi di fatture.
    """
    master = {}
    by_codice = {}  # codice → key principale (per merge cross-key)

    def smart_key(nome, codice=None):
        cod = (str(codice) if codice else "").strip()
        if cod and cod in by_codice:
            return by_codice[cod]
        return key_canonica(nome)

    def merge(key, nome_raw, fonte, **fields):
        if not key:
            return
        if key not in master:
            master[key] = {
                "id": str(uuid.uuid4()),
                "nome_canonico": (nome_raw or key).strip().title()[:120],
                "key": key,
                "aliases": set(),
                "codici": set(),
                "fornitori": set(),
                "categorie": set(),
                "unita_misura": "",
                "prezzi_storici": [],
                "ultimo_prezzo": 0,
                "miglior_prezzo": None,
                "miglior_fornitore": "",
                "aliquota_iva": 0,
                "fonti": set(),
                "immagine_url": "",
                "link_prodotto": "",
                "totale_apparizioni": 0,
            }
        m = master[key]
        if nome_raw:
            m["aliases"].add(nome_raw.strip()[:200])
        cod = fields.get("codice")
        if cod:
            cod = str(cod).strip()
            if cod:
                m["codici"].add(cod)
                if cod not in by_codice:
                    by_codice[cod] = key
        if fields.get("fornitore"):
            m["fornitori"].add(str(fields["fornitore"]))
        if fields.get("categoria"):
            m["categorie"].add(str(fields["categoria"]))
        if fields.get("immagine_url") and not m["immagine_url"]:
            m["immagine_url"] = str(fields["immagine_url"]).strip()
        if fields.get("link_prodotto") and not m["link_prodotto"]:
            m["link_prodotto"] = str(fields["link_prodotto"]).strip()
        if fields.get("unita_misura") and not m["unita_misura"]:
            m["unita_misura"] = str(fields["unita_misura"])
        if fields.get("aliquota_iva"):
            try:
                iva = float(fields["aliquota_iva"])
                if iva > 0:
                    m["aliquota_iva"] = iva
            except (ValueError, TypeError):
                pass
        prezzo = fields.get("prezzo") or 0
        try:
            prezzo = float(prezzo)
        except Exception:
            prezzo = 0
        if prezzo > 0:
            m["prezzi_storici"].append(
                {
                    "prezzo": prezzo,
                    "fonte": fonte,
                    "fornitore": fields.get("fornitore", ""),
                    "data": fields.get("data", ""),
                }
            )
            m["ultimo_prezzo"] = prezzo
            if not m.get("miglior_prezzo") or prezzo < m["miglior_prezzo"]:
                m["miglior_prezzo"] = prezzo
                m["miglior_fornitore"] = fields.get("fornitore", "") or fonte
        m["fonti"].add(fonte)
        m["totale_apparizioni"] += 1

    def _num(v):
        """Converte in float numeri salvati come stringa (spazi, virgola decimale)."""
        try:
            s = str(v).strip().replace(" ", "")
            if "," in s and "." not in s:
                s = s.replace(",", ".")
            return float(s or 0)
        except Exception:
            return 0.0

    # Fornitori COMPLETAMENTE esclusi (tri-stato "escluso", diverso da
    # "solo_magazzino" che invece deve popolare il catalogo): le loro righe
    # fattura non devono mai finire in prodotti_master, in nessuna forma.
    _fornitori_esclusi_docs = await db.fornitori.find(
        {"$or": [{"escluso": True}, {"tipo_fornitura": "escluso"}]}, {"nome": 1}
    ).to_list(5000)
    _fornitori_esclusi = {(d.get("nome") or "").strip().lower() for d in _fornitori_esclusi_docs}

    # 1. fatture.prodotti (priorità: portano i codici)
    async for f in db.fatture.find({}, {"prodotti": 1, "fornitore": 1, "data_fattura": 1}):
        forn = f.get("fornitore", "")
        if forn and forn.strip().lower() in _fornitori_esclusi:
            continue
        for p in f.get("prodotti") or []:
            nome = p.get("descrizione", "")
            cod = p.get("codice_articolo") or p.get("codice_prodotto")
            k = smart_key(nome, cod)
            if not k:
                continue
            # 'prezzo' nelle fatture è GIÀ il prezzo unitario (PrezzoUnitario).
            # NON va diviso per la quantità — il totale di riga sta in 'prezzo_totale'.
            pr = _num(p.get("prezzo"))
            qt = _num(p.get("quantita"))
            tot = _num(p.get("prezzo_totale"))
            # Fallback: se il prezzo unitario manca, ricavalo dal totale / quantità.
            prezzo_unit = pr if pr > 0 else ((tot / qt) if qt > 0 and tot > 0 else pr)
            merge(
                k,
                nome,
                "fattura",
                codice=cod,
                fornitore=forn,
                unita_misura=p.get("unita_misura"),
                aliquota_iva=p.get("aliquota_iva"),
                prezzo=prezzo_unit,
                data=f.get("data_fattura", ""),
            )

    # 2. acquaviva_prodotti
    async for p in db.acquaviva_prodotti.find({}):
        cod = p.get("codice")
        k = smart_key(p.get("nome"), cod)
        if not k:
            continue
        merge(
            k,
            p.get("nome"),
            "acquaviva",
            codice=cod,
            fornitore="Dolciaria Acquaviva",
            categoria=p.get("categoria"),
            prezzo=p.get("prezzo_singolo") or 0,
            immagine_url=p.get("immagine_url") or p.get("foto_url"),
            link_prodotto=p.get("link_prodotto"),
        )

    # 3. prodotti_vendita
    async for p in db.prodotti_vendita.find({}):
        cod = p.get("codice_prodotto")
        k = smart_key(p.get("nome"), cod)
        if not k:
            continue
        merge(
            k,
            p.get("nome"),
            "prodotti_vendita",
            codice=cod,
            fornitore=p.get("fornitore"),
            categoria=p.get("categoria"),
            prezzo=p.get("costo_produzione") or 0,
            immagine_url=p.get("immagine_url") or p.get("foto_url"),
            link_prodotto=p.get("link_prodotto"),
        )

    # 4. magazzino_bar_prodotti
    async for p in db.magazzino_bar_prodotti.find({}):
        k = smart_key(p.get("nome"))
        if not k:
            continue
        merge(
            k,
            p.get("nome"),
            "magazzino_bar",
            fornitore=p.get("fornitore"),
            categoria=p.get("categoria"),
            unita_misura=p.get("unita"),
        )

    # 5. listino_prodotti
    async for p in db.listino_prodotti.find({}):
        cod = p.get("codice")
        k = smart_key(p.get("nome"), cod)
        if not k:
            continue
        merge(
            k,
            p.get("nome"),
            "listino",
            codice=cod,
            fornitore=p.get("fornitore"),
            categoria=p.get("categoria"),
            prezzo=p.get("prezzo") or 0,
        )

    # 6. Cataloghi web SAIMA/MEPA. In precedenza venivano scaricati nel
    # dizionario ingredienti ma il catalogo unificato non leggeva questa fonte:
    # uno scraping riuscito risultava quindi comunque "mancante" negli Ordini.
    async for p in db.dizionario_ingredienti.find({"fonte": {"$in": ["saima", "mepa"]}}):
        cod = p.get("codice_articolo")
        k = smart_key(p.get("nome"), cod)
        if not k:
            continue
        fonte = p.get("fonte") or "catalogo_web"
        merge(
            k,
            p.get("nome"),
            fonte,
            codice=cod,
            fornitore=p.get("fornitore"),
            categoria=p.get("categoria"),
            unita_misura=p.get("unita_confezione"),
            immagine_url=p.get("immagine_url"),
            link_prodotto=p.get("link_prodotto"),
        )

    # Persisti — usa upsert + cleanup per essere idempotente e concurrent-safe
    from datetime import timedelta as _timedelta
    from app.lotti.routers.utils import parse_data_flessibile

    def _parse_data_fattura(s):
        """Alias verso il parser condiviso (ritorna date)."""
        return parse_data_flessibile(s)

    oggi = datetime.now(timezone.utc).date()
    limite_90gg = oggi - _timedelta(days=90)

    # Dizionario canonico condiviso (una sola lettura, riusato per tutti i prodotti)
    diz_canonico = await _carica_dizionario_canonico()

    docs = []
    for m in master.values():
        m["aliases"] = sorted(list(m["aliases"]))[:20]
        m["codici"] = sorted(list(m["codici"]))[:10]
        m["fornitori"] = sorted(list(m["fornitori"]))[:10]
        m["categorie"] = sorted(list(m["categorie"]))[:5]
        m["fonti"] = sorted(list(m["fonti"]))

        # ── NOME CANONICO DAL DIZIONARIO CONDIVISO ────────────────────────────
        # Se una delle descrizioni grezze (aliases) è riconosciuta dal dizionario,
        # usa quel nome canonico: così "CAT.A UOVA FRESCHE COD.3" diventa "Uova
        # Fresche" e combacia con i lotti fornitori e le ricette. Altrimenti tiene
        # il nome leggibile già calcolato (title-case della descrizione).
        # IMPORTANTE: MAI cercare il canonico su un alias che è spazzatura (righe
        # non-prodotto: "Documento", "Nota di credito", "Vassoio...", "Intervento
        # lavori"...) — la ricerca nel dizionario fa un match "ripulito" abbastanza
        # aggressivo da poter agganciare per sbaglio un ingrediente vero non
        # correlato (bug reale trovato 01/07/2026: "vassoio stella trasp." ->
        # "Tè", "tovaglioi decor natal." -> "Aglio"). Un alias spazzatura resta col
        # suo nome leggibile grezzo, che il filtro _RX_NON_ORDINABILI su
        # nome_canonico riconosce correttamente come non ordinabile.
        _canc = ""
        for _alias in m["aliases"]:
            if _e_spazzatura(_alias):
                continue
            _canc = _canonico_da_dizionario(_alias, diz_canonico)
            if _canc:
                break
        if _canc:
            m["nome_canonico"] = _canc
            m["canonico_da_dizionario"] = True
        else:
            m["canonico_da_dizionario"] = False

        # ── MIGLIOR PREZZO SOLO ULTIMI 90 GIORNI ──────────────────────────────
        # I prezzi vecchi (2023/2024) non valgono: i listini cambiano.
        # Cerco il prezzo più basso TRA QUELLI con data negli ultimi 90 giorni.
        prezzi_recenti = []
        for ps in m["prezzi_storici"]:
            d = _parse_data_fattura(ps.get("data"))
            if d and d >= limite_90gg and (ps.get("prezzo") or 0) > 0:
                prezzi_recenti.append({**ps, "_data": d})

        if prezzi_recenti:
            # Miglior prezzo = più basso tra i recenti, scartando gli outlier
            # implausibili (stesso bug/fix di listino.py "Birra Corona 0,37€":
            # un min() cieco farebbe vincere per sempre un singolo prezzo-
            # fattura errato come "miglior prezzo" del comparatore).
            from app.lotti.routers.utils import valore_affidabile
            migliore = valore_affidabile(prezzi_recenti, chiave="prezzo")
            m["miglior_prezzo_90gg"] = round(migliore["prezzo"], 4)
            m["miglior_fornitore_90gg"] = migliore.get("fornitore", "")
            m["miglior_prezzo_data"] = migliore.get("data", "")
            # Ultimo prezzo = il più recente per data
            piu_recente = max(prezzi_recenti, key=lambda x: x["_data"])
            m["ultimo_prezzo"] = round(piu_recente["prezzo"], 4)
            m["ha_prezzo_recente"] = True
        else:
            # Nessun prezzo negli ultimi 90gg: segnalo che il dato è vecchio
            m["miglior_prezzo_90gg"] = None
            m["miglior_fornitore_90gg"] = ""
            m["miglior_prezzo_data"] = ""
            m["ha_prezzo_recente"] = False

        # ── AUMENTO PREZZO: confronto ultimo vs precedente ────────────────────
        # Ordino TUTTI i prezzi per data e confronto gli ultimi due con prezzo valido.
        tutti_con_data = sorted(
            [{**ps, "_d": _parse_data_fattura(ps.get("data"))} for ps in m["prezzi_storici"] if (ps.get("prezzo") or 0) > 0],
            key=lambda x: x["_d"] or oggi,
        )
        m["aumento_pct"] = None
        m["prezzo_precedente"] = None
        if len(tutti_con_data) >= 2:
            ultimo_p = tutti_con_data[-1]["prezzo"]
            prec_p = tutti_con_data[-2]["prezzo"]
            if prec_p > 0:
                variazione = round((ultimo_p - prec_p) / prec_p * 100, 1)
                m["aumento_pct"] = variazione  # positivo=aumento, negativo=calo
                m["prezzo_precedente"] = round(prec_p, 4)

        # Storico prezzi: lo tengo PER FORNITORE (i 4 più recenti di ciascuno),
        # non i 30 più recenti in assoluto. Così un fornitore più economico ma
        # fatturato di rado NON viene buttato fuori dal comparatore: la promessa
        # "miglior prezzo tra più fornitori" regge davvero (Enzo 14/06/2026).
        _per_forn: dict = {}
        for ps in m["prezzi_storici"]:
            _per_forn.setdefault((ps.get("fornitore", ""), ps.get("fonte", "")), []).append(ps)
        _tenuti = []
        for _gruppo in _per_forn.values():
            _gruppo.sort(key=lambda x: _parse_data_fattura(x.get("data")) or oggi, reverse=True)
            _tenuti.extend(_gruppo[:4])
        m["prezzi_storici"] = sorted(
            _tenuti,
            key=lambda x: _parse_data_fattura(x.get("data")) or oggi,
            reverse=True,
        )
        m["updated_at"] = datetime.now(timezone.utc).isoformat()
        # Categoria merceologica + flag ordinabile (calcolati una volta, validi ovunque):
        # la pagina Ordini mostra solo gli ordinabili, divisi per categoria.
        _nome_cat = m.get("nome_canonico") or m.get("key") or ""
        m["categoria_merce"] = _categoria_merce(_nome_cat, m.get("categorie"))
        m["ordinabile"] = not _e_spazzatura(_nome_cat)
        docs.append(m)

    # Crea indice unique su key ASSICURANDO prima la dedup dei documenti esistenti
    # Se l'indice unique esiste già su una collection con duplicati, create_index fallisce.
    try:
        existing_indexes = await db.prodotti_master.index_information()
        if "key_1" not in existing_indexes:
            # Dedup documenti esistenti via pipeline ($group mantiene il primo per key)
            await db.prodotti_master.delete_many({"key": None})
            # Trova duplicati e tieni solo il primo
            pipeline_dedup = [
                {"$group": {"_id": "$key", "first_id": {"$first": "$_id"}, "count": {"$sum": 1}}},
                {"$match": {"count": {"$gt": 1}}},
            ]
            async for g in db.prodotti_master.aggregate(pipeline_dedup):
                await db.prodotti_master.delete_many(
                    {"key": g["_id"], "_id": {"$ne": g["first_id"]}}
                )
            await db.prodotti_master.create_index("key", unique=True)
            await db.prodotti_master.create_index("nome_canonico")
            await db.prodotti_master.create_index([("aliases", 1)])
            await db.prodotti_master.create_index([("codici", 1)])
            await db.prodotti_master.create_index([("fonti", 1)])
    except Exception as _ie:
        logger.debug("[prodotti_master] errore non bloccante ignorato")

    # Set di tutte le key ricalcolate
    keys_attuali = {m["key"] for m in docs}

    # Upsert tutti i documenti (concurrent-safe grazie all'indice unique)
    from pymongo import UpdateOne

    if docs:
        ops = [
            UpdateOne(
                {"key": d["key"]},
                {"$set": d, "$setOnInsert": {"created_at": d["updated_at"]}},
                upsert=True,
            )
            for d in docs
        ]
        for i in range(0, len(ops), 500):
            await db.prodotti_master.bulk_write(ops[i : i + 500], ordered=False)

    # Elimina documenti stale (key non più nelle fonti)
    if keys_attuali:
        await db.prodotti_master.delete_many({"key": {"$nin": list(keys_attuali)}})

    totale_finale = await db.prodotti_master.count_documents({})
    return {"ok": True, "totale": totale_finale, "elaborate": len(docs)}


async def _run_rebuild_background():
    """Esegue il rebuild salvando lo stato in sync_status (per il polling)."""
    await db.sync_status.update_one(
        {"_id": "rebuild_master"},
        {"$set": {"stato": "in_corso", "iniziato": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    try:
        res = await _esegui_rebuild()
        await db.sync_status.update_one(
            {"_id": "rebuild_master"},
            {"$set": {"stato": "completato", "fine": datetime.now(timezone.utc).isoformat(), **res}},
            upsert=True,
        )
    except Exception as e:
        logger.exception("[prodotti-master] rebuild background fallito")
        await db.sync_status.update_one(
            {"_id": "rebuild_master"},
            {"$set": {"stato": "errore", "errore": str(e)[:300], "fine": datetime.now(timezone.utc).isoformat()}},
            upsert=True,
        )


@router.post("/rebuild")
async def rebuild(background: BackgroundTasks):
    """Avvia il rebuild del catalogo in background (l'operazione è pesante e supererebbe
    il timeout HTTP). Risponde subito; lo stato si legge da GET /prodotti-master/stato-rebuild."""
    background.add_task(_run_rebuild_background)
    return {"avviato": True, "messaggio": "Rebuild avviato in background. Controlla lo stato."}




@router.post("/collega-righe-fatture")
async def collega_righe_fatture():
    """Aggancia ogni riga fattura (fatture.prodotti[]) al catalogo: scrive
    prodotto_key = key_canonica(descrizione) — la STESSA chiave usata dal rebuild,
    quindi la riga punta al prodotto master corrispondente — e, quando risolvibile,
    nome_canonico dal dizionario. Le righe non-prodotto (servizi/riferimenti/non-food)
    sono marcate riga_non_prodotto=True così non risultano "non collegate".
    Bulk e idempotente. Carica i doc prima di scrivere (no cursore lettura+scrittura)."""
    from pymongo import UpdateOne

    diz = await _carica_dizionario_canonico()
    _fornitori_esclusi_docs = await db.fornitori.find(
        {"$or": [{"escluso": True}, {"tipo_fornitura": "escluso"}]}, {"nome": 1}
    ).to_list(5000)
    _fornitori_esclusi = {(d.get("nome") or "").strip().lower() for d in _fornitori_esclusi_docs}
    docs = await db.fatture.find({}, {"_id": 1, "prodotti": 1, "fornitore": 1}).to_list(20000)
    ops = []
    fatture_agg = righe_link = righe_nonprod = 0
    for f in docs:
        if (f.get("fornitore") or "").strip().lower() in _fornitori_esclusi:
            continue
        prods = f.get("prodotti") or []
        changed = False
        for r in prods:
            if not isinstance(r, dict):
                continue
            desc = (r.get("descrizione") or r.get("nome") or "").strip()
            if not desc:
                continue
            if _e_spazzatura(desc):
                if not r.get("riga_non_prodotto"):
                    r["riga_non_prodotto"] = True
                    changed = True
                righe_nonprod += 1
                continue
            k = key_canonica(desc)
            if k and r.get("prodotto_key") != k:
                r["prodotto_key"] = k
                changed = True
            if not r.get("nome_canonico"):
                can = _canonico_da_dizionario(desc, diz)
                if can:
                    r["nome_canonico"] = can
                    changed = True
            righe_link += 1
        if changed:
            ops.append(UpdateOne({"_id": f["_id"]}, {"$set": {"prodotti": prods}}))
        if len(ops) >= 300:
            await db.fatture.bulk_write(ops, ordered=False)
            fatture_agg += len(ops)
            ops = []
    if ops:
        await db.fatture.bulk_write(ops, ordered=False)
        fatture_agg += len(ops)
    return {
        "ok": True,
        "fatture_totali": len(docs),
        "fatture_aggiornate": fatture_agg,
        "righe_collegate": righe_link,
        "righe_non_prodotto": righe_nonprod,
    }
