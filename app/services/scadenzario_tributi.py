"""Scadenzario tributi: pagato nei termini, in ritardo, ravveduto o no.

Richiesta del titolare del 30/09/2026: a ogni quietanza il sistema deve dire
se il tributo e' stato pagato in ritardo e, se si', se il ravvedimento e' stato
fatto con i codici giusti e per l'importo giusto; poi un avviso bonario o una
cartella si confrontano con questo scadenzario («avviso n. ... non dovuto:
F24 pagati regolarmente con sanzioni e interessi»).

Per ogni riga a debito di ogni quietanza (codice + periodo):

* **scadenza di legge** — dal modello del commercialista se c'e' (conosce le
  proroghe), altrimenti dalla regola del codice (``scadenza_da_regola``): il 16
  del mese dopo per ritenute, IVA mensile, addizionali trattenute, contributi;
  i codici annuali con la loro data. Sabato, domenica e festivi slittano al
  primo giorno lavorativo; dal 1° al 20 agosto al 20 agosto (art. 3-quater DL
  16/2012). Senza regola la scadenza resta vuota: niente si inventa.
* **ritardo** — giorni tra scadenza e data della quietanza.
* **ravvedimento** — sanzioni (89xx) e interessi (199x, 150x) della stessa
  delega per lo stesso periodo, confrontati con quelli che la legge chiede:
  art. 13 D.Lgs. 472/1997, sanzione base 30% (violazioni fino al 31/08/2024)
  o 25% (dal 01/09/2024, D.Lgs. 87/2024), ridotta per fascia di ritardo;
  interessi al tasso legale giorno per giorno, anno per anno. Per le
  ritenute gli interessi si cumulano al tributo (Ris. AdE 18/E/2023): si
  vedono solo se il dovuto e' noto.

Il confronto e' per **delega e periodo**: la sanzione di un periodo copre
tutti i tributi di quel periodo pagati in ritardo nella stessa delega.

Esiti: PUNTUALE, RAVVEDUTO, RAVVEDIMENTO_INSUFFICIENTE, RITARDO_NON_RAVVEDUTO,
RITARDO_DA_VERIFICARE (sanzione compresa nel codice, es. IMU, o contributi
INPS con sanzioni civili), SCADENZA_NON_DETERMINATA. Ogni esito porta la sua
motivazione con numeri e fonti. Nessun giudizio definitivo: le differenze si
verificano col commercialista.

Lo scadenzario e' persistente (collezione ``scadenzario_tributi``, una riga
per sezione+codice+periodo), riscritto in modo idempotente a ogni quietanza
importata e dal giro dei 30 minuti.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app.constants.codici_ravvedimento import CODICI_RAVVEDIMENTO
from app.services.calendario_lavorativo import e_festivo
from app.services import f24_controllo_incrociato as reg

COLL = "scadenzario_tributi"

PUNTUALE = "PUNTUALE"
RAVVEDUTO = "RAVVEDUTO"
RAVVEDIMENTO_INSUFFICIENTE = "RAVVEDIMENTO_INSUFFICIENTE"
RITARDO_NON_RAVVEDUTO = "RITARDO_NON_RAVVEDUTO"
RITARDO_DA_VERIFICARE = "RITARDO_DA_VERIFICARE"
SCADENZA_NON_DETERMINATA = "SCADENZA_NON_DETERMINATA"

ETICHETTE = {
    PUNTUALE: "Pagato nei termini",
    RAVVEDUTO: "Pagato in ritardo, ravveduto",
    RAVVEDIMENTO_INSUFFICIENTE: "Ravveduto, ma sanzione/interessi non bastano",
    RITARDO_NON_RAVVEDUTO: "Pagato in ritardo, senza ravvedimento",
    RITARDO_DA_VERIFICARE: "In ritardo, ravvedimento da verificare",
    SCADENZA_NON_DETERMINATA: "Scadenza non determinata",
}

# Saggio degli interessi legali (art. 1284 c.c., decreti MEF annuali).
TASSI_LEGALI = {
    2010: Decimal("1"), 2011: Decimal("1.5"), 2012: Decimal("2.5"), 2013: Decimal("2.5"),
    2014: Decimal("1"), 2015: Decimal("0.5"), 2016: Decimal("0.2"), 2017: Decimal("0.1"),
    2018: Decimal("0.3"), 2019: Decimal("0.8"), 2020: Decimal("0.05"), 2021: Decimal("0.01"),
    2022: Decimal("1.25"), 2023: Decimal("5"), 2024: Decimal("2.5"), 2025: Decimal("2"),
    2026: Decimal("1.6"),
}
NUOVO_REGIME = "2024-09-01"  # D.Lgs. 87/2024: violazioni commesse da questa data

# Tolleranza del confronto sanzione/interessi: arrotondamenti del software
# del commercialista (per riga, al centesimo) — 50 centesimi o il 3%.
TOLLERANZA_CENTS = 50
TOLLERANZA_PCT = Decimal("0.03")

# Codici mensili: scadenza il 16 del mese successivo al periodo.
_MENSILI = {
    "1001", "1002", "1004", "1012", "1019", "1020", "1038", "1040", "1045", "1049",
    "1050", "1051", "1052", "1058", "1601", "1602", "1712", "1713",
}
# Addizionali trattenute dal sostituto: l'anno e' quello d'imposta, il mese
# quello della trattenuta (spesso nell'anno dopo). Si prova anno e anno+1.
_ADDIZIONALI = {"3802", "3847", "3848"}
_IVA_MENSILE = {f"60{m:02d}" for m in range(1, 13)}
_IVA_TRIMESTRALE = {"6031": (5, 16), "6032": (8, 16), "6033": (11, 16)}
# Codici annuali: (mese, giorno, anni dopo l'anno di riferimento).
_ANNUALI = {
    "6099": (3, 16, 1),   # IVA annuale
    "6013": (12, 27, 0),  # acconto IVA
    "2001": (6, 30, 0), "2002": (11, 30, 0), "2003": (6, 30, 1),   # IRES
    "3812": (6, 30, 0), "3813": (11, 30, 0), "3800": (6, 30, 1),   # IRAP
    "4033": (6, 30, 0), "4034": (11, 30, 0), "4001": (6, 30, 1),   # IRPEF
    "1668": None,
}
_SANZIONI = {c for c in CODICI_RAVVEDIMENTO if c.startswith("89")}
_INTERESSI = set(CODICI_RAVVEDIMENTO) - _SANZIONI


# ── calendario ───────────────────────────────────────────────────────────

def termine_effettivo(g: date) -> date:
    """Proroga di Ferragosto e slittamento al primo giorno lavorativo."""
    if g.month == 8 and g.day <= 20:
        g = date(g.year, 8, 20)
    while e_festivo(g):
        g += timedelta(days=1)
    return g


def _sedici_mese_dopo(anno: int, mese: int) -> date:
    return date(anno + 1, 1, 16) if mese == 12 else date(anno, mese + 1, 16)


def scadenza_da_regola(sezione: str, codice: str, anno: Optional[int], mese: Optional[int],
                       data_pagamento: Optional[str] = None) -> Tuple[Optional[date], str]:
    """(scadenza, fonte). Scadenza None se la regola non c'e'."""
    c = str(codice or "").upper()
    if not anno:
        return None, "periodo mancante"
    if c in _IVA_MENSILE and c != "6099":
        m = int(c[2:])
        return termine_effettivo(_sedici_mese_dopo(anno, m)), "regola IVA mensile (16 del mese dopo)"
    if c in _IVA_TRIMESTRALE:
        m, g = _IVA_TRIMESTRALE[c]
        return termine_effettivo(date(anno, m, g)), "regola IVA trimestrale"
    if c in _ANNUALI and _ANNUALI[c]:
        m, g, dopo = _ANNUALI[c]
        return termine_effettivo(date(anno + dopo, m, g)), "regola codice annuale (senza proroghe)"
    if mese and (c in _MENSILI or sezione == "sezione_inps"):
        return termine_effettivo(_sedici_mese_dopo(anno, mese)), "regola 16 del mese dopo"
    if mese and c in _ADDIZIONALI:
        # Anno d'imposta o anno della trattenuta: vale quello che da' il
        # ritardo minore (mai un ritardo inventato).
        candidati = [termine_effettivo(_sedici_mese_dopo(a, mese)) for a in (anno, anno + 1)]
        if data_pagamento:
            pagato = date.fromisoformat(data_pagamento)
            dopo = [s for s in candidati if s >= pagato]
            if dopo:
                return min(dopo), "regola addizionali trattenute (anno d'imposta ambiguo)"
        return max(candidati), "regola addizionali trattenute (anno d'imposta ambiguo)"
    return None, "nessuna regola per il codice"


# ── ravvedimento ─────────────────────────────────────────────────────────

def percentuale_ravvedimento(giorni: int, scadenza: date) -> Tuple[Decimal, str, str]:
    """(percentuale sul tributo, regime, fascia) per l'omesso/tardivo versamento."""
    nuovo = scadenza.isoformat() >= NUOVO_REGIME
    anno_dopo = (giorni <= 365)
    if nuovo:
        regime = "D.Lgs. 87/2024 (sanzione base 25%)"
        if giorni <= 14:
            return (Decimal("0.0833") * giorni).quantize(Decimal("0.0001")), regime, f"entro 14 giorni ({giorni} gg × 0,0833%)"
        if giorni <= 30:
            return Decimal("1.25"), regime, "15–30 giorni (12,5% ridotto a 1/10)"
        if giorni <= 90:
            return Decimal("1.3889"), regime, "31–90 giorni (12,5% ridotto a 1/9)"
        if anno_dopo:
            return Decimal("3.125"), regime, "entro un anno (25% ridotto a 1/8)"
        return Decimal("3.5714"), regime, "oltre un anno (25% ridotto a 1/7)"
    regime = "art. 13 D.Lgs. 471/1997 previgente (sanzione base 30%)"
    if giorni <= 14:
        return (Decimal("0.1") * giorni).quantize(Decimal("0.0001")), regime, f"entro 14 giorni ({giorni} gg × 0,1%)"
    if giorni <= 30:
        return Decimal("1.5"), regime, "15–30 giorni (15% ridotto a 1/10)"
    if giorni <= 90:
        return Decimal("1.6667"), regime, "31–90 giorni (15% ridotto a 1/9)"
    if anno_dopo:
        return Decimal("3.75"), regime, "entro un anno (30% ridotto a 1/8)"
    if giorni <= 730:
        return Decimal("4.2857"), regime, "entro due anni (30% ridotto a 1/7)"
    return Decimal("5"), regime, "oltre due anni (30% ridotto a 1/6)"


