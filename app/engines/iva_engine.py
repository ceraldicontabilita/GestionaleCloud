"""
Motore IVA — attribuzione del periodo di liquidazione per COMPETENZA.

Fonte di verità: memoria/SPECIFICA_IVA.md. Questo modulo implementa il cuore
fiscale della specifica: dato quando un'operazione è avvenuta e quando la
fattura è stata ricevuta/registrata, stabilisce a QUALE liquidazione IVA
mensile va attribuita l'IVA a credito (che NON coincide con il mese di
ricezione).

Regole (SPECIFICA_IVA.md §9):
  A — stesso mese: mese operazione == mese ricezione → periodo = mese ricezione.
  B — entro il 15 del mese successivo (stesso anno solare): ricezione E
      registrazione entro il giorno 15 → periodo = mese operazione.
  C — dopo il 15: oltre il giorno 15 → periodo = mese ricezione.
  D — cambio anno: anno ricezione > anno operazione → periodo = mese ricezione
      (mai retroattribuzione all'anno precedente; §6).
  E — già utilizzata: gestita a monte dal flag `iva_utilizzata` (qui non entra).

La "regola dei 12 giorni" (§3) è un controllo DOCUMENTALE sul fornitore
(emissione fattura) e NON determina il periodo IVA dell'acquirente: sta in
`controllo_emissione_12_giorni`, separata dall'attribuzione.
"""
from datetime import date
from typing import Optional, Tuple

# Etichette regola applicata (coerenti con la specifica §9)
STESSO_MESE = "STESSO_MESE"
ENTRO_15_MESE_SUCCESSIVO = "ENTRO_15_MESE_SUCCESSIVO"
RICEVUTA_DOPO_IL_15 = "RICEVUTA_DOPO_IL_15"
OPERAZIONE_ANNO_PRECEDENTE = "OPERAZIONE_ANNO_PRECEDENTE"


def _parse(d) -> Optional[date]:
    """Accetta date ('YYYY-MM-DD', datetime, date) → date, o None."""
    if d is None or d == "":
        return None
    if isinstance(d, date):
        return d
    s = str(d)[:10]
    try:
        y, m, g = int(s[0:4]), int(s[5:7]), int(s[8:10])
        return date(y, m, g)
    except (ValueError, TypeError, IndexError):
        return None


def _periodo(d: date) -> str:
    return f"{d.year}-{d.month:02d}"


def attribuisci_periodo_iva(
    data_operazione,
    data_ricezione,
    data_registrazione=None,
) -> Tuple[Optional[str], str]:
    """Ritorna (periodo_iva_attribuito 'YYYY-MM', regola_applicata).

    Se mancano le date essenziali ritorna (None, 'DA_VERIFICARE').
    `data_registrazione` assente = si usa la data di ricezione.
    """
    op = _parse(data_operazione)
    ric = _parse(data_ricezione)
    reg = _parse(data_registrazione) or ric
    if op is None or ric is None:
        return None, "DA_VERIFICARE"

    # Regola D — cambio anno: mai retroattribuire all'anno precedente.
    if ric.year > op.year:
        return _periodo(ric), OPERAZIONE_ANNO_PRECEDENTE

    # Ricezione precedente all'operazione o anni incoerenti: prudenza.
    if ric.year < op.year:
        return _periodo(ric), RICEVUTA_DOPO_IL_15

    # Da qui: stesso anno solare.
    # Regola A — stesso mese.
    if op.month == ric.month:
        return _periodo(ric), STESSO_MESE

    # Regola B — mese di ricezione = mese operazione + 1, entro il giorno 15
    # (sia ricezione sia registrazione), stesso anno.
    if ric.month == op.month + 1 and ric.day <= 15 and reg is not None and reg.day <= 15:
        return _periodo(op), ENTRO_15_MESE_SUCCESSIVO

    # Regola C — tutti gli altri casi (dopo il 15, o mesi più distanti):
    # l'IVA compete al mese di ricezione.
    return _periodo(ric), RICEVUTA_DOPO_IL_15


def controllo_emissione_12_giorni(data_operazione, data_trasmissione_sdi) -> dict:
    """Controllo DOCUMENTALE sul fornitore (§3): la fattura immediata va emessa
    entro 12 giorni dall'operazione. NON tocca il periodo IVA dell'acquirente:
    serve solo a segnalare un'anomalia sul fornitore.
    Ritorna {giorni, anomalia(bool), messaggio}."""
    op = _parse(data_operazione)
    tx = _parse(data_trasmissione_sdi)
    if op is None or tx is None:
        return {"giorni": None, "anomalia": False, "messaggio": "date insufficienti"}
    giorni = (tx - op).days
    anomalia = giorni > 12
    return {
        "giorni": giorni,
        "anomalia": anomalia,
        "messaggio": (
            f"Fattura trasmessa allo SDI dopo {giorni} giorni dall'operazione "
            f"(oltre i 12 previsti)" if anomalia else "Emissione nei termini"
        ),
    }
