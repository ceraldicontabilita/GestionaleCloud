"""
Motore fiscale — costo del personale, IRES e IRAP.

Implementa le sezioni 12-14 della specifica
(memoria/SPECIFICA_F24_CEDOLINI_IRES_IRAP_CHAT.md):

  §12 Costo del personale = retribuzioni lorde + quota INPS datoriale +
      premio INAIL + TFR maturato + 13ª/14ª + fondi a carico azienda +
      altri oneri − sgravi/recuperi datoriali.
      NON si sommano di nuovo: netto pagato, IRPEF, addizionali, IVS
      trattenuta al dipendente (già dentro il lordo contabilizzato).
  §13 IRES = (ricavi imponibili − costi deducibili ± variazioni fiscali)
      × aliquota versionata per periodo d'imposta.
  §14 IRAP: motore SEPARATO dall'IRES; parte dal valore della produzione,
      distingue le tipologie di personale, applica le regole dell'anno e
      NON sottrae mai automaticamente l'intero F24.

Le aliquote sono VERSIONATE per anno (regola §13 "versionata per periodo
d'imposta"). I valori base sono quelli nazionali; l'eventuale maggiorazione
regionale IRAP è un parametro esplicito (mai deciso in automatico: regola
parametri dell'utente — proporre, non scegliere).
"""
from typing import Any, Dict, List, Optional

# ── Aliquote versionate per periodo d'imposta ──────────────────────────────
# {anno_da: aliquota} — si applica l'aliquota dell'anno più recente ≤ anno.
ALIQUOTE_IRES = {
    2017: 0.24,   # IRES 24% dal periodo d'imposta 2017
}
ALIQUOTE_IRAP_BASE = {
    2008: 0.039,  # aliquota ordinaria nazionale 3,9%
}


def _aliquota_per_anno(tabella: Dict[int, float], anno: int) -> float:
    anni_validi = [a for a in tabella if a <= anno]
    if not anni_validi:
        raise ValueError(f"Nessuna aliquota versionata per l'anno {anno}")
    return tabella[max(anni_validi)]


def aliquota_ires(anno: int) -> float:
    return _aliquota_per_anno(ALIQUOTE_IRES, anno)


def aliquota_irap(anno: int, maggiorazione_regionale: float = 0.0) -> float:
    """Aliquota IRAP dell'anno. La maggiorazione regionale (es. Regioni in
    piano di rientro sanitario) va passata ESPLICITAMENTE: il motore non la
    sceglie da solo."""
    return _aliquota_per_anno(ALIQUOTE_IRAP_BASE, anno) + float(maggiorazione_regionale or 0)


# ── §12 Costo del personale ────────────────────────────────────────────────

# Voci che NON vanno mai risommate se il lordo è già contabilizzato
VOCI_NON_COSTO = (
    "netto_pagato", "irpef", "addizionale_regionale",
    "addizionale_comunale", "ivs_trattenuta_dipendente",
)


def calcola_costo_personale(voci: Dict[str, float]) -> Dict[str, Any]:
    """Formula §12. `voci` accetta (tutte opzionali, default 0):
      retribuzioni_lorde, inps_datoriale, premio_inail, tfr_maturato,
      tredicesima, quattordicesima, fondi_azienda, altri_oneri,
      sgravi_recuperi (in sottrazione).

    Eventuali chiavi in VOCI_NON_COSTO vengono IGNORATE e segnalate:
    sono trattenute/pagamenti già compresi nel lordo, non nuovi costi.
    """
    def v(nome):
        return float(voci.get(nome, 0) or 0)

    ignorate = sorted(k for k in voci if k in VOCI_NON_COSTO and voci[k])

    componenti = {
        "retribuzioni_lorde": v("retribuzioni_lorde"),
        "inps_datoriale": v("inps_datoriale"),
        "premio_inail": v("premio_inail"),
        "tfr_maturato": v("tfr_maturato"),
        "tredicesima": v("tredicesima"),
        "quattordicesima": v("quattordicesima"),
        "fondi_azienda": v("fondi_azienda"),
        "altri_oneri": v("altri_oneri"),
    }
    sgravi = v("sgravi_recuperi")
    totale = round(sum(componenti.values()) - sgravi, 2)

    return {
        "costo_personale": totale,
        "componenti": componenti,
        "sgravi_recuperi": sgravi,
        "voci_ignorate": ignorate,
        "nota": ("Ignorate (già comprese nel lordo, non sono nuovi costi): "
                 + ", ".join(ignorate)) if ignorate else
                "Nessuna trattenuta risommata: formula §12 rispettata",
    }


