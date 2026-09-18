from app.menu import qromo_auto_sync as mod


def test_auto_sync_qromo_non_parte_per_default(monkeypatch):
    avviati = []
    monkeypatch.delenv("ENABLE_QROMO_AUTO_SYNC", raising=False)
    monkeypatch.setattr(mod, "_started", False)
    monkeypatch.setattr(mod.threading.Thread, "start", lambda self: avviati.append(self))

    assert mod.avvia_sync_qromo_background() is False
    assert avviati == []
    assert mod._started is False


def test_auto_sync_qromo_richiede_opt_in_esplicito(monkeypatch):
    avviati = []
    monkeypatch.setenv("ENABLE_QROMO_AUTO_SYNC", "true")
    monkeypatch.setattr(mod, "_started", False)
    monkeypatch.setattr(mod.threading.Thread, "start", lambda self: avviati.append(self))

    assert mod.avvia_sync_qromo_background() is True
    assert len(avviati) == 1
    assert mod._started is True
    assert mod.avvia_sync_qromo_background() is False
    assert len(avviati) == 1
