"""Relazioni documentali (DRV-03): ogni entita' che ha un originale su Drive lo dichiara
in ``entity_relations`` con target ``documento`` (id = ``drive_id``), relazione
``has_source_document``.

Un solo registro: la relazione usa ``upsert_entity_relation`` e la sua chiave
deterministica, quindi il secondo giro non crea nulla (criterio di collaudo
dell'idempotenza). Il giro e' **simulazione per difetto** (``dry_run``). Scrive solo
in ``entity_relations`` e, con ``dry_run=False``, il ``drive_file_id`` sul cedolino
(mai sovrascritto, mai dove l'originale non e' univoco).

Fonti, tutte gia' in archivio e lette una volta sola (un prefetch, regola 4):

* campo ``drive_file_id`` del documento (fatture attive, modelli F24, quietanze,
  inbox, cartelle, importazioni di estratti conto);
* ``collegamento_tipo/collegamento_id`` del protocollo Drive (riga canonica
  attiva, mai una copia identica ``duplicato_di``), verso entita' vive: gli id
  HR si verificano nell'archivio HR (chiave ``id`` testo);
* **impronta del file** dove il documento non ha ``drive_file_id``: SHA-256 col
  registro della cartella unica (``registro_originali``, copia in ``ELABORATE``),
  MD5 col protocollo (solo per ritrovare la copia identica su Drive). Mai nome o
  importo;
* **occorrenze** (``source_occurrences``): le copie dello stesso contenuto che il
  motore ha visto arrivare. Sono provenienza dichiarata dal motore, non
  ambiguita': una busta o una quietanza puo' avere piu' file, e un file puo'
  contenere piu' buste (documento combinato).

Ambiguo non vuol dire indovinato: un'entita' con piu' file non attestati, un file
con piu' fatture/F24/quietanze, o un'impronta che dopo il registro resta su piu'
file identici senza un solo creatore, entra ``pending`` (= ``DA_VERIFICARE``)
con il motivo.
"""
from __future__ import annotations

import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from app.constants.fattura_attiva import fattura_attiva
from app.db_collections import COLL_ENTITY_RELATIONS
from app.services.entity_relations import relation_key, upsert_entity_relation
from app.services.registro_originali import Originale, RegistroOriginali, leggi_registro, sha256_valido

logger = logging.getLogger(__name__)

TIPO_DOCUMENTO = "documento"
RELAZIONE = "has_source_document"
CHIAVE_STATO = "relazioni_documentali"
STATO_CONFERMATA = "confirmed"
STATO_DA_VERIFICARE = "pending"
STATO_REVOCATA = "revoked"
ATTORE = "relazioni_documentali"
ESEMPI_MAX = 50
LIMITE_SCRITTURE = 2000

MOTIVO_PIU_FILE = "entita_con_piu_file"
MOTIVO_PIU_ENTITA = "file_con_piu_entita"
MOTIVO_COPIE_IDENTICHE = "impronta_su_piu_file_identici"

FONTE_CAMPO = "campo"
FONTE_PROTOCOLLO = "protocollo"
FONTE_IMPRONTA = "impronta"               # MD5 del file, protocollo Drive
FONTE_IMPRONTA_SHA256 = "impronta_sha256"  # SHA-256 del file, registro della cartella unica
FONTE_OCCORRENZA = "occorrenza"
# Le fonti che dicono «questo e' il file del documento» (non una copia attestata).
FONTI_PRIMARIE = frozenset({FONTE_CAMPO, FONTE_IMPRONTA, FONTE_IMPRONTA_SHA256})

_MD5_RE = re.compile(r"^[0-9a-fA-F]{32}$")
_BLOB_SHA_RE = re.compile(r"([0-9a-f]{64})$")


@dataclass(frozen=True)
class Sorgente:
    """Una collezione che puo' avere un originale su Drive."""
    collezione: str
    tipo: str
    campi_impronta: Tuple[str, ...] = ()
    occorrenze: bool = False
    id_preferito: str = "_id"


