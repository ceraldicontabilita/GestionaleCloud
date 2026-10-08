"""
shelf_life.py
═══════════════════════════════════════════════════════════════════
Sistema di calcolo automatico della data di scadenza dei lotti
di produzione Ceraldi Group.

LOGICA:
  La scadenza NON viene dalla fattura del fornitore (che spesso
  non la riporta, es. Fiorentino). Viene calcolata dal sistema
  in base a:

  1. INGREDIENTE PIÙ DEPERIBILE nella ricetta
     → l'ingrediente che scade prima determina la scadenza del prodotto

  2. METODO DI CONSERVAZIONE scelto dall'operatore:
     - Temperatura ambiente (vetrina)  → giorni più brevi
     - Frigorifero (0-4°C)             → giorni medi
     - Abbattitore positivo (3°C)      → giorni più lunghi
     - Abbattitore negativo / freezer  → settimane/mesi

  3. TIPO PRODOTTO (pasticceria fresca, cotta, secca, con crema...)

FONTI NORMATIVE:
  - Reg. CE 852/2004 (igiene alimenti)
  - Reg. UE 1169/2011 (etichettatura)
  - Linee guida HACCP italiane
  - Circolare Min. Salute n.10/1992

SHELF LIFE TABELLA (giorni dalla produzione):
  ╔══════════════════════════╦═══════╦══════╦══════════╦══════════╗
  ║ Prodotto                 ║Amb.   ║Frigo ║Abbatt.+  ║Abbatt.-  ║
  ╠══════════════════════════╬═══════╬══════╬══════════╬══════════╣
  ║ Con crema/uova           ║  0    ║  3   ║   5      ║  60      ║
  ║ Con panna fresca         ║  0    ║  2   ║   4      ║  30      ║
  ║ Con ricotta              ║  0    ║  3   ║   5      ║  60      ║
  ║ Babà / Rum               ║ 15   ║ 20   ║  30      ║ 180      ║
  ║ Sfogliatelle             ║  2   ║  5   ║  10      ║  90      ║
  ║ Cornetti/Brioche vuoti   ║  1   ║  3   ║   7      ║  90      ║
  ║ Cornetti farciti crema   ║  0   ║  2   ║   4      ║  30      ║
  ║ Torte pan di spagna      ║  0   ║  4   ║   7      ║  60      ║
  ║ Mousse/semifreddi        ║  0   ║  3   ║   5      ║  90      ║
  ║ Biscotti secchi          ║ 30   ║ 30   ║  30      ║ 180      ║
  ║ Pasta frolla cotta       ║  7   ║ 14   ║  21      ║ 180      ║
  ║ Pasta sfoglia cotta      ║  2   ║  5   ║  10      ║  90      ║
  ║ Cannoli/Cassate          ║  0   ║  3   ║   5      ║  60      ║
  ║ Cioccolatini/praline     ║ 20   ║ 30   ║  40      ║ 180      ║
  ║ Arancini/Crocchè         ║  0   ║  2   ║   4      ║  60      ║
  ║ Pizza/Focaccia           ║  1   ║  3   ║   5      ║  60      ║
  ║ Salumi/affettati         ║  0   ║  5   ║   7      ║  90      ║
  ║ Preparazioni con pesce   ║  0   ║  1   ║   2      ║  30      ║
  ║ Latticini freschi        ║  0   ║  5   ║   7      ║  30      ║
  ╚══════════════════════════╩═══════╩══════╩══════════╩══════════╝

INGREDIENTI DEPERIBILI (ordine dal più al meno critico):
  Pesce crudo        → 0/1 giorno
  Uova crude         → 0 giorno (ambiente), 3 frigo
  Panna fresca       → 0 (ambiente), 2 frigo
  Ricotta            → 0 (ambiente), 3 frigo
  Carne macinata     → 0 (ambiente), 1 frigo
  Fior di latte      → 0 (ambiente), 2 frigo
  Crema pasticcera   → 0 (ambiente), 3 frigo
  Mascarpone         → 0 (ambiente), 3 frigo
  Uova cotte         → 1 giorno, 3 frigo, 90 congelatore
  Latte fresco       → 1 giorno, 4 frigo
  Burro              → 3 giorni, 14 frigo
  Farina/Zucchero    → non deperibili (non influenzano)

REGOLA PRODOTTO COTTO IN FORNO (Enzo, 20/07/2026 — caso Sfogliatella Riccia):
  Le uova NEL RIPIENO di un prodotto che viene COTTO IN FORNO (sfogliatelle,
  cornetti, torte pan di spagna, biscotti, frolla, pizza...) cuociono insieme
  all'impasto: NON hanno la deperibilità delle uova crude (es. crema/mousse
  MAI cotta dopo l'aggiunta). Prima venivano trattate allo stesso modo, con
  due conseguenze sbagliate: (1) il congelatore risultava troppo breve (60gg
  invece dei 90gg/3 mesi già corretti nella tabella prodotto, sovrascritti
  dall'ingrediente "uova" generico), (2) nessun collegamento con la vera
  ragione per cui la Sfogliatella in FRIGO (non congelata) va consumata in
  giornata: l'impasto sfogliato perde la croccantezza per l'umidità del
  frigo (non è un rischio delle uova, è la sfoglia) — fonti reali:
  https://www.webnapoli24.com/2023/05/29/sfogliatelle-come-conservarle-tempo-e-dove-metterle/
  https://www.pintauro.eu/raccomandazioni.html (24h consumo ottimale non
  congelata) — prima calibrata a frigo=1 su quelle fonti, poi corretta a
  frigo=3 il 20/07/2026 su indicazione diretta di Enzo (titolare, responsabile
  del piano di autocontrollo del suo negozio: la sua esperienza pratica prevale
  sulla stima da fonti generiche quando la corregge esplicitamente).
  Il congelatore industriale può arrivare a 12 mesi con packaging sottovuoto
  (fonte: schede tecniche prodotti surgelati confezionati), ma qui si tratta
  di un congelatore comune di negozio senza confezionamento controllato: si
  resta prudenti su 90 giorni (3 mesi), il valore indicato da Enzo.
  Il motore ora prende sempre il MINIMO tra scadenza-prodotto e
  scadenza-ingrediente (mai il contrario): un ingrediente può solo
  ACCORCIARE la scadenza di un prodotto, mai allungarla oltre quanto la
  categoria prodotto già prevede.
═══════════════════════════════════════════════════════════════════
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/shelf-life", tags=["Shelf Life"])


# ── Enum metodi di conservazione ──────────────────────────────────────────────
METODI_CONSERVAZIONE = {
    "ambiente": "Temperatura ambiente (vetrina/banco)",
    "frigo": "Frigorifero 0-4°C",
    "abbattitore_positivo": "Abbattitore positivo (3°C) → frigo",
    "abbattitore_negativo": "Abbattitore negativo (-18°C) → freezer",
}


# ── Ingredienti deperibili con giorni di shelf life per metodo ─────────────────
# Struttura: keyword → { metodo: giorni }
# Se un ingrediente è presente nella ricetta, prende il minimo tra i suoi giorni
# e quello degli altri ingredienti. Questo determina la scadenza finale.

INGREDIENTI_DEPERIBILI = {
    # CRITICO — pesce/crostacei
    "pesce": {"ambiente": 0, "frigo": 1, "abbattitore_positivo": 2, "abbattitore_negativo": 30},
    "salmone": {"ambiente": 0, "frigo": 1, "abbattitore_positivo": 2, "abbattitore_negativo": 30},
    "gamberi": {"ambiente": 0, "frigo": 1, "abbattitore_positivo": 2, "abbattitore_negativo": 30},
    # MOLTO DEPERIBILE — uova crude, panna, ricotta
    "uova crude": {
        "ambiente": 0,
        "frigo": 3,
        "abbattitore_positivo": 5,
        "abbattitore_negativo": 60,
    },
    "uova": {"ambiente": 1, "frigo": 3, "abbattitore_positivo": 5, "abbattitore_negativo": 60},
    # Uova COTTE (nel ripieno di un prodotto cotto in forno insieme all'impasto,
    # es. sfogliatella, torta pan di spagna): usata al posto di "uova"/"uova
    # crude" quando il prodotto è in PRODOTTI_COTTI_IN_FORNO — vedi calcola_scadenza.
    "uova cotte": {"ambiente": 1, "frigo": 3, "abbattitore_positivo": 5, "abbattitore_negativo": 90},
    "panna fresca": {
        "ambiente": 0,
        "frigo": 2,
        "abbattitore_positivo": 4,
        "abbattitore_negativo": 30,
    },
    "panna": {"ambiente": 0, "frigo": 3, "abbattitore_positivo": 5, "abbattitore_negativo": 60},
    "ricotta": {"ambiente": 0, "frigo": 3, "abbattitore_positivo": 5, "abbattitore_negativo": 60},
    "carne": {"ambiente": 0, "frigo": 2, "abbattitore_positivo": 4, "abbattitore_negativo": 90},
    # DEPERIBILE — latticini freschi, crema
    "fior di latte": {
        "ambiente": 0,
        "frigo": 2,
        "abbattitore_positivo": 4,
        "abbattitore_negativo": 30,
    },
    "mozzarella": {
        "ambiente": 0,
        "frigo": 3,
        "abbattitore_positivo": 5,
        "abbattitore_negativo": 30,
    },
    "crema pasticcera": {
        "ambiente": 0,
        "frigo": 3,
        "abbattitore_positivo": 5,
        "abbattitore_negativo": 60,
    },
    "crema": {"ambiente": 0, "frigo": 3, "abbattitore_positivo": 5, "abbattitore_negativo": 60},
    "mascarpone": {
        "ambiente": 0,
        "frigo": 3,
        "abbattitore_positivo": 5,
        "abbattitore_negativo": 60,
    },
    "latte": {"ambiente": 1, "frigo": 4, "abbattitore_positivo": 7, "abbattitore_negativo": 90},
    "burro": {"ambiente": 3, "frigo": 14, "abbattitore_positivo": 21, "abbattitore_negativo": 180},
    "formaggio": {
        "ambiente": 2,
        "frigo": 7,
        "abbattitore_positivo": 14,
        "abbattitore_negativo": 90,
    },
    # SEMI-DEPERIBILE — specifici pasticceria
    "rum": {"ambiente": 15, "frigo": 20, "abbattitore_positivo": 30, "abbattitore_negativo": 180},
    "bagna": {"ambiente": 10, "frigo": 15, "abbattitore_positivo": 25, "abbattitore_negativo": 180},
}

# Shelf life di default per tipo prodotto (se nessun ingrediente deperibile trovato)
SHELF_LIFE_PRODOTTO = {
    # Pasticceria fresca con farcitura
    "baba": {"ambiente": 15, "frigo": 20, "abbattitore_positivo": 30, "abbattitore_negativo": 180},
    "babà": {"ambiente": 15, "frigo": 20, "abbattitore_positivo": 30, "abbattitore_negativo": 180},
    # frigo=3 (non 5): valore confermato da Enzo (titolare, responsabile del
    # piano di autocontrollo HACCP del suo negozio) il 20/07/2026 — il primo
    # tentativo (1 giorno) era troppo breve nella sua esperienza pratica.
    "sfogliatella": {
        "ambiente": 2,
        "frigo": 3,
        "abbattitore_positivo": 10,
        "abbattitore_negativo": 90,
    },
    "sfogliatelle": {
        "ambiente": 2,
        "frigo": 3,
        "abbattitore_positivo": 10,
        "abbattitore_negativo": 90,
    },
    "cornetto": {"ambiente": 1, "frigo": 3, "abbattitore_positivo": 7, "abbattitore_negativo": 90},
    "brioche": {"ambiente": 2, "frigo": 4, "abbattitore_positivo": 7, "abbattitore_negativo": 90},
    "torta": {"ambiente": 0, "frigo": 4, "abbattitore_positivo": 7, "abbattitore_negativo": 60},
    "pan di spagna": {
        "ambiente": 0,
        "frigo": 4,
        "abbattitore_positivo": 7,
        "abbattitore_negativo": 60,
    },
    "mousse": {"ambiente": 0, "frigo": 3, "abbattitore_positivo": 5, "abbattitore_negativo": 90},
    "semifreddo": {
        "ambiente": 0,
        "frigo": 0,
        "abbattitore_positivo": 0,
        "abbattitore_negativo": 90,
    },
    "cannolo": {"ambiente": 0, "frigo": 3, "abbattitore_positivo": 5, "abbattitore_negativo": 60},
    "cannoli": {"ambiente": 0, "frigo": 3, "abbattitore_positivo": 5, "abbattitore_negativo": 60},
    "cassata": {"ambiente": 0, "frigo": 4, "abbattitore_positivo": 7, "abbattitore_negativo": 60},
    "pastiera": {
        "ambiente": 5,
        "frigo": 10,
        "abbattitore_positivo": 15,
        "abbattitore_negativo": 90,
    },
    "struffoli": {
        "ambiente": 7,
        "frigo": 14,
        "abbattitore_positivo": 21,
        "abbattitore_negativo": 90,
    },
    "roccocò": {
        "ambiente": 30,
        "frigo": 30,
        "abbattitore_positivo": 30,
        "abbattitore_negativo": 180,
    },
    "biscotto": {
        "ambiente": 30,
        "frigo": 30,
        "abbattitore_positivo": 30,
        "abbattitore_negativo": 180,
    },
    "biscotti": {
        "ambiente": 30,
        "frigo": 30,
        "abbattitore_positivo": 30,
        "abbattitore_negativo": 180,
    },
    "frolla": {"ambiente": 7, "frigo": 14, "abbattitore_positivo": 21, "abbattitore_negativo": 180},
    "crostata": {"ambiente": 5, "frigo": 7, "abbattitore_positivo": 14, "abbattitore_negativo": 90},
    "cioccolato": {
        "ambiente": 20,
        "frigo": 30,
        "abbattitore_positivo": 40,
        "abbattitore_negativo": 180,
    },
    "praline": {
        "ambiente": 15,
        "frigo": 30,
        "abbattitore_positivo": 40,
        "abbattitore_negativo": 180,
    },
    # Lievitati da ricorrenza / secchi da forno — LUNGA CONSERVAZIONE
    # (Enzo 23/07/2026, caso Panettone artigianale: "è un prodotto cotto che
    # va conservato per 3 mesi, non 1 giorno perché c'è l'uovo dentro").
    "panettone": {"ambiente": 90, "frigo": 90, "abbattitore_positivo": 90, "abbattitore_negativo": 180},
    "pandoro": {"ambiente": 90, "frigo": 90, "abbattitore_positivo": 90, "abbattitore_negativo": 180},
    "colomba": {"ambiente": 60, "frigo": 60, "abbattitore_positivo": 60, "abbattitore_negativo": 180},
    "roccoco": {"ambiente": 30, "frigo": 30, "abbattitore_positivo": 30, "abbattitore_negativo": 180},
    "mostacciolo": {"ambiente": 30, "frigo": 30, "abbattitore_positivo": 30, "abbattitore_negativo": 180},
    "mostaccioli": {"ambiente": 30, "frigo": 30, "abbattitore_positivo": 30, "abbattitore_negativo": 180},
    "susamielli": {"ambiente": 30, "frigo": 30, "abbattitore_positivo": 30, "abbattitore_negativo": 180},
    "tarall": {"ambiente": 30, "frigo": 30, "abbattitore_positivo": 30, "abbattitore_negativo": 180},
    # Rosticceria
    "arancino": {"ambiente": 0, "frigo": 2, "abbattitore_positivo": 4, "abbattitore_negativo": 60},
    "arancini": {"ambiente": 0, "frigo": 2, "abbattitore_positivo": 4, "abbattitore_negativo": 60},
    "crocchè": {"ambiente": 0, "frigo": 2, "abbattitore_positivo": 4, "abbattitore_negativo": 60},
    "pizza": {"ambiente": 1, "frigo": 3, "abbattitore_positivo": 5, "abbattitore_negativo": 60},
    "focaccia": {"ambiente": 1, "frigo": 3, "abbattitore_positivo": 5, "abbattitore_negativo": 60},
    "rustico": {"ambiente": 1, "frigo": 3, "abbattitore_positivo": 5, "abbattitore_negativo": 60},
    "calzone": {"ambiente": 0, "frigo": 2, "abbattitore_positivo": 4, "abbattitore_negativo": 60},
    # Default generico
    "_default": {"ambiente": 1, "frigo": 5, "abbattitore_positivo": 10, "abbattitore_negativo": 90},
}

# Prodotti COTTI IN FORNO (impasto + ripieno cuociono insieme): le eventuali
# uova nel ripieno cuociono con l'impasto e non hanno la deperibilità delle
# uova crude aggiunte DOPO la cottura (crema pasticcera, mousse, panna fresca
# — quelle restano sempre "crude" indipendentemente dal prodotto). Esclusi
# apposta: cannolo/cannoli/cassata (guscio fritto/cotto ma farciti con
# ricotta CRUDA dopo), mousse/semifreddo (mai cotti), arancini/crocchè
# (fritti, non hanno uova nel ripieno tipico).
PRODOTTI_COTTI_IN_FORNO = {
    "baba", "babà", "sfogliatella", "sfogliatelle", "cornetto", "brioche",
    "torta", "pan di spagna", "biscotto", "biscotti", "frolla", "crostata",
    "pizza", "focaccia", "rustico", "calzone", "roccocò", "struffoli", "pastiera",
    "panettone", "pandoro", "colomba", "roccoco", "mostacciolo", "mostaccioli",
    "susamielli", "tarall",
}

# Prodotti a LUNGA CONSERVAZIONE (interamente cotti e stabili a scaffale:
# lievitati da ricorrenza e secchi da forno). Per questi la tabella prodotto
# è AUTOREVOLE: gli ingredienti cotti NELL'IMPASTO (uova, latte, burro) non
# accorciano la scadenza — un panettone non "scade domani" per l'uovo cotto
# dentro. Le farciture aggiunte DOPO la cottura (crema, panna, ricotta,
# mascarpone...) invece accorciano eccome, come per ogni altro prodotto.
PRODOTTI_LUNGA_CONSERVAZIONE = {
    "panettone", "pandoro", "colomba", "roccocò", "roccoco",
    "mostacciolo", "mostaccioli", "susamielli", "tarall",
    "biscotto", "biscotti",
}
INGREDIENTI_COTTI_NELL_IMPASTO = {"uova", "uova crude", "uova cotte", "latte", "burro"}


# ── Funzione principale ────────────────────────────────────────────────────────


def calcola_scadenza(
    nome_prodotto: str,
    ingredienti: list,
    metodo_conservazione: str,
    data_produzione: Optional[datetime] = None,
) -> dict:
    """
    Calcola la data di scadenza di un lotto di produzione.

    Parametri:
      nome_prodotto        → es. "Torta Margherita", "Babà al Rum"
      ingredienti          → lista stringhe o dict con campo 'nome'
      metodo_conservazione → "ambiente" | "frigo" | "abbattitore_positivo" | "abbattitore_negativo"
      data_produzione      → datetime, default = oggi

    Ritorna:
      {
        giorni:             int   → giorni di conservazione
        data_scadenza:      str   → "DD/MM/YYYY"
        metodo:             str   → metodo conservazione usato
        ingrediente_critico: str  → ingrediente che ha determinato la scadenza
        avviso:             str   → messaggio per l'operatore
        livello_rischio:    str   → "alto" | "medio" | "basso"
      }
    """
    if data_produzione is None:
        data_produzione = datetime.now(timezone.utc)

    metodo = metodo_conservazione if metodo_conservazione in METODI_CONSERVAZIONE else "frigo"

    # Normalizza lista ingredienti
    nomi_ingredienti = []
    for ing in ingredienti or []:
        if isinstance(ing, dict):
            nome = (ing.get("nome") or ing.get("nome_fattura") or "").lower()
        else:
            nome = str(ing).lower()
        if nome:
            nomi_ingredienti.append(nome)

    # 1. Categoria prodotto (dal nome) → base di partenza. PRIMA veniva usata
    #    solo come fallback quando nessun ingrediente deperibile era trovato:
    #    così un ingrediente generico (es. "uova") poteva SOVRASCRIVERE un
    #    valore prodotto più specifico e già corretto (es. "sfogliatella" in
    #    congelatore: 90gg) con uno peggiore/più lungo (uova generiche: 60gg) —
    #    bug segnalato da Enzo 20/07/2026 sul lotto Sfogliatella Riccia. Ora la
    #    categoria prodotto è SEMPRE la base, e un ingrediente può solo
    #    ACCORCIARLA (mai allungarla): è la regola prudenziale corretta in
    #    sicurezza alimentare — non si prende mai la stima più lunga tra due.
    nome_lower = nome_prodotto.lower()
    categoria_prodotto = None
    shelf_prodotto = SHELF_LIFE_PRODOTTO["_default"]
    for keyword, shelf in SHELF_LIFE_PRODOTTO.items():
        if keyword != "_default" and keyword in nome_lower:
            categoria_prodotto = keyword
            shelf_prodotto = shelf
            break
    prodotto_cotto_in_forno = categoria_prodotto in PRODOTTI_COTTI_IN_FORNO

    giorni_min = shelf_prodotto.get(metodo, 3)
    ingrediente_critico = None

    # 2. Ingrediente più deperibile: può solo abbassare giorni_min. Per ogni
    #    ingrediente si prende la keyword più specifica (la più lunga tra
    #    quelle che matchano), non una qualsiasi tra quelle in conflitto.
    for nome_ing in nomi_ingredienti:
        match_keyword, match_shelf = None, None
        for keyword, shelf in INGREDIENTI_DEPERIBILI.items():
            if keyword == "uova cotte":
                continue  # mai per match diretto: solo via sostituzione sotto
            if keyword in nome_ing and (match_keyword is None or len(keyword) > len(match_keyword)):
                match_keyword, match_shelf = keyword, shelf
        if match_keyword is None:
            continue
        # Prodotto a lunga conservazione (panettone, biscotti…): uova/latte/
        # burro sono COTTI nell'impasto e non accorciano la scadenza della
        # categoria — solo le farciture post-cottura (crema, panna…) contano.
        if categoria_prodotto in PRODOTTI_LUNGA_CONSERVAZIONE and match_keyword in INGREDIENTI_COTTI_NELL_IMPASTO:
            continue
        # Uova nel ripieno di un prodotto cotto in forno: cuociono con
        # l'impasto, non hanno la deperibilità delle uova crude.
        if match_keyword in ("uova", "uova crude") and prodotto_cotto_in_forno:
            match_keyword, match_shelf = "uova cotte", INGREDIENTI_DEPERIBILI["uova cotte"]
        giorni = match_shelf.get(metodo, match_shelf.get("frigo", 3))
        if giorni < giorni_min:
            giorni_min = giorni
            ingrediente_critico = match_keyword

    # 3. Calcola data scadenza
    data_scadenza = data_produzione + timedelta(days=giorni_min)

    # 4. Determina livello di rischio e avviso
    if giorni_min == 0:
        livello = "alto"
        avviso = "⚠️ Da consumare il giorno stesso — non conservare"
    elif giorni_min <= 2:
        livello = "alto"
        avviso = f"⚠️ Altamente deperibile — consumare entro {giorni_min} giorni"
    elif giorni_min <= 7:
        livello = "medio"
        avviso = f"Conservare a {METODI_CONSERVAZIONE[metodo]} — scade in {giorni_min} giorni"
    else:
        livello = "basso"
        avviso = f"Conservare a {METODI_CONSERVAZIONE[metodo]} — {giorni_min} giorni di shelf life"

    return {
        "giorni": giorni_min,
        "data_scadenza": data_scadenza.strftime("%d/%m/%Y"),
        "data_scadenza_iso": data_scadenza.strftime("%Y-%m-%d"),
        "metodo": metodo,
        "metodo_label": METODI_CONSERVAZIONE[metodo],
        "ingrediente_critico": ingrediente_critico,
        "avviso": avviso,
        "livello_rischio": livello,
    }


# ── Endpoint REST ──────────────────────────────────────────────────────────────


@router.post("/calcola")
async def calcola_shelf_life(payload: dict):
    """
    Calcola la scadenza dato un prodotto e i suoi ingredienti.
    Payload:
      { nome_prodotto, ingredienti: [...], metodo_conservazione, data_produzione? }
    """
    return calcola_scadenza(
        nome_prodotto=payload.get("nome_prodotto", ""),
        ingredienti=payload.get("ingredienti", []),
        metodo_conservazione=payload.get("metodo_conservazione", "frigo"),
        data_produzione=None,
    )


@router.get("/tabella")
async def tabella_shelf_life():
    """Restituisce la tabella completa shelf life per categoria prodotto."""
    return {
        "ingredienti_deperibili": {k: v for k, v in INGREDIENTI_DEPERIBILI.items()},
        "shelf_life_prodotti": {k: v for k, v in SHELF_LIFE_PRODOTTO.items() if k != "_default"},
        "metodi_conservazione": METODI_CONSERVAZIONE,
    }


@router.get("/metodi")
async def lista_metodi():
    """Lista i metodi di conservazione disponibili."""
    return [{"id": k, "label": v} for k, v in METODI_CONSERVAZIONE.items()]
