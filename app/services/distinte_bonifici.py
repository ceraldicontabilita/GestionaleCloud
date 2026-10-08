"""Le distinte «beneficiari vari»: tutto quello che il sistema sa di ognuna.

La banca addebita un bonifico cumulativo ("VS.DISP. RIF. MB0B… FAVORE
BENEFICIARI VARI DISTINTA - ADD.TOT") senza dire a chi va: la ricevuta porta
lo stesso nome generico. Nessun algoritmo puo' indovinare il beneficiario
(titolare, 30/09/2026): qui si mettono in fila i dati dell'estratto, della
ricevuta e della busta paga, e la persona associa dipendente e causale dalla
pagina «Distinte» di HR (stesso `associa` della coda «Bonifici da associare»).

Due segnali, entrambi solo *suggerimenti*, mai scritture:

* ``suggerimento``: l'importo e' il netto di UN solo dipendente nel periodo;
* ``suggerimento_nota``: la nota scritta nella causale dell'estratto («… - Vespa
  acc stipendio») nomina UN solo dipendente. La nota puo' citare chi paga per
  piu' persone («stipendi» a nome del titolare): per questo resta un suggerimento.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

_DISTINTA = re.compile(r"BENEFICIARI\s+(VARI|DIVERSI)", re.I)
_RIF = re.compile(r"RIF\.?\s*:?\s*(MB[0-9A-Z]{8,})", re.I)
_NOTA = re.compile(r"ADD\.\s*(?:TOT|SPE)\s*-\s*(.+)$", re.I)


def e_distinta(testo: Any) -> bool:
    """Addebito cumulativo «FAVORE BENEFICIARI VARI/DIVERSI»."""
    return bool(_DISTINTA.search(str(testo or "")))


def nota_distinta(testo: Any) -> Optional[str]:
    """La nota scritta dopo «ADD.TOT - » nella causale dell'estratto, se c'e'."""
    m = _NOTA.search(str(testo or ""))
    return m.group(1).strip() if m else None


def _importo(valore: Any) -> float:
    try:
        return abs(float(valore or 0))
    except (TypeError, ValueError):
        return 0.0


def _giorno(valore: Any) -> str:
    return str(valore or "")[:10]


def _mesi_indietro(giorno: str, quanti: int) -> List[tuple]:
    """(anno, mese) del giorno e dei ``quanti`` mesi prima."""
    try:
        anno, mese = int(giorno[:4]), int(giorno[5:7])
    except ValueError:
        return []
    out = []
    for i in range(quanti + 1):
        m = mese - i
        a = anno
        while m < 1:
            m += 12
            a -= 1
        out.append((a, m))
    return out


async def _netti(db_gest) -> Dict[tuple, Dict[float, List[Dict[str, str]]]]:
    """(anno, mese) -> netto in centesimi -> dipendenti con quel netto."""
    righe = await db_gest["cedolini"].find(
        {}, {"_id": 0, "dipendente_id": 1, "nome_dipendente": 1, "anno": 1, "mese": 1, "netto": 1},
    ).to_list(20000)
    out: Dict[tuple, Dict[int, List[Dict[str, str]]]] = {}
    for r in righe:
        try:
            chiave = (int(r["anno"]), int(r["mese"]))
            centesimi = int(round(float(r["netto"]) * 100))
        except (KeyError, TypeError, ValueError):
            continue
        if centesimi <= 0 or not r.get("dipendente_id"):
            continue
        out.setdefault(chiave, {}).setdefault(centesimi, []).append(
            {"dipendente_id": r["dipendente_id"], "nome": r.get("nome_dipendente") or ""})
    return out


def suggerimento(netti, giorno: str, importo: float) -> Optional[Dict[str, Any]]:
    """Il solo dipendente il cui netto (busta del mese o dei due prima) e'
    uguale all'importo; con piu' candidati o nessuno, niente."""
    centesimi = int(round(importo * 100))
    trovati: Dict[str, Dict[str, Any]] = {}
    for anno, mese in _mesi_indietro(giorno, 2):
        for c in netti.get((anno, mese), {}).get(centesimi, []):
            trovati.setdefault(c["dipendente_id"], {**c, "anno": anno, "mese": mese})
    if len(trovati) != 1:
        return None
    return next(iter(trovati.values()))


async def _indici_hr(db_hr) -> Dict[str, Any]:
    from app.hr.routers.dipendenti_cloud import _indici_dipendenti

    return await _indici_dipendenti(db_hr)