# Il tipo e' lo stesso vocabolario delle relazioni gia' in archivio (`invoice`,
# `f24_model`, `f24_receipt`, `payslip`, `bonifico_pdf`); gli altri sono nuovi e
# distinti per collezione, cosi' due archivi con lo stesso id non si confondono.
SORGENTI: Tuple[Sorgente, ...] = (
    Sorgente("invoices", "invoice"),
    Sorgente("f24_unificato", "f24_model", ("pdf_hash",), True),
    Sorgente("quietanze_f24", "f24_receipt", ("pdf_hash",), True),
    Sorgente("cedolini", "payslip", ("source_file_hash",), True, id_preferito="id"),
    Sorgente("documents_inbox", "inbox_document", ("sha256", "file_hash")),
    Sorgente("bonifici_transfers", "bonifico_pdf", ("document_hash",)),
    Sorgente("ricevute_pagopa", "pagopa_receipt", ("pdf_hash",)),
    Sorgente("cartelle_pagamento", "cartella_pagamento", ("sha256",)),
    Sorgente("estratti_conto_originali", "estratto_conto_originale", ("blob_key",)),
    Sorgente("estratto_conto_nexi", "estratto_conto_nexi", ("content_sha256",)),
    Sorgente("paypal_statements", "estratto_conto_paypal", ("source_sha256",)),
    Sorgente("sumup_conto_estratti", "estratto_conto_sumup", ("content_sha256",)),
    Sorgente("mutui_estratti_annuali", "estratto_mutuo", ("sha256",)),
    Sorgente("drive_estratti_conto_imports", "estratto_conto_import"),
)
# tipi di cui il protocollo puo' dire «questo file e' di quell'entita'» e di cui
# conosciamo gli id vivi nel gestionale
SORGENTI_CAMPO: Tuple[Tuple[str, str], ...] = tuple(
    (s.collezione, s.tipo) for s in SORGENTI if s.tipo in ("invoice", "f24_model", "f24_receipt"))
# collegamento_tipo del protocollo -> tipo entita'
TIPI_COLLEGAMENTO = {
    "invoice": "invoice",
    "f24_unificato": "f24_model",
    "quietanze_f24": "f24_receipt",
    "hr_cedolino": "hr_payslip",
    "hr_bonifico": "hr_bonifico",
}
TIPI_HR = frozenset({"hr_payslip", "hr_bonifico"})
# un file = una sola entita' (altrimenti ambiguo). Cedolini, distinte, ricevute e
# estratti possono stare in un documento combinato.
TIPI_ESCLUSIVI = frozenset({"invoice", "f24_model", "f24_receipt"})
# Entita' che hanno per natura piu' file (le copie arrivate da canali diversi):
# la busta e' nella copia singola e nei PDF combinati del mese.
TIPI_MULTI_FILE = frozenset({"payslip", "hr_payslip"})
STATI_ESCLUSI = frozenset({"eliminato", "sostituito", "archived", "archiviata", "deleted"})


@dataclass(frozen=True)
class Osservazione:
    entity_type: str
    entity_id: str
    drive_id: str
    fonte: str  # campo | protocollo | impronta | impronta_sha256 | occorrenza
    md5: Optional[str] = None
    incerta: bool = False  # l'impronta e' su piu' file identici senza un solo creatore


@dataclass
class Prevista:
    entity_type: str
    entity_id: str
    drive_id: str
    status: str
    motivo: Optional[str] = None
    fonti: List[str] = field(default_factory=list)
    md5: Optional[str] = None

    @property
    def chiave(self) -> str:
        return relation_key(self.entity_type, self.entity_id, RELAZIONE, TIPO_DOCUMENTO, self.drive_id)

    @property
    def primaria(self) -> bool:
        """Il file del documento (campo, impronta propria), non una copia attestata."""
        return bool(FONTI_PRIMARIE & set(self.fonti)) and self.status == STATO_CONFERMATA


def _t(valore: Any) -> str:
    return str(valore).strip() if valore is not None else ""


def _id_di(doc: Dict[str, Any], preferito: str = "_id") -> str:
    # `_id` e' la chiave del runtime ERP (regola 10) e quella che il protocollo
    # scrive in `collegamento_id`; `id` e' un campo dei dati, assente su molti
    # F24 e quietanze e numerico su meta' delle fatture. I cedolini hanno solo `id`.
    for campo in (preferito, "id" if preferito == "_id" else "_id"):
        valore = _t(doc.get(campo))
        if valore:
            return valore
    return ""


# ── piano (puro) ─────────────────────────────────────────────────────────────

