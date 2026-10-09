"""Le copie identiche fra `app/` e `app/hr/` sono un solo modulo.

Sei sottopercorsi erano duplicati senza una sola differenza di
comportamento: quattro identici byte a byte, uno diverso per una riga di
docstring, e `audit_logger`, dove la copia HR era solo piu' povera (le
mancava `log_sicurezza`). Non c'era nulla da classificare: solo due file da
tenere allineati a mano, che e' il meccanismo con cui nasce la deriva descritta in
`tests/runtime/test_fork_app_hr.py` (il limite 15k di `document_ai_extractor`
rimasto sbagliato per mesi sul lato HR).

Per le eccezioni il re-export cambia anche qualcosa di sostanziale: prima
`app.exceptions.NotFoundError` e `app.hr.exceptions.NotFoundError` erano due
classi omonime e **distinte**, quindi un `except` scritto da un lato non
intercettava quella sollevata dall'altro.
"""
import pytest

COPPIE = [
    ("app.hr.services.payslip_pdf_parser", "app.services.payslip_pdf_parser",
     ["PayslipPDFParser", "parse_all_payslips"]),
    ("app.hr.utils.busta_paga_parser", "app.utils.busta_paga_parser",
     ["detect_format", "extract_busta_paga_data", "parse_italian_number"]),
    ("app.hr.utils.error_handler", "app.utils.error_handler",
     ["APIResponse", "handle_errors", "handle_errors_sync"]),
    ("app.hr.exceptions.custom_exceptions", "app.exceptions.custom_exceptions",
     ["AppError", "NotFoundError", "ValidationError", "validate_required_fields"]),
    ("app.hr.services.partite_aperte_engine", "app.services.partite_aperte_engine",
     ["crea_partita", "chiudi_partita", "ricalcola_residui"]),
    ("app.hr.services.audit_logger", "app.services.audit_logger",
     ["COLL_AUDIT_LOG", "get_storia_entita", "log_evento", "log_sicurezza"]),
]


@pytest.mark.parametrize("modulo_hr,modulo_erp,nomi", COPPIE)
def test_il_lato_hr_espone_gli_stessi_oggetti(modulo_hr, modulo_erp, nomi):
    import importlib

    hr = importlib.import_module(modulo_hr)
    erp = importlib.import_module(modulo_erp)
    for nome in nomi:
        assert getattr(hr, nome) is getattr(erp, nome), (
            f"{modulo_hr}.{nome} non e' lo stesso oggetto di "
            f"{modulo_erp}.{nome}: il fork e' tornato."
        )


def test_una_sola_classe_per_eccezione():
    """Due classi omonime e distinte non si intercettano a vicenda."""
    from app.exceptions import NotFoundError as erp_not_found
    from app.hr.exceptions import NotFoundError as hr_not_found

    assert hr_not_found is erp_not_found

    with pytest.raises(erp_not_found):
        raise hr_not_found("Dipendente", "abc")
