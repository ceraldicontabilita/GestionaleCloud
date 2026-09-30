"""Lievito e impasto: un solo modello per ricette, produzione e calcolatore.

Perché esiste: la dose di lievito scritta in una ricetta vale per UNA
lievitazione (certe ore a una certa temperatura). Quando cambiano ore o
temperatura il lievito va ricalcolato, il resto della ricetta no.

Fonti delle formule (nessun numero è inventato):
- Formula «Japi 2» (forum La Verace / RafCalc), lievito di birra fresco:
  LB = F · C · (1+S/200) · (1+O/300) / ((−80 + 4,2·I − 0,0305·I²) · T^2,5 · H^1,2)
  F farina g, I idratazione %, T temperatura °C, H ore, S sale g/litro,
  O grassi g/litro, C = 2250. Campo dichiarato: 15–35 °C, 1–96 ore,
  idratazione 50–100 %, sale e grassi 0–60 g/l.
- Ore in frigo: la formula non copre le basse temperature. Si convertono in
  ore equivalenti alla temperatura ambiente con la regola di Hamelman
  (la velocità di fermentazione si triplica ogni 9 °C circa).
- Conversioni fresco → secco: attivo × 0,4, istantaneo × 1/3 (rapporti
  d'uso comune indicati dai produttori).
- Temperatura dell'acqua: metodo delle temperature base
  (TFI × fattori − somma delle altre temperature − attrito).
- Mix di farine: media pesata lineare della forza W.

Per le RICETTE non si usa la formula assoluta: si scala il lievito scritto in
ricetta col rapporto fra le condizioni di riferimento (dichiarate sulla
ricetta) e quelle di oggi. Senza riferimento il lievito resta com'è e si
segnala che manca il dato.
"""

from __future__ import annotations

import math
import re
from typing import Any

COEFF_JAPI2 = 2250.0
T_MIN, T_MAX = 15.0, 35.0
ORE_MIN, ORE_MAX = 1.0, 96.0
IDRO_MIN, IDRO_MAX = 50.0, 100.0
FATTORE_AFFIDABILE = (0.25, 4.0)

CONVERSIONE_LIEVITO = {"fresco": 1.0, "secco_attivo": 0.4, "istantaneo": 1 / 3}

# Lievito di birra (fresco, compresso, secco): SI. Chimico, per dolci, in
# polvere, madre, miglioratore: NO (non dipendono da ore e temperatura come il
# lievito di birra, o hanno una gestione propria).
_LIEVITO_SI = re.compile(r"\blievit", re.I)
_LIEVITO_NO = re.compile(r"chimic|dolci|polvere|madre|pasta\s+madre|licoli|"
                         r"cremor|bicarbonat|ammoniaca|naturale|miglior", re.I)


class DatoNonValido(ValueError):
    """Un valore fuori dal campo accettato: il messaggio va mostrato così com'è."""


def _num(valore: Any, nome: str, minimo: float, massimo: float, *, obbligatorio=True) -> float | None:
    if valore in (None, ""):
        if obbligatorio:
            raise DatoNonValido(f"Manca {nome}.")
        return None
    try:
        n = float(valore)
    except (TypeError, ValueError) as exc:
        raise DatoNonValido(f"{nome.capitalize()} non è un numero.") from exc
    if not math.isfinite(n) or n < minimo or n > massimo:
        raise DatoNonValido(f"{nome.capitalize()} va da {minimo:g} a {massimo:g}.")
    return n


def e_lievito_di_birra(nome: str) -> bool:
    nome = str(nome or "")
    return bool(_LIEVITO_SI.search(nome)) and not _LIEVITO_NO.search(nome)


def velocita_relativa(t_da: float, t_a: float) -> float:
    """Quante volte è più veloce la fermentazione a t_a rispetto a t_da (Hamelman)."""
    return 3 ** ((t_a - t_da) / 9.0)


