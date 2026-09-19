"""Lettura della Comunicazione Liquidazioni Periodiche IVA (LIPE).

La LIPE e' il documento **canonico** dell'IVA mensile: e' quello che il
commercialista trasmette all'Agenzia. Il gestionale la legge per confrontare
mese per mese la propria liquidazione con quella dichiarata, e per affiancarci
i prospetti F24 da pagare.

**Si legge per posizione, mai per ordine del testo.** Il livello testo del PDF
restituisce le celle mescolate alle caselle di spunta del modulo: su VP14 di
febbraio 2026 la sequenza grezza e' `1 , o a credito 2 18.058, 9 2`, dove `1`
e `2` sono spunte e il valore e' `18.058,92`. Leggendo in ordine si ottiene
`218.058,92` — un errore da 200.000 EUR su un numero fiscale.

Le celle stanno invece ad ascisse fisse del modulo ministeriale:

- colonna **DEBITI**: la parte intera finisce a x ~= 388, i due decimali
  stanno a x ~= 392 e x ~= 407;
- colonna **CREDITI**: parte intera a x ~= 532, decimali a x ~= 536 e 551.

Tutto il resto della riga (le spunte a x ~= 323 e 467, le parole «o a
credito», «Metodo») non e' un valore e non va raccolto.

**La prova che la lettura e' giusta non e' il parser, e' l'aritmetica del
modulo**: `VP6 = VP5 - VP4` e `VP14 = VP6 + VP8 - VP7`. `quadra()` la
verifica su ogni periodo; se non torna, il periodo esce con
`quadratura_ok = False` e non si usa come fonte.

Una cella vuota resta `None`, mai zero: febbraio 2026 ha VP2 (operazioni
attive) in bianco, ed e' un fatto del documento, non un difetto di lettura.
"""
from typing import Any, Dict, List, Optional, Tuple

__all__ = [
    "CAMPI_VP",
    "ANCORA_DEBITI",
    "ANCORA_CREDITI",
    "valore_cella",
    "valori_riga",
    "quadra",
    "parse_lipe",
]

#: I righi del quadro VP che interessano il confronto, col loro significato.
CAMPI_VP: Dict[str, str] = {
    "VP2": "totale_operazioni_attive",
    "VP3": "totale_operazioni_passive",
    "VP4": "iva_esigibile",
    "VP5": "iva_detratta",
    "VP6": "iva_dovuta_o_credito",
    "VP7": "debito_periodo_precedente",
    "VP8": "credito_periodo_precedente",
    "VP9": "credito_anno_precedente",
    "VP10": "versamenti_auto",
    "VP11": "crediti_imposta",
    "VP12": "interessi_trimestrali",
    "VP13": "acconto_dovuto",
    "VP14": "iva_da_versare_o_credito",
}

#: (fine della parte intera, ascissa del primo decimale, del secondo).
ANCORA_DEBITI = (388.0, 392.5, 407.5)
ANCORA_CREDITI = (532.0, 536.0, 551.0)

_TOLLERANZA_X = 4.0
_TOLLERANZA_RIGA = 6.0
_CENTESIMI_TOLLERATI = 0.02


def _vicino(valore: float, ancora: float) -> bool:
    return abs(valore - ancora) <= _TOLLERANZA_X


def valore_cella(parole: List[Dict[str, Any]], ancora: Tuple[float, float, float]) -> Optional[float]:
    """Il numero scritto nella cella che finisce su `ancora`, o `None`.

    Raccoglie tre pezzi e solo quelli: la parte intera con la virgola, e i due
    decimali alle loro ascisse. Una cella che porta la sola virgola e' vuota.
    """
    fine_intero, dec1, dec2 = ancora
    intero = next(
        (w["text"] for w in parole if _vicino(w["x1"], fine_intero)), ""
    )
    primo = next((w["text"] for w in parole if _vicino(w["x0"], dec1)), "")
    secondo = next((w["text"] for w in parole if _vicino(w["x0"], dec2)), "")

    cifre_intere = intero.replace(".", "").replace(",", "").strip()
    decimali = f"{primo.strip()}{secondo.strip()}"
    if not cifre_intere and not decimali:
        return None
    if not cifre_intere.isdigit() and cifre_intere:
        return None
    if decimali and not decimali.isdigit():
        return None
    return float(f"{cifre_intere or 0}.{decimali.ljust(2, '0')}")


