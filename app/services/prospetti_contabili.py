"""Prospetti contabili del consulente del lavoro: cosa dovra' contenere l'F24 del mese.

Il «Prospetto contabile» (paghe, stampa del consulente) riassume ogni mese le
ritenute fiscali, il credito bonus, le addizionali e il saldo DM10: sono gli
importi che l'F24 del consulente versa. Il prospetto e' il fatto che dice cosa
ci si aspetta; l'F24 (e la sua quietanza) e' la prova.

Regole:

* si legge solo cio' che si e' visto stampato (una voce non riconosciuta resta in
  ``non_mappate``, mai un conto inventato); gli importi sono centesimi interi;
* l'F24 si aggancia per **codice + periodo + importo al centesimo** (le righe dello
  stesso codice e periodo si sommano: il 3848 puo' avere due comuni); mai per solo
  importo; piu' F24 ugualmente buoni = candidati, nessun aggancio;
* la quietanza arriva dall'F24 gia' agganciato (stessa prova del registro F24);
* l'abbinamento parte all'arrivo del secondo pezzo, in tutti e due i sensi
  (``collega_prospetti`` dopo l'import di un prospetto, di un modello o di una quietanza);
* il prospetto non scrive in Prima Nota ne' nel giornale: e' un indice di prova.
"""
from __future__ import annotations

import hashlib
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

TIPO = "prospetto_contabile"
COLL_PROSPETTI = "prospetti_contabili"

CANONICA = "canonica"
SUPERATO = "superato"

COMPLETO = "COMPLETO"            # ogni importo atteso e' nell'F24, al centesimo
PARZIALE = "PARZIALE"            # qualche importo si', qualcuno no o diverso
NESSUN_F24 = "NESSUN_F24"        # nessun F24 col codice, il periodo e l'importo atteso
AMBIGUO = "AMBIGUO"              # piu' F24 ugualmente compatibili: si sceglie a mano
SENZA_ATTESI = "SENZA_ATTESI"    # nel prospetto nessuna voce che l'F24 versa

_MESI = {
    "GENNAIO": 1, "FEBBRAIO": 2, "MARZO": 3, "APRILE": 4, "MAGGIO": 5, "GIUGNO": 6,
    "LUGLIO": 7, "AGOSTO": 8, "SETTEMBRE": 9, "OTTOBRE": 10, "NOVEMBRE": 11, "DICEMBRE": 12,
}

# Le voci del prospetto che l'F24 versa, come stampate (nessun'altra si indovina):
# (codice, sezione F24, lato, anno rispetto al prospetto, [etichette]).
_ATTESI: List[Tuple[str, str, str, int, List[str]]] = [
    ("1001", "sezione_erario", "debito", 0, ["RITENUTE FISCALI"]),
    ("1655", "sezione_erario", "credito", 0, ["CREDITO BONUS IRPEF", "BONUS IRPEF CONGUAGLIATO"]),
    ("3802", "sezione_regioni", "debito", -1, ["ADD. REGIONALE ANNO PRECEDENTE"]),
    ("3848", "sezione_tributi_locali", "debito", -1, ["ADD. COMUNALE ANNO PRECEDENTE"]),
    ("DM10", "sezione_inps", "debito", 0, ["IMPORTO VERSATO DM/10", "SALDO DM10 UN", "SALDO DM10"]),
]

_IMPORTO = r"\d{1,3}(?:\.\d{3})*,\d{2}"
_RE_VOCE = re.compile(rf"^\|?\s*(.+?)\s{{2,}}({_IMPORTO})([+-])(?:\||\s|$)")
_RE_PERIODO = re.compile(r"([A-Z]+)\s+(\d{4})\s+\*{3}\s*PROSPETTO\s+CONTABILE")
_RE_DITTA = re.compile(r"DITTA\s*:\s*(.+?)\s+CODICE\s*:\s*(\d+)")
_RE_STAMPA = re.compile(r"STAMPATO\s+IL\s*:\s*(\d{2})/(\d{2})/(\d{4})\s+ALLE\s*:\s*(\d{2}):(\d{2})")


def e_riepilogo_paghe(testo: str) -> bool:
    """Il «Prospetto riepilogativo elaborazione paghe» (Paghe Infinity): il riepilogo mensile del consulente."""
    t = re.sub(r"\s+", " ", (testo or "").upper())
    return "PROSPETTO RIEPILOGATIVO ELABORAZIONE PAGHE" in t and "RIEPILOGO IMPORTI A DEBITO/CREDITO" in t


