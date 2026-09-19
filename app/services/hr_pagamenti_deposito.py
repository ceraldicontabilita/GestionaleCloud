"""Ponte gestionale -> HR per i PAGAMENTI degli stipendi.

Decisione del titolare (14/09/2026, audit E2E): l'import e' centralizzato nel
gestionale ("se importo da /documenti#tab=import i dati me li devo trovare in
/hr/dipendenti/paghe-bonifici"). Il gestionale legge i PDF dei bonifici
(fascicolo Drive ``05_PERSONALE_E_CEDOLINI/DIPENDENTI/<persona>/BONIFICI``,
Import documenti, upload dalla pagina salari) e gli estratti conto bancari;
l'archivio dei pagamenti che gli utenti vedono e' pero' quello dell'app HR:

* ``pagamenti_esiti`` (un documento per bonifico ricevuto, chiave ``key``),
* ``paghe_mensili`` (busta del mese, stato ``in_attesa_pagamento``/``parziale``/
  ``pagato`` ricalcolato dal MOTORE UNICO ``_ricalcola_stato_paga``),
* ``bonifici_da_associare`` (coda manuale: dipendente non univoco o causale
  senza il segnale "stipendio" — mai indovinato).

Questo modulo scrive in quelle collezioni attraverso il database HR in-process
(``app.hr.database.Database.get_db()``: stesso adattatore, stesse regole
dell'app HR) e riusa le funzioni HR gia' esistenti (``_indici_dipendenti``,
``_ricalcola_stato_paga``, ``_e_movimento_non_stipendio``) invece di copiarle.

Due ingressi, una sola logica di deposito:

* ``deposita_bonifico_transfer_in_hr`` — un documento di ``bonifici_transfers``
  (PDF letto dal parser del gestionale). Chiave HR ``gc:<sha256 del PDF[:24]>``;
  il PDF viaggia con l'esito (``pdf_data``) cosi' in HR si puo' riaprire.
* ``deposita_movimento_banca_in_hr`` — una riga di ``estratto_conto_movimenti``
  (uscita "VOSTRA DISPOSIZIONE ... FAVORE <dipendente> ... stip luglio 2026").
  Chiave HR ``ecm:<id movimento>``, ``cro`` dal riferimento bancario "RIF. ...".

Regole comuni (le stesse dell'importatore Drive dell'app HR):

* dipendente risolto da codice fiscale, poi nome completo univoco, poi
  cognome univoco; ambiguo -> coda ``bonifici_da_associare``; nessun
  dipendente -> non e' un pagamento HR (fornitore, PayPal, socio);
* decisione del titolare (19/09/2026): **il nome/cognome di un dipendente
  riconosciuto in modo univoco basta da solo** come segnale che e' un
  pagamento a lui, senza bisogno della parola "stipendio/salario/..." in
  causale ne' di un lotto paghe — "non posso pagare un bonifico a, ad
  esempio, Vespa Vincenzo e aspettarmi di pagare una fattura di un
  fornitore, il nome di un dipendente e' un dipendente". Il ``fascicolo``
  Drive e il ``lotto_paghe`` bancario restano registrati sul pagamento
  depositato (campo ``segnale``, utile per distinguere a posteriori un
  lotto di paghe da un bonifico isolato) ma non decidono piu' se
  depositarlo: quello lo decide solo il nome risolto in modo univoco;
* resta pero' il veto esplicito: TFR, fatture, commissioni, mutui, fornitori
  (``_e_movimento_non_stipendio``, ``_ESCLUSIONE_RE``) non entrano mai,
  nemmeno in coda, **anche quando la causale contiene un nome di dipendente
  riconosciuto**: la causale che dice chiaramente "e' un'altra cosa" vince
  sempre sul nome;
* competenza: periodo scritto in causale/nome file, altrimenti la regola del
  giorno 25 del gestionale (``stipendi_bonifici.competenza_bonifico_stipendio``);
* dedup: stesso hash del PDF o stessa chiave -> gia' presente; stesso
  dipendente + stesso importo + data entro 3 giorni -> e' lo STESSO pagamento
  visto da un'altra fonte (PDF vs riga banca vs CSV): l'esito esistente viene
  solo arricchito (cro, hash, PDF) e mai duplicato.

Ogni documento sorgente del gestionale riceve il marcatore ``hr_deposito``
(``esito``, ``key``, ``dipendente_id``, ``at``): il job periodico
``hr_pagamenti_deposito`` (scheduler) riprende solo i documenti senza
marcatore, quindi ogni punto di inserimento del gestionale (Drive, email,
upload, API) finisce in HR senza doverli agganciare uno per uno.
Se il database HR non e' configurato il deposito e' un no-op segnalato una
volta sola nel log: l'ingestione contabile non deve mai fallire per l'HR.
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

CAMPO_MARCATORE = "hr_deposito"
PREFISSO_KEY_PDF = "gc"
PREFISSO_KEY_BANCA = "ecm"
ORIGINE_PDF = "gestionale-bonifico-pdf"
ORIGINE_BANCA = "gestionale-estratto-conto"
TOLLERANZA_GIORNI = 3
TOLLERANZA_IMPORTO = 0.01

ESITO_DEPOSITATO = "depositato"
ESITO_ARRICCHITO = "arricchito"
ESITO_DUPLICATO = "duplicato"
ESITO_IN_CODA = "in_coda"
ESITO_NON_DIPENDENTE = "non_dipendente"
ESITO_NON_STIPENDIO = "non_stipendio"
ESITO_DATI_INCOMPLETI = "dati_incompleti"
ESITO_HR_NON_CONFIGURATO = "hr_non_configurato"

_CF_RE = re.compile(r"\b([A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z])\b", re.I)
# Pagamenti a un dipendente che NON sono lo stipendio del mese: non entrano
# in pagamenti_esiti e non vanno nemmeno in coda.
_ESCLUSIONE_RE = re.compile(
    r"\bTFR\b|fattur|\bFPR\b|\bFT\b\s*\d|prestit|finanziament|COMM\.?\s*SU|"
    r"rimbors|\bnota\s+spese|fornitor|"
    # Audit 19/09/2026 su PR #500: un omonimo di un dipendente puo' comparire
    # come beneficiario di un pagamento che non e' affatto uno stipendio —
    # un fornitore individuale/professionista (niente SRL/SPA da riconoscere)
    # o un pagamento occasionale. Queste parole non compaiono mai in una vera
    # causale di stipendio, quindi escludono senza creare falsi negativi.
    r"per\s+conto\s+di|consulenz|occasional|ritenut|caparra|ristrutturazion|"
    r"\blavori\b",
    re.I,
)
_RIF_BANCA_RE = re.compile(r"RIF\.?\s*([A-Z0-9]+(?:/[0-9]+)?)", re.I)
# Addebito cumulativo della banca su piu' persone, senza nominarne nessuna:
# e' proprio il caso per cui esiste la coda HR "bonifici da associare".
_BENEFICIARI_DIVERSI_RE = re.compile(r"BENEFICIARI\s+(VARI|DIVERSI)", re.I)
# Un giorno in cui l'azienda dispone bonifici ad almeno N dipendenti diversi
# e' un lotto paghe (acconti o saldi): il segnale "stipendio" in causale non
# serve. Sotto questa soglia decide una persona (coda HR).
LOTTO_PAGHE_MIN_DIPENDENTI = 3

_avviso_non_configurato_emesso = False


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm(testo: Any) -> str:
    return re.sub(r"\s+", " ", str(testo or "").strip()).lower()


def _importo(valore: Any) -> Optional[float]:
    if valore is None or valore == "" or isinstance(valore, bool):
        return None
    try:
        importo = round(abs(float(valore)), 2)
    except (TypeError, ValueError):
        return None
    return importo if importo > 0 else None


def _data_iso(valore: Any) -> Optional[str]:
    """``YYYY-MM-DD`` da ISO (anche con ora/fuso), ``dd/mm/yyyy`` o datetime."""
    if isinstance(valore, datetime):
        return valore.strftime("%Y-%m-%d")
    testo = str(valore or "").strip()
    if not testo:
        return None
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", testo)
    if m:
        return "%s-%s-%s" % m.groups()
    m = re.match(r"^(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})", testo)
    if m:
        return "%s-%02d-%02d" % (m.group(3), int(m.group(2)), int(m.group(1)))
    return None


def _giorni_tra(a: Optional[str], b: Optional[str]) -> Optional[int]:
    try:
        da = datetime.strptime(str(a)[:10], "%Y-%m-%d")
        db_ = datetime.strptime(str(b)[:10], "%Y-%m-%d")
    except (TypeError, ValueError):
        return None
    return abs((da - db_).days)


def _nome_dipendente(dip: Dict[str, Any]) -> str:
    return (
        dip.get("nome_completo")
        or " ".join(p for p in (dip.get("cognome"), dip.get("nome")) if p)
        or ""
    ).strip()


# ── riconoscimento del dipendente e della natura del pagamento ───────────────

def risolvi_dipendente(indici: Dict[str, Any], testo: str) -> Tuple[Optional[Dict[str, Any]], str]:
    """``(dipendente, motivo)``: ``motivo`` in ``cf``/``nome``/``cognome``
    quando univoco, ``ambiguo`` se piu' persone combaciano, ``nessuno`` altrimenti.

    Stessa scala dell'importatore Drive HR (``trova_dipendente``), con il
    codice fiscale davanti: nelle causali bancarie "ADD.TOT - CRLVLR88H14F839O
    stipendio" e' l'identita' piu' sicura.
    """
    haystack = _norm(testo)
    if not haystack:
        return None, "nessuno"
    by_cf = indici.get("cf") or {}
    trovati_cf = {}
    for m in _CF_RE.finditer(str(testo or "")):
        dip = by_cf.get(m.group(1).upper())
        if dip:
            trovati_cf[dip["id"]] = dip
    if len(trovati_cf) == 1:
        return next(iter(trovati_cf.values())), "cf"
    if len(trovati_cf) > 1:
        return None, "ambiguo"

    per_nome = {}
    for nome_n, dip in (indici.get("nome") or {}).items():
        if nome_n and nome_n in haystack:
            per_nome[dip["id"]] = dip
    if len(per_nome) == 1:
        return next(iter(per_nome.values())), "nome"
    if len(per_nome) > 1:
        return None, "ambiguo"

    per_cognome = {}
    for cogn, lista in (indici.get("cogn") or {}).items():
        if cogn and re.search(r"(?<![a-z'])" + re.escape(cogn) + r"(?![a-z])", haystack):
            for dip in lista:
                per_cognome[dip["id"]] = dip
    if len(per_cognome) == 1:
        return next(iter(per_cognome.values())), "cognome"
    if len(per_cognome) > 1:
        return None, "ambiguo"
    return None, "nessuno"


def e_pagamento_non_stipendio(testo: str) -> bool:
    """TFR, fatture, commissioni, mutui/fornitori/tasse: mai in HR."""
    if _ESCLUSIONE_RE.search(testo or ""):
        return True
    from app.hr.routers.dipendenti_cloud import _e_movimento_non_stipendio

    return _e_movimento_non_stipendio(testo or "")


def _periodo(mese: Any, anno: Any) -> Optional[Tuple[int, int]]:
    try:
        m, a = int(mese or 0), int(anno or 0)
    except (TypeError, ValueError):
        return None
    return (m, a) if 1 <= m <= 14 and a >= 2000 else None


def _anno_per_mese(mese: int, data: Optional[str]) -> Optional[int]:
    """Anno di competenza quando la causale dice solo il mese: quello del
    bonifico, salvo dicembre pagato a gennaio."""
    if not data:
        return None
    anno, mese_pag = int(data[:4]), int(data[5:7])
    if mese == 12 and mese_pag == 1:
        return anno - 1
    return anno


def periodo_bonifico(testo: str, data: Optional[str],
                     mese_dichiarato: Any = None, anno_dichiarato: Any = None) -> Optional[Tuple[int, int]]:
    """Competenza ``(mese, anno)``: campi gia' estratti dal parser, poi la
    causale/nome file, infine la regola del giorno 25 sulla data del bonifico."""
    from app.services.stipendi_bonifici import estrai_periodo_causale, competenza_bonifico_stipendio

    esplicito = _periodo(mese_dichiarato, anno_dichiarato)
    if esplicito:
        return esplicito
    try:
        mese_solo = int(mese_dichiarato or 0)
    except (TypeError, ValueError):
        mese_solo = 0
    if 1 <= mese_solo <= 14:
        anno = _anno_per_mese(mese_solo, data)
        if anno:
            return mese_solo, anno
    dalla_causale = estrai_periodo_causale(testo or "")
    if dalla_causale:
        return dalla_causale
    return competenza_bonifico_stipendio(data) if data else None


def _cro_da_descrizione(descrizione: str) -> Optional[str]:
    m = _RIF_BANCA_RE.search(descrizione or "")
    return m.group(1) if m else None


# ── contesto HR (indici caricati una volta per giro) ─────────────────────────

class ContestoHR:
    """Database HR + indici dipendenti/esiti caricati una sola volta per giro.

    Per un deposito singolo (hook dell'ingest) il costo e' quello di un giro
    da un documento; per il backfill evita N query per documento sull'adattatore
    HR, che non ha indici.
    """

    def __init__(self, db_hr, indici: Dict[str, Any], esiti: List[Dict[str, Any]],
                 hash_in_coda: set):
        self.db = db_hr
        self.indici = indici
        self.per_hash: Dict[str, Dict[str, Any]] = {}
        self.per_key: Dict[str, Dict[str, Any]] = {}
        self.per_dipendente: Dict[str, List[Dict[str, Any]]] = {}
        for e in esiti:
            self._indicizza(e)
        self.hash_in_coda = set(hash_in_coda)
        self.periodi_toccati: set = set()

    def _indicizza(self, esito: Dict[str, Any]) -> None:
        if esito.get("hash"):
            self.per_hash[esito["hash"]] = esito
        if esito.get("key"):
            self.per_key[esito["key"]] = esito
        if esito.get("dipendente_id"):
            self.per_dipendente.setdefault(str(esito["dipendente_id"]), []).append(esito)

    def esito_equivalente(self, dipendente_id: str, importo: float, data: Optional[str],
                          hash_pdf: Optional[str], key: str) -> Tuple[Optional[Dict[str, Any]], str]:
        if hash_pdf and hash_pdf in self.per_hash:
            return self.per_hash[hash_pdf], "hash"
        if key in self.per_key:
            return self.per_key[key], "key"
        for e in self.per_dipendente.get(str(dipendente_id), []):
            try:
                stesso_importo = abs(float(e.get("importo") or 0) - importo) <= TOLLERANZA_IMPORTO
            except (TypeError, ValueError):
                continue
            if not stesso_importo:
                continue
            giorni = _giorni_tra(e.get("data"), data)
            if giorni is not None and giorni <= TOLLERANZA_GIORNI:
                return e, "vicino"
        return None, ""


def _db_hr():
    """Database HR in-process, ``None`` se non configurato (segnalato una volta)."""
    global _avviso_non_configurato_emesso
    from app.hr.database import Database, DatabaseNonConfigurato

    db_hr = Database.get_db()
    if db_hr is None or isinstance(db_hr, DatabaseNonConfigurato):
        if not _avviso_non_configurato_emesso:
            _avviso_non_configurato_emesso = True
            logger.warning(
                "[HR deposito pagamenti] database HR non configurato: bonifici ed "
                "estratti conto restano solo nel gestionale"
            )
        return None
    return db_hr


async def carica_contesto_hr() -> Optional[ContestoHR]:
    db_hr = _db_hr()
    if db_hr is None:
        return None
    from app.hr.routers.dipendenti_cloud import _indici_dipendenti

    indici = await _indici_dipendenti(db_hr)
    esiti = await db_hr.pagamenti_esiti.find({}, {"_id": 0, "pdf_data": 0}).to_list(None)
    in_coda = set()
    async for b in db_hr.bonifici_da_associare.find({}, {"_id": 0, "hash": 1}):
        if b.get("hash"):
            in_coda.add(b["hash"])
    return ContestoHR(db_hr, indici, esiti, in_coda)


# ── deposito vero e proprio ──────────────────────────────────────────────────

async def _scrivi_esito(ctx: ContestoHR, esito: Dict[str, Any]) -> None:
    await ctx.db.pagamenti_esiti.update_one({"key": esito["key"]}, {"$set": esito}, upsert=True)
    ctx._indicizza(esito)
    dip, mese, anno = esito["dipendente_id"], int(esito["mese"]), int(esito["anno"])
    await ctx.db.paghe_mensili.update_one(
        {"dipendente_id": dip, "anno": anno, "mese": mese},
        {"$set": {"dipendente_id": dip, "anno": anno, "mese": mese,
                  "bonifico_da_esiti": True, "updated_at": _now_iso()}},
        upsert=True,
    )
    ctx.periodi_toccati.add((dip, anno, mese))


async def _arricchisci_esito(ctx: ContestoHR, esistente: Dict[str, Any],
                             nuovo: Dict[str, Any]) -> List[str]:
    """Completa i soli campi vuoti dell'esito gia' presente (mai sovrascrive)."""
    aggiunte: Dict[str, Any] = {}
    for campo in ("cro", "hash", "pdf_data", "beneficiario", "causale",
                  "gestionale_transfer_id", "gestionale_movimento_id", "gestionale_fonte"):
        if nuovo.get(campo) and not esistente.get(campo):
            aggiunte[campo] = nuovo[campo]
    if aggiunte.get("pdf_data"):
        aggiunte["ha_pdf"] = True
    if not aggiunte:
        return []
    await ctx.db.pagamenti_esiti.update_one({"key": esistente["key"]}, {"$set": aggiunte})
    esistente.update({k: v for k, v in aggiunte.items() if k != "pdf_data"})
    if aggiunte.get("hash"):
        ctx.per_hash[aggiunte["hash"]] = esistente
    return sorted(aggiunte)


async def _metti_in_coda(ctx: ContestoHR, *, hash_pdf: Optional[str], data: Optional[str],
                         importo: Optional[float], causale: str, pdf_filename: Optional[str],
                         pdf_data: Optional[str], fonte: str, riferimento: Dict[str, Any]) -> str:
    coda_id = str(uuid.uuid4())
    await ctx.db.bonifici_da_associare.insert_one({
        "id": coda_id, "hash": hash_pdf, "data": data, "importo": importo,
        "causale": causale, "pdf_filename": pdf_filename, "pdf_data": pdf_data,
        "fonte": fonte, "stato": "da_associare", "created_at": _now_iso(),
        **riferimento,
    })
    if hash_pdf:
        ctx.hash_in_coda.add(hash_pdf)
    return coda_id


async def _ricalcola_periodi(ctx: ContestoHR) -> None:
    """Stessa sequenza dell'importatore Drive HR: prima ``bonifico_importo`` =
    somma degli esiti del periodo (anche 0, se un esito e' stato tolto), poi
    il motore unico ``_ricalcola_stato_paga``."""
    from app.hr.routers.dipendenti_cloud import _ricalcola_stato_paga

    while ctx.periodi_toccati:
        dip, anno, mese = ctx.periodi_toccati.pop()
        tot = 0.0
        async for e in ctx.db.pagamenti_esiti.find(
                {"dipendente_id": dip, "mese": mese, "anno": anno}, {"_id": 0, "importo": 1}):
            tot += float(e.get("importo") or 0)
        await ctx.db.paghe_mensili.update_one(
            {"dipendente_id": dip, "anno": anno, "mese": mese},
            {"$set": {"bonifico_importo": round(tot, 2), "bonifico_ricevuto": tot > 0,
                      "bonifico_da_esiti": True, "updated_at": _now_iso()}})
        await _ricalcola_stato_paga(ctx.db, dip, anno, mese)


def _marcatore(esito: str, **extra: Any) -> Dict[str, Any]:
    marca = {"esito": esito, "at": _now_iso()}
    marca.update({k: v for k, v in extra.items() if v is not None})
    return marca


async def _marca(db, collezione: str, doc_id: Any, marca: Dict[str, Any], dry_run: bool) -> None:
    if dry_run or doc_id is None:
        return
    await db[collezione].update_one({"id": doc_id}, {"$set": {CAMPO_MARCATORE: marca}})


async def _deposita(
    ctx: ContestoHR, *, key: str, testo: str, data: Optional[str], importo: Optional[float],
    hash_pdf: Optional[str], cro: Optional[str], causale: str, pdf_filename: Optional[str],
    pdf_data: Optional[str], origine: str, mese_dichiarato: Any, anno_dichiarato: Any,
    riferimento: Dict[str, Any], dry_run: bool, segnale_esplicito: Optional[str] = None,
) -> Dict[str, Any]:
    """Cuore comune ai due ingressi. Ritorna il marcatore da scrivere sul documento sorgente.

    ``segnale_esplicito`` (``fascicolo`` Drive della persona, ``lotto_paghe``
    bancario dello stesso giorno): dal 19/09/2026 non decide piu' se il
    pagamento viene depositato (basta il nome dipendente risolto in modo
    univoco da ``risolvi_dipendente``, decisione del titolare, vedi docstring
    del modulo) — resta solo scritto nel marcatore finale (campo ``segnale``)
    come metadato utile a distinguere un lotto paghe da un bonifico isolato."""
    if e_pagamento_non_stipendio(testo):
        return _marcatore(ESITO_NON_STIPENDIO)
    if _BENEFICIARI_DIVERSI_RE.search(testo or ""):
        dip, motivo = None, "beneficiari_diversi"
    else:
        dip, motivo = risolvi_dipendente(ctx.indici, testo)
    if dip is None and motivo == "nessuno":
        return _marcatore(ESITO_NON_DIPENDENTE)
    if hash_pdf and (hash_pdf in ctx.per_hash or hash_pdf in ctx.hash_in_coda):
        esistente = ctx.per_hash.get(hash_pdf)
        return _marcatore(ESITO_DUPLICATO, key=(esistente or {}).get("key"), motivo="hash")
    if not importo or not data:
        return _marcatore(ESITO_DATI_INCOMPLETI, dipendente_id=(dip or {}).get("id"))

    periodo = periodo_bonifico(testo, data, mese_dichiarato, anno_dichiarato)
    # Un nome/cognome risolto in modo univoco (motivo "cf"/"nome"/"cognome")
    # e' gia' un segnale sufficiente da solo (decisione del titolare,
    # 19/09/2026): non serve piu' la parola "stipendio" ne' un lotto paghe.
    # L'esclusione esplicita (TFR/fattura/commissione/...) e' gia' stata
    # applicata sopra, prima ancora di risolvere il dipendente: resta un
    # veto valido anche con un nome dipendente riconosciuto dentro.
    if dip is None or periodo is None:
        # ambiguo, oppure nessun dipendente riconosciuto: decide una
        # persona dalla coda HR.
        if dry_run:
            return _marcatore(ESITO_IN_CODA, motivo=motivo if dip is None else "periodo_sconosciuto")
        coda_id = await _metti_in_coda(
            ctx, hash_pdf=hash_pdf, data=data, importo=importo, causale=causale,
            pdf_filename=pdf_filename, pdf_data=pdf_data, fonte=origine, riferimento=riferimento,
        )
        return _marcatore(ESITO_IN_CODA, coda_id=coda_id,
                          motivo=motivo if dip is None else "periodo_sconosciuto")

    mese, anno = periodo
    esistente, come = ctx.esito_equivalente(dip["id"], importo, data, hash_pdf, key)
    nuovo = {
        "key": key, "hash": hash_pdf, "cro": cro, "dipendente_id": dip["id"],
        "data": data, "importo": importo, "causale": causale,
        "beneficiario": _nome_dipendente(dip), "mese": mese, "anno": anno,
        "origine": origine, "pdf_data": pdf_data, "ha_pdf": bool(pdf_data),
        **riferimento,
    }
    if esistente is not None:
        if dry_run:
            return _marcatore(ESITO_ARRICCHITO, key=esistente.get("key"), dipendente_id=dip["id"], motivo=come)
        campi = await _arricchisci_esito(ctx, esistente, nuovo)
        return _marcatore(ESITO_ARRICCHITO if campi else ESITO_DUPLICATO,
                          key=esistente.get("key"), dipendente_id=dip["id"], motivo=come,
                          campi=campi or None)
    if dry_run:
        return _marcatore(ESITO_DEPOSITATO, key=key, dipendente_id=dip["id"], mese=mese, anno=anno,
                          segnale=segnale_esplicito)
    await _scrivi_esito(ctx, nuovo)
    return _marcatore(ESITO_DEPOSITATO, key=key, dipendente_id=dip["id"], mese=mese, anno=anno,
                      segnale=segnale_esplicito)


# ── ingresso 1: PDF bonifico del gestionale (bonifici_transfers) ─────────────

_STATI_CICLO = {"da elaborare", "elaborate", "errori"}


def fascicolo_persona(source_path: Any) -> Optional[str]:
    """Nome della cartella-persona quando il file viene dal fascicolo Drive
    ``05_PERSONALE_E_CEDOLINI/DIPENDENTI/<PERSONA>/BONIFICI/DA ELABORARE/x.pdf``.

    Il percorso relativo salvato dall'ingest e' ``<PERSONA>/BONIFICI/DA
    ELABORARE/x.pdf``; per la radice ``03_BANCHE_E_PAGAMENTI/BONIFICI`` e' solo
    ``DA ELABORARE/x.pdf`` (nessuna persona). La cartella e' la classificazione
    esplicita del titolare: vale come identita' del dipendente E come segnale
    "e' un bonifico stipendio" anche quando il parser non legge la causale
    (es. ``AGGIUNTIVA``, ``ricevuta per ordinante``).
    """
    parti = [p.strip() for p in str(source_path or "").split("/") if p.strip()]
    for i, parte in enumerate(parti):
        if parte.casefold() == "bonifici" and i >= 1 and parti[i - 1].casefold() not in _STATI_CICLO:
            return parti[i - 1]
    return None


def _testo_transfer(transfer: Dict[str, Any]) -> str:
    beneficiario = transfer.get("beneficiario") or {}
    nome = beneficiario.get("nome") if isinstance(beneficiario, dict) else beneficiario
    persona = fascicolo_persona(transfer.get("source_path"))
    return " ".join(str(p) for p in (persona, nome, transfer.get("causale"), transfer.get("source_file")) if p)


async def _source_path_transfer(db, transfer: Dict[str, Any]) -> Optional[str]:
    """Percorso Drive del transfer; per quelli archiviati prima del 14/09/2026
    lo recupera dal documento di Import documenti che lo ha generato."""
    if transfer.get("source_path"):
        return transfer["source_path"]
    if not transfer.get("id"):
        return None
    inbox = await db["documents_inbox"].find_one(
        {"bonifico_transfer_id": transfer["id"]}, {"_id": 0, "source_path": 1}
    )
    return (inbox or {}).get("source_path") or None


async def deposita_bonifico_transfer_in_hr(db, transfer: Dict[str, Any],
                                          ctx: Optional[ContestoHR] = None,
                                          dry_run: bool = False) -> Dict[str, Any]:
    """Porta in HR un documento di ``bonifici_transfers``; ritorna il marcatore."""
    if ctx is None:
        ctx = await carica_contesto_hr()
        if ctx is None:
            return _marcatore(ESITO_HR_NON_CONFIGURATO)
    if transfer.get("fatture_associate") or transfer.get("fattura_associata"):
        marca = _marcatore(ESITO_NON_STIPENDIO, motivo="fattura_fornitore")
        await _marca(db, "bonifici_transfers", transfer.get("id"), marca, dry_run)
        return marca
    transfer = dict(transfer)
    transfer["source_path"] = await _source_path_transfer(db, transfer)
    persona = fascicolo_persona(transfer.get("source_path"))
    hash_pdf = transfer.get("document_hash")
    pdf_data = transfer.get("pdf_data")
    if pdf_data is None and transfer.get("id") and not dry_run:
        con_pdf = await db["bonifici_transfers"].find_one({"id": transfer["id"]}, {"_id": 0, "pdf_data": 1})
        pdf_data = (con_pdf or {}).get("pdf_data")
    marca = await _deposita(
        ctx,
        key=f"{PREFISSO_KEY_PDF}:{(hash_pdf or transfer.get('id') or '')[:24]}",
        testo=_testo_transfer(transfer),
        segnale_esplicito="fascicolo" if persona else None,
        data=_data_iso(transfer.get("data")),
        importo=_importo(transfer.get("importo")),
        hash_pdf=hash_pdf,
        cro=transfer.get("cro_trn") or None,
        causale=str(transfer.get("causale") or transfer.get("source_file") or ""),
        pdf_filename=transfer.get("source_file"),
        pdf_data=pdf_data,
        origine=ORIGINE_PDF,
        mese_dichiarato=transfer.get("periodo_mese") or transfer.get("mese_pagamento_file"),
        anno_dichiarato=transfer.get("periodo_anno") or transfer.get("anno_pagamento_file"),
        riferimento={"gestionale_transfer_id": transfer.get("id"),
                     "gestionale_fonte": transfer.get("source")},
        dry_run=dry_run,
    )
    if not dry_run:
        await _ricalcola_periodi(ctx)
    await _marca(db, "bonifici_transfers", transfer.get("id"), marca, dry_run)
    return marca


# ── ingresso 2: riga di estratto conto (estratto_conto_movimenti) ────────────

def movimento_candidato_stipendio(mov: Dict[str, Any]) -> bool:
    """Solo le uscite con un beneficiario "FAVORE ..." (bonifici disposti
    dall'azienda). Commissioni, accrediti, POS, addebiti diretti restano fuori."""
    tipo = str(mov.get("tipo") or "").lower()
    try:
        negativo = float(mov.get("importo") or 0) < 0
    except (TypeError, ValueError):
        negativo = False
    if tipo not in {"uscita", "addebito", "dare"} and not negativo:
        return False
    from app.services.stipendi_bonifici import estrai_nome_favore

    return bool(estrai_nome_favore(str(mov.get("descrizione") or mov.get("descrizione_originale") or "")))


def date_lotti_paghe(ctx: ContestoHR, movimenti: List[Dict[str, Any]]) -> set:
    """Giorni in cui l'azienda ha disposto bonifici ad almeno
    ``LOTTO_PAGHE_MIN_DIPENDENTI`` dipendenti diversi: un lotto paghe.

    Negli estratti conto reali di gennaio-aprile 2026 la descrizione e' solo
    "VS.DISP. RIF. ... FAVORE TAIANO LUIGI - ADD.TOT" (nessuna causale): 12
    bonifici lo stesso giorno a 12 dipendenti sono gli acconti/saldi del mese,
    non 12 decisioni da prendere a mano.
    """
    per_data: Dict[str, set] = {}
    for mov in movimenti:
        if not movimento_candidato_stipendio(mov):
            continue
        descrizione = str(mov.get("descrizione") or mov.get("descrizione_originale") or "")
        if e_pagamento_non_stipendio(descrizione) or _BENEFICIARI_DIVERSI_RE.search(descrizione):
            continue
        data = _data_iso(mov.get("data"))
        dip, _ = risolvi_dipendente(ctx.indici, descrizione)
        if data and dip:
            per_data.setdefault(data, set()).add(dip["id"])
    return {d for d, dips in per_data.items() if len(dips) >= LOTTO_PAGHE_MIN_DIPENDENTI}


async def deposita_movimento_banca_in_hr(db, mov: Dict[str, Any],
                                        ctx: Optional[ContestoHR] = None,
                                        dry_run: bool = False,
                                        segnale_esplicito: Optional[str] = None) -> Dict[str, Any]:
    """Porta in HR una riga di ``estratto_conto_movimenti``; ritorna il marcatore.

    ``segnale_esplicito="lotto_paghe"`` quando la data e' in ``date_lotti_paghe``."""
    if ctx is None:
        ctx = await carica_contesto_hr()
        if ctx is None:
            return _marcatore(ESITO_HR_NON_CONFIGURATO)
    descrizione = str(mov.get("descrizione") or mov.get("descrizione_originale") or "")
    if not movimento_candidato_stipendio(mov):
        marca = _marcatore(ESITO_NON_STIPENDIO, motivo="non_bonifico_in_uscita")
        await _marca(db, "estratto_conto_movimenti", mov.get("id"), marca, dry_run)
        return marca
    marca = await _deposita(
        ctx,
        key=f"{PREFISSO_KEY_BANCA}:{mov.get('id')}",
        testo=descrizione,
        data=_data_iso(mov.get("data")),
        importo=_importo(mov.get("importo")),
        hash_pdf=None,
        cro=_cro_da_descrizione(descrizione),
        causale=descrizione,
        pdf_filename=None,
        pdf_data=None,
        origine=ORIGINE_BANCA,
        mese_dichiarato=None,
        anno_dichiarato=None,
        riferimento={"gestionale_movimento_id": mov.get("id"),
                     "gestionale_fonte": mov.get("source") or "estratto_conto"},
        dry_run=dry_run,
        segnale_esplicito=segnale_esplicito,
    )
    if not dry_run:
        await _ricalcola_periodi(ctx)
    await _marca(db, "estratto_conto_movimenti", mov.get("id"), marca, dry_run)
    return marca


# ── giro periodico / backfill ────────────────────────────────────────────────

async def deposita_pagamenti_in_hr(db, *, dry_run: bool = False, limit: int = 2000,
                                   dettaglio_max: int = 200) -> Dict[str, Any]:
    """Riprende tutti i bonifici PDF e le righe banca senza marcatore.

    Usato dal job scheduler ``hr_pagamenti_deposito`` e dall'endpoint di
    backfill ``POST /api/prima-nota-salari/deposita-pagamenti-hr``.
    """
    ctx = await carica_contesto_hr()
    if ctx is None:
        return {"status": ESITO_HR_NON_CONFIGURATO, "dry_run": dry_run,
                "bonifici_pdf": {}, "estratto_conto": {}, "dettaglio": []}

    report: Dict[str, Any] = {"status": "ok", "dry_run": dry_run,
                              "bonifici_pdf": {}, "estratto_conto": {}, "dettaglio": []}

    def _registra(sezione: str, doc_id: Any, marca: Dict[str, Any], extra: Dict[str, Any]) -> None:
        conteggi = report[sezione]
        conteggi[marca["esito"]] = conteggi.get(marca["esito"], 0) + 1
        if len(report["dettaglio"]) < dettaglio_max and marca["esito"] in {
            ESITO_DEPOSITATO, ESITO_ARRICCHITO, ESITO_IN_CODA, ESITO_DATI_INCOMPLETI,
        }:
            report["dettaglio"].append({"sezione": sezione, "id": doc_id, **extra,
                                        **{k: v for k, v in marca.items() if k != "at"}})

    transfers = await db["bonifici_transfers"].find(
        {CAMPO_MARCATORE: {"$exists": False}}, {"_id": 0, "pdf_data": 0}
    ).to_list(limit)
    for transfer in transfers:
        try:
            marca = await deposita_bonifico_transfer_in_hr(db, transfer, ctx=ctx, dry_run=dry_run)
        except Exception as exc:  # un documento rotto non ferma il giro
            logger.warning("[HR deposito pagamenti] bonifico %s: %s", transfer.get("id"), exc)
            marca = _marcatore("errore", motivo=str(exc)[:200])
        _registra("bonifici_pdf", transfer.get("id"), marca, {
            "data": _data_iso(transfer.get("data")), "importo": _importo(transfer.get("importo")),
            "testo": _testo_transfer(transfer)[:120],
        })

    movimenti = await db["estratto_conto_movimenti"].find(
        {CAMPO_MARCATORE: {"$exists": False}}, {"_id": 0}
    ).to_list(limit)
    # Riesame: righe gia' messe in coda solo perche' senza la parola
    # "stipendio". Le righe di un lotto paghe possono arrivare in giri diversi
    # (e la regola del lotto e' nata dopo il primo giro reale del 14/09/2026):
    # se ora il giorno risulta un lotto, la riga esce dalla coda HR ed entra
    # nei pagamenti come le altre.
    riesame = await db["estratto_conto_movimenti"].find(
        {f"{CAMPO_MARCATORE}.esito": ESITO_IN_CODA,
         f"{CAMPO_MARCATORE}.motivo": "senza_segnale_stipendio"}, {"_id": 0}
    ).to_list(limit)
    lotti = date_lotti_paghe(ctx, movimenti + riesame)

    async def _deposita_movimento(mov: Dict[str, Any], sezione: str) -> None:
        try:
            segnale = "lotto_paghe" if _data_iso(mov.get("data")) in lotti else None
            marca = await deposita_movimento_banca_in_hr(db, mov, ctx=ctx, dry_run=dry_run,
                                                        segnale_esplicito=segnale)
        except Exception as exc:
            logger.warning("[HR deposito pagamenti] movimento %s: %s", mov.get("id"), exc)
            marca = _marcatore("errore", motivo=str(exc)[:200])
        _registra(sezione, mov.get("id"), marca, {
            "data": _data_iso(mov.get("data")), "importo": _importo(mov.get("importo")),
            "testo": str(mov.get("descrizione") or "")[:120],
        })

    for mov in movimenti:
        await _deposita_movimento(mov, "estratto_conto")

    report["estratto_conto_riesame"] = {}
    for mov in riesame:
        if _data_iso(mov.get("data")) not in lotti:
            continue
        if not dry_run:
            await ctx.db.bonifici_da_associare.update_one(
                {"gestionale_movimento_id": mov.get("id"), "stato": "da_associare"},
                {"$set": {"stato": "ritirato", "ritirato_il": _now_iso(),
                          "ritirato_motivo": "lotto_paghe: entrato nei pagamenti"}})
        await _deposita_movimento(mov, "estratto_conto_riesame")

    # Riesame 2: "FAVORE BENEFICIARI VARI/DIVERSI" (addebito cumulativo senza
    # nomi). Nel primo giro reale (14/09/2026) finivano "non_dipendente"
    # oppure, quando la causale libera citava una persona ("... - Vincenzo
    # ceraldi stipendi", 4.600 EUR per piu' dipendenti), attribuiti a lei.
    # Ora vanno sempre in coda: l'esito sbagliato viene tolto e il periodo
    # ricalcolato, poi la riga rientra dal percorso normale.
    cumulativi = [
        m for m in await db["estratto_conto_movimenti"].find(
            {f"{CAMPO_MARCATORE}.esito": {"$in": [ESITO_NON_DIPENDENTE, ESITO_DEPOSITATO]}}, {"_id": 0}
        ).to_list(limit)
        if _BENEFICIARI_DIVERSI_RE.search(str(m.get("descrizione") or m.get("descrizione_originale") or ""))
        and movimento_candidato_stipendio(m)
    ]
    for mov in cumulativi:
        marca_vecchia = mov.get(CAMPO_MARCATORE) or {}
        if marca_vecchia.get("esito") == ESITO_DEPOSITATO and not dry_run:
            key = marca_vecchia.get("key") or f"{PREFISSO_KEY_BANCA}:{mov.get('id')}"
            esito_errato = await ctx.db.pagamenti_esiti.find_one({"key": key}, {"_id": 0, "pdf_data": 0})
            if esito_errato:
                await ctx.db.pagamenti_esiti.delete_one({"key": key})
                ctx.per_key.pop(key, None)
                for lista in ctx.per_dipendente.values():
                    lista[:] = [e for e in lista if e.get("key") != key]
                try:
                    ctx.periodi_toccati.add((esito_errato["dipendente_id"],
                                             int(esito_errato["anno"]), int(esito_errato["mese"])))
                except (KeyError, TypeError, ValueError):
                    pass
        await _deposita_movimento(mov, "estratto_conto_riesame")

    report["letti"] = {"bonifici_pdf": len(transfers), "estratto_conto": len(movimenti),
                       "estratto_conto_riesame": len(riesame)}
    return report
