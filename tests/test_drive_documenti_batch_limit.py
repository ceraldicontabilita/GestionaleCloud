from app.services import drive_documenti_ingest as d


def test_batch_size_fisso_e_sicuro(monkeypatch):
    """Il motore generico lavora sempre a lotti di 25 documenti per ciclo."""
    monkeypatch.delenv("DRIVE_DOCUMENTI_BATCH_SIZE", raising=False)
    assert d._batch_size() == 25

    # Eventuali vecchie variabili Render non devono riaprire una catch-up storm.
    monkeypatch.setenv("DRIVE_DOCUMENTI_BATCH_SIZE", "250")
    assert d._batch_size() == 25
