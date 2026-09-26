"""Piano tributi: cio' che deve arrivare ogni anno, e se e' arrivato e pagato.

Il registro F24 (``f24_controllo_incrociato``) vede solo i modelli che sono
arrivati: un tributo mai arrivato non lo segnala nessuno. Qui il titolare
dichiara una volta i tributi ricorrenti (voci del piano) e ogni voce apre,
per ogni periodo dell'anno, un'**attesa** (``expectation_policy``) che le
prove successive possono soltanto soddisfare:

* nessun F24 e scadenza passata → «manca F24»;
* F24 arrivato senza prova di pagamento → «da pagare» (o in ritardo);
* sola quietanza, o addebito compatibile non ancora agganciato →
  ``DA_VERIFICARE``: la quietanza non sostituisce la banca;
* addebito bancario agganciato al modello → ``SODDISFATTO``.

L'importo non si stima mai: e' quello delle righe del modello arrivato,
altrimenti resta vuoto. Nessuna scrittura sui modelli F24: il piano legge il
registro unico e non ne crea un secondo.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app.services import f24_controllo_incrociato as registro_f24
from app.services.expectation_policy import (
    ExpectationStatus, expectation_fields, mandatory_expectations_closed,
)

COLL_PIANO = "piano_tributi"
TIPO_ATTESA = "tributo_piano"
OWNER_ATTESA = "fiscale"

# Stati di una casella, con la parola che la pagina scrive accanto al colore.
PAGATO = "pagato"
DA_CONFERMARE_BANCA = "da_confermare_banca"
QUIETANZA_SENZA_BANCA = "quietanza_senza_banca"
DA_PAGARE = "da_pagare"
SCADUTO_NON_PAGATO = "scaduto_non_pagato"
MANCA_F24 = "manca_f24"
FUTURO = "futuro"
DA_VERIFICARE_A_MANO = "da_verificare_a_mano"
CREDITO_USATO = "credito_usato"
CREDITO_ASSENTE = "credito_assente"

ETICHETTE = {
    PAGATO: "Pagato (banca)",
    DA_CONFERMARE_BANCA: "Addebito da confermare",
    QUIETANZA_SENZA_BANCA: "Quietanza, banca da verificare",
    DA_PAGARE: "F24 arrivato, da pagare",
    SCADUTO_NON_PAGATO: "F24 scaduto, nessun pagamento",
    MANCA_F24: "Manca F24",
    FUTURO: "Non ancora scaduto",
    DA_VERIFICARE_A_MANO: "Fuori F24: da verificare",
    CREDITO_USATO: "Credito usato",
    CREDITO_ASSENTE: "Nessun credito",
}

_STATO_ATTESA = {
    PAGATO: ExpectationStatus.SODDISFATTO.value,
    DA_CONFERMARE_BANCA: ExpectationStatus.DA_VERIFICARE.value,
    QUIETANZA_SENZA_BANCA: ExpectationStatus.DA_VERIFICARE.value,
    DA_VERIFICARE_A_MANO: ExpectationStatus.DA_VERIFICARE.value,
    DA_PAGARE: ExpectationStatus.ATTESO.value,
    SCADUTO_NON_PAGATO: ExpectationStatus.ATTESO.value,
    MANCA_F24: ExpectationStatus.ATTESO.value,
    FUTURO: ExpectationStatus.ATTESO.value,
    CREDITO_USATO: ExpectationStatus.NON_APPLICABILE.value,
    CREDITO_ASSENTE: ExpectationStatus.NON_APPLICABILE.value,
}

MESI_TUTTI = list(range(1, 13))
MESI_RATE_SALDO = list(range(1, 12))       # rate del saldo addizionali: gennaio-novembre
MESI_RATE_ACCONTO = list(range(3, 12))     # acconto addizionale comunale: marzo-novembre


def _voce(id_: str, gruppo: str, etichetta: str, codici: List[str], **kw: Any) -> Dict[str, Any]:
    return {"id": id_, "gruppo": gruppo, "etichetta": etichetta, "codici": codici,
            "attivo": True, "obbligatorio": kw.pop("obbligatorio", True), **kw}


# Voci confermate dal titolare il 26/09/2026 (ricavate dagli F24 2025-2026),
# piu' IRES, IRAP, IMU e COSAP. Codici verificati sull'Agenzia delle Entrate.
#   periodo = "mese":       riga con anno = anno piano + anno_offset e mese in ``mesi``;
#                           scadenza il 16 del mese dopo.
#   periodo = "anno":       riga con anno = anno piano + anno_offset; scadenza fissa;
#                           ``versamento_entro`` separa acconto e saldo con lo stesso codice.
#   periodo = "versamento": modello versato nel mese della scadenza (INAIL).
#   periodo = "manuale":    fuori F24, nessuna prova automatica.
PIANO_BASE: List[Dict[str, Any]] = [
    _voce("ritenute_1001", "Erario", "Ritenute lavoro dipendente", ["1001"],
          periodo="mese", mesi=MESI_TUTTI, anno_offset=0),
    _voce("inps_dm10", "INPS", "Contributi dipendenti (DM10)", ["DM10"],
          periodo="mese", mesi=MESI_TUTTI, anno_offset=0),
    _voce("inps_cxx", "INPS", "Gestione separata (CXX)", ["CXX"],
          periodo="mese", mesi=MESI_TUTTI, anno_offset=0),
    _voce("add_regionale_3802", "Regione", "Addizionale regionale, rate del saldo", ["3802"],
          periodo="mese", mesi=MESI_RATE_SALDO, anno_offset=-1),
    _voce("add_comunale_saldo_3848", "Comune", "Addizionale comunale, rate del saldo", ["3848"],
          periodo="mese", mesi=MESI_RATE_SALDO, anno_offset=-1),
    _voce("add_comunale_acconto_3847", "Comune", "Addizionale comunale, acconto", ["3847"],
          periodo="mese", mesi=MESI_RATE_ACCONTO, anno_offset=0),
    _voce("credito_1704", "Crediti in compensazione", "Credito L. 207/2024", ["1704"],
          periodo="mese", mesi=MESI_TUTTI, anno_offset=0, obbligatorio=False, natura="credito"),
    _voce("credito_1701", "Crediti in compensazione", "Trattamento integrativo", ["1701"],
          periodo="mese", mesi=MESI_TUTTI, anno_offset=None, obbligatorio=False, natura="credito"),
    _voce("inail", "INAIL", "Autoliquidazione INAIL", ["P"], sezione="sezione_inail",
          periodo="versamento", scadenze=[(2, 16)]),
    _voce("ires_saldo", "IRES", "IRES saldo", ["2003"],
          periodo="anno", anno_offset=-1, scadenze=[(6, 30)]),
    _voce("ires_acconto_1", "IRES", "IRES acconto prima rata", ["2001"],
          periodo="anno", anno_offset=0, scadenze=[(6, 30)]),
    _voce("ires_acconto_2", "IRES", "IRES acconto seconda rata", ["2002"],
          periodo="anno", anno_offset=0, scadenze=[(11, 30)]),
    _voce("irap_saldo", "IRAP", "IRAP saldo", ["3800"],
          periodo="anno", anno_offset=-1, scadenze=[(6, 30)]),
    _voce("irap_acconto_1", "IRAP", "IRAP acconto prima rata", ["3812"],
          periodo="anno", anno_offset=0, scadenze=[(6, 30)]),
    _voce("irap_acconto_2", "IRAP", "IRAP acconto seconda rata", ["3813"],
          periodo="anno", anno_offset=0, scadenze=[(11, 30)]),
    _voce("imu_acconto", "IMU", "IMU acconto", ["3918", "3930", "3925", "3916", "3914"],
          periodo="anno", anno_offset=0, scadenze=[(6, 16)], versamento_entro=(8, 31)),
    _voce("imu_saldo", "IMU", "IMU saldo", ["3918", "3930", "3925", "3916", "3914"],
          periodo="anno", anno_offset=0, scadenze=[(12, 16)], versamento_dal=(9, 1)),
    _voce("cosap", "Comune", "COSAP / canone unico (suolo pubblico)", [],
          periodo="manuale", scadenze=[],
          nota="Non si paga con F24 ma con avviso del Comune: scadenza e prova da impostare."),
]


# ── calendario delle scadenze ─────────────────────────────────────────────

def _pasqua(anno: int) -> date:
    a, b, c = anno % 19, anno // 100, anno % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    lettera = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * lettera) // 451
    mese = (h + lettera - 7 * m + 114) // 31
    giorno = (h + lettera - 7 * m + 114) % 31 + 1
    return date(anno, mese, giorno)


def _festivo(g: date) -> bool:
    fissi = {(1, 1), (1, 6), (4, 25), (5, 1), (6, 2), (8, 15), (11, 1), (12, 8), (12, 25), (12, 26)}
    return g.weekday() >= 5 or (g.month, g.day) in fissi or g == _pasqua(g.year) + timedelta(days=1)


def scadenza_effettiva(nominale: date) -> date:
    """Il 16 agosto slitta al 20 (proroga estiva); un festivo al primo lavorativo."""
    if (nominale.month, nominale.day) == (8, 16):
        nominale = date(nominale.year, 8, 20)
    while _festivo(nominale):
        nominale += timedelta(days=1)
    return nominale


def _scadenza_mensile(anno: int, mese: int) -> date:
    if mese == 12:
        return scadenza_effettiva(date(anno + 1, 1, 16))
    return scadenza_effettiva(date(anno, mese + 1, 16))


# ── il piano salvato ──────────────────────────────────────────────────────

def _serializza(voce: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(voce)
    for chiave in ("scadenze",):
        if chiave in out:
            out[chiave] = [list(s) for s in out[chiave]]
    for chiave in ("versamento_entro", "versamento_dal"):
        if out.get(chiave):
            out[chiave] = list(out[chiave])
    return out


async def voci_piano(db) -> List[Dict[str, Any]]:
    """Le voci salvate; al primo uso si scrive il piano di base, una volta."""
    salvate = await db[COLL_PIANO].find({}, {"_id": 0}).to_list(500)
    noti = {v.get("id") for v in salvate}
    # Si aggiungono solo le voci di base mai salvate: una voce che il titolare
    # ha modificato o spento resta com'e'.
    mancanti = [_serializza(v) for v in PIANO_BASE if v["id"] not in noti]
    if mancanti:
        ora = datetime.now(timezone.utc).isoformat()
        await db[COLL_PIANO].insert_many([{**v, "creato_il": ora, "origine": "base"} for v in mancanti])
        salvate = await db[COLL_PIANO].find({}, {"_id": 0}).to_list(500)
    ordine = {v["id"]: i for i, v in enumerate(PIANO_BASE)}
    return sorted(salvate, key=lambda v: (ordine.get(v.get("id"), 999), v.get("etichetta") or ""))


CAMPI_MODIFICABILI = {"attivo", "etichetta", "scadenze", "nota", "mesi", "obbligatorio"}


async def aggiorna_voce(db, voce_id: str, modifiche: Dict[str, Any]) -> Dict[str, Any]:
    await voci_piano(db)
    esistente = await db[COLL_PIANO].find_one({"id": voce_id}, {"_id": 0})
    if not esistente:
        raise KeyError(voce_id)
    campi = {k: v for k, v in modifiche.items() if k in CAMPI_MODIFICABILI}
    if "scadenze" in campi:
        scadenze = []
        for s in campi["scadenze"] or []:
            mese, giorno = int(s[0]), int(s[1])
            date(2024, mese, giorno)  # ValueError se la data non esiste
            scadenze.append([mese, giorno])
        campi["scadenze"] = scadenze
    if "mesi" in campi:
        campi["mesi"] = sorted({int(m) for m in campi["mesi"] or [] if 1 <= int(m) <= 12})
    if not campi:
        return esistente
    campi["aggiornato_il"] = datetime.now(timezone.utc).isoformat()
    await db[COLL_PIANO].update_one({"id": voce_id}, {"$set": campi})
    return {**esistente, **campi}


async def aggiungi_voce(db, dati: Dict[str, Any]) -> Dict[str, Any]:
    """Voce nuova su codici tributo scelti dal titolare (es. un codice che compare)."""
    await voci_piano(db)
    codici = [registro_f24.normalizza_codice(c) for c in dati.get("codici") or [] if str(c).strip()]
    periodo = dati.get("periodo") or "mese"
    if periodo not in ("mese", "anno", "versamento", "manuale"):
        raise ValueError("periodo non valido")
    if periodo != "manuale" and not codici:
        raise ValueError("serve almeno un codice tributo")
    voce = {
        "id": f"utente_{uuid.uuid4().hex[:10]}", "gruppo": dati.get("gruppo") or "Altri",
        "etichetta": dati.get("etichetta") or " / ".join(codici) or "Voce manuale",
        "codici": codici, "attivo": True, "obbligatorio": bool(dati.get("obbligatorio", True)),
        "periodo": periodo, "mesi": dati.get("mesi") or MESI_TUTTI,
        "anno_offset": int(dati.get("anno_offset") or 0), "scadenze": dati.get("scadenze") or [],
        "origine": "titolare", "creato_il": datetime.now(timezone.utc).isoformat(),
    }
    await db[COLL_PIANO].insert_one(dict(voce))
    return voce


# ── confronto con il registro F24 ─────────────────────────────────────────

def _euro(cents: int) -> str:
    return str((Decimal(cents) / 100).quantize(Decimal("0.01")))


def _data(testo: Optional[str]) -> Optional[date]:
    try:
        return date.fromisoformat(str(testo)[:10]) if testo else None
    except ValueError:
        return None


def _modelli_con_righe(registro: Dict[str, Any]) -> List[Tuple[Dict[str, Any], List[Dict[str, Any]]]]:
    return [(f24, registro_f24.righe_modello(f24)) for f24 in registro["f24"]]


def _righe_voce(voce: Dict[str, Any], righe: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    codici = {registro_f24.normalizza_codice(c) for c in voce.get("codici") or []}
    sezione = voce.get("sezione")
    return [r for r in righe if r["codice"] in codici and (not sezione or r["sezione"] == sezione)]


def _chiave_doppione(f24: Dict[str, Any]) -> Tuple[Any, Any]:
    return registro_f24.data_versamento_modello(f24), registro_f24.saldo_modello_cents(f24)


def _stato_da_prove(prove: Dict[str, Any], scadenza: Optional[date], oggi: date) -> str:
    if prove["pagato_banca"]:
        return PAGATO
    if prove["addebito_compatibile_non_agganciato"]:
        return DA_CONFERMARE_BANCA
    if prove["quietanza_presente"]:
        return QUIETANZA_SENZA_BANCA
    if scadenza and scadenza < oggi:
        return SCADUTO_NON_PAGATO
    return DA_PAGARE


_PRIORITA = [PAGATO, DA_CONFERMARE_BANCA, QUIETANZA_SENZA_BANCA, SCADUTO_NON_PAGATO, DA_PAGARE]


def _casella(
    voce: Dict[str, Any], anno: int, chiave_periodo: str, etichetta_periodo: str,
    scadenza: Optional[date], trovati: List[Tuple[Dict[str, Any], List[Dict[str, Any]]]],
    registro: Dict[str, Any], oggi: date,
) -> Dict[str, Any]:
    credito = voce.get("natura") == "credito"
    modelli: List[Dict[str, Any]] = []
    for f24, righe in trovati:
        prove = registro_f24.prove_modello(f24, registro)
        stato = _stato_da_prove(prove, scadenza, oggi)
        modelli.append({
            "f24_id": f24.get("id"),
            "data_versamento": prove["data_versamento"],
            "stato": stato,
            "debito_cents": sum(r["importo_debito_cents"] for r in righe),
            "credito_cents": sum(r["importo_credito_cents"] for r in righe),
            "movimenti": [
                {"id": m["movimento_id"], "data": m["data"], "agganciato": m["agganciato"],
                 "link": m["link"]}
                for m in prove["addebiti_banca"] if m.get("movimento_id")
            ],
            "quietanze": [q["quietanza_id"] for q in prove["quietanze"] if q.get("quietanza_id")],
            "pdf_url": registro_f24.PDF_F24_URL.format(f24_id=f24.get("id")),
            "_doppione": _chiave_doppione(f24),
        })
    # Due modelli con stessa data e stesso saldo sono lo stesso versamento
    # registrato due volte: contano una volta, e la casella lo dice.
    per_chiave: Dict[Tuple[Any, Any], List[Dict[str, Any]]] = {}
    for m in modelli:
        per_chiave.setdefault(m["_doppione"], []).append(m)
    versamenti = []
    doppioni = 0
    for gruppo in per_chiave.values():
        gruppo.sort(key=lambda m: _PRIORITA.index(m["stato"]))
        versamenti.append(gruppo[0])
        doppioni += len(gruppo) - 1
    for m in modelli:
        m.pop("_doppione", None)

    if credito:
        stato = CREDITO_USATO if versamenti else CREDITO_ASSENTE
    elif voce.get("periodo") == "manuale":
        stato = DA_VERIFICARE_A_MANO
    elif not versamenti:
        stato = MANCA_F24 if scadenza and scadenza < oggi else FUTURO
    else:
        # Piu' versamenti diversi nello stesso periodo (es. un ravvedimento):
        # la casella prende lo stato peggiore, perche' uno non basta a
        # chiudere l'altro.
        stato = max((m["stato"] for m in versamenti), key=_PRIORITA.index)

    debito = sum(m["debito_cents"] for m in versamenti)
    credito_cents = sum(m["credito_cents"] for m in versamenti)
    return {
        "periodo": chiave_periodo,
        "etichetta_periodo": etichetta_periodo,
        "scadenza": scadenza.isoformat() if scadenza else None,
        "stato": stato,
        "etichetta_stato": ETICHETTE[stato],
        "importo": _euro(debito) if versamenti and debito else None,
        "credito": _euro(credito_cents) if versamenti and credito_cents else None,
        "modelli": modelli,
        "modelli_doppi": doppioni,
        **expectation_fields(
            expectation_type=TIPO_ATTESA, owner=OWNER_ATTESA,
            source_fact_id=f"piano:{voce['id']}:{anno}:{chiave_periodo}",
        ),
        "expectation_status": _STATO_ATTESA[stato],
        "mandatory": bool(voce.get("obbligatorio", True)) and not credito,
    }


def _anno_riga(voce: Dict[str, Any], anno: int) -> Optional[int]:
    offset = voce.get("anno_offset")
    return None if offset is None else anno + int(offset)


def caselle_voce(voce: Dict[str, Any], anno: int, modelli, registro, oggi: date) -> List[Dict[str, Any]]:
    periodo = voce.get("periodo")
    caselle: List[Dict[str, Any]] = []
    if periodo == "mese":
        anno_riga = _anno_riga(voce, anno)
        for mese in voce.get("mesi") or MESI_TUTTI:
            trovati = []
            for f24, righe in modelli:
                mie = [r for r in _righe_voce(voce, righe)
                       if r["mese"] == mese and (anno_riga is None or r["anno"] == anno_riga)]
                if anno_riga is None:
                    # Crediti con anno di riferimento variabile: conta il mese di versamento.
                    dv = _data(registro_f24.data_versamento_modello(f24))
                    atteso = _scadenza_mensile(anno, mese)
                    mie = [r for r in _righe_voce(voce, righe)] if (
                        dv and (dv.year, dv.month) == (atteso.year, atteso.month)) else []
                if mie:
                    trovati.append((f24, mie))
            caselle.append(_casella(voce, anno, f"{mese:02d}", f"{mese:02d}/{anno}",
                                    _scadenza_mensile(anno, mese), trovati, registro, oggi))
    elif periodo == "anno":
        anno_riga = _anno_riga(voce, anno)
        entro = voce.get("versamento_entro")
        dal = voce.get("versamento_dal")
        for mese_s, giorno_s in voce.get("scadenze") or []:
            scadenza = scadenza_effettiva(date(anno, int(mese_s), int(giorno_s)))
            trovati = []
            for f24, righe in modelli:
                mie = [r for r in _righe_voce(voce, righe) if r["anno"] == anno_riga]
                dv = _data(registro_f24.data_versamento_modello(f24))
                if entro and dv and dv > date(anno, int(entro[0]), int(entro[1])):
                    mie = []
                if dal and dv and dv < date(anno, int(dal[0]), int(dal[1])):
                    mie = []
                if mie:
                    trovati.append((f24, mie))
            caselle.append(_casella(voce, anno, f"{int(mese_s):02d}", f"scad. {scadenza:%d/%m/%Y}",
                                    scadenza, trovati, registro, oggi))
    elif periodo == "versamento":
        for mese_s, giorno_s in voce.get("scadenze") or []:
            scadenza = scadenza_effettiva(date(anno, int(mese_s), int(giorno_s)))
            trovati = []
            for f24, righe in modelli:
                dv = _data(registro_f24.data_versamento_modello(f24))
                mie = _righe_voce(voce, righe)
                if mie and dv and (dv.year, dv.month) == (scadenza.year, scadenza.month):
                    trovati.append((f24, mie))
            caselle.append(_casella(voce, anno, f"{int(mese_s):02d}", f"scad. {scadenza:%d/%m/%Y}",
                                    scadenza, trovati, registro, oggi))
    else:  # manuale
        for mese_s, giorno_s in voce.get("scadenze") or []:
            scadenza = scadenza_effettiva(date(anno, int(mese_s), int(giorno_s)))
            caselle.append(_casella(voce, anno, f"{int(mese_s):02d}", f"scad. {scadenza:%d/%m/%Y}",
                                    scadenza, [], registro, oggi))
    return caselle


def _codici_fuori_piano(voci, modelli, anno: int) -> List[Dict[str, Any]]:
    """Codici versati nell'anno che nessuna voce copre: si vedono, non si attendono."""
    coperti = {registro_f24.normalizza_codice(c) for v in voci for c in v.get("codici") or []}
    trovati: Dict[str, Dict[str, Any]] = {}
    for f24, righe in modelli:
        dv = _data(registro_f24.data_versamento_modello(f24))
        if not dv or dv.year != anno:
            continue
        for r in righe:
            if r["codice"] in coperti or not r["codice"]:
                continue
            voce = trovati.setdefault(r["codice"], {
                "codice": r["codice"], "descrizione": r.get("descrizione") or "",
                "sezione": r["sezione"], "versamenti": [],
            })
            voce["versamenti"].append({
                "f24_id": f24.get("id"), "data_versamento": dv.isoformat(),
                "periodo_riferimento": r["periodo_riferimento"],
                "importo_debito": _euro(r["importo_debito_cents"]),
                "importo_credito": _euro(r["importo_credito_cents"]),
            })
    return sorted(trovati.values(), key=lambda v: v["codice"])


