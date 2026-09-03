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
``verifica_codice`` non scrivono mai; ``riconcilia_addebiti`` scrive solo con
``dry_run=False`` ed e' idempotente.
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
from app.engines import tributi_engine as te
from app.services.conti_pos import data_italiana
from app.services.f24_payment_evidence import (
    patch_pagamento_banca, patch_quietanza_associata, stato_evidenza_pagamento,
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
    ``periodo_riferimento`` ('MM/AAAA'), poi solo anno."""
    mese_raw, anno_raw = riga.get("mese"), riga.get("anno")
    if anno_raw and str(anno_raw).strip().isdigit():
        anno = int(str(anno_raw).strip())
        mese = int(str(mese_raw).strip()) if mese_raw and str(mese_raw).strip().isdigit() else 0
        return {"mese": mese if 1 <= mese <= 12 else None, "anno": anno}
    testo = riga.get("periodo_riferimento") or riga.get("periodo") or ""
    parsed = te._parse_periodo(testo)
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
    }


def _quietanza_legacy(doc: Dict[str, Any]) -> Dict[str, Any]:
    dg = doc.get("dati_generali") or {}
    protocollo = doc.get("protocollo_telematico") or dg.get("protocollo_telematico") or doc.get("protocollo")
    importo = centesimi(
        doc.get("saldo_delega") or doc.get("saldo") or (doc.get("totali") or {}).get("saldo_netto")
    )
    return {
        "id": doc.get("id"),
        "fonte": COLL_QUIETANZE_F24,
        "filename": doc.get("file_name") or doc.get("filename") or "",
        "data": _data_iso(doc.get("data_pagamento") or dg.get("data_pagamento") or dg.get("data_versamento")),
        "protocollo": re.sub(r"[^0-9A-Z]", "", str(protocollo).upper()) if protocollo else None,
        "protocollo_originale": protocollo,
        "importo_cents": importo,
        "f24_ids": sorted({str(v) for v in (doc.get("f24_associati") or []) if v}),
        "righe": righe_modello(doc),
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
    return {
        "codice_tributo": codice,
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


def proposte_aggancio(registro: Dict[str, Any]) -> Dict[str, Any]:
    """Calcola, senza scrivere, gli agganci univoci e i casi ambigui.

    Banca ↔ F24: |data movimento − data versamento| ≤ 3 gg e importo esatto
    al centesimo, univoco in entrambe le direzioni (e nessun duplicato
    bancario con stessa data/importo). Quietanza ↔ F24: protocollo uguale,
    oppure stessa data di versamento e importo esatto. Mai per solo importo.
    """
    modelli = registro["f24"]
    aperti = [f for f in modelli if _f24_aperto_banca(f)]
    liberi = [m for m in registro["movimenti"] if _movimento_libero(m)]

    firme: Dict[Tuple[str, int], List[str]] = {}
    for m in liberi:
        firme.setdefault((data_movimento(m) or "", importo_movimento_cents(m) or -1), []).append(
            str(m.get("id") or m.get("fingerprint"))
        )
    duplicati = {mid for ids in firme.values() if len(ids) > 1 for mid in ids}

    cand_per_f24: Dict[str, List[Dict[str, Any]]] = {}
    cand_per_mov: Dict[str, List[str]] = {}
    for f in aperti:
        fid = str(f.get("id"))
        dv, saldo = data_versamento_modello(f), saldo_modello_cents(f)
        if not dv or saldo is None:
            continue
        for m in liberi:
            mid = str(m.get("id") or m.get("fingerprint"))
            gg = _giorni_tra(dv, data_movimento(m))
            imp = importo_movimento_cents(m)
            if gg is None or gg > TOLLERANZA_AGGANCIO_GG or imp is None:
                continue
            if abs(imp - saldo) <= TOLLERANZA_AGGANCIO_CENTS:
                cand_per_f24.setdefault(fid, []).append(m)
                cand_per_mov.setdefault(mid, []).append(fid)

    banca_proposte, banca_ambigue = [], []
    for f in aperti:
        fid = str(f.get("id"))
        cands = cand_per_f24.get(fid, [])
        if not cands:
            continue
        voci = [{
            "movimento_id": str(m.get("id") or m.get("fingerprint")),
            "data_movimento": data_movimento(m), "data_movimento_it": data_italiana(data_movimento(m)),
            "importo": euro(importo_movimento_cents(m)), "descrizione": m.get("descrizione"),
        } for m in cands]
        record = {
            "f24_id": fid, "file_name": f.get("file_name"),
            "data_versamento": data_versamento_modello(f),
            "data_versamento_it": data_italiana(data_versamento_modello(f)),
            "importo": euro(saldo_modello_cents(f)), "candidati": voci,
        }
        mid = voci[0]["movimento_id"]
        univoco = len(cands) == 1 and mid not in duplicati and cand_per_mov.get(mid, []) == [fid]
        if univoco:
            banca_proposte.append({**record, "movimento_id": mid, "movimento": cands[0],
                                   "criterio": "data_±3gg_e_importo_esatto"})
        else:
            banca_ambigue.append({**record, "motivo": (
                "movimento con duplicato bancario (stessa data e importo)" if mid in duplicati
                else "piu' candidati: scelta manuale"
            )})

    # Quietanze ↔ F24
    con_quietanza = {str(f.get("quietanza_id")) for f in modelli if f.get("quietanza_id")}
    quiet_proposte, quiet_ambigue, quiet_senza_modello = [], [], []
    for q in registro["quietanze"]:
        if q["f24_ids"] or str(q.get("id")) in con_quietanza:
            continue
        cands = []
        for f in modelli:
            if f.get("quietanza_id"):
                continue
            per_prot = bool(q["protocollo"]) and q["protocollo"] in protocolli_modello(f)
            saldo = saldo_modello_cents(f)
            per_data_imp = (
                bool(q["data"]) and q["data"] == data_versamento_modello(f)
                and q["importo_cents"] is not None and saldo is not None
                and abs(q["importo_cents"] - saldo) <= TOLLERANZA_AGGANCIO_CENTS
            )
            if per_prot or per_data_imp:
                cands.append((f, "protocollo" if per_prot else "data_e_importo_esatto"))
        vista = _vista_quietanza(q, False)
        if len(cands) == 1:
            f, criterio = cands[0]
            quiet_proposte.append({**vista, "f24_id": f.get("id"), "file_name": f.get("file_name"),
                                   "criterio": criterio})
        elif cands:
            quiet_ambigue.append({**vista, "candidati": [
                {"f24_id": f.get("id"), "file_name": f.get("file_name"), "criterio": c} for f, c in cands
            ]})
        else:
            quiet_senza_modello.append({**vista, "motivo": (
                "quietanza senza importo/protocollo confrontabile" if q["importo_cents"] is None and not q["protocollo"]
                else "nessun modello F24 con lo stesso protocollo o stessa data+importo"
            )})

    con_candidato = set(cand_per_mov)
    addebiti_senza_modello = [{
        "movimento_id": str(m.get("id") or m.get("fingerprint")),
        "data": data_movimento(m), "data_it": data_italiana(data_movimento(m)),
        "importo": euro(importo_movimento_cents(m)), "descrizione": m.get("descrizione"),
        "alert": "F24_MANCANTE",
    } for m in liberi if str(m.get("id") or m.get("fingerprint")) not in con_candidato]

    return {
        "banca": {"proposte": banca_proposte, "ambigue": banca_ambigue},
        "quietanze": {"proposte": quiet_proposte, "ambigue": quiet_ambigue,
                      "senza_modello": quiet_senza_modello},
        "addebiti_senza_modello": addebiti_senza_modello,
        "conteggi": {
            **registro["conteggi"],
            "f24_senza_prova_bancaria": len(aperti),
            "movimenti_liberi": len(liberi),
            "banca_proposte": len(banca_proposte), "banca_ambigue": len(banca_ambigue),
            "quietanze_proposte": len(quiet_proposte), "quietanze_ambigue": len(quiet_ambigue),
            "quietanze_senza_modello": len(quiet_senza_modello),
            "addebiti_senza_modello": len(addebiti_senza_modello),
            "importo_addebiti_senza_modello": euro(sum(
                importo_movimento_cents(m) or 0 for m in liberi
                if str(m.get("id") or m.get("fingerprint")) not in con_candidato
            )),
        },
    }


async def riconcilia_addebiti(db, *, dry_run: bool = True) -> Dict[str, Any]:
    """Aggancio idempotente addebito I24 ↔ F24 e quietanza ↔ F24.

    ``dry_run=True`` (default) restituisce le proposte senza scrivere.
    Con ``dry_run=False`` applica SOLO le proposte univoche; al giro
    successivo quei modelli/movimenti non sono piu' liberi → 0 scritture.
    """
    registro = await carica_registro(db)
    piano = proposte_aggancio(registro)
    applicate = {"banca": 0, "quietanze": 0}
    if dry_run:
        return {"dry_run": True, **piano, "applicate": applicate}

    now = datetime.now(timezone.utc).isoformat()
    modelli_per_id = {str(f.get("id")): f for f in registro["f24"]}
    for p in piano["banca"]["proposte"]:
        f24 = modelli_per_id[p["f24_id"]]
        movimento = p["movimento"]
        patch_banca = {
            **patch_pagamento_banca(
                movimento_id=p["movimento_id"], data_pagamento=data_movimento(movimento),
                riferimento=(movimento.get("f24_info") or {}).get("riferimento"),
            ),
            "importo_residuo": 0.0,
            "criterio_aggancio_banca": p["criterio"],
            "updated_at": now,
        }
        await db[COLL_F24].update_one({"id": p["f24_id"]}, {"$set": patch_banca})
        f24.update(patch_banca)  # la quietanza (sotto) non deve declassare questa prova
        await db[COLL_ESTRATTO_CONTO].update_one(
            {"$or": [{"id": p["movimento_id"]}, {"fingerprint": p["movimento_id"]}]},
            {"$set": {"riconciliato": True, "tipo_riconciliazione": "f24_tributi",
                      "f24_ids": [p["f24_id"]], "data_riconciliazione": now}},
        )
        try:
            from app.services.accounting_relation_writers import record_f24_bank_allocations
            await record_f24_bank_allocations(db, f24=f24, allocations=[{
                "movimento_id": p["movimento_id"], "importo": p["importo"], "codici_tributo": [],
            }])
        except Exception:  # noqa: BLE001 - la relazione e' un indice, non la prova
            logger.exception("Relazione bancaria F24 %s non registrata", p["f24_id"])
        applicate["banca"] += 1

    for p in piano["quietanze"]["proposte"]:
        f24 = modelli_per_id[str(p["f24_id"])]
        patch = patch_quietanza_associata(
            quietanza_id=str(p["quietanza_id"]), protocollo=p.get("protocollo") or "",
            data_quietanza=p.get("data"),
        )
        if stato_evidenza_pagamento(f24)["verificato_banca"]:
            # La quietanza non declassa una prova bancaria gia' presente.
            for chiave in ("status", "stato_pagamento", "pagato", "pagamento_verificato_banca"):
                patch.pop(chiave, None)
        await db[COLL_F24].update_one({"id": p["f24_id"]}, {"$set": {
            **patch, "quietanza_fonte": p["fonte"], "criterio_aggancio_quietanza": p["criterio"],
            "updated_at": now,
        }})
        await db[p["fonte"]].update_one(
            {"id": p["quietanza_id"]},
            {"$set": {"f24_id": p["f24_id"], "f24_associati": [p["f24_id"]], "updated_at": now}},
        )
        applicate["quietanze"] += 1

    return {"dry_run": False, **piano, "applicate": applicate}