def interessi_legali_cents(importo_cents: int, dal: date, al: date) -> int:
    """Interessi al tasso legale pro die, spezzati per anno solare (365 giorni)."""
    if al <= dal or importo_cents <= 0:
        return 0
    totale = Decimal(0)
    g = dal
    while g < al:
        fine_anno = date(g.year + 1, 1, 1)
        fino = min(al, fine_anno)
        tasso = TASSI_LEGALI.get(g.year, TASSI_LEGALI[max(TASSI_LEGALI)])
        totale += Decimal(importo_cents) * tasso / Decimal(100) * Decimal((fino - g).days) / Decimal(365)
        g = fino
    return int(totale.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _basta(pagato: int, atteso: int) -> bool:
    margine = max(TOLLERANZA_CENTS, int(Decimal(atteso) * TOLLERANZA_PCT))
    return pagato + margine >= atteso


def _periodo_testo(anno: Optional[int], mese: Optional[int]) -> str:
    return f"{mese:02d}/{anno}" if anno and mese else str(anno or "senza periodo")


def _data_it(d: Optional[str]) -> str:
    return f"{d[8:10]}/{d[5:7]}/{d[:4]}" if d and len(d) >= 10 else "—"


def _euro_it(cents: int) -> str:
    return f"{Decimal(cents) / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " €"


# ── calcolo ──────────────────────────────────────────────────────────────

def calcola(pagamenti: Iterable[Dict[str, Any]],
            scadenze_modello: Optional[Dict[Tuple, str]] = None,
            dovuti: Optional[Dict[Tuple, int]] = None) -> List[Dict[str, Any]]:
    """Una riga per sezione+codice+periodo, con ogni pagamento valutato.

    ``scadenze_modello``: {(sezione, codice, anno, mese): 'AAAA-MM-GG'} dai
    modelli del commercialista; ``dovuti``: {(...): cents} dovuto noto
    (modello o ritenute attese), per vedere gli interessi cumulati al tributo.
    """
    scadenze_modello = scadenze_modello or {}
    dovuti = dovuti or {}
    voci: Dict[Tuple, Dict[str, Any]] = {}

    for p in pagamenti:
        data_p = p.get("data")
        righe = p.get("_righe") or []
        if not data_p or not righe:
            continue
        pagato_il = date.fromisoformat(data_p)
        per_periodo: Dict[Tuple, Dict[str, Any]] = defaultdict(
            lambda: {"tributi": [], "sanzioni": 0, "interessi": 0, "codici_sanzione": set(), "codici_interessi": set()})
        for r in righe:
            debito = int(r.get("importo_debito_cents") or 0)
            if debito <= 0:
                continue
            codice = str(r.get("codice") or "").upper()
            gruppo = per_periodo[(r.get("anno"), r.get("mese"))]
            if codice in _SANZIONI:
                gruppo["sanzioni"] += debito
                gruppo["codici_sanzione"].add(codice)
            elif codice in _INTERESSI:
                gruppo["interessi"] += debito
                gruppo["codici_interessi"].add(codice)
            else:
                gruppo["tributi"].append(r)

        prima = (p.get("quietanze") or [{}])[0]
        for (anno, mese), gruppo in per_periodo.items():
            valutati = []
            for r in gruppo["tributi"]:
                sezione, codice = str(r.get("sezione") or ""), str(r.get("codice") or "").upper()
                chiave = (sezione, codice, anno, mese)
                importo = int(r.get("importo_debito_cents") or 0)
                if chiave in scadenze_modello:
                    scad = termine_effettivo(date.fromisoformat(scadenze_modello[chiave]))
                    fonte = "F24 del commercialista"
                else:
                    scad, fonte = scadenza_da_regola(sezione, codice, anno, mese, data_p)
                giorni = (pagato_il - scad).days if scad else None
                valutati.append({"r": r, "chiave": chiave, "importo": importo, "scadenza": scad,
                                 "fonte": fonte, "giorni": giorni})

            # Sanzione e interessi attesi per i tributi in ritardo del periodo.
            ritardo = [v for v in valutati if v["giorni"] is not None and v["giorni"] > 0]
            sanz_attesa = int_attesi = 0
            dettagli_calcolo = []
            for v in ritardo:
                dovuto = dovuti.get(v["chiave"])
                base = min(v["importo"], dovuto) if dovuto else v["importo"]
                pct, regime, fascia = percentuale_ravvedimento(v["giorni"], v["scadenza"])
                s = int((Decimal(base) * pct / 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
                i = interessi_legali_cents(base, v["scadenza"], pagato_il)
                sanz_attesa += s
                int_attesi += i
                v.update({"pct": pct, "regime": regime, "fascia": fascia, "sanzione_attesa": s,
                          "interessi_attesi": i, "base": base,
                          "interessi_cumulati": max(0, v["importo"] - dovuto) if dovuto else None})
                dettagli_calcolo.append(v)
            interessi_cumulati = sum(v.get("interessi_cumulati") or 0 for v in ritardo)
            interessi_pagati = gruppo["interessi"] + interessi_cumulati
            sezioni_ritardo = {v["chiave"][0] for v in ritardo}
            sanzione_nel_codice = bool(sezioni_ritardo & {"sezione_tributi_locali", "sezione_inps", "sezione_inail"})

            for v in valutati:
                if v["scadenza"] is None:
                    stato = SCADENZA_NON_DETERMINATA
                    motivo = f"nessuna scadenza: {v['fonte']}"
                elif v["giorni"] <= 0:
                    stato = PUNTUALE
                    motivo = (f"pagato il {_data_it(data_p)}, scadenza {_data_it(v['scadenza'].isoformat())} "
                              f"({v['fonte']})")
                elif gruppo["sanzioni"] or gruppo["interessi"]:
                    basta_s = _basta(gruppo["sanzioni"], sanz_attesa)
                    # Interessi: si giudicano solo se si vedono (codice
                    # interessi o dovuto noto); cumulati e ignoti non bocciano.
                    visibili = gruppo["interessi"] or any(x.get("interessi_cumulati") is not None for x in ritardo)
                    basta_i = (not visibili) or _basta(interessi_pagati, int_attesi)
                    stato = RAVVEDUTO if (basta_s and basta_i) else RAVVEDIMENTO_INSUFFICIENTE
                    motivo = (
                        f"pagato il {_data_it(data_p)}, {v['giorni']} giorni dopo la scadenza "
                        f"{_data_it(v['scadenza'].isoformat())} ({v['fonte']}); {v['fascia']}, {v['regime']}. "
                        f"Periodo {_periodo_testo(anno, mese)} nella delega: sanzioni versate "
                        f"{_euro_it(gruppo['sanzioni'])} ({', '.join(sorted(gruppo['codici_sanzione'])) or 'nessun codice'}) "
                        f"su {_euro_it(sanz_attesa)} attese; interessi "
                        + (f"versati {_euro_it(interessi_pagati)} su {_euro_it(int_attesi)} attesi"
                           if visibili else f"attesi {_euro_it(int_attesi)}, cumulati al tributo (non separabili)")
                    )
                elif sanzione_nel_codice and v["chiave"][0] in {"sezione_tributi_locali", "sezione_inps", "sezione_inail"}:
                    stato = RITARDO_DA_VERIFICARE
                    motivo = (f"pagato il {_data_it(data_p)}, {v['giorni']} giorni dopo la scadenza "
                              f"{_data_it(v['scadenza'].isoformat())}: per questa sezione sanzioni e interessi "
                              "si versano nello stesso codice o come sanzioni civili: da verificare")
                else:
                    stato = RITARDO_NON_RAVVEDUTO
                    motivo = (f"pagato il {_data_it(data_p)}, {v['giorni']} giorni dopo la scadenza "
                              f"{_data_it(v['scadenza'].isoformat())} ({v['fonte']}), senza sanzione ne' interessi "
                              f"nella delega: ravvedimento atteso {_euro_it(v.get('sanzione_attesa', 0))} di sanzione "
                              f"({v.get('fascia')}) e {_euro_it(v.get('interessi_attesi', 0))} di interessi")

                voce = voci.get(v["chiave"])
                if voce is None:
                    sezione, codice, a, m = v["chiave"]
                    voce = voci[v["chiave"]] = {
                        "chiave": f"{sezione}|{codice}|{a or ''}|{m or ''}", "sezione": sezione,
                        "codice": codice, "anno": a, "mese": m, "periodo": _periodo_testo(a, m),
                        "scadenza": v["scadenza"].isoformat() if v["scadenza"] else None,
                        "scadenza_fonte": v["fonte"], "pagamenti": [],
                    }
                voce["pagamenti"].append({
                    "data": data_p, "protocollo": p.get("protocollo"), "importo_cents": v["importo"],
                    "giorni_ritardo": v["giorni"], "stato": stato, "motivazione": motivo,
                    "quietanza_id": prima.get("id"), "pdf_url": prima.get("pdf_url"),
                    "compensazione_totale": bool(p.get("compensazione_totale")),
                    "sanzioni_periodo_cents": gruppo["sanzioni"],
                    "interessi_periodo_cents": gruppo["interessi"],
                    "sanzione_attesa_cents": v.get("sanzione_attesa", 0),
                    "interessi_attesi_cents": v.get("interessi_attesi", 0),
                    "sanzioni_periodo_attese_cents": sanz_attesa,
                    "interessi_periodo_attesi_cents": int_attesi,
                    "fascia": v.get("fascia"), "regime": v.get("regime"),
                })

    gravita = [RAVVEDIMENTO_INSUFFICIENTE, RITARDO_NON_RAVVEDUTO, RITARDO_DA_VERIFICARE,
               SCADENZA_NON_DETERMINATA, RAVVEDUTO, PUNTUALE]
    risultato = []
    for voce in voci.values():
        voce["pagamenti"].sort(key=lambda x: x["data"])
        stati = {x["stato"] for x in voce["pagamenti"]}
        voce["stato"] = next(s for s in gravita if s in stati)
        voce["stato_label"] = ETICHETTE[voce["stato"]]
        voce["pagato_cents"] = sum(x["importo_cents"] for x in voce["pagamenti"])
        voce["ultimo_pagamento"] = voce["pagamenti"][-1]["data"]
        voce["motivazione"] = next(x["motivazione"] for x in voce["pagamenti"] if x["stato"] == voce["stato"])
        risultato.append(voce)
    risultato.sort(key=lambda v: (-(v["anno"] or 0), -(v["mese"] or 0), v["codice"]))
    return risultato


async def carica(db) -> List[Dict[str, Any]]:
    """Calcola dallo stesso registro unico di Tributi (modelli, quietanze, ritenute)."""
    from app.services import tributi_per_codice as tributi

    registro = await reg.carica_registro(db)
    ritenute = await db[tributi.COLL_RITENUTE].find({}, {"_id": 0}).to_list(5000)
    voci = tributi.costruisci(registro, ritenute)
    scadenze = {}
    dovuti = {}
    for v in voci:
        k = (v["sezione"], v["codice"], v["anno"], v["mese"])
        if any(d["tipo"] in ("commercialista", "ritenuta") for d in v["documenti"]) and v.get("scadenza"):
            scadenze[k] = v["scadenza"]
        if v.get("dovuto_cents"):
            dovuti[k] = v["dovuto_cents"]
    quietanze = [q for q in registro["quietanze"] if q.get("righe")]
    return calcola(reg.pagamenti_da_quietanze(quietanze), scadenze, dovuti)


async def aggiorna(db) -> Dict[str, int]:
    """Riscrive lo scadenzario persistente (upsert per chiave, idempotente)."""
    voci = await carica(db)
    ora = datetime.now(timezone.utc).isoformat()
    scritte = invariate = 0
    for v in voci:
        attuale = await db[COLL].find_one({"chiave": v["chiave"]}, {"_id": 0, "aggiornato_il": 0, "stato_dal": 0})
        if attuale == v:
            invariate += 1
            continue
        extra = {"aggiornato_il": ora}
        if not attuale or attuale.get("stato") != v["stato"]:
            extra["stato_dal"] = ora
        await db[COLL].update_one({"chiave": v["chiave"]}, {"$set": {**v, **extra}}, upsert=True)
        scritte += 1
    return {"voci": len(voci), "scritte": scritte, "invariate": invariate}


def riepilogo(voci: List[Dict[str, Any]], *, anno: Optional[int] = None, stato: Optional[str] = None,
              cerca: Optional[str] = None) -> Dict[str, Any]:
    scelte = [
        v for v in voci
        if (not anno or v.get("anno") == anno)
        and (not stato or v.get("stato") == stato)
        and (not cerca or str(cerca).lower() in f"{v['codice']} {v['periodo']}".lower())
    ]
    per_stato: Dict[str, int] = defaultdict(int)
    for v in scelte:
        per_stato[v["stato"]] += 1
    return {
        "voci": scelte,
        "per_stato": [{"id": k, "label": ETICHETTE[k], "n": per_stato.get(k, 0)} for k in ETICHETTE],
        "anni": sorted({v["anno"] for v in voci if v.get("anno")}, reverse=True),
    }


# ── avviso bonario / cartella: dovuto o no ───────────────────────────────

NON_DOVUTO = "NON_DOVUTO"
DOVUTO_DIFFERENZA = "DOVUTO_DIFFERENZA"
DOVUTO = "DOVUTO"
DA_VERIFICARE = "DA_VERIFICARE"


def verdetto_riga(codice: str, anno: Optional[int], mese: Optional[int], importo_richiesto_cents: int,
                  voci: List[Dict[str, Any]], *, sanzioni_richieste_cents: int = 0,
                  interessi_richiesti_cents: int = 0, data_versamento_ade: Optional[str] = None) -> Dict[str, Any]:
    """La riga di un avviso (codice, periodo, importo) contro lo scadenzario.

    Una riga «non dovuta» porta sempre la prova: data, protocollo e importo
    della quietanza, e — se in ritardo — sanzioni e interessi versati.
    """
    c = str(codice or "").upper()
    trovate = [v for v in voci if v["codice"] == c and v.get("anno") == anno
               and (mese is None or v.get("mese") == mese)]
    prove = [
        {"data": p["data"], "protocollo": p.get("protocollo"), "importo_cents": p["importo_cents"],
         "stato": p["stato"], "motivazione": p["motivazione"], "pdf_url": p.get("pdf_url")}
        for v in trovate for p in v["pagamenti"]
    ]
    pagato = sum(p["importo_cents"] for p in prove)
    stati = {p["stato"] for p in prove}
    periodo = _periodo_testo(anno, mese)
    base = {"codice": c, "periodo": periodo, "importo_richiesto_cents": importo_richiesto_cents,
            "sanzioni_richieste_cents": sanzioni_richieste_cents,
            "interessi_richiesti_cents": interessi_richiesti_cents,
            "pagato_cents": pagato, "prove": prove}
    note = []
    if data_versamento_ade and prove and data_versamento_ade not in {p["data"] for p in prove}:
        note.append(f"l'Agenzia indica il versamento del {_data_it(data_versamento_ade)}, le quietanze dicono "
                    + ", ".join(_data_it(p["data"]) for p in prove) + ": chiedere lo sgravio allegando la quietanza")
    if not prove:
        return {**base, "verdetto": DOVUTO, "differenza_cents": importo_richiesto_cents, "note": note,
                "motivazione": f"nessuna quietanza per {c} {periodo}: se non pagato con un F24 che manca in "
                               "archivio, l'importo è dovuto"}
    manca = max(0, importo_richiesto_cents - pagato)
    if stati <= {PUNTUALE} and not manca:
        verdetto, motivo = NON_DOVUTO, (f"{c} {periodo} pagato nei termini: "
                                        + "; ".join(f"{_data_it(p['data'])} prot. {p['protocollo'] or '—'} "
                                                    f"{_euro_it(p['importo_cents'])}" for p in prove))
    elif stati <= {PUNTUALE, RAVVEDUTO} and not manca:
        verdetto, motivo = NON_DOVUTO, (f"{c} {periodo} pagato in ritardo e ravveduto con sanzioni e interessi: "
                                        + " · ".join(p["motivazione"] for p in prove if p["stato"] == RAVVEDUTO))
    elif manca:
        verdetto, motivo = DOVUTO_DIFFERENZA, (f"richiesti {_euro_it(importo_richiesto_cents)}, versati "
                                               f"{_euro_it(pagato)}: differenza {_euro_it(manca)}")
    elif RAVVEDIMENTO_INSUFFICIENTE in stati or RITARDO_NON_RAVVEDUTO in stati:
        verdetto = DOVUTO_DIFFERENZA
        attesa = sum(p.get("sanzione_attesa_cents", 0) + p.get("interessi_attesi_cents", 0)
                     for v in trovate for p in v["pagamenti"])
        motivo = ("tributo versato, ma in ritardo senza ravvedimento sufficiente: sono dovuti sanzione e "
                  f"interessi (con il ravvedimento sarebbero stati circa {_euro_it(attesa)}; con l'avviso "
                  "bonario la sanzione è ridotta a un terzo se si paga entro 60 giorni)")
        manca = max(0, sanzioni_richieste_cents + interessi_richiesti_cents)
    else:
        verdetto, motivo = DA_VERIFICARE, " · ".join(p["motivazione"] for p in prove)
    return {**base, "verdetto": verdetto, "differenza_cents": manca, "motivazione": motivo, "note": note}


def verdetto_avviso(numero: Optional[str], righe: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Il verdetto complessivo e il prospetto delle differenze."""
    da_pagare = sum(r["differenza_cents"] for r in righe if r["verdetto"] in (DOVUTO, DOVUTO_DIFFERENZA))
    ref = f"Avviso n. {numero}" if numero else "L'avviso"
    if righe and all(r["verdetto"] == NON_DOVUTO for r in righe):
        ravv = any(p["stato"] == RAVVEDUTO for r in righe for p in r["prove"])
        testo = (f"{ref} non dovuto: F24 pagati regolarmente"
                 + (" con sanzioni e interessi da ravvedimento" if ravv else " nei termini")
                 + ". Chiedere l'annullamento (CIVIS o commercialista) allegando le quietanze.")
        esito = NON_DOVUTO
    elif da_pagare:
        testo = f"{ref}: dovuti {_euro_it(da_pagare)} secondo le quietanze in archivio (prospetto per riga)."
        esito = DOVUTO_DIFFERENZA
    else:
        testo = f"{ref}: righe da verificare col commercialista (vedi motivazioni)."
        esito = DA_VERIFICARE
    return {"esito": esito, "testo": testo, "da_pagare_cents": da_pagare,
            "non_dovuto_cents": sum(r["importo_richiesto_cents"] for r in righe if r["verdetto"] == NON_DOVUTO)}