async def griglia(db, anno: int, oggi: Optional[date] = None) -> Dict[str, Any]:
    """Il piano dell'anno con lo stato di ogni casella, in una sola lettura del registro."""
    oggi = oggi or datetime.now(timezone.utc).date()
    voci = [v for v in await voci_piano(db) if v.get("attivo", True)]
    registro = await registro_f24.carica_registro(db)
    modelli = _modelli_con_righe(registro)

    righe_griglia = []
    tutte: List[Dict[str, Any]] = []
    for voce in voci:
        caselle = caselle_voce(voce, anno, modelli, registro, oggi)
        tutte.extend(caselle)
        righe_griglia.append({
            "voce": {k: voce.get(k) for k in (
                "id", "gruppo", "etichetta", "codici", "periodo", "obbligatorio", "natura", "nota")},
            "caselle": caselle,
        })

    obbligatorie = [c for c in tutte if c["mandatory"]]
    conteggi: Dict[str, int] = {}
    for c in tutte:
        conteggi[c["stato"]] = conteggi.get(c["stato"], 0) + 1
    return {
        "anno": anno,
        "oggi": oggi.isoformat(),
        "voci": righe_griglia,
        "conteggi": conteggi,
        "etichette": ETICHETTE,
        "mancano": [
            {"voce": r["voce"]["etichetta"], "codici": r["voce"]["codici"],
             "periodo": c["etichetta_periodo"], "scadenza": c["scadenza"], "stato": c["stato"]}
            for r in righe_griglia for c in r["caselle"]
            if c["mandatory"] and c["stato"] in (MANCA_F24, SCADUTO_NON_PAGATO)
        ],
        "modelli_doppi": sum(c["modelli_doppi"] for c in tutte),
        # L'anno e' chiuso solo quando ogni attesa obbligatoria e' positiva.
        "anno_chiuso": mandatory_expectations_closed(obbligatorie),
        "fuori_piano": _codici_fuori_piano(voci, modelli, anno),
    }
