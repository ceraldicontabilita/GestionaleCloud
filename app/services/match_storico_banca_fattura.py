"""Il punteggio con cui si rivalidano gli auto-abbinamenti storici banca↔fattura.

Era il cuore di `handlers/estratto_conto.py`, un **secondo** motore di
riconciliazione registrato sullo stesso evento `estratto_conto.importato` del
motore canonico (`riconcilia_documenti_e_pagamenti`). Marcava fatture
`pagato: True` su un punteggio, scriveva in Prima Nota banca con
`source="estratto_conto_auto"` e chiudeva le scadenze; le sue altre tre gambe
leggevano campi che in archivio non esistono —
`f24_unificato.totale_debito` (sta in `totali.totale_debito`),
`prima_nota_salari.importo` e `.nome_dipendente` (sono `importo_busta` e
`dipendente_nome`), `corrispettivi.riconciliato` — quindi non hanno mai
prodotto niente: zero righe `estratto_conto_auto` in Prima Nota e zero
proposte dei suoi quattro tipi in `operazioni_da_confermare`. I suoi test
passavano perche' costruivano documenti con quei campi.

Il motore e' stato cancellato. Resta solo il punteggio, perche'
`ripristina_abbinamenti_banca_senza_identita` lo usa per decidere se un
auto-abbinamento **gia' in archivio** (40 righe con
`riconciliazione_automatica`) regge la regola forte di identita': importo
esatto **piu'** nome fornitore **piu'** numero fattura leggibile in causale.
"""
import logging
import re
from datetime import datetime
from typing import Dict

logger = logging.getLogger(__name__)

# Scelta utente (10/07/2026): "solo importo esatto ±0,01 €".
TOLLERANZA_IMPORTO = 0.01      # solo importo esatto (±1 centesimo)
TOLLERANZA_GIORNI = 30         # finestra temporale del match storico
SOGLIA_AUTO = 0.90             # sopra questa soglia l'abbinamento storico regge


def punteggio_match_storico(movimento: Dict, fattura: Dict) -> float:
    """Punteggio 0-1 fra un movimento bancario e una fattura, gia' abbinati.

    Importo esatto (60%), identita' obbligatoria — nome fornitore **e** numero
    fattura leggibili in causale (30%) — e vicinanza di data (10%). Senza
    identita' torna 0: importo e data da soli generavano falsi positivi (un
    accredito NUMIA da 24,40 scambiato per una fattura Leasys).
    """
    if (movimento.get("tipo") or "").lower() != "uscita":
        return 0.0

    score = 0.0

    imp_mov = abs(float(movimento.get("importo", 0)))
    imp_fatt = float(fattura.get("importo_totale") or fattura.get("total_amount") or 0)

    if imp_mov <= 0 or imp_fatt <= 0:
        return 0.0

    # Match importo (peso 60%) — FILTRO DURO: solo importo esatto ±0,01 €
    # (scelta utente 10/07/2026), qualunque cosa dica la descrizione.
    importi_ammessi = [imp_fatt]
    if fattura.get("importo_residuo") is not None:
        importi_ammessi.append(float(fattura.get("importo_residuo") or 0))
    importi_ammessi.extend(
        float(rata.get("importo") or 0)
        for rata in fattura.get("pagamento_rate") or []
        if isinstance(rata, dict)
    )
    if any(
        valore > 0 and abs(imp_mov - valore) <= TOLLERANZA_IMPORTO
        for valore in importi_ammessi
    ):
        score += 0.60
    else:
        return 0.0  # importo diverso, scarta subito

    # Identita' obbligatoria: importo+data da soli generano falsi positivi
    # (es. accredito NUMIA da 24,40 scambiato per fattura Leasys).
    desc = " ".join(str(movimento.get(k) or "") for k in (
        "descrizione", "description", "descrizione_originale", "causale", "beneficiario"
    )).upper()
    forn = (fattura.get("cedente_denominazione") or
            fattura.get("fornitore_ragione_sociale") or
            fattura.get("supplier_name") or "").upper()
    stop = {"SRL", "SPA", "SNC", "SAS", "SOCIETA", "UNIPERSONALE", "ITALIA"}
    parole = [
        p for p in re.sub(r"[^A-Z0-9]+", " ", forn).split()
        if len(p) >= 4 and p not in stop
    ]
    match_fornitore = any(parola in desc for parola in parole[:6])

    numero = (fattura.get("numero_fattura") or fattura.get("numero_documento")
              or fattura.get("invoice_number") or "")
    from app.services.payment_invoice_matching import invoice_reference_in_text
    match_numero = invoice_reference_in_text(numero, desc)
    # Regola contabile unica: importo e fornitore non bastano, anche se la
    # data coincide e la candidata e' una sola. Il numero fattura deve essere
    # esplicitamente leggibile nella causale; in caso contrario non si crea
    # neppure una proposta automatica da questo motore legacy.
    if not (match_fornitore and match_numero):
        return 0.0
    score += 0.30

    # Match data (peso 10%)
    try:
        data_mov  = datetime.strptime(
            (movimento.get("data") or movimento.get("data_operazione") or "")[:10],
            "%Y-%m-%d"
        )
        data_fatt = datetime.strptime(
            (fattura.get("data_documento") or fattura.get("invoice_date") or "")[:10],
            "%Y-%m-%d"
        )
        delta = abs((data_mov - data_fatt).days)
        if delta <= 5:
            score += 0.10
        elif delta <= TOLLERANZA_GIORNI:
            score += 0.05
    except Exception as exc:  # noqa: BLE001
        # La data manca o non e' in ISO: il bonus di vicinanza non si somma,
        # il punteggio resta quello di importo piu' identita'. Il log dice
        # *quale* data non si e' letta, non «errore».
        logger.info(
            "Punteggio storico senza bonus data: movimento=%s fattura=%s (%s: %s)",
            movimento.get("data") or movimento.get("data_operazione"),
            fattura.get("data_documento") or fattura.get("invoice_date"),
            type(exc).__name__, exc,
        )

    return min(score, 1.0)
