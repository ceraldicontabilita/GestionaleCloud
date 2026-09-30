"""Registro unico F24 ↔ quietanze ↔ banca ↔ cedolini HR (PR 11 + PR 12).

Il commercialista che riceve un avviso bonario ha in mano tre dati per riga:
codice tributo, periodo, importo. Qui li si incrocia con TUTTO cio' che
l'archivio possiede su quel tributo, in una sola lettura:

* righe tributo dei modelli ``f24_unificato`` (``sezione_erario`` /
  ``sezione_regioni`` / ``sezione_tributi_locali`` / ``sezione_inps`` /
  ``sezione_inail``): stesso codice + stesso periodo, importo al centesimo;
* quietanze reali: ``fiscal_documents`` con ``category = quietanza_f24``
  (indice Drive: data e protocollo nel nome file) piu' l'eventuale
  collezione storica ``quietanze_f24`` alimentata dall'import email;
* addebiti bancari ``I24 AGENZIA ENTRATE`` / F24 in
  ``estratto_conto_movimenti``: agganciati al modello, oppure compatibili
  (finestra scadenza −3/+40 giorni, importo esatto) ma non ancora agganciati;
* ritenute/contributi dei cedolini HR del periodo (``app_cedolini``) per i
  tributi da sostituto d'imposta.

Regole cardine rispettate: F24, riga tributo, quietanza e movimento bancario
restano entita' distinte; nessuna associazione per solo importo (sempre data
±3 giorni + importo esatto, oppure protocollo); i casi ambigui restano
proposte; la quietanza documenta il versamento ma non sostituisce la prova
bancaria (``stato_evidenza_pagamento``). Le funzioni ``controlla_*`` e
``verifica_codice`` non scrivono mai; ``riconcilia_f24_banca`` (l'unico motore
F24 ↔ banca, a livelli) scrive solo i riscontri CERTI ed e' idempotente.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional, Set, Tuple

from app.db_collections import (
    COLL_ESTRATTO_CONTO, COLL_F24, COLL_FISCAL_DOCUMENTS, COLL_QUIETANZE_F24,
)
from app.constants.codici_ravvedimento import CODICI_RAVVEDIMENTO
from app.engines import tributi_engine as te
from app.services.calendario_lavorativo import giorni_lavorativi_tra
from app.services.conti_pos import data_italiana
from app.services.f24_payment_evidence import (
    patch_pagamento_banca, stato_evidenza_pagamento,
)
from app.services.hr_cedolini_lettura import cedolini_hr_periodo, riepilogo_ritenute

logger = logging.getLogger(__name__)

ESITO_COPERTO = "COPERTO"
ESITO_PAGATO_SENZA_QUIETANZA = "PAGATO_SENZA_QUIETANZA"
ESITO_DA_PAGARE = "DA_PAGARE"
ESITO_NON_TROVATO = "NON_TROVATO"
ESITO_IMPORTO_DIVERSO = "IMPORTO_DIVERSO"
ESITI = (
    ESITO_COPERTO, ESITO_PAGATO_SENZA_QUIETANZA, ESITO_DA_PAGARE,
    ESITO_NON_TROVATO, ESITO_IMPORTO_DIVERSO,
)

# Tributi da sostituto d'imposta: natura da confrontare con i cedolini HR.
TRIBUTI_SOSTITUTO: Dict[str, str] = {
    "1001": "irpef", "1002": "irpef", "1004": "irpef", "1012": "irpef", "1040": "irpef",
    "3802": "addizionale_regionale",
    "3847": "addizionale_comunale", "3848": "addizionale_comunale",
    "DM10": "inps", "DM10/INPS": "inps", "INPS": "inps", "RC01": "inps",
}

FINESTRA_BANCA_PRIMA_GG = 3
FINESTRA_BANCA_DOPO_GG = 40
TOLLERANZA_AGGANCIO_GG = 3
# Confronto riga avviso ↔ riga F24: ±0,01 (arrotondamenti dell'avviso).
TOLLERANZA_IMPORTO_CENTS = 1
# Aggancio banca/quietanza ↔ modello: importo ESATTO al centesimo.
TOLLERANZA_AGGANCIO_CENTS = 0

REGEX_MOVIMENTI_F24 = "I24|F24|AGENZIA.*ENTRATE"
PDF_F24_URL = "/api/f24-riconciliazione/commercialista/{f24_id}/pdf"

_RE_NOME_QUIETANZA = re.compile(
    r"^(?P<data>\d{4}-\d{2}-\d{2})__F24_(?P<n>\d+)__quietanza_AE(?:__prot_(?P<prot>[0-9A-Za-z-]+))?",
)


# ── conversioni ──────────────────────────────────────────────────────────────

def centesimi(valore: Any) -> Optional[int]:
    """Importo → centesimi interi (arrotondamento commerciale). None se ignoto."""
    if valore in (None, "", False):
        return None
    if isinstance(valore, str):
        testo = valore.strip().replace("€", "").replace(" ", "")
        if "," in testo:
            testo = testo.replace(".", "").replace(",", ".")
        valore = testo
    try:
        return int((Decimal(str(valore)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, TypeError, ValueError):
        return None


def euro(cents: Optional[int]) -> Optional[float]:
    if cents is None:
        return None
    return float((Decimal(int(cents)) / Decimal(100)).quantize(Decimal("0.01")))


def normalizza_codice(codice: Any) -> str:
    testo = re.sub(r"\s+", "", str(codice or "")).upper()
    return "DM10" if testo in {"DM10", "DM10/INPS", "DM-10"} else testo


def parse_periodo_avviso(periodo: Any, anno_imposta: Any = None) -> Dict[str, Optional[int]]:
    """'MM/AAAA', 'MM-AAAA', 'AAAA-MM', 'AAAA' → {mese, anno}. ValueError se ignoto."""
    testo = str(periodo or "").strip()
    if not testo and anno_imposta:
        testo = str(anno_imposta)
    if re.fullmatch(r"\d{4}", testo):
        return {"mese": None, "anno": int(testo)}
    m = re.fullmatch(r"(\d{1,2})\s*[/-]\s*(\d{4})", testo)
    if m:
        mese, anno = int(m.group(1)), int(m.group(2))
    else:
        m = re.fullmatch(r"(\d{4})\s*[/-]\s*(\d{1,2})", testo)
        if not m:
            raise ValueError(f"periodo non valido: {testo!r} (usa MM/AAAA oppure AAAA)")
        anno, mese = int(m.group(1)), int(m.group(2))
    if mese == 0:
        return {"mese": None, "anno": anno}
    if not 1 <= mese <= 12:
        raise ValueError(f"mese non valido nel periodo {testo!r}")
    return {"mese": mese, "anno": anno}


def etichetta_periodo(periodo: Dict[str, Optional[int]]) -> str:
    if periodo.get("mese"):
        return f"{int(periodo['mese']):02d}/{periodo['anno']}"
    return str(periodo.get("anno") or "")


def _data_iso(valore: Any) -> Optional[str]:
    if isinstance(valore, (datetime, date)):
        return valore.strftime("%Y-%m-%d")
    testo = str(valore or "").strip()[:10]
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", testo):
        return testo
    m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", testo)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return None


def _giorni_tra(a: Optional[str], b: Optional[str]) -> Optional[int]:
    if not a or not b:
        return None
    try:
        return abs((date.fromisoformat(a) - date.fromisoformat(b)).days)
    except ValueError:
        return None


# ── righe e dati dei modelli ─────────────────────────────────────────────────

def periodo_riga(riga: Dict[str, Any]) -> Dict[str, Optional[int]]:
    """Periodo di una riga tributo: campi mese/anno espliciti, poi
    ``periodo_riferimento`` ('MM/AAAA'), poi solo anno. Una riga rateizzata
    ('01/01 2022', rateazione '0101') non ha mese: e' la rata, non gennaio."""
    rateizzata = te.riga_rateizzata(riga)
    mese_raw, anno_raw = riga.get("mese"), riga.get("anno")
    if anno_raw and str(anno_raw).strip().isdigit():
        anno = int(str(anno_raw).strip())
        mese = int(str(mese_raw).strip()) if mese_raw and str(mese_raw).strip().isdigit() else 0
        return {"mese": mese if 1 <= mese <= 12 and not rateizzata else None, "anno": anno}
    testo = riga.get("periodo_riferimento") or riga.get("periodo") or ""
    parsed = None if rateizzata else te._parse_periodo(testo)
    if parsed:
        return {"mese": parsed[0], "anno": parsed[1]}
    m = re.search(r"(\d{4})", str(testo))
    return {"mese": None, "anno": int(m.group(1))} if m else {"mese": None, "anno": None}


def righe_modello(f24: Dict[str, Any]) -> List[Dict[str, Any]]:
    righe = []
    for r in te._righe_f24(f24):
        periodo = periodo_riga(r)
        righe.append({
            "codice": normalizza_codice(r.get("_codice")),
            "sezione": r.get("_sezione"),
            "periodo_riferimento": r.get("periodo_riferimento") or r.get("periodo") or "",
            "mese": periodo["mese"],
            "anno": periodo["anno"],
            "importo_debito_cents": (
                r.get("importo_debito_cents") if isinstance(r.get("importo_debito_cents"), int)
                else centesimi(r.get("importo_debito") or r.get("importo")) or 0
            ),
            "importo_credito_cents": (
                r.get("importo_credito_cents") if isinstance(r.get("importo_credito_cents"), int)
                else centesimi(r.get("importo_credito")) or 0
            ),
            "descrizione": r.get("descrizione") or "",
        })
    return righe


def data_versamento_modello(f24: Dict[str, Any]) -> Optional[str]:
    dg = f24.get("dati_generali") or {}
    for valore in (
        dg.get("data_versamento"), f24.get("data_versamento"), dg.get("scadenza_nominale"),
        f24.get("data_scadenza"), dg.get("data_pagamento"),
    ):
        iso = _data_iso(valore)
        if iso:
            return iso
    return None


def saldo_modello_cents(f24: Dict[str, Any]) -> Optional[int]:
    totali = f24.get("totali") or {}
    for chiave in ("saldo_netto_cents", "saldo_finale_cents", "saldo_delega_cents"):
        if isinstance(totali.get(chiave), int):
            return totali[chiave]
    for chiave in ("saldo_netto", "saldo_finale", "saldo_delega"):
        c = centesimi(totali.get(chiave))
        if c is not None:
            return c
    return centesimi(f24.get("importo_totale") or f24.get("importo"))


def protocolli_modello(f24: Dict[str, Any]) -> Set[str]:
    dg = f24.get("dati_generali") or {}
    valori = (
        f24.get("protocollo"), f24.get("protocollo_telematico"), f24.get("protocollo_quietanza"),
        dg.get("protocollo"), dg.get("protocollo_telematico"),
    )
    return {re.sub(r"[^0-9A-Z]", "", str(v).upper()) for v in valori if v}


# ── quietanze e movimenti normalizzati ───────────────────────────────────────

