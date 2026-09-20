"""Regression contracts for boundaries where a convenience feature could forge evidence."""

import asyncio
from pathlib import Path

import pytest
from fastapi import HTTPException


def run(coro):
    return asyncio.run(coro)


def test_public_qr_config_redacts_wifi_password():
    source = (ROOT / "app/menu/routes/qrcode_routes.py").read_text(encoding="utf-8")
    assert 'wifi.pop("password", None)' in source
    assert "return _public_config(config)" in source


def test_wifi_qr_and_legacy_backup_download_require_admin_token():
    qr_source = (ROOT / "app/menu/routes/qrcode_routes.py").read_text(encoding="utf-8")
    backup_source = (ROOT / "app/menu/routes/backup_routes.py").read_text(encoding="utf-8")
    assert "async def generate_wifi_qr(_username: str = Depends(verify_token))" in qr_source
    assert "async def public_download_backup(filename: str, _username: str = Depends(verify_token))" in backup_source


def test_reseed_requires_admin_token():
    source = (ROOT / "app/menu/routes/seed_routes.py").read_text(encoding="utf-8")
    assert "async def seed_database(_username: str = Depends(verify_token))" in source


def test_no_wifi_password_is_hardcoded_in_source():
    source = (ROOT / "app/menu/routes/qrcode_routes.py").read_text(encoding="utf-8")
    assert "ceraldi2024" not in source
    assert "MENU_WIFI_PASSWORD" in source


def test_daily_haccp_reports_expected_readings_without_writing_them():
    from app.lotti.routers import haccp_auto

    result = run(haccp_auto.verifica_e_popola_oggi())

    assert result["ok"] is True
    assert result["generato"] is False
    assert result["elementi"] == []


def test_historical_haccp_population_is_disabled():
    """La rotta che riempiva lo storico temperature non esiste piu'."""
    from app.lotti.routers import haccp_auto

    assert not hasattr(haccp_auto, "popola_temperature_storiche")
    with pytest.raises(HTTPException) as exc:
        run(haccp_auto.popola_sanificazione_storica())
    assert exc.value.status_code == 410


def test_haccp_periodic_automation_never_creates_evidence():
    """Il modulo che fabbricava le registrazioni non esiste piu'.

    `automatismi_haccp` generava controlli dell'olio «entro le soglie»,
    temperature di cottura conformi e reclami a fornitori estratti a sorte.
    Era stato messo a tacere con tre `return 0`, e lo scheduler continuava a
    chiamarlo ogni 5 giorni per scrivere «creati: 0». Tre funzioni vuote, un
    job, un blocco di recupero all'avvio, un endpoint e una spia in
    diagnostica per un lavoro che non si doveva fare: cancellati.

    Questo test resta perche' la porta non si riapra dal nulla.
    """
    import importlib

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("app.lotti.routers.automatismi_haccp")

    scheduler = (ROOT / "app/lotti/routers/scheduler.py").read_text(encoding="utf-8")
    assert "automatismi_haccp" not in scheduler, (
        "Lo scheduler chiama ancora gli automatismi che fabbricavano il registro."
    )


@pytest.mark.parametrize("relative", [
    "app/lotti/routers/sanificazione.py",
    "app/lotti/routers/disinfestazione.py",
])
def test_missing_annual_service_sheets_remain_to_be_verified(relative):
    source = (ROOT / relative).read_text(encoding="utf-8")
    assert '"stato": "DA_VERIFICARE"' in source
ROOT = Path(__file__).resolve().parents[2]
