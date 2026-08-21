"""
Motore unico di instradamento Prima Nota (Cassa / Banca / Provvisoria).

Prima di questo modulo la stessa decisione "il fornitore paga in cassa o in
banca?" era reimplementata in modo indipendente in almeno 7 punti del
codice (handlers/prima_nota.py, fatture_module/metodo_pagamento.py,
fatture_module/pagamento.py, sync_relazionale.py, data_propagation.py,
prima_nota_module/sync.py), ciascuno con la propria lista di parole chiave.
Le liste non erano sincronizzate tra loro: un fornitore con metodo
"assegno" o "carta" poteva risultare "Banca" in un punto e "sospeso"
nell'altro (vedi commento storico in app/routers/prima_nota_module/sync.py).

Regola canonica unica (decisione utente 03/08/2026):

    fornitore "Cassa"           -> Prima Nota Cassa
    fornitore "Banca"           -> Prima Nota Provvisoria finche' non esiste
                                   un movimento reale dell'estratto conto
    fornitore "Misto"           -> Prima Nota Provvisoria (attesa conferma utente)
    fornitore senza metodo      -> None (il chiamante DEVE generare un alert e
                                   chiedere all'utente di impostare il metodo,
                                   mai instradare "a caso")

I metodi storici piu' specifici (riba, assegno, bonifico, rid, carta, sepa,
bancomat, paypal, stripe, domiciliazione, bancario...) sono tutti strumenti
che transitano dal conto corrente: vengono ricondotti a "banca". Non sono
piu' categorie distinte nel nuovo modello: chi ha ancora questi valori
salvati va normalizzato (vedi scripts/migra_metodo_pagamento_fornitori.py).
"""
from typing import Optional

CASSA = "cassa"
BANCA = "banca"
MISTO = "misto"

# Fornitore -> Prima Nota Provvisoria: l'utente deve confermare come dividere
# il pagamento prima che il sistema scriva in cassa o banca.
PROVVISORIA = "provvisoria"

_KEYWORDS_CASSA = {"cassa", "contanti", "contante", "cash", "mp01"}
_KEYWORDS_MISTO = {"misto"}

# Valori (canonici + legacy ancora in DB) dei metodi pagamento che richiedono
# un IBAN in anagrafica fornitore. Usata nei filtri ``$in`` del repository
# fornitori/IBAN: punto unico al posto delle due liste divergenti che prima
# vivevano in suppliers/iban_service.py e suppliers_module/common.py.
METODI_RICHIEDONO_IBAN = [
    "banca", "bonifico", "sepa", "rid", "sdd",
    "assegno", "riba", "mav", "rav", "f24", "carta", "misto",
]

# Ogni altra parola chiave storicamente usata per uno strumento che transita
# dal conto corrente: tutte ricondotte a "banca" (decisione 2026-07).
_KEYWORDS_BANCA_SUBSTRING = (
    "banca", "bancar", "bancomat",
    "bonific",                       # bonifico, bonifico bancario, bonif.
    "sepa", "rid", "riba", "sdd",
    "assegn",                        # assegno, assegno bancario/circolare
    "cart", "credit", "debit",       # carta, carta di credito/debito
    "domicili",                      # domiciliazione/domiciliato
    "paypal", "stripe",
    "mav", "rav", "f24",
    # codici pagamento Fattura Elettronica (MP01 = contanti, gestito sopra
    # come cassa; tutti gli altri MPxx sono strumenti bancari)
    "mp0", "mp1", "mp2",
)


def normalizza_metodo_pagamento(metodo_raw: Optional[str]) -> Optional[str]:
    """Canonicalizza un metodo di pagamento fornitore a {cassa, banca, misto}.

    Ritorna None per metodo vuoto o non riconosciuto: il fornitore e'
    considerato "non definito" e va segnalato all'utente, mai instradato
    automaticamente.
    """
    if not metodo_raw:
        return None
    m = str(metodo_raw).strip().lower()
    if not m:
        return None

    if m in _KEYWORDS_MISTO or "misto" in m:
        return MISTO

    # "contrassegno" = contanti alla consegna: e' CASSA, e va controllato
    # PRIMA del loop banca perche' contiene la sottostringa "assegn".
    if m in _KEYWORDS_CASSA or "contant" in m or "cash" in m or "contrassegn" in m:
        return CASSA

    if m in ("mp01",):
        return CASSA

    for kw in _KEYWORDS_BANCA_SUBSTRING:
        if kw in m:
            return BANCA

    return None


def decide_destinazione_fattura(
    metodo_pagamento_fornitore: Optional[str],
    evidenza_bancaria: bool = False,
) -> Optional[str]:
    """Decide dove instradare una fattura in base al metodo del fornitore.

    Ritorna 'cassa' | 'banca' | 'provvisoria' | None.

    Il metodo anagrafico "banca" descrive *come* il fornitore viene pagato,
    non prova che il denaro sia gia' uscito. Per questo la destinazione e'
    Banca solo quando il chiamante fornisce ``evidenza_bancaria=True`` dopo
    aver collegato una riga reale e non gia' usata dell'estratto conto.
    None significa fornitore senza metodo definito: il chiamante deve
    generare un alert e chiedere conferma, non decidere da solo.
    Questa e' l'UNICA funzione che deve decidere questa destinazione in
    tutto il gestionale.
    """
    canonico = normalizza_metodo_pagamento(metodo_pagamento_fornitore)
    if canonico == CASSA:
        return CASSA
    if canonico == BANCA:
        return BANCA if evidenza_bancaria else PROVVISORIA
    if canonico == MISTO:
        return PROVVISORIA
    return None
