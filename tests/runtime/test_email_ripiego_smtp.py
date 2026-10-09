import pytest

from app.hr.services import email_smtp as e


def test_se_il_relay_fallisce_l_email_parte_con_smtp(monkeypatch):
    inviate = []
    monkeypatch.setattr(e, "_credenziali_relay", lambda: {"url": "https://x", "secret": "s"})
    monkeypatch.setattr(e, "credenziali_smtp", lambda: {"host": "h", "port": 465, "user": "u@x.it", "password": "p"})

    def relay_ko(*a, **k):
        raise RuntimeError("404")

    monkeypatch.setattr(e, "_invia_via_relay", relay_ko)
    monkeypatch.setattr(e, "_invia_via_smtp", lambda cred, d, o, c, *a, **k: inviate.append((d, o)))
    e.invia_email("bar@x.it", "Oggetto", "Corpo")
    assert inviate == [("bar@x.it", "Oggetto")]


def test_senza_smtp_resta_l_errore_del_relay(monkeypatch):
    monkeypatch.setattr(e, "_credenziali_relay", lambda: {"url": "https://x", "secret": "s"})
    monkeypatch.setattr(e, "credenziali_smtp", lambda: None)

    def relay_ko(*a, **k):
        raise RuntimeError("404 relay")

    monkeypatch.setattr(e, "_invia_via_relay", relay_ko)
    with pytest.raises(RuntimeError, match="404 relay"):
        e.invia_email("bar@x.it", "O", "C")


def test_con_il_relay_funzionante_non_si_usa_smtp(monkeypatch):
    usati = []
    monkeypatch.setattr(e, "_credenziali_relay", lambda: {"url": "https://x", "secret": "s"})
    monkeypatch.setattr(e, "_invia_via_relay", lambda *a, **k: usati.append("relay"))
    monkeypatch.setattr(e, "_invia_via_smtp", lambda *a, **k: usati.append("smtp"))
    e.invia_email("bar@x.it", "O", "C")
    assert usati == ["relay"]
