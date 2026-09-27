"""Istantanee: il riepilogo pesante si serve subito e si ricalcola in sottofondo.

26/09/2026: stato delle fonti, aggiornamento dati, conteggi dei provvisori,
grafici della Dashboard e IVA si ricalcolavano a ogni apertura (3-35 s).
"""
import asyncio

from app.middleware import performance
from app.middleware.performance import istantanea


def _run(coro):
    return asyncio.run(coro)


def _pulisci():
    _run(performance.cache.clear_all())


def test_la_seconda_richiesta_non_ricalcola_e_dice_quando_e_stata_calcolata():
    _pulisci()
    chiamate = []

    @istantanea(ttl=60)
    async def riepilogo(anno: int):
        chiamate.append(anno)
        return {"totale": 10}

    async def scenario():
        prima = await riepilogo(anno=2026)
        seconda = await riepilogo(anno=2026)
        altro_anno = await riepilogo(anno=2025)
        return prima, seconda, altro_anno

    prima, seconda, altro = _run(scenario())
    assert chiamate == [2026, 2025]
    assert prima["totale"] == seconda["totale"] == 10
    assert seconda["istantanea"]["calcolata_at"] == prima["istantanea"]["calcolata_at"]
    assert seconda["istantanea"]["in_aggiornamento"] is False


def test_scaduta_si_serve_subito_e_si_ricalcola_una_volta_sola():
    _pulisci()
    valori = iter([{"n": 1}, {"n": 2}, {"n": 3}])
    chiamate = []

    @istantanea(ttl=0, max_eta=600)
    async def riepilogo():
        chiamate.append(1)
        await asyncio.sleep(0.01)
        return next(valori)

    async def scenario():
        prima = await riepilogo()
        # Tre richieste insieme sulla copia scaduta: tutte subito, un ricalcolo.
        vecchie = await asyncio.gather(riepilogo(), riepilogo(), riepilogo())
        await asyncio.sleep(0.05)
        nuova = await riepilogo()
        return prima, vecchie, nuova

    prima, vecchie, nuova = _run(scenario())
    assert prima["n"] == 1
    assert [v["n"] for v in vecchie] == [1, 1, 1]
    assert all(v["istantanea"]["in_aggiornamento"] for v in vecchie)
    assert nuova["n"] == 2
    assert len(chiamate) == 3  # il primo calcolo, un ricalcolo per le tre, quello dell'ultima


def test_una_scrittura_riuscita_svuota_le_istantanee():
    _pulisci()
    chiamate = []

    @istantanea(ttl=600)
    async def riepilogo():
        chiamate.append(1)
        return {"n": len(chiamate)}

    async def app_finta(scope, receive, send):
        await send({"type": "http.response.start", "status": 200})

    middleware = performance.IstantaneeMiddleware(app_finta)

    async def invia(_):
        return None

    async def scenario():
        await riepilogo()
        await middleware({"type": "http", "method": "GET"}, None, invia)
        dopo_get = await riepilogo()
        await middleware({"type": "http", "method": "POST"}, None, invia)
        dopo_post = await riepilogo()
        return dopo_get, dopo_post

    dopo_get, dopo_post = _run(scenario())
    assert dopo_get["n"] == 1
    assert dopo_post["n"] == 2


def test_una_scrittura_rifiutata_non_svuota():
    _pulisci()
    chiamate = []

    @istantanea(ttl=600)
    async def riepilogo():
        chiamate.append(1)
        return {"n": len(chiamate)}

    async def app_rifiuta(scope, receive, send):
        await send({"type": "http.response.start", "status": 403})

    async def invia(_):
        return None

    async def scenario():
        await riepilogo()
        await performance.IstantaneeMiddleware(app_rifiuta)({"type": "http", "method": "POST"}, None, invia)
        return await riepilogo()

    assert _run(scenario())["n"] == 1


def test_rileggi_chiede_il_dato_fresco():
    _pulisci()
    chiamate = []

    @istantanea(ttl=600)
    async def riepilogo():
        chiamate.append(1)
        return {"n": len(chiamate)}

    async def app_finta(scope, receive, send):
        await send({"type": "http.response.start", "status": 200})

    async def invia(_):
        return None

    middleware = performance.IstantaneeMiddleware(app_finta)

    async def scenario():
        await riepilogo()
        await middleware({"type": "http", "method": "GET", "headers": [(b"x-rileggi", b"1")]}, None, invia)
        return await riepilogo()

    assert _run(scenario())["n"] == 2
