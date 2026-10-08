"""Confronto mensile fra l'IVA del gestionale e quella del commercialista.

Tre fonti, tre nature diverse, e non vanno confuse:

1. **il gestionale** — `iva_liquidation_query.get_iva_period_snapshot`, la
   fonte unica in lettura dei nostri numeri;
2. **la LIPE** — la Comunicazione Liquidazioni Periodiche IVA che il
   commercialista trasmette all'Agenzia. E' il documento **canonico**
   dell'IVA mensile: quando i due numeri divergono, quello giusto e' questo,
   e lo scarto e' un difetto nostro da spiegare;
3. **i versamenti F24** — quietanze e modelli con i codici 6001..6012 (IVA
   mensile) e l'anno di riferimento sulla riga.

Il confronto LIPE ↔ F24 (dovuto, versato, stato) lo fa un motore solo,
`incroci_fiscali.incroci`: qui si aggiunge la colonna del gestionale e si
tiene il contratto dell'endpoint `/api/iva/confronto-commercialista/{anno}`.
Il confronto non "aggiusta" niente e non scrive sul consuntivo: dice dove i
numeri divergono e di quanto, e lascia decidere.

Tre cose che non sono scostamenti e non vanno segnalate come tali:

- un mese che il gestionale non sa ancora calcolare (periodo aperto, dati
  mancanti) non e' uno scarto: e' un «non lo so», e si dice cosi';
- una LIPE assente per quel mese non rende sbagliato il nostro numero;
- una LIPE **a credito** non genera nessun F24: l'assenza del versamento e'
  corretta, non un pagamento dimenticato. Il caso da segnalare e' l'opposto,
  LIPE a debito senza F24.
"""
import logging
from typing import Any, Dict, List, Optional

from app.services.incroci_fiscali import (
    COLL_LIPE, SOGLIA_CENTS, STATO_ECCEDENTE, STATO_MANCANTE, STATO_OK, STATO_PARZIALE,
    confronta_importi, incroci,
)

__all__ = [
    "COLL_LIPE",
    "TOLLERANZA",
    "SOGLIA_VERSAMENTO",
    "scarto",
    "confronta_periodo",
    "confronto_mensile",
]

logger = logging.getLogger(__name__)

#: Sotto il centesimo i due numeri (gestionale ↔ LIPE) sono lo stesso numero.
TOLLERANZA = 0.01
#: Dovuto ↔ versato: la soglia del motore degli incroci, 1,00 EUR.
SOGLIA_VERSAMENTO = SOGLIA_CENTS / 100

ESITO_ALLINEATO = "allineato"
ESITO_SCOSTAMENTO = "scostamento"
ESITO_NOSTRO_ASSENTE = "gestionale_non_calcolabile"
ESITO_LIPE_ASSENTE = "lipe_assente"

#: Stati del nostro calcolo che non sono un numero da confrontare.
STATI_NON_CALCOLABILI = (None, "", "NON_CALCOLATO", "DATI_MANCANTI", "NON_VERIFICABILE")

#: Nota del versamento per stato del motore.
_NOTA_PER_STATO = {
    STATO_OK: "versato", STATO_MANCANTE: "f24_mancante",
    STATO_PARZIALE: "importo_diverso", STATO_ECCEDENTE: "importo_diverso",
}


def scarto(nostro: Optional[float], loro: Optional[float]) -> Optional[float]:
    """Nostro meno loro, o `None` se manca un lato. Mai zero per finta."""
    if nostro is None or loro is None:
        return None
    return round(float(nostro) - float(loro), 2)


def _quasi_zero(valore: Optional[float]) -> bool:
    return valore is not None and abs(valore) <= TOLLERANZA