def pianifica(osservazioni: Iterable[Osservazione]) -> List[Prevista]:
    """Dalle osservazioni alle relazioni previste, ordinate per chiave."""
    per_coppia: Dict[Tuple[str, str, str], Prevista] = {}
    certe: Dict[Tuple[str, str, str], bool] = {}
    for o in osservazioni:
        if not (o.entity_type and o.entity_id and o.drive_id):
            continue
        chiave = (o.entity_type, o.entity_id, o.drive_id)
        p = per_coppia.setdefault(chiave, Prevista(o.entity_type, o.entity_id, o.drive_id, STATO_CONFERMATA))
        if o.fonte not in p.fonti:
            p.fonti.append(o.fonte)
        p.md5 = p.md5 or o.md5
        if not o.incerta:
            certe[chiave] = True

    def _copia_attestata(p: Prevista) -> bool:
        return FONTE_OCCORRENZA in p.fonti and not (FONTI_PRIMARIE & set(p.fonti))

    file_di_entita: Dict[Tuple[str, str], set] = defaultdict(set)
    entita_di_file: Dict[Tuple[str, str], set] = defaultdict(set)
    for (tipo, ent, drive), p in per_coppia.items():
        entita_di_file[(tipo, drive)].add(ent)
        if tipo not in TIPI_MULTI_FILE and not _copia_attestata(p):
            file_di_entita[(tipo, ent)].add(drive)

    for chiave, p in per_coppia.items():
        tipo, ent, drive = chiave
        if not certe.get(chiave):
            p.status, p.motivo = STATO_DA_VERIFICARE, MOTIVO_COPIE_IDENTICHE
        elif len(file_di_entita[(tipo, ent)]) > 1 and not _copia_attestata(p):
            p.status, p.motivo = STATO_DA_VERIFICARE, MOTIVO_PIU_FILE
        elif tipo in TIPI_ESCLUSIVI and len(entita_di_file[(tipo, drive)]) > 1:
            p.status, p.motivo = STATO_DA_VERIFICARE, MOTIVO_PIU_ENTITA
    return sorted(per_coppia.values(), key=lambda p: p.chiave)


# ── lettura delle fonti ──────────────────────────────────────────────────────

async def _leggi(db, collezione: str, query: Dict[str, Any], proiezione: Dict[str, int]) -> List[Dict[str, Any]]:
    return await db[collezione].find(query, proiezione).to_list(length=None)


class Risolutore:
    """Da un'impronta al file su Drive: SHA-256 col registro della cartella unica,
    MD5 col protocollo. Un'impronta che il registro o il protocollo non conoscono
    non da' niente (mai un nome, mai un importo)."""

    def __init__(self, registro: Optional[RegistroOriginali] = None,
                 protocollo: Optional[Sequence[Dict[str, Any]]] = None):
        self.registro = registro or RegistroOriginali()
        self.protocollo_letto = protocollo is not None
        self._per_md5: Dict[str, List[str]] = defaultdict(list)
        for r in protocollo or ():
            md5, drive_id = _t(r.get("md5")).lower(), _t(r.get("drive_id"))
            if _MD5_RE.match(md5) and drive_id and drive_id not in self._per_md5[md5]:
                self._per_md5[md5].append(drive_id)

    def trova(self, impronta: Any) -> Optional[Originale]:
        h = _t(impronta).lower()
        if len(h) == 64:
            return self.registro.trova(h)
        if _MD5_RE.match(h):
            ids = self._per_md5.get(h)
            if not ids:
                return None
            if len(ids) == 1:
                return Originale(ids[0], tuple(ids), True)
            return Originale(None, tuple(sorted(ids)), False)
        return None


def _impronta_propria(doc: Dict[str, Any], campi: Tuple[str, ...]) -> Optional[str]:
    for campo in campi:
        valore = _t(doc.get(campo)).lower()
        if campo == "blob_key":
            trovato = _BLOB_SHA_RE.search(valore)
            valore = trovato.group(1) if trovato else ""
        if _MD5_RE.match(valore) or sha256_valido(valore):
            return valore
    return None


def _osserva(out: List[Osservazione], tipo: str, ident: str, ris: Originale, fonte: str,
             impronta: str, contatori: Dict[str, int]) -> None:
    md5 = impronta if len(impronta) == 32 else None
    if ris.drive_id and ris.certo:
        out.append(Osservazione(tipo, ident, ris.drive_id, fonte, md5))
        return
    contatori["impronte_su_piu_file_identici"] += 1
    for drive_id in ris.candidati:
        out.append(Osservazione(tipo, ident, drive_id, fonte, md5, incerta=True))


