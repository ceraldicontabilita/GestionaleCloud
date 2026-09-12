from app import scheduler as scheduler_module
from app.services.scheduler_sheets_sync_policy import automatic_sheets_sync_enabled


def test_full_sync_automatico_sheets_attivo_solo_con_backend_sheets():
    assert automatic_sheets_sync_enabled("sheets") is True
    assert automatic_sheets_sync_enabled(" SHEETS ") is True
    assert automatic_sheets_sync_enabled("supabase") is False
    assert automatic_sheets_sync_enabled("") is False


def test_policy_scheduler_sheets_installata():
    assert getattr(
        scheduler_module.scheduler,
        "_sheets_sync_policy_installed",
        False,
    ) is True


def test_policy_non_modifica_sync_all_manuale():
    from app.services import google_sheets_ledger

    # Il job periodico viene neutralizzato a livello scheduler. La funzione di
    # export/sync resta intatta per l'azione manuale dell'amministratore.
    assert callable(google_sheets_ledger.sync_all)
    assert google_sheets_ledger.sync_all.__name__ == "sync_all"
