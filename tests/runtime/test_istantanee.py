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


def test_la_copia_si_svuota_prima_che_parta_la_risposta_della_scrittura():
    """Il client rilegge appena riceve la risposta: la copia deve gia' essere via."""
    _pulisci()
    chiamate = []

    @istantanea(ttl=600)
    async def riepilogo():
        chiamate.append(1)
        return {"n": len(chiamate)}

    async def app_finta(scope, receive, send):
        await send({"type": "http.response.start", "status": 200})
        await send({"type": "http.response.body", "body": b"{}"})

    letti_alla_partenza = []

    async def invia(messaggio):
        if messaggio["type"] == "http.response.start":
            letti_alla_partenza.append((await riepilogo())["n"])

    async def scenario():
        await riepilogo()
        await performance.IstantaneeMiddleware(app_finta)({"type": "http", "method": "POST"}, None, invia)

    _run(scenario())
    assert letti_alla_partenza == [2]


def test_un_ricalcolo_partito_prima_della_scrittura_non_rimette_il_dato_vecchio():
    _pulisci()
    stato = {"valore": 3}

    @istantanea(ttl=600)
    async def riepilogo():
        letto = stato["valore"]
        await asyncio.sleep(0.05)
        return {"n": letto}

    async def scenario():
        vecchio = asyncio.create_task(riepilogo())
        await asyncio.sleep(0.01)
        stato["valore"] = 5
        await performance.svuota_istantanee()
        dopo = await riepilogo()
        await vecchio
        ancora = await riepilogo()
        return dopo, ancora

    dopo, ancora = _run(scenario())
    assert dopo["n"] == 5
    assert ancora["n"] == 5


def test_il_server_di_collaudo_ha_le_stesse_istantanee_della_produzione():
    """27/09/2026: senza il middleware il collaudo E2E leggeva i conteggi di
    prima delle scritture e aspettava un numero vecchio (5 invece di 3)."""
    from pathlib import Path

    radice = Path(__file__).resolve().parents[2]
    for sorgente in ("app/main.py", "scripts/e2e_distruttivo_server.py"):
        assert "app.add_middleware(IstantaneeMiddleware)" in (radice / sorgente).read_text(encoding="utf-8"), sorgente


# --- Copia salvata (01/10/2026): sopravvive al riavvio, una scrittura la invalida -----------

class _StatoFinto:
    """Il minimo di ``sistema_stato``: find_one e update_one per chiave."""

    def __init__(self):
        self.documenti = {}

    async def find_one(self, filtro, _proiezione=None):
        return self.documenti.get(filtro["chiave"])

    async def update_one(self, filtro, aggiornamento, upsert=False):
        self.documenti[filtro["chiave"]] = dict(aggiornamento["$set"])


def _con_stato(monkeypatch):
    stato = _StatoFinto()
    monkeypatch.setattr(performance, "_archivio_stato", lambda: stato)
    monkeypatch.setattr(performance, "_svuotate_at_iso", "")
    return stato


def test_dopo_un_riavvio_si_serve_la_copia_salvata_e_si_ricalcola(monkeypatch):
    stato = _con_stato(monkeypatch)
    _pulisci()
    valori = iter([{"n": 1}, {"n": 2}])

    @istantanea(ttl=60, persistente=True)
    async def riepilogo_persistente(anno: int):
        await asyncio.sleep(0.01)
        return next(valori)

    async def scenario():
        prima = await riepilogo_persistente(anno=2026)
        await asyncio.sleep(0.05)
        assert len(stato.documenti) == 1
        await performance.cache.clear_all()  # il riavvio: la memoria e' vuota
        dopo_riavvio = await riepilogo_persistente(anno=2026)
        await asyncio.sleep(0.05)
        rinfrescata = await riepilogo_persistente(anno=2026)
        return prima, dopo_riavvio, rinfrescata

    prima, dopo, rinfrescata = _run(scenario())
    assert prima["n"] == 1 and prima["istantanea"]["in_aggiornamento"] is False
    # Subito la copia di prima, dichiarata «in aggiornamento» e venuta dalla copia salvata...
    assert dopo["n"] == 1
    assert dopo["istantanea"]["in_aggiornamento"] is True
    assert dopo["istantanea"]["da_copia_salvata"] is True
    # ...e il ricalcolo in sottofondo la sostituisce.
    assert rinfrescata["n"] == 2


def test_una_scrittura_invalida_la_copia_salvata(monkeypatch):
    stato = _con_stato(monkeypatch)
    _pulisci()
    valori = iter([{"n": 1}, {"n": 2}])

    @istantanea(ttl=60, persistente=True)
    async def riepilogo_invalidato(anno: int):
        return next(valori)

    async def scenario():
        await riepilogo_invalidato(anno=2026)
        await asyncio.sleep(0.05)
        await asyncio.sleep(0.01)
        await performance.svuota_istantanee()  # l'utente salva qualcosa
        return await riepilogo_invalidato(anno=2026)

    dopo_scrittura = _run(scenario())
    # Niente copia di prima della scrittura: si ricalcola e si aspetta il dato vero.
    assert dopo_scrittura["n"] == 2
    assert "da_copia_salvata" not in dopo_scrittura["istantanea"]
    assert stato is not None


def test_senza_persistente_non_si_salva_niente(monkeypatch):
    stato = _con_stato(monkeypatch)
    _pulisci()

    @istantanea(ttl=60)
    async def riepilogo_solo_memoria():
        return {"n": 1}

    async def scenario():
        await riepilogo_solo_memoria()
        await asyncio.sleep(0.05)

    _run(scenario())
    assert stato.documenti == {}
