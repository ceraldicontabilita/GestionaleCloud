"""Registro versamenti F24 interno: il «Cassetto fiscale» del gestionale.

La fonte e' la quietanza AdE (una delega = un pagamento, copie unite da
``pagamenti_da_quietanze``). Per ogni anno di versamento, ogni codice tributo
ha il suo importo a debito e a credito mese per mese; in piu', a differenza
del Cassetto, dice quando un codice che si versa ogni mese **non e'
pervenuto** in un mese gia' scaduto.

Tre viste, una lettura sola del registro unico F24:

* **codici** — per codice: debito e credito per mese di versamento, totali,
  mesi di riferimento mancanti per i codici mensili;
* **deleghe** — ogni F24 quietanzato (data, protocollo, saldo, debito,
  credito, da dove e' arrivato: Posta, Drive, Caricato), comprese le deleghe
  a saldo zero, pagate tutte in compensazione;
* **crediti** — ogni codice a credito (per anno di riferimento) con gli F24
  che lo hanno usato e i debiti che ha pagato: il credito si scarica delega
  dopo delega.

Nessuna scrittura, nessuna stima: un mese senza quietanza resta vuoto.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any, Dict, List, Optional

from app.constants.codici_ravvedimento import CODICI_RAVVEDIMENTO
from app.services import f24_controllo_incrociato as reg
from app.services.tributi_per_codice import descrizione_codice, natura_codice

MESI = ["gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic"]

# Un codice e' «mensile» se nell'anno di riferimento e' stato versato per
# almeno tanti mesi diversi: sotto questa soglia un mese vuoto non e' un buco.
MIN_MESI_MENSILE = 3
# Il periodo mese M scade il 16 del mese dopo.
GIORNO_SCADENZA = 16


def _periodo_scaduto(anno: int, mese: int, oggi: str) -> bool:
    a, m = (anno + 1, 1) if mese == 12 else (anno, mese + 1)
    return f"{a}-{m:02d}-{GIORNO_SCADENZA:02d}" < oggi


def _vista_delega(p: Dict[str, Any]) -> Dict[str, Any]:
    righe = p.get("_righe") or []
    debito = sum(int(r.get("importo_debito_cents") or 0) for r in righe)
    credito = sum(int(r.get("importo_credito_cents") or 0) for r in righe)
    prima = (p.get("quietanze") or [{}])[0]
    return {
        "chiave": p["chiave"],
        "data": p.get("data"),
        "protocollo": p.get("protocollo"),
        "saldo_cents": p.get("importo_cents"),
        "debito_cents": debito,
        "credito_cents": credito,
        "compensazione_totale": bool(p.get("compensazione_totale")),
        "origini": p.get("origini") or [],
        "copie": len(p.get("quietanze") or []),
        "quietanza_id": prima.get("id"),
        "pdf_url": prima.get("pdf_url"),
        "filename": prima.get("filename"),
        "righe": [
            {"sezione": r.get("sezione"), "codice": r.get("codice"),
             "periodo": reg._periodo(r.get("anno"), r.get("mese")),
             "debito_cents": int(r.get("importo_debito_cents") or 0),
             "credito_cents": int(r.get("importo_credito_cents") or 0)}
            for r in righe
        ],
    }


def costruisci(
    pagamenti: List[Dict[str, Any]], *, anno: Optional[int] = None, origine: Optional[str] = None,
    oggi: Optional[str] = None,
) -> Dict[str, Any]:
    oggi = oggi or date.today().isoformat()
    datati = [p for p in pagamenti if p.get("data") and p.get("_righe")]
    anni = sorted({int(p["data"][:4]) for p in datati}, reverse=True)
    per_origine: Dict[str, int] = defaultdict(int)
    for p in datati:
        for o in p.get("origini") or ["altro"]:
            per_origine[o] += 1
    if origine:
        datati = [p for p in datati if origine in (p.get("origini") or ["altro"])]
    anno = anno or (anni[0] if anni else None)
    dell_anno = [p for p in datati if anno and p["data"].startswith(str(anno))]

    # ── codici: debito e credito per mese di versamento ──────────────────
    codici: Dict[tuple, Dict[str, Any]] = {}
    for p in dell_anno:
        mese_vers = int(p["data"][5:7])
        for r in p["_righe"]:
            sezione, codice = str(r.get("sezione") or ""), str(r.get("codice") or "")
            if not codice:
                continue
            c = codici.get((sezione, codice))
            if c is None:
                c = codici[(sezione, codice)] = {
                    "chiave": f"{sezione}|{codice}", "sezione": sezione, "codice": codice,
                    "descrizione": descrizione_codice(codice, sezione, r.get("descrizione") or ""),
                    "natura": natura_codice(codice, r.get("descrizione") or ""),
                    "mesi": {m: {"debito_cents": 0, "credito_cents": 0} for m in range(1, 13)},
                    "debito_cents": 0, "credito_cents": 0, "deleghe": 0,
                }
            deb, cred = int(r.get("importo_debito_cents") or 0), int(r.get("importo_credito_cents") or 0)
            c["mesi"][mese_vers]["debito_cents"] += deb
            c["mesi"][mese_vers]["credito_cents"] += cred
            c["debito_cents"] += deb
            c["credito_cents"] += cred
            c["deleghe"] += 1

    # ── mesi di riferimento non pervenuti (codici mensili, anno di riferimento) ──
    periodi: Dict[tuple, set] = defaultdict(set)
    for p in datati:
        for r in p["_righe"]:
            if r.get("anno") == anno and r.get("mese") and int(r.get("importo_debito_cents") or 0) > 0:
                periodi[(str(r.get("sezione") or ""), str(r.get("codice") or ""))].add(int(r["mese"]))
    for chiave, mesi_pagati in periodi.items():
        codice = chiave[1]
        if codice.upper() in CODICI_RAVVEDIMENTO or len(mesi_pagati) < MIN_MESI_MENSILE:
            continue
        mancanti = [m for m in range(1, 13) if m not in mesi_pagati and _periodo_scaduto(anno, m, oggi)]
        c = codici.get(chiave)
        if c is None:  # riferimento di quest'anno versato solo l'anno dopo
            c = codici[chiave] = {
                "chiave": f"{chiave[0]}|{codice}", "sezione": chiave[0], "codice": codice,
                "descrizione": descrizione_codice(codice, chiave[0]), "natura": natura_codice(codice),
                "mesi": {m: {"debito_cents": 0, "credito_cents": 0} for m in range(1, 13)},
                "debito_cents": 0, "credito_cents": 0, "deleghe": 0,
            }
        c["mensile"] = True
        c["periodi_pagati"] = sorted(mesi_pagati)
        c["mancanti"] = mancanti
    for c in codici.values():
        c.setdefault("mensile", False)
        c.setdefault("periodi_pagati", [])
        c.setdefault("mancanti", [])
        c["mesi"] = [{"mese": m, **v} for m, v in sorted(c["mesi"].items())]
    ordinati = sorted(codici.values(), key=lambda c: (
        0 if c["codice"].isdigit() else 1, c["codice"].zfill(6), c["sezione"]))

    # ── crediti: ogni codice a credito e gli F24 che lo hanno scaricato ──
    crediti: Dict[tuple, Dict[str, Any]] = {}
    for p in sorted(datati, key=lambda x: x["data"]):
        righe = p["_righe"]
        debiti = [
            {"codice": r.get("codice"), "periodo": reg._periodo(r.get("anno"), r.get("mese")),
             "importo_cents": int(r.get("importo_debito_cents") or 0)}
            for r in righe if int(r.get("importo_debito_cents") or 0) > 0
        ]
        for r in righe:
            cred = int(r.get("importo_credito_cents") or 0)
            if cred <= 0:
                continue
            chiave = (str(r.get("sezione") or ""), str(r.get("codice") or ""), r.get("anno"))
            k = crediti.get(chiave)
            if k is None:
                k = crediti[chiave] = {
                    "chiave": f"{chiave[0]}|{chiave[1]}|{chiave[2] or ''}", "sezione": chiave[0],
                    "codice": chiave[1], "anno_riferimento": chiave[2],
                    "descrizione": descrizione_codice(chiave[1], chiave[0], r.get("descrizione") or ""),
                    "utilizzato_cents": 0, "utilizzi": [],
                }
            k["utilizzato_cents"] += cred
            k["utilizzi"].append({
                "data": p["data"], "protocollo": p.get("protocollo"), "importo_cents": cred,
                "periodo": reg._periodo(r.get("anno"), r.get("mese")),
                "utilizzato_progressivo_cents": k["utilizzato_cents"],
                "saldo_delega_cents": p.get("importo_cents"),
                "compensazione_totale": bool(p.get("compensazione_totale")),
                "debiti_compensati": debiti, "origini": p.get("origini") or [],
                "pdf_url": ((p.get("quietanze") or [{}])[0]).get("pdf_url"),
            })
    lista_crediti = sorted(
        (k for k in crediti.values() if not anno or any(u["data"].startswith(str(anno)) for u in k["utilizzi"])
         or k["anno_riferimento"] == anno),
        key=lambda k: (-(k["anno_riferimento"] or 0), k["codice"]),
    )

    deleghe = sorted((_vista_delega(p) for p in dell_anno), key=lambda d: d["data"], reverse=True)
    return {
        "anno": anno,
        "anni": anni,
        "origine": origine,
        "mesi": MESI,
        "codici": ordinati,
        "deleghe": deleghe,
        "crediti": lista_crediti,
        "totali": {
            "deleghe": len(deleghe),
            "compensate_saldo_zero": sum(1 for d in deleghe if d["compensazione_totale"]),
            "debito_cents": sum(d["debito_cents"] for d in deleghe),
            "credito_cents": sum(d["credito_cents"] for d in deleghe),
            "saldo_cents": sum(int(d["saldo_cents"] or 0) for d in deleghe),
            "codici": len(ordinati),
            "codici_con_mancanti": sum(1 for c in ordinati if c["mancanti"]),
        },
        "origini": [{"id": k, "label": v, "deleghe": per_origine.get(k, 0)} for k, v in reg.ORIGINI.items()],
    }


async def vista_versamenti(db, *, anno: Optional[int] = None, origine: Optional[str] = None) -> Dict[str, Any]:
    registro = await reg.carica_registro(db)
    quietanze = [q for q in registro["quietanze"] if q.get("righe")]
    return costruisci(reg.pagamenti_da_quietanze(quietanze), anno=anno, origine=origine)
