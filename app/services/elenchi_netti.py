"""«Elenco netti» del consulente del lavoro: cosa va pagato ai dipendenti per il mese.

E' la stampa delle paghe (Paghe Infinity) con, per ogni dipendente, l'importo netto da bonificare, diviso
per ripartizione (tipo di pagamento: contanti/assegno, accredito su conto, gruppo di addebito). Come il
prospetto contabile per i tributi, e' il fatto che dice **cosa ci si aspetta**; la prova resta il bonifico
in banca. Non scrive in Prima Nota, nel giornale ne' sui cedolini.

Regole:

* si legge solo cio' che e' stampato; ogni ripartizione deve quadrare (somma delle righe = totale di
  ripartizione, numero di righe = «Nr dipendenti»), altrimenti non si deposita;
* identita' del dipendente: il codice dipendente dello studio (`cod_dip`) e il nome stampato, mai associati
  a una persona dell'anagrafica per solo nome qui (lo fara' il motore bonifici/stipendi con il codice fiscale);
* l'IBAN, se stampato, si conserva per intero (e' il dato della disposizione) ma l'interfaccia lo maschera;
* idempotente per SHA-256; una stampa piu' recente dello stesso mese sostituisce la precedente (resta,
  `superato`), mai cancellata.
"""
from __future__ import annotations

import hashlib
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

TIPO = "elenco_netti"
COLL_ELENCHI_NETTI = "elenchi_netti"
CANONICA = "canonica"
SUPERATO = "superato"

_MESI = {
    "GENNAIO": 1, "FEBBRAIO": 2, "MARZO": 3, "APRILE": 4, "MAGGIO": 5, "GIUGNO": 6,
    "LUGLIO": 7, "AGOSTO": 8, "SETTEMBRE": 9, "OTTOBRE": 10, "NOVEMBRE": 11, "DICEMBRE": 12,
}
_IMPORTO = r"\d{1,3}(?:\.\d{3})*,\d{2}"
_RE_PERIODO = re.compile(r"PERIODO\s+DI\s+ELABORAZIONE:?\s*([A-Z]+)\s+(\d{4})", re.I)
_RE_AZIENDA = re.compile(r"AZIENDA:?\s*(\d{6})\s+(\S.*?)\s*$", re.I | re.M)
_RE_PAGINA = re.compile(r"^\[PAGINA\s+\d+\]\s*$", re.M)
_RE_PAGAMENTO = re.compile(r"COD\s+TIPO\s+PAGAMENTO:\s*(.*?)\s*;\s*COD\s+GRUPPO\s+ADDEBITO:\s*(.*?)\s*;", re.I)
_RE_RIGA = re.compile(
    rf"^\s*(\d{{7}})\s+(\S.*?)\s+({_IMPORTO})(?:\s+(IT\d{{2}}[A-Z0-9]{{23}})(?:\s+(\d{{5}}\s+\d{{5}}))?\s*(.*))?$", re.M)
# «Totale di ripartizione» compare a volte duplicato nel livello testo del PDF («…ripartizioneTotale di ripartizione»).
_RE_TOTALE = re.compile(rf"TOTALE\s+DI\s+RIPARTIZIONE(?:TOTALE\s+DI\s+RIPARTIZIONE)?\s*({_IMPORTO})\s+NR\s+DIPENDENTI\s+(\d+)", re.I)
_RE_AZIENDALE = re.compile(rf"TOTALE\s+AZIENDALE\s*({_IMPORTO})\s+NR\s+DIPENDENTI\s+(\d+)", re.I)


def riconosci(testo: str) -> bool:
    """Dal contenuto: titolo «Elenco netti», periodo di elaborazione e almeno un totale di ripartizione."""
    t = re.sub(r"\s+", " ", (testo or "").upper())
    return ("ELENCO NETTI" in t and "PERIODO DI ELABORAZIONE" in t and "TOTALE DI RIPARTIZIONE" in t
            and "NR DIPENDENTI" in t)


def _cents(valore: str) -> int:
    return int(valore.replace(".", "").replace(",", ""))


