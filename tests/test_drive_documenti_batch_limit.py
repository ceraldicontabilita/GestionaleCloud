from app.services import drive_documenti_ingest as d


def test_batch_size_default(monkeypatch):
    monkeypatch.delenv("DRIVE_DOCUMENTI_BATCH_SIZE", raising=False)
    assert d._batch_size() == 25


def test_batch_size_limiti(monkeypatch):
    monkeypatch.setenv("DRIVE_DOCUMENTI_BATCH_SIZE", "0")
    assert d._batch_size() == 1

    monkeypatch.setenv("DRIVE_DOCUMENTI_BATCH_SIZE", "250")
    assert d._batch_size() == 100

    monkeypatch.setenv("DRIVE_DOCUMENTI_BATCH_SIZE", "non-numero")
    assert d._batch_size() == 25
