"""Relazioni documentali (DRV-03, parte minima per MINI-06): ogni entita' contabile
che ha un originale su Drive lo dichiara in ``entity_relations`` con target
``documento`` (id = ``drive_id``), relazione ``has_source_document``.

Un solo registro: la relazione usa ``upsert_entity_relation`` e la sua chiave
deterministica, quindi il secondo giro non crea nulla (criterio di collaudo
dell'idempotenza). Il giro e' **simulazione per difetto** (``dry_run``) e non
scrive mai altrove: ne' sul documento di origine, ne' sul protocollo.

Fonti, tutte gia' in archivio:

* campo ``drive_file_id`` di fatture attive, modelli F24 e quietanze;
* ``collegamento_tipo/collegamento_id`` del protocollo Drive (riga canonica
  attiva, mai una copia identica ``duplicato_di``);
* cedolini del gestionale: impronta MD5 nota (``source_file_hash`` di 32
  caratteri) uguale a quella della riga canonica del protocollo. L'MD5 qui
  serve solo a ritrovare la copia identica su Drive; un'impronta SHA-256 non
  ha ancora un corrispondente nel protocollo (DRV-02) e resta fuori.

Ambiguo non vuol dire indovinato: un'entita' con piu' file, o un file con piu'
entita' dove ne vale una sola (fattura, F24, quietanza), entra ``pending``
(= ``DA_VERIFICARE``) con il motivo. I cedolini possono condividere un file
(documento combinato): non e' ambiguita'.
"""
from __future__ import annotations

import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from app.constants.fattura_attiva import fattura_attiva
from app.db_collections import COLL_ENTITY_RELATIONS
from app.services.entity_relations import relation_key, upsert_entity_relation

logger = logging.getLogger(__name__)

TIPO_DOCUMENTO = "documento"
RELAZIONE = "has_source_document"
CHIAVE_STATO = "relazioni_documentali"
STATO_CONFERMATA = "confirmed"
STATO_DA_VERIFICARE = "pending"
STATO_REVOCATA = "revoked"
ATTORE = "relazioni_documentali"
ESEMPI_MAX = 50

MOTIVO_PIU_FILE = "entita_con_piu_file"
MOTIVO_PIU_ENTITA = "file_con_piu_entita"

# collezione del gestionale -> tipo entita' (stesso vocabolario delle relazioni gia' in archivio)
SORGENTI_CAMPO: Tuple[Tuple[str, str], ...] = (
    ("invoices", "invoice"),
    ("f24_unificato", "f24_model"),
    ("quietanze_f24", "f24_receipt"),
)
# collegamento_tipo del protocollo -> tipo entita'
TIPI_COLLEGAMENTO = {
    "invoice": "invoice",
    "f24_unificato": "f24_model",
    "quietanze_f24": "f24_receipt",
    "hr_cedolino": "hr_payslip",
    "hr_bonifico": "hr_bonifico",
}
# un file = una sola entita' (altrimenti ambiguo). Cedolini e distinte possono
# stare in un documento combinato.
TIPI_ESCLUSIVI = frozenset({"invoice", "f24_model", "f24_receipt"})
STATI_ESCLUSI = frozenset({"eliminato", "sostituito", "archived", "archiviata", "deleted"})
_MD5_RE = re.compile(r"^[0-9a-fA-F]{32}$")


@dataclass(frozen=True)
class Osservazione:
    entity_type: str
    entity_id: str
    drive_id: str
    fonte: str  # campo | protocollo | impronta
    md5: Optional[str] = None


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


def _t(valore: Any) -> str:
    return str(valore).strip() if valore is not None else ""


def _id_di(doc: Dict[str, Any]) -> str:
    # `_id` e' la chiave del runtime ERP (regola 10) e quella che il protocollo
    # scrive in `collegamento_id`; `id` e' un campo dei dati, assente su molti
    # F24 e quietanze e numerico su meta' delle fatture.
    for campo in ("_id", "id"):
        valore = _t(doc.get(campo))
        if valore:
            return valore
    return ""


# ── piano (puro) ─────────────────────────────────────────────────────────────