def confronta_periodo(
    periodo: str,
    nostro: Optional[Dict[str, Any]],
    lipe: Optional[Dict[str, Any]],
    f24: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """La riga di confronto di un mese. Funzione pura: nessuna lettura."""
    nostro = nostro or {}
    # Audit 27/09/2026: un mese DATI_MANCANTI o NON_VERIFICABILE ha cifre
    # parziali (IVA acquisti None o vendite di pochi giorni): confrontarle
    # con la LIPE produceva uno «scostamento» che era solo un «non lo so».
    calcolabile = nostro.get("stato_calcolo") not in STATI_NON_CALCOLABILI

    nostra_vendite = nostro.get("iva_vendite") if calcolabile else None
    nostra_acquisti = nostro.get("iva_acquisti") if calcolabile else None

    lipe_esigibile = (lipe or {}).get("iva_esigibile")
    lipe_detratta = (lipe or {}).get("iva_detratta")

    s_vendite = scarto(nostra_vendite, lipe_esigibile)
    s_acquisti = scarto(nostra_acquisti, lipe_detratta)

    if lipe is None:
        esito = ESITO_LIPE_ASSENTE
    elif not calcolabile:
        esito = ESITO_NOSTRO_ASSENTE
    elif _quasi_zero(s_vendite) and _quasi_zero(s_acquisti):
        esito = ESITO_ALLINEATO
    else:
        esito = ESITO_SCOSTAMENTO

    # Il versamento: una LIPE a credito non deve produrre nessun F24. Lo
    # stato viene dal motore degli incroci (soglia 1,00 EUR), qui si traduce
    # nella nota del contratto.
    lipe_a_debito = (lipe or {}).get("iva_da_versare_o_credito_segno") == "debito"
    dovuto = (lipe or {}).get("iva_da_versare_o_credito") if lipe_a_debito else None
    pagato = (f24 or {}).get("importo")
    stato_versamento = (f24 or {}).get("stato")
    differenza = (f24 or {}).get("differenza")
    if not lipe:
        nota_f24 = "lipe_assente"
    elif not lipe_a_debito:
        nota_f24 = "nessun_versamento_dovuto" if pagato is None else "versamento_non_atteso"
    elif pagato is None:
        nota_f24 = "f24_mancante"
    else:
        if stato_versamento is None:
            esito_importi = confronta_importi(round(float(dovuto) * 100), round(float(pagato) * 100))
            stato_versamento = esito_importi["stato"]
            differenza = esito_importi["differenza_cents"] / 100
        nota_f24 = _NOTA_PER_STATO.get(stato_versamento, "importo_diverso")

    return {
        "periodo": periodo,
        "esito": esito,
        "gestionale": {
            "iva_vendite": nostra_vendite,
            "iva_acquisti": nostra_acquisti,
            "saldo": nostro.get("saldo") if calcolabile else None,
            "stato_calcolo": nostro.get("stato_calcolo"),
            "attendibile": nostro.get("attendibile"),
            "motivi": nostro.get("motivi") or [],
            "conteggi": nostro.get("conteggi") or {},
        },
        "commercialista_lipe": {
            "iva_esigibile": lipe_esigibile,
            "iva_detratta": lipe_detratta,
            "operazioni_attive": (lipe or {}).get("totale_operazioni_attive"),
            "operazioni_passive": (lipe or {}).get("totale_operazioni_passive"),
            "iva_da_versare_o_credito": (lipe or {}).get("iva_da_versare_o_credito"),
            "segno": (lipe or {}).get("iva_da_versare_o_credito_segno"),
            "quadratura_ok": (lipe or {}).get("quadratura_ok"),
        },
        "f24": {
            "dovuto_da_lipe": dovuto,
            "versato": pagato,
            "differenza": differenza if lipe_a_debito and pagato is not None else None,
            "stato": stato_versamento if lipe_a_debito and pagato is not None else None,
            "codice_tributo": (f24 or {}).get("codice_tributo"),
            "documenti": (f24 or {}).get("documenti") or [],
            "hints": (f24 or {}).get("hints") or [],
            "nota": nota_f24,
        },
        "scarti": {
            "iva_vendite": s_vendite,
            "iva_acquisti": s_acquisti,
        },
    }


async def confronto_mensile(db, anno: int) -> Dict[str, Any]:
    """Dodici righe di confronto per l'anno richiesto.

    LIPE e versamenti vengono dal motore degli incroci (una lettura sola del
    registro F24); qui si aggiunge il nostro calcolo mese per mese.
    """
    from app.services.iva_liquidation_query import get_iva_period_snapshot

    quadro = await incroci(db, anni=[anno])
    lipe_per_periodo: Dict[str, Dict[str, Any]] = {}
    async for doc in db[COLL_LIPE].find({"periodo": {"$regex": f"^{anno}"}}, {"_id": 0}):
        periodo = doc.get("periodo")
        if periodo:
            lipe_per_periodo[periodo] = doc

    f24_per_periodo: Dict[str, Dict[str, Any]] = {}
    for riga in quadro["confronti_iva_mensile"]:
        if riga["versato_f24"] is None or (not riga["f24_versamenti"] and not riga["versato_f24"]):
            continue
        f24_per_periodo[riga["periodo"]] = {
            "importo": riga["versato_f24"], "codice_tributo": riga["codice_tributo"],
            "documenti": riga["f24_sources"], "stato": riga["stato"], "differenza": riga["differenza"],
            "hints": riga["hints"],
        }

    righe: List[Dict[str, Any]] = []
    for mese in range(1, 13):
        periodo = f"{anno}-{mese:02d}"
        try:
            nostro = await get_iva_period_snapshot(db, anno=anno, mese=mese)
        except Exception as exc:  # noqa: BLE001 — un mese illeggibile non ferma l'anno
            logger.warning("Confronto IVA %s: gestionale non leggibile: %s: %s",
                           periodo, type(exc).__name__, exc)
            nostro = None
        righe.append(confronta_periodo(
            periodo, nostro, lipe_per_periodo.get(periodo), f24_per_periodo.get(periodo),
        ))

    conteggi: Dict[str, int] = {}
    for riga in righe:
        conteggi[riga["esito"]] = conteggi.get(riga["esito"], 0) + 1

    return {
        "anno": anno,
        "righe": righe,
        "conteggi": conteggi,
        "periodi_con_scostamento": [
            r["periodo"] for r in righe if r["esito"] == ESITO_SCOSTAMENTO
        ],
        "periodi_senza_lipe": [
            r["periodo"] for r in righe if r["esito"] == ESITO_LIPE_ASSENTE
        ],
        "f24_mancanti": [
            r["periodo"] for r in righe if r["f24"]["nota"] == "f24_mancante"
        ],
        "guardia": quadro["guardia"],
    }