def entita_viva(s: Sorgente, doc: Dict[str, Any]) -> bool:
    """Fuori le fatture non attive e i documenti archiviati, eliminati o in quarantena."""
    if s.tipo == "invoice":
        return fattura_attiva(doc)
    return not (_t(doc.get("status")).lower() in STATI_ESCLUSI or _t(doc.get("entity_status")).lower() == "deleted")


def _proiezione(s: Sorgente) -> Dict[str, int]:
    campi = ["_id", "id", "drive_file_id", "drive_md5", "status", "stato_import", "entity_status", "deleted",
             *s.campi_impronta]
    if s.occorrenze:
        campi.append("source_occurrences")
    return {c: 1 for c in campi}


async def osservazioni_da_archivio(db, risolutore: Optional[Risolutore] = None) -> Tuple[
        List[Osservazione], Dict[str, set], Dict[str, Any]]:
    """Campo ``drive_file_id``, impronta propria e occorrenze di ogni sorgente.

    Dove il documento ha ``drive_file_id`` vale quello e basta (l'impronta non lo
    contraddice, non lo affianca). Restituisce anche, per i tipi che il protocollo
    puo' collegare, gli id delle entita' vive: servono a scartare i collegamenti verso
    documenti che non esistono piu' o sono fuori (archiviati, in quarantena)."""
    risolutore = risolutore or Risolutore()
    trovate: List[Osservazione] = []
    vive: Dict[str, set] = {}
    conteggi: Dict[str, Any] = defaultdict(int)
    per_sorgente: Dict[str, Dict[str, int]] = {}
    for s in SORGENTI:
        righe = await _leggi(db, s.collezione, {}, _proiezione(s))
        stat = per_sorgente.setdefault(s.tipo, defaultdict(int))
        conserva_vive = (s.collezione, s.tipo) in SORGENTI_CAMPO
        if conserva_vive:
            vive[s.tipo] = set()
        for doc in righe:
            if not entita_viva(s, doc):
                continue
            ident = _id_di(doc, s.id_preferito)
            if not ident:
                continue
            stat["righe"] += 1
            if conserva_vive:
                vive[s.tipo].add(ident)
                if _t(doc.get("id")):
                    vive[s.tipo].add(_t(doc.get("id")))
            file_id = _t(doc.get("drive_file_id"))
            if file_id:
                trovate.append(Osservazione(s.tipo, ident, file_id, FONTE_CAMPO,
                                            _t(doc.get("drive_md5")).lower() or None))
                stat["con_drive_file_id"] += 1
            else:
                impronta = _impronta_propria(doc, s.campi_impronta)
                if impronta:
                    stat["con_impronta"] += 1
                    ris = risolutore.trova(impronta)
                    if ris is None:
                        stat["impronta_senza_file"] += 1
                    else:
                        fonte = FONTE_IMPRONTA_SHA256 if len(impronta) == 64 else FONTE_IMPRONTA
                        _osserva(trovate, s.tipo, ident, ris, fonte, impronta, conteggi)
                        stat["con_file"] += 1
            if s.occorrenze:
                occorrenze = doc.get("source_occurrences")
                visti: Set[str] = set()
                for occ in occorrenze if isinstance(occorrenze, list) else []:
                    if not isinstance(occ, dict):
                        continue
                    stat["occorrenze"] += 1
                    h = _t(occ.get("source_file_hash") or occ.get("md5")).lower()
                    if not h or h in visti:
                        continue
                    visti.add(h)
                    ris = risolutore.trova(h)
                    if ris is None:
                        stat["occorrenze_senza_file"] += 1
                    else:
                        _osserva(trovate, s.tipo, ident, ris, FONTE_OCCORRENZA, h, conteggi)
    conteggi["per_sorgente"] = {t: dict(v) for t, v in sorted(per_sorgente.items())}
    return trovate, vive, dict(conteggi)


async def osservazioni_da_campi(db) -> Tuple[List[Osservazione], Dict[str, set]]:
    """Compatibilita': solo i campi ``drive_file_id`` e gli id vivi, senza impronte."""
    trovate, vive, _ = await osservazioni_da_archivio(db, None)
    return [o for o in trovate if o.fonte == FONTE_CAMPO], vive