def _quietanza_da_fiscal_document(doc: Dict[str, Any]) -> Dict[str, Any]:
    nome = str(doc.get("filename") or "")
    m = _RE_NOME_QUIETANZA.match(nome)
    meta = doc.get("metadata") or {}
    protocollo = (
        meta.get("protocollo") or meta.get("protocollo_telematico") or doc.get("protocollo_telematico")
        or (m.group("prot") if m else None)
    )
    importo = centesimi(meta.get("importo") or meta.get("saldo") or doc.get("importo") or doc.get("saldo"))
    f24_ids = {
        str(v) for v in (
            [doc.get("f24_id"), meta.get("f24_id")]
            + list(doc.get("f24_associati") or []) + list(doc.get("f24_ids") or [])
        ) if v
    }
    return {
        "id": doc.get("id"),
        "fonte": COLL_FISCAL_DOCUMENTS,
        "filename": nome,
        "data": _data_iso(meta.get("data_pagamento") or doc.get("data_pagamento") or (m.group("data") if m else None)),
        "protocollo": re.sub(r"[^0-9A-Z]", "", str(protocollo).upper()) if protocollo else None,
        "protocollo_originale": protocollo,
        "importo_cents": importo,
        "f24_ids": sorted(f24_ids),
        "origini": origini_documento(doc),
    }


# Da dove arriva un documento F24: posta (Gmail, casella documenti), Drive,
# caricato a mano. Un documento arrivato da piu' canali li porta tutti.
ORIGINI = {"posta": "Posta", "drive": "Drive", "caricato": "Caricato", "altro": "Altro"}


def _origine_da_source(source: Any) -> Optional[str]:
    s = str(source or "").lower()
    if not s:
        return None
    if "drive" in s:
        return "drive"
    if any(k in s for k in ("gmail", "email", "mail", "inbox", "posta", "pec")):
        return "posta"
    if "upload" in s or "manuale" in s:
        return "caricato"
    return "altro"


def origini_documento(doc: Dict[str, Any]) -> List[str]:
    """Canali da cui e' arrivato il documento, in ordine fisso (posta, drive, caricato, altro)."""
    trovate = set()
    for campo in ("fonte", "source", "origine", "source_module"):
        o = _origine_da_source(doc.get(campo))
        if o and not (campo == "fonte" and doc.get(campo) in (COLL_QUIETANZE_F24, COLL_FISCAL_DOCUMENTS)):
            trovate.add(o)
    for occ in doc.get("source_occurrences") or []:
        if isinstance(occ, dict):
            o = _origine_da_source(occ.get("source"))
            if o:
                trovate.add(o)
            if occ.get("drive_file_id"):
                trovate.add("drive")
    if doc.get("drive_file_id"):
        trovate.add("drive")
    if doc.get("email_info") or doc.get("gmail_message_id") or doc.get("email_id"):
        trovate.add("posta")
    return [o for o in ORIGINI if o in trovate] or ["altro"]


def saldo_quietanza_cents(doc: Dict[str, Any]) -> Optional[int]:
    """Saldo della delega; 0 e' un saldo letto (F24 tutto in compensazione), non un saldo mancante."""
    dg = doc.get("dati_generali") or {}
    totali = doc.get("totali") or {}
    if totali.get("saldo_netto_cents") not in (None, ""):
        try:
            return int(totali["saldo_netto_cents"])
        except (TypeError, ValueError):
            pass
    for valore in (doc.get("saldo_delega"), doc.get("saldo"), dg.get("saldo_delega"), totali.get("saldo_netto")):
        if valore is None or valore == "" or valore is False:
            continue
        cents = centesimi(valore)
        if cents is not None:
            return cents
        try:
            if Decimal(str(valore).replace(",", ".")) == 0:
                return 0
        except (InvalidOperation, ValueError):
            continue
    return None


def _quietanza_legacy(doc: Dict[str, Any]) -> Dict[str, Any]:
    dg = doc.get("dati_generali") or {}
    protocollo = doc.get("protocollo_telematico") or dg.get("protocollo_telematico") or doc.get("protocollo")
    importo = centesimi(
        doc.get("saldo_delega") or doc.get("saldo") or (doc.get("totali") or {}).get("saldo_netto")
    )
    righe = righe_modello(doc)
    if importo is None and righe:
        # Saldo zero letto: la delega e' tutta in compensazione.
        importo = saldo_quietanza_cents(doc)
    return {
        "id": doc.get("id"),
        "fonte": COLL_QUIETANZE_F24,
        "filename": doc.get("file_name") or doc.get("filename") or "",
        "data": _data_iso(doc.get("data_pagamento") or dg.get("data_pagamento") or dg.get("data_versamento")),
        "protocollo": re.sub(r"[^0-9A-Z]", "", str(protocollo).upper()) if protocollo else None,
        "protocollo_originale": protocollo,
        "importo_cents": importo,
        "f24_ids": sorted({str(v) for v in (doc.get("f24_associati") or []) if v}),
        "righe": righe,
        "origini": origini_documento(doc),
        # F24 del commercialista che questa quietanza ravvede (f24_ravvedimento).
        "ravvedimento_di": list(doc.get("ravvedimento_di") or []),
        # Rata del piano INPS che questa quietanza paga (dilazioni_inps).
        "dilazione_inps": doc.get("dilazione_inps"),
    }


def data_movimento(m: Dict[str, Any]) -> Optional[str]:
    info = m.get("f24_info") or {}
    for valore in (m.get("data_contabile"), m.get("data"), m.get("data_valuta"), info.get("data_incasso")):
        iso = _data_iso(valore)
        if iso:
            return iso
    return None


def importo_movimento_cents(m: Dict[str, Any]) -> Optional[int]:
    c = centesimi(m.get("importo"))
    return abs(c) if c is not None else None


def f24_ids_movimento(m: Dict[str, Any]) -> Set[str]:
    ids = {str(v) for v in (m.get("f24_ids") or []) if v}
    for chiave in ("f24_id", "f24_riconciliato_id"):
        if m.get(chiave):
            ids.add(str(m[chiave]))
    return ids


def _movimento_libero(m: Dict[str, Any]) -> bool:
    return not f24_ids_movimento(m) and m.get("tipo_riconciliazione") != "f24_tributi"


# ── caricamento del registro ─────────────────────────────────────────────────

async def carica_registro(db) -> Dict[str, Any]:
    """Legge una volta sola modelli, quietanze e addebiti bancari F24."""
    modelli = await db[COLL_F24].find(
        {"status": {"$ne": "eliminato"}}, {"_id": 0, "pdf_data": 0},
    ).to_list(5000)
    modelli = [f for f in modelli if f.get("entity_status") != "deleted"]

    quietanze: List[Dict[str, Any]] = []
    fiscal = await db[COLL_FISCAL_DOCUMENTS].find(
        {"category": "quietanza_f24"}, {"_id": 0, "pdf_data": 0},
    ).to_list(5000)
    quietanze.extend(_quietanza_da_fiscal_document(d) for d in fiscal
                     if d.get("entity_status") != "deleted")
    try:
        legacy = await db[COLL_QUIETANZE_F24].find({}, {"_id": 0, "pdf_data": 0}).to_list(5000)
    except Exception:  # noqa: BLE001 - collezione storica facoltativa
        legacy = []
    quietanze.extend(_quietanza_legacy(d) for d in legacy if d.get("entity_status") != "deleted")

    movimenti = await db[COLL_ESTRATTO_CONTO].find({"$or": [
        {"descrizione": {"$regex": REGEX_MOVIMENTI_F24, "$options": "i"}},
        {"descrizione_originale": {"$regex": REGEX_MOVIMENTI_F24, "$options": "i"}},
        {"classificazione_tipo": "f24"},
    ]}, {"_id": 0}).to_list(20000)
    movimenti = [
        m for m in movimenti
        if m.get("entity_status") != "deleted" and str(m.get("tipo") or "uscita").lower() != "entrata"
    ]

    # Indici: quietanze e movimenti per modello.
    quietanze_per_f24: Dict[str, List[Dict[str, Any]]] = {}
    for q in quietanze:
        for fid in q["f24_ids"]:
            quietanze_per_f24.setdefault(fid, []).append(q)
    quietanze_per_id = {str(q["id"]): q for q in quietanze if q.get("id")}
    movimenti_per_id = {str(m.get("id") or m.get("fingerprint")): m for m in movimenti}
    movimenti_per_f24: Dict[str, List[Dict[str, Any]]] = {}
    for m in movimenti:
        for fid in f24_ids_movimento(m):
            movimenti_per_f24.setdefault(fid, []).append(m)
    for f in modelli:
        fid = str(f.get("id"))
        riferimenti = {str(f.get("movimento_bancario_id") or "")}
        riferimenti.update(str(a.get("movimento_id") or "") for a in (f.get("allocazioni_banca") or []))
        for rif in riferimenti - {""}:
            m = movimenti_per_id.get(rif)
            if m and m not in movimenti_per_f24.setdefault(fid, []):
                movimenti_per_f24[fid].append(m)
        if f.get("quietanza_id"):
            q = quietanze_per_id.get(str(f["quietanza_id"]))
            if q and q not in quietanze_per_f24.setdefault(fid, []):
                quietanze_per_f24[fid].append(q)

    return {
        "f24": modelli,
        "quietanze": quietanze,
        "movimenti": movimenti,
        "quietanze_per_f24": quietanze_per_f24,
        "movimenti_per_f24": movimenti_per_f24,
        "conteggi": {
            "f24": len(modelli), "quietanze": len(quietanze), "movimenti_f24_banca": len(movimenti),
            "quietanze_fiscal_documents": len(fiscal), "quietanze_legacy": len(legacy),
        },
    }


# ── prove per modello ────────────────────────────────────────────────────────

def _vista_movimento(m: Dict[str, Any], agganciato: bool, f24: Dict[str, Any]) -> Dict[str, Any]:
    data = data_movimento(m)
    return {
        "movimento_id": m.get("id") or m.get("fingerprint"),
        "data": data,
        "data_it": data_italiana(data),
        "importo": euro(importo_movimento_cents(m)),
        "descrizione": m.get("descrizione") or m.get("descrizione_originale"),
        "agganciato": agganciato,
        "giorni_dalla_scadenza": _giorni_tra(data, data_versamento_modello(f24)),
        "link": f"/riconciliazione/banca?movimento={m.get('id') or m.get('fingerprint')}",
    }


def _vista_quietanza(q: Dict[str, Any], agganciata: bool) -> Dict[str, Any]:
    return {
        "quietanza_id": q.get("id"),
        "fonte": q.get("fonte"),
        "filename": q.get("filename"),
        "protocollo": q.get("protocollo_originale"),
        "data": q.get("data"),
        "data_it": data_italiana(q.get("data")),
        "importo": euro(q.get("importo_cents")),
        "agganciata": agganciata,
    }


