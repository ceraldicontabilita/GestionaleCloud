"""
Generatore turni settimanale con vincoli reali.

Differenze chiave rispetto al vecchio foglio: i vincoli sono verificati e,
quando non si riescono a rispettare, viene EMESSO UN AVVISO invece di forzare
in silenzio. Vincoli:
  - indisponibilità (ferie approvate + indisponibilità inviate) → mai a lavoro
  - 11h di riposo tra fine turno e inizio del turno successivo (D.Lgs 66/2003)
  - niente due "lunghe" consecutive
  - almeno un riposo settimanale per ciascuno
  - equità: bilancia ore e numero di lunghe
"""
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

GIORNI_NOMI = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]

TURNI_DEFAULT: Dict[str, Dict[str, Any]] = {
    "apertura":   {"label": "Apertura",   "inizio": "07:00", "fine": "15:00", "ore": 8},
    "mattina":    {"label": "Mattina",    "inizio": "08:00", "fine": "16:00", "ore": 8},
    "lunga":      {"label": "Lunga",      "inizio": "09:30", "fine": "19:30", "ore": 9},
    "pomeriggio": {"label": "Pomeriggio", "inizio": "15:00", "fine": "21:00", "ore": 6},
    "riposo":       {"label": "Riposo",            "inizio": None, "fine": None, "ore": 0},
    "indisponibile": {"label": "Indisponibile/Ferie", "inizio": None, "fine": None, "ore": 0},
}

ORDER = ["lunga", "apertura", "mattina", "pomeriggio"]

FABBISOGNO_DEFAULT: Dict[int, Dict[str, int]] = {
    0: {"apertura": 1, "mattina": 1, "lunga": 1, "pomeriggio": 2},
    1: {"apertura": 1, "mattina": 1, "lunga": 1, "pomeriggio": 2},
    2: {"apertura": 1, "mattina": 1, "lunga": 1, "pomeriggio": 2},
    3: {"apertura": 1, "mattina": 1, "lunga": 1, "pomeriggio": 2},
    4: {"apertura": 1, "mattina": 1, "lunga": 1, "pomeriggio": 2},
    5: {"apertura": 1, "mattina": 1, "lunga": 2, "pomeriggio": 2},  # sabato
    6: {"apertura": 1, "pomeriggio": 1},                            # domenica ridotto
}

MIN_RIPOSO_MIN = 11 * 60


def _min(hhmm: Optional[str]) -> Optional[int]:
    if not hhmm:
        return None
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _gap_ok(turni: Dict[str, Any], turno_prec: Optional[str], turno_succ: str) -> bool:
    """True se tra fine(prec) e inizio(succ) ci sono >= 11h (giorni consecutivi)."""
    if not turno_prec:
        return True
    fine_prec = _min(turni.get(turno_prec, {}).get("fine"))
    inizio_succ = _min(turni.get(turno_succ, {}).get("inizio"))
    if fine_prec is None or inizio_succ is None:
        return True  # uno dei due è riposo/indisponibile
    gap = (24 * 60 - fine_prec) + inizio_succ
    return gap >= MIN_RIPOSO_MIN


def _indisponibile(indisp: List[Dict[str, Any]], dip_id: str, data: str) -> bool:
    for r in indisp:
        if r.get("dipendente_id") != dip_id:
            continue
        dal, al = r.get("dal"), r.get("al")
        if dal and al and dal <= data <= al:
            return True
        if r.get("data") == data:
            return True
    return False