def suggerimento_da_nota(indici: Dict[str, Any], nota: Optional[str]) -> Optional[Dict[str, Any]]:
    """Il dipendente nominato dalla nota della causale, se uno solo."""
    if not nota:
        return None
    from app.services.hr_pagamenti_deposito import risolvi_dipendente

    dip, motivo = risolvi_dipendente(indici, nota)
    if dip is None:
        return None
    return {"dipendente_id": dip.get("id"),
            "nome": dip.get("nome_completo") or f"{dip.get('cognome', '')} {dip.get('nome', '')}".strip(),
            "motivo": motivo, "nota": nota}


async def elenco_distinte(db_gest, db_hr, indici: Optional[Dict[str, Any]] = None,
                          coda: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    """Una riga per distinta ancora da associare, con tutti i dati estratti."""
    if coda is None:
        coda = await db_hr["bonifici_da_associare"].find(
            {"stato": "da_associare"}, {"_id": 0, "pdf_data": 0}).to_list(2000)
    if not coda:
        return []
    coda_per_rif: Dict[str, List[Dict[str, Any]]] = {}
    for c in coda:
        rif = c.get("rif_banca")
        if rif:
            coda_per_rif.setdefault(str(rif).upper(), []).append(c)
    if not coda_per_rif:
        return []
    if indici is None:
        indici = await _indici_hr(db_hr)

    movimenti = await db_gest["estratto_conto_movimenti"].find(
        {"descrizione": {"$regex": r"BENEFICIARI\s+(VARI|DIVERSI)", "$options": "i"}},
        {"_id": 0, "id": 1, "data": 1, "importo": 1, "descrizione": 1, "descrizione_originale": 1,
         "livello_evidenza": 1, "ignorata": 1, "status": 1, "source_filename": 1,
         "source_filename_ufficiale": 1, "data_pagamento": 1, "in_quarantena": 1},
    ).to_list(5000)

    distinte: Dict[str, Dict[str, Any]] = {}
    for m in movimenti:
        if m.get("status") in ("deleted", "archived") or m.get("in_quarantena"):
            continue
        testo = str(m.get("descrizione") or m.get("descrizione_originale") or "")
        if not _DISTINTA.search(testo):
            continue
        rif = _RIF.search(testo)
        if not rif:
            continue
        chiave = rif.group(1).upper()
        d = distinte.setdefault(chiave, {"rif": chiave, "movimenti": []})
        d["movimenti"].append(m)

    ricevute: Dict[str, List[Dict[str, Any]]] = {}
    if distinte:
        for t in await db_gest["bonifici_transfers"].find(
                {"cro_trn": {"$in": list(distinte)}},
                {"_id": 0, "cro_trn": 1, "source_file": 1, "data": 1, "importo": 1, "causale": 1},
        ).to_list(5000):
            ricevute.setdefault(str(t["cro_trn"]).upper(), []).append(t)

    netti = await _netti(db_gest)
    righe: List[Dict[str, Any]] = []
    for rif, d in distinte.items():
        voci = coda_per_rif.get(rif)
        if not voci:
            continue  # gia' associata, ignorata o mai entrata in coda
        tot = next((m for m in d["movimenti"] if re.search(r"ADD\.\s*TOT", str(m.get("descrizione") or ""), re.I)),
                   d["movimenti"][0])
        spe = next((m for m in d["movimenti"] if re.search(r"ADD\.\s*SPE", str(m.get("descrizione") or ""), re.I)), None)
        importo = _importo(tot.get("importo"))
        voce = next((v for v in voci if abs(_importo(v.get("importo")) - importo) < 0.005), voci[0])
        nota = _NOTA.search(str(tot.get("descrizione") or ""))
        giorno = _giorno(tot.get("data"))
        righe.append({
            "id": voce["id"],
            "data": giorno,
            "importo": importo,
            "causale": voce.get("causale") or tot.get("descrizione"),
            "pdf_filename": voce.get("pdf_filename"),
            "distinta": {
                "rif": rif,
                "commissione": _importo(spe.get("importo")) if spe else None,
                "nota": (nota.group(1).strip() if nota else None),
                "movimento_id": tot.get("id"),
                "estratto": tot.get("source_filename_ufficiale") or tot.get("source_filename"),
                "ufficiale": tot.get("livello_evidenza") == "ufficiale",
                "ignorata": bool(tot.get("ignorata")),
                "ricevuta": [{"file": r.get("source_file"), "data": _giorno(r.get("data")),
                              "importo": _importo(r.get("importo")), "causale": r.get("causale")}
                             for r in ricevute.get(rif, [])],
                "suggerimento": suggerimento(netti, giorno, importo),
                "suggerimento_nota": suggerimento_da_nota(indici, nota.group(1).strip() if nota else None),
            },
        })
    righe.sort(key=lambda r: r["data"], reverse=True)
    return righe
