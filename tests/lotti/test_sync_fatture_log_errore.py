"""Il giro fatture Gestionale→Lotti dice perche' fallisce, anche con un
errore dal messaggio vuoto e col registro su Supabase irraggiungibile."""
import asyncio
import logging

import httpx

from app.lotti.routers import scheduler


def test_errore_vuoto_ha_il_tipo_e_il_registro_giu_non_esplode(monkeypatch, caplog):
    import app.lotti.routers.gestionale_fatture as gf

    async def sync(**_k):
        raise httpx.ReadTimeout("")

    class Registro:
        async def insert_one(self, _doc):
            raise httpx.ReadTimeout("")

    class Db:
        scheduler_logs = Registro()

    monkeypatch.setattr(gf, "configurato", lambda: True)
    monkeypatch.setattr(gf, "esegui_sync_gestionale", sync)
    monkeypatch.setattr(scheduler, "db", Db())
    with caplog.at_level(logging.WARNING):
        asyncio.run(scheduler.job_sync_gestionale_fatture())
    assert "fallito: ReadTimeout" in caplog.text
    assert "registro gestionale-fatture non scritto: ReadTimeout" in caplog.text