def riconosci(testo: str) -> bool:
    """Il prospetto del consulente, in uno dei due formati.

    Vecchio: intestazione «PROSPETTO CONTABILE», la ditta e almeno una voce dei conti.
    Nuovo (Paghe Infinity): «Prospetto riepilogativo elaborazione paghe» con il riepilogo debiti/crediti.
    """
    t = re.sub(r"\s+", " ", (testo or "").upper())
    return e_riepilogo_paghe(testo) or ("*** PROSPETTO CONTABILE ***" in t and "DITTA :" in t and (
        "RITENUTE FISCALI" in t or "SALDO DM10" in t or "TOTALE RETRIBUZIONI LORDE" in t))


def _cents(valore: str) -> int:
    return int(valore.replace(".", "").replace(",", ""))


def _etichetta(testo: str) -> str:
    return re.sub(r"\s+", " ", testo).strip(" |.")


# Riepilogo paghe nuovo formato: le voci della sezione «RIEPILOGO IMPORTI A DEBITO/CREDITO».
# Si mappano sull'F24 solo le due che coincidono al centesimo con una riga F24 (INPS dipendenti e
# gestione separata); IRPEF e addizionali si dividono nell'F24 su piu' codici e periodi (3847/3848,
# anni diversi): si vedono, non si usano (mai un conto inventato).
_RE_RP_PERIODO = re.compile(r"\bAL\s+([A-Z]+)\s+(\d{4})\s+NORM", re.I)
_RE_RP_AZIENDA = re.compile(r"^\s*(\d{6})\s+(\S.*?)\s*$", re.M)
_RE_RP_VOCE = re.compile(rf"^(.+?)\s+({_IMPORTO})\s+PERIODO\s+VERSAMENTO\s+(\d{{2}})/(\d{{4}})\s*$", re.I | re.M)
_RE_RP_NETTI = re.compile(rf"TOTALE\s+NETTI\s+({_IMPORTO})", re.I)
_RE_RP_TOTALE = re.compile(rf"TOTALE\s+COMPLESSIVO\s+({_IMPORTO})", re.I)
_ATTESI_RIEPILOGO: List[Tuple[str, str, str, str]] = [
    # (inizio etichetta, codice, sezione F24, lato)
    ("9001 I.N.P.S. ID.", "DM10", "sezione_inps", "debito"),
    ("9005 I.N.P.S. - GESTIONE SEPARATA", "CXX", "sezione_inps", "debito"),
]


def _leggi_riepilogo_paghe(testo: str) -> Dict[str, Any]:
    """Il riepilogo mensile paghe come dati; deve quadrare: netti + importi a debito = totale complessivo."""
    periodo = _RE_RP_PERIODO.search(testo)
    mese = _MESI.get(periodo.group(1).upper()) if periodo else None
    anno = int(periodo.group(2)) if periodo else None
    azienda = _RE_RP_AZIENDA.search(testo)
    netti = _RE_RP_NETTI.search(testo)
    totale = _RE_RP_TOTALE.search(testo)
    voci: List[Dict[str, Any]] = []
    for m in _RE_RP_VOCE.finditer(testo):
        voci.append({"etichetta": _etichetta(m.group(1)), "importo_cents": _cents(m.group(2)), "segno": "+",
                     "periodo_versamento": f"{m.group(3)}/{m.group(4)}"})
    attesi: List[Dict[str, Any]] = []
    usate = set()
    for inizio, codice, sezione, lato in _ATTESI_RIEPILOGO:
        v = next((x for x in voci if x["etichetta"].upper().startswith(inizio)), None)
        if v and mese and anno and v["periodo_versamento"] == f"{mese:02d}/{anno}" and v["importo_cents"] > 0:
            usate.add(v["etichetta"])
            attesi.append({"codice": codice, "sezione": sezione, "lato": lato, "mese": mese, "anno": anno,
                           "importo_cents": v["importo_cents"], "etichetta": v["etichetta"]})
    netti_cents = _cents(netti.group(1)) if netti else None
    totale_cents = _cents(totale.group(1)) if totale else None
    mancanti = [nome for nome, valore in (("periodo", mese), ("ditta", azienda), ("totale_complessivo", totale_cents),
                                          ("totale_netti", netti_cents)) if not valore]
    # La prova che si e' letto tutto: netti + tutti gli importi a debito = totale complessivo, al centesimo.
    if not mancanti and netti_cents + sum(v["importo_cents"] for v in voci) != totale_cents:
        mancanti.append("quadratura")
    return {
        "formato": "riepilogo_paghe",
        "ditta": azienda.group(2).strip() if azienda else None,
        "codice_ditta": azienda.group(1) if azienda else None,
        "mese": mese, "anno": anno,
        "stampato_il": None,    # il riepilogo non porta la data di stampa: l'ultimo arrivato vale
        "voci": voci, "attesi": attesi,
        "non_mappate": [v for v in voci if v["etichetta"] not in usate],
        "netti_cents": netti_cents, "totale_complessivo_cents": totale_cents,
        "mancanti": mancanti,
    }


