"""
Router per utility: allergeni, calcola-scadenza, stats, scadenze-ingredienti,
importa-dati-iniziali, aggiorna-materie-da-fatture, esporta/importa ricette,
registro-lotti-asl, registro-tracciabilita, pulizia-dati.
"""

import re
import unicodedata
from datetime import datetime, timezone, timedelta, date

from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import HTMLResponse, Response
from app.lotti.auth import require_admin

from app.lotti.db import database as db

router = APIRouter(tags=["Utils"])


# ════════════════════════════════════════════════════════════════════════════
# HELPER CONDIVISI — usare questi invece di ridefinirli in ogni router.
# Centralizzati per evitare versioni divergenti (una correzione vale ovunque).
# ════════════════════════════════════════════════════════════════════════════

# Filtro CANONICO "lotto ancora attivo/in giro". Un lotto è finito in TRE modi
# diversi nei dati (debito storico): stato testuale (smaltito/esaurito), flag
# esaurito=True (svuotato in FIFO), flag consumato=True. Chi ne controlla solo
# uno o due lascia passare lotti già finiti (es. la ricerca globale mostrava
# gli smaltiti come attivi). USARE SEMPRE questo, mai reinventarlo nel router.
FILTRO_LOTTO_APERTO = {
    "stato": {"$nin": ["smaltito", "esaurito"]},
    "esaurito": {"$ne": True},
    "consumato": {"$ne": True},
}

# Reparto bar: bevande/alcolici che si comprano e confrontano a CARTONE/UNITÀ,
# MAI a kg/litro (regola Enzo: un rum da 2L si paga a bottiglia). Fonte UNICA
# della regola — prima era duplicata in food_cost.py (rischio: aggiungerne una
# in un file e non nell'altro la faceva tornare a €/kg).
CATEGORIE_BEVANDE_A_UNITA = {
    "ACQUA", "BIRRE", "VINO", "PROSECCO", "LIQUORI", "AMARI", "SCIROPPI",
    "SUCCHI", "BIBITE",
}


def parse_data_flessibile(s, come_datetime: bool = False):
    """Parsa una data in vari formati (gg/mm/aaaa, ISO, gg-mm-aaaa) in modo robusto.
    Ritorna un oggetto date (default) o datetime se come_datetime=True, oppure None.

    È la versione unica che sostituisce i parser sparsi in analisi_ordini, fornitori,
    lotti_produzione, prodotti_master (formati fattura italiani + ISO con orario).
    """
    if not s:
        return None
    txt = str(s).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            d = datetime.strptime(txt[:10], fmt)
            return d if come_datetime else d.date()
        except Exception:
            continue
    # ISO con eventuale orario / Z
    try:
        d = datetime.fromisoformat(txt.replace("Z", "+00:00"))
        return d.replace(tzinfo=None) if come_datetime else d.date()
    except Exception:
        return None


def stems_ricerca(q: str) -> list:
    """Radici condivise per la ricerca prodotti: unifica singolare/plurale.
    'margarina' -> 'margarin' (matcha margarine/margarina), 'nocciole' -> 'nocciol'.
    Parole corte (<4) restano intere. Max 6 token. UNICO motore per tutte le ricerche."""
    out = []
    for w in re.sub(r"[^\w\s]", " ", (q or "").lower()).split():
        if len(w) < 2:
            continue
        out.append(w[:-1] if len(w) > 3 and w[-1] in "aeiou" else w)
    return out[:6]


