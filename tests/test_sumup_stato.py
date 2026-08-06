"""Verifica configurazione SumUp: deve dire la verita' senza esporre la chiave."""
import asyncio

import httpx
import pytest

from app.routers import sumup


def _run(awaitable):
    return asyncio.run(awaitable)


class _Risposta:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class _Client:
    def __init__(self, risposta=None, errore=None):
        self._risposta = risposta
        self._errore = errore

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def get(self, url, headers=None):
        if self._errore:
            raise self._errore
        return self._risposta


def _configura(monkeypatch, chiave="sup_sk_abcd1234EFGH", merchant="MFNRDMC4"):
    monkeypatch.setattr(sumup.settings, "SUMUP_API_KEY", chiave, raising=False)
    monkeypatch.setattr(sumup.settings, "SUMUP_MERCHANT_CODE", merchant, raising=False)


def _risponde(monkeypatch, risposta=None, errore=None):
    monkeypatch.setattr(
        sumup.httpx, "AsyncClient",
        lambda *a, **k: _Client(risposta=risposta, errore=errore),
    )


def test_dice_chiaramente_se_la_chiave_manca(monkeypatch):
    _configura(monkeypatch, chiave="")
    stato = _run(sumup.stato_sumup(_admin={}))
    assert stato["chiave_configurata"] is False
    assert stato["connessione_ok"] is False
    assert "SUMUP_API_KEY" in stato["messaggio"]


def test_segnala_il_merchant_code_mancante(monkeypatch):
    _configura(monkeypatch, merchant="")
    stato = _run(sumup.stato_sumup(_admin={}))
    assert stato["connessione_ok"] is False
    assert "SUMUP_MERCHANT_CODE" in stato["messaggio"]


def test_non_restituisce_mai_la_chiave_in_chiaro(monkeypatch):
    _configura(monkeypatch, chiave="sup_sk_segretissima_9999")
    _risponde(monkeypatch, _Risposta(200, {
        "merchant_profile": {"company_name": "ceraldi group srl",
                             "merchant_code": "MFNRDMC4"},
    }))
    stato = _run(sumup.stato_sumup(_admin={}))
    assert "sup_sk_segretissima_9999" not in str(stato)
    assert stato["chiave_visibile"] == "...9999"


def test_connessione_riuscita(monkeypatch):
    _configura(monkeypatch)
    _risponde(monkeypatch, _Risposta(200, {
        "merchant_profile": {"company_name": "ceraldi group srl",
                             "merchant_code": "MFNRDMC4"},
    }))
    stato = _run(sumup.stato_sumup(_admin={}))
    assert stato["connessione_ok"] is True
    assert stato["esercente"] == "ceraldi group srl"


def test_chiave_di_un_altro_esercente_non_e_valida(monkeypatch):
    """Chiave buona ma di un altro conto: leggeremmo transazioni sbagliate."""
    _configura(monkeypatch, merchant="MFNRDMC4")
    _risponde(monkeypatch, _Risposta(200, {
        "merchant_profile": {"company_name": "altra ditta",
                             "merchant_code": "XXXXXXX1"},
    }))
    stato = _run(sumup.stato_sumup(_admin={}))
    assert stato["connessione_ok"] is False
    assert "XXXXXXX1" in stato["messaggio"]


@pytest.mark.parametrize("codice", [401, 403])
def test_chiave_rifiutata_suggerisce_la_causa_probabile(monkeypatch, codice):
    _configura(monkeypatch)
    _risponde(monkeypatch, _Risposta(codice))
    stato = _run(sumup.stato_sumup(_admin={}))
    assert stato["connessione_ok"] is False
    assert "pubblica" in stato["messaggio"]


def test_sumup_irraggiungibile_non_fa_esplodere_la_pagina(monkeypatch):
    _configura(monkeypatch)
    _risponde(monkeypatch, errore=httpx.ConnectTimeout("timeout"))
    stato = _run(sumup.stato_sumup(_admin={}))
    assert stato["connessione_ok"] is False
    assert "non raggiungibile" in stato["messaggio"]


def test_lo_stato_richiede_privilegi_admin():
    """L'audit ha trovato endpoint di configurazione senza controllo ruolo.

    Qui la chiave API e' in gioco: la gate deve restare sul server, non solo
    nel menu del frontend.
    """
    import inspect

    from app.utils.dependencies import get_current_admin_user

    parametri = inspect.signature(sumup.stato_sumup).parameters.values()
    assert any(
        getattr(p.default, "dependency", None) is get_current_admin_user
        for p in parametri
    ), "stato_sumup deve restare admin-only"