def prove_modello(f24: Dict[str, Any], registro: Dict[str, Any]) -> Dict[str, Any]:
    """Quietanze e addebiti del modello: agganciati, oppure compatibili nella
    finestra scadenza −3/+40 giorni con importo esatto (non agganciati)."""
    fid = str(f24.get("id"))
    evidenza = stato_evidenza_pagamento(f24)
    data_vers = data_versamento_modello(f24)
    saldo = saldo_modello_cents(f24)

    agganciati = registro["movimenti_per_f24"].get(fid, [])
    ids_agganciati = {str(m.get("id") or m.get("fingerprint")) for m in agganciati}
    addebiti = [_vista_movimento(m, True, f24) for m in agganciati]
    compatibili: List[Dict[str, Any]] = []
    if data_vers and saldo is not None:
        inizio = date.fromisoformat(data_vers) - timedelta(days=FINESTRA_BANCA_PRIMA_GG)
        fine = date.fromisoformat(data_vers) + timedelta(days=FINESTRA_BANCA_DOPO_GG)
        for m in registro["movimenti"]:
            mid = str(m.get("id") or m.get("fingerprint"))
            if mid in ids_agganciati or not _movimento_libero(m):
                continue
            dm = data_movimento(m)
            if not dm or not (inizio <= date.fromisoformat(dm) <= fine):
                continue
            imp = importo_movimento_cents(m)
            if imp is not None and abs(imp - saldo) <= TOLLERANZA_AGGANCIO_CENTS:
                compatibili.append(_vista_movimento(m, False, f24))

    quietanze_agganciate = registro["quietanze_per_f24"].get(fid, [])
    quietanze = [_vista_quietanza(q, True) for q in quietanze_agganciate]
    protocolli = protocolli_modello(f24)
    for q in registro["quietanze"]:
        if q in quietanze_agganciate or q["f24_ids"]:
            continue
        per_protocollo = bool(q["protocollo"]) and q["protocollo"] in protocolli
        per_data_importo = (
            bool(q["data"]) and q["data"] == data_vers
            and q["importo_cents"] is not None and saldo is not None
            and abs(q["importo_cents"] - saldo) <= TOLLERANZA_AGGANCIO_CENTS
        )
        if per_protocollo or per_data_importo:
            quietanze.append({**_vista_quietanza(q, False),
                              "criterio": "protocollo" if per_protocollo else "data_e_importo"})

    banca_agganciata = evidenza["verificato_banca"] or bool(addebiti)
    banca_compatibile = len(compatibili) == 1
    quietanza_presente = evidenza["quietanza_presente"] or bool(quietanze)
    return {
        "stato_evidenza": evidenza["stato"],
        "pagato_banca": banca_agganciata,
        "addebito_compatibile_non_agganciato": banca_compatibile,
        "addebiti_ambigui": len(compatibili) > 1,
        "quietanza_presente": quietanza_presente,
        "addebiti_banca": addebiti + compatibili,
        "quietanze": quietanze,
        "data_versamento": data_vers,
        "saldo_modello_cents": saldo,
    }


def _esito_da_prove(prove: Dict[str, Any]) -> Tuple[str, str]:
    pagato = prove["pagato_banca"] or prove["addebito_compatibile_non_agganciato"]
    if pagato and prove["quietanza_presente"]:
        return ESITO_COPERTO, "F24 pagato: addebito bancario e quietanza presenti"
    if prove["quietanza_presente"]:
        return ESITO_COPERTO, "quietanza presente (addebito bancario da verificare in estratto conto)"
    if pagato:
        motivo = (
            "addebito bancario agganciato al modello, nessuna quietanza in archivio"
            if prove["pagato_banca"] else
            "addebito bancario compatibile (data ±3 gg, importo esatto) non ancora agganciato, nessuna quietanza"
        )
        return ESITO_PAGATO_SENZA_QUIETANZA, motivo
    if prove["addebiti_ambigui"]:
        return ESITO_DA_PAGARE, "piu' addebiti compatibili: aggancio ambiguo, scegliere manualmente"
    return ESITO_DA_PAGARE, "modello presente ma senza quietanza ne' addebito bancario"


def _vista_modello(f24: Dict[str, Any], righe: List[Dict[str, Any]], prove: Dict[str, Any]) -> Dict[str, Any]:
    fid = f24.get("id")
    return {
        "f24_id": fid,
        "file_name": f24.get("file_name") or f24.get("filename"),
        "data_versamento": prove["data_versamento"],
        "data_versamento_it": data_italiana(prove["data_versamento"]),
        "saldo_modello": euro(prove["saldo_modello_cents"]),
        "importo_righe": euro(sum(r["importo_debito_cents"] for r in righe)),
        "credito_righe": euro(sum(r["importo_credito_cents"] for r in righe)),
        "righe": [
            {
                "codice_tributo": r["codice"], "sezione": r["sezione"],
                "periodo_riferimento": r["periodo_riferimento"],
                "importo_debito": euro(r["importo_debito_cents"]),
                "importo_credito": euro(r["importo_credito_cents"]),
                "descrizione": r["descrizione"],
            } for r in righe
        ],
        "status": f24.get("status"),
        "pagato": bool(f24.get("pagato")),
        "stato_evidenza": prove["stato_evidenza"],
        "quietanza_id": f24.get("quietanza_id"),
        "movimento_bancario_id": f24.get("movimento_bancario_id"),
        "pdf_url": PDF_F24_URL.format(f24_id=fid),
    }


def _periodo_compatibile(riga: Dict[str, Any], periodo: Dict[str, Optional[int]]) -> bool:
    if riga["anno"] != periodo["anno"]:
        return False
    if periodo["mese"] is None or riga["mese"] is None:
        return True
    return riga["mese"] == periodo["mese"]


# ── indizi per una riga non trovata ──────────────────────────────────────────

INDIZIO_COMPENSAZIONE_6099 = "POSSIBILE_COMPENSAZIONE_6099"
INDIZIO_ERRORE_PERIODO = "POSSIBILE_ERRORE_PERIODO_IMPUTAZIONE"
# «Importo quasi identico»: la sola soglia del cruscotto fiscale del titolare,
# 1,00 EUR assoluto. Serve a proporre dove guardare, mai ad associare.
TOLLERANZA_INDIZIO_CENTS = 100