# ── §13 IRES ───────────────────────────────────────────────────────────────

def calcola_ires(
    anno: int,
    ricavi_imponibili: float,
    costi_deducibili: float,
    variazioni_in_aumento: float = 0.0,
    variazioni_in_diminuzione: float = 0.0,
) -> Dict[str, Any]:
    """Imponibile = ricavi − costi + variazioni in aumento − in diminuzione.
    Aliquota versionata per periodo d'imposta."""
    imponibile = round(
        float(ricavi_imponibili) - float(costi_deducibili)
        + float(variazioni_in_aumento) - float(variazioni_in_diminuzione), 2
    )
    aliquota = aliquota_ires(anno)
    imposta = round(max(0.0, imponibile) * aliquota, 2)
    return {
        "anno": anno,
        "imponibile_ires": imponibile,
        "aliquota": aliquota,
        "imposta_ires": imposta,
        "dettaglio": {
            "ricavi_imponibili": float(ricavi_imponibili),
            "costi_deducibili": float(costi_deducibili),
            "variazioni_in_aumento": float(variazioni_in_aumento),
            "variazioni_in_diminuzione": float(variazioni_in_diminuzione),
        },
    }


# ── §14 IRAP ───────────────────────────────────────────────────────────────

TIPOLOGIE_PERSONALE = (
    "indeterminato", "determinato", "apprendistato",
    "collaboratore", "amministratore",
)


def calcola_irap(
    anno: int,
    valore_produzione: float,
    costo_personale_per_tipo: Optional[Dict[str, float]] = None,
    deduzioni_personale_per_tipo: Optional[Dict[str, float]] = None,
    altre_deduzioni: float = 0.0,
    maggiorazione_regionale: float = 0.0,
) -> Dict[str, Any]:
    """Motore IRAP separato dall'IRES (§14).

    - parte dal VALORE DELLA PRODUZIONE (mai dall'utile IRES);
    - il personale è distinto per tipologia: le deduzioni vanno passate
      per tipo (es. il tempo indeterminato è deducibile secondo le regole
      dell'anno, determinato/collaboratori tipicamente no) — il motore
      applica ciò che riceve, con tracciabilità, e NON sottrae mai
      automaticamente l'intero F24;
    - aliquota versionata + maggiorazione regionale esplicita.
    """
    costo_personale_per_tipo = costo_personale_per_tipo or {}
    deduzioni_personale_per_tipo = deduzioni_personale_per_tipo or {}

    sconosciute = sorted(
        set(costo_personale_per_tipo) | set(deduzioni_personale_per_tipo)
    ) if any(t not in TIPOLOGIE_PERSONALE
             for t in set(costo_personale_per_tipo) | set(deduzioni_personale_per_tipo)) else []
    sconosciute = [t for t in sconosciute if t not in TIPOLOGIE_PERSONALE]

    # Le deduzioni non possono superare il costo dichiarato per quel tipo
    deduzioni_applicate: Dict[str, float] = {}
    for tipo, importo in deduzioni_personale_per_tipo.items():
        tetto = float(costo_personale_per_tipo.get(tipo, importo) or 0)
        deduzioni_applicate[tipo] = round(min(float(importo or 0), tetto), 2)

    totale_deduzioni_personale = round(sum(deduzioni_applicate.values()), 2)
    imponibile = round(
        float(valore_produzione) - totale_deduzioni_personale - float(altre_deduzioni or 0), 2
    )
    aliquota = aliquota_irap(anno, maggiorazione_regionale)
    imposta = round(max(0.0, imponibile) * aliquota, 2)

    return {
        "anno": anno,
        "valore_produzione": float(valore_produzione),
        "deduzioni_personale": deduzioni_applicate,
        "totale_deduzioni_personale": totale_deduzioni_personale,
        "altre_deduzioni": float(altre_deduzioni or 0),
        "imponibile_irap": imponibile,
        "aliquota": aliquota,
        "imposta_irap": imposta,
        "tipologie_sconosciute": sconosciute,
        "nota": "Mai sottratto l'intero F24: le deduzioni derivano dal costo "
                "del personale per tipologia (prospetto paghe/consulente)",
    }