async def leggi_protocollo() -> Optional[List[Dict[str, Any]]]:
    """Righe canoniche attive del protocollo Drive (sola lettura), ``None`` se
    la connessione non e' configurata: mai un elenco vuoto al posto di «non lo so»."""
    from app.services import postgres_diretto

    dsn = postgres_diretto.dsn()
    if not dsn:
        return None
    conn = await postgres_diretto.connetti(dsn)
    try:
        righe = await conn.fetch(
            "select drive_id, md5, collegamento_tipo, collegamento_id from gestionale.protocollo_drive "
            "where stato = 'attivo' and duplicato_di is null")
        return [dict(r) for r in righe]
    finally:
        await conn.close()


async def leggi_id_hr() -> Optional[Dict[str, Set[str]]]:
    """Gli ``id`` (testo, UUID) delle buste e dei bonifici nell'archivio HR, per verificare
    i collegamenti del protocollo. ``None`` se l'HR non e' raggiungibile."""
    from app.services import hr_cedolini_deposito as deposito

    dsn = deposito.dsn_hr()
    if not dsn:
        return None
    con = await deposito.connetti_hr(dsn)
    try:
        schema = deposito.TABELLA_CEDOLINI.rsplit(".", 1)[0]
        return {
            "hr_payslip": {r["id"] for r in await con.fetch(f"select id from {deposito.TABELLA_CEDOLINI}")},
            "hr_bonifico": {r["id"] for r in await con.fetch(f'select id from {schema}."app_bonifici"')},
        }
    finally:
        await con.close()


def osservazioni_da_protocollo(righe: Sequence[Dict[str, Any]],
                               vive: Optional[Dict[str, set]] = None) -> Tuple[List[Osservazione], Dict[str, int]]:
    """Collegamenti del protocollo. Dove l'entita' e' verificabile (fatture, F24,
    quietanze, buste e bonifici HR) un collegamento verso un id che non e' vivo si
    scarta e si conta."""
    trovate: List[Osservazione] = []
    non_mappati: Dict[str, int] = defaultdict(int)
    for r in righe:
        tipo_coll, id_coll = _t(r.get("collegamento_tipo")), _t(r.get("collegamento_id"))
        if not tipo_coll or not id_coll:
            continue
        tipo = TIPI_COLLEGAMENTO.get(tipo_coll)
        if not tipo:
            non_mappati[tipo_coll] += 1
            continue
        if vive is not None and tipo in vive and id_coll not in vive[tipo]:
            non_mappati[f"{tipo_coll}:entita_assente"] += 1
            continue
        trovate.append(Osservazione(tipo, id_coll, _t(r.get("drive_id")), FONTE_PROTOCOLLO,
                                    _t(r.get("md5")).lower() or None))
    return trovate, dict(non_mappati)


# ── esecuzione ───────────────────────────────────────────────────────────────

async def _relazioni_esistenti(db) -> Dict[str, str]:
    righe = await db[COLL_ENTITY_RELATIONS].find(
        {"target.type": TIPO_DOCUMENTO, "relation_type": RELAZIONE},
        {"_id": 0, "relation_key": 1, "status": 1}).to_list(length=None)
    return {r["relation_key"]: _t(r.get("status")) for r in righe if r.get("relation_key")}


def _evidenze(p: Prevista) -> List[Dict[str, Any]]:
    prove = [{"type": "drive_file_id", "value": p.drive_id}]
    if p.md5:
        prove.append({"type": "md5", "value": p.md5})
    return prove


def _conta(piano: Sequence[Prevista]) -> Dict[str, Dict[str, int]]:
    out: Dict[str, Dict[str, int]] = {}
    for p in piano:
        voce = out.setdefault(p.entity_type, {STATO_CONFERMATA: 0, STATO_DA_VERIFICARE: 0})
        voce[p.status] += 1
    return dict(sorted(out.items()))