def condizioni(dati: dict | None) -> dict:
    """Legge e controlla ore e temperature di una lievitazione.

    ore_ambiente: ore a temperatura ambiente (puntata + appretto).
    temperatura_c: temperatura ambiente in °C.
    ore_frigo / temperatura_frigo_c: facoltative, per la maturazione in frigo.
    """
    dati = dati or {}
    ore_amb = _num(dati.get("ore_ambiente"), "le ore a temperatura ambiente", 0.5, 96)
    t_amb = _num(dati.get("temperatura_c"), "la temperatura ambiente", 10, 40)
    ore_frigo = _num(dati.get("ore_frigo"), "le ore in frigo", 0, 120, obbligatorio=False) or 0.0
    t_frigo = _num(dati.get("temperatura_frigo_c"), "la temperatura del frigo", 0, 10,
                   obbligatorio=ore_frigo > 0)
    return {
        "ore_ambiente": ore_amb,
        "temperatura_c": t_amb,
        "ore_frigo": ore_frigo,
        "temperatura_frigo_c": t_frigo if ore_frigo > 0 else None,
    }


def ore_equivalenti(c: dict) -> float:
    """Ore a temperatura ambiente che fanno lo stesso lavoro dell'intera lievitazione."""
    ore = c["ore_ambiente"]
    if c.get("ore_frigo"):
        ore += c["ore_frigo"] * velocita_relativa(c["temperatura_c"], c["temperatura_frigo_c"])
    return ore


def _denominatore_tempo(c: dict) -> float:
    return c["temperatura_c"] ** 2.5 * ore_equivalenti(c) ** 1.2


def fattore_lievito(riferimento: dict, oggi: dict) -> float:
    """Per quanto moltiplicare il lievito scritto in ricetta per le condizioni di oggi."""
    return _denominatore_tempo(riferimento) / _denominatore_tempo(oggi)


def _avvisi_campo(c: dict) -> list[str]:
    avvisi = []
    if not T_MIN <= c["temperatura_c"] <= T_MAX:
        avvisi.append(f"A {c['temperatura_c']:g} °C la formula è fuori dal campo in cui è stata "
                      f"tarata ({T_MIN:g}–{T_MAX:g} °C): controlla la lievitazione a vista.")
    teq = ore_equivalenti(c)
    if not ORE_MIN <= teq <= ORE_MAX:
        avvisi.append(f"{teq:.1f} ore equivalenti sono fuori dal campo tarato "
                      f"({ORE_MIN:g}–{ORE_MAX:g} ore).")
    return avvisi


def adegua_lievito(ingredienti: list[dict], riferimento: dict | None, oggi: dict | None,
                   moltiplicatore: float = 1.0) -> dict:
    """Ricalcola le righe di lievito di birra di una ricetta per le condizioni di oggi.

    Non tocca le altre righe. Se la ricetta non dichiara per quale lievitazione
    vale la sua dose, non inventa: restituisce stato «manca_riferimento».
    """
    righe = [i for i in (ingredienti or []) if isinstance(i, dict) and e_lievito_di_birra(i.get("nome"))]
    if not righe:
        return {"stato": "senza_lievito", "righe": []}
    base = {"stato": "manca_riferimento", "fattore": None, "avvisi": [],
            "righe": [{"nome": r.get("nome"), "unita": r.get("unita_misura") or r.get("unita") or "",
                       "ricetta": None if _quantita(r) is None else _arrotonda(_quantita(r) * moltiplicatore),
                       "oggi": None} for r in righe]}
    if not riferimento:
        return base
    rif = condizioni(riferimento)
    if oggi is None:
        return {**base, "stato": "manca_condizioni", "riferimento": rif}
    cond = condizioni(oggi)
    f = fattore_lievito(rif, cond)
    avvisi = _avvisi_campo(cond)
    if not FATTORE_AFFIDABILE[0] <= f <= FATTORE_AFFIDABILE[1]:
        avvisi.append(f"Il lievito cambia di {f:.2f} volte rispetto alla ricetta: una "
                      "differenza così grande va provata prima di produrre in quantità.")
    fuori = []
    for r in righe:
        q = _quantita(r)
        oggi_q = None if q is None else _arrotonda(q * f * moltiplicatore)
        fuori.append({"nome": r.get("nome"), "unita": r.get("unita_misura") or r.get("unita") or "",
                      "ricetta": None if q is None else _arrotonda(q * moltiplicatore), "oggi": oggi_q})
        if q is None:
            avvisi.append(f"{r.get('nome')}: la ricetta non ha la dose, non posso ricalcolarla.")
    return {"stato": "ricalcolato", "fattore": round(f, 3), "riferimento": rif,
            "condizioni": cond, "ore_equivalenti": round(ore_equivalenti(cond), 1),
            "righe": fuori, "avvisi": avvisi}