def valori_riga(
    parole: List[Dict[str, Any]], top: float
) -> Tuple[Optional[float], Optional[float]]:
    """(debiti, crediti) della riga il cui rigo VP sta a quota `top`."""
    riga = [w for w in parole if abs(w["top"] - top) <= _TOLLERANZA_RIGA]
    return valore_cella(riga, ANCORA_DEBITI), valore_cella(riga, ANCORA_CREDITI)


def _importo(coppia: Tuple[Optional[float], Optional[float]]) -> Optional[float]:
    """Un rigo con una sola casella compilata: quello che c'e', ovunque sia."""
    debiti, crediti = coppia
    return debiti if debiti is not None else crediti


def quadra(periodo: Dict[str, Any]) -> bool:
    """L'aritmetica del modulo: se non torna, la lettura non si usa.

    `VP6 = VP5 - VP4` (in valore assoluto: il segno lo da' la colonna) e
    `VP14 = VP6 + VP8 - VP7`. Un rigo assente vale zero solo qui dentro, per
    il controllo: sul dato resta `None`.
    """
    def n(chiave: str) -> float:
        valore = periodo.get(chiave)
        return 0.0 if valore is None else float(valore)

    atteso_vp6 = abs(n("iva_detratta") - n("iva_esigibile"))
    if abs(atteso_vp6 - n("iva_dovuta_o_credito")) > _CENTESIMI_TOLLERATI:
        return False

    atteso_vp14 = abs(
        n("iva_dovuta_o_credito") + n("credito_periodo_precedente")
        - n("debito_periodo_precedente")
    )
    return abs(atteso_vp14 - n("iva_da_versare_o_credito")) <= _CENTESIMI_TOLLERATI


def _mese(parole: List[Dict[str, Any]]) -> Optional[str]:
    """Le due cifre della casella «Mese», in alto nel quadro VP1."""
    cifre = sorted(
        (w for w in parole if 154 <= w["top"] <= 164 and 150 < w["x0"] < 190),
        key=lambda w: w["x0"],
    )
    testo = "".join(w["text"] for w in cifre).strip()
    return testo.zfill(2) if testo.isdigit() else None


def _anno(parole: List[Dict[str, Any]]) -> Optional[str]:
    """L'anno d'imposta, scritto una cifra per casella nella prima pagina."""
    cifre = [w["text"] for w in parole if w["text"].isdigit() and len(w["text"]) == 1]
    unito = "".join(cifre)
    for inizio in range(len(unito) - 3):
        pezzo = unito[inizio:inizio + 4]
        if pezzo.startswith("20") and pezzo.isdigit():
            return pezzo
    return None


def parse_lipe(pdf_bytes: bytes) -> Dict[str, Any]:
    """Legge una LIPE e restituisce un periodo per ogni quadro VP compilato."""
    import io

    import pdfplumber

    periodi: List[Dict[str, Any]] = []
    anno: Optional[str] = None

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for numero_pagina, pagina in enumerate(pdf.pages, start=1):
            parole = pagina.extract_words()
            if anno is None:
                anno = _anno(parole)

            righi = {
                w["text"]: w["top"]
                for w in parole
                if w["text"] in CAMPI_VP
            }
            if "VP14" not in righi:
                continue  # copertina o pagina senza quadro VP

            mese = _mese(parole)
            periodo: Dict[str, Any] = {
                "pagina": numero_pagina,
                "mese": mese,
                "periodo": f"{anno}-{mese}" if anno and mese else None,
            }
            for rigo, nome in CAMPI_VP.items():
                if rigo not in righi:
                    periodo[nome] = None
                    continue
                coppia = valori_riga(parole, righi[rigo])
                periodo[nome] = _importo(coppia)
                if rigo in ("VP6", "VP14"):
                    debiti, _crediti = coppia
                    periodo[f"{nome}_segno"] = (
                        None if periodo[nome] is None
                        else ("debito" if debiti is not None else "credito")
                    )
            periodo["quadratura_ok"] = quadra(periodo)
            periodi.append(periodo)

    return {
        "anno": anno,
        "periodi": periodi,
        "periodi_letti": len(periodi),
        "periodi_che_non_quadrano": [
            p.get("periodo") or f"pagina {p['pagina']}"
            for p in periodi if not p["quadratura_ok"]
        ],
    }
