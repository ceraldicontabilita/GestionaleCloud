"""
Piano dei Conti Router - Contabilità Generale
Gestione del piano dei conti secondo i principi di ragioneria italiana.
"""
from fastapi import APIRouter, HTTPException, Body, Depends, Query
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import logging

from app.database import Database
from app.utils.dependencies import get_current_admin_user
from app.utils.error_handler import handle_errors
from app.utils.parsing import safe_float
from app.services.mapping_piano_conti import (
    OPERATIVO_A_UFFICIALE,
    alias_operativi,
    categoria_cee,
    conto_cee,
    conto_cee_valido,
    piano_conti_cee,
    raggruppa_per_categoria,
    risolvi_codice_cee,
    saldi_in_cee,
)
from app.services.piano_conti_ufficiale import CONTI_UFFICIALI
from app.services.stato_pagamento_fattura import FILTRO_NON_PAGATE

logger = logging.getLogger(__name__)
router = APIRouter()

# Collezione DISMESSA (audit del commercialista 03/09/2026 §2, PR 7): era un
# secondo piano dei conti (31 conti operativi, saldo 0) parallelo al CEE
# ufficiale. Si legge SOLO per compatibilita' (conversione degli eventuali
# conti creati a mano); nessuna nuova scrittura. Il piano esposto e' quello
# di ``app/services/piano_conti_ufficiale.py`` con i codici operativi come
# alias (``app/services/mapping_piano_conti.py``).
COLLECTION_PIANO_CONTI = "piano_conti"
COLLECTION_MOVIMENTI_CONTABILI = "movimenti_contabili"

MESSAGGIO_PIANO_CEE = (
    "Il piano dei conti e' quello CEE ufficiale del bilancio "
    "(app/services/piano_conti_ufficiale.py): i conti non si creano, "
    "modificano o eliminano a mano. I vecchi codici operativi restano alias."
)

# ============== STRUTTURA OPERATIVA (ALIAS) ==============
# Schema operativo storico, oggi SOLO alias dei conti CEE (vedi
# mapping_piano_conti.OPERATIVO_A_UFFICIALE): il motore di registrazione
# §6.1 e il dizionario articoli scrivono ancora questi codici, che le API
# convertono sempre nel conto ufficiale.
# - Gruppo (2 cifre): 01-99
# - Sottogruppo (2 cifre): 01-99
# - Conto (2 cifre): 01-99
# Formato codice: GG.SS.CC

STRUTTURA_BASE = {
    "attivo": {
        "codice": "01",
        "nome": "ATTIVO",
        "descrizione": "Elementi patrimoniali attivi",
        "conti_tipici": [
            {"codice": "01.01.01", "nome": "Cassa", "natura": "finanziario"},
            {"codice": "01.01.02", "nome": "Banca c/c", "natura": "finanziario"},
            {"codice": "01.02.01", "nome": "Crediti v/clienti", "natura": "finanziario"},
            {"codice": "01.03.01", "nome": "Magazzino merci", "natura": "economico"},
            {"codice": "01.04.01", "nome": "IVA a credito", "natura": "finanziario"},
            # A7 (scelta utente 2026-07-13): conto rettificativo dell'attivo per
            # la partita doppia degli ammortamenti (mappa all'ufficiale 41)
            {"codice": "01.05.01", "nome": "Fondo ammortamento", "natura": "economico"},
        ]
    },
    "passivo": {
        "codice": "02",
        "nome": "PASSIVO",
        "descrizione": "Elementi patrimoniali passivi",
        "conti_tipici": [
            {"codice": "02.01.01", "nome": "Debiti v/fornitori", "natura": "finanziario"},
            {"codice": "02.02.01", "nome": "Debiti tributari", "natura": "finanziario"},
            {"codice": "02.02.02", "nome": "Debiti v/INPS", "natura": "finanziario"},
            {"codice": "02.03.01", "nome": "IVA a debito", "natura": "finanziario"},
            {"codice": "02.04.01", "nome": "TFR", "natura": "finanziario"},
        ]
    },
    "patrimonio_netto": {
        "codice": "03",
        "nome": "PATRIMONIO NETTO",
        "descrizione": "Capitale proprio",
        "conti_tipici": [
            {"codice": "03.01.01", "nome": "Capitale sociale", "natura": "economico"},
            {"codice": "03.02.01", "nome": "Riserva legale", "natura": "economico"},
            {"codice": "03.03.01", "nome": "Utile d'esercizio", "natura": "economico"},
            {"codice": "03.03.02", "nome": "Perdita d'esercizio", "natura": "economico"},
        ]
    },
    "ricavi": {
        "codice": "04",
        "nome": "RICAVI",
        "descrizione": "Componenti positivi di reddito",
        "conti_tipici": [
            {"codice": "04.01.01", "nome": "Ricavi vendite prodotti", "natura": "economico"},
            {"codice": "04.01.02", "nome": "Ricavi vendite bar", "natura": "economico"},
            {"codice": "04.01.03", "nome": "Ricavi vendite cucina", "natura": "economico"},
            {"codice": "04.02.01", "nome": "Ricavi prestazioni servizi", "natura": "economico"},
            {"codice": "04.03.01", "nome": "Proventi finanziari", "natura": "economico"},
        ]
    },
    "costi": {
        "codice": "05",
        "nome": "COSTI",
        "descrizione": "Componenti negativi di reddito",
        "conti_tipici": [
            {"codice": "05.01.01", "nome": "Acquisto merci", "natura": "economico"},
            {"codice": "05.01.02", "nome": "Acquisto materie prime", "natura": "economico"},
            {"codice": "05.02.01", "nome": "Costi per servizi", "natura": "economico"},
            {"codice": "05.02.02", "nome": "Utenze (luce, gas, acqua)", "natura": "economico"},
            {"codice": "05.02.03", "nome": "Canoni di locazione", "natura": "economico"},
            {"codice": "05.03.01", "nome": "Salari e stipendi", "natura": "economico"},
            {"codice": "05.03.02", "nome": "Contributi previdenziali", "natura": "economico"},
            {"codice": "05.03.03", "nome": "TFR", "natura": "economico"},
            {"codice": "05.04.01", "nome": "Ammortamento immobilizzazioni", "natura": "economico"},
            {"codice": "05.05.01", "nome": "Oneri finanziari", "natura": "economico"},
            {"codice": "05.06.01", "nome": "Imposte e tasse", "natura": "economico"},
        ]
    }
}


