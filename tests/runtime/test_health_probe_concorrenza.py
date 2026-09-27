"""Piu' controlli di salute in coda sulla stessa probe rispondono tutti.

Quando il server rallenta, Render accoda piu' ``/api/health``: aspettano la
stessa probe, il primo la raccoglie e la azzera, e il secondo leggeva None e
rispondeva 500, cioe' «server morto» proprio nel momento peggiore.
"""
import asyncio

from app.services.health_probe import VERIFICATA, ProbeUnica


def test_due_controlli_sulla_stessa_probe_non_danno_errore():
    probe = ProbeUnica("archivio")

    async def lenta():
        await asyncio.sleep(0.05)

    async def scenario():
        return await asyncio.gather(
            probe.esito(lenta, timeout=1.0),
            probe.esito(lenta, timeout=1.0),
            probe.esito(lenta, timeout=1.0),
        )

    esiti = asyncio.run(scenario())
    assert [e[0] for e in esiti] == [VERIFICATA] * 3
