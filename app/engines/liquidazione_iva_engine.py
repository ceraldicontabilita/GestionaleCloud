"""
Motore liquidazione IVA mensile — SELEZIONE fatture e TOTALI (logica pura).

Fonte di verità: la specifica del titolare (non è nel repository: vale il codice) §10-13, §18, §22.

Questo modulo NON tocca il database: riceve una lista di fatture (già
arricchite dal motore `iva_fatture`/`iva_engine`, quindi con
`periodo_iva_attribuito`, `iva_detraibile`, `iva_utilizzata`,
`stato_detrazione_iva`) e stabilisce, per un dato periodo mensile 'YYYY-MM',
quali entrano nella liquidazione e quali no (con il motivo). Calcola poi i
totali (IVA acquisti, saldo) dato l'IVA vendite e il credito precedente.

Il DIVIETO DI DUPLICAZIONE (§11) è realizzato qui a monte del calcolo:
una fattura con `iva_utilizzata = true` viene sempre esclusa dal nuovo
calcolo, così la stessa IVA non finisce in due liquidazioni. La marcatura
effettiva di `iva_utilizzata` avviene solo alla CONFERMA, gestita dal router.
"""
from typing import Any, Dict, List, Tuple

# Stati della liquidazione (SPECIFICA_IVA.md §12)
BOZZA = "BOZZA"
CALCOLATA = "CALCOLATA"
DA_VERIFICARE = "DA_VERIFICARE"
CONFERMATA = "CONFERMATA"
TRASMESSA = "TRASMESSA"
RIAPERTA = "RIAPERTA"
RETTIFICATA = "RETTIFICATA"

STATI_LIQUIDAZIONE = {
    BOZZA, CALCOLATA, DA_VERIFICARE, CONFERMATA, TRASMESSA, RIAPERTA, RETTIFICATA,
}
# Una liquidazione in questi stati non deve essere sovrascritta senza riapertura.
STATI_BLOCCATI = {CONFERMATA, TRASMESSA}

# Tipi di movimento IVA per fattura (SPECIFICA_IVA.md §22 movimenti_iva_fattura)
MOV_ATTRIBUZIONE = "ATTRIBUZIONE"
MOV_UTILIZZO = "UTILIZZO"
MOV_ESCLUSIONE = "ESCLUSIONE"
MOV_RETTIFICA = "RETTIFICA"
MOV_RECUPERO_ANNUALE = "RECUPERO_ANNUALE"

# Stati detrazione che rendono una fattura AMMISSIBILE a un nuovo calcolo (§10)
# ``NON_VALUTATA`` (valore storico, nessuno lo scrive piu') vuol dire «non
# deciso»: come nel riepilogo annuale non entra nel calcolo ma blocca il mese.
STATI_DETRAZIONE_AMMESSI = {"DA_INSERIRE", "RINVIATA"}
STATI_DETRAZIONE_DA_DECIDERE = ("DA_VERIFICARE", "NON_VALUTATA")

# Note di credito ricevute: RIDUCONO l'IVA detraibile (audit 27/09/2026,
# punto 8). Prima erano escluse dal calcolo (liquidazione) o sommate in
# positivo (dashboard): entrano col segno negativo.
from app.constants.tipi_documento import TIPI_NOTA_CREDITO


def e_nota_credito(f: Dict[str, Any]) -> bool:
    return str(f.get("tipo_documento") or "").upper() in TIPI_NOTA_CREDITO