def leggi_prospetto(testo: str) -> Dict[str, Any]:
    """Il prospetto come dati; cio' che non si legge resta ``None`` e va in ``mancanti``."""
    if e_riepilogo_paghe(testo):
        return _leggi_riepilogo_paghe(testo)
    t = (testo or "").upper()
    periodo = _RE_PERIODO.search(t)
    ditta = _RE_DITTA.search(t)
    stampa = _RE_STAMPA.search(t)

    voci: List[Dict[str, Any]] = []
    for riga in t.splitlines():
        m = _RE_VOCE.match(riga)
        if m and not riga.lstrip("| ").startswith("_"):
            voci.append({"etichetta": _etichetta(m.group(1)), "importo_cents": _cents(m.group(2)), "segno": m.group(3)})

    mese = _MESI.get(periodo.group(1)) if periodo else None
    anno = int(periodo.group(2)) if periodo else None
    attesi: List[Dict[str, Any]] = []
    usate = set()
    for codice, sezione, lato, offset, etichette in _ATTESI:
        trovata = next((v for e in etichette for v in voci if v["etichetta"] == e and v["importo_cents"] > 0), None)
        if trovata and mese and anno:
            usate.add(trovata["etichetta"])
            attesi.append({
                "codice": codice, "sezione": sezione, "lato": lato,
                "mese": mese, "anno": anno + offset, "importo_cents": trovata["importo_cents"],
                "etichetta": trovata["etichetta"],
            })
    mancanti = [nome for nome, valore in (("periodo", mese), ("ditta", ditta), ("stampato_il", stampa)) if not valore]
    return {
        "ditta": ditta.group(1).strip() if ditta else None,
        "codice_ditta": ditta.group(2) if ditta else None,
        "mese": mese, "anno": anno,
        "stampato_il": (f"{stampa.group(3)}-{stampa.group(2)}-{stampa.group(1)}T{stampa.group(4)}:{stampa.group(5)}"
                        if stampa else None),
        "voci": voci,
        "attesi": attesi,
        # Importi che l'F24 non versa o che non si sanno ancora mappare: si vedono, non si usano.
        "non_mappate": [v for v in voci if v["etichetta"] not in usate and v["importo_cents"] > 0
                        and v["importo_cents"] not in {a["importo_cents"] for a in attesi}
                        and any(k in v["etichetta"] for k in ("VERSATO", "ADD.", "BONUS"))],
        "mancanti": mancanti,
    }


# ── aggancio all'F24 ──────────────────────────────────────────────────────

def _somma_righe(righe: List[Dict[str, Any]]) -> Dict[Tuple[str, int, int], Tuple[int, int]]:
    """(codice, mese, anno) -> (debito, credito) in centesimi: righe uguali si sommano."""
    out: Dict[Tuple[str, int, int], Tuple[int, int]] = {}
    for r in righe:
        try:
            chiave = (str(r["codice"]), int(r["mese"]), int(r["anno"]))
        except (TypeError, ValueError, KeyError):
            continue
        d, c = out.get(chiave, (0, 0))
        out[chiave] = (d + int(r.get("importo_debito_cents") or 0), c + int(r.get("importo_credito_cents") or 0))
    return out


