from app.services import (
    drive_cedolini_ingest,
    drive_documenti_ingest,
    drive_f24_ingest,
    drive_invoice_ingest,
    drive_quietanze_ingest,
)


def test_scanner_canonici_condividono_lo_stesso_loader_senza_toccare_quello_generale():
    canonical = drive_invoice_ingest._load_credentials_fatture

    assert drive_cedolini_ingest._load_credentials_cedolini is canonical
    assert drive_quietanze_ingest._load_credentials_quietanze is canonical
    assert drive_f24_ingest._load_credentials is canonical
    assert drive_documenti_ingest._load_credentials is canonical

    # Il loader condiviso originale resta distinto: altri servizi (per esempio
    # il ledger Google Sheets) non vengono spostati implicitamente sulla
    # credenziale Drive canonica.
    assert drive_invoice_ingest._load_credentials is not canonical
