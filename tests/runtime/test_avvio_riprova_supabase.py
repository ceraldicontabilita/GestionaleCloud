"""Un 522 passeggero di Supabase non deve bruciare un deploy.

Il 19/09/2026 tre deploy sono falliti — 17:52, 19:02, 19:16 — sempre cosi':

    ERROR app.database: Connessione al registro dati fallita:
    Supabase RPC gc_collection_catalog fallita (HTTP 522): errore remoto
    ERROR: Application startup failed. Exiting.

522 e' l'edge di Supabase che non raggiunge il database: passa da solo. Ma
`connect_db` non riprovava, quindi l'istanza nuova moriva, restava viva la
vecchia, e il codice gia' unito su `main` non arrivava in produzione.

Il confine che questi test difendono: si riprova su cio' che passa (rete,
5xx del gateway), si fallisce **subito** su cio' che non passa (credenziali
sbagliate, backend non supportato). Meglio un'istanza che non parte che una
che serve numeri senza archivio.
"""
import asyncio

import pytest

from app.database import ATTESE_RIPROVA, Database, _e_passeggero


def _run(coroutine):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coroutine)
    finally:
        loop.close()


class _Errore(RuntimeError):
    def __init__(self, status):
        self.status = status
        super().__init__(f"HTTP {status}")


class _Runtime:
    """Fallisce i primi `fallimenti` tentativi, poi riesce."""

    def __init__(self, fallimenti, errore=None):
        self.rimasti = fallimenti
        self.errore = errore or _Errore(522)
        self.tentativi = 0

    async def hydrate(self):
        self.tentativi += 1
        if self.rimasti > 0:
            self.rimasti -= 1
            raise self.errore


@pytest.fixture(autouse=True)
def _senza_attese(monkeypatch):
    """I test non devono dormire 31 secondi."""
    async def _subito(_):
        return None
    monkeypatch.setattr("app.database.asyncio.sleep", _subito)


# ── Cosa si riprova ───────────────────────────────────────────────────────

def test_un_522_isolato_non_ferma_l_avvio():
    """Il caso reale dei tre deploy persi."""
    runtime = _Runtime(fallimenti=1)

    _run(Database._idrata_con_riprove(runtime))

    assert runtime.tentativi == 2


@pytest.mark.parametrize("stato", [429, 500, 502, 503, 504, 520, 521, 522, 523, 524])
def test_gli_stati_del_gateway_si_riprovano(stato):
    runtime = _Runtime(fallimenti=1, errore=_Errore(stato))

    _run(Database._idrata_con_riprove(runtime))

    assert runtime.tentativi == 2


@pytest.mark.parametrize("errore", [asyncio.TimeoutError(), ConnectionError(), OSError()])
def test_anche_un_errore_di_rete_senza_stato_si_riprova(errore):
    runtime = _Runtime(fallimenti=1, errore=errore)

    _run(Database._idrata_con_riprove(runtime))

    assert runtime.tentativi == 2


def test_resiste_a_un_buco_lungo_ma_non_infinito():
    runtime = _Runtime(fallimenti=len(ATTESE_RIPROVA))

    _run(Database._idrata_con_riprove(runtime))

    assert runtime.tentativi == len(ATTESE_RIPROVA) + 1


# ── Cosa NON si riprova: l'avvio deve fallire chiuso ──────────────────────

@pytest.mark.parametrize("stato", [401, 403, 404, 422])
def test_le_credenziali_sbagliate_falliscono_subito(stato):
    """Riprovare un 401 cinque volte ritarda soltanto la verita'."""
    runtime = _Runtime(fallimenti=99, errore=_Errore(stato))

    with pytest.raises(RuntimeError):
        _run(Database._idrata_con_riprove(runtime))

    assert runtime.tentativi == 1


def test_un_errore_senza_stato_e_non_di_rete_non_si_riprova():
    runtime = _Runtime(fallimenti=99, errore=ValueError("payload incomprensibile"))

    with pytest.raises(ValueError):
        _run(Database._idrata_con_riprove(runtime))

    assert runtime.tentativi == 1


def test_un_archivio_irraggiungibile_per_sempre_fa_fallire_l_avvio():
    """Meglio un'istanza che non parte che una che serve numeri senza dati."""
    runtime = _Runtime(fallimenti=99)

    with pytest.raises(RuntimeError):
        _run(Database._idrata_con_riprove(runtime))

    assert runtime.tentativi == len(ATTESE_RIPROVA) + 1


# ── Il giudizio sul singolo errore ────────────────────────────────────────

def test_il_522_e_passeggero_e_il_401_no():
    assert _e_passeggero(_Errore(522)) is True
    assert _e_passeggero(_Errore(401)) is False


def test_le_attese_crescono_e_restano_brevi():
    """Cinque tentativi in ~31s: passa un buco, non tiene in piedi un rotto."""
    assert list(ATTESE_RIPROVA) == sorted(ATTESE_RIPROVA)
    assert sum(ATTESE_RIPROVA) < 60