def valuta_modello(attesi: List[Dict[str, Any]], righe: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Quanti importi attesi l'F24 contiene, uno per uno, al centesimo."""
    somme = _somma_righe(righe)
    dettaglio = []
    for a in attesi:
        d, c = somme.get((a["codice"], a["mese"], a["anno"]), (0, 0))
        trovato = d if a["lato"] == "debito" else c
        voce = {k: a[k] for k in ("codice", "mese", "anno", "lato", "importo_cents")}
        if a["codice"] == "DM10" and not trovato:
            # RC01 non e' un altro nome del DM10: e' lo stesso contributo del periodo versato in ritardo,
            # con sanzioni e interessi. Pagato per intero + sanzioni = RAVVEDUTO; meno dell'atteso = DIFFERENZA.
            rd, rc = somme.get(("RC01", a["mese"], a["anno"]), (0, 0))
            ravveduto = rd if a["lato"] == "debito" else rc
            if ravveduto:
                voce.update({
                    "trovato_cents": ravveduto, "codice_trovato": "RC01",
                    "esito": "RAVVEDUTO" if ravveduto >= a["importo_cents"] else "DIFFERENZA",
                    "sanzioni_interessi_cents": ravveduto - a["importo_cents"],
                })
                dettaglio.append(voce)
                continue
        esito = ("OK" if trovato == a["importo_cents"] else
                 "DIFFERENZA" if trovato else "ASSENTE")
        dettaglio.append({**voce, "trovato_cents": trovato or None, "esito": esito})
    return {"ok": sum(1 for d in dettaglio if d["esito"] in ("OK", "RAVVEDUTO")), "dettaglio": dettaglio}


def _scegli_modello(attesi, modelli) -> Tuple[Optional[Dict[str, Any]], List[str], Dict[str, Any]]:
    """Il modello con piu' importi esatti. Parita' fra modelli DIVERSI (non la stessa
    delega registrata due volte) = candidati, nessuna scelta."""
    from app.services import f24_controllo_incrociato as registro_f24

    punteggi = []
    for f24, righe in modelli:
        v = valuta_modello(attesi, righe)
        if v["ok"]:
            punteggi.append((v["ok"], f24, v))
    if not punteggi:
        return None, [], {"ok": 0, "dettaglio": valuta_modello(attesi, [])["dettaglio"]}
    migliore = max(p[0] for p in punteggi)
    in_testa = [p for p in punteggi if p[0] == migliore]
    # Due copie della stessa delega (data e saldo uguali) sono un modello solo.
    distinti: Dict[Tuple[Any, Any], Tuple[int, Dict[str, Any], Dict[str, Any]]] = {}
    for p in in_testa:
        chiave = (registro_f24.data_versamento_modello(p[1]), registro_f24.saldo_modello_cents(p[1]))
        distinti.setdefault(chiave if chiave != (None, None) else (p[1].get("id"), None), p)
    if len(distinti) > 1:
        return None, [str(p[1].get("id")) for p in in_testa], in_testa[0][2]
    scelto = next(iter(distinti.values()))
    return scelto[1], [], scelto[2]


async def collega_prospetti(db) -> Dict[str, int]:
    """Aggancia ogni prospetto canonico all'F24 (e alla quietanza) che lo versa.

    Idempotente: si puo' richiamare a ogni arrivo di un modello o di una quietanza.
    Un prospetto gia' COMPLETO con la sua quietanza non si ritocca.
    """
    from app.services import f24_controllo_incrociato as registro_f24

    prospetti = await db[COLL_PROSPETTI].find({"stato": CANONICA}, {"_id": 0}).to_list(2000)
    da_fare = [p for p in prospetti if not (p.get("esito") == COMPLETO and p.get("quietanze"))]
    if not da_fare:
        return {"esaminati": 0, "aggiornati": 0}
    registro = await registro_f24.carica_registro(db)
    modelli = [(f24, registro_f24.righe_modello(f24)) for f24 in registro["f24"]]
    aggiornati = 0
    for p in da_fare:
        attesi = p.get("attesi") or []
        if not attesi:
            nuovo = {"esito": SENZA_ATTESI, "f24_id": None, "candidati": [], "quietanze": [], "riscontro": []}
        else:
            modello, candidati, valutazione = _scegli_modello(attesi, modelli)
            if modello is None and candidati:
                esito = AMBIGUO
            elif modello is None:
                esito = NESSUN_F24
            else:
                esito = COMPLETO if valutazione["ok"] == len(attesi) else PARZIALE
            quietanze: List[Dict[str, Any]] = []
            data_versamento = None
            if modello is not None:
                prove = registro_f24.prove_modello(modello, registro)
                data_versamento = prove.get("data_versamento")
                quietanze = [{"id": q.get("quietanza_id"), "criterio": q.get("criterio") or "agganciata"}
                             for q in prove["quietanze"] if q.get("quietanza_id")]
            nuovo = {
                "esito": esito,
                "f24_id": modello.get("id") if modello is not None else None,
                "candidati": candidati,
                "data_versamento": data_versamento,
                "quietanze": quietanze,
                "riscontro": valutazione["dettaglio"],
            }
        if any(p.get(k) != v for k, v in nuovo.items()):
            await db[COLL_PROSPETTI].update_one(
                {"id": p["id"]}, {"$set": {**nuovo, "collegato_il": datetime.now(timezone.utc).isoformat()}})
            aggiornati += 1
    return {"esaminati": len(da_fare), "aggiornati": aggiornati}


# ── deposito ──────────────────────────────────────────────────────────────

async def deposita_prospetto(db, prospetto: Dict[str, Any], *, documento_id: Optional[str],
                             filename: str, sha256: str) -> Optional[str]:
    """Un prospetto per ditta e mese: una stampa piu' recente sostituisce la precedente
    (che resta, ``superato``); una piu' vecchia arriva gia' superata. Mai cancellato."""
    if prospetto["mancanti"] or not prospetto["attesi"] and not prospetto["voci"]:
        return None
    chiave = f"{prospetto['codice_ditta']}:{prospetto['anno']}-{prospetto['mese']:02d}"
    gia = await db[COLL_PROSPETTI].find_one({"sha256": sha256}, {"_id": 0, "id": 1})
    if gia:
        return gia["id"]
    stesse = await db[COLL_PROSPETTI].find({"periodo_chiave": chiave}, {"_id": 0}).to_list(50)
    canonica = next((q for q in stesse if q.get("stato") == CANONICA), None)
    nuova_e_piu_recente = not canonica or (prospetto["stampato_il"] or "") >= (canonica.get("stampato_il") or "")
    pid = str(uuid.uuid4())
    doc = {
        "id": pid, "periodo_chiave": chiave, "sha256": sha256, "filename": filename,
        "documento_id": documento_id,
        "ditta": prospetto["ditta"], "codice_ditta": prospetto["codice_ditta"],
        "mese": prospetto["mese"], "anno": prospetto["anno"], "stampato_il": prospetto["stampato_il"],
        "attesi": prospetto["attesi"], "non_mappate": prospetto["non_mappate"], "voci": prospetto["voci"],
        "formato": prospetto.get("formato", "prospetto_contabile"),
        "netti_cents": prospetto.get("netti_cents"), "totale_complessivo_cents": prospetto.get("totale_complessivo_cents"),
        "stato": CANONICA if nuova_e_piu_recente else SUPERATO,
        "versione": len(stesse) + 1,
        "sostituisce": canonica["id"] if canonica and nuova_e_piu_recente else None,
        "esito": None, "f24_id": None, "candidati": [], "quietanze": [], "riscontro": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db[COLL_PROSPETTI].insert_one(dict(doc))
    if canonica and nuova_e_piu_recente:
        await db[COLL_PROSPETTI].update_one({"id": canonica["id"]}, {"$set": {"stato": SUPERATO}})
    return pid


async def archivia_prospetto(db, *, filename: str, content: bytes, testo: str,
                             source_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Conserva l'originale, deposita il prospetto e prova subito l'aggancio all'F24."""
    from app.routers.documenti import _archive_non_payment_document

    prospetto = leggi_prospetto(testo)
    metadata = {
        "ditta": prospetto["ditta"], "mese": prospetto["mese"], "anno": prospetto["anno"],
        "attesi": len(prospetto["attesi"]), "mancanti": prospetto["mancanti"],
        # Il prospetto non e' un pagamento ne' un obbligo: e' l'indice di cosa l'F24 deve versare.
        "obligation_status": "NON_APPLICABILE",
    }
    archiviato = await _archive_non_payment_document(
        db, filename=filename, content=content, document_type=TIPO,
        metadata=metadata, source_context=source_context,
    )
    documento_id = archiviato.get("doc_id")
    pid = await deposita_prospetto(
        db, prospetto, documento_id=documento_id, filename=filename,
        sha256=hashlib.sha256(content).hexdigest(),
    )
    esito = None
    if pid and documento_id:
        await db["documents_inbox"].update_one(
            {"id": documento_id, "status": "da_verificare"},
            {"$set": {"status": "archiviato", "prospetto_id": pid}},
        )
    if pid:
        try:
            esito = await collega_prospetti(db)
        except Exception as exc:  # noqa: BLE001 - il prospetto resta depositato, lo riprende il giro F24
            logger.error("Prospetto %s depositato ma non agganciato: %s: %s", pid, type(exc).__name__, exc)
    doc = await db[COLL_PROSPETTI].find_one({"id": pid}, {"_id": 0, "esito": 1, "f24_id": 1}) if pid else None
    archiviato.update({
        "workflow": "PROSPETTO_CONTABILE", "prospetto_id": pid, "prospetto": {
            k: prospetto[k] for k in ("ditta", "mese", "anno", "attesi", "mancanti")},
        "abbinamento": doc, "giro": esito,
        "message": (
            f"Prospetto contabile {prospetto['mese']:02d}/{prospetto['anno']}: {len(prospetto['attesi'])} importi attesi"
            + (f", F24 {(doc or {}).get('esito') or 'da cercare'}" if pid else "")
            if pid else
            f"Prospetto contabile conservato ma non letto per intero (mancano: {', '.join(prospetto['mancanti']) or '-'})"
        ),
    })
    return archiviato