def pianifica(osservazioni: Iterable[Osservazione]) -> List[Prevista]:
    """Dalle osservazioni alle relazioni previste, ordinate per chiave."""
    per_coppia: Dict[Tuple[str, str, str], Prevista] = {}
    for o in osservazioni:
        if not (o.entity_type and o.entity_id and o.drive_id):
            continue
        p = per_coppia.setdefault((o.entity_type, o.entity_id, o.drive_id),
                                  Prevista(o.entity_type, o.entity_id, o.drive_id, STATO_CONFERMATA))
        if o.fonte not in p.fonti:
            p.fonti.append(o.fonte)
        p.md5 = p.md5 or o.md5

    file_di_entita: Dict[Tuple[str, str], set] = defaultdict(set)
    entita_di_file: Dict[Tuple[str, str], set] = defaultdict(set)
    for (tipo, ent, drive) in per_coppia:
        file_di_entita[(tipo, ent)].add(drive)
        entita_di_file[(tipo, drive)].add(ent)

    for (tipo, ent, drive), p in per_coppia.items():
        if len(file_di_entita[(tipo, ent)]) > 1:
            p.status, p.motivo = STATO_DA_VERIFICARE, MOTIVO_PIU_FILE
        elif tipo in TIPI_ESCLUSIVI and len(entita_di_file[(tipo, drive)]) > 1:
            p.status, p.motivo = STATO_DA_VERIFICARE, MOTIVO_PIU_ENTITA
    return sorted(per_coppia.values(), key=lambda p: p.chiave)


# ── lettura delle fonti ──────────────────────────────────────────────────────

async def _leggi(db, collezione: str, query: Dict[str, Any], proiezione: Dict[str, int]) -> List[Dict[str, Any]]:
    return await db[collezione].find(query, proiezione).to_list(length=None)


async def osservazioni_da_campi(db) -> Tuple[List[Osservazione], Dict[str, set]]:
    """`drive_file_id` scritto sul documento (proiezione senza payload) e, per
    ogni tipo, gli id delle entita' vive: servono a scartare i collegamenti del
    protocollo verso documenti che non esistono piu' o sono fuori (archiviati,
    in quarantena)."""
    trovate: List[Osservazione] = []
    vive: Dict[str, set] = {}
    for collezione, tipo in SORGENTI_CAMPO:
        righe = await _leggi(db, collezione, {}, {
            "_id": 1, "id": 1, "drive_file_id": 1, "drive_md5": 1, "status": 1, "stato_import": 1,
            "entity_status": 1, "deleted": 1})
        vive[tipo] = set()
        for doc in righe:
            if tipo == "invoice":
                if not fattura_attiva(doc):
                    continue
            elif _t(doc.get("status")).lower() in STATI_ESCLUSI or _t(doc.get("entity_status")).lower() == "deleted":
                continue
            ident = _id_di(doc)
            vive[tipo].add(ident)
            if _t(doc.get("id")):
                vive[tipo].add(_t(doc.get("id")))
            file_id = _t(doc.get("drive_file_id"))
            if file_id:
                trovate.append(Osservazione(tipo, ident, file_id, "campo", _t(doc.get("drive_md5")).lower() or None))
    return trovate, vive


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


def osservazioni_da_protocollo(righe: Sequence[Dict[str, Any]],
                               vive: Optional[Dict[str, set]] = None) -> Tuple[List[Osservazione], Dict[str, int]]:
    """Collegamenti del protocollo. Dove l'entita' e' verificabile (fatture, F24,
    quietanze) un collegamento verso un id che non e' vivo si scarta e si conta."""
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
        trovate.append(Osservazione(tipo, id_coll, _t(r.get("drive_id")), "protocollo",
                                    _t(r.get("md5")).lower() or None))
    return trovate, dict(non_mappati)


async def osservazioni_cedolini(db, righe_protocollo: Sequence[Dict[str, Any]]) -> Tuple[List[Osservazione], Dict[str, int]]:
    """Cedolino ↔ file per impronta MD5 nota. Una impronta su piu' file canonici
    e' ambigua: si emettono tutte le coppie e il piano le marca `pending`."""
    per_md5: Dict[str, List[str]] = defaultdict(list)
    for r in righe_protocollo:
        md5 = _t(r.get("md5")).lower()
        if _MD5_RE.match(md5) and _t(r.get("drive_id")):
            per_md5[md5].append(_t(r["drive_id"]))
    conteggi = {"cedolini_con_md5": 0, "cedolini_md5_senza_file": 0, "cedolini_sha256_non_collegabili": 0}
    trovate: List[Osservazione] = []
    righe = await _leggi(db, "cedolini", {"source_file_hash": {"$nin": [None, ""]}}, {
        "_id": 1, "id": 1, "source_file_hash": 1, "status": 1, "entity_status": 1})
    for doc in righe:
        if _t(doc.get("status")).lower() in STATI_ESCLUSI:
            continue
        impronta = _t(doc.get("source_file_hash")).lower()
        if len(impronta) == 64:
            conteggi["cedolini_sha256_non_collegabili"] += 1
            continue
        if not _MD5_RE.match(impronta):
            continue
        conteggi["cedolini_con_md5"] += 1
        file_ids = per_md5.get(impronta)
        if not file_ids:
            conteggi["cedolini_md5_senza_file"] += 1
            continue
        for drive_id in file_ids:
            trovate.append(Osservazione("payslip", _id_di(doc), drive_id, "impronta", impronta))
    return trovate, conteggi


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