def decidi_drive_file_id_cedolini(piano: Sequence[Prevista]) -> Tuple[Dict[str, str], Dict[str, int]]:
    """Il ``drive_file_id`` da scrivere sul cedolino: ``{id_cedolino: drive_id}``.

    Solo se il file e' **uno solo e certo**: quello che l'impronta propria del
    cedolino (o un ``drive_file_id`` gia' scritto) indica, oppure l'unico file in cui
    la busta compare. Piu' file senza un'impronta propria: ``DA_VERIFICARE``, non si
    scrive (le copie restano come relazioni, e' l'originale che non e' deciso)."""
    per_busta: Dict[str, List[Prevista]] = defaultdict(list)
    for p in piano:
        if p.entity_type == "payslip":
            per_busta[p.entity_id].append(p)
    da_scrivere: Dict[str, str] = {}
    conteggi = {"cedolini_con_file": len(per_busta), "drive_file_id_gia_scritto": 0,
                "drive_file_id_da_scrivere": 0, "drive_file_id_da_verificare": 0}
    for ident, voci in per_busta.items():
        certe = [v for v in voci if v.status == STATO_CONFERMATA]
        primari = {v.drive_id for v in certe if v.primaria}
        if any(FONTE_CAMPO in v.fonti for v in certe):
            conteggi["drive_file_id_gia_scritto"] += 1
            continue
        if len(primari) == 1:
            da_scrivere[ident] = next(iter(primari))
        elif not primari and len(voci) == 1 and len(certe) == 1:
            da_scrivere[ident] = certe[0].drive_id
        else:
            conteggi["drive_file_id_da_verificare"] += 1
    conteggi["drive_file_id_da_scrivere"] = len(da_scrivere)
    return da_scrivere, conteggi


async def calcola(db, *, protocollo: Optional[Sequence[Dict[str, Any]]] = None,
                  leggi_prot: Optional[Callable[[], Awaitable[Optional[List[Dict[str, Any]]]]]] = None,
                  leggi_hr: Optional[Callable[[], Awaitable[Optional[Dict[str, Set[str]]]]]] = None) -> Dict[str, Any]:
    """Piano completo e confronto con l'archivio. Sola lettura."""
    if protocollo is None:
        try:
            protocollo = await (leggi_prot or leggi_protocollo)()
        except Exception as exc:  # noqa: BLE001 - il protocollo non raggiungibile si dichiara
            logger.warning("Protocollo Drive non letto per le relazioni documentali: %s: %s",
                           type(exc).__name__, exc)
            protocollo = None
    hr_ids: Optional[Dict[str, Set[str]]] = None
    if leggi_hr is not None:
        try:
            hr_ids = await leggi_hr()
        except Exception as exc:  # noqa: BLE001 - l'HR e' a valle: si dichiara, non si azzera
            logger.warning("Archivio HR non letto per le relazioni documentali: %s: %s", type(exc).__name__, exc)
    try:
        registro = await leggi_registro(db)
    except Exception as exc:  # noqa: BLE001 - senza registro niente impronta SHA-256, si dichiara
        logger.warning("Registro della cartella unica non letto: %s: %s", type(exc).__name__, exc)
        registro = None
    risolutore = Risolutore(registro, protocollo)
    osservazioni, vive, conteggi_fonti = await osservazioni_da_archivio(db, risolutore)
    vive.update(hr_ids or {})
    non_mappati: Dict[str, int] = {}
    if protocollo is not None:
        da_prot, non_mappati = osservazioni_da_protocollo(protocollo, vive)
        osservazioni += da_prot
    piano = pianifica(osservazioni)
    esistenti = await _relazioni_esistenti(db)
    da_scrivere_cedolini, conteggi_ced = decidi_drive_file_id_cedolini(piano)

    nuove: List[Prevista] = []
    da_aggiornare: List[Prevista] = []
    gia = 0
    revocate = 0
    for p in piano:
        vecchio = esistenti.get(p.chiave)
        if vecchio is None:
            nuove.append(p)
        elif vecchio == STATO_REVOCATA:
            revocate += 1  # una relazione ritirata non rinasce da sola
        elif vecchio != p.status:
            da_aggiornare.append(p)
        else:
            gia += 1
    previste = {p.chiave for p in piano}
    per_sorgente = conteggi_fonti.pop("per_sorgente", {})
    riepilogo = {
        "protocollo": "letto" if protocollo is not None else "non_disponibile",
        "hr": "verificato" if hr_ids is not None else ("non_verificato" if leggi_hr is not None else "non_richiesto"),
        "registro_cartella_unica": len(registro) if registro is not None else "non_disponibile",
        "previste": len(piano),
        "nuove": len(nuove),
        "aggiornate": len(da_aggiornare),
        "gia_presenti": gia,
        "revocate_rispettate": revocate,
        "non_piu_dedotte": sum(1 for k in esistenti if k not in previste),
        "da_verificare": sum(1 for p in piano if p.status == STATO_DA_VERIFICARE),
        "per_tipo": _conta(piano),
        "per_fonte_dati": per_sorgente,
        "collegamenti_non_mappati": non_mappati,
        **conteggi_fonti,
        **conteggi_ced,
    }
    if protocollo is None:
        # senza protocollo l'impronta MD5 non si risolve: lo si dichiara, non si conta zero
        riepilogo["impronte_md5"] = "protocollo_non_disponibile"
    return {"piano": piano, "nuove": nuove, "da_aggiornare": da_aggiornare,
            "cedolini_da_scrivere": da_scrivere_cedolini, "riepilogo": riepilogo}


