from pathlib import Path


def test_drive_sync_rilancia_la_riconciliazione_del_periodo_operativo():
    """L'EC puo' precedere la fattura, senza riesaminare lo storico escluso."""
    sorgente = Path("app/services/drive_estratti_conto_ingest.py").read_text(
        encoding="utf-8"
    )

    assert 'data_dal = f"{anno_minimo}-01-01"' in sorgente
    assert "await riconcilia_movimenti_banca(\n                data_dal=data_dal" in sorgente
    assert "riconcilia_movimenti_banca(movimento_ids=" not in sorgente


def test_scheduler_estratti_conto_gira_ogni_cinque_minuti():
    sorgente = Path("app/scheduler.py").read_text(encoding="utf-8")
    blocco = sorgente.split('id="drive_estratti_conto_ingest"', 1)[0].rsplit(
        "scheduler.add_job(", 1
    )[1]

    assert "'interval', minutes=5" in blocco
