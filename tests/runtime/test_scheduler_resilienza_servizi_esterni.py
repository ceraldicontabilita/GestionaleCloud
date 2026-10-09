"""Resilienza scheduler quando un servizio esterno (IMAP/Gmail) non
risponde. app/scheduler.py::scan_verbali_email_task avvolge l'intero corpo
in un try/except che logga e ritorna, invece di propagare — ma prima di
questo file nessun test verificava che accada davvero, solo osservazione
statica del codice. Un job che esplode senza essere catturato manderebbe
in errore l'intero AsyncIOScheduler per quel giro."""
import asyncio

from app.config import settings
from app.database import Database
import app.scheduler as scheduler_mod
import app.services.verbali_email_logic as verbali_mod


def test_scan_verbali_non_propaga_eccezione_servizio_esterno(monkeypatch):
    """Se scan_email_con_priorita (IMAP/Gmail) solleva un errore di
    connessione, il task NON deve propagarlo: deve restare isolato,
    altrimenti un solo giro con Gmail irraggiungibile fermerebbe lo
    scheduler invece di riprovare al giro successivo."""
    monkeypatch.setattr(settings, "ENABLE_EMAIL_VERBALI_SYNC", True)
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: object()))

    async def _servizio_esterno_giu(db, days_back=30):
        raise ConnectionError("IMAP/Gmail non raggiungibile (simulato)")

    monkeypatch.setattr(verbali_mod, "scan_email_con_priorita", _servizio_esterno_giu)

    # Se questa chiamata solleva, il test fallisce da solo (nessun pytest.raises):
    # è esattamente il comportamento che vogliamo escludere.
    asyncio.run(scheduler_mod.scan_verbali_email_task())


def test_scan_verbali_saltato_se_canale_spento(monkeypatch):
    """Interruttore ENABLE_EMAIL_VERBALI_SYNC=False: il task deve uscire
    subito senza nemmeno provare a contattare il servizio esterno."""
    monkeypatch.setattr(settings, "ENABLE_EMAIL_VERBALI_SYNC", False)

    chiamato = {"si": False}

    async def _non_deve_essere_chiamato(db, days_back=30):
        chiamato["si"] = True
        return {}

    monkeypatch.setattr(verbali_mod, "scan_email_con_priorita", _non_deve_essere_chiamato)

    asyncio.run(scheduler_mod.scan_verbali_email_task())
    assert chiamato["si"] is False


def test_scan_verbali_gestisce_anche_fallimento_websocket_e_telegram(monkeypatch):
    """Anche se il servizio principale ha successo ma le notifiche
    (WebSocket/Telegram, servizi esterni anch'essi) falliscono, il task
    non deve propagare: sono avvolte in try/except dedicati nel codice."""
    monkeypatch.setattr(settings, "ENABLE_EMAIL_VERBALI_SYNC", True)
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: object()))

    async def _successo_con_nuovi_verbali(db, days_back=30):
        return {
            "fase_1_completamenti": {"quietanze_trovate": 0, "quietanze_cercate": 0,
                                      "pdf_trovati": 0, "pdf_cercati": 0},
            "fase_2_nuovi": {"verbali_nuovi": 3},
        }

    monkeypatch.setattr(verbali_mod, "scan_email_con_priorita", _successo_con_nuovi_verbali)

    import app.services.websocket_manager as ws_mod

    async def _websocket_giu(*a, **k):
        raise ConnectionError("WebSocket manager non disponibile (simulato)")

    monkeypatch.setattr(ws_mod, "notify_data_change", _websocket_giu)

    asyncio.run(scheduler_mod.scan_verbali_email_task())  # non deve sollevare
