"""17/09/2026: all'avvio il catalogo Supabase (gc_collection_catalog) veniva
ritentato solo 3 volte con pause di 0,5 s e 1 s. Con il database sotto carico
per qualche decina di secondi (statement timeout) il processo usciva con
"Catalogo Supabase non disponibile": il deploy Render falliva e l'istanza
precedente, riavviata, cadeva nello stesso errore → produzione giu' per
minuti (osservato 00:18-00:21 UTC). L'avvio ora insiste per circa un minuto
e mezzo; la regola "mai un archivio parziale" resta: se il catalogo non
arriva, l'avvio si interrompe comunque.
"""
import asyncio

import pytest

from app.services import supabase_runtime_database as srd


def _database():
    return srd.SupabaseRuntimeDatabase("test", {
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_test",
        "SUPABASE_RUNTIME_SECRET": "runtime-secret-test",
    })


def _timeout():
    return srd.SupabaseRPCError(
        "gc_collection_catalog", 500, "57014",
        "canceling statement due to statement timeout",
    )


def test_il_catalogo_sopravvive_a_una_raffica_di_statement_timeout(monkeypatch):
    database = _database()
    chiamate = []
    attese = []

    async def rpc(function_name, payload):
        chiamate.append(function_name)
        if len(chiamate) <= 6:  # con 3 tentativi soltanto sarebbe gia' morto
            raise _timeout()
        return [{"collection": "fatture", "row_count": 3}]

    async def sleep(delay):
        attese.append(delay)

    monkeypatch.setattr(database, "_rpc", rpc)
    monkeypatch.setattr(srd.asyncio, "sleep", sleep)

    manifest = asyncio.run(database._manifest())

    assert manifest == [{"collection": "fatture", "row_count": 3}]
    assert chiamate == ["gc_collection_catalog"] * 7
    # backoff esponenziale con tetto: nessuna pausa oltre il massimo
    assert attese == [0.5, 1.0, 2.0, 4.0, 8.0, 8.0]
    assert max(attese) == srd._MANIFEST_DELAY_MAX_SECONDS


def test_l_avvio_aspetta_almeno_un_minuto_prima_di_arrendersi():
    # Somma delle pause fra i tentativi (senza contare la durata dei timeout
    # stessi): deve coprire la finestra di carico osservata in produzione.
    pause = [min(0.5 * (2 ** i), srd._MANIFEST_DELAY_MAX_SECONDS)
             for i in range(srd._MANIFEST_RETRIES - 1)]
    assert sum(pause) >= 60


def test_senza_catalogo_l_avvio_si_interrompe_ancora(monkeypatch):
    database = _database()

    async def rpc(function_name, payload):
        raise _timeout()

    async def sleep(delay):
        return None

    monkeypatch.setattr(database, "_rpc", rpc)
    monkeypatch.setattr(srd.asyncio, "sleep", sleep)

    with pytest.raises(RuntimeError, match="Catalogo Supabase non disponibile"):
        asyncio.run(database._manifest())


def test_un_errore_non_transitorio_non_viene_ritentato(monkeypatch):
    database = _database()
    chiamate = []

    async def rpc(function_name, payload):
        chiamate.append(function_name)
        raise srd.SupabaseRPCError("gc_collection_catalog", 401, "42501", "permission denied")

    monkeypatch.setattr(database, "_rpc", rpc)

    with pytest.raises(srd.SupabaseRPCError):
        asyncio.run(database._manifest())
    assert chiamate == ["gc_collection_catalog"]
