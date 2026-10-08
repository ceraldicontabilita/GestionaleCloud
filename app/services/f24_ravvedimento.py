"""F24 del commercialista e il suo ravvedimento: due modelli, un legame.

Il commercialista manda un F24; se non viene pagato alla scadenza, il titolare
lo rifa' da se' con il ravvedimento e paga di piu'. In archivio restano due
modelli «da pagare» (es. ``1040 12/2024`` per 520,00 EUR e, accanto, ``1040
12/2024`` 521,57 piu' la sanzione ``8948 12/2024`` 7,22 = 528,79 EUR) e
l'addebito in banca e' di 528,79: nessun modello ha l'importo dell'addebito
del commercialista, e nessun abbinamento per importo puo' spiegarlo.

Il legame si prova con i **codici tributo**, mai con un importo vicino:

- il documento di ravvedimento (modello o quietanza AdE) porta almeno una
  sanzione da ravvedimento (``CODICI_RAVVEDIMENTO``: 8947-8953 per ritenute e
  addizionali, Ris. AdE 18/E del 28/04/2023; 890x/891x per gli altri tributi)
  o un codice d'interessi (1989-1994, 1507-1512);
- ogni riga a debito dell'originale (sezione, codice, periodo) c'e' anche nel
  ravvedimento, con lo stesso importo al centesimo **oppure** con un importo
  maggiore solo se per quel periodo c'e' una sanzione o un codice d'interessi:
  la Ris. 18/E dice che «gli interessi dovuti sono cumulati al tributo che si
  intende ravvedere», quindi la differenza e' l'interesse, dichiarata riga per
  riga, non una tolleranza;
- i crediti compensati dell'originale ci sono uguali al centesimo;
- almeno una riga dell'originale e' ravveduta (altrimenti e' il pagamento
  ordinario, che collega gia' ``quietanze_import``);
- un solo ravvedimento possibile per originale, e nessuna riga del
  ravvedimento contesa da due originali: altrimenti restano candidati.

L'originale non si tocca (resta il documento del commercialista, con il suo
stato); gli si scrive accanto ``ravvedimento`` col legame e il dettaglio. Il
modello di ravvedimento prende l'etichetta ``RAVVEDIMENTO`` e ``ravvedimento_di``;
la quietanza AdE lo stesso ``ravvedimento_di``. Quietanza e addebito in banca
si riscontrano con ``f24_controllo_incrociato.riscontri_quietanze_banca``:
l'importo che la banca addebita e' quello del ravvedimento, uguale al centesimo.
Nessun giudizio fiscale: fatti e differenze da verificare col commercialista.
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app.constants.codici_ravvedimento import CODICI_RAVVEDIMENTO
from app.db_collections import COLL_F24, COLL_QUIETANZE_F24
from app.services.f24_controllo_incrociato import (
    _quietanza_legacy, centesimi, euro, pagamenti_da_quietanze, righe_modello,
)

logger = logging.getLogger(__name__)

ETICHETTA = "RAVVEDIMENTO"
STATO_RAVVEDUTO = "RAVVEDUTO"
_STATI_SCARTATI = {"eliminato", "deleted", "archiviato"}

# Chiave di una riga: sezione, codice, anno, mese (None per i tributi annuali).
Chiave = Tuple[str, str, Optional[int], Optional[int]]


def _chiave(r: Dict[str, Any]) -> Chiave:
    return (str(r.get("sezione") or ""), str(r.get("codice") or ""), r.get("anno"), r.get("mese"))


def _periodo_testo(anno: Optional[int], mese: Optional[int]) -> str:
    if anno and mese:
        return f"{mese:02d}/{anno}"
    return str(anno) if anno else "senza periodo"


def _cf(doc: Dict[str, Any]) -> str:
    return str(
        doc.get("codice_fiscale") or (doc.get("dati_generali") or {}).get("codice_fiscale") or ""
    ).strip().upper()


def scomponi(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Debiti e crediti per riga, sanzioni e periodi ravveduti di un documento F24."""
    debiti: Dict[Chiave, int] = defaultdict(int)
    crediti: Dict[Chiave, int] = defaultdict(int)
    sanzioni: List[Dict[str, Any]] = []
    periodi_ravveduti: set = set()
    for r in righe_modello(doc):
        codice = str(r.get("codice") or "").upper()
        if not codice:
            continue
        if codice in CODICI_RAVVEDIMENTO:
            if r["importo_debito_cents"]:
                sanzioni.append({
                    "codice": codice, "sezione": r["sezione"], "periodo": _periodo_testo(r["anno"], r["mese"]),
                    "importo": euro(r["importo_debito_cents"]), "importo_cents": r["importo_debito_cents"],
                })
            periodi_ravveduti.add((r["sezione"], r["anno"], r["mese"]))
            continue
        if r["importo_debito_cents"]:
            debiti[_chiave(r)] += r["importo_debito_cents"]
        if r["importo_credito_cents"]:
            crediti[_chiave(r)] += r["importo_credito_cents"]
    return {"debiti": dict(debiti), "crediti": dict(crediti), "sanzioni": sanzioni,
            "periodi_ravveduti": periodi_ravveduti}