def applica_a_ingredienti(ingredienti: list[dict], esito: dict) -> list[dict]:
    """Copia degli ingredienti con il lievito di oggi (per lo scarico di magazzino)."""
    if esito.get("stato") != "ricalcolato" or not esito.get("fattore"):
        return ingredienti
    f = esito["fattore"]
    nuovi = []
    for i in ingredienti:
        if isinstance(i, dict) and e_lievito_di_birra(i.get("nome")) and _quantita(i) is not None:
            nuovi.append({**i, "quantita": _arrotonda(_quantita(i) * f), "lievito_ricalcolato": True})
        else:
            nuovi.append(i)
    return nuovi


def _quantita(riga: dict) -> float | None:
    try:
        q = float(riga.get("quantita"))
    except (TypeError, ValueError):
        return None
    return q if math.isfinite(q) and q > 0 else None


def _arrotonda(q: float) -> float:
    return round(q, 2 if q < 10 else 1 if q < 100 else 0)


# ── Calcolatore impasto (pagina «Calcolatore impasti») ───────────────────────

def lievito_japi2(farina_g: float, idratazione: float, temperatura: float, ore: float,
                  sale_g_l: float = 0, grassi_g_l: float = 0) -> float:
    idro = -80 + 4.2 * idratazione - 0.0305 * idratazione ** 2
    return (farina_g * COEFF_JAPI2 * (1 + sale_g_l / 200) * (1 + grassi_g_l / 300)
            / (idro * temperatura ** 2.5 * ore ** 1.2))


def calcola_impasto(req: dict) -> dict:
    """Ricetta completa di un impasto diretto o con prefermento.

    Parte dal peso totale (panetti × peso) e dall'idratazione; sale e grassi in
    grammi per litro d'acqua come nella tradizione napoletana.
    """
    panetti = _num(req.get("panetti"), "il numero di panetti", 1, 2000)
    peso = _num(req.get("peso_panetto_g"), "il peso del panetto", 20, 5000)
    idro = _num(req.get("idratazione_pct"), "l'idratazione", 45, 110)
    sale_l = _num(req.get("sale_g_litro"), "il sale per litro", 0, 80)
    grassi_l = _num(req.get("grassi_g_litro"), "i grassi per litro", 0, 150, obbligatorio=False) or 0.0
    tipo = str(req.get("tipo_lievito") or "fresco")
    if tipo not in CONVERSIONE_LIEVITO:
        raise DatoNonValido("Tipo di lievito non riconosciuto.")
    cond = condizioni(req)

    totale = panetti * peso
    # totale = farina × (1 + I/100 + sale/1000·I/100 + grassi/1000·I/100 + lievito≈0)
    per_farina = 1 + idro / 100 * (1 + sale_l / 1000 + grassi_l / 1000)
    farina = totale / per_farina
    acqua = farina * idro / 100
    sale = acqua * sale_l / 1000
    grassi = acqua * grassi_l / 1000
    avvisi = _avvisi_campo(cond)
    if not IDRO_MIN <= idro <= IDRO_MAX:
        avvisi.append(f"Idratazione {idro:g}%: la formula è tarata fra {IDRO_MIN:g} e {IDRO_MAX:g}%.")
    teq = ore_equivalenti(cond)
    fresco = lievito_japi2(farina, min(max(idro, IDRO_MIN), IDRO_MAX), cond["temperatura_c"],
                           teq, sale_l, grassi_l)
    esito = {
        "totale_g": round(totale), "farina_g": round(farina), "acqua_g": round(acqua),
        "sale_g": round(sale, 1), "grassi_g": round(grassi, 1),
        "ore_equivalenti": round(teq, 1),
        "lievito": {"tipo": tipo, "fresco_g": _arrotonda(fresco),
                    "grammi": _arrotonda(fresco * CONVERSIONE_LIEVITO[tipo]),
                    "percentuale_farina": round(fresco * CONVERSIONE_LIEVITO[tipo] / farina * 100, 3)},
        "avvisi": avvisi,
    }

    pref = req.get("prefermento") or {}
    if pref.get("tipo") in ("biga", "poolish"):
        quota = _num(pref.get("quota_farina_pct"), "la quota di farina nel prefermento", 5, 100)
        idro_p = _num(pref.get("idratazione_pct"), "l'idratazione del prefermento", 40, 120)
        lievito_p = _num(pref.get("lievito_pct"), "il lievito del prefermento (% sulla farina)", 0.01, 3)
        farina_p = farina * quota / 100
        acqua_p = farina_p * idro_p / 100
        if acqua_p > acqua:
            raise DatoNonValido("Il prefermento usa più acqua di tutto l'impasto: abbassa la quota "
                                "o l'idratazione del prefermento.")
        esito["prefermento"] = {
            "tipo": pref["tipo"], "farina_g": round(farina_p), "acqua_g": round(acqua_p),
            "lievito_g": _arrotonda(farina_p * lievito_p / 100),
        }
        esito["chiusura"] = {"farina_g": round(farina - farina_p), "acqua_g": round(acqua - acqua_p),
                             "sale_g": round(sale, 1), "grassi_g": round(grassi, 1)}
    return esito


