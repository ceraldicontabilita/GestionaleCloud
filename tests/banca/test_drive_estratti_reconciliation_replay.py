from pathlib import Path


def test_drive_sync_non_rilancia_la_riconciliazione_generale():
    """Il job Drive usa le pipeline incrementali e non rilegge lo storico."""
    sorgente = Path("app/services/drive_estratti_conto_ingest.py").read_text(
        encoding="utf-8"
    )

    assert '"reason": "gestita_dalle_pipeline_incrementali"' in sorgente
    assert "await riconcilia_movimenti_banca(" not in sorgente


def test_fattura_arrivata_dopo_ec_riprocessa_solo_i_candidati():
    sorgente = Path("app/routers/invoices/fatture_upload.py").read_text(
        encoding="utf-8"
    )

    assert "riprocessa_estratto_dopo_import_fattura(db, invoice)" in sorgente
    assert "riconcilia_movimenti_banca(movimento_ids=movimento_ids)" in sorgente


def test_scheduler_estratti_conto_gira_ogni_cinque_minuti():
    sorgente = Path("app/scheduler.py").read_text(encoding="utf-8")
    blocco = sorgente.split('id="drive_estratti_conto_ingest"', 1)[0].rsplit(
        "scheduler.add_job(", 1
    )[1]

    assert "'interval', minutes=5" in blocco
