import asyncio

from app.services import drive_documenti_ingest
from app.services.drive_documenti_status_policy import aggregate_channel_status


def test_aggregate_ok_senza_errori():
    status, errors = aggregate_channel_status({
        "verbale": {"status": "ok"},
        "bonifico": {"status": "running"},
    })
    assert status == "ok"
    assert errors == []


def test_aggregate_degraded_con_errori_parziali():
    status, errors = aggregate_channel_status({
        "verbale": {"status": "ok"},
        "bonifico": {"status": "error"},
        "cartella_esattoriale": {"status": "error"},
    })
    assert status == "degraded"
    assert errors == ["bonifico", "cartella_esattoriale"]


def test_aggregate_error_se_falliscono_tutti_i_canali_eseguiti():
    status, errors = aggregate_channel_status({
        "bonifico": {"status": "error"},
        "cartella_esattoriale": {"status": "error"},
    })
    assert status == "error"
    assert errors == ["bonifico", "cartella_esattoriale"]


def test_sync_tutti_e_avvolto_dalla_policy():
    assert getattr(drive_documenti_ingest.sync_tutti, "_aggregate_status_policy", False)


def test_wrapper_corregge_status_esterno_senza_toccare_i_canali(monkeypatch):
    original = drive_documenti_ingest.sync_tutti.__wrapped__

    async def fake_original(_db):
        return {
            "status": "ok",
            "canali": {
                "bonifico": {"status": "error", "message": "no access"},
                "verbale": {"status": "ok"},
            },
        }

    from app.services import drive_documenti_status_policy as policy

    async def scenario():
        channels = (await fake_original(None))["canali"]
        status, errors = policy.aggregate_channel_status(channels)
        return status, errors

    status, errors = asyncio.run(scenario())
    assert status == "degraded"
    assert errors == ["bonifico"]
    assert original is not None