def _esempio(p: Prevista) -> Dict[str, Any]:
    return {"entity_type": p.entity_type, "entity_id": p.entity_id, "drive_id": p.drive_id,
            "status": p.status, "motivo": p.motivo, "fonti": sorted(p.fonti)}


def _regola(p: Prevista) -> str:
    if FONTE_CAMPO in p.fonti:
        return "drive_file_id"
    if FONTE_IMPRONTA_SHA256 in p.fonti:
        return "impronta_sha256"
    if FONTE_IMPRONTA in p.fonti:
        return "impronta_md5"
    if FONTE_OCCORRENZA in p.fonti:
        return "occorrenza"
    return "collegamento_protocollo"


async def esegui(db, *, dry_run: bool = True, protocollo: Optional[Sequence[Dict[str, Any]]] = None,
                 leggi_prot: Optional[Callable[[], Awaitable[Optional[List[Dict[str, Any]]]]]] = None,
                 leggi_hr: Optional[Callable[[], Awaitable[Optional[Dict[str, Set[str]]]]]] = None,
                 limite: int = LIMITE_SCRITTURE) -> Dict[str, Any]:
    """Backfill. ``dry_run`` (difetto) non scrive; altrimenti crea le relazioni mancanti,
    allinea lo stato di quelle esistenti (mai una revocata) e scrive il ``drive_file_id``
    dei cedolini che non lo hanno. ``limite`` = scritture per giro (relazioni e cedolini
    ciascuno): si ripete finche' ``restanti`` e' 0, ogni giro riprende da dove manca."""
    esito = await calcola(db, protocollo=protocollo, leggi_prot=leggi_prot, leggi_hr=leggi_hr)
    scritte = scritti_ced = 0
    daf = esito["cedolini_da_scrivere"]
    if not dry_run:
        for p in (esito["nuove"] + esito["da_aggiornare"])[:max(0, int(limite))]:
            await upsert_entity_relation(
                db, source_type=p.entity_type, source_id=p.entity_id, relation_type=RELAZIONE,
                target_type=TIPO_DOCUMENTO, target_id=p.drive_id, status=p.status,
                rule=_regola(p), evidence=_evidenze(p),
                provenance={"fonti": sorted(p.fonti), "motivo": p.motivo,
                            "verifica": "DA_VERIFICARE" if p.status == STATO_DA_VERIFICARE else "CERTO"},
                actor=ATTORE)
            scritte += 1
        for ident, drive_id in list(sorted(daf.items()))[:max(0, int(limite))]:
            # solo dove manca: la prima scrittura fissa l'originale (mai sovrascritta)
            await db["cedolini"].update_one({"id": ident}, {"$set": {"drive_file_id": drive_id}})
            scritti_ced += 1
    da_fare = len(esito["nuove"]) + len(esito["da_aggiornare"]) + len(daf)
    return {
        "dry_run": dry_run, **esito["riepilogo"], "scritte": scritte, "cedolini_scritti": scritti_ced,
        "restanti": da_fare - scritte - scritti_ced,
        "ambigue": [_esempio(p) for p in esito["piano"] if p.status == STATO_DA_VERIFICARE][:ESEMPI_MAX],
        "esempi_nuove": [_esempio(p) for p in esito["nuove"][:10]],
    }


__all__ = ["Osservazione", "Prevista", "pianifica", "calcola", "esegui", "leggi_protocollo", "leggi_id_hr",
           "decidi_drive_file_id_cedolini", "TIPO_DOCUMENTO", "RELAZIONE", "CHIAVE_STATO"]