def _deduplica_conti_per_codice(conti: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Restituisce una vista deterministica con un solo conto per codice.

    Il frontend carica elenco e bilancio in parallelo. Prima della protezione
    atomica, due inizializzazioni concorrenti potevano inserire due copie
    identiche dell'intero piano. I saldi sono calcolati per codice: lasciare le
    copie nella risposta li sommerebbe più volte anche se i movimenti sorgente
    sono unici.

    I record senza codice non vengono fusi: non hanno una chiave contabile
    sufficiente e devono restare visibili per una verifica separata.
    """
    ordinati = sorted(
        conti,
        key=lambda conto: (
            str(conto.get("codice") or ""),
            str(conto.get("created_at") or ""),
            str(conto.get("id") or ""),
        ),
    )
    unici: Dict[str, Dict[str, Any]] = {}
    senza_codice: List[Dict[str, Any]] = []
    copie_eccedenti = 0

    for conto in ordinati:
        codice = str(conto.get("codice") or "").strip()
        if not codice:
            senza_codice.append(conto)
            continue
        if codice in unici:
            copie_eccedenti += 1
            continue
        unici[codice] = conto

    if copie_eccedenti:
        logger.warning(
            "Piano dei Conti: escluse dalla vista %s copie eccedenti per codice",
            copie_eccedenti,
        )

    return [*unici.values(), *senza_codice]


async def _conti_operativi_legacy(db) -> List[Dict[str, Any]]:
    """Lettura di compatibilita' della collezione dismessa ``piano_conti``.

    Serve solo a segnalare eventuali conti creati a mano che non hanno un
    alias nel piano CEE. Nessuna scrittura, nessuna inizializzazione.
    """
    try:
        conti = await db[COLLECTION_PIANO_CONTI].find({}, {"_id": 0}).sort("codice", 1).to_list(1000)
    except Exception:  # pragma: no cover - collezione assente o backend minimale
        return []
    return _deduplica_conti_per_codice(conti or [])


@router.get("/")
@handle_errors
async def get_piano_conti(anno: str = None) -> Dict[str, Any]:
    """Piano dei conti CEE UFFICIALE con saldi calcolati al volo dall'anno
    selezionato (se `anno` non è passato, cumulativo su tutti gli anni).

    Un solo piano (audit 03/09/2026, PR 7): i conti sono quelli del bilancio
    del commercialista; il codice operativo storico (es. 05.01.01) compare
    come ``alias_operativo``; i saldi per codice operativo vengono sommati
    sul conto CEE. La vecchia collezione ``piano_conti`` non viene piu'
    scritta: i suoi eventuali conti senza mapping sono elencati a parte.
    """
    db = Database.get_db()

    saldi = await _calcola_saldi_piano_conti(db, anno)
    conti = piano_conti_cee(saldi)

    non_mappati = [
        {"codice": c.get("codice"), "nome": c.get("nome"), "categoria": c.get("categoria")}
        for c in await _conti_operativi_legacy(db)
        if not risolvi_codice_cee(c.get("codice"))
    ]

    return {
        "conti": conti,
        "grouped": raggruppa_per_categoria(conti),
        "totale": len(conti),
        "schema": "CEE",
        "fonte": "piano_conti_ufficiale",
        "fonte_saldi": "movimenti_contabili",
        "struttura": STRUTTURA_BASE,
        "conti_operativi_non_mappati": non_mappati,
        "anno": anno,
    }


def _intero_o_none(valore: Any) -> Optional[int]:
    try:
        return int(valore)
    except (TypeError, ValueError):
        return None


def _anno_scrittura(scrittura: Dict[str, Any]) -> Optional[int]:
    """Anno della scrittura: il campo ``anno`` o, in mancanza, la data."""
    anno = _intero_o_none(scrittura.get("anno"))
    if anno is not None:
        return anno
    data = str(scrittura.get("data_documento") or scrittura.get("data") or "")
    return _intero_o_none(data[:4]) if len(data) >= 4 else None


# Lato "naturale" del saldo per categoria CEE: un conto dell'attivo o di
# costo e' positivo in DARE, uno del passivo, del netto o di ricavo in AVERE.
_CATEGORIE_SALDO_DARE = {"attivo", "costi"}
_CATEGORIE_ECONOMICHE = {"ricavi", "costi"}


async def _calcola_saldi_piano_conti(db, anno: str = None) -> Dict[str, float]:
    """Saldi di ogni conto dal LIBRO GIORNALE (``movimenti_contabili``), per
    codice di riga, col segno del conto CEE di destinazione.

    Audit 27/09/2026 (punto 1): prima i saldi si ricalcolavano dalle
    collezioni operative — un secondo sistema accanto al giornale, che
    contava 555 fatture archiviate doppie, i corrispettivi cancellati,
    sommava ``prezzo_totale`` stringa e leggeva sugli F24 campi che nessun
    F24 ha. Ora il piano dei conti somma le stesse righe del bilancio di
    verifica (``contabilita_gestionale._bilancio_verifica_da_registro``),
    stesso predicato di scrittura attiva, e la conversione CEE resta quella
    di ``mapping_piano_conti`` (chi chiama usa ``saldi_in_cee``).

    - conti economici (ricavi, costi): flusso dell'anno ``anno``;
    - conti patrimoniali: saldo cumulativo fino al 31/12 di ``anno``;
    - senza ``anno``: tutto il registro.
    La scrittura di chiusura dell'esercizio (``chiusura_esercizio``) degli
    anni del flusso economico non si somma: il suo effetto — portare il
    risultato a patrimonio netto — e' ricostruito qui sotto dai conti
    economici, altrimenti ricavi e costi dell'anno chiuso varrebbero zero.
    Cio' che il giornale non registra (pagamenti, stipendi) non compare:
    un saldo che manca e' un dato da registrare, non da stimare.
    """
    from app.services.registrazione_contabile import FILTRO_SCRITTURA_ATTIVA

    anno_int = _intero_o_none(anno) if anno else None
    scritture = await db[COLLECTION_MOVIMENTI_CONTABILI].find(
        dict(FILTRO_SCRITTURA_ATTIVA),
        {"_id": 0, "righe": 1, "anno": 1, "data": 1, "data_documento": 1, "tipo": 1},
    ).to_list(None)

    grezzi: Dict[str, float] = {}
    for scrittura in scritture:
        righe = scrittura.get("righe") or []
        if not righe:
            continue
        anno_s = _anno_scrittura(scrittura)
        if anno_int is not None:
            if anno_s is None or anno_s > anno_int:
                continue
            nel_flusso = anno_s == anno_int
        else:
            nel_flusso = True
        if scrittura.get("tipo") == "chiusura_esercizio" and nel_flusso:
            continue
        for riga in righe:
            codice = str(riga.get("conto_codice") or riga.get("conto") or "").strip()
            cee = risolvi_codice_cee(codice)
            if not cee:
                continue
            if categoria_cee(cee) in _CATEGORIE_ECONOMICHE and not nel_flusso:
                continue
            try:
                dare = float(riga.get("dare") or 0)
                avere = float(riga.get("avere") or 0)
            except (TypeError, ValueError):
                logger.warning("Riga non numerica nel giornale (conto %s): esclusa dai saldi", codice)
                continue
            grezzi[codice] = grezzi.get(codice, 0.0) + dare - avere

    saldi: Dict[str, float] = {}
    for codice, dare_meno_avere in grezzi.items():
        categoria = categoria_cee(risolvi_codice_cee(codice))
        saldo = dare_meno_avere if categoria in _CATEGORIE_SALDO_DARE else -dare_meno_avere
        saldi[codice] = round(saldo, 2)

    # Risultato dell'esercizio (ricavi - costi del flusso) sul netto: utile
    # in 03.03.01, perdita in 03.03.02 col segno del netto (negativa).
    ricavi = sum(v for k, v in saldi.items() if categoria_cee(risolvi_codice_cee(k)) == "ricavi")
    costi = sum(v for k, v in saldi.items() if categoria_cee(risolvi_codice_cee(k)) == "costi")
    risultato = round(ricavi - costi, 2)
    if risultato > 0:
        saldi["03.03.01"] = round(saldi.get("03.03.01", 0.0) + risultato, 2)
    elif risultato < 0:
        saldi["03.03.02"] = round(saldi.get("03.03.02", 0.0) + risultato, 2)
    return saldi


async def inizializza_piano_conti_base(db) -> List[Dict[str, Any]]:
    """Il piano dei conti non si "inizializza" piu' in una collezione: e' il
    CEE ufficiale in codice (audit 03/09/2026, PR 7). Nessuna scrittura;
    restituisce la stessa lista esposta da ``GET /api/piano-conti/``."""
    return piano_conti_cee()


@router.post("/")
@handle_errors
async def create_conto(data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Il piano dei conti e' il CEE ufficiale: nessun conto creato a mano.

    Un codice gia' CEE (o un alias operativo mappato) esiste gia'; qualunque
    altro codice non entra in un secondo piano parallelo (collezione
    ``piano_conti`` dismessa). Risposta 409 in entrambi i casi, con il conto
    CEE corrispondente quando c'e'.
    """
    codice = str(data.get("codice") or "").strip()
    if not codice:
        raise HTTPException(status_code=400, detail="Codice obbligatorio")
    cee = risolvi_codice_cee(codice)
    if cee:
        raise HTTPException(
            status_code=409,
            detail=f"Conto con codice {codice} gia' esistente nel piano CEE come {cee} "
                   f"({CONTI_UFFICIALI.get(cee, '')}). {MESSAGGIO_PIANO_CEE}",
        )
    raise HTTPException(status_code=409, detail=f"Conto {codice} non creato. {MESSAGGIO_PIANO_CEE}")


@router.put("/{conto_id}")
@handle_errors
async def update_conto(conto_id: str, data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """I conti CEE non si modificano a mano (piano dismesso, PR 7)."""
    raise HTTPException(status_code=409, detail=f"Conto {conto_id} non modificabile. {MESSAGGIO_PIANO_CEE}")


@router.delete("/{conto_id}")
@handle_errors
async def delete_conto(conto_id: str) -> Dict[str, Any]:
    """I conti CEE non si eliminano (piano dismesso, PR 7)."""
    raise HTTPException(status_code=409, detail=f"Conto {conto_id} non eliminabile. {MESSAGGIO_PIANO_CEE}")


# Le regole di categorizzazione NON stanno qui: l'unico sistema e' la pagina Learning Machine >
# Regole categorizzazione (`/api/regole/*`, `regole_categorizzazione_fornitori|descrizioni`,
# `regole_categorie`). La vecchia collezione `regole_categorizzazione` e i suoi endpoint
# `/api/piano-conti/regole` (consolidamento 19/09/2026: il motore non li leggeva piu') sono
# stati tolti il 01/10/2026; i dati restano in archivio, nessuno li legge.

# ============== REGISTRAZIONE CONTABILE FATTURA ==============

@router.post("/registra-fattura")
@handle_errors
async def registra_fattura_contabilita(data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """
    Registra una fattura nella contabilità generale (partita doppia).

    Delega al MOTORE UNICO `app.services.registrazione_contabile` (P1 §6.1):
    idempotente, con numero registrazione, fonte documento, data competenza,
    DARE/AVERE, centro di costo e audit log.
    """
    from app.services.registrazione_contabile import registra_fattura as _registra

    db = Database.get_db()
    fattura_id = data.get("fattura_id")
    if not fattura_id:
        raise HTTPException(status_code=400, detail="fattura_id obbligatorio")

    fattura = await db["invoices"].find_one({"id": fattura_id})
    if not fattura:
        raise HTTPException(status_code=404, detail="Fattura non trovata")

    res = await _registra(db, fattura)
    if res.get("stato") == "gia_registrato":
        return {"success": False, "message": "Fattura già registrata in contabilità",
                "movimento_id": res.get("movimento_id")}
    if res.get("stato") != "registrato":
        return {"success": False, "message": res.get("motivo", "Registrazione non eseguita")}
    return {"success": True, "message": "Fattura registrata in contabilità",
            "movimento": res["movimento"]}


async def _nome_conto(codice: str) -> str:
    """Nome leggibile per un codice conto (alias operativo o CEE)."""
    from app.services.categorizzazione_contabile import PIANO_CONTI_ESTESO

    return (
        (PIANO_CONTI_ESTESO.get(codice) or {}).get("nome")
        or CONTI_UFFICIALI.get(codice)
        or CONTI_UFFICIALI.get(risolvi_codice_cee(codice) or "", codice)
    )


async def _conto_da_categoria(db, categoria: str) -> Optional[str]:
    """Mappa categoria → codice conto leggendo `regole_categorie` (scritta
    dalla pagina Excel `regole_categorizzazione.py`), con fallback ai default
    della stessa pagina se il titolare non ha ancora personalizzato quella
    categoria (stesso comportamento di `GET /api/regole` e del download
    Excel: DB prima, default poi).

    La categoria viene normalizzata (`normalizza_categoria`: minuscolo,
    underscore, SENZA accenti) prima di ogni confronto — stessa
    normalizzazione applicata al salvataggio di una regola/categoria in
    `regole_categorizzazione.py`. Prima di questo fix "Caffè" (scritto
    dall'utente) non combaciava mai con la chiave interna "caffe", e la
    regola restava silenziosamente inefficace (audit 19/09/2026)."""
    from app.routers.accounting.regole_categorizzazione import (
        DEFAULT_CATEGORIE,
        normalizza_categoria,
    )

    categoria_norm = normalizza_categoria(categoria)
    riga = await db["regole_categorie"].find_one({"categoria": categoria_norm})
    if riga and riga.get("conto"):
        return str(riga["conto"]).strip()

    default = DEFAULT_CATEGORIE.get(categoria_norm)
    return str(default["conto"]).strip() if default and default.get("conto") else None


def _regola_piu_specifica(
    regole: List[Dict[str, Any]], testo_lower: str
) -> Optional[Dict[str, Any]]:
    """La regola il cui pattern combacia con il testo, la più specifica
    (pattern più lungo) quando più regole combaciano — stesso principio già
    usato da `regole_riconoscimento_banca.trova_regola_per_descrizione` per
    lo stesso problema: due regole utente sovrapposte (es. "ACME" e
    "ACME SRL") davano un risultato diverso a seconda del solo ordine di
    iterazione del DB, che non è garantito stabile nel tempo (audit
    19/09/2026)."""
    migliore: Optional[Dict[str, Any]] = None
    for regola in regole:
        pattern = str(regola.get("pattern") or "").strip().lower()
        if pattern and pattern in testo_lower:
            if migliore is None or len(pattern) > len(str(migliore.get("pattern") or "")):
                migliore = regola
    return migliore


async def _conto_da_regole_utente(
    db, fornitore: str, linee: List[Dict[str, Any]]
) -> Optional[Dict[str, str]]:
    """Regole scritte DAVVERO dal titolare tramite l'Excel di
    `regole_categorizzazione.py` (le uniche 3 collezioni che quella pagina
    legge/scrive: `regole_categorizzazione_fornitori`,
    `regole_categorizzazione_descrizioni`, `regole_categorie`).

    Precedenza: fornitore prima di descrizione (un fornitore riconosciuto è
    un'identità più affidabile di una parola nella descrizione, stesso
    ordine dichiarato nel foglio "Istruzioni" dell'Excel). Match case-
    insensitive "contiene", non regex: i pattern li scrive un umano da Excel
    e possono contenere caratteri (``S.p.A.``, ``&``) che non sono regex
    valide o che avrebbero un significato diverso da quello letterale
    inteso dal titolare. Tra piu' regole dello stesso tipo che combaciano
    vince il pattern piu' specifico (`_regola_piu_specifica`), non il primo
    incontrato nell'iterazione del DB.

    Ritorna None se nessuna regola matcha, o se la categoria trovata non ha
    (ancora) un conto associato, o se il conto non esiste nel piano CEE.
    """
    fornitore_lower = (fornitore or "").strip().lower()
    categoria: Optional[str] = None

    if fornitore_lower:
        regole_forn = await db["regole_categorizzazione_fornitori"].find(
            {"attivo": True}
        ).to_list(5000)
        migliore = _regola_piu_specifica(regole_forn, fornitore_lower)
        if migliore:
            categoria = str(migliore.get("categoria") or "").strip()

    if not categoria and linee:
        regole_desc = await db["regole_categorizzazione_descrizioni"].find(
            {"attivo": True}
        ).to_list(5000)
        if regole_desc:
            for linea in linee:
                descr = str((linea or {}).get("descrizione") or "").strip().lower()
                if not descr:
                    continue
                migliore = _regola_piu_specifica(regole_desc, descr)
                if migliore:
                    categoria = str(migliore.get("categoria") or "").strip()
                    break

    if not categoria:
        return None

    codice_conto = await _conto_da_categoria(db, categoria)
    if not codice_conto or not risolvi_codice_cee(codice_conto):
        return None

    return {"codice": codice_conto, "nome": await _nome_conto(codice_conto)}


async def _segnala_conto_bassa_confidenza(
    db, *, fattura: Dict[str, Any], codice_scartato: str, confidenza: float, soglia: float,
) -> None:
    """Rende visibile un match del motore ricco scartato per bassa confidenza
    (audit 19/09/2026, fix "Mobile bar" -> Telefonia): stesso pattern di
    segnalazione gia' usato per l'anomalia cespiti in
    `registrazione_contabile._righe_capitalizzazione_cespiti` (upsert su
    `agenti_segnalazioni`, mai bloccante)."""
    logger.warning(
        "determina_conti_fattura: match motore ricco a bassa confidenza "
        "(%.2f < %.2f) per conto %s, fornitore=%r — fallback a 05.01.01, da verificare",
        confidenza, soglia, codice_scartato,
        fattura.get("supplier_name") or fattura.get("cedente_denominazione"),
    )
    fattura_id = fattura.get("id")
    try:
        await db["agenti_segnalazioni"].update_one(
            {"tipo": "conto_costo_bassa_confidenza", "fattura_id": fattura_id, "letta": False},
            {"$set": {
                "dettaglio": {
                    "conto_scartato": codice_scartato,
                    "confidenza": confidenza,
                    "soglia": soglia,
                    "fornitore": fattura.get("supplier_name") or fattura.get("cedente_denominazione"),
                },
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }, "$setOnInsert": {"created_at": datetime.now(timezone.utc).isoformat()}},
            upsert=True,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[PianoConti] segnalazione all'agente non registrata: la proposta "
            "sotto soglia resta senza traccia: %s", exc)


async def determina_conti_fattura(db, fattura: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    """Determina i conti da usare per registrare una fattura (motore unico,
    consolidamento 19/09/2026: prima esistevano 4 motori scollegati per
    questa scelta — questo è l'unico rimasto).

    Ordine di decisione:
      1. Regole utente scritte dall'Excel (`_conto_da_regole_utente`):
         fornitore, poi descrizione riga.
      2. Motore ricco `categorizzazione_contabile.categorizza_fattura_completa`
         sulle righe fattura: si prende il conto con l'importo aggregato
         maggiore (`riepilogo_conti`) — stesso algoritmo già usato da
         `POST /api/contabilita/ricategorizza-fatture` — MA solo se la
         confidenza del match che ha prodotto quel conto e' almeno
         `SOGLIA_CONFIDENZA_AUTOMATICA` (audit 19/09/2026: "Mobile bar con
         ripiani in legno" matchava il pattern debole "mobile" di Telefonia
         con la stessa confidenza di un match forte, scrivendo in automatico
         una deducibilita' 80% invece di 100% senza nessuna soglia ne'
         segnalazione). Sotto soglia il conto specifico NON si applica: si
         ricade sul fallback generico, come se il motore ricco non avesse
         trovato nulla, e il caso viene segnalato (mai una scrittura fiscale
         automatica a bassa confidenza, CLAUDE.md sezione F24).
      3. Fallback finale: 05.01.01 Acquisto merci (nessuna riga, il motore
         ricco non ha trovato alcun pattern, o il match trovato era sotto
         soglia).
    """
    from app.services.categorizzazione_contabile import (
        categorizza_fattura_completa,
        SOGLIA_CONFIDENZA_AUTOMATICA,
    )

    fornitore = fattura.get("supplier_name") or fattura.get("cedente_denominazione") or ""
    # Una fattura estera letta dal PDF non ha righe XML: le descrizioni lette
    # dall'AI (solo testo, senza importi) dicono comunque cosa si e' comprato.
    linee = fattura.get("linee") or [
        {"descrizione": testo} for testo in (fattura.get("descrizione_righe_ai") or []) if testo
    ]

    conto_costo = await _conto_da_regole_utente(db, fornitore, linee)

    if not conto_costo and linee:
        categorizzazione = categorizza_fattura_completa(linee, fornitore)
        riepilogo = categorizzazione.get("riepilogo_conti") or []
        dettaglio = categorizzazione.get("dettaglio_linee") or []
        if riepilogo:
            if any(c.get("importo") for c in riepilogo):
                principale = max(riepilogo, key=lambda c: c.get("importo", 0))
            else:
                # Righe senza importo (fattura estera letta dal PDF): vince il
                # conto con piu' righe, a parita' quello della prima riga.
                ordine = [r.get("conto_codice") for r in dettaglio]
                principale = max(riepilogo, key=lambda c: (
                    ordine.count(c["codice"]),
                    -ordine.index(c["codice"]) if c["codice"] in ordine else -len(ordine),
                ))
            codice_vincente = principale["codice"]
            # Confidenza del match: il massimo tra le righe che sono finite
            # su questo conto (basta UNA riga con evidenza forte per fidarsi
            # del conto anche se altre righe simili ci sono arrivate con un
            # pattern debole).
            confidenza_vincente = max(
                (float(riga.get("confidenza") or 0)
                 for riga in dettaglio if riga.get("conto_codice") == codice_vincente),
                default=0.0,
            )
            if confidenza_vincente >= SOGLIA_CONFIDENZA_AUTOMATICA:
                conto_costo = {
                    "codice": codice_vincente,
                    "nome": principale.get("nome") or await _nome_conto(codice_vincente),
                }
            else:
                await _segnala_conto_bassa_confidenza(
                    db, fattura=fattura, codice_scartato=codice_vincente,
                    confidenza=confidenza_vincente, soglia=SOGLIA_CONFIDENZA_AUTOMATICA,
                )

    if not conto_costo:
        conto_costo = {"codice": "05.01.01", "nome": "Acquisto merci"}

    return {
        "costo": conto_costo,
        "iva_credito": {"codice": "01.04.01", "nome": "IVA a credito"},
        "debito_fornitore": {"codice": "02.01.01", "nome": "Debiti v/fornitori"},
    }


async def aggiorna_saldo_conto(db, codice_conto: str, importo: float, tipo: str):
    """I saldi per conto non si persistono piu' (collezione ``piano_conti``
    dismessa, audit 03/09/2026 PR 7): il libro mastro e il bilancio di
    verifica li ricavano dalle scritture di ``movimenti_contabili`` e il
    Piano dei Conti da ``_calcola_saldi_piano_conti``. Rimane per
    compatibilita' con i chiamanti del motore §6.1: non scrive nulla."""
    if codice_conto and not risolvi_codice_cee(codice_conto):
        logger.warning("Conto %s fuori dal piano CEE (alias non mappato)", codice_conto)
    return None


# ============== MOVIMENTI CONTABILI ==============

@router.get("/conto/{codice}/movimenti")
@handle_errors
async def get_movimenti_per_conto(
    codice: str,
    limit: int = 50,
    anno: str = None,
    schema: str = None,
) -> Dict[str, Any]:
    """
    Dettaglio movimenti per un conto del piano dei conti.
    Logica SEMANTICA per conto — nessun fuzzy matching inaffidabile:
      - 01.01.01 (Cassa)          → prima_nota_cassa
      - 01.01.02 (Banca c/c)      → estratto_conto_movimenti (tutti)
      - 01.02.* (Crediti)         → fatture_ricevute non incassate
      - 02.01.* (Debiti fornitori) → fatture_ricevute non pagate
      - categoria=costi            → fatture_ricevute pagate
      - categoria=ricavi           → prima_nota_banca tipo=entrata
      - altri                      → info conto senza movimenti
    """
    db = Database.get_db()

    # Un solo piano: il codice puo' essere CEE (es. 55.01.01) oppure un alias
    # operativo (es. 05.01.09). La logica semantica qui sotto ragiona sui
    # codici operativi: con un CEE si considerano tutti i suoi alias, con un
    # alias soltanto quello. Otto codici operativi collidono con codici CEE
    # veri: la pagina Piano dei Conti passa ``schema=cee``, i vecchi link e
    # il dizionario articoli restano nello schema operativo.
    codice_richiesto = str(codice or "").strip()
    schema_cee = str(schema or "").strip().lower() == "cee"
    cee = risolvi_codice_cee(codice_richiesto, preferisci_operativo=not schema_cee)
    if not cee:
        raise HTTPException(status_code=404, detail=f"Conto {codice} non trovato nel piano CEE")
    conto = conto_cee(cee)
    richiesto_e_alias = codice_richiesto in OPERATIVO_A_UFFICIALE and not (
        schema_cee and conto_cee_valido(codice_richiesto)
    )
    if richiesto_e_alias:
        codici_operativi = [codice_richiesto]
    else:
        codici_operativi = alias_operativi(cee) or [codice_richiesto]
    conto["codice_richiesto"] = codice_richiesto
    conto["codici_operativi"] = codici_operativi
    codice = codici_operativi[0]

    cat  = (conto.get("categoria") or "").lower()

    movimenti: list = []
    fonte: str      = "nessuna"

    # ── CASSA ────────────────────────────────────────────────────────────────
    # Elenco coerente col saldo cumulativo calcolato in _calcola_saldi_piano_conti:
    # tutti i movimenti fino a fine anno selezionato, non solo quelli dell'anno.
    if cee == "19.03.03" or "01.01.01" in codici_operativi:
        q_cassa: dict = {}
        if anno:
            q_cassa["data"] = {"$lte": f"{anno}-12-31"}
        docs = await db["prima_nota_cassa"].find(
            q_cassa, {"_id": 0}
        ).sort("data", -1).limit(limit).to_list(limit)
        movimenti = [
            {"data": d.get("data"),
             "descrizione": d.get("causale") or d.get("descrizione") or d.get("riferimento") or "—",
             "importo": abs(safe_float(d.get("importo", 0))),
             "tipo": d.get("tipo") or ("entrata" if safe_float(d.get("importo", 0)) >= 0 else "uscita"),
             "categoria": d.get("categoria", ""),
             "fonte": "Prima Nota Cassa"}
            for d in docs
        ]
        fonte = "prima_nota_cassa"

    # ── BANCA C/C ─────────────────────────────────────────────────────────────
    # Stesso motivo della Cassa: elenco cumulativo fino a fine anno, coerente
    # col saldo calcolato in _calcola_saldi_piano_conti.
    elif cee in ("19.01.01", "19.01.05") or "01.01.02" in codici_operativi:
        # Prima prova prima_nota_banca (movimenti manuali confermati)
        q_banca: dict = {}
        if anno:
            q_banca["data"] = {"$lte": f"{anno}-12-31"}
        docs = await db["prima_nota_banca"].find(
            q_banca, {"_id": 0}
        ).sort("data", -1).limit(limit).to_list(limit)
        if not docs:
            # Fallback: estratto_conto_movimenti (collection reale e aggiornata
            # dell'estratto conto; "movimenti_bancari" era una tabella legacy
            # pre-migrazione, ferma, senza scritture recenti)
            docs = await db["estratto_conto_movimenti"].find(
                q_banca, {"_id": 0, "data": 1, "data_contabile": 1, "descrizione": 1,
                          "descrizione_originale": 1, "importo": 1, "tipo": 1, "categoria": 1}
            ).sort("data", -1).limit(limit).to_list(limit)
            movimenti = [
                {"data": d.get("data") or d.get("data_contabile"),
                 "descrizione": d.get("descrizione") or d.get("descrizione_originale") or "—",
                 "importo": abs(safe_float(d.get("importo", 0))),
                 "tipo": d.get("tipo", "uscita"),
                 "categoria": d.get("categoria", ""),
                 "fonte": "Estratto Conto"}
                for d in docs
            ]
            fonte = "estratto_conto_movimenti"
        else:
            movimenti = [
                {"data": d.get("data"),
                 "descrizione": d.get("descrizione") or d.get("causale") or "—",
                 "importo": abs(safe_float(d.get("importo", 0))),
                 "tipo": d.get("tipo", "uscita"),
                 "categoria": d.get("categoria", ""),
                 "fonte": "Prima Nota Banca"}
                for d in docs
            ]
            fonte = "prima_nota_banca"

    # ── CREDITI V/CLIENTI ─────────────────────────────────────────────────────
    elif any(c.startswith("01.02") for c in codici_operativi):
        # Una fattura fatta dopo lo scontrino e' gia' incassata al banco: non e' un credito.
        q_crediti: dict = {"gia_in_corrispettivi": {"$ne": True}}
        if anno:
            q_crediti["$or"] = [
                {"data_fattura": {"$gte": f"{anno}-01-01", "$lte": f"{anno}-12-31"}},
                {"date": {"$gte": f"{anno}-01-01", "$lte": f"{anno}-12-31"}},
            ]
        # "fatture" non è mai stata una collection reale (nessun altro punto del
        # codice la scrive): le fatture emesse (crediti v/clienti) vivono in
        # fatture_emesse (canonica P1 §5.5). Prima questo ramo restituiva sempre lista vuota.
        docs = await db["fatture_emesse"].find(
            q_crediti, {"_id": 0}
        ).sort("data_fattura", -1).limit(limit).to_list(limit)
        movimenti = [
            {"data": d.get("data_fattura") or d.get("date"),
             "descrizione": f"Fatt. {d.get('numero_fattura') or d.get('number') or ''} — {d.get('fornitore') or d.get('cliente') or d.get('client') or ''}",
             "importo": abs(safe_float(d.get("importo_totale") or d.get("amount") or 0)),
             "tipo": "entrata", "categoria": "fattura",
             "fonte": "Fatture Emesse"}
            for d in docs
        ]
        fonte = "fatture_emesse"

    # ── DEBITI V/FORNITORI ────────────────────────────────────────────────────
    # NB: "fatture_passive" non è mai stata la collection reale delle fatture
    # ricevute (nessun punto del codice la scrive) — le fatture ricevute vivono
    # in "invoices" (stessa collection usata da _calcola_saldi_piano_conti).
    # Prima questo ramo interrogava sempre una collection vuota → click sul
    # conto apriva una pagina senza movimenti, pur avendo un saldo diverso da 0.
    elif cee == "33.03.01" or any(c.startswith("02.01") for c in codici_operativi):
        q_debiti: dict = {
            "status": {"$nin": ["deleted", "archived", "archiviata"]},
            **FILTRO_NON_PAGATE,
        }
        if anno:
            q_debiti["invoice_date"] = {"$lte": f"{anno}-12-31"}
        docs = await db["invoices"].find(
            q_debiti,
            {"_id": 0, "supplier_name": 1, "invoice_number": 1, "invoice_date": 1,
             "total_amount": 1, "status": 1}
        ).sort("invoice_date", -1).limit(limit).to_list(limit)
        movimenti = [
            {"data": d.get("invoice_date"),
             "descrizione": f"Fatt. {d.get('invoice_number', '')} — {d.get('supplier_name', '')}",
             "importo": abs(safe_float(d.get("total_amount") or 0)),
             "tipo": "uscita", "categoria": d.get("status", ""),
             "fonte": "Fatture Ricevute"}
            for d in docs
        ]
        fonte = "invoices"

    # ── COSTI / ACQUISTI ──────────────────────────────────────────────────────
    # Stesso split per riga-fattura via dizionario_articoli usato dal saldo
    # (_calcola_saldi_piano_conti): PRIMA questo ramo elencava TUTTE le
    # fatture dell'anno per QUALSIASI sotto-conto costi, senza filtrare per
    # il conto effettivamente cliccato — segnalato dall'utente 18/07/2026:
    # cliccando "05.02.22 Noleggio automezzi" (saldo €0, Inattivo) usciva lo
    # stesso elenco misto di 40 fatture di fornitori completamente estranei
    # mostrato per "05.01.09 Acquisto caffè e affini". Ogni riga fattura è
    # assegnata al conto del dizionario articoli (o 05.01.01 di default se
    # l'articolo non è mappato) — qui si filtra a SOLO le righe del conto
    # richiesto, esattamente come fa il calcolo del saldo.
    elif cat in ("costi",):
        q_periodo: dict = {}
        if anno:
            q_periodo["$or"] = [
                {"invoice_date": {"$gte": f"{anno}-01-01", "$lte": f"{anno}-12-31"}},
                {"data_documento": {"$gte": f"{anno}-01-01", "$lte": f"{anno}-12-31"}},
            ]
        pipe_righe_conto = [
            *([{"$match": q_periodo}] if q_periodo else []),
            {"$unwind": {"path": "$linee", "preserveNullAndEmptyArrays": False}},
            {"$lookup": {
                "from": "dizionario_articoli",
                "localField": "linee.descrizione",
                "foreignField": "descrizione",
                "as": "diz",
            }},
            {"$addFields": {
                "conto_assegnato": {
                    "$ifNull": [{"$arrayElemAt": ["$diz.conto", 0]}, "05.01.01"]
                },
                "imponibile_riga": {
                    "$ifNull": [
                        "$linee.prezzo_totale",
                        {"$ifNull": ["$linee.imponibile", {"$ifNull": ["$linee.importo", 0]}]}
                    ]
                },
            }},
            # Il dizionario articoli puo' contenere sia l'alias operativo sia
            # il codice CEE (scelto dalla pagina Piano dei Conti).
            {"$match": {"conto_assegnato": (
                codice if richiesto_e_alias
                else {"$in": sorted(set(codici_operativi) | {cee})}
            )}},
            {"$sort": {"invoice_date": -1}},
            {"$limit": limit},
            {"$project": {
                "_id": 0, "invoice_date": 1, "invoice_number": 1, "supplier_name": 1,
                "status": 1, "imponibile_riga": 1, "linea_descrizione": "$linee.descrizione",
            }},
        ]
        docs = await db["invoices"].aggregate(pipe_righe_conto).to_list(limit)
        movimenti = [
            {"data": d.get("invoice_date"),
             "descrizione": f"Fatt. {d.get('invoice_number', '')} — {d.get('supplier_name', '')} — {d.get('linea_descrizione', '')}",
             "importo": abs(safe_float(d.get("imponibile_riga") or 0)),
             "tipo": "uscita", "categoria": d.get("status", ""),
             "fonte": "Fatture Ricevute (riga)",
             "linea_descrizione": d.get("linea_descrizione", "")}
            for d in docs
        ]
        fonte = "invoices_righe"

        # Safety net: se il dizionario è del tutto vuoto (nessuna riga
        # matchata in nessun conto), _calcola_saldi_piano_conti ricade su
        # "tutto l'imponibile su 05.01.01" — replichiamo lo stesso fallback
        # qui, altrimenti 05.01.01 risulterebbe vuoto pur avendo un saldo.
        if "05.01.01" in codici_operativi and not movimenti:
            diz_count = await db["dizionario_articoli"].count_documents({})
            if diz_count == 0:
                docs_fallback = await db["invoices"].find(
                    q_periodo,
                    {"_id": 0, "supplier_name": 1, "invoice_number": 1, "invoice_date": 1,
                     "total_amount": 1, "status": 1}
                ).sort("invoice_date", -1).limit(limit).to_list(limit)
                movimenti = [
                    {"data": d.get("invoice_date"),
                     "descrizione": f"Fatt. {d.get('invoice_number', '')} — {d.get('supplier_name', '')}",
                     "importo": abs(safe_float(d.get("total_amount") or 0)),
                     "tipo": "uscita", "categoria": d.get("status", ""),
                     "fonte": "Fatture Ricevute"}
                    for d in docs_fallback
                ]
                fonte = "invoices"

    # ── RICAVI ────────────────────────────────────────────────────────────────
    # I corrispettivi sono importati come totale giornaliero unico, senza
    # disaggregazione per settore/reparto: solo 04.01.01 ha un saldo reale
    # (vedi _calcola_saldi_piano_conti). Mostrare l'elenco completo dei
    # corrispettivi anche per gli altri sotto-conti (bar, cucina, servizi...)
    # farebbe credere che abbiano un saldo proprio quando in realtà è 0.
    elif cat in ("ricavi",):
        if "04.01.01" not in codici_operativi:
            fonte = "nessuna"
        else:
            q_ricavi: dict = {}
            if anno:
                q_ricavi["anno"] = int(anno)
            docs_corr = await db["corrispettivi"].find(
                q_ricavi, {"_id": 0, "data": 1, "descrizione": 1, "importo": 1, "totale": 1, "totale_imponibile": 1}
            ).sort("data", -1).limit(limit).to_list(limit)
            movimenti = [
                {"data": d.get("data"),
                 "descrizione": d.get("descrizione") or "Corrispettivo",
                 "importo": abs(safe_float(d.get("importo") or d.get("totale") or 0)),
                 "tipo": "entrata", "categoria": "corrispettivo",
                 "fonte": "Corrispettivi"}
                for d in docs_corr
            ]
            fonte = "corrispettivi"

    # ── PATRIMONIO NETTO ──────────────────────────────────────────────────────
    # Capitale sociale e riserve non hanno una fonte transazionale nel
    # gestionale (sono dati statutari, non movimenti): Utile/Perdita
    # d'esercizio invece è calcolato come Ricavi − Costi dell'anno.
    elif cat == "patrimonio_netto":
        if {"03.03.01", "03.03.02"} & set(codici_operativi):
            saldi_periodo = await _calcola_saldi_piano_conti(db, anno)
            ricavi = sum(v for k, v in saldi_periodo.items()
                         if categoria_cee(risolvi_codice_cee(k)) == "ricavi")
            costi = sum(v for k, v in saldi_periodo.items()
                        if categoria_cee(risolvi_codice_cee(k)) == "costi")
            risultato = round(ricavi - costi, 2)
            movimenti = [{
                "data": f"{anno}-12-31" if anno else "",
                "descrizione": f"Ricavi {ricavi:.2f} − Costi {costi:.2f}",
                "importo": abs(risultato),
                "tipo": "entrata" if risultato >= 0 else "uscita",
                "categoria": "risultato_esercizio",
                "fonte": "Calcolato (Ricavi − Costi)",
            }]
            fonte = "calcolato"
        else:
            fonte = "nessuna"

    totale_importo = sum(m.get("importo", 0) for m in movimenti)

    return {
        "conto": conto,
        "movimenti": movimenti,
        "totale_movimenti": len(movimenti),
        "totale_importo": round(totale_importo, 2),
        "fonte": fonte,
        "nota": (
            "Utile/Perdita d'esercizio calcolato come Ricavi meno Costi del periodo, "
            "non è un movimento registrato direttamente."
        ) if fonte == "calcolato" else (
            "Movimenti contabili diretti non disponibili — "
            "i dati mostrati provengono dalla fonte più rilevante per questo conto."
        ) if movimenti else (
            "Capitale sociale e riserve sono dati statutari, non tracciati come movimenti in questo gestionale."
            if cat == "patrimonio_netto" else
            "I corrispettivi non sono disaggregati per settore: solo il totale (04.01.01) ha un saldo reale."
            if cat == "ricavi" else
            "Nessun movimento disponibile per questo conto nel periodo selezionato."
        ),
    }


@router.get("/movimenti")
@handle_errors
async def get_movimenti_contabili(
    skip: int = 0,
    limit: int = 50,
    data_da: str = None,
    data_a: str = None
) -> Dict[str, Any]:
    """Ottiene i movimenti contabili."""
    db = Database.get_db()

    query = {}
    if data_da:
        query["data_documento"] = {"$gte": data_da}
    if data_a:
        if "data_documento" in query:
            query["data_documento"]["$lte"] = data_a
        else:
            query["data_documento"] = {"$lte": data_a}

    movimenti = await db[COLLECTION_MOVIMENTI_CONTABILI].find(
        query, {"_id": 0}
    ).sort("data_registrazione", -1).skip(skip).limit(limit).to_list(limit)

    totale = await db[COLLECTION_MOVIMENTI_CONTABILI].count_documents(query)

    return {
        "movimenti": movimenti,
        "totale": totale,
        "skip": skip,
        "limit": limit
    }


@router.get("/bilancio")
@handle_errors
async def get_bilancio(anno: str = None) -> Dict[str, Any]:
    """Bilancio completo (SP + CE) con saldi filtrati per anno.
    Usa `_calcola_saldi_piano_conti` come fonte unica di verità e il piano
    CEE ufficiale come unico elenco di conti (PR 7): compaiono i conti che
    hanno un alias operativo o un saldo, cosi' un codice non viene mai
    sommato due volte.
    """
    db = Database.get_db()

    real_saldi = await _calcola_saldi_piano_conti(db, anno)
    saldi_cee = saldi_in_cee(real_saldi)
    conti = [
        conto for conto in piano_conti_cee(real_saldi)
        if conto["alias_operativi"] or abs(saldi_cee.get(conto["codice"], 0.0)) >= 0.005
    ]

    bilancio = {
        "anno": anno,
        "stato_patrimoniale": {
            "attivo":            {"conti": [], "totale": 0.0},
            "passivo":           {"conti": [], "totale": 0.0},
            "patrimonio_netto":  {"conti": [], "totale": 0.0},
        },
        "conto_economico": {
            "ricavi":     {"conti": [], "totale": 0.0},
            "costi":      {"conti": [], "totale": 0.0},
            "risultato":  0.0,
        }
    }

    for conto in conti:
        codice = conto.get("codice", "")
        saldo = saldi_cee.get(codice, 0.0)
        categoria = conto.get("categoria", "")

        info = {"codice": codice, "nome": conto.get("nome"), "saldo": saldo,
                "alias_operativi": conto.get("alias_operativi") or []}

        if categoria == "attivo":
            bilancio["stato_patrimoniale"]["attivo"]["conti"].append(info)
            bilancio["stato_patrimoniale"]["attivo"]["totale"] += saldo
        elif categoria == "passivo":
            bilancio["stato_patrimoniale"]["passivo"]["conti"].append(info)
            bilancio["stato_patrimoniale"]["passivo"]["totale"] += saldo
        elif categoria == "patrimonio_netto":
            bilancio["stato_patrimoniale"]["patrimonio_netto"]["conti"].append(info)
            bilancio["stato_patrimoniale"]["patrimonio_netto"]["totale"] += saldo
        elif categoria == "ricavi":
            bilancio["conto_economico"]["ricavi"]["conti"].append(info)
            bilancio["conto_economico"]["ricavi"]["totale"] += saldo
        elif categoria == "costi":
            bilancio["conto_economico"]["costi"]["conti"].append(info)
            bilancio["conto_economico"]["costi"]["totale"] += saldo

    bilancio["conto_economico"]["risultato"] = (
        bilancio["conto_economico"]["ricavi"]["totale"] -
        bilancio["conto_economico"]["costi"]["totale"]
    )

    # Round
    for key in ["attivo", "passivo", "patrimonio_netto"]:
        bilancio["stato_patrimoniale"][key]["totale"] = round(bilancio["stato_patrimoniale"][key]["totale"], 2)
    for key in ["ricavi", "costi"]:
        bilancio["conto_economico"][key]["totale"] = round(bilancio["conto_economico"][key]["totale"], 2)
    bilancio["conto_economico"]["risultato"] = round(bilancio["conto_economico"]["risultato"], 2)

    # §6.2/§6.3: vista derivata in PIANO DEI CONTI UFFICIALE CEE (scelta utente: il piano
    # canonico è solo quello ufficiale del bilancio). Converte i saldi operativi interni
    # nei conti ufficiali senza alterare l'output storico soprastante.
    try:
        from app.services.mapping_piano_conti import classifica_saldi_ufficiale
        voci_ufficiali = classifica_saldi_ufficiale(real_saldi)
        bilancio["bilancio_ufficiale"] = {
            "stato_patrimoniale": [v for v in voci_ufficiali.values() if v["sezione"] == "SP"],
            "conto_economico": [v for v in voci_ufficiali.values() if v["sezione"] == "CE"],
            "nota": "Saldi riclassificati sul piano dei conti ufficiale CEE (mapping_piano_conti).",
        }
    except Exception as e:
        logger.warning(f"Vista bilancio ufficiale non disponibile: {e}")

    return bilancio


@router.post("/registra-tutte-fatture")
@handle_errors
async def registra_tutte_fatture_contabilita(
    dry_run: bool = Query(False, description="Solo conteggio, nessuna scrittura"),
) -> Dict[str, Any]:
    """
    Registra tutte le fatture non ancora registrate in contabilità.
    Delega al MOTORE UNICO `app.services.registrazione_contabile` (P1 §6.1).
    """
    from app.services.registrazione_contabile import registra_tutte_fatture
    return await registra_tutte_fatture(Database.get_db(), dry_run=bool(dry_run is True))


@router.post("/registra-corrispettivi")
@handle_errors
async def registra_corrispettivi_contabilita(
    dry_run: bool = Query(False, description="Solo conteggio, nessuna scrittura"),
) -> Dict[str, Any]:
    """
    Registra i corrispettivi in contabilità (Cassa/Banca -> Ricavi + IVA a debito).
    Delega al MOTORE UNICO `app.services.registrazione_contabile` (P1 §6.1).
    """
    from app.services.registrazione_contabile import registra_tutti_corrispettivi
    return await registra_tutti_corrispettivi(Database.get_db(), dry_run=bool(dry_run is True))


@router.post("/registra-pregresso")
@handle_errors
async def registra_pregresso_contabilita(
    dry_run: bool = Query(False, description="Solo conteggio, nessuna scrittura"),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Recupero del PREGRESSO non registrato (audit 03/09/2026 §2, PR 8).

    Dal deploy della registrazione automatica ogni fattura/corrispettivo
    entra nel libro giornale al momento dell'import; questo comando, riservato
    all'amministratore e idempotente, registra in un solo giro tutto cio' che
    era arrivato prima (riusa `/registra-tutte-fatture` e
    `/registra-corrispettivi`: un solo motore, nessun sistema parallelo).
    `?dry_run=true` restituisce subito i conteggi senza scrivere.

    Il giro vero parte in background e risponde subito (16/09/2026: con
    1.043 documenti superava il timeout del gateway Render, il client
    riceveva 499/502 mentre il server continuava senza che nessuno potesse
    seguirne l'esito). Avanzamento ed esito finale: `GET .../registra-pregresso/stato`.
    """
    from app.services.registrazione_contabile import (
        avvia_pregresso_in_background, registra_pregresso,
    )
    db = Database.get_db()
    if dry_run is True:
        return await registra_pregresso(db, dry_run=True)
    if not avvia_pregresso_in_background(db):
        return {"status": "running", "message": "Registrazione del pregresso già in corso"}
    return {"status": "started", "message": "Registrazione del pregresso avviata"}


@router.get("/registra-pregresso/stato")
@handle_errors
async def stato_registra_pregresso(
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Avanzamento (fase, documenti fatti/totale, registrati, errori) ed esito
    dell'ultimo giro di `POST /registra-pregresso`."""
    from app.services.registrazione_contabile import stato_pregresso
    return await stato_pregresso(Database.get_db())
