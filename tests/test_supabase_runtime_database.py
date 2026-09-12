"""Contratto del runtime documentale Supabase senza dipendenze di rete."""
import asyncio

from app.services.supabase_runtime_database import (
    SupabaseRuntimeDatabase,
    documents_digest,
)


class FakeRestSupabase(SupabaseRuntimeDatabase):
    def __init__(self, remote=None):
        super().__init__("test", {
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_test",
            "SUPABASE_RUNTIME_SECRET": "runtime-secret-test",
        })
        self.remote = {
            collection: {str(item["_id"]): dict(item) for item in documents}
            for collection, documents in (remote or {}).items()
        }

    async def _rpc(self, function_name, payload):
        if function_name == "gc_collection_manifest":
            return [
                {
                    "collection": collection,
                    "row_count": len(documents),
                    "digest_sha256": "non-usato-dal-client",
                }
                for collection, documents in sorted(self.remote.items())
                if documents
            ]
        if function_name == "gc_fetch_collection":
            documents = list(
                self.remote.get(payload["p_collection"], {}).values()
            )
            documents.sort(key=lambda item: str(item["_id"]))
            start = payload["p_offset"]
            return documents[start:start + payload["p_limit"]]
        if function_name == "gc_upsert_documents":
            target = self.remote.setdefault(payload["p_collection"], {})
            for document in payload["p_documents"]:
                target[str(document["_id"])] = dict(document)
            return len(payload["p_documents"])
        if function_name == "gc_delete_documents":
            target = self.remote.setdefault(payload["p_collection"], {})
            deleted = 0
            for item_id in payload["p_ids"]:
                deleted += int(target.pop(str(item_id), None) is not None)
            return deleted
        raise AssertionError(function_name)


class TimeoutRestSupabase(FakeRestSupabase):
    def __init__(self, remote=None):
        super().__init__(remote)
        self.manifest_attempts = 0
        self.fetch_limits = []

    async def _rpc(self, function_name, payload):
        if function_name == "gc_collection_manifest":
            self.manifest_attempts += 1
            if self.manifest_attempts < 3:
                raise RuntimeError("canceling statement due to statement timeout")
        if function_name == "gc_fetch_collection":
            self.fetch_limits.append(payload["p_limit"])
            if payload["p_limit"] > 250:
                raise RuntimeError("canceling statement due to statement timeout")
        return await super()._rpc(function_name, payload)


class ConcurrentAppendSupabase(FakeRestSupabase):
    async def _rpc(self, function_name, payload):
        result = await super()._rpc(function_name, payload)
        if function_name == "gc_collection_manifest":
            self.remote["alerts"]["nuovo"] = {"_id": "nuovo", "tipo": "concorrente"}
        return result


def test_hydrate_carica_collezioni_e_documenti():
    runtime = FakeRestSupabase({
        "fatture": [{"_id": "f2", "numero": 2}, {"_id": "f1", "numero": 1}],
    })
    result = asyncio.run(runtime.hydrate())
    documents = asyncio.run(runtime["fatture"].find({}).to_list(None))

    assert result["righe"] == 2
    assert {item["_id"] for item in documents} == {"f1", "f2"}


def test_hydrate_ritenta_manifest_e_riduce_il_lotto_sui_timeout(monkeypatch):
    async def no_sleep(_delay):
        return None

    monkeypatch.setattr("app.services.supabase_runtime_database.asyncio.sleep", no_sleep)
    remote = {"fatture": [{"_id": str(i), "numero": i} for i in range(600)]}
    runtime = TimeoutRestSupabase(remote)

    result = asyncio.run(runtime.hydrate())

    assert result["righe"] == 600
    assert runtime.manifest_attempts == 3
    assert runtime.fetch_limits[:3] == [1000, 500, 250]


def test_fetch_ritenta_timeout_transitorio_al_lotto_minimo(monkeypatch):
    attempts = 0
    delays = []

    async def fake_sleep(delay):
        delays.append(delay)

    async def transient_timeout(_function_name, payload):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RuntimeError("canceling statement due to statement timeout")
        return [{"_id": "f1"}]

    runtime = FakeRestSupabase()
    monkeypatch.setattr("app.services.supabase_runtime_database._PAGE_SIZE", 10)
    monkeypatch.setattr(runtime, "_rpc", transient_timeout)
    monkeypatch.setattr("app.services.supabase_runtime_database.asyncio.sleep", fake_sleep)

    documents = asyncio.run(runtime._fetch_collection_documents("fatture"))

    assert documents == [{"_id": "f1"}]
    assert attempts == 3
    assert delays == [0.5, 1.0]


def test_fetch_fallisce_dopo_retry_limitati_al_lotto_minimo(monkeypatch):
    attempts = 0

    async def no_sleep(_delay):
        return None

    async def always_timeout(_function_name, _payload):
        nonlocal attempts
        attempts += 1
        raise RuntimeError("canceling statement due to statement timeout")

    runtime = FakeRestSupabase()
    monkeypatch.setattr("app.services.supabase_runtime_database._PAGE_SIZE", 10)
    monkeypatch.setattr(runtime, "_rpc", always_timeout)
    monkeypatch.setattr("app.services.supabase_runtime_database.asyncio.sleep", no_sleep)

    try:
        asyncio.run(runtime._fetch_collection_documents("fatture"))
    except RuntimeError as exc:
        assert "statement timeout" in str(exc)
    else:
        raise AssertionError("Il timeout permanente deve interrompere l'hydration")

    assert attempts == 5


