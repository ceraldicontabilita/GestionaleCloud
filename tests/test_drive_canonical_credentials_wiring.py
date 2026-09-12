import asyncio

from app.services import (
    drive_cedolini_ingest,
    drive_documenti_ingest,
    drive_f24_ingest,
    drive_invoice_ingest,
    drive_quietanze_ingest,
)


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


def test_sync_generico_canale_sconosciuto_resta_fail_closed():
    result = asyncio.run(drive_documenti_ingest.sync(None, "canale_inesistente"))
    assert result["status"] == "error"