def _norm(s):
    """Normalizzazione leggera condivisa: spazi compressi, lowercase."""
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def valore_affidabile(items: list, chiave=None):
    """Sceglie il valore più basso da una lista, scartando gli outlier
    implausibili: se il minimo è sproporzionato (oltre 8x più basso della
    mediana) è quasi certamente un errore isolato in una fattura (es. un
    cartone da 24 birre scritto "0,37€" invece del prezzo vero), non un vero
    sconto — in quel caso si usa l'elemento mediano invece del minimo.
    `items`: lista di numeri, oppure di dict/tuple se si passa `chiave`
    (es. "prezzo" o l'indice 1 di una tupla (fornitore, prezzo)) per estrarre
    il valore da confrontare. Ritorna l'ELEMENTO scelto intero (non solo il
    valore), None se la lista è vuota.
    UNICO motore anti-outlier prezzi: sostituisce le versioni locali
    divergenti scoperte in listino.py (sync_da_fatture/_calcola_righe/import
    fattura) e prodotti_master.py (rebuild comparatore 90gg) — stesso bug in
    più punti (scoperto 02/07/2026, "Birra Corona 0,37€"), helper unico ora."""
    if not items:
        return None
    get = (lambda x: x[chiave]) if chiave is not None else (lambda x: x)
    ordinati = sorted(items, key=get)
    minimo = get(ordinati[0])
    mediana = get(ordinati[len(ordinati) // 2])
    if len(ordinati) > 1 and mediana > 0 and minimo < mediana / 8:
        return ordinati[len(ordinati) // 2]
    return ordinati[0]


def normalizza_nome(nome) -> str:
    """Normalizza un nome prodotto per confronti e raggruppamenti:
    minuscolo, senza spazi superflui. Versione unica condivisa tra i router."""
    return (nome or "").strip().lower()


async def prezzi_fatture_per_fornitore(db_conn, fornitore_match: str) -> dict:
    """Costruisce una mappa {descrizione_normalizzata: {prezzo, quantita, data}} dalle
    righe delle fatture di un fornitore. Serve ad agganciare al catalogo (SAIMA/MEPA/
    Acquaviva) il prezzo realmente pagato: se un prodotto del catalogo è già stato
    comprato, mostriamo il suo prezzo dalla fattura. I nomi del catalogo ufficiale e
    delle fatture coincidono quasi sempre, quindi il match per nome è affidabile.

    fornitore_match: sottostringa (lowercase) per riconoscere il fornitore
    (es. "saima", "mepa", "acquaviva").
    """
    prezzi = {}
    # supporta più alternative separate da "|" (es. "acquaviva|vandemoortele|alpha")
    alternative = [a.strip() for a in (fornitore_match or "").lower().split("|") if a.strip()]
    async for f in db_conn.fatture.find(
        {}, {"_id": 0, "fornitore": 1, "data_fattura": 1, "prodotti": 1}
    ):
        forn = (f.get("fornitore") or "").lower()
        if alternative and not any(a in forn for a in alternative):
            continue
        data = f.get("data_fattura", "")
        # data_fattura è in formati misti (dd/mm/yyyy e ISO): "più recente" va
        # deciso su date VERE, non sulle stringhe ("30/06/2026" > "05/07/2026"
        # lessicograficamente — sceglieva il prezzo vecchio).
        data_ord = parse_data_flessibile(data) or date.min
        for p in f.get("prodotti", []):
            desc = _norm(p.get("descrizione"))
            try:
                prezzo = float(p.get("prezzo") or 0)
            except (ValueError, TypeError):
                prezzo = 0
            if not desc or prezzo <= 0:
                continue
            try:
                qta = float(p.get("quantita") or 0)
            except (ValueError, TypeError):
                qta = 0
            voce = {"prezzo": prezzo, "quantita": qta, "data": data, "_data_ord": data_ord}
            # tieni il più recente per descrizione
            prev = prezzi.get(desc)
            if not prev or data_ord > prev["_data_ord"]:
                prezzi[desc] = voce
            # indicizza ANCHE per codice articolo del fornitore (riga XML
            # CodiceArticolo/CodiceValore): stesso codice dei suoi cataloghi →
            # match deterministico, senza dipendere da come è scritto il nome.
            cod = _norm_codice_articolo(p.get("codice_articolo"))
            if cod:
                chiave_cod = f"codart::{cod}"
                prev_c = prezzi.get(chiave_cod)
                if not prev_c or data_ord > prev_c["_data_ord"]:
                    prezzi[chiave_cod] = voce
    for v in prezzi.values():  # chiave di servizio: non deve uscire dall'helper
        v.pop("_data_ord", None)
    return prezzi


def _norm_codice_articolo(cod) -> str:
    """Normalizza un codice articolo per il confronto catalogo<->fattura:
    maiuscolo, senza spazi, senza zeri iniziali ('0862' e '862' sono lo
    stesso codice). Codici troppo corti dopo la pulizia = inaffidabili."""
    s = str(cod or "").strip().upper().replace(" ", "").lstrip("0")
    return s if len(s) >= 2 else ""


def applica_prezzo_da_fatture(prodotti: list, prezzi: dict) -> list:
    """Per ogni prodotto del catalogo imposta prezzo e flag gia_acquistato SOLO se
    corrisponde davvero a una riga di fattura. Ordine dei match (dal più sicuro):
    1. CODICE ARTICOLO del fornitore (riga XML CodiceArticolo == codice del suo
       catalogo) — deterministico, non dipende da come è scritto il nome;
    2. nome normalizzato esatto;
    3. forte sovrapposizione di parole significative (Jaccard alto + coverage).
    Niente match su sottostringa, che assegnava lo stesso prezzo a prodotti
    diversi. I prodotti non trovati restano invariati (ordinabili senza prezzo)."""
    _STOP = {"da", "di", "in", "kg", "gr", "g", "lt", "l", "ml", "cf", "pz", "x",
             "confezione", "conf", "al", "alla", "con", "per", "e"}

    def _tok(s):
        # accenti via ("Davì"/"Jolì" in catalogo vs "davi"/"joli" in fattura):
        # senza questa normalizzazione il match fallisce su nomi identici
        s = unicodedata.normalize("NFKD", _norm(s)).encode("ascii", "ignore").decode("ascii")
        s = re.sub(r"[^\w\s]", " ", s)
        return {w for w in s.split() if len(w) >= 3 and w not in _STOP and not w.isdigit()}

    if not prezzi:
        # nessun acquisto per questo fornitore: nessun prodotto è "già acquistato"
        for prod in prodotti:
            prod["prezzo_listino"] = 0
            prod["prezzo_acquisto_confezione"] = 0
            prod["prezzo_singolo"] = 0
            prod["prezzo_fattura"] = 0
            prod["gia_acquistato"] = False
        return prodotti
    # le chiavi "codart::" servono SOLO al match per codice: fuori dall'indice fuzzy
    index = [(_tok(k), k, v) for k, v in prezzi.items() if not k.startswith("codart::")]
    matches = {}
    candidati_fuzzy = []
    for pos, prod in enumerate(prodotti):
        # 1) tutti i codici vecchi/nuovi/alias del fornitore, non uno soltanto.
        codici = [prod.get(c) for c in ("codice_articolo", "codice", "codice_aqv_2025", "codice_aqv_2026")]
        codici.extend(prod.get("codici_alias") or [])
        match = None
        for valore in codici:
            cod = _norm_codice_articolo(valore)
            if cod and prezzi.get(f"codart::{cod}"):
                match = prezzi[f"codart::{cod}"]
                break
        nome_n = _norm(prod.get("nome") or prod.get("nome_display") or "")
        # 2) nome ufficiale o descrizione fattura dichiarata esplicitamente.
        if not match and nome_n:
            match = prezzi.get(nome_n)
        if not match:
            for alias in prod.get("alias_fattura") or []:
                match = prezzi.get(_norm(alias))
                if match:
                    break
        if match:
            matches[pos] = match
            continue
        # 3) fuzzy conservativo e uno-a-uno. Prima raccogliamo tutti i candidati,
        # poi ogni riga fattura può essere assegnata a un solo prodotto: evita
        # che lo stesso prezzo (es. pistacchio) compaia su tre varianti diverse.
        nt = _tok(nome_n)
        if len(nt) >= 2:
            for ft, chiave, voce in index:
                if not ft:
                    continue
                inter = len(nt & ft)
                if not inter:
                    continue
                jacc = inter / len(nt | ft)
                copertura_prodotto = inter / len(nt)
                copertura_fattura = inter / len(ft)
                if jacc >= 0.72 and copertura_prodotto >= 0.75 and copertura_fattura >= 0.65:
                    candidati_fuzzy.append((jacc, min(copertura_prodotto, copertura_fattura), pos, chiave, voce))

    usati_prodotti, usate_righe = set(matches), set()
    for _score, _coverage, pos, chiave, voce in sorted(
        candidati_fuzzy, key=lambda c: (c[0], c[1]), reverse=True
    ):
        if pos in usati_prodotti or chiave in usate_righe:
            continue
        matches[pos] = voce
        usati_prodotti.add(pos)
        usate_righe.add(chiave)

    for pos, prod in enumerate(prodotti):
        match = matches.get(pos)
        if match and match.get("prezzo", 0) > 0:
            prezzo = round(float(match["prezzo"]), 4)
            prod["prezzo_listino"] = prezzo
            prod["prezzo_acquisto_confezione"] = prezzo
            prod["prezzo_fattura"] = prezzo
            prod["prezzo_fattura_fonte"] = "fattura_xml"
            prod["gia_acquistato"] = True
            prod["prezzo_fattura_data"] = match.get("data", "")
            # quantità dell'ultima riga fattura (es. cartoni/pezzi comprati):
            # a colpo d'occhio nei cataloghi si vede anche QUANTO si è comprato
            prod["quantita_ultima_fattura"] = match.get("quantita", 0)
        else:
            # non comprato → nessun prezzo (sovrascrive eventuali vecchi prezzi-listino)
            prod["prezzo_listino"] = 0
            prod["prezzo_acquisto_confezione"] = 0
            prod["prezzo_singolo"] = 0
            prod["prezzo_fattura"] = 0
            prod["gia_acquistato"] = False
    return prodotti


# MongoDB connection
def set_database(database):
    """Permette override del db dall'esterno (compatibilità)."""
    global db
    db = database


# ── Allergeni (inline, piccoli dict locali) ──────────────────────────────────

_ALLERGENI_KEYS = {
    "glutine": {
        "nome": "Cereali contenenti GLUTINE",
        "keywords": [
            "glutine",
            "grano",
            "frumento",
            "farina",
            "semola",
            "orzo",
            "segale",
            "avena",
            "farro",
            "malto",
            "pangrattato",
            "farina 00",
            "farina 0",
            "tipo 00",
            "spaghetti",
            "paccheri",
            "maccheroni",
            "pasta di grano",
            "pasta di semola",
            "couscous",
            "bulgur",
        ],
    },
    "uova": {
        "nome": "UOVA e derivati",
        "keywords": ["uova", "uovo", "tuorlo", "albume", "ovoprodotti", "maionese", "zabaione"],
    },
    "latte": {
        "nome": "LATTE e derivati (incluso lattosio)",
        "keywords": [
            "latte",
            "lattosio",
            "panna",
            "burro",
            "formaggio",
            "mozzarella",
            "ricotta",
            "mascarpone",
            "yogurt",
            "parmigiano",
            "grana",
            "pecorino",
            "caseina",
            "siero di latte",
            "crema",
            "besciamella",
        ],
    },
    "soia": {
        "nome": "SOIA e derivati",
        "keywords": ["soia", "soja", "tofu", "miso", "lecitina di soia", "proteine di soia"],
    },
    "arachidi": {
        "nome": "ARACHIDI e derivati",
        "keywords": ["arachidi", "arachide", "burro di arachidi", "olio di arachidi"],
    },
    "frutta_guscio": {
        "nome": "FRUTTA A GUSCIO",
        "keywords": [
            "mandorle",
            "mandorla",
            "nocciole",
            "nocciola",
            "noci",
            "noce",
            "pistacchi",
            "pistacchio",
            "pinoli",
            "castagne",
            "gianduia",
            "nutella",
            "pasta di nocciole",
        ],
    },
    "sesamo": {
        "nome": "SEMI DI SESAMO e derivati",
        "keywords": ["sesamo", "semi di sesamo", "tahina"],
    },
    "solfiti": {
        "nome": "ANIDRIDE SOLFOROSA e SOLFITI (>10mg/kg)",
        "keywords": ["solfiti", "anidride solforosa", "metabisolfito", "vino", "aceto"],
    },
    "pesce": {
        "nome": "PESCE e derivati",
        "keywords": [
            "pesce",
            "merluzzo",
            "salmone",
            "tonno",
            "acciuga",
            "alice",
            "sardina",
            "sgombro",
            "colatura",
        ],
    },
    "crostacei": {
        "nome": "CROSTACEI e derivati",
        "keywords": ["crostacei", "gamberi", "scampi", "aragosta", "granchio"],
    },
    "molluschi": {
        "nome": "MOLLUSCHI e derivati",
        "keywords": ["molluschi", "cozze", "vongole", "ostriche", "calamari", "polpo"],
    },
    "sedano": {"nome": "SEDANO e derivati", "keywords": ["sedano", "sedano rapa"]},
    "senape": {"nome": "SENAPE e derivati", "keywords": ["senape", "mostarda"]},
    "lupini": {"nome": "LUPINI e derivati", "keywords": ["lupini", "lupino", "farina di lupini"]},
}


def _rileva_allergeni(ingredienti: list) -> dict:
    import re
    trovati = {}
    for ing in ingredienti:
        if not ing:
            continue
        ing_l = ing.lower().strip()
        for all_id, info in _ALLERGENI_KEYS.items():
            if all_id not in trovati:
                for kw in info["keywords"]:
                    # match su PAROLA INTERA (confini di parola) per evitare falsi positivi
                    # tipo "semolato"->"semola" o "00" dentro un prezzo. Le kw multi-parola
                    # (es. "farina 00") restano gestite dal \b iniziale/finale.
                    if re.search(r"(?<![a-zà-ù])" + re.escape(kw) + r"(?![a-zà-ù])", ing_l):
                        trovati[all_id] = {"nome": info["nome"], "ingredienti": [ing]}
                        break
    nomi = [i["nome"] for i in trovati.values()]
    testo = ("Contiene: " + ", ".join(nomi)) if nomi else "Non contiene allergeni dichiarati"
    return {
        "allergeni_presenti": list(trovati.keys()),
        "allergeni_dettaglio": trovati,
        "testo_etichetta": testo,
        "contiene_allergeni": bool(trovati),
    }


def _calcola_scadenza(
    ingredienti: list,
    data_produzione: str,
    abbattuto: bool = False,
    nome_prodotto: str = "",
    metodo_conservazione: str = "frigo",
) -> tuple:
    """
    Calcola la data di scadenza usando il motore shelf_life.
    Mantiene la firma originale per compatibilità con lotti_produzione.py.

    LOGICA AGGIORNATA:
    - NON usa la data scadenza del fornitore (molti non la forniscono, es. Fiorentino)
    - Calcola la scadenza dall'ingrediente PIÙ DEPERIBILE nella ricetta
    - Considera il metodo di conservazione scelto dall'operatore:
        "ambiente"            → vetrina/banco (giorni più brevi)
        "frigo"               → frigorifero 0-4°C (default)
        "abbattitore_positivo" → abbattimento positivo 3°C (più giorni)
        "abbattitore_negativo" → freezer -18°C (settimane/mesi)
    - Se abbattuto=True (retrocompatibilità) → usa abbattitore_negativo
    """
    from app.lotti.routers.shelf_life import calcola_scadenza as _shelf_calcola

    try:
        fmt = "%d/%m/%Y" if "/" in data_produzione else "%Y-%m-%d"
        dt_prod = datetime.strptime(data_produzione, fmt).replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        dt_prod = datetime.now(timezone.utc)

    # Se abbattuto=True per retrocompatibilità
    if abbattuto:
        metodo_conservazione = "abbattitore_negativo"

    # Calcola con il nuovo motore
    result = _shelf_calcola(
        nome_prodotto=nome_prodotto,
        ingredienti=ingredienti,
        metodo_conservazione=metodo_conservazione,
        data_produzione=dt_prod,
    )

    giorni_frigo = result["giorni"]
    data_scad_frigo = result["data_scadenza"]
    ing_critico = result["ingrediente_critico"] or "prodotto generico"

    # Calcola anche la versione abbattuta (per retrocompatibilità)
    result_abb = _shelf_calcola(
        nome_prodotto=nome_prodotto,
        ingredienti=ingredienti,
        metodo_conservazione="abbattitore_negativo",
        data_produzione=dt_prod,
    )
    giorni_abb = result_abb["giorni"]
    data_scad_abb = result_abb["data_scadenza"]
    mesi_abb = giorni_abb // 30

    return (data_scad_frigo, data_scad_abb, ing_critico, giorni_frigo, giorni_abb, mesi_abb)


# ── Stats ────────────────────────────────────────────────────────────────────


@router.get("/stats")
async def get_stats():
    # materie_prime ora è lotti_fornitori (unica fonte)
    materie_count = await db.lotti_fornitori.count_documents({})
    ricette_count = await db.ricette.count_documents({})
    lotti_count = await db.lotti.count_documents({})
    fatture_count = await db.fatture.count_documents({})
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    lotti_recenti = await db.lotti.count_documents({"created_at": {"$gte": week_ago}})
    return {
        "materie_prime": materie_count,
        "ricette": ricette_count,
        "lotti_totali": lotti_count,
        "lotti_settimana": lotti_recenti,
        "fatture": fatture_count,
    }


# ── Root ─────────────────────────────────────────────────────────────────────


@router.get("/")
async def root():
    return {"message": "API Tracciabilità Lotti", "version": "1.0.0"}


# ── Importa dati iniziali ────────────────────────────────────────────────────


# ── Aggiorna materie da fatture ──────────────────────────────────────────────


@router.post("/aggiorna-materie-da-fatture")
async def aggiorna_materie_da_fatture():
    """Deprecato — le materie prime sono ora letti direttamente da lotti_fornitori."""
    count = await db.lotti_fornitori.count_documents({})
    return {
        "message": "Dati materie prime già disponibili in lotti_fornitori",
        "totale_lotti": count,
        "aggiornamenti": 0,
    }



# ── Esporta ricette ───────────────────────────────────────────────────────────


# ── Registro lotti ASL ────────────────────────────────────────────────────────


@router.get("/registro-lotti-asl", response_class=HTMLResponse)
async def genera_registro_lotti_asl(data_inizio: str = Query(...), data_fine: str = Query(...)):
    try:
        dt_inizio = datetime.strptime(data_inizio, "%Y-%m-%d")
        dt_fine = datetime.strptime(data_fine, "%Y-%m-%d")
        data_inizio_it = dt_inizio.strftime("%d/%m/%Y")
        data_fine_it = dt_fine.strftime("%d/%m/%Y")
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato data non valido. Usa YYYY-MM-DD")

    # Limite alzato 2000→50000 (audit 24/07/2026): con più di 2000 lotti in
    # archivio il registro ASL perdeva i più VECCHI in silenzio (il registro
    # mensile usa già 50000: stessa completezza).
    lotti = await db.lotti.find({}, {"_id": 0}).sort("created_at", -1).to_list(50000)
    lotti_filtrati = []
    for lotto in lotti:
        # Salta lotti senza prodotto valido (es. colazione acquaviva registrata in vendite_banco)
        prodotto = (lotto.get("prodotto") or lotto.get("prodotto_nome") or "").strip()
        if not prodotto or prodotto == "-":
            continue
        data_prod = lotto.get("data_produzione", "")
        try:
            fmt = "%d/%m/%Y" if "/" in data_prod else "%Y-%m-%d"
            dt_lotto = datetime.strptime(data_prod, fmt)
            if dt_inizio <= dt_lotto <= dt_fine:
                lotti_filtrati.append(lotto)
        except (ValueError, TypeError):
            continue
    lotti_filtrati.sort(key=lambda x: x.get("data_produzione", ""), reverse=True)

    rows_html = ""
    for idx, lotto in enumerate(lotti_filtrati, 1):
        ingredienti = lotto.get("ingredienti_dettaglio", [])[:5]
        ing_text = "; ".join([i.split(" - ")[0][:35] for i in ingredienti]) if ingredienti else "-"
        allergeni = lotto.get("allergeni_testo", "")
        allergeni_display = (
            "-"
            if (not allergeni or "Non contiene" in allergeni)
            else allergeni.replace("Contiene: ", "")
        )
        alert_class = ' class="allergeni"' if allergeni_display != "-" else ""
        prodotto_display = (
            lotto.get("prodotto") or lotto.get("prodotto_nome") or "-"
        ).strip() or "-"
        rows_html += f"""<tr>
            <td class="center">{idx}</td>
            <td class="center">{lotto.get('data_produzione','-')}</td>
            <td><strong>{prodotto_display}</strong></td>
            <td class="mono center">{lotto.get('numero_lotto','-')}</td>
            <td class="center">{lotto.get('quantita',1)} {lotto.get('unita_misura','pz')}</td>
            <td class="center">{lotto.get('data_scadenza','-')}</td>
            <td class="center">{lotto.get('scadenza_abbattuto','-') if lotto.get('scadenza_abbattuto') else '-'}</td>
            <td class="small">{ing_text}</td>
            <td{alert_class}>{allergeni_display}</td>
        </tr>"""

    total = len(lotti_filtrati)
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M")

    return HTMLResponse(content=f"""<!DOCTYPE html><html lang="it"><head>
<meta charset="UTF-8"><title>Registro Lotti ASL - {data_inizio_it} / {data_fine_it}</title>
<style>
@page {{ size: A4 landscape; margin: 12mm 10mm; }}
*{{ margin:0;padding:0;box-sizing:border-box; }}
body {{ font-family: Arial,sans-serif; font-size:9px; color:#1a1a2e; }}
.print-bar {{ display:flex;justify-content:space-between;align-items:center;padding:12px 16px;background:#1a1a2e;margin-bottom:14px;border-radius:8px; }}
.print-bar h2 {{ color:#fff;font-size:14px; }}
.btn-print {{ background:#f59e0b;color:#fff;border:none;padding:8px 20px;border-radius:6px;font-size:12px;font-weight:600;cursor:pointer; }}
@media print {{ .print-bar {{ display:none; }} }}
.doc-header {{ border-bottom:3px solid #1a1a2e;padding-bottom:10px;margin-bottom:12px;display:flex;justify-content:space-between;align-items:flex-end; }}
.doc-title h1 {{ font-size:16px;font-weight:700;text-transform:uppercase; }}
.doc-meta {{ text-align:right;font-size:9px;color:#444;line-height:1.7; }}
.summary-bar {{ display:flex;gap:12px;margin-bottom:12px; }}
.summary-box {{ flex:1;background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;padding:8px 12px; }}
.summary-box .val {{ font-size:18px;font-weight:700;color:#1a1a2e; }}
.summary-box .lbl {{ font-size:8px;color:#666; }}
table {{ width:100%;border-collapse:collapse;font-size:8.5px; }}
thead {{ background:#1a1a2e;color:#fff; }}
thead th {{ padding:6px 5px;text-align:left;font-weight:600;font-size:8px;text-transform:uppercase; }}
tbody tr {{ border-bottom:1px solid #e8eaf0; }}
tbody tr:nth-child(even) {{ background:#f9fafb; }}
td {{ padding:5px;vertical-align:top; }}
td.center {{ text-align:center; }}
td.mono {{ font-family:monospace;font-weight:700;background:#f1f5f9;border-radius:3px;font-size:9px; }}
td.small {{ font-size:7.5px;color:#555; }}
td.allergeni {{ color:#dc2626;font-weight:600;font-size:8px; }}
.footer {{ margin-top:20px;padding-top:12px;border-top:2px solid #1a1a2e;display:grid;grid-template-columns:1fr 1fr 1fr;gap:20px;font-size:8.5px; }}
.firma-line {{ border-bottom:1px solid #333;height:30px;margin-top:6px; }}
</style></head><body>
<div class="print-bar"><h2>Registro Lotti ASL — {data_inizio_it} / {data_fine_it}</h2>
<button class="btn-print" onclick="window.print()">Stampa / Salva PDF</button></div>
<div class="doc-header">
<div class="doc-title"><h1>Registro Tracciabilità Lotti di Produzione</h1>
<p style="font-size:9px;margin-top:3px">Ai sensi del Reg. CE 178/2002 e Reg. CE 852/2004</p></div>
<div class="doc-meta">
<div><strong>Azienda:</strong> Ceraldi Group S.R.L.</div>
<div><strong>Indirizzo:</strong> Piazza Carità 14, 80134 Napoli (NA)</div>
<div><strong>Periodo:</strong> {data_inizio_it} — {data_fine_it}</div>
<div><strong>Stampa:</strong> {now_str}</div></div></div>
<div class="summary-bar">
<div class="summary-box"><div class="val">{total}</div><div class="lbl">Lotti nel periodo</div></div>
<div class="summary-box"><div class="val">{len(set(item.get('prodotto','') for item in lotti_filtrati))}</div><div class="lbl">Prodotti distinti</div></div>
<div class="summary-box"><div class="val">{len([item for item in lotti_filtrati if item.get('allergeni_testo') and 'Non contiene' not in item.get('allergeni_testo','')])}</div><div class="lbl">Con allergeni</div></div>
<div class="summary-box"><div class="val">{(dt_fine-dt_inizio).days+1}</div><div class="lbl">Giorni coperti</div></div></div>
<table><thead><tr>
<th style="width:3%">N°</th><th style="width:8%">Data Prod.</th><th style="width:14%">Prodotto</th>
<th style="width:14%">Codice Lotto</th><th style="width:6%">Quantità</th><th style="width:8%">Scad. Frigo</th>
<th style="width:8%">Scad. Abbatt.</th><th style="width:24%">Ingredienti</th><th style="width:15%">Allergeni</th>
</tr></thead><tbody>{'<tr><td colspan="9" style="text-align:center;padding:30px;color:#999">Nessun lotto nel periodo selezionato</td></tr>' if total==0 else rows_html}</tbody></table>
<div class="footer">
<div><strong>Firma Responsabile Produzione</strong><div class="firma-line"></div><p style="margin-top:4px;font-size:8px">Nome e Cognome: ______________________</p></div>
<div><strong>Firma Responsabile HACCP</strong><div class="firma-line"></div><p style="margin-top:4px;font-size:8px">Nome e Cognome: ______________________</p></div>
<div><strong>Firma Ispettore ASL</strong><div class="firma-line"></div><p style="margin-top:4px;font-size:8px">Data ispezione: ______________________</p></div>
</div>
<p style="font-size:7.5px;color:#666;margin-top:12px">Conservare il presente registro per almeno 5 anni.</p>
</body></html>""")


# ── Registro tracciabilità ────────────────────────────────────────────────────


def _nome_ingrediente(ing) -> str:
    """`ricette.ingredienti` è una lista di NOMI (stringhe), ma alcune ricette
    importate/proposte possono portarci dentro un dizionario
    {nome, quantita, unita}: senza questo, un solo dizionario faceva fallire
    con errore 500 l'INTERO registro di tracciabilità richiesto dall'ASL."""
    if isinstance(ing, dict):
        return str(ing.get("nome") or "")
    return str(ing or "")


@router.get("/registro-tracciabilita", response_class=HTMLResponse)
async def get_registro_tracciabilita():
    """Genera il registro di tracciabilità fatture-ricette (Reg. CE 178/2002)"""
    fornitori_esclusi_docs = await db.fornitori.find({"escluso": True}, {"nome": 1}).to_list(1000)
    nomi_esclusi = {f["nome"].lower().strip() for f in fornitori_esclusi_docs}
    fatture = await db.fatture.find({}, {"_id": 0}).sort("data_fattura", -1).to_list(50000)
    fatture = [f for f in fatture if f.get("fornitore", "").lower().strip() not in nomi_esclusi]
    ricette = await db.ricette.find({}, {"_id": 0}).to_list(5000)

    ingrediente_ricette = {}
    for ricetta in ricette:
        for ing in ricetta.get("ingredienti", []):
            for parola in [p for p in _nome_ingrediente(ing).lower().split() if len(p) > 3]:
                ingrediente_ricette.setdefault(parola, set()).add(ricetta.get("nome", ""))

    registro = []
    prodotti_utilizzati = set()
    for fattura in fatture:
        fornitore = fattura.get("fornitore", "N/A")
        data_fattura = fattura.get("data_fattura", "N/A")
        numero_fattura = fattura.get("numero_fattura", "N/A")
        for prodotto in fattura.get("prodotti", []):
            desc = prodotto.get("descrizione", "")
            ricette_correlate = set()
            for parola in [p for p in desc.lower().split() if len(p) > 3]:
                for chiave, ricette_set in ingrediente_ricette.items():
                    if parola in chiave or chiave in parola:
                        ricette_correlate.update(ricette_set)
            if ricette_correlate:
                prodotti_utilizzati.add(desc)
                registro.append(
                    {
                        "fornitore": fornitore,
                        "data_fattura": data_fattura,
                        "numero_fattura": numero_fattura,
                        "prodotto": desc,
                        "quantita": prodotto.get("quantita", ""),
                        "ricette": list(ricette_correlate)[:10],
                    }
                )

    # AUDIT_REGISTRI_STAMPE §5: la stampa mostra al massimo 500 righe mentre le
    # statistiche in testa dichiarano il totale VERO. Prima nessuno lo diceva:
    # si leggeva "1200 collegamenti" e se ne contavano 500. Ora c'è scritto.
    LIMITE_RIGHE = 500
    avviso_troncamento = ""
    if len(registro) > LIMITE_RIGHE:
        avviso_troncamento = (
            f'<div style="margin:10px 0;padding:10px 14px;background:#faf3e6;'
            f'border:1px solid #e0d2b4;border-radius:6px;font-size:9pt;color:#6f583a">'
            f'<strong>Mostrate le prime {LIMITE_RIGHE} righe di {len(registro)}.</strong> '
            f"Per l'elenco completo scarica il CSV: contiene tutti i collegamenti."
            f"</div>"
        )

    righe = ""
    for item in registro[:LIMITE_RIGHE]:
        ricette_html = "".join(
            [
                f'<span style="background:#e3f2fd;padding:2px 8px;border-radius:10px;font-size:8pt;white-space:nowrap">{r}</span>'
                for r in item["ricette"]
            ]
        )
        righe += f"""<tr>
            <td>{item['data_fattura']}</td><td>{item['fornitore']}</td>
            <td>{item['numero_fattura'][:20]}...</td><td>{item['prodotto'][:50]}...</td>
            <td>{item['quantita']}</td><td style="display:flex;flex-wrap:wrap;gap:4px">{ricette_html}</td>
        </tr>"""

    return HTMLResponse(content=f"""<!DOCTYPE html><html lang="it"><head>
<meta charset="UTF-8"><title>Registro Tracciabilità</title>
<style>@page{{size:A4 landscape;margin:10mm}}@media print{{.no-print{{display:none}}}}
body{{font-family:Arial,sans-serif;font-size:10pt;color:#333}}
.header{{text-align:center;border-bottom:3px solid #2e7d32;padding-bottom:15px;margin-bottom:20px}}
.header h1{{color:#2e7d32;margin:0;font-size:18pt}}
.stats{{display:flex;justify-content:space-around;margin:20px 0;padding:15px;background:#e8f5e9;border-radius:8px}}
.stat{{text-align:center}}.stat-value{{font-size:24pt;font-weight:bold;color:#2e7d32}}
table{{width:100%;border-collapse:collapse;margin:15px 0}}
th,td{{border:1px solid #ddd;padding:8px;text-align:left;font-size:9pt}}
th{{background:#2e7d32;color:white}}
.btn-print{{padding:12px 30px;font-size:14pt;background:#2e7d32;color:white;border:none;border-radius:5px;cursor:pointer;margin:5px}}
.footer{{margin-top:30px;text-align:center;font-size:9pt;color:#999;border-top:1px solid #ddd;padding-top:15px}}
</style></head><body>
<div class="header"><h1>REGISTRO TRACCIABILITÀ FATTURE - RICETTE</h1>
<p><strong>Ceraldi Group S.R.L.</strong> - Piazza Carità 14, 80134 Napoli (NA)</p>
<p>Generato il: {datetime.now().strftime('%d/%m/%Y alle %H:%M')}</p></div>
<div class="stats">
<div class="stat"><div class="stat-value">{len(fatture)}</div><div>FATTURE TOTALI</div></div>
<div class="stat"><div class="stat-value">{len(prodotti_utilizzati)}</div><div>PRODOTTI UTILIZZATI</div></div>
<div class="stat"><div class="stat-value">{len(ricette)}</div><div>RICETTE TOTALI</div></div>
<div class="stat"><div class="stat-value">{len(registro)}</div><div>COLLEGAMENTI</div></div></div>
<div class="no-print" style="text-align:center;margin:20px 0">
<button onclick="window.print()" class="btn-print">Stampa PDF</button>
<a href="/api/registro-tracciabilita/csv" class="btn-print" style="text-decoration:none">Scarica CSV</a></div>
<h2>Dettaglio Prodotti e Ricette Correlate</h2>
{avviso_troncamento}
<table><tr><th>Data Fattura</th><th>Fornitore</th><th>N° Fattura</th><th>Prodotto</th><th>Qtà</th><th>Ricette</th></tr>
{righe}</table>
<div class="footer"><p>Conforme a Reg. CE 178/2002 - Rintracciabilità degli alimenti</p></div>
</body></html>""")


@router.get("/registro-tracciabilita/csv")
async def get_registro_tracciabilita_csv():
    fornitori_esclusi_docs = await db.fornitori.find({"escluso": True}, {"nome": 1}).to_list(1000)
    nomi_esclusi = {f["nome"].lower().strip() for f in fornitori_esclusi_docs}
    fatture = await db.fatture.find({}, {"_id": 0}).sort("data_fattura", -1).to_list(50000)
    fatture = [f for f in fatture if f.get("fornitore", "").lower().strip() not in nomi_esclusi]
    ricette = await db.ricette.find({}, {"_id": 0}).to_list(5000)

    ingrediente_ricette = {}
    for ricetta in ricette:
        for ing in ricetta.get("ingredienti", []):
            for parola in [p for p in _nome_ingrediente(ing).lower().split() if len(p) > 3]:
                ingrediente_ricette.setdefault(parola, set()).add(ricetta.get("nome", ""))

    lines = ["Data Fattura;Fornitore;N° Fattura;Prodotto;Quantità;Prezzo;Ricette Correlate"]
    for fattura in fatture:
        for prodotto in fattura.get("prodotti", []):
            desc = prodotto.get("descrizione", "").replace(";", ",")
            ricette_correlate = set()
            for parola in [p for p in desc.lower().split() if len(p) > 3]:
                for chiave, rs in ingrediente_ricette.items():
                    if parola in chiave or chiave in parola:
                        ricette_correlate.update(rs)
            ricette_str = ", ".join(list(ricette_correlate)[:10]).replace(";", ",")
            fornitore = fattura.get("fornitore", "").replace(";", ",")
            numero = fattura.get("numero_fattura", "").replace(";", ",")
            lines.append(
                f'"{fattura.get("data_fattura","")}";"{fornitore}";"{numero}";"{desc}";"{prodotto.get("quantita","")}";"{prodotto.get("prezzo_unitario","")}";"{ricette_str}"'
            )

    filename = f"registro_tracciabilita_{datetime.now().strftime('%Y%m%d')}.csv"
    return Response(
        content="\n".join(lines).encode("utf-8-sig"),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/registro-tracciabilita/json")
async def get_registro_tracciabilita_json():
    fornitori_esclusi_docs = await db.fornitori.find({"escluso": True}, {"nome": 1}).to_list(1000)
    nomi_esclusi = {f["nome"].lower().strip() for f in fornitori_esclusi_docs}
    fatture = await db.fatture.find({}, {"_id": 0}).sort("data_fattura", -1).to_list(50000)
    fatture = [f for f in fatture if f.get("fornitore", "").lower().strip() not in nomi_esclusi]
    ricette = await db.ricette.find({}, {"_id": 0}).to_list(5000)

    ingrediente_ricette = {}
    for ricetta in ricette:
        for ing in ricetta.get("ingredienti", []):
            for parola in [p for p in _nome_ingrediente(ing).lower().split() if len(p) > 3]:
                if ricetta.get("nome", "") not in ingrediente_ricette.setdefault(parola, []):
                    ingrediente_ricette[parola].append(ricetta.get("nome", ""))

    registro = []
    for fattura in fatture:
        entry = {
            "fornitore": fattura.get("fornitore", ""),
            "data_fattura": fattura.get("data_fattura", ""),
            "numero_fattura": fattura.get("numero_fattura", ""),
            "prodotti": [],
        }
        for prodotto in fattura.get("prodotti", []):
            desc = prodotto.get("descrizione", "")
            ricette_correlate = set()
            for parola in [p for p in desc.lower().split() if len(p) > 3]:
                for chiave, rl in ingrediente_ricette.items():
                    if parola in chiave or chiave in parola:
                        ricette_correlate.update(rl)
            entry["prodotti"].append(
                {
                    "descrizione": desc,
                    "quantita": prodotto.get("quantita", ""),
                    "ricette_correlate": list(ricette_correlate)[:10],
                }
            )
        registro.append(entry)

    return {
        "azienda": "Ceraldi Group S.R.L.",
        "generato_il": datetime.now().isoformat(),
        "totale_fatture": len(fatture),
        "registro": registro,
    }


# ── Pulizia dati ──────────────────────────────────────────────────────────────


@router.post("/pulizia-dati-spazzatura")
async def pulizia_dati_spazzatura(_admin=Depends(require_admin)):
    """Rimuove dati di test/spazzatura dal database."""
    deleted = {}
    # materie_prime unificata in lotti_fornitori (03/07/2026).
    # \btest\b (parola intera): "test pinco" sì, "TESTA di vitello" NO —
    # senza confine di parola la pulizia cancellerebbe prodotti veri.
    _RX_TEST = {"$regex": r"\btest\b", "$options": "i"}
    for coll_name in ["lotti", "lotti_fornitori"]:
        coll = db[coll_name]
        result = await coll.delete_many(
            {
                "$or": [
                    {"prodotto": _RX_TEST},
                    {"prodotto_nome": _RX_TEST},
                    {"nome": _RX_TEST},
                ]
            }
        )
        deleted[coll_name] = result.deleted_count

    # ── Magazzino bar: via le righe-nota diventate prodotti (omaggi,
    #    riferimenti contabili) e i doppioni con lo stesso nome normalizzato
    #    (segnalati da Enzo 02/07/2026: "+1 CARTONE IN OMAGGIO" ecc.) ──
    from app.lotti.routers.classificatore_alimenti import e_merce_alimentare
    from app.lotti.routers.prodotti_master import normalize_nome
    prodotti_bar = await db.magazzino_bar_prodotti.find(
        {}, {"_id": 0, "id": 1, "nome": 1, "stock": 1, "pezzi_per_collo": 1}
    ).to_list(3000)
    import re as _re
    _rx_test = _re.compile(r"\btest\b|\bzzz\b|\bprova\b", _re.IGNORECASE)
    junk_ids = [p_["id"] for p_ in prodotti_bar
                if p_.get("nome") and (not e_merce_alimentare(p_["nome"])
                                        or _rx_test.search(p_["nome"]))]
    if junk_ids:
        res = await db.magazzino_bar_prodotti.delete_many({"id": {"$in": junk_ids}})
        deleted["magazzino_bar_junk"] = res.deleted_count
    # doppioni per nome normalizzato: tengo il più "ricco" (pezzi_per_collo
    # impostato, poi stock più alto) e sommo lo stock degli altri
    gruppi = {}
    for p_ in prodotti_bar:
        if p_["id"] in junk_ids or not p_.get("nome"):
            continue
        gruppi.setdefault(normalize_nome(p_["nome"]), []).append(p_)
    uniti = 0
    for gr in gruppi.values():
        if len(gr) < 2:
            continue
        gr.sort(key=lambda x: (float(x.get("pezzi_per_collo") or 0),
                                float(x.get("stock") or 0)), reverse=True)
        capo, doppi = gr[0], gr[1:]
        stock_extra = sum(float(d.get("stock") or 0) for d in doppi)
        if stock_extra:
            await db.magazzino_bar_prodotti.update_one(
                {"id": capo["id"]}, {"$inc": {"stock": round(stock_extra, 3)}})
        await db.magazzino_bar_prodotti.delete_many(
            {"id": {"$in": [d["id"] for d in doppi]}})
        uniti += len(doppi)
    if uniti:
        deleted["magazzino_bar_doppioni_uniti"] = uniti
    return {"message": "Pulizia completata", "eliminati": deleted}
