"""Funzioni pure per pianificare le bozze ordine senza inventare calendari.

Il profilo del fornitore prevale; quando manca un calendario strutturato si
mantiene la copertura prudente legacy di sette giorni e lo si dichiara nella
provenienza della proposta.
"""

from datetime import date, time, timedelta
import re


NOMI_GIORNI = {
    "lun": 0, "lunedi": 0, "lunedì": 0,
    "mar": 1, "martedi": 1, "martedì": 1,
    "mer": 2, "mercoledi": 2, "mercoledì": 2,
    "gio": 3, "giovedi": 3, "giovedì": 3,
    "ven": 4, "venerdi": 4, "venerdì": 4,
    "sab": 5, "sabato": 5,
    "dom": 6, "domenica": 6,
}


def giorni_consegna_profilo(profilo: dict) -> list[int]:
    strutturati = profilo.get("giorni_consegna_settimana") or []
    validi = sorted({int(g) for g in strutturati if isinstance(g, int) and 0 <= g <= 6})
    if validi:
        return validi
    testo = str(profilo.get("giorni_consegna") or "").lower()
    tokens = re.findall(r"[a-zà-ù]+", testo)
    return sorted({NOMI_GIORNI[t] for t in tokens if t in NOMI_GIORNI})


def _in_chiusura_fornitore(giorno: date, profilo: dict) -> bool:
    iso = giorno.isoformat()
    for periodo in profilo.get("chiusure_programmate") or []:
        if isinstance(periodo, dict) and str(periodo.get("dal") or "") <= iso <= str(periodo.get("al") or ""):
            return True
    testo = str(profilo.get("giorni_chiusura") or "").lower()
    return any(NOMI_GIORNI.get(token) == giorno.weekday() for token in re.findall(r"[a-zà-ù]+", testo))


def piano_consegne(
    oggi: date, profilo: dict | None, giorni_non_operativi: set[date] | None = None,
    copertura_default: int = 7, ora_corrente: time | None = None,
) -> dict:
    profilo = profilo or {}
    giorni_non_operativi = giorni_non_operativi or set()
    consegne = giorni_consegna_profilo(profilo)
    if not consegne:
        return {
            "calendario_verificato": False,
            "giorni_copertura": copertura_default,
            "prima_consegna": None,
            "consegna_successiva": None,
            "motivo": "calendario fornitore non compilato: copertura standard 7 giorni",
        }

    lead = max(0, min(int(profilo.get("lead_time_giorni") or 0), 30))
    cutoff_superato = False
    cutoff = str(profilo.get("ora_limite_ordine") or "").strip()
    if ora_corrente and re.fullmatch(r"\d{2}:\d{2}", cutoff):
        hh, mm = (int(x) for x in cutoff.split(":"))
        if 0 <= hh <= 23 and 0 <= mm <= 59 and ora_corrente >= time(hh, mm):
            lead += 1
            cutoff_superato = True
    partenza = oggi + timedelta(days=lead)
    trovate = []
    saltati = []
    for offset in range(0, 61):
        giorno = partenza + timedelta(days=offset)
        if giorno.weekday() not in consegne:
            continue
        if giorno in giorni_non_operativi or _in_chiusura_fornitore(giorno, profilo):
            saltati.append(giorno.isoformat())
            continue
        trovate.append(giorno)
        if len(trovate) == 2:
            break
    if not trovate:
        return {
            "calendario_verificato": True, "giorni_copertura": 21,
            "prima_consegna": None, "consegna_successiva": None,
            "giorni_saltati": saltati,
            "motivo": "nessuna consegna utile trovata nei prossimi 60 giorni: revisione manuale necessaria",
        }
    prima = trovate[0]
    seconda = trovate[1] if len(trovate) > 1 else prima + timedelta(days=copertura_default)
    copertura = max(copertura_default, min((seconda - oggi).days, 21))
    motivo = f"copertura fino alla consegna successiva del {seconda.isoformat()}"
    if cutoff_superato:
        motivo += f"; limite ordine {cutoff} gia superato"
    if saltati:
        motivo += f"; consegne saltate: {', '.join(saltati[:4])}"
    return {
        "calendario_verificato": True,
        "giorni_copertura": copertura,
        "prima_consegna": prima.isoformat(),
        "consegna_successiva": seconda.isoformat(),
        "giorni_saltati": saltati,
        "motivo": motivo,
    }


def applica_fattori_quantita(qta_base: float, giorni_copertura: int, fattore_vendite: float, unita: str) -> float:
    import math
    fattore_calendario = max(1.0, min(float(giorni_copertura) / 7.0, 3.0))
    fattore_vendite = max(0.75, min(float(fattore_vendite or 1.0), 1.30))
    valore = max(0.0, float(qta_base or 0)) * fattore_calendario * fattore_vendite
    return float(math.ceil(valore)) if str(unita or "").lower() in {"pz", "pezzi", "collo", "colli"} else round(valore, 2)
