"""
Arricchimento IVA delle fatture di acquisto (SPECIFICA_IVA.md §7, §9).

Data una fattura ricevuta (documento `invoices`), calcola i campi IVA per
competenza usando il motore `iva_engine`: date normalizzate, periodo IVA
attribuito, regola applicata, stato di detrazione. Non modifica nulla di
esistente: aggiunge solo i campi IVA, preservando `iva_utilizzata` se la
fattura è già stata inserita in una liquidazione.
"""
from typing import Any, Dict, List, Optional

from app.engines import iva_engine


def _data_operazione_da_righe(linee: Optional[List[Dict[str, Any]]]) -> Optional[str]:
    """Per le fatture periodiche l'operazione è il periodo indicato nelle righe:
    si usa la data di FINE periodo (quando l'operazione si è conclusa)."""
    if not linee:
        return None
    for l in linee:
        fine = (l.get("data_fine_periodo") or "").strip()
        if fine:
            return fine[:10]
    for l in linee:
        inizio = (l.get("data_inizio_periodo") or "").strip()
        if inizio:
            return inizio[:10]
    return None


def campi_iva_da_fattura(inv: Dict[str, Any]) -> Dict[str, Any]:
    """Ritorna i campi IVA da aggiungere/aggiornare su una fattura di acquisto.

    Non tocca l'IVA già utilizzata: se `iva_utilizzata` è True resta True e lo
    stato resta 'INSERITA_IN_LIQUIDAZIONE' (una fattura in liquidazione
    confermata non va ri-attribuita)."""
    data_documento = inv.get("data_documento") or inv.get("invoice_date")
    data_operazione = _data_operazione_da_righe(inv.get("linee")) or data_documento
    # Data di ricezione: quando la fattura è diventata disponibile nel
    # gestionale. Priorità: campo esplicito → data importazione (created_at).
    data_ricezione = (
        inv.get("data_ricezione_sdi")
        or inv.get("data_ricezione")
        or (str(inv.get("created_at"))[:10] if inv.get("created_at") else None)
        or data_documento
    )
    data_registrazione = inv.get("data_registrazione") or data_ricezione

    periodo_attribuito, regola = iva_engine.attribuisci_periodo_iva(
        data_operazione, data_ricezione, data_registrazione
    )

    iva = float(inv.get("iva") or inv.get("total_iva") or inv.get("iva_totale") or 0)
    gia_utilizzata = bool(inv.get("iva_utilizzata"))

    if gia_utilizzata:
        stato = "INSERITA_IN_LIQUIDAZIONE"
        # P1-b (fix 13/07/2026): una fattura la cui IVA è già stata usata in una
        # liquidazione confermata NON va ri-attribuita. Si preserva il periodo
        # attribuito esistente (allineato al periodo utilizzato), evitando che
        # un ricalcolo produca attribuito ≠ utilizzato e quadri incoerenti.
        periodo_attribuito_finale = (
            inv.get("periodo_iva_attribuito")
            or inv.get("periodo_iva_utilizzato")
            or periodo_attribuito
        )
    elif periodo_attribuito is None:
        stato = "DA_VERIFICARE"
        periodo_attribuito_finale = periodo_attribuito
    else:
        stato = "DA_INSERIRE"
        periodo_attribuito_finale = periodo_attribuito

    return {
        "data_documento": data_documento,
        "data_operazione": data_operazione,
        "data_ricezione": data_ricezione,
        "data_registrazione": data_registrazione,
        "periodo_iva_attribuito": periodo_attribuito_finale,
        "regola_iva_applicata": regola,
        "iva_detraibile": round(iva, 2),
        "iva_utilizzata": gia_utilizzata,
        "periodo_iva_utilizzato": inv.get("periodo_iva_utilizzato"),
        "stato_detrazione_iva": inv.get("stato_detrazione_iva") if gia_utilizzata else stato,
    }
