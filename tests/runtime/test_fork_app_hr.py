"""Guardia contro la crescita del fork `app/hr`.

`app/hr` e' nato come copia di `app/`: oggi ~46 sottopercorsi esistono in
entrambi. Il problema non e' l'estetica, e' che la deriva fra le due copie e'
fatta di CORREZIONI APPLICATE DA UN LATO SOLO, che restano invisibili finche'
qualcuno non inciampa nel ramo sbagliato. Due casi reali gia' accertati:

- `services/document_ai_extractor.py`: il limite del testo passato all'AI era
  stato alzato da 15.000 a 150.000 caratteri sul lato ERP, perche' tagliava
  estratti conto e PDF multipagina. La copia HR e' rimasta a 15.000 per mesi.
- `parsers/f24_parser.py`: le due copie divergevano sul formato anglosassone
  («1,234.56» valeva 1234.56 da un lato e 1.23456 dall'altro, un fattore
  1000 su un importo F24). Erano pero' entrambe irraggiungibili, quindi il
  difetto non era in produzione: rimosse il 19/09/2026 tenendo la sola
  `app/services/f24_parser.py`, che e' quella viva.

Questa guardia non pretende di smontare il fork: blocca soltanto la sua
CRESCITA. Un sottopercorso nuovo in entrambi i rami fa fallire la CI il giorno
in cui nasce, invece di lasciarlo vivere su un lato solo.

Quando una famiglia viene unificata, il suo sottopercorso si toglie da
`FORK_NOTO`: la lista puo' solo accorciarsi. Il test lo impone in entrambe le
direzioni, altrimenti il debito resterebbe scritto qui anche dopo essere stato
saldato.
"""
from pathlib import Path

RADICE = Path(__file__).resolve().parents[2]

# I marcatori di pacchetto non sono codice duplicato: un sotto-pacchetto deve
# averli per esistere.
IGNORATI = {"__init__.py"}

# ATTENZIONE a chi cerca codice morto con il criterio «mai citato in tests/»:
# questo file nomina i duplicati PROPRIO PERCHE' lo sono, non perche' siano
# usati. Contarlo fra le citazioni fa risultare vivi moduli irraggiungibili —
# e' successo il 19/09/2026 con i tre `f24_parser` che la Fase 1 si era persa.
# Va escluso dal corpus delle citazioni.

# Fotografia del 19/09/2026, accorciata dalla Fase 2 (i sette
# `services/handlers/*` HR erano copie del lato ERP e sono spariti).
# Solo da accorciare.
FORK_NOTO = {
    # Guscio della sotto-applicazione: legittimamente separati.
    "config.py",
    "database.py",
    "main.py",
    # Fork veri, da consolidare (vedi «Aperto» in CLAUDE.md).
    "exceptions/custom_exceptions.py",
    "parsers/busta_paga_multi_template.py",
    "parsers/payslip_parser_v2.py",
    "repositories/base_repository.py",
    "repositories/user_repository.py",
    "routers/auth.py",
    "routers/employees/dipendenti.py",
    "routers/f24_parser.py",
    "routers/libro_unico_parser.py",
    "routers/pin_login.py",
    "routers/tfr.py",
    "services/alert_engine.py",
    "services/audit_logger.py",
    "services/cedolini_manager.py",
    "services/document_ai_extractor.py",
    "services/event_bus.py",
    "services/paghe_riconciliazione.py",
    "services/partite_aperte_engine.py",
    "services/payslip_pdf_parser.py",
    "services/salari_unificati_v2.py",
    "utils/busta_paga_parser.py",
    "utils/dependencies.py",
    "utils/error_handler.py",
}


def _sottopercorsi_duplicati() -> set:
    app = RADICE / "app"
    hr = app / "hr"
    lato_erp = {
        p.relative_to(app).as_posix()
        for p in app.rglob("*.py")
        if not p.is_relative_to(hr)
    }
    lato_hr = {p.relative_to(hr).as_posix() for p in hr.rglob("*.py")}
    return {d for d in (lato_erp & lato_hr) if Path(d).name not in IGNORATI}


def test_nessun_nuovo_file_duplicato_fra_app_e_app_hr():
    nuovi = sorted(_sottopercorsi_duplicati() - FORK_NOTO)
    assert not nuovi, (
        "Nuovi file presenti con lo stesso sottopercorso sia in app/ sia in "
        "app/hr/:\n  " + "\n  ".join(nuovi) + "\n\n"
        "Il fork app/hr non deve crescere: una correzione applicata a una sola "
        "delle due copie resta invisibile (vedi il limite 15k di "
        "document_ai_extractor, rimasto sbagliato per mesi sul lato HR).\n"
        "Metti la logica in un solo modulo sotto app/ e fai del lato HR un "
        "re-export, come app/hr/services/document_ai_extractor.py."
    )


def test_il_fork_noto_non_elenca_file_gia_unificati():
    """La lista puo' solo accorciarsi: un residuo qui dentro racconterebbe un
    debito gia' saldato, ed e' esattamente il tipo di documentazione falsa che
    CLAUDE.md vieta."""
    spariti = sorted(FORK_NOTO - _sottopercorsi_duplicati())
    assert not spariti, (
        "Questi sottopercorsi non sono piu' duplicati: toglili da FORK_NOTO.\n  "
        + "\n  ".join(spariti)
    )