def leggi_elenco(testo: str) -> Dict[str, Any]:
    """L'elenco come dati. Cio' che non si legge o non quadra va in ``mancanti``."""
    periodo = _RE_PERIODO.search(testo)
    azienda = _RE_AZIENDA.search(testo)
    mese = _MESI.get(periodo.group(1).upper()) if periodo else None
    anno = int(periodo.group(2)) if periodo else None
    ripartizioni: List[Dict[str, Any]] = []
    mancanti: List[str] = []
    pagine = [p for p in _RE_PAGINA.split(testo) if p.strip()] or [testo]
    for pagina in pagine:
        totali = _RE_TOTALE.findall(pagina)
        if not totali:
            continue
        pagamento = _RE_PAGAMENTO.search(pagina)
        righe = []
        for m in _RE_RIGA.finditer(pagina):
            righe.append({
                "cod_dip": m.group(1), "nome": re.sub(r"\s+", " ", m.group(2)).strip(),
                "importo_cents": _cents(m.group(3)), "iban": m.group(4),
                "banca": re.sub(r"\s+", " ", f"{m.group(5) or ''} {m.group(6) or ''}").strip() or None,
            })
        totale_cents, n = _cents(totali[-1][0]), int(totali[-1][1])
        quadra = sum(r["importo_cents"] for r in righe) == totale_cents and len(righe) == n
        ripartizioni.append({
            "tipo_pagamento": (pagamento.group(1).strip() if pagamento else "") or None,
            "gruppo_addebito": (pagamento.group(2).strip() if pagamento else "") or None,
            "righe": righe, "totale_cents": totale_cents, "numero_dipendenti": n, "quadra": quadra,
        })
        if not quadra:
            mancanti.append(f"quadratura_ripartizione_{len(ripartizioni)}")
    # Il totale aziendale (ultima pagina) e' la prova che nessuna ripartizione manca.
    aziendale = _RE_AZIENDALE.search(testo)
    if aziendale and ripartizioni and (
            _cents(aziendale.group(1)) != sum(r["totale_cents"] for r in ripartizioni)
            or int(aziendale.group(2)) != sum(len(r["righe"]) for r in ripartizioni)):
        mancanti.append("totale_aziendale")
    if not periodo or not mese:
        mancanti.append("periodo")
    if not azienda:
        mancanti.append("ditta")
    if not ripartizioni:
        mancanti.append("ripartizioni")
    return {
        "ditta": azienda.group(2).strip() if azienda else None,
        "codice_ditta": azienda.group(1) if azienda else None,
        "mese": mese, "anno": anno, "ripartizioni": ripartizioni,
        "totale_cents": sum(r["totale_cents"] for r in ripartizioni),
        "numero_righe": sum(len(r["righe"]) for r in ripartizioni),
        "totale_aziendale_cents": _cents(aziendale.group(1)) if aziendale else None,
        "mancanti": mancanti,
    }


async def deposita_elenco(db, elenco: Dict[str, Any], *, documento_id: Optional[str], filename: str,
                          sha256: str) -> Optional[str]:
    """Un elenco canonico per ditta e mese: il piu' recente sostituisce il precedente, che resta."""
    if elenco["mancanti"]:
        return None
    gia = await db[COLL_ELENCHI_NETTI].find_one({"sha256": sha256}, {"_id": 0, "id": 1})
    if gia:
        return gia["id"]
    chiave = f"{elenco['codice_ditta']}:{elenco['anno']}-{elenco['mese']:02d}"
    precedenti = await db[COLL_ELENCHI_NETTI].find({"periodo_chiave": chiave}, {"_id": 0}).to_list(50)
    canonica = next((q for q in precedenti if q.get("stato") == CANONICA), None)
    eid = str(uuid.uuid4())
    await db[COLL_ELENCHI_NETTI].insert_one({
        "id": eid, "periodo_chiave": chiave, "sha256": sha256, "filename": filename, "documento_id": documento_id,
        "ditta": elenco["ditta"], "codice_ditta": elenco["codice_ditta"], "mese": elenco["mese"], "anno": elenco["anno"],
        "ripartizioni": elenco["ripartizioni"], "totale_cents": elenco["totale_cents"],
        "numero_righe": elenco["numero_righe"], "stato": CANONICA, "versione": len(precedenti) + 1,
        "sostituisce": canonica["id"] if canonica else None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    if canonica:
        await db[COLL_ELENCHI_NETTI].update_one({"id": canonica["id"]}, {"$set": {"stato": SUPERATO}})
    return eid


async def archivia_elenco(db, *, filename: str, content: bytes, testo: str,
                          source_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Conserva l'originale e deposita l'elenco dei netti da pagare."""
    from app.routers.documenti import _archive_non_payment_document

    elenco = leggi_elenco(testo)
    metadata = {
        "ditta": elenco["ditta"], "mese": elenco["mese"], "anno": elenco["anno"],
        "totale_cents": elenco["totale_cents"], "righe": elenco["numero_righe"], "mancanti": elenco["mancanti"],
        # Non e' un pagamento ne' un obbligo contabile: dice cosa ci si aspetta di bonificare.
        "obligation_status": "NON_APPLICABILE",
    }
    archiviato = await _archive_non_payment_document(
        db, filename=filename, content=content, document_type=TIPO, metadata=metadata, source_context=source_context)
    documento_id = archiviato.get("doc_id")
    eid = await deposita_elenco(
        db, elenco, documento_id=documento_id, filename=filename, sha256=hashlib.sha256(content).hexdigest())
    if eid and documento_id:
        await db["documents_inbox"].update_one(
            {"id": documento_id, "status": "da_verificare"}, {"$set": {"status": "archiviato", "elenco_netti_id": eid}})
    archiviato.update({
        "workflow": "ELENCO_NETTI", "elenco_netti_id": eid,
        "message": (
            f"Elenco netti {elenco['mese']:02d}/{elenco['anno']}: {elenco['numero_righe']} dipendenti, "
            f"totale {elenco['totale_cents'] / 100:.2f} EUR"
            if eid else
            f"Elenco netti conservato ma non depositato (da verificare: {', '.join(elenco['mancanti']) or '-'})"
        ),
    })
    return archiviato
