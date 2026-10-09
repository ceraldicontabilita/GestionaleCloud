import asyncio

from app.hr import main as hr_main


def test_avvio_collega_database_anche_senza_scheduler(monkeypatch):
    eventi = []

    async def connect():
        eventi.append("db")

    async def seed():
        eventi.append("seed")

    async def fix():
        eventi.append("fix")

    monkeypatch.setattr(hr_main.Database, "connect", connect)
    monkeypatch.setattr("app.hr.services.tfr_seed.seed_tfr_periodi", seed)
    monkeypatch.setattr("app.hr.services.startup_fixes.applica_fix_avvio", fix)

    asyncio.run(hr_main.avvio(avvia_scheduler=False))

    # Il ripristino conserva l'avvio privo di scritture dati implicite.
    # I mock rimangono installati per rilevare anche chiamate accidentali.
    assert eventi == ["db"]