def test_manifest_limita_attesa_tra_retry(monkeypatch):
    delays = []

    async def fake_sleep(delay):
        delays.append(delay)

    class TwoTimeouts(FakeRestSupabase):
        def __init__(self):
            super().__init__({"fatture": [{"_id": "f1"}]})
            self.attempts = 0

        async def _rpc(self, function_name, payload):
            if function_name == "gc_collection_manifest":
                self.attempts += 1
                if self.attempts < 3:
                    raise RuntimeError("canceling statement due to statement timeout")
            return await super()._rpc(function_name, payload)

    monkeypatch.setattr("app.services.supabase_runtime_database.asyncio.sleep", fake_sleep)
    runtime = TwoTimeouts()
    asyncio.run(runtime.hydrate())

    assert runtime.attempts == 3
    assert delays == [0.5, 1.0]


def test_manifest_usa_catalogo_bootstrap_solo_dopo_tutti_i_timeout(monkeypatch):
    runtime = FakeRestSupabase()
    attempts = 0

    async def always_timeout(_function_name, _payload):
        nonlocal attempts
        attempts += 1
        raise RuntimeError("canceling statement due to statement timeout")

    async def no_sleep(_delay):
        return None

    monkeypatch.setattr(runtime, "_rpc", always_timeout)
    monkeypatch.setattr("app.services.supabase_runtime_database.asyncio.sleep", no_sleep)
    manifest = asyncio.run(runtime._manifest())

    assert attempts == 3
    assert len(manifest) >= 70
    assert all(row["row_count"] == 0 and row["bootstrap"] for row in manifest)
    assert {"documents_inbox", "invoices", "prima_nota_cassa"}.issubset(
        {row["collection"] for row in manifest}
    )


def test_hydrate_accetta_righe_aggiunte_dopo_il_manifest():
    runtime = ConcurrentAppendSupabase({"alerts": [{"_id": "iniziale"}]})

    result = asyncio.run(runtime.hydrate())

    assert result["righe"] == 2
    assert result["fogli"][0]["valide"] == 2


def test_fetch_deduplica_id_ripetuto_da_paginazione_concorrente(monkeypatch):
    runtime = FakeRestSupabase()
    pages = [
        [{"_id": "a"}, {"_id": "b"}],
        [{"_id": "b"}, {"_id": "c"}],
        [],
    ]

    async def fake_rpc(_function_name, _payload):
        return pages.pop(0)

    monkeypatch.setattr("app.services.supabase_runtime_database._PAGE_SIZE", 2)
    monkeypatch.setattr(runtime, "_rpc", fake_rpc)
    documents = asyncio.run(runtime._fetch_collection_documents("alerts", expected_count=3))

    assert [row["_id"] for row in documents] == ["a", "b", "c"]


def test_hydrate_registra_hydration_result_per_lhealth_check():
    # Prima dell'idratazione l'attributo deve essere un vero None su
    # istanza, non delegato a SheetDatabase.__getattr__ (che restituirebbe
    # una SheetTable e romperebbe /api/health con un AttributeError).
    runtime = FakeRestSupabase({
        "fatture": [{"_id": "f1", "numero": 1}],
    })
    assert runtime.hydration_result is None

    result = asyncio.run(runtime.hydrate())

    assert runtime.hydration_result == result
    assert runtime.hydration_result["fogli"] == [
        {"collezione": "fatture", "valide": 1, "numero_errori": 0},
    ]


def test_mutazioni_e_batch_vengono_persistiti():
    runtime = FakeRestSupabase()

    async def scenario():
        async with runtime.batch_writes():
            await runtime["fornitori"].insert_one({"_id": "a", "nome": "A"})
            await runtime["fornitori"].insert_one({"_id": "b", "nome": "B"})
            await runtime["fornitori"].update_one(
                {"_id": "a"}, {"$set": {"nome": "Aggiornato"}},
            )
        await runtime["fornitori"].delete_one({"_id": "b"})

    asyncio.run(scenario())

    assert runtime.remote["fornitori"] == {
        "a": {"_id": "a", "nome": "Aggiornato"},
    }


def test_mirror_elimina_obsoleti_e_verifica_impronta():
    runtime = FakeRestSupabase({
        "dipendenti": [
            {"_id": "vecchio", "nome": "Da eliminare"},
            {"_id": "v1", "nome": "Prima"},
        ],
    })
    source = [
        {"_id": "v1", "nome": "Vincenzo"},
        {"_id": "v2", "nome": "Valerio"},
    ]

    asyncio.run(runtime.mirror_collection("dipendenti", source))
    check = asyncio.run(runtime.verify_collection("dipendenti", source))

    assert set(runtime.remote["dipendenti"]) == {"v1", "v2"}
    assert check["coincide"] is True
    assert check["impronta_origine"] == documents_digest(source)
    assert check["impronta_destinazione"] == documents_digest(source)
