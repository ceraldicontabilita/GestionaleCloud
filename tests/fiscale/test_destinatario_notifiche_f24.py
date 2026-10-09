"""L'email delle scadenze F24 non e' mai partita, e nessuno lo sapeva.

Il destinatario veniva cercato in `configurazioni` e poi in `users`: due
collezioni in cui **nessun punto del codice scrive mai**, e che in produzione
hanno zero righe. Nessun destinatario, nessun invio, nemmeno una riga di log
— proprio sulle scadenze fiscali, dove il silenzio costa una sanzione.

Misurato il 19/09/2026 col censimento delle collezioni: su 196 nomi usati dal
codice, 26 sono letti e mai scritti da nessuno. Queste due erano fra quelle.
"""
import asyncio

import pytest

from app.services.f24_scadenze_notifiche import destinatario_notifiche


def _run(coroutine):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coroutine)
    finally:
        loop.close()


class _Db:
    def __init__(self, dati=None, esplode=()):
        self._dati = dati or {}
        self._esplode = set(esplode)

    def __getitem__(self, nome):
        db = self

        class _Coll:
            async def find_one(self, query=None, proj=None):
                if nome in db._esplode:
                    raise RuntimeError("collezione non leggibile")
                return db._dati.get(nome)
        return _Coll()


# ── Il difetto: due collezioni vuote e nessun avviso ──────────────────────

def test_senza_nessuna_fonte_non_inventa_un_destinatario(monkeypatch, caplog):
    monkeypatch.delenv("ADMIN_EMAIL", raising=False)

    with caplog.at_level("WARNING"):
        assert _run(destinatario_notifiche(_Db())) is None

    assert any("Nessun destinatario" in r.message for r in caplog.records), (
        "Il silenzio era il difetto: se non parte, deve dirlo."
    )


def test_la_variabile_di_ambiente_salva_l_invio(monkeypatch):
    """La stessa `ADMIN_EMAIL` che HR usa gia': una convenzione sola."""
    monkeypatch.setenv("ADMIN_EMAIL", "titolare@example.it")

    assert _run(destinatario_notifiche(_Db())) == "titolare@example.it"


def test_con_la_variabile_non_si_avvisa_di_niente(monkeypatch, caplog):
    monkeypatch.setenv("ADMIN_EMAIL", "titolare@example.it")

    with caplog.at_level("WARNING"):
        _run(destinatario_notifiche(_Db()))

    assert not [r for r in caplog.records if "Nessun destinatario" in r.message]


# ── L'ordine delle fonti ──────────────────────────────────────────────────

def test_la_configurazione_batte_tutto(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "ambiente@example.it")
    db = _Db({"configurazioni": {"email_notifiche": "config@example.it"},
              "users": {"email": "admin@example.it"}})

    assert _run(destinatario_notifiche(db)) == "config@example.it"


def test_l_utente_admin_batte_l_ambiente(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "ambiente@example.it")
    db = _Db({"users": {"email": "admin@example.it"}})

    assert _run(destinatario_notifiche(db)) == "admin@example.it"


def test_il_campo_email_vale_come_alternativa_di_email_notifiche(monkeypatch):
    monkeypatch.delenv("ADMIN_EMAIL", raising=False)
    db = _Db({"configurazioni": {"email": "seconda@example.it"}})

    assert _run(destinatario_notifiche(db)) == "seconda@example.it"


# ── Le insidie dei valori vuoti ───────────────────────────────────────────

@pytest.mark.parametrize("valore", ["", "   ", None])
def test_un_campo_vuoto_non_e_un_destinatario(monkeypatch, valore):
    """Una stringa vuota passerebbe un `if doc.get(...)` scritto male e
    manderebbe l'email a nessuno, senza errori."""
    monkeypatch.setenv("ADMIN_EMAIL", "ambiente@example.it")
    db = _Db({"configurazioni": {"email_notifiche": valore}})

    assert _run(destinatario_notifiche(db)) == "ambiente@example.it"


def test_gli_spazi_intorno_all_indirizzo_si_tolgono(monkeypatch):
    monkeypatch.delenv("ADMIN_EMAIL", raising=False)
    db = _Db({"users": {"email": "  admin@example.it  "}})

    assert _run(destinatario_notifiche(db)) == "admin@example.it"


def test_una_fonte_illeggibile_non_ferma_le_altre(monkeypatch):
    monkeypatch.delenv("ADMIN_EMAIL", raising=False)
    db = _Db({"users": {"email": "admin@example.it"}}, esplode=("configurazioni",))

    assert _run(destinatario_notifiche(db)) == "admin@example.it"
