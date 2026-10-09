"""L'allarme «temperature non registrate oggi» (T1/T2) deve partire quando
il turno delle 07:00 ha aperto le caselle ma nessuno ha misurato: prima
bastava che la chiave esistesse e l'allarme non partiva mai (HAC-01)."""
import asyncio
from datetime import datetime, timezone

import pytest
from mongomock_motor import AsyncMongoMockClient


@pytest.fixture()
def sup(monkeypatch):
    import app.lotti.routers.supervisor_operativo as s
    db = AsyncMongoMockClient()["t"]
    monkeypatch.setattr(s, "db", db)
    ora = datetime(2026, 9, 25, 9, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(s, "_ora_locale", lambda: ora)
    return s, db


def _scheda(num, casella):
    return {"anno": 2026, "frigorifero_numero": num, "temperature": {"9": {"25": casella}}}


def test_caselle_aperte_e_vuote_fanno_partire_t1(sup):
    s, db = sup
    asyncio.run(db.temperature_positive.insert_many([
        _scheda(1, {"temp": None, "stato": "da_rilevare"}),
        _scheda(2, {"temp": 3.1, "firma_verificata": True}),
    ]))
    alerts = []
    asyncio.run(s.check_temperature_oggi(alerts))
    t1 = [a for a in alerts if a.get("id") == "T1" or "T1" in str(a)]
    assert t1 and "N° 1" in str(t1[0])


def test_misura_o_giro_firmato_spengono_t1(sup):
    s, db = sup
    asyncio.run(db.temperature_positive.insert_many([
        _scheda(1, {"temp": 3.0}),
        _scheda(2, {"temp": None, "stato": "conforme", "firma_verificata": True}),
    ]))
    asyncio.run(db.temperature_negative.insert_one(
        {"anno": 2026, "congelatore_numero": 1, "temperature": {"9": {"25": {"temp": -19}}}}))
    alerts = []
    asyncio.run(s.check_temperature_oggi(alerts))
    assert not alerts, alerts
