import asyncio

from app.services import (
    drive_cedolini_ingest,
    drive_documenti_ingest,
    drive_estratti_conto_ingest,
    drive_f24_ingest,
    drive_invoice_ingest,
    drive_quietanze_ingest,
)
from app.services import drive_credential_probe


def test_scanner_canonici_hanno_loader_specifici_e_lasciano_intatto_quello_generale():
    loaders = {
        drive_invoice_ingest._load_credentials_fatture,
        drive_cedolini_ingest._load_credentials_cedolini,
        drive_quietanze_ingest._load_credentials_quietanze,
        drive_f24_ingest._load_credentials,
    }
    assert len(loaders) == 4
    assert drive_invoice_ingest._load_credentials not in loaders


def test_ingest_generico_e_wrappato_per_selezionare_il_folder_del_canale():
    assert drive_documenti_ingest.sync.__name__ == "sync_with_folder_probe"
    assert drive_documenti_ingest._build_drive_service.__name__ == "build_with_folder_probe"


def test_estratti_usa_loader_multi_root_verificato():
    assert drive_estratti_conto_ingest._load_credentials_estratti.__name__ == "_load_estratti_verified"


def test_sync_generico_canale_sconosciuto_resta_fail_closed():
    result = asyncio.run(drive_documenti_ingest.sync(None, "canale_inesistente"))
    assert result["status"] == "error"


def test_probe_prova_prima_il_loader_condiviso_reale(monkeypatch):
    sentinel = object()
    accessi = []

    monkeypatch.setattr(
        drive_invoice_ingest,
        "_load_credentials",
        lambda: (sentinel, None),
    )
    monkeypatch.setattr(
        drive_credential_probe,
        "_can_access",
        lambda creds, folder_id: accessi.append((creds, folder_id)) or True,
    )
    monkeypatch.setattr(
        drive_credential_probe,
        "_raw_candidates",
        lambda: iter(()),
    )

    creds, err = drive_credential_probe.load_credentials_for_folder("folder-canonico")

    assert creds is sentinel
    assert err is None
    assert accessi == [(sentinel, "folder-canonico")]


def test_probe_diagnostica_quante_credenziali_ha_davvero_provato(monkeypatch):
    shared = object()
    dedicata = object()

    monkeypatch.setattr(
        drive_invoice_ingest,
        "_load_credentials",
        lambda: (shared, None),
    )
    monkeypatch.setattr(
        drive_credential_probe,
        "_raw_candidates",
        lambda: iter((("DEDICATA", "raw"),)),
    )
    monkeypatch.setattr(
        drive_credential_probe,
        "_credentials_from_raw",
        lambda raw: dedicata,
    )
    monkeypatch.setattr(
        drive_credential_probe,
        "_can_access",
        lambda creds, folder_id: False,
    )

    creds, err = drive_credential_probe.load_credentials_for_folder("folder-canonico")

    assert creds is None
    assert "credenziali provate=2" in err
    assert "errori caricamento=0" in err


def test_probe_multi_root_rifiuta_credenziale_che_vede_solo_una_radice(monkeypatch):
    shared = object()
    dedicata = object()
    accessi = []

    monkeypatch.setattr(
        drive_credential_probe,
        "_shared_candidate",
        lambda: (shared, None),
    )
    monkeypatch.setattr(
        drive_credential_probe,
        "_raw_candidates",
        lambda: iter((("DEDICATA", "raw"),)),
    )
    monkeypatch.setattr(
        drive_credential_probe,
        "_credentials_from_raw",
        lambda raw: dedicata,
    )

    def can_access(creds, folder_id):
        accessi.append((creds, folder_id))
        if creds is shared:
            return folder_id == "root-a"
        return False

    monkeypatch.setattr(drive_credential_probe, "_can_access", can_access)

    creds, err = drive_credential_probe.load_credentials_for_folders(
        ["root-a", "root-b"]
    )

    assert creds is None
    assert "radici=2" in err
    assert "credenziali provate=2" in err
    assert (shared, "root-a") in accessi
    assert (shared, "root-b") in accessi


def test_probe_multi_root_accetta_solo_stessa_credenziale_su_tutte_le_radici(monkeypatch):
    shared = object()

    monkeypatch.setattr(
        drive_credential_probe,
        "_shared_candidate",
        lambda: (shared, None),
    )
    monkeypatch.setattr(
        drive_credential_probe,
        "_raw_candidates",
        lambda: iter(()),
    )
    monkeypatch.setattr(
        drive_credential_probe,
        "_can_access",
        lambda creds, folder_id: creds is shared and folder_id in {"root-a", "root-b"},
    )

    creds, err = drive_credential_probe.load_credentials_for_folders(
        ["root-a", "root-b", "root-a"]
    )

    assert creds is shared
    assert err is None