async def calcola(db, *, protocollo: Optional[Sequence[Dict[str, Any]]] = None,
                  leggi_prot: Optional[Callable[[], Awaitable[Optional[List[Dict[str, Any]]]]]] = None) -> Dict[str, Any]:
    """Piano completo e confronto con l'archivio. Sola lettura."""
    if protocollo is None:
        try:
            protocollo = await (leggi_prot or leggi_protocollo)()
        except Exception as exc:  # noqa: BLE001 - il protocollo non raggiungibile si dichiara
            logger.warning("Protocollo Drive non letto per le relazioni documentali: %s: %s",
                           type(exc).__name__, exc)
            protocollo = None
    osservazioni, vive = await osservazioni_da_campi(db)
    non_mappati: Dict[str, int] = {}
    conteggi_ced: Dict[str, int] = {}
    if protocollo is not None:
        da_prot, non_mappati = osservazioni_da_protocollo(protocollo, vive)
        osservazioni += da_prot
        da_ced, conteggi_ced = await osservazioni_cedolini(db, protocollo)
        osservazioni += da_ced
    piano = pianifica(osservazioni)
    esistenti = await _relazioni_esistenti(db)

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
    return {
        "piano": piano, "nuove": nuove, "da_aggiornare": da_aggiornare,
        "riepilogo": {
            "protocollo": "letto" if protocollo is not None else "non_disponibile",
            "previste": len(piano),
            "nuove": len(nuove),
            "aggiornate": len(da_aggiornare),
            "gia_presenti": gia,
            "revocate_rispettate": revocate,
            "non_piu_dedotte": sum(1 for k in esistenti if k not in previste),
            "da_verificare": sum(1 for p in piano if p.status == STATO_DA_VERIFICARE),
            "per_tipo": _conta(piano),
            "collegamenti_non_mappati": non_mappati,
            **conteggi_ced,
        },
    }


def _esempio(p: Prevista) -> Dict[str, Any]:
    return {"entity_type": p.entity_type, "entity_id": p.entity_id, "drive_id": p.drive_id,
            "status": p.status, "motivo": p.motivo, "fonti": sorted(p.fonti)}


def _regola(p: Prevista) -> str:
    if "campo" in p.fonti:
        return "drive_file_id"
    if "protocollo" in p.fonti:
        return "collegamento_protocollo"
    return "impronta_md5"


async def esegui(db, *, dry_run: bool = True, protocollo: Optional[Sequence[Dict[str, Any]]] = None,
                 leggi_prot: Optional[Callable[[], Awaitable[Optional[List[Dict[str, Any]]]]]] = None) -> Dict[str, Any]:
    """Backfill. ``dry_run`` (difetto) non scrive; altrimenti crea solo le mancanti
    e allinea lo stato di quelle esistenti (mai una revocata)."""
    esito = await calcola(db, protocollo=protocollo, leggi_prot=leggi_prot)
    scritte = 0
    if not dry_run:
        for p in esito["nuove"] + esito["da_aggiornare"]:
            await upsert_entity_relation(
                db, source_type=p.entity_type, source_id=p.entity_id, relation_type=RELAZIONE,
                target_type=TIPO_DOCUMENTO, target_id=p.drive_id, status=p.status,
                rule=_regola(p), evidence=_evidenze(p),
                provenance={"fonti": sorted(p.fonti), "motivo": p.motivo,
                            "verifica": "DA_VERIFICARE" if p.status == STATO_DA_VERIFICARE else "CERTO"},
                actor=ATTORE)
            scritte += 1
    return {
        "dry_run": dry_run, **esito["riepilogo"], "scritte": scritte,
        "ambigue": [_esempio(p) for p in esito["piano"] if p.status == STATO_DA_VERIFICARE][:ESEMPI_MAX],
        "esempi_nuove": [_esempio(p) for p in esito["nuove"][:10]],
    }


__all__ = ["Osservazione", "Prevista", "pianifica", "calcola", "esegui", "leggi_protocollo",
           "TIPO_DOCUMENTO", "RELAZIONE", "CHIAVE_STATO"]