def _ravveduto(periodi: set, chiave: Chiave) -> bool:
    """Il periodo della riga ha una sanzione o un interesse nella stessa sezione.

    Il periodo deve coincidere: una sanzione annuale (8904 «2025», l'IVA
    mensile si scrive con l'anno e il mese nel codice) copre solo le righe
    annuali, mai una ritenuta mensile dello stesso anno.
    """
    sezione, _codice, anno, mese = chiave
    return (sezione, anno, mese) in periodi


def contiene(contenitore: Dict[str, Any], documento: Dict[str, Any]) -> bool:
    """Ogni riga di ``documento`` (sanzioni comprese) e' in ``contenitore`` al centesimo."""
    c, d = scomponi(contenitore), scomponi(documento)
    sanzioni_c = defaultdict(int)
    for s in c["sanzioni"]:
        sanzioni_c[(s["sezione"], s["codice"], s["periodo"])] += s["importo_cents"]
    sanzioni_d = defaultdict(int)
    for s in d["sanzioni"]:
        sanzioni_d[(s["sezione"], s["codice"], s["periodo"])] += s["importo_cents"]
    return (
        all(c["debiti"].get(k) == v for k, v in d["debiti"].items())
        and all(c["crediti"].get(k) == v for k, v in d["crediti"].items())
        and all(sanzioni_c.get(k) == v for k, v in sanzioni_d.items())
    )