def indizi_riga_mancante(
    codice: str, periodo: Dict[str, Optional[int]], importo_cents: int, registro: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Dove guardare prima di dire «non pagato». Sola lettura, nessun esito cambia.

    * una riga 6099 (IVA annuale) di importo uguale entro 1,00 EUR, a debito o a
      credito: il tributo puo' essere stato versato o compensato come saldo IVA;
    * lo stesso codice con importo uguale ma un altro anno: periodo imputato
      male sul modello.

    Sono indizi da verificare con il commercialista, non prove di pagamento:
    chi li legge decide, il registro non li applica mai."""
    indizi: List[Dict[str, Any]] = []
    for f24 in registro["f24"]:
        for r in righe_modello(f24):
            importo_riga = r["importo_debito_cents"] or r["importo_credito_cents"]
            if not importo_riga or abs(importo_riga - importo_cents) > TOLLERANZA_INDIZIO_CENTS:
                continue
            tipo = None
            if r["codice"] == "6099" and codice != "6099":
                tipo = INDIZIO_COMPENSAZIONE_6099
                spiegazione = (
                    "Riga 6099 (IVA annuale) di importo quasi identico"
                    + (" a credito: possibile compensazione" if r["importo_credito_cents"] else ": possibile versamento come saldo IVA")
                )
            elif r["codice"] == codice and periodo.get("anno") and r["anno"] and r["anno"] != periodo["anno"]:
                tipo = INDIZIO_ERRORE_PERIODO
                spiegazione = f"Stesso codice {codice} con importo quasi identico ma anno {r['anno']}: possibile errore di imputazione del periodo"
            if not tipo:
                continue
            data = data_versamento_modello(f24)
            prove = prove_modello(f24, registro)
            indizi.append({
                "tipo": tipo,
                "spiegazione": spiegazione + " — da verificare con il commercialista",
                "f24_id": f24.get("id"),
                "file_name": f24.get("file_name"),
                "codice_tributo": r["codice"],
                "periodo": r["periodo_riferimento"],
                "importo": euro(importo_riga),
                "a_credito": bool(r["importo_credito_cents"]),
                "data_versamento": data,
                "data_versamento_it": data_italiana(data),
                "pdf_url": PDF_F24_URL.format(f24_id=f24.get("id")),
                # un modello non pagato non prova niente: lo si dice
                "stato_evidenza": prove["stato_evidenza"],
                "pagato_banca": prove["pagato_banca"],
            })
    indizi.sort(key=lambda i: i["data_versamento"] or "", reverse=True)
    return indizi


# ── controllo di una riga dell'avviso ────────────────────────────────────────

def controlla_riga(
    riga_avviso: Dict[str, Any], registro: Dict[str, Any],
    cedolini_hr: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    codice = normalizza_codice(riga_avviso.get("codice_tributo"))
    periodo = parse_periodo_avviso(riga_avviso.get("periodo"), riga_avviso.get("anno_imposta"))
    importo_cents = centesimi(riga_avviso.get("importo"))
    if not codice:
        raise ValueError("codice_tributo obbligatorio")
    if importo_cents is None:
        raise ValueError(f"importo non valido per il tributo {codice}")

    candidati: List[Dict[str, Any]] = []
    for f24 in registro["f24"]:
        righe = [r for r in righe_modello(f24)
                 if r["codice"] == codice and _periodo_compatibile(r, periodo)]
        if not righe:
            continue
        somma = sum(r["importo_debito_cents"] for r in righe)
        candidati.append({"f24": f24, "righe": righe, "somma_cents": somma,
                          "differenza_cents": importo_cents - somma})

    base = {
        "codice_tributo": codice,
        "descrizione_tributo": next(
            (r["descrizione"] for c in candidati for r in c["righe"] if r["descrizione"]), None,
        ),
        "periodo": etichetta_periodo(periodo),
        "anno_imposta": riga_avviso.get("anno_imposta") or periodo["anno"],
        "importo": euro(importo_cents),
        "importo_cents": importo_cents,
        "descrizione": riga_avviso.get("descrizione"),
    }

    if not candidati:
        esito = {
            **base, "esito": ESITO_NON_TROVATO, "differenza": None,
            "motivazione": f"nessuna riga {codice} per il periodo {base['periodo']} nei {registro['conteggi']['f24']} modelli in archivio",
            "righe_f24": [], "quietanze": [], "addebiti_banca": [],
        }
    else:
        esatti = [c for c in candidati if abs(c["differenza_cents"]) <= TOLLERANZA_IMPORTO_CENTS]
        if not esatti:
            vicino = min(candidati, key=lambda c: abs(c["differenza_cents"]))
            prove = {c["f24"].get("id"): prove_modello(c["f24"], registro) for c in candidati}
            esito = {
                **base, "esito": ESITO_IMPORTO_DIVERSO,
                "differenza": euro(vicino["differenza_cents"]),
                "differenza_cents": vicino["differenza_cents"],
                "importo_f24": euro(vicino["somma_cents"]),
                "motivazione": (
                    f"riga {codice} {base['periodo']} presente nel modello "
                    f"{vicino['f24'].get('file_name') or vicino['f24'].get('id')} per "
                    f"{euro(vicino['somma_cents']):.2f} €: differenza avviso − F24 = "
                    f"{euro(vicino['differenza_cents']):.2f} €"
                ),
                "righe_f24": [_vista_modello(c["f24"], c["righe"], prove[c["f24"].get("id")]) for c in candidati],
                "quietanze": [q for c in candidati for q in prove[c["f24"].get("id")]["quietanze"]],
                "addebiti_banca": [a for c in candidati for a in prove[c["f24"].get("id")]["addebiti_banca"]],
            }
        else:
            valutati = []
            for c in esatti:
                prove = prove_modello(c["f24"], registro)
                es, motivo = _esito_da_prove(prove)
                valutati.append((c, prove, es, motivo))
            ordine = {ESITO_COPERTO: 0, ESITO_PAGATO_SENZA_QUIETANZA: 1, ESITO_DA_PAGARE: 2}
            valutati.sort(key=lambda v: ordine[v[2]])
            migliore = valutati[0]
            esito = {
                **base, "esito": migliore[2], "differenza": 0.0,
                "motivazione": migliore[3] + (
                    f" ({len(valutati)} modelli con la stessa riga)" if len(valutati) > 1 else ""
                ),
                "righe_f24": [_vista_modello(c["f24"], c["righe"], p) for c, p, _, _ in valutati],
                "quietanze": [q for _, p, _, _ in valutati for q in p["quietanze"]],
                "addebiti_banca": [a for _, p, _, _ in valutati for a in p["addebiti_banca"]],
            }

    esito["indizi"] = (
        indizi_riga_mancante(codice, periodo, importo_cents, registro)
        if esito["esito"] in (ESITO_NON_TROVATO, ESITO_IMPORTO_DIVERSO) else []
    )

    natura = TRIBUTI_SOSTITUTO.get(codice)
    esito["natura_sostituto"] = natura
    if natura and cedolini_hr is not None:
        riepilogo = riepilogo_ritenute(cedolini_hr.get("cedolini") or [], natura, euro(importo_cents))
        riepilogo["configurato"] = cedolini_hr.get("configurato", True)
        riepilogo["errore"] = cedolini_hr.get("errore")
        riepilogo["periodo"] = base["periodo"]
        riepilogo["link"] = "/hr/"
        esito["cedolini_hr"] = riepilogo
    else:
        esito["cedolini_hr"] = None
    return esito


async def controlla_avviso(
    db, righe: Iterable[Dict[str, Any]], *, includi_cedolini_hr: bool = True,
    leggi_cedolini: Callable[[int, int], Awaitable[Dict[str, Any]]] = cedolini_hr_periodo,
    numero_avviso: Optional[str] = None, data_avviso: Optional[str] = None,
) -> Dict[str, Any]:
    """Controllo incrociato di tutte le righe di un avviso bonario. Sola lettura."""
    righe = list(righe)
    registro = await carica_registro(db)

    cedolini_per_periodo: Dict[Tuple[int, int], Dict[str, Any]] = {}
    if includi_cedolini_hr:
        for r in righe:
            if normalizza_codice(r.get("codice_tributo")) not in TRIBUTI_SOSTITUTO:
                continue
            periodo = parse_periodo_avviso(r.get("periodo"), r.get("anno_imposta"))
            if periodo["mese"] and periodo["anno"] and (periodo["anno"], periodo["mese"]) not in cedolini_per_periodo:
                cedolini_per_periodo[(periodo["anno"], periodo["mese"])] = await leggi_cedolini(
                    periodo["anno"], periodo["mese"],
                )

    esiti = []
    for r in righe:
        periodo = parse_periodo_avviso(r.get("periodo"), r.get("anno_imposta"))
        ced = cedolini_per_periodo.get((periodo["anno"], periodo["mese"])) if periodo["mese"] else None
        esiti.append(controlla_riga(r, registro, ced))

    # Scadenzario: pagato nei termini o ravveduto → la riga non e' dovuta.
    from app.services import scadenzario_tributi as sc

    quietanze_con_righe = [q for q in registro["quietanze"] if q.get("righe")]
    scadenze = {}
    for f24 in registro["f24"]:
        if str(f24.get("etichetta") or "").upper() == "RAVVEDIMENTO":
            continue
        dv = data_versamento_modello(f24)
        if dv:
            for r in righe_modello(f24):
                scadenze.setdefault((r["sezione"], r["codice"], r["anno"], r["mese"]), dv)
    voci_scad = sc.calcola(pagamenti_da_quietanze(quietanze_con_righe), scadenze)
    verdetti = []
    for r, e in zip(righe, esiti):
        periodo = parse_periodo_avviso(r.get("periodo"), r.get("anno_imposta"))
        v = sc.verdetto_riga(
            normalizza_codice(r.get("codice_tributo")), periodo["anno"], periodo["mese"], e["importo_cents"],
            voci_scad, sanzioni_richieste_cents=centesimi(r.get("importo_sanzioni")) or 0,
            interessi_richiesti_cents=centesimi(r.get("importo_interessi")) or 0,
            data_versamento_ade=_data_iso(r.get("data_versamento_ade")),
        )
        e["scadenzario"] = v
        verdetti.append(v)

    per_esito = {e: 0 for e in ESITI}
    totali = {e: 0 for e in ESITI}
    for e in esiti:
        per_esito[e["esito"]] += 1
        totali[e["esito"]] += e["importo_cents"]
    totale = sum(e["importo_cents"] for e in esiti)
    coperto = totali[ESITO_COPERTO]
    versato_senza_quietanza = totali[ESITO_PAGATO_SENZA_QUIETANZA]
    return {
        "numero_avviso": numero_avviso,
        "data_avviso": _data_iso(data_avviso),
        "data_avviso_it": data_italiana(_data_iso(data_avviso)),
        "righe": esiti,
        "riepilogo": {
            "n_righe": len(esiti),
            "totale_avviso": euro(totale),
            "totale_coperto": euro(coperto),
            "totale_pagato_senza_quietanza": euro(versato_senza_quietanza),
            "totale_scoperto": euro(totale - coperto - versato_senza_quietanza),
            "per_esito": per_esito,
            "importi_per_esito": {k: euro(v) for k, v in totali.items()},
        },
        "verdetto": sc.verdetto_avviso(numero_avviso, verdetti),
        "fonti": registro["conteggi"],
        "cedolini_hr_letti": {
            f"{m:02d}/{a}": {"n": len(v.get("cedolini") or []), "configurato": v.get("configurato"), "errore": v.get("errore")}
            for (a, m), v in cedolini_per_periodo.items()
        },
        "sola_lettura": True,
    }


# ── verifica-codice sul registro unico (PR 12) ───────────────────────────────

async def verifica_codice(
    db, codice_tributo: str, anno: Optional[str] = None, mese: Optional[str] = None,
) -> Dict[str, Any]:
    """Tutte le righe di un tributo (opzionalmente per anno/mese) con le prove
    reali: modello, quietanza (fiscal_documents/legacy) e addebito bancario."""
    codice = normalizza_codice(codice_tributo)
    registro = await carica_registro(db)
    filtro_anno = int(anno) if anno and str(anno).isdigit() else None
    filtro_mese = int(mese) if mese and str(mese).isdigit() else None

    risultati = []
    for f24 in registro["f24"]:
        righe = [r for r in righe_modello(f24) if r["codice"] == codice]
        if filtro_anno is not None:
            righe = [r for r in righe if r["anno"] == filtro_anno]
        if filtro_mese is not None:
            righe = [r for r in righe if r["mese"] == filtro_mese]
        if not righe:
            continue
        prove = prove_modello(f24, registro)
        es, motivo = _esito_da_prove(prove)
        vista = _vista_modello(f24, righe, prove)
        risultati.append({
            **vista,
            "esito": es, "motivazione": motivo,
            "quietanze": prove["quietanze"], "addebiti_banca": prove["addebiti_banca"],
            "pagato": es in (ESITO_COPERTO, ESITO_PAGATO_SENZA_QUIETANZA),
            "pagamento_verificato_banca": prove["pagato_banca"],
        })
    risultati.sort(key=lambda r: r.get("data_versamento") or "", reverse=True)
    periodo_cercato = (
        f"{filtro_mese:02d}/{filtro_anno}" if filtro_mese and filtro_anno
        else str(filtro_anno) if filtro_anno else "tutti"
    )
    from app.services.codici_tributo_f24 import CODICI_TRIBUTO_F24

    return {
        "codice_tributo": codice,
        "descrizione": (CODICI_TRIBUTO_F24.get(codice) or {}).get("descrizione"),
        "periodo_cercato": periodo_cercato,
        "pagato": any(r["pagamento_verificato_banca"] for r in risultati),
        "righe_f24": risultati,
        # chiavi storiche dell'endpoint, ora alimentate dal registro unico
        "pagamenti": [r for r in risultati if r["pagato"]],
        "quietanze_da_verificare_banca": sum(
            1 for r in risultati if r["quietanze"] and not r["pagamento_verificato_banca"]
        ),
        "in_attesa": [
            {"f24_id": r["f24_id"], "scadenza": r["data_versamento"],
             "scadenza_it": r["data_versamento_it"], "importo": r["saldo_modello"]}
            for r in risultati if r["esito"] == ESITO_DA_PAGARE
        ],
        "fonti": registro["conteggi"],
    }


# ── aggancio addebiti/quietanze ↔ F24 (PR 12) ────────────────────────────────

def _f24_aperto_banca(f24: Dict[str, Any]) -> bool:
    return not stato_evidenza_pagamento(f24)["verificato_banca"]


# ── riscontro quietanza ↔ addebito bancario ─────────────────────────────────
#
# Quietanza e addebito sono due prove dello stesso pagamento, e restano due
# record distinti: qui si collegano, non si fondono, e il modello F24 non si
# ricostruisce (se manca resta «F24 mancante»). Serve perche' il motore
# canonico abbina la banca ai soli modelli: al 27/09/2026 242 pagamenti su 328
# avevano la sola quietanza, e i loro addebiti I24 restavano orfani.
#
# Un pagamento e' il suo protocollo telematico: due copie della stessa
# quietanza (scaricata due volte, nomi diversi) sono un pagamento solo.
# Un motore solo, a livelli (RST-F24B). Ogni coppia pagamento ↔ addebito ha un
# ``livello`` e una ``motivazione`` con importo, date e causale confrontati:
#
# * CERTO: importo uguale al centesimo, addebito entro 2 giorni lavorativi
#   (con i festivi) dalla data del pagamento, causale di delega F24/I24 e,
#   per una quietanza, la «DATA INCASSO» della causale uguale alla sua data.
#   E' l'unico livello che scrive il pagamento;
# * PROBABILE: importo e data uguali ma causale senza data d'incasso, oppure
#   piu' addebiti compatibili (si mostrano tutti, non se ne sceglie uno);
# * PARZIALE: differenza d'importo sotto la soglia (5 EUR), con la differenza;
# * NESSUN_MATCH: nessun addebito, dicendo se l'estratto del periodo c'e';
# * MOVIMENTO_ORFANO: addebito senza quietanza, da riscaricare.
#
# I livelli diversi da CERTO scrivono solo una relazione ``pending`` in
# ``entity_relations``, mai un pagamento. Mai per solo importo.

RISCONTRO_CERTO = "RISCONTRATO_BANCA"
RISCONTRO_DA_VERIFICARE = "DA_VERIFICARE"
LIVELLO_CERTO = "CERTO"
LIVELLO_PROBABILE = "PROBABILE"
LIVELLO_PARZIALE = "PARZIALE"
LIVELLO_NESSUN_MATCH = "NESSUN_MATCH"
LIVELLO_MOVIMENTO_ORFANO = "MOVIMENTO_ORFANO"
LIVELLI = (LIVELLO_CERTO, LIVELLO_PROBABILE, LIVELLO_PARZIALE, LIVELLO_NESSUN_MATCH,
           LIVELLO_MOVIMENTO_ORFANO)
GIORNI_LAVORATIVI_ADDEBITO = 2
GIORNI_COPERTURA_ESTRATTO = 5
SOGLIA_PARZIALE_CENTS = 500
NOTA_COMMERCIALISTA = "da verificare con il commercialista"
_RE_ADDEBITO_DELEGA = re.compile(r"\bI24\b|\bF24\b|DELEGA\s+UNIFICATA", re.I)
_RE_DATA_INCASSO = re.compile(r"DATA\s+INCASSO\s+(\d{2})/(\d{2})/(\d{4})", re.I)


def data_incasso_causale(m: Dict[str, Any]) -> Optional[str]:
    """La «DATA INCASSO gg/mm/aaaa» che la banca scrive nella causale I24.

    Se la riga tenuta ha la causale troncata (il vecchio archivio scrive solo
    «I24 AGENZIA ENTRATE») vale quella dell'export ufficiale della banca, la
    copia dello stesso movimento messa in quarantena come doppione
    (``causale_export_banca``, vedi ``causali_export_banca``).
    """
    for campo in ("descrizione", "descrizione_originale", "causale", "causale_export_banca"):
        trovata = _RE_DATA_INCASSO.search(str(m.get(campo) or ""))
        if trovata:
            return f"{trovata.group(3)}-{trovata.group(2)}-{trovata.group(1)}"
    return None


async def causali_export_banca(db, movimenti: List[Dict[str, Any]]) -> int:
    """Alle righe I24 senza data d'incasso aggiunge la causale della copia in quarantena.

    Quando due export dello stesso conto portano la stessa riga, resta la
    copia gia' collegata e l'altra va in ``estratto_conto_movimenti_quarantena``
    con ``duplicato_di`` (``doppioni_estratto_conto.ripulisci_import``): se la
    causale completa era sull'altra, la «DATA INCASSO» spariva e un addebito
    certo restava da verificare (8.139,63 EUR del 17/06/2026). La copia vale
    solo con lo stesso importo al centesimo; si annota in memoria, non si scrive.
    """
    from app.services.doppioni_estratto_conto import COLLEZIONE_QUARANTENA

    senza = {
        str(m["id"]): m for m in movimenti
        if m.get("id") and e_addebito_delega(m) and not data_incasso_causale(m)
    }
    if not senza:
        return 0
    copie = await db[COLLEZIONE_QUARANTENA].find(
        {"duplicato_di": {"$in": list(senza)}},
        {"_id": 0, "id": 1, "duplicato_di": 1, "importo": 1,
         "descrizione": 1, "descrizione_originale": 1},
    ).to_list(len(senza) * 4 + 10)
    arricchiti = 0
    for copia in copie:
        m = senza.get(str(copia.get("duplicato_di") or ""))
        if m is None or m.get("causale_export_banca"):
            continue
        cents = importo_movimento_cents(m)
        if not cents or importo_movimento_cents(copia) != cents:
            continue
        testo = str(copia.get("descrizione") or copia.get("descrizione_originale") or "")
        if _RE_DATA_INCASSO.search(testo):
            m["causale_export_banca"] = testo
            m["causale_export_banca_da"] = copia.get("id")
            arricchiti += 1
    return arricchiti


def e_addebito_delega(m: Dict[str, Any]) -> bool:
    """Un addebito di delega F24 (I24): non un bollettino CBILL/PagoPA all'Agenzia."""
    testo = str(m.get("descrizione") or m.get("descrizione_originale") or "")
    return bool(_RE_ADDEBITO_DELEGA.search(testo))


def url_pdf_quietanza(q: Dict[str, Any]) -> Optional[str]:
    """Il PDF vero della quietanza, con gli stessi lettori dell'analisi F24."""
    if not q.get("id"):
        return None
    if q.get("fonte") == COLL_FISCAL_DOCUMENTS:
        return f"/api/fiscal/documents/{q['id']}/content"
    return f"/api/f24-public/pdf/{q['id']}"


def data_invio_protocollo(protocollo: Any) -> Optional[str]:
    """Il giorno in cui la delega e' stata inviata, dalle prime cifre del protocollo.

    Il protocollo telematico dell'AdE comincia con AAMMGG dell'invio
    («26060212304532735/000001» = 02/06/2026). Una delega inviata prima del
    giorno di versamento e' stata programmata (di norma dall'intermediario);
    una inviata il giorno stesso no.
    """
    m = re.match(r"(\d{2})(\d{2})(\d{2})\d", str(protocollo or "").strip())
    if not m:
        return None
    try:
        return date(2000 + int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
    except ValueError:
        return None


def tipo_versamento_righe(righe: Iterable[Dict[str, Any]]) -> Optional[str]:
    """Ordinario, ravvedimento (sanzioni o interessi) o regolarizzazione (RC01)."""
    codici = {str(r.get("codice") or "").upper() for r in righe if r.get("codice")}
    if not codici:
        return None
    if "RC01" in codici:
        return "regolarizzazione"
    if codici & CODICI_RAVVEDIMENTO:
        return "ravvedimento"
    return "ordinario"


def pagamenti_da_quietanze(quietanze: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Le quietanze raggruppate per pagamento: protocollo, data e saldo uguali.

    Il protocollo da solo non basta: dallo stesso PDF escono deleghe diverse
    con lo stesso protocollo e importi diversi (5.959,18 e 12,95 EUR il
    21/08/2023). Due copie dello stesso pagamento coincidono in tutti e tre.
    Senza protocollo, o senza data e saldo, la quietanza fa pagamento da sola.
    """
    gruppi: Dict[str, List[Dict[str, Any]]] = {}
    for q in quietanze:
        if q.get("protocollo") and q.get("data") and q.get("importo_cents") is not None:
            chiave = f"{q['protocollo']}|{q['data']}|{q['importo_cents']}"
        else:
            chiave = f"id:{q.get('id')}"
        gruppi.setdefault(chiave, []).append(q)
    pagamenti = []
    for chiave, copie in gruppi.items():
        prima = copie[0]
        inviato_il = data_invio_protocollo(prima.get("protocollo_originale"))
        ravvedimento_di = sorted({str(o) for q in copie for o in (q.get("ravvedimento_di") or [])})
        righe = prima.get("righe") or []
        pagamenti.append({
            "chiave": chiave,
            "protocollo": prima.get("protocollo_originale"),
            "data": prima.get("data"),
            "importo_cents": prima.get("importo_cents"),
            "quietanze": [{"id": q.get("id"), "fonte": q.get("fonte"), "filename": q.get("filename"),
                           "pdf_url": url_pdf_quietanza(q)} for q in copie],
            "origini": [o for o in ORIGINI if any(o in (q.get("origini") or []) for q in copie)],
            # Saldo zero con righe a debito: pagata tutta in compensazione,
            # nessun addebito in banca da cercare.
            "compensazione_totale": prima.get("importo_cents") == 0 and any(
                int(r.get("importo_debito_cents") or 0) > 0 for r in righe),
            "ravvedimento_di": ravvedimento_di,
            "inviato_il": inviato_il,
            "programmato": (inviato_il < prima["data"]) if inviato_il and prima.get("data") else None,
            "tipo_versamento": tipo_versamento_righe(righe),
            # Nessun modello del commercialista collegato, nemmeno come ravvedimento.
            "senza_modello": not ravvedimento_di and not any(q.get("f24_ids") for q in copie),
            "dilazione_inps": next((q["dilazione_inps"] for q in copie if q.get("dilazione_inps")), None),
            "_righe": righe,
        })
    return pagamenti


def _vista_addebito(m: Dict[str, Any]) -> Dict[str, Any]:
    data = data_movimento(m)
    mid = str(m.get("id") or m.get("fingerprint"))
    return {
        "movimento_id": mid,
        "data": data,
        "data_it": data_italiana(data),
        "importo": euro(importo_movimento_cents(m)),
        "descrizione": m.get("descrizione") or m.get("descrizione_originale"),
        "data_incasso": data_incasso_causale(m),
        "link": f"/riconciliazione/banca?movimento={mid}",
    }


def _vista_pagamento(p: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "chiave": p["chiave"],
        "protocollo": p["protocollo"],
        "data": p["data"],
        "data_it": data_italiana(p["data"]),
        "importo": euro(p["importo_cents"]),
        "quietanze": p["quietanze"],
        "inviato_il": p.get("inviato_il"),
        "inviato_il_it": data_italiana(p["inviato_il"]) if p.get("inviato_il") else None,
        "programmato": p.get("programmato"),
        "tipo_versamento": p.get("tipo_versamento"),
        "senza_modello": p.get("senza_modello"),
        "dilazione_inps": p.get("dilazione_inps"),
        # Pagamento di ravvedimento: gli F24 del commercialista che ravvede.
        "ravvedimento_di": [
            {"f24_id": oid, "pdf_url": f"/api/f24-public/pdf/{oid}"} for oid in p.get("ravvedimento_di") or []
        ],
    }


def _mid(m: Dict[str, Any]) -> str:
    return str(m.get("id") or m.get("fingerprint"))


def _abbina(
    unita: Iterable[Dict[str, Any]], addebiti: List[Dict[str, Any]], soglia_parziale_cents: int,
) -> Tuple[Dict[str, Dict[str, List[Dict[str, Any]]]], Dict[str, List[str]]]:
    """Candidati di ogni pagamento fra gli addebiti, senza scrivere e senza scegliere.

    ``unita``: ``chiave``, ``data`` (ISO), ``importo_cents`` e, per un modello,
    ``bidirezionale`` (la data del modello e' quella programmata: l'addebito
    puo' anche precederla). L'addebito sta entro ``GIORNI_LAVORATIVI_ADDEBITO``
    giorni lavorativi e la sua «DATA INCASSO», se c'e', e' quella del pagamento.
    Un addebito gia' candidato esatto di un pagamento non e' proposto come
    parziale di un altro.
    """
    per_unita: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    for u in unita:
        if not u["data"] or not u["importo_cents"]:
            continue
        giorno_u = date.fromisoformat(u["data"])
        for m in addebiti:
            imp = importo_movimento_cents(m)
            if imp is None:
                continue
            diff = imp - u["importo_cents"]
            if abs(diff) > soglia_parziale_cents:
                continue
            lavorativi = giorni_lavorativi_tra(giorno_u, date.fromisoformat(data_movimento(m)))
            dentro = (abs(lavorativi) <= GIORNI_LAVORATIVI_ADDEBITO if u.get("bidirezionale")
                      else 0 <= lavorativi <= GIORNI_LAVORATIVI_ADDEBITO)
            if not dentro:
                continue
            incasso = data_incasso_causale(m)
            if u.get("incasso_obbligatorio") and incasso and incasso != u["data"]:
                continue  # la banca dice che e' un altro versamento (la data del modello e' solo programmata)
            voce = {"m": m, "giorni": lavorativi, "incasso": incasso, "diff": diff}
            per_unita.setdefault(u["chiave"], {"esatti": [], "parziali": []})[
                "esatti" if diff == 0 else "parziali"].append(voce)
    esatti = {_mid(v["m"]) for c in per_unita.values() for v in c["esatti"]}
    per_addebito: Dict[str, List[str]] = {}
    for chiave, c in per_unita.items():
        c["parziali"] = [v for v in c["parziali"] if _mid(v["m"]) not in esatti]
        for v in c["esatti"] + c["parziali"]:
            per_addebito.setdefault(_mid(v["m"]), []).append(chiave)
    return per_unita, per_addebito


def _valuta(
    u: Dict[str, Any], c: Optional[Dict[str, List[Dict[str, Any]]]],
    per_addebito: Dict[str, List[str]],
) -> Optional[Dict[str, Any]]:
    """Il livello di un pagamento; ``None`` se non ha nessun candidato."""
    if not c or not (c["esatti"] or c["parziali"]):
        return None

    def unico(v: Dict[str, Any]) -> bool:
        return per_addebito.get(_mid(v["m"])) == [u["chiave"]]

    esatti, parziali = c["esatti"], c["parziali"]
    if esatti:
        if len(esatti) == 1 and unico(esatti[0]):
            v = esatti[0]
            certo = not u.get("incasso_obbligatorio") or v["incasso"] == u["data"]
            return {"livello": LIVELLO_CERTO if certo else LIVELLO_PROBABILE,
                    "scelto": v, "candidati": esatti}
        return {"livello": LIVELLO_PROBABILE, "scelto": None, "candidati": esatti}
    if len(parziali) == 1 and unico(parziali[0]):
        return {"livello": LIVELLO_PARZIALE, "scelto": parziali[0], "candidati": parziali}
    return {"livello": LIVELLO_PARZIALE, "scelto": None, "candidati": parziali}


def _motivo_coppia(
    *, etichetta: str, importo_cents: int, data: str, v: Dict[str, Any], livello: str,
) -> str:
    addebito = _vista_addebito(v["m"])
    testo = (
        f"importo {addebito['importo']:.2f} EUR"
        + (" uguale al centesimo" if not v["diff"] else
           f" contro {importo_cents / 100:.2f} EUR: differenza {v['diff'] / 100:+.2f} EUR "
           f"(soglia {SOGLIA_PARZIALE_CENTS / 100:.2f} EUR)")
        + f"; {etichetta} del {data_italiana(data)}, addebito del {addebito['data_it']} "
        f"({abs(v['giorni'])} gg lavorativi {'dopo' if v['giorni'] >= 0 else 'prima'})"
    )
    if v["incasso"]:
        testo += f"; DATA INCASSO nella causale: {data_italiana(v['incasso'])}"
        if v["m"].get("causale_export_banca_da"):
            testo += f" (export ufficiale della banca, copia {v['m']['causale_export_banca_da']})"
    elif livello != LIVELLO_CERTO:
        testo += "; la causale non riporta la data d'incasso: da verificare"
    return testo


def riscontri_quietanze_banca(
    quietanze: Iterable[Dict[str, Any]], movimenti: Iterable[Dict[str, Any]],
    *, soglia_parziale_cents: int = SOGLIA_PARZIALE_CENTS,
) -> Dict[str, Any]:
    """Calcola, senza scrivere, il riscontro di ogni pagamento con la banca.

    Ogni esito porta ``livello`` e ``motivazione`` (importo, date, causale
    confrontati). Un pagamento o un addebito con piu' candidati resta da
    verificare con l'elenco dei candidati: niente si sceglie a caso.
    """
    pagamenti = pagamenti_da_quietanze(quietanze)
    addebiti = [m for m in movimenti if e_addebito_delega(m) and data_movimento(m)]
    date_banca = sorted(data_movimento(m) for m in addebiti)
    copertura = (date_banca[0], date_banca[-1]) if date_banca else (None, None)

    unita = [{"chiave": p["chiave"], "data": p["data"], "importo_cents": p["importo_cents"],
              "incasso_obbligatorio": True} for p in pagamenti]
    candidati, per_addebito = _abbina(unita, addebiti, soglia_parziale_cents)

    riscontri: List[Dict[str, Any]] = []
    da_verificare: List[Dict[str, Any]] = []
    senza_addebito: List[Dict[str, Any]] = []
    senza_estratto: List[Dict[str, Any]] = []
    incompleti: List[Dict[str, Any]] = []
    compensate: List[Dict[str, Any]] = []
    for p, u in zip(pagamenti, unita):
        if p["data"] and p.get("compensazione_totale"):
            compensate.append({**_vista_pagamento(p), "stato": "COMPENSATA", "motivazione": (
                "saldo zero: tributi pagati interamente con i crediti della stessa delega, "
                "nessun addebito in banca atteso")})
            continue
        if not p["data"] or not p["importo_cents"]:
            incompleti.append({**_vista_pagamento(p), "motivo": (
                "data di pagamento non letta" if not p["data"] else "saldo non letto")})
            continue
        valutazione = _valuta(u, candidati.get(p["chiave"]), per_addebito)
        if valutazione and valutazione["scelto"]:
            v = valutazione["scelto"]
            livello = valutazione["livello"]
            voce = {**_vista_pagamento(p), "livello": livello, "addebito": _vista_addebito(v["m"]),
                    "motivazione": _motivo_coppia(etichetta="quietanza", importo_cents=p["importo_cents"],
                                                  data=p["data"], v=v, livello=livello),
                    "stato": RISCONTRO_CERTO if livello == LIVELLO_CERTO else RISCONTRO_DA_VERIFICARE}
            if livello == LIVELLO_PARZIALE:
                voce["differenza"] = euro(v["diff"])
                voce["motivazione"] += f": {NOTA_COMMERCIALISTA}"
            (riscontri if livello == LIVELLO_CERTO else da_verificare).append(voce)
        elif valutazione:
            da_verificare.append({
                **_vista_pagamento(p), "stato": RISCONTRO_DA_VERIFICARE,
                "livello": valutazione["livello"],
                "candidati": [_vista_addebito(v["m"]) for v in valutazione["candidati"]],
                "motivazione": f"{len(valutazione['candidati'])} addebiti compatibili, oppure un addebito "
                               "conteso da piu' quietanze: scegliere a mano",
            })
        else:
            coperto = bool(copertura[0]) and copertura[0] <= p["data"] and (
                date.fromisoformat(p["data"]) + timedelta(days=GIORNI_COPERTURA_ESTRATTO)
            ).isoformat() <= copertura[1]
            voce = {**_vista_pagamento(p), "livello": LIVELLO_NESSUN_MATCH,
                    "estratto_periodo_presente": coperto}
            if coperto:
                senza_addebito.append({**voce, "motivazione": (
                    "nessun addebito I24 di pari importo (o entro "
                    f"{SOGLIA_PARZIALE_CENTS / 100:.0f} EUR) entro {GIORNI_LAVORATIVI_ADDEBITO} giorni "
                    "lavorativi; estratto del periodo presente: si'. Possibile: pagato da un altro "
                    f"conto o pagamento mai transitato ({NOTA_COMMERCIALISTA})")})
            else:
                senza_estratto.append({**voce, "motivazione": (
                    "estratto conto del periodo assente: non si puo' dire se il pagamento manchi; "
                    "caricare l'estratto del periodo")})

    usati = set(per_addebito)
    addebiti_senza = [
        {**_vista_addebito(m), "livello": LIVELLO_MOVIMENTO_ORFANO, "motivazione": (
            "addebito di delega F24 senza quietanza di pari importo e data: "
            "probabile quietanza da riscaricare dal Cassetto Fiscale")}
        for m in addebiti if _mid(m) not in usati
    ]
    ordina = lambda righe: sorted(righe, key=lambda r: r.get("data") or "", reverse=True)  # noqa: E731
    addebito_di = {v["chiave"]: v["addebito"] for v in riscontri}
    ripetuti = tributi_versati_due_volte(pagamenti, addebito_di)
    return {
        "tributi_ripetuti": ordina(ripetuti),
        "riscontrati": ordina(riscontri),
        "da_verificare": ordina(da_verificare),
        "quietanze_senza_addebito": ordina(senza_addebito),
        "quietanze_senza_estratto": ordina(senza_estratto),
        "addebiti_senza_quietanza": ordina(addebiti_senza),
        "quietanze_incomplete": ordina(incompleti),
        "compensate_saldo_zero": ordina(compensate),
        "copertura_banca": {"dal": copertura[0], "al": copertura[1]},
        "conteggi": {
            "pagamenti": len(pagamenti), "riscontrati": len(riscontri),
            "da_verificare": len(da_verificare), "quietanze_senza_addebito": len(senza_addebito),
            "addebiti_senza_quietanza": len(addebiti_senza),
            "fuori_periodo_estratto": len(senza_estratto), "quietanze_incomplete": len(incompleti),
            "tributi_ripetuti": len(ripetuti), "compensate_saldo_zero": len(compensate),
            "per_livello": {
                LIVELLO_CERTO: len(riscontri),
                LIVELLO_PROBABILE: sum(1 for v in da_verificare if v.get("livello") == LIVELLO_PROBABILE),
                LIVELLO_PARZIALE: sum(1 for v in da_verificare if v.get("livello") == LIVELLO_PARZIALE),
                LIVELLO_NESSUN_MATCH: len(senza_addebito) + len(senza_estratto),
                LIVELLO_MOVIMENTO_ORFANO: len(addebiti_senza),
            },
        },
    }


def riscontri_modelli_banca(
    registro: Dict[str, Any], esito_quietanze: Dict[str, Any],
    *, soglia_parziale_cents: int = SOGLIA_PARZIALE_CENTS,
) -> Dict[str, Any]:
    """Modelli F24 ancora senza prova bancaria ↔ addebiti, con lo stesso motore a livelli.

    Un modello con la sua quietanza e' provato dall'addebito della quietanza
    (catena dovuto → F24 → quietanza → addebito) solo se il saldo del modello
    e' uguale a quell'addebito al centesimo. Un modello senza quietanza si
    confronta con gli addebiti liberi e non gia' reclamati da una quietanza:
    data programmata ±2 giorni lavorativi, importo esatto, causale di delega.
    Due modelli sullo stesso addebito, o due addebiti per lo stesso modello,
    restano da verificare. Niente si scrive qui: solo il livello CERTO, poi.
    """
    modelli = [f for f in registro["f24"] if _f24_aperto_banca(f)]
    certo_di_quietanza: Dict[str, Dict[str, Any]] = {}
    reclamati: Set[str] = set()
    for r in esito_quietanze["riscontrati"]:
        reclamati.add(r["addebito"]["movimento_id"])
        for q in r["quietanze"]:
            certo_di_quietanza[str(q["id"])] = r["addebito"]
    for r in esito_quietanze["da_verificare"]:
        for a in ([r["addebito"]] if r.get("addebito") else []) + list(r.get("candidati") or []):
            reclamati.add(a["movimento_id"])

    per_id_movimento = {_mid(m): m for m in registro["movimenti"]}
    riscontrati: List[Dict[str, Any]] = []
    da_verificare: List[Dict[str, Any]] = []
    senza_quietanza: List[Dict[str, Any]] = []

    def vista(f: Dict[str, Any]) -> Dict[str, Any]:
        dv = data_versamento_modello(f)
        return {"f24_id": str(f.get("id")), "file_name": f.get("file_name"), "data": dv,
                "data_it": data_italiana(dv), "importo": euro(saldo_modello_cents(f))}

    for f in modelli:
        fid = str(f.get("id"))
        quietanze = registro["quietanze_per_f24"].get(fid, [])
        if not quietanze and not f.get("quietanza_id"):
            senza_quietanza.append(f)
            continue
        saldo = saldo_modello_cents(f)
        for q in quietanze:
            a = certo_di_quietanza.get(str(q.get("id")))
            if a and saldo is not None and centesimi(a["importo"]) == saldo:
                m = per_id_movimento.get(a["movimento_id"]) or {}
                riscontrati.append({
                    **vista(f), "livello": LIVELLO_CERTO, "criterio": "via_quietanza",
                    "movimento_id": a["movimento_id"], "addebito": a, "data_movimento": a["data"],
                    "riferimento": (m.get("f24_info") or {}).get("riferimento"),
                    "motivazione": (
                        f"quietanza {q.get('protocollo_originale') or q.get('id')} riscontrata con l'addebito "
                        f"del {a['data_it']} di {a['importo']:.2f} EUR, uguale al saldo del modello"),
                })
                break

    liberi = [m for m in registro["movimenti"]
              if _movimento_libero(m) and e_addebito_delega(m) and data_movimento(m)
              and _mid(m) not in reclamati]
    unita = [{"chiave": str(f.get("id")), "data": data_versamento_modello(f),
              "importo_cents": saldo_modello_cents(f), "bidirezionale": True} for f in senza_quietanza]
    candidati, per_addebito = _abbina(unita, liberi, soglia_parziale_cents)
    for f, u in zip(senza_quietanza, unita):
        valutazione = _valuta(u, candidati.get(u["chiave"]), per_addebito)
        if not valutazione:
            continue
        v, livello = valutazione["scelto"], valutazione["livello"]
        if v:
            voce = {**vista(f), "livello": livello, "movimento_id": _mid(v["m"]),
                    "addebito": _vista_addebito(v["m"]), "data_movimento": data_movimento(v["m"]),
                    "riferimento": (v["m"].get("f24_info") or {}).get("riferimento"),
                    "criterio": "importo_data_causale",
                    "motivazione": _motivo_coppia(etichetta="modello", importo_cents=u["importo_cents"],
                                                  data=u["data"], v=v, livello=livello)}
            if livello == LIVELLO_PARZIALE:
                voce["differenza"] = euro(v["diff"])
                voce["motivazione"] += f": {NOTA_COMMERCIALISTA}"
            (riscontrati if livello == LIVELLO_CERTO else da_verificare).append(voce)
        else:
            da_verificare.append({
                **vista(f), "livello": livello,
                "candidati": [_vista_addebito(c["m"]) for c in valutazione["candidati"]],
                "motivazione": f"{len(valutazione['candidati'])} addebiti compatibili, oppure un addebito "
                               "conteso da piu' modelli: scegliere a mano"})

    # Due modelli certi sullo stesso addebito non si scelgono: entrambi da verificare.
    per_movimento: Dict[str, List[Dict[str, Any]]] = {}
    for r in riscontrati:
        per_movimento.setdefault(r["movimento_id"], []).append(r)
    contesi = {mid for mid, voci in per_movimento.items() if len(voci) > 1}
    if contesi:
        for r in [r for r in riscontrati if r["movimento_id"] in contesi]:
            riscontrati.remove(r)
            da_verificare.append({**r, "livello": LIVELLO_PROBABILE, "motivazione": (
                "stesso addebito e stesso saldo in piu' modelli F24: scegliere a mano")})
    return {
        "riscontrati": riscontrati, "da_verificare": da_verificare,
        "conteggi": {"modelli_aperti": len(modelli), "riscontrati": len(riscontrati),
                     "da_verificare": len(da_verificare)},
    }


def tributi_versati_due_volte(
    pagamenti: Iterable[Dict[str, Any]], addebito_di: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """La stessa riga a debito (sezione, codice, periodo, importo al centesimo) in
    due deleghe diverse versate lo stesso giorno.

    Le rate (RC01 mensile, avvisi rateizzati) ripetono la stessa riga in giorni
    diversi e restano fuori; due copie della stessa quietanza sono gia' un
    pagamento solo. Il 16/06/2026 l'IMU 3918 da 3.574,00 EUR e il credito 6099
    da 1.604,90 EUR erano in una delega programmata il 02/06 e in una inviata il
    giorno stesso, entrambe addebitate. Si dichiara il fatto, non si decide.
    """
    addebito_di = addebito_di or {}
    per_riga: Dict[Tuple, set] = {}
    per_chiave = {}
    for p in pagamenti:
        if not p.get("data"):
            continue
        per_chiave[p["chiave"]] = p
        for r in p.get("_righe") or []:
            if r.get("importo_debito_cents"):
                k = (p["data"], r.get("sezione"), r.get("codice"), r.get("anno"), r.get("mese"),
                     r["importo_debito_cents"])
                per_riga.setdefault(k, set()).add(p["chiave"])
    gruppi: Dict[Tuple[str, ...], List[Tuple]] = {}
    for k, chiavi in per_riga.items():
        if len(chiavi) > 1:
            gruppi.setdefault(tuple(sorted(chiavi)), []).append(k)
    esito = []
    for chiavi, righe in gruppi.items():
        coinvolti = [per_chiave[c] for c in chiavi]
        viste = []
        for p in coinvolti:
            v = _vista_pagamento(p)
            v["addebito"] = addebito_di.get(p["chiave"])
            viste.append(v)
        descr = ", ".join(
            f"{codice} {_periodo(anno, mese)} {cents / 100:.2f}"
            for _data, _sez, codice, anno, mese, cents in sorted(righe, key=str)
        )
        invii = ", ".join(
            f"inviata il {v['inviato_il_it'] or '?'}"
            + (f", addebitata il {v['addebito']['data_it']}" if v.get("addebito") else ", addebito non trovato")
            for v in viste
        )
        esito.append({
            "chiave": "||".join(chiavi),
            "data": coinvolti[0]["data"],
            "data_it": data_italiana(coinvolti[0]["data"]),
            "righe": descr,
            "pagamenti": viste,
            "motivazione": (
                f"stesse righe ({descr}) in {len(viste)} deleghe versate il "
                f"{data_italiana(coinvolti[0]['data'])} ({invii}): da verificare col commercialista"
            ),
        })
    return esito


def _periodo(anno: Any, mese: Any) -> str:
    if anno and mese:
        return f"{int(mese):02d}/{anno}"
    return str(anno or "")


ALERT_QUIETANZA_SENZA_ADDEBITO = "F24_QUIETANZA_SENZA_ADDEBITO"
ALERT_ADDEBITO_SENZA_QUIETANZA = "BNK_F24_SENZA_QUIETANZA"
ALERT_TRIBUTO_DUE_VOLTE = "F24_TRIBUTO_VERSATO_DUE_VOLTE"


async def applica_riscontri_quietanze(
    db, esito: Dict[str, Any], *, con_alert: bool = True,
) -> Dict[str, int]:
    """Scrive i riscontri certi su quietanze e addebito; apre e chiude gli alert.

    Idempotente: un riscontro gia' scritto uguale non si riscrive. Il
    movimento non diventa «riconciliato»: e' spiegato dalla quietanza, ma il
    modello F24 (se manca) resta da caricare.
    """
    from app.services.alert_engine import genera_alert, risolvi_alert

    now = datetime.now(timezone.utc).isoformat()
    scritti = {"quietanze": 0, "addebiti": 0, "relazioni": 0, "alert_aperti": 0, "alert_chiusi": 0}
    for r in esito["riscontrati"]:
        a = r["addebito"]
        riscontro = {
            "stato": RISCONTRO_CERTO, "livello": r["livello"], "movimento_id": a["movimento_id"], "data_addebito": a["data"],
            "importo": a["importo"], "data_incasso": a["data_incasso"], "motivazione": r["motivazione"],
        }
        for q in r["quietanze"]:
            collezione = q.get("fonte") or COLL_QUIETANZE_F24
            attuale = await db[collezione].find_one({"id": q["id"]}, {"_id": 0, "riscontro_banca": 1})
            vecchio = {k: v for k, v in ((attuale or {}).get("riscontro_banca") or {}).items()
                       if k != "verificato_il"}
            if vecchio != riscontro:
                await db[collezione].update_one({"id": q["id"]}, {"$set": {
                    "riscontro_banca": {**riscontro, "verificato_il": now},
                    "movimento_bancario_id": a["movimento_id"],
                }})
                scritti["quietanze"] += 1
            scritti["relazioni"] += await _scrivi_relazione(
                db, movimento_id=a["movimento_id"], tipo_target="f24_receipt", target_id=str(q["id"]),
                status="confirmed", rule=f"f24_banca:{r['livello']}",
                importo_cents=centesimi(a["importo"]), collezione_target=collezione)
            scritti["relazioni"] += await _revoca_candidate_altrove(
                db, "f24_receipt", str(q["id"]), a["movimento_id"])
        ids = sorted(str(q["id"]) for q in r["quietanze"] if q.get("id"))
        risultato = await db[COLL_ESTRATTO_CONTO].update_one(
            {"$or": [{"id": a["movimento_id"]}, {"fingerprint": a["movimento_id"]}],
             "quietanze_f24_ids": {"$ne": ids}},
            {"$set": {"quietanze_f24_ids": ids, "quietanza_f24_protocollo": r["protocollo"],
                      "quietanza_f24_riscontro": RISCONTRO_CERTO}},
        )
        scritti["addebiti"] += int(getattr(risultato, "modified_count", 0) or 0)
        if con_alert:
            scritti["alert_chiusi"] += await risolvi_alert(ALERT_ADDEBITO_SENZA_QUIETANZA, a["movimento_id"], db)
            scritti["alert_chiusi"] += await risolvi_alert(ALERT_QUIETANZA_SENZA_ADDEBITO, r["chiave"], db)
    for r in esito["da_verificare"]:
        for a in ([r["addebito"]] if r.get("addebito") else list(r.get("candidati") or [])):
            for q in r["quietanze"]:
                scritti["relazioni"] += await _scrivi_relazione(
                    db, movimento_id=a["movimento_id"], tipo_target="f24_receipt",
                    target_id=str(q["id"]), status="pending", rule=f"f24_banca:{r['livello']}",
                    importo_cents=centesimi(a["importo"]),
                    collezione_target=q.get("fonte") or COLL_QUIETANZE_F24)
    if not con_alert:
        return scritti

    for q in esito["quietanze_senza_addebito"]:
        creato = await genera_alert(
            ALERT_QUIETANZA_SENZA_ADDEBITO, q["chiave"], COLL_QUIETANZE_F24,
            f"Quietanza F24 del {q['data_it']} ({q['importo']:.2f} EUR, protocollo "
            f"{q['protocollo'] or '-'}): {q['motivazione']}", db,
            extra={"record": [q]},
        )
        scritti["alert_aperti"] += int(bool(creato))
    for t in esito.get("tributi_ripetuti") or []:
        creato = await genera_alert(
            ALERT_TRIBUTO_DUE_VOLTE, t["chiave"], COLL_QUIETANZE_F24,
            f"F24 del {t['data_it']}: {t['motivazione']}", db,
            extra={"record": t["pagamenti"]},
        )
        scritti["alert_aperti"] += int(bool(creato))
    for m in esito["addebiti_senza_quietanza"]:
        creato = await genera_alert(
            ALERT_ADDEBITO_SENZA_QUIETANZA, m["movimento_id"], COLL_ESTRATTO_CONTO,
            f"Addebito del {m['data_it']} ({m['importo']:.2f} EUR): {m['motivazione']}", db,
            extra={"record": [m]},
        )
        scritti["alert_aperti"] += int(bool(creato))
    return scritti


async def _scrivi_relazione(
    db, *, movimento_id: str, tipo_target: str, target_id: str, status: str, rule: str,
    importo_cents: Optional[int], collezione_target: str,
) -> int:
    """Relazione movimento → pagamento in ``entity_relations``; 1 solo se e' cambiata."""
    from app.db_collections import COLL_ENTITY_RELATIONS
    from app.services.entity_relations import relation_key, upsert_entity_relation

    tipo_relazione = "settles_f24_receipt" if tipo_target == "f24_receipt" else "settles_f24_model"
    chiave = relation_key("bank_movement", movimento_id, tipo_relazione, tipo_target, target_id)
    attuale = await getattr(db, COLL_ENTITY_RELATIONS).find_one(
        {"relation_key": chiave}, {"_id": 0, "status": 1, "rule": 1})
    if attuale and attuale.get("status") == status and attuale.get("rule") == rule:
        return 0
    await upsert_entity_relation(
        db, source_type="bank_movement", source_id=movimento_id, relation_type=tipo_relazione,
        target_type=tipo_target, target_id=target_id, status=status, rule=rule,
        evidence=[{"type": "bank_movement_id", "value": movimento_id},
                  {"type": "livello", "value": rule.split(":")[-1]}],
        amount=euro(importo_cents) if importo_cents is not None else None,
        provenance={"source_collection": COLL_ESTRATTO_CONTO, "target_collection": collezione_target},
    )
    return 1


async def _revoca_candidate_altrove(db, tipo_target: str, target_id: str, movimento_id: str) -> int:
    """Un pagamento diventato certo ritira le candidature verso altri addebiti."""
    from app.db_collections import COLL_ENTITY_RELATIONS
    from app.services.entity_relations import revoke_entity_relation

    tipo_relazione = "settles_f24_receipt" if tipo_target == "f24_receipt" else "settles_f24_model"
    aperte = await getattr(db, COLL_ENTITY_RELATIONS).find(
        {"target.type": tipo_target, "target.id": target_id, "status": "pending",
         "relation_type": tipo_relazione}, {"_id": 0, "source": 1}).to_list(50)
    ritirate = 0
    for r in aperte:
        altro = str((r.get("source") or {}).get("id") or "")
        if altro and altro != movimento_id:
            ritirate += int(await revoke_entity_relation(
                db, source_type="bank_movement", source_id=altro, relation_type=tipo_relazione,
                target_type=tipo_target, target_id=target_id))
    return ritirate


async def applica_riscontri_modelli(db, esito: Dict[str, Any]) -> Dict[str, int]:
    """Scrive la prova bancaria dei soli modelli CERTI; gli altri livelli sono relazioni pending."""
    from app.services.accounting_relation_writers import record_f24_bank_allocations
    from app.services.alert_engine import chiudi_alert_movimento_riconciliato

    now = datetime.now(timezone.utc).isoformat()
    scritti = {"modelli": 0, "relazioni": 0}
    for r in esito["riscontrati"]:
        f24 = await db[COLL_F24].find_one({"id": r["f24_id"]}, {"_id": 0, "pdf_data": 0})
        if not f24 or not _f24_aperto_banca(f24):
            continue
        patch = {
            **patch_pagamento_banca(
                movimento_id=r["movimento_id"], data_pagamento=r["data_movimento"],
                riferimento=r.get("riferimento")),
            "importo_residuo": 0.0, "criterio_aggancio_banca": r["criterio"], "updated_at": now,
        }
        await db[COLL_F24].update_one({"id": r["f24_id"]}, {"$set": patch})
        await db[COLL_ESTRATTO_CONTO].update_one(
            {"$or": [{"id": r["movimento_id"]}, {"fingerprint": r["movimento_id"]}]},
            {"$set": {"riconciliato": True, "tipo_riconciliazione": "f24_tributi",
                      "f24_ids": [r["f24_id"]], "data_riconciliazione": now}},
        )
        try:
            await record_f24_bank_allocations(db, f24={**f24, **patch}, allocations=[{
                "movimento_id": r["movimento_id"], "importo": r["importo"], "codici_tributo": [],
            }])
            await chiudi_alert_movimento_riconciliato(db, r["movimento_id"], "f24")
        except Exception as exc:  # noqa: BLE001 - la relazione e' un indice, non la prova
            logger.exception("Relazione bancaria F24 %s non registrata (%s)", r["f24_id"],
                             type(exc).__name__)
        scritti["modelli"] += 1
    for r in esito["da_verificare"]:
        for mid in ([r["movimento_id"]] if r.get("movimento_id") else
                    [c["movimento_id"] for c in r.get("candidati") or []]):
            scritti["relazioni"] += await _scrivi_relazione(
                db, movimento_id=mid, tipo_target="f24_model", target_id=r["f24_id"],
                status="pending", rule=f"f24_banca:{r['livello']}",
                importo_cents=centesimi(r.get("importo")), collezione_target=COLL_F24)
    return scritti


async def riconcilia_f24_banca(
    db, *, dry_run: bool = False, soglia_parziale_cents: int = SOGLIA_PARZIALE_CENTS,
) -> Dict[str, Any]:
    """L'unico motore F24 ↔ banca: registro letto una volta, livelli, scritture certe, alert.

    Idempotente: dopo un giro completo il successivo scrive 0 righe.
    """
    registro = await carica_registro(db)
    await causali_export_banca(db, registro["movimenti"])
    esito = riscontri_quietanze_banca(
        registro["quietanze"], registro["movimenti"], soglia_parziale_cents=soglia_parziale_cents)
    esito["modelli"] = riscontri_modelli_banca(
        registro, esito, soglia_parziale_cents=soglia_parziale_cents)
    if dry_run:
        return {"dry_run": True, **esito}
    scritti = await applica_riscontri_quietanze(db, esito)
    scritti["modelli"] = await applica_riscontri_modelli(db, esito["modelli"])
    return {"dry_run": False, **esito, "scritti": scritti}


async def riconcilia_f24_arrivato(db, importo: Any) -> Dict[str, Any]:
    """All'arrivo di una quietanza o di un modello: solo pagamenti e addebiti di pari importo.

    Il confronto chiede l'importo uguale al centesimo (o entro la soglia del
    livello PARZIALE, che qui non scrive), quindi il sottoinsieme con lo stesso
    importo da' lo stesso esito certo del giro completo senza rileggere l'intero
    registro a ogni file del lotto. Gli alert li apre solo il giro dei 30 minuti,
    che conosce la copertura dell'estratto conto.
    """
    cents = centesimi(importo)
    if not cents:
        try:
            zero = importo is not None and Decimal(str(importo).replace(",", ".")) == 0
        except (InvalidOperation, ValueError):
            zero = False
        if zero:
            return {"saltato": "saldo zero: pagato in compensazione, nessun addebito atteso"}
        return {"saltato": "saldo non letto"}
    valore = euro(abs(cents))
    quietanze = await db[COLL_QUIETANZE_F24].find(
        {"$or": [{"saldo": valore}, {"saldo": str(valore)}, {"totali.saldo_netto": valore}]},
        {"_id": 0, "pdf_data": 0},
    ).to_list(200)
    movimenti = await db[COLL_ESTRATTO_CONTO].find(
        {"importo": {"$in": [valore, -valore]}}, {"_id": 0},
    ).to_list(200)
    movimenti = [m for m in movimenti if m.get("entity_status") != "deleted"
                 and str(m.get("tipo") or "uscita").lower() != "entrata"]
    await causali_export_banca(db, movimenti)
    quietanze_norm = [_quietanza_legacy(q) for q in quietanze if q.get("entity_status") != "deleted"]
    esito = riscontri_quietanze_banca(quietanze_norm, movimenti)
    scritti = await applica_riscontri_quietanze(db, esito, con_alert=False)
    modelli = [f for f in await db[COLL_F24].find(
        {"status": {"$ne": "eliminato"}}, {"_id": 0, "pdf_data": 0}).to_list(5000)
        if f.get("entity_status") != "deleted" and saldo_modello_cents(f) == abs(cents)]
    registro = {"f24": modelli, "movimenti": movimenti,
                "quietanze_per_f24": {str(f.get("id")): [q for q in quietanze_norm
                                                         if str(f.get("id")) in q["f24_ids"]]
                                      for f in modelli}}
    esito_modelli = riscontri_modelli_banca(registro, esito)
    scritti["modelli"] = await applica_riscontri_modelli(db, esito_modelli)
    return {**esito["conteggi"], "modelli": esito_modelli["conteggi"], "scritti": scritti}