def mix_farine(w_a: Any, w_b: Any, w_voluto: Any, farina_totale_g: Any) -> dict:
    a = _num(w_a, "la W della prima farina", 50, 500)
    b = _num(w_b, "la W della seconda farina", 50, 500)
    w = _num(w_voluto, "la W voluta", 50, 500)
    tot = _num(farina_totale_g, "la farina totale", 1, 1_000_000)
    if a == b:
        raise DatoNonValido("Le due farine hanno la stessa W: il mix non cambia la forza.")
    quota_a = (w - b) / (a - b)
    if not 0 <= quota_a <= 1:
        raise DatoNonValido(f"Con W {a:g} e W {b:g} si arriva solo fra {min(a, b):g} e {max(a, b):g}.")
    return {"farina_a_g": round(tot * quota_a), "farina_b_g": round(tot * (1 - quota_a)),
            "quota_a_pct": round(quota_a * 100, 1)}


def temperatura_acqua(tfi: Any, t_ambiente: Any, t_farina: Any, attrito: Any,
                      t_prefermento: Any = None) -> dict:
    tfi_ = _num(tfi, "la temperatura finale dell'impasto", 15, 32)
    amb = _num(t_ambiente, "la temperatura ambiente", 0, 45)
    far = _num(t_farina, "la temperatura della farina", 0, 45)
    att = _num(attrito, "l'attrito dell'impastatrice", 0, 30)
    pref = _num(t_prefermento, "la temperatura del prefermento", 0, 40, obbligatorio=False)
    fattori = 4 if pref is not None else 3
    acqua = tfi_ * fattori - amb - far - att - (pref or 0)
    avvisi = []
    if acqua < 1:
        avvisi.append("Serve acqua sotto 1 °C: usa ghiaccio tritato in parte dell'acqua.")
    if acqua > 40:
        avvisi.append("Oltre 40 °C l'acqua indebolisce il lievito: alza la temperatura della farina o dell'ambiente.")
    return {"acqua_c": round(acqua, 1), "avvisi": avvisi}


def attrito_da_impasto(tfi_misurata: Any, t_ambiente: Any, t_farina: Any, t_acqua: Any) -> dict:
    """Ricava l'attrito della propria impastatrice da un impasto già fatto."""
    tfi_ = _num(tfi_misurata, "la temperatura misurata a fine impasto", 10, 40)
    amb = _num(t_ambiente, "la temperatura ambiente", 0, 45)
    far = _num(t_farina, "la temperatura della farina", 0, 45)
    acq = _num(t_acqua, "la temperatura dell'acqua usata", 0, 60)
    return {"attrito_c": round(tfi_ * 3 - amb - far - acq, 1)}
