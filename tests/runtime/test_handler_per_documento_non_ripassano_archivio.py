"""Guardia: un handler che scatta PER DOCUMENTO non ripassa l'intero archivio.

Il 20/09/2026 le 49 fatture di settembre non entravano. Non era Drive, non era
il parser: era `on_fattura_created_riprocessa`, registrato su `fattura.created`.

`fattura.created` nasce **una volta per fattura**, e il giro Drive ne importa 25
per volta. Quell'handler eseguiva cinque motori che lavorano su intere
collezioni — fra cui `riprocessa_bonifici_pendenti(limit=2000)` su
`bonifici_transfers`, che pesa 90 MB. Quindi importare 25 fatture costava 25
ripassi completi dell'archivio.

Misurato in produzione quel giorno: CPU 0,95 su 1 core, RAM 1,13 GB su 2,
`gestionale.documents` a 1.172 MB, il giro da 15 minuti che non finiva mai
(«Execution of job ... skipped: maximum number of running instances reached»),
l'istanza riavviata a meta' file, e Supabase che rispondeva 520/522 perche' era
il gestionale stesso a martellarlo. Delle 49 fatture ne erano entrate 4.

Gli stessi cinque motori sono gia' nel giro «Automazioni Prima Nota» (ogni 30
minuti), che chiama `riconcilia_documenti_e_pagamenti`: un sovrainsieme
stretto, idempotente, uno solo. L'handler per-documento era un doppione — e i
doppioni, dice CLAUDE.md, si eliminano, non si affiancano.

Questa guardia impedisce che un ripasso globale torni su un evento
per-documento. Non vieta i motori: vieta di chiamarli da li'.
"""
import inspect

import pytest

from app.services.event_bus import EventTypes, _handlers, register_all_handlers

# Motori che leggono o riscrivono una collezione intera. Chiamarli una volta per
# documento importato moltiplica il costo per il numero di documenti del lotto.
MOTORI_GLOBALI = (
    "run_auto_match",
    "riprocessa_bonifici_pendenti",
    "riprocessa_intenti_assegni",
    "riprocessa_collegamenti_paypal",
    "riconcilia_paypal_importato",
    "reconcile_deterministic_invoice_allocations",
    "riconcilia_documenti_e_pagamenti",
)

# Eventi che nascono una volta per singolo documento importato.
EVENTI_PER_DOCUMENTO = (
    EventTypes.FATTURA_CREATED,
    EventTypes.CORRISPETTIVO_REGISTRATO,
)


@pytest.fixture(scope="module", autouse=True)
def _registra_gli_handler_veri():
    """Registra gli handler come all'avvio: il test guarda il registro vero."""
    _handlers.clear()
    register_all_handlers()
    yield
    _handlers.clear()


def _motori_globali_chiamati(handler) -> list:
    try:
        sorgente = inspect.getsource(handler)
    except (OSError, TypeError):  # pragma: no cover - builtin o lambda
        return []
    return [m for m in MOTORI_GLOBALI if m in sorgente]


@pytest.mark.parametrize("evento", EVENTI_PER_DOCUMENTO)
def test_nessun_handler_per_documento_ripassa_tutto_l_archivio(evento):
    colpevoli = {
        handler.__name__: motori
        for handler in _handlers.get(evento, [])
        if (motori := _motori_globali_chiamati(handler))
    }
    assert not colpevoli, (
        f"Handler registrati su '{evento}' che ripassano l'intero archivio:\n  "
        + "\n  ".join(f"{nome} -> {', '.join(motori)}" for nome, motori in colpevoli.items())
        + "\n\n'" + evento + "' nasce UNA VOLTA PER DOCUMENTO e il giro Drive ne "
        "importa 25 alla volta: un motore che legge una collezione intera va "
        "chiamato una volta sola, dal giro «Automazioni Prima Nota» (ogni 30 "
        "minuti, `riconcilia_documenti_e_pagamenti`), non da qui. Il 20/09/2026 "
        "questo ha impedito a 45 fatture su 49 di entrare in archivio."
    )


def test_il_ripasso_completo_esiste_ancora_nel_giro_dei_30_minuti():
    """Tolto dal per-documento, il ripasso NON deve sparire: sta nello scheduler.

    Senza questo controllo la guardia sopra si potrebbe soddisfare cancellando
    anche il giro periodico, e gli agganci tardivi (una fattura che arriva dopo
    l'assegno) non avverrebbero mai piu'.
    """
    from pathlib import Path

    scheduler = Path(__file__).resolve().parents[2] / "app" / "scheduler.py"
    sorgente = scheduler.read_text(encoding="utf-8")
    assert "riconcilia_documenti_e_pagamenti" in sorgente, (
        "Il giro «Automazioni Prima Nota» non chiama piu' "
        "`riconcilia_documenti_e_pagamenti`: senza di lui nessuno ripassa piu' "
        "assegni, bonifici PDF, PayPal e allocazioni, e una prova arrivata dopo "
        "il documento non viene piu' agganciata."
    )


def test_i_motori_globali_restano_dentro_il_ripasso_unico():
    """Il giro dei 30 minuti deve coprire tutti i motori tolti dall'handler."""
    from app.services import reconciliation_orchestrator, paypal_reconciliation_pipeline

    sorgente = inspect.getsource(
        reconciliation_orchestrator.riconcilia_documenti_e_pagamenti
    )
    # Il sottopasso PayPal ora ha una sola implementazione condivisa dagli
    # import, ma rimane chiamato dal ripasso periodico.
    if "riconcilia_paypal_importato" in sorgente:
        sorgente += inspect.getsource(paypal_reconciliation_pipeline.riconcilia_paypal_importato)
    mancanti = [
        m for m in MOTORI_GLOBALI
        if m != "riconcilia_documenti_e_pagamenti" and m not in sorgente
    ]
    assert not mancanti, (
        "`riconcilia_documenti_e_pagamenti` non chiama piu': "
        + ", ".join(mancanti)
        + ". Erano nell'handler per-fattura tolto il 20/09/2026: se escono anche "
        "da qui, quel lavoro non lo fa piu' nessuno."
    )