def confronta(originale: Dict[str, Any], ravvedimento: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Il dettaglio del legame se ``ravvedimento`` ravvede ``originale``, altrimenti None."""
    o, r = scomponi(originale), scomponi(ravvedimento)
    if o["sanzioni"] or o["periodi_ravveduti"] or not (r["sanzioni"] or r["periodi_ravveduti"]):
        return None
    if not o["debiti"]:
        return None
    cf_o, cf_r = _cf(originale), _cf(ravvedimento)
    if cf_o and cf_r and cf_o != cf_r:
        return None
    righe = []
    ravvedute = 0
    for chiave, importo_o in sorted(o["debiti"].items(), key=lambda kv: str(kv[0])):
        importo_r = r["debiti"].get(chiave)
        if importo_r is None:
            return None
        periodo_ravveduto = _ravveduto(r["periodi_ravveduti"], chiave)
        if importo_r != importo_o and not (importo_r > importo_o and periodo_ravveduto):
            return None
        ravvedute += int(periodo_ravveduto)
        sezione, codice, anno, mese = chiave
        righe.append({
            "sezione": sezione, "codice": codice, "periodo": _periodo_testo(anno, mese),
            "originale": euro(importo_o), "versato": euro(importo_r),
            "interessi_cumulati": euro(importo_r - importo_o),
            "ravveduta": periodo_ravveduto,
        })
    for chiave, credito_o in o["crediti"].items():
        if r["crediti"].get(chiave) != credito_o:
            return None
    if not ravvedute:
        return None
    interessi = sum(centesimi(x["interessi_cumulati"]) or 0 for x in righe)
    sanzioni_pertinenti = [
        s for s in r["sanzioni"]
        if any(x["ravveduta"] and x["periodo"] == s["periodo"] and x["sezione"] == s["sezione"] for x in righe)
    ]
    return {
        "righe": righe,
        "chiavi": sorted(o["debiti"], key=str),
        "sanzioni": sanzioni_pertinenti,
        "interessi_cumulati": euro(interessi),
        "sanzioni_totale": euro(sum(s["importo_cents"] for s in sanzioni_pertinenti)),
    }


def _motivazione(dettaglio: Dict[str, Any], origine: str) -> str:
    ravvedute = [x for x in dettaglio["righe"] if x["ravveduta"]]
    n = len(dettaglio["righe"])
    parti = [
        (f"tutte le {n} righe" if n > 1 else "l'unica riga")
        + f" dell'F24 del commercialista (codice e periodo) {'sono' if n > 1 else 'e'}' {origine}",
        "righe ravvedute: " + ", ".join(
            f"{x['codice']} {x['periodo']} {x['originale']:.2f} -> {x['versato']:.2f}"
            + (f" (interessi cumulati {x['interessi_cumulati']:.2f})" if x["interessi_cumulati"] else "")
            for x in ravvedute
        ),
    ]
    if dettaglio["sanzioni"]:
        parti.append("sanzioni e interessi con codice proprio: " + ", ".join(
            f"{s['codice']} {s['periodo']} {s['importo']:.2f}" for s in dettaglio["sanzioni"]
        ))
    return "; ".join(parti)


def abbina_ravvedimenti(
    modelli: Iterable[Dict[str, Any]], quietanze: Iterable[Dict[str, Any]],
) -> Dict[str, Any]:
    """Collega ogni F24 originale al suo ravvedimento (modello e/o quietanza AdE).

    Funzione pura: riceve i documenti gia' letti, non scrive niente.
    """
    modelli = [m for m in modelli if m.get("id")
               and str(m.get("status") or "").lower() not in _STATI_SCARTATI]
    quietanze = [q for q in quietanze if q.get("id")
                 and str(q.get("status") or "").lower() not in _STATI_SCARTATI]
    parti = {str(m["id"]): scomponi(m) for m in modelli}
    originali = [m for m in modelli
                 if not parti[str(m["id"])]["sanzioni"] and not parti[str(m["id"])]["periodi_ravveduti"]]
    ravvedimenti = [m for m in modelli
                    if parti[str(m["id"])]["sanzioni"] or parti[str(m["id"])]["periodi_ravveduti"]]

    # Le copie della stessa quietanza sono un pagamento solo.
    per_id = {str(q["id"]): q for q in quietanze}
    gruppi = []
    for p in pagamenti_da_quietanze(_quietanza_legacy(q) for q in quietanze):
        copie = [per_id[str(c["id"])] for c in p["quietanze"] if str(c["id"]) in per_id]
        if copie and (scomponi(copie[0])["sanzioni"] or scomponi(copie[0])["periodi_ravveduti"]):
            gruppi.append({"chiave": p["chiave"], "copie": copie, "protocollo": p["protocollo"],
                           "data": p["data"], "importo_cents": p["importo_cents"]})

    proposte = []
    for o in originali:
        su_modelli = [(r, d) for r in ravvedimenti if (d := confronta(o, r))]
        su_quietanze = [(g, d) for g in gruppi if (d := confronta(o, g["copie"][0]))]
        proposte.append({"originale": o, "modelli": su_modelli, "quietanze": su_quietanze})

    # Una riga di un ravvedimento non si da' a due originali (es. due copie
    # dello stesso modello del commercialista): quelle coppie restano candidate.
    contese: Dict[Tuple[str, Chiave], int] = defaultdict(int)
    for p in proposte:
        for r, d in p["modelli"]:
            for k in d["chiavi"]:
                contese[(f"m:{r['id']}", k)] += 1
        for g, d in p["quietanze"]:
            for k in d["chiavi"]:
                contese[(f"q:{g['chiave']}", k)] += 1

    abbinati, ambigui = [], []
    for p in proposte:
        o = p["originale"]
        if not p["modelli"] and not p["quietanze"]:
            continue
        conteso = any(contese[(f"m:{r['id']}", k)] > 1 for r, d in p["modelli"] for k in d["chiavi"]) or any(
            contese[(f"q:{g['chiave']}", k)] > 1 for g, d in p["quietanze"] for k in d["chiavi"])
        modello, gruppo, dettaglio, origine = None, None, None, None
        if len(p["modelli"]) == 1:
            modello, dettaglio = p["modelli"][0]
            origine = "nel modello di ravvedimento"
            # La quietanza e' quella che il matcher ha gia' legato al modello,
            # oppure l'unica che ravvede lo stesso originale.
            # La quietanza del ravvedimento contiene il modello riga per riga
            # (puo' portare anche altri tributi pagati con la stessa delega).
            candidate = [g for g, _ in p["quietanze"] if contiene(g["copie"][0], modello)]
            gruppo = candidate[0] if len(candidate) == 1 else None
        elif not p["modelli"] and len(p["quietanze"]) == 1:
            gruppo, dettaglio = p["quietanze"][0]
            origine = "nella quietanza AdE del ravvedimento"
        if dettaglio is None or conteso:
            ambigui.append({
                "originale_id": o["id"],
                "modelli_candidati": [r["id"] for r, _ in p["modelli"]],
                "quietanze_candidate": [c["id"] for g, _ in p["quietanze"] for c in g["copie"]],
                "motivazione": (
                    "la stessa riga del ravvedimento risulta anche in un altro F24 del commercialista"
                    if conteso else "piu' ravvedimenti compatibili: scegliere a mano"
                ),
            })
            continue
        abbinati.append({
            "originale_id": o["id"],
            "originale_file": o.get("file_name") or o.get("filename"),
            "importo_originale": euro(centesimi(
                (o.get("totali") or {}).get("saldo_netto") or o.get("saldo"))),
            "f24_ravvedimento_id": modello["id"] if modello else None,
            "quietanza_ids": sorted(str(c["id"]) for c in gruppo["copie"]) if gruppo else [],
            "protocollo": gruppo["protocollo"] if gruppo else None,
            "data_pagamento": gruppo["data"] if gruppo else None,
            "importo_ravvedimento": euro(
                gruppo["importo_cents"] if gruppo
                else centesimi((modello.get("totali") or {}).get("saldo_netto") or modello.get("saldo"))),
            "righe": dettaglio["righe"],
            "sanzioni": [{k: v for k, v in s.items() if k != "importo_cents"} for s in dettaglio["sanzioni"]],
            "interessi_cumulati": dettaglio["interessi_cumulati"],
            "sanzioni_totale": dettaglio["sanzioni_totale"],
            "motivazione": _motivazione(dettaglio, origine),
        })
    return {"abbinati": abbinati, "ambigui": ambigui,
            "conteggi": {"originali": len(originali), "ravvedimenti_modello": len(ravvedimenti),
                         "ravvedimenti_quietanza": len(gruppi), "abbinati": len(abbinati),
                         "ambigui": len(ambigui)}}


async def applica_ravvedimenti(db, esito: Dict[str, Any]) -> Dict[str, int]:
    """Scrive i legami, solo dove cambiano: il secondo giro non riscrive niente."""
    scritti = {"originali": 0, "modelli_ravvedimento": 0, "quietanze": 0}
    per_modello: Dict[str, set] = defaultdict(set)
    per_quietanza: Dict[str, set] = defaultdict(set)
    for a in esito["abbinati"]:
        legame = {"stato": STATO_RAVVEDUTO, **{k: a[k] for k in (
            "f24_ravvedimento_id", "quietanza_ids", "protocollo", "data_pagamento",
            "importo_ravvedimento", "righe", "sanzioni", "interessi_cumulati",
            "sanzioni_totale", "motivazione")}}
        attuale = await db[COLL_F24].find_one({"id": a["originale_id"]}, {"_id": 0, "ravvedimento": 1})
        if (attuale or {}).get("ravvedimento") != legame:
            await db[COLL_F24].update_one({"id": a["originale_id"]}, {"$set": {"ravvedimento": legame}})
            scritti["originali"] += 1
        if a["f24_ravvedimento_id"]:
            per_modello[a["f24_ravvedimento_id"]].add(str(a["originale_id"]))
        for qid in a["quietanza_ids"]:
            per_quietanza[qid].add(str(a["originale_id"]))
    for mid, originali in per_modello.items():
        attuale = await db[COLL_F24].find_one({"id": mid}, {"_id": 0, "etichetta": 1, "ravvedimento_di": 1})
        nuovo = {"etichetta": ETICHETTA, "ravvedimento_di": sorted(originali)}
        if {k: (attuale or {}).get(k) for k in nuovo} != nuovo:
            await db[COLL_F24].update_one({"id": mid}, {"$set": nuovo})
            scritti["modelli_ravvedimento"] += 1
    # Un legame che non regge piu' (modello eliminato, secondo candidato
    # arrivato) si toglie: resterebbe a dire «ravveduto» senza prova.
    abbinati = {str(a["originale_id"]) for a in esito["abbinati"]}
    for doc in await db[COLL_F24].find({"ravvedimento": {"$exists": True}}, {"_id": 0, "id": 1}).to_list(5000):
        if str(doc.get("id")) not in abbinati:
            await db[COLL_F24].update_one({"id": doc["id"]}, {"$unset": {"ravvedimento": ""}})
            scritti["originali"] += 1
    for doc in await db[COLL_F24].find({"ravvedimento_di": {"$exists": True}}, {"_id": 0, "id": 1}).to_list(5000):
        if str(doc.get("id")) not in per_modello:
            await db[COLL_F24].update_one({"id": doc["id"]}, {"$unset": {"ravvedimento_di": "", "etichetta": ""}})
            scritti["modelli_ravvedimento"] += 1
    for doc in await db[COLL_QUIETANZE_F24].find(
            {"ravvedimento_di": {"$exists": True}}, {"_id": 0, "id": 1}).to_list(5000):
        if str(doc.get("id")) not in per_quietanza:
            await db[COLL_QUIETANZE_F24].update_one({"id": doc["id"]}, {"$unset": {"ravvedimento_di": ""}})
            scritti["quietanze"] += 1
    for qid, originali in per_quietanza.items():
        attuale = await db[COLL_QUIETANZE_F24].find_one({"id": qid}, {"_id": 0, "ravvedimento_di": 1})
        if (attuale or {}).get("ravvedimento_di") != sorted(originali):
            await db[COLL_QUIETANZE_F24].update_one(
                {"id": qid}, {"$set": {"ravvedimento_di": sorted(originali)}})
            scritti["quietanze"] += 1
    return scritti


async def collega_ravvedimenti(db, *, dry_run: bool = False) -> Dict[str, Any]:
    """Il giro: modelli e quietanze letti una volta, legami scritti per id."""
    modelli = await db[COLL_F24].find({}, {"_id": 0, "pdf_data": 0}).to_list(5000)
    quietanze = await db[COLL_QUIETANZE_F24].find({}, {"_id": 0, "pdf_data": 0}).to_list(5000)
    # Calcolo puro su migliaia di documenti: ~10 s sull'event loop facevano scadere l'health check di
    # Render (5 s) e riavviavano il servizio ogni ~20 minuti, azzerando i timer degli altri giri.
    esito = await asyncio.to_thread(abbina_ravvedimenti, modelli, quietanze)
    if dry_run:
        return {"dry_run": True, **esito}
    return {"dry_run": False, **esito, "scritti": await applica_ravvedimenti(db, esito)}
