"""Confronto mensile fra l'IVA del gestionale e quella del commercialista.

Tre fonti, tre nature diverse, e non vanno confuse:

1. **il gestionale** — `iva_liquidation_query.get_iva_period_snapshot`, la
   fonte unica in lettura dei nostri numeri;
2. **la LIPE** — la Comunicazione Liquidazioni Periodiche IVA che il
   commercialista trasmette all'Agenzia. E' il documento **canonico**
   dell'IVA mensile: quando i due numeri divergono, quello giusto e' questo,
   e lo scarto e' un difetto nostro da spiegare;
3. **i prospetti F24** — quello che c'e' davvero da pagare, codici tributo
   6001..6012 (IVA mensile) con l'anno di riferimento.

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
from typing import Any, Dict, List, Optional

__all__ = [
    "COLL_LIPE",
    "TOLLERANZA",
    "scarto",
    "confronta_periodo",
    "f24_iva_per_periodo",
    "confronto_mensile",
]

COLL_LIPE = "lipe_periodi"
COLL_F24 = "f24_unificato"

#: Sotto il centesimo i due numeri sono lo stesso numero.
TOLLERANZA = 0.01

ESITO_ALLINEATO = "allineato"
ESITO_SCOSTAMENTO = "scostamento"
ESITO_NOSTRO_ASSENTE = "gestionale_non_calcolabile"
ESITO_LIPE_ASSENTE = "lipe_assente"


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
    calcolabile = nostro.get("stato_calcolo") not in (None, "NON_CALCOLATO")

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

    # Il versamento: una LIPE a credito non deve produrre nessun F24.
    lipe_a_debito = (lipe or {}).get("iva_da_versare_o_credito_segno") == "debito"
    dovuto = (lipe or {}).get("iva_da_versare_o_credito") if lipe_a_debito else None
    pagato = (f24 or {}).get("importo")
    if not lipe:
        nota_f24 = "lipe_assente"
    elif not lipe_a_debito:
        nota_f24 = "nessun_versamento_dovuto" if pagato is None else "versamento_non_atteso"
    elif pagato is None:
        nota_f24 = "f24_mancante"
    elif _quasi_zero(scarto(pagato, dovuto)):
        nota_f24 = "versato"
    else:
        nota_f24 = "importo_diverso"

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
            "codice_tributo": (f24 or {}).get("codice_tributo"),
            "documenti": (f24 or {}).get("documenti") or [],
            "nota": nota_f24,
        },
        "scarti": {
            "iva_vendite": s_vendite,
            "iva_acquisti": s_acquisti,
        },
    }


async def f24_iva_per_periodo(db, anno: int) -> Dict[str, Dict[str, Any]]:
    """I versamenti IVA mensili (6001..6012) dell'anno, per `YYYY-MM`.

    Un solo prefetch della collezione: la regola del §4 vieta una query per
    mese. L'anno sta sulla **riga** del tributo (`anno`), non sul modello:
    e' il periodo di riferimento del versamento, che non coincide con la
    data in cui l'F24 e' stato pagato.
    """
    per_periodo: Dict[str, Dict[str, Any]] = {}
    proiezione = {"_id": 0, "sezione_erario": 1, "file_name": 1, "status": 1}
    async for modello in db[COLL_F24].find({}, proiezione):
        if (modello.get("status") or "") in ("annullato", "stornato"):
            continue
        righe = modello.get("sezione_erario")
        if not isinstance(righe, list):
            continue
        for riga in righe:
            if not isinstance(riga, dict):
                continue
            codice = str(riga.get("codice_tributo") or "")
            anno_riga = str(riga.get("anno") or "")
            if not codice.startswith("60") or len(codice) != 4:
                continue
            mese = codice[2:]
            if not mese.isdigit() or not 1 <= int(mese) <= 12:
                continue
            if anno_riga != str(anno):
                continue
            chiave = f"{anno_riga}-{mese}"
            voce = per_periodo.setdefault(
                chiave, {"importo": 0.0, "codice_tributo": codice, "documenti": []}
            )
            voce["importo"] = round(
                voce["importo"] + float(riga.get("importo_debito") or 0), 2
            )
            nome = modello.get("file_name")
            if nome and nome not in voce["documenti"]:
                voce["documenti"].append(nome)
    return per_periodo


async def confronto_mensile(db, anno: int) -> Dict[str, Any]:
    """Dodici righe di confronto per l'anno richiesto."""
    from app.services.iva_liquidation_query import get_iva_period_snapshot

    lipe_per_periodo: Dict[str, Dict[str, Any]] = {}
    async for doc in db[COLL_LIPE].find(
        {"periodo": {"$regex": f"^{anno}"}}, {"_id": 0}
    ):
        periodo = doc.get("periodo")
        if periodo:
            lipe_per_periodo[periodo] = doc

    f24_per_periodo = await f24_iva_per_periodo(db, anno)

    righe: List[Dict[str, Any]] = []
    for mese in range(1, 13):
        periodo = f"{anno}-{mese:02d}"
        try:
            nostro = await get_iva_period_snapshot(db, anno=anno, mese=mese)
        except Exception:  # noqa: BLE001 — un mese illeggibile non ferma l'anno
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
    }