def genera_settimana(
    dipendenti: List[Dict[str, Any]],
    indisponibilita: List[Dict[str, Any]],
    settimana_inizio: str,
    fabbisogno: Optional[Dict[int, Dict[str, int]]] = None,
    turni: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    turni = turni or TURNI_DEFAULT
    fabbisogno = fabbisogno or FABBISOGNO_DEFAULT
    base = datetime.strptime(settimana_inizio, "%Y-%m-%d")
    date = [(base + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]

    ids = [d["id"] for d in dipendenti]
    nome = {d["id"]: d.get("nome_completo", "") for d in dipendenti}
    assign: Dict[str, List[Optional[str]]] = {i: [None] * 7 for i in ids}
    ore = {i: 0 for i in ids}
    lunghe = {i: 0 for i in ids}
    riposi = {i: 0 for i in ids}
    avvisi: List[str] = []

    for gi, data in enumerate(date):
        wd = (base + timedelta(days=gi)).weekday()
        fab = fabbisogno.get(wd, {})
        assegnati_oggi = set()

        for turno_key in ORDER:
            for _ in range(fab.get(turno_key, 0)):
                cand = []
                for i in ids:
                    if i in assegnati_oggi:
                        continue
                    if _indisponibile(indisponibilita, i, data):
                        continue
                    prec = assign[i][gi - 1] if gi > 0 else None
                    if turno_key == "lunga" and prec == "lunga":
                        continue
                    if not _gap_ok(turni, prec, turno_key):
                        continue
                    cand.append(i)
                cand.sort(key=lambda i: (ore[i], lunghe[i]))
                if not cand:
                    avvisi.append(f"{GIORNI_NOMI[gi]} {data}: turno «{turni[turno_key]['label']}» scoperto")
                    continue
                scelto = cand[0]
                assign[scelto][gi] = turno_key
                assegnati_oggi.add(scelto)
                ore[scelto] += turni[turno_key]["ore"]
                if turno_key == "lunga":
                    lunghe[scelto] += 1

        # restanti → indisponibile o riposo
        for i in ids:
            if assign[i][gi] is not None:
                continue
            if _indisponibile(indisponibilita, i, data):
                assign[i][gi] = "indisponibile"
            else:
                assign[i][gi] = "riposo"
                riposi[i] += 1

    # riposo settimanale garantito
    for i in ids:
        if riposi[i] == 0:
            avvisi.append(f"{nome[i]}: nessun riposo settimanale nella settimana")

    giorni = []
    for gi, data in enumerate(date):
        ass = {}
        for i in ids:
            tk = assign[i][gi]
            t = turni[tk]
            ass[i] = {"turno": tk, "label": t["label"], "inizio": t["inizio"],
                      "fine": t["fine"], "ore": t["ore"]}
        giorni.append({"data": data, "giorno_nome": GIORNI_NOMI[gi], "assegnazioni": ass})

    totali = {i: {"nome": nome[i], "ore": ore[i], "lunghe": lunghe[i], "riposi": riposi[i]} for i in ids}
    return {"giorni": giorni, "totali": totali, "avvisi": avvisi}


def rivalida(doc: Dict[str, Any], turni: Optional[Dict[str, Dict[str, Any]]] = None) -> List[str]:
    """Ricontrolla i vincoli su uno schedule (usata dopo una modifica manuale)."""
    turni = turni or TURNI_DEFAULT
    giorni = doc.get("giorni", [])
    avvisi: List[str] = []
    # raccogli per dipendente la sequenza di turni
    dip_ids = set()
    for g in giorni:
        dip_ids.update(g.get("assegnazioni", {}).keys())
    for i in dip_ids:
        seq = [g["assegnazioni"].get(i, {}).get("turno") for g in giorni]
        nome = doc.get("totali", {}).get(i, {}).get("nome", i)
        riposi = sum(1 for t in seq if t == "riposo")
        if riposi == 0:
            avvisi.append(f"{nome}: nessun riposo settimanale")
        for k in range(1, len(seq)):
            if seq[k] == "lunga" and seq[k - 1] == "lunga":
                avvisi.append(f"{nome}: due «lunghe» consecutive ({giorni[k-1]['giorno_nome']}–{giorni[k]['giorno_nome']})")
            if not _gap_ok(turni, seq[k - 1], seq[k]) and seq[k] in turni and turni[seq[k]]["inizio"]:
                avvisi.append(f"{nome}: meno di 11h tra {giorni[k-1]['giorno_nome']} e {giorni[k]['giorno_nome']}")
    return avvisi