def _iva_detraibile(f: Dict[str, Any]) -> float:
    """IVA detraibile gia' classificata, mai l'IVA totale per presunzione."""
    val = f.get("iva_detraibile")
    try:
        return round(float(val or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def iva_detraibile_con_segno(f: Dict[str, Any]) -> float:
    """IVA detraibile col segno della liquidazione: positiva per una fattura,
    negativa per una nota di credito (TD04/TD08), qualunque segno porti il
    documento (l'XML di una nota di credito ha di norma importi positivi)."""
    valore = _iva_detraibile(f)
    return -abs(valore) if e_nota_credito(f) else valore


def detraibilita_da_decidere(f: Dict[str, Any]) -> bool:
    """La fattura porta IVA ma nessuno ha ancora deciso quanta se ne detrae:
    ``iva_detraibile`` assente (non zero: non deciso) o stato
    ``DA_VERIFICARE``. Un documento senza IVA non ha nulla da decidere; uno
    gia' usato in una liquidazione, annullato o duplicato non conta."""
    if f.get("annullata") is True or f.get("duplicata") is True or f.get("iva_utilizzata") is True:
        return False
    if f.get("stato_detrazione_iva") == "INDETRAIBILE":
        return False
    iva_documento = 0.0
    for chiave in ("iva_documento", "iva", "total_tax", "totale_iva"):
        try:
            iva_documento = abs(float(f.get(chiave) or 0))
        except (TypeError, ValueError):
            continue
        if iva_documento:
            break
    if f.get("iva_detraibile") is None:
        return iva_documento > 0
    return f.get("stato_detrazione_iva") in STATI_DETRAZIONE_DA_DECIDERE


def _id_fattura(f: Dict[str, Any]) -> Any:
    return f.get("id") or f.get("_id")


def seleziona_fatture_per_liquidazione(
    fatture: List[Dict[str, Any]],
    periodo: str,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Divide le fatture del periodo in INCLUSE ed ESCLUSE (con motivo).

    Regole di inclusione (§10):
      - periodo_iva_attribuito == periodo
      - iva_utilizzata != true          (divieto di duplicazione §11)
      - iva_detraibile diversa da zero
      - documento non annullato/duplicato
      - stato_detrazione_iva in {DA_INSERIRE, RINVIATA}
      - una nota di credito (TD04/TD08) entra col segno negativo

    Ritorna (incluse, escluse). Ogni voce ESCLUSA ha `motivo_esclusione`.
    Le fatture di un periodo diverso NON compaiono nel risultato: non
    riguardano questa liquidazione.
    """
    incluse: List[Dict[str, Any]] = []
    escluse: List[Dict[str, Any]] = []

    for f in fatture:
        if f.get("periodo_iva_attribuito") != periodo:
            continue  # non appartiene a questo periodo: non è né inclusa né esclusa qui

        def _escludi(motivo: str):
            escluse.append({
                "id": _id_fattura(f),
                "invoice_number": f.get("invoice_number"),
                "supplier_name": f.get("supplier_name"),
                "iva": _iva_detraibile(f),
                "motivo_esclusione": motivo,
            })

        if f.get("annullata") is True:
            _escludi("Documento annullato")
            continue
        if f.get("duplicata") is True:
            _escludi("Documento duplicato")
            continue
        if f.get("iva_utilizzata") is True:
            # §11: già utilizzata in una precedente liquidazione
            _escludi(
                f"Già utilizzata nella liquidazione {f.get('periodo_iva_utilizzato') or 'precedente'}"
            )
            continue
        stato = f.get("stato_detrazione_iva")
        if stato is not None and stato not in STATI_DETRAZIONE_AMMESSI:
            _escludi(f"Stato detrazione '{stato}' non ammesso nel calcolo")
            continue
        if (abs(_iva_detraibile(f)) if e_nota_credito(f) else _iva_detraibile(f)) <= 0:
            _escludi("IVA detraibile nulla o negativa")
            continue

        incluse.append(f)

    return incluse, escluse


def seleziona_fatture_per_competenza(
    fatture: List[Dict[str, Any]],
    periodo: str,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Seleziona la base IVA di competenza del mese.

    Questa vista risponde alla domanda *quanta IVA detraibile appartiene al
    periodo?* e non alla domanda *quanta IVA posso ancora inserire in una
    nuova liquidazione?*. Per questo ``iva_utilizzata`` e qualunque campo di
    pagamento (cassa, banca, pagata/non pagata) non sono criteri di
    esclusione. L'utilizzo viene esposto separatamente dal chiamante.

    Restano escluse soltanto le posizioni che non contribuiscono: documenti
    annullati o duplicati, indetraibili esplicite e fatture senza IVA
    detraibile classificata. Le note di credito entrano col segno negativo.
    """
    incluse: List[Dict[str, Any]] = []
    escluse: List[Dict[str, Any]] = []

    for f in fatture:
        if f.get("periodo_iva_attribuito") != periodo:
            continue

        def _escludi(motivo: str) -> None:
            escluse.append({
                "id": _id_fattura(f),
                "invoice_number": f.get("invoice_number"),
                "supplier_name": f.get("supplier_name"),
                "iva": _iva_detraibile(f),
                "motivo_esclusione": motivo,
            })

        if f.get("annullata") is True:
            _escludi("Documento annullato")
            continue
        if f.get("duplicata") is True:
            _escludi("Documento duplicato")
            continue
        if f.get("stato_detrazione_iva") == "INDETRAIBILE":
            _escludi("IVA esplicitamente indetraibile")
            continue
        if abs(_iva_detraibile(f)) <= 0 or (not e_nota_credito(f) and _iva_detraibile(f) < 0):
            _escludi("IVA detraibile non classificata o nulla")
            continue

        incluse.append(f)

    return incluse, escluse


def calcola_totali(
    incluse: List[Dict[str, Any]],
    iva_vendite: float = 0.0,
    credito_precedente: float = 0.0,
) -> Dict[str, float]:
    """Calcola i totali della liquidazione dato l'elenco delle fatture incluse.

    saldo = iva_vendite - iva_acquisti - credito_precedente
      saldo > 0 → IVA a DEBITO (da versare)
      saldo < 0 → IVA a CREDITO (riportata al periodo successivo)
    """
    iva_acquisti = round(sum(iva_detraibile_con_segno(f) for f in incluse), 2)
    iva_vendite = round(float(iva_vendite or 0), 2)
    credito_precedente = round(float(credito_precedente or 0), 2)
    saldo = round(iva_vendite - iva_acquisti - credito_precedente, 2)
    return {
        "iva_vendite": iva_vendite,
        "iva_acquisti": iva_acquisti,
        "credito_precedente": credito_precedente,
        "saldo": saldo,
        "debito_periodo": saldo if saldo > 0 else 0.0,
        "credito_periodo": round(-saldo, 2) if saldo < 0 else 0.0,
    }
