"""Contratto del runtime documentale Supabase senza dipendenze di rete."""
import asyncio
import pytest

from app.services.supabase_runtime_database import (
    SupabaseRPCError,
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
        if function_name == "gc_collection_catalog":
            return [
                {
                    "collection": collection,
                    "row_count": len(documents),
                    "digest_sha256": "non-usato-dal-client",
                }
                for collection, documents in sorted(self.remote.items())
                if documents
            ]
        if function_name in {
            "gc_fetch_collection",
            "gc_fetch_collection_after",
            "gc_fetch_collection_after_projected",
            "gc_fetch_collection_projected",
        }:
            documents = list(
                self.remote.get(payload["p_collection"], {}).values()
            )
            documents.sort(key=lambda item: str(item["_id"]))
            if function_name in {
                "gc_fetch_collection_after",
                "gc_fetch_collection_after_projected",
            }:
                documents = [
                    item for item in documents
                    if str(item["_id"]) > payload["p_after_id"]
                ]
            if function_name in {
                "gc_fetch_collection_after_projected",
                "gc_fetch_collection_projected",
            }:
                documents = [
                    {
                        key: value for key, value in item.items()
                        if key not in payload["p_exclude_fields"]
                    }
                    for item in documents
                ]
            start = payload.get("p_offset", 0)
            return documents[start:start + payload["p_limit"]]
        if function_name == "gc_fetch_documents_exact":
            field = payload["p_field"]
            values = set(payload["p_values"])
            documents = []
            for item in self.remote.get(payload["p_collection"], {}).values():
                candidate = item.get("_id") if field == "_id" else item.get(field)
                if str(candidate) not in values:
                    continue
                documents.append({
                    key: value for key, value in item.items()
                    if key not in payload["p_exclude_fields"]
                })
            return documents
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
        if function_name == "gc_align_processed_document_status":
            updated = 0
            for collection in ("documents_inbox__shard_001", "documents_inbox"):
                for document in self.remote.get(collection, {}).values():
                    processed = document.get("processed") is True
                    xml_processed = document.get("xml_processed") is True
                    if (processed or xml_processed) and document.get("status") in {
                        "nuovo", "da_processare", None,
                    }:
                        document["status"] = "processato"
                        updated += 1
            return updated
        raise AssertionError(function_name)


class TimeoutRestSupabase(FakeRestSupabase):
    def __init__(self, remote=None):
        super().__init__(remote)
        self.manifest_attempts = 0
        self.fetch_limits = []

    async def _rpc(self, function_name, payload):
        if function_name == "gc_collection_catalog":
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
        if function_name == "gc_collection_catalog":
            self.remote["alerts"]["nuovo"] = {"_id": "nuovo", "tipo": "concorrente"}
        return result


class FailingWriteSupabase(FakeRestSupabase):
    async def _rpc(self, function_name, payload):
        if function_name == "gc_upsert_documents" and payload["p_documents"]:
            raise RuntimeError("scrittura Supabase rifiutata")
        return await super()._rpc(function_name, payload)


@pytest.mark.parametrize("collection", ["documents_inbox", "documents_inbox__shard_001"])
@pytest.mark.parametrize("status,code,detail", [
    (500, "57014", "canceling statement due to statement timeout"),
    (502, "", "errore remoto"),
])
def test_keyset_ritenta_senza_passare_a_offset(monkeypatch, collection, status, code, detail):
    runtime = FakeRestSupabase()
    calls = []

    async def rpc(function, payload):
        calls.append((function, dict(payload)))
        if len(calls) == 1:
            return [{"_id": "a"}, {"_id": "b"}]
        if len(calls) == 2:
            raise SupabaseRPCError(function, status, code, detail)
        return [{"_id": "c"}]

    async def no_sleep(_delay):
        pass

    monkeypatch.setattr("app.services.supabase_runtime_database._PAGE_SIZE", 2)
    monkeypatch.setattr("app.services.supabase_runtime_database.asyncio.sleep", no_sleep)
    monkeypatch.setattr(runtime, "_rpc", rpc)
    rows = asyncio.run(runtime._fetch_collection_documents(collection))
    assert [row["_id"] for row in rows] == ["a", "b", "c"]
    assert all(call[0] == "gc_fetch_collection_after" for call in calls)
    assert [call[1]["p_after_id"] for call in calls] == ["", "b", "b"]


def test_keyset_fallback_solo_rpc_assente(monkeypatch):
    runtime = FakeRestSupabase()
    calls = []

    async def rpc(function, payload):
        calls.append(function)
        if function == "gc_fetch_collection_after":
            raise SupabaseRPCError(function, 404, "PGRST202", "function not found")
        assert payload["p_offset"] == 0
        return [{"_id": "a"}]

    monkeypatch.setattr(runtime, "_rpc", rpc)
    assert asyncio.run(runtime._fetch_collection_documents("documents_inbox")) == [{"_id": "a"}]
    assert calls == ["gc_fetch_collection_after", "gc_fetch_collection"]


def test_proiezione_esclusiva_viene_applicata_dentro_supabase(monkeypatch):
    runtime = FakeRestSupabase({
        "documents_inbox": [{"_id": "d1", "filename": "a.pdf", "pdf_data": "enorme"}],
    })
    calls = []
    original_rpc = runtime._rpc

    async def rpc(function, payload):
        calls.append((function, dict(payload)))
        return await original_rpc(function, payload)

    monkeypatch.setattr(runtime, "_rpc", rpc)
    rows = asyncio.run(
        runtime["documents_inbox"].find({}, {"pdf_data": 0}).to_list(None)
    )

    assert rows == [{"_id": "d1", "filename": "a.pdf"}]
    assert calls[0] == (
        "gc_fetch_collection_after_projected",
        {
            "p_collection": "documents_inbox__shard_001",
            "p_limit": 500,
            "p_after_id": "",
            "p_exclude_fields": ["pdf_data"],
        },
    )


def test_proiezione_esclusiva_offset_viene_applicata_dentro_supabase(monkeypatch):
    runtime = FakeRestSupabase({
        "invoices": [{"_id": "f1", "numero": "1", "xml_raw": "enorme"}],
    })
    calls = []
    original_rpc = runtime._rpc

    async def rpc(function, payload):
        calls.append((function, dict(payload)))
        return await original_rpc(function, payload)

    monkeypatch.setattr(runtime, "_rpc", rpc)
    rows = asyncio.run(runtime["invoices"].find({}, {"xml_raw": 0}).to_list(None))

    assert rows == [{"_id": "f1", "numero": "1"}]
    assert calls == [("gc_fetch_collection_projected", {
        "p_collection": "invoices",
        "p_limit": 500,
        "p_offset": 0,
        "p_exclude_fields": ["xml_raw"],
    })]


def test_count_non_scarica_il_payload_documentale(monkeypatch):
    runtime = FakeRestSupabase({
        "cedolini": [
            {"_id": "c1", "anno": 2026, "pdf_data": "enorme"},
            {"_id": "c2", "anno": 2025, "pdf_data": "altro"},
        ],
    })
    calls = []
    original_rpc = runtime._rpc

    async def rpc(function, payload):
        calls.append((function, dict(payload)))
        return await original_rpc(function, payload)

    monkeypatch.setattr(runtime, "_rpc", rpc)
    count = asyncio.run(runtime["cedolini"].count_documents({"anno": 2026}))

    assert count == 1
    assert calls[0][0] == "gc_fetch_collection_projected"
    assert calls[0][1]["p_exclude_fields"] == ["pdf_data"]


def test_count_con_filtro_sul_payload_conserva_il_campo(monkeypatch):
    runtime = FakeRestSupabase({
        "cedolini": [{"_id": "c1", "pdf_data": "presente"}],
    })
    calls = []
    original_rpc = runtime._rpc

    async def rpc(function, payload):
        calls.append((function, dict(payload)))
        return await original_rpc(function, payload)

    monkeypatch.setattr(runtime, "_rpc", rpc)
    count = asyncio.run(runtime["cedolini"].count_documents({
        "pdf_data": {"$exists": True},
    }))

    assert count == 1
    assert calls[0][0] == "gc_fetch_collection"


def test_aggregate_non_scarica_il_payload_documentale(monkeypatch):
    runtime = FakeRestSupabase({
        "bonifici_transfers": [
            {"_id": "b1", "importo": 10, "pdf_data": "enorme"},
            {"_id": "b2", "importo": 20, "pdf_data": "altro"},
        ],
    })
    calls = []
    original_rpc = runtime._rpc

    async def rpc(function, payload):
        calls.append((function, dict(payload)))
        return await original_rpc(function, payload)

    monkeypatch.setattr(runtime, "_rpc", rpc)
    rows = asyncio.run(runtime["bonifici_transfers"].aggregate([
        {"$group": {"_id": None, "totale": {"$sum": "$importo"}}},
    ]).to_list(1))

    assert rows[0]["totale"] == 30
    assert calls[0][0] == "gc_fetch_collection_projected"
    assert calls[0][1]["p_exclude_fields"] == ["pdf_data"]

def test_allineamento_status_usa_una_sola_rpc_senza_caricare_documenti(monkeypatch):
    runtime = FakeRestSupabase({
        "documents_inbox": [
            {"_id": "d1", "processed": True, "status": "nuovo", "pdf_data": "enorme"},
            {"_id": "d2", "processed": False, "status": "nuovo"},
        ],
    })
    calls = []
    original_rpc = runtime._rpc

    async def rpc(function, payload):
        calls.append(function)
        return await original_rpc(function, payload)

    monkeypatch.setattr(runtime, "_rpc", rpc)
    updated = asyncio.run(runtime.align_processed_document_status())

    assert updated == 1
    assert calls == ["gc_align_processed_document_status"]
    assert runtime.remote["documents_inbox"]["d1"]["status"] == "processato"


def test_find_one_per_id_usa_lookup_puntuale_e_non_scarica_la_collezione(monkeypatch):
    runtime = FakeRestSupabase({
        "invoices": [
            {"_id": "pk1", "id": "f1", "xml_raw": "grande"},
            {"_id": "pk2", "id": "f2", "xml_raw": "altro"},
        ],
    })
    calls = []
    original_rpc = runtime._rpc

    async def rpc(function, payload):
        calls.append((function, dict(payload)))
        return await original_rpc(function, payload)

    monkeypatch.setattr(runtime, "_rpc", rpc)
    found = asyncio.run(runtime["invoices"].find_one({"id": "f2"}))

    assert found["_id"] == "pk2"
    assert calls == [("gc_fetch_documents_exact", {
        "p_collection": "invoices",
        "p_field": "id",
        "p_values": ["f2"],
        "p_exclude_fields": [],
    })]


@pytest.mark.parametrize("field", ["sha256", "pdf_hash", "version_id"])
def test_hash_e_versione_usano_lookup_puntuale(monkeypatch, field):
    runtime = FakeRestSupabase({
        "documenti": [{"_id": "pk1", field: "exact-value", "company_id": "CERALDI"}],
    })
    calls = []
    original_rpc = runtime._rpc

    async def rpc(function, payload):
        calls.append((function, dict(payload)))
        return await original_rpc(function, payload)

    monkeypatch.setattr(runtime, "_rpc", rpc)
    found = asyncio.run(runtime["documenti"].find_one(
        {"company_id": "CERALDI", field: "exact-value"}
    ))

    assert found["_id"] == "pk1"
    assert calls == [("gc_fetch_documents_exact", {
        "p_collection": "documenti",
        "p_field": field,
        "p_values": ["exact-value"],
        "p_exclude_fields": [],
    })]


def test_insert_e_update_per_id_non_caricano_tutta_la_collezione(monkeypatch):
    runtime = FakeRestSupabase({
        "invoices": [{"_id": "pk1", "id": "f1", "totale": 10}],
    })
    calls = []
    original_rpc = runtime._rpc

    async def rpc(function, payload):
        calls.append(function)
        return await original_rpc(function, payload)

    monkeypatch.setattr(runtime, "_rpc", rpc)

    async def scenario():
        await runtime["invoices"].insert_one({"_id": "pk2", "id": "f2"})
        await runtime["invoices"].update_one(
            {"id": "f1"}, {"$set": {"totale": 20}},
        )

    asyncio.run(scenario())

    assert "gc_fetch_collection" not in calls
    assert "gc_fetch_collection_after" not in calls
    assert calls == [
        "gc_fetch_documents_exact", "gc_upsert_documents",
        "gc_fetch_documents_exact", "gc_upsert_documents",
    ]
    assert runtime.remote["invoices"]["pk1"]["totale"] == 20


@pytest.mark.parametrize("status,code", [(403, "42501"), (404, "42P01")])
def test_keyset_non_nasconde_errori_permessi_o_schema(monkeypatch, status, code):
    runtime = FakeRestSupabase()
    calls = []

    async def rpc(function, payload):
        calls.append(function)
        raise SupabaseRPCError(function, status, code, "errore remoto")

    monkeypatch.setattr(runtime, "_rpc", rpc)
    with pytest.raises(SupabaseRPCError):
        asyncio.run(runtime._fetch_collection_documents("documents_inbox"))
    assert calls == ["gc_fetch_collection_after"]


@pytest.mark.parametrize("page", [[{}], [{"_id": "a"}]])
def test_keyset_interrompe_cursore_mancante_o_ripetuto(monkeypatch, page):
    runtime = FakeRestSupabase()
    pages = [[{"_id": "a"}], page]

    async def rpc(_function, _payload):
        return pages.pop(0)

    monkeypatch.setattr("app.services.supabase_runtime_database._PAGE_SIZE", 1)
    monkeypatch.setattr(runtime, "_rpc", rpc)
    with pytest.raises(RuntimeError, match="Cursore keyset non avanzato"):
        asyncio.run(runtime._fetch_collection_documents("documents_inbox"))


def test_hydrate_carica_solo_catalogo_e_lettura_arriva_da_supabase():
    runtime = FakeRestSupabase({
        "fatture": [{"_id": "f2", "numero": 2}, {"_id": "f1", "numero": 1}],
    })
    result = asyncio.run(runtime.hydrate())
    assert runtime["fatture"]._documents == []
    documents = asyncio.run(runtime["fatture"].find({}).to_list(None))

    assert result["righe"] == 2
    assert {item["_id"] for item in documents} == {"f1", "f2"}


def test_hydrate_unisce_shard_fisico_nella_collezione_logica():
    runtime = FakeRestSupabase({
        "documents_inbox__shard_001": [
            {"_id": "storico", "stato": "elaborato"},
        ],
        "documents_inbox": [
            {"_id": "corrente", "stato": "da_elaborare"},
        ],
    })

    result = asyncio.run(runtime.hydrate())
    documents = asyncio.run(runtime["documents_inbox"].find({}).to_list(None))

    assert {item["_id"] for item in documents} == {"storico", "corrente"}
    assert "documents_inbox__shard_001" not in asyncio.run(
        runtime.list_collection_names()
    )
    assert result["righe"] == 2


def test_mutazione_documento_shard_resta_nello_shard_e_non_duplica():
    runtime = FakeRestSupabase({
        "documents_inbox__shard_001": [
            {"_id": "storico", "stato": "elaborato"},
        ],
        "documents_inbox": [
            {"_id": "corrente", "stato": "da_elaborare"},
        ],
    })

    async def scenario():
        await runtime.hydrate()
        await runtime["documents_inbox"].update_one(
            {"_id": "storico"}, {"$set": {"nota": "aggiornata"}},
        )
        await runtime["documents_inbox"].delete_one({"_id": "storico"})

    asyncio.run(scenario())

    assert "storico" not in runtime.remote["documents_inbox__shard_001"]
    assert "storico" not in runtime.remote["documents_inbox"]
    assert set(runtime.remote["documents_inbox"]) == {"corrente"}


def test_hydrate_ritenta_manifest_senza_scaricare_le_collezioni(monkeypatch):
    async def no_sleep(_delay):
        return None

    monkeypatch.setattr("app.services.supabase_runtime_database.asyncio.sleep", no_sleep)
    monkeypatch.setattr("app.services.supabase_runtime_database._PAGE_SIZE", 1000)
    remote = {"fatture": [{"_id": str(i), "numero": i} for i in range(600)]}
    runtime = TimeoutRestSupabase(remote)

    result = asyncio.run(runtime.hydrate())

    assert result["righe"] == 600
    assert runtime.manifest_attempts == 3
    assert runtime.fetch_limits == []


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


def test_fetch_ritenta_errore_http_520_transitorio(monkeypatch):
    attempts = 0

    async def no_sleep(_delay):
        return None

    async def transient_520(_function_name, _payload):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError(
                "Supabase RPC gc_fetch_collection fallita (HTTP 520): errore remoto"
            )
        return [{"_id": "f1"}]

    runtime = FakeRestSupabase()
    monkeypatch.setattr("app.services.supabase_runtime_database._PAGE_SIZE", 10)
    monkeypatch.setattr(runtime, "_rpc", transient_520)
    monkeypatch.setattr("app.services.supabase_runtime_database.asyncio.sleep", no_sleep)

    documents = asyncio.run(runtime._fetch_collection_documents("fatture"))

    assert documents == [{"_id": "f1"}]
    assert attempts == 2


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
            if function_name == "gc_collection_catalog":
                self.attempts += 1
                if self.attempts < 3:
                    raise RuntimeError("canceling statement due to statement timeout")
            return await super()._rpc(function_name, payload)

    monkeypatch.setattr("app.services.supabase_runtime_database.asyncio.sleep", fake_sleep)
    runtime = TwoTimeouts()
    asyncio.run(runtime.hydrate())

    assert runtime.attempts == 3
    assert delays == [0.5, 1.0]


def test_manifest_non_avvia_un_archivio_parziale_dopo_timeout(monkeypatch):
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
    with pytest.raises(RuntimeError, match="archivio parziale"):
        asyncio.run(runtime._manifest())

    assert attempts == 3


def test_catalogo_carica_archivi_contabili_e_collezioni_nuove():
    remote = {name: [{"_id": "origine", "source_id": "documento"}] for name in (
        "movimenti_contabili", "bank_payment_allocations", "riconciliazioni_match",
        "verbali_noleggio", "job_state", "nuova_collezione_non_predefinita",
    )}
    runtime = FakeRestSupabase(remote)
    result = asyncio.run(runtime.hydrate())
    assert result["righe"] == len(remote)
    assert set(asyncio.run(runtime.list_collection_names())) == set(remote)
    for name in remote:
        assert asyncio.run(runtime[name].find({}).to_list(None)) == remote[name]


def test_catalogo_fallback_dinamico_solo_rpc_assente(monkeypatch):
    runtime = FakeRestSupabase()
    calls = []

    async def rpc(function, payload):
        calls.append(function)
        if function == "gc_collection_catalog":
            raise SupabaseRPCError(function, 404, "PGRST202", "not found")
        return [{"collection": "movimenti_contabili", "row_count": 304}]

    monkeypatch.setattr(runtime, "_rpc", rpc)
    assert asyncio.run(runtime._manifest())[0]["row_count"] == 304
    assert calls == ["gc_collection_catalog", "gc_collection_manifest"]


@pytest.mark.parametrize("status,code", [(403, "42501"), (404, "42P01")])
def test_catalogo_non_nasconde_errori_permessi_o_schema(monkeypatch, status, code):
    runtime = FakeRestSupabase()
    calls = []

    async def rpc(function, payload):
        calls.append(function)
        raise SupabaseRPCError(function, status, code, "errore remoto")

    monkeypatch.setattr(runtime, "_rpc", rpc)
    with pytest.raises(SupabaseRPCError):
        asyncio.run(runtime._manifest())
    assert calls == ["gc_collection_catalog"]


def test_hydrate_accetta_righe_aggiunte_dopo_il_manifest():
    runtime = ConcurrentAppendSupabase({"alerts": [{"_id": "iniziale"}]})

    result = asyncio.run(runtime.hydrate())

    assert result["righe"] == 1
    assert result["fogli"][0]["valide"] == 1
    documents = asyncio.run(runtime["alerts"].find({}).to_list(None))
    assert {item["_id"] for item in documents} == {"iniziale", "nuovo"}


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


def test_letture_non_restano_ferme_allhydration():
    runtime = FakeRestSupabase({"fatture": [{"_id": "f1", "numero": 1}]})

    async def scenario():
        await runtime.hydrate()
        prima = await runtime["fatture"].find({}).to_list(None)
        runtime.remote["fatture"]["f2"] = {"_id": "f2", "numero": 2}
        dopo = await runtime["fatture"].find({}).to_list(None)
        return prima, dopo

    prima, dopo = asyncio.run(scenario())

    assert [item["_id"] for item in prima] == ["f1"]
    assert {item["_id"] for item in dopo} == {"f1", "f2"}


def test_scrittura_fallita_non_lascia_documento_fantasma():
    runtime = FailingWriteSupabase()

    async def scenario():
        with pytest.raises(RuntimeError, match="rifiutata"):
            await runtime["fatture"].insert_one({"_id": "ghost", "numero": 99})
        return await runtime["fatture"].find_one({"_id": "ghost"})

    assert asyncio.run(scenario()) is None
    assert runtime["fatture"]._documents == []


def test_health_probe_verifica_anche_rpc_di_scrittura_senza_creare_righe():
    runtime = FakeRestSupabase({"fatture": [{"_id": "f1"}]})

    result = asyncio.run(runtime.health_probe())

    assert result == {"collections": 1, "write_path": "verified"}
    assert runtime.remote["runtime_health"] == {}


def test_scheduler_lease_acquisisce_e_rilascia_con_owner_del_processo(monkeypatch):
    runtime = FakeRestSupabase()
    calls = []

    async def rpc(function_name, payload):
        calls.append((function_name, dict(payload)))
        return True

    monkeypatch.setattr(runtime, "_rpc", rpc)

    async def scenario():
        async with runtime.scheduler_lease("import-email", ttl_seconds=60) as acquired:
            assert acquired is True

    asyncio.run(scenario())

    assert [name for name, _ in calls] == [
        "gc_try_scheduler_lease",
        "gc_release_scheduler_lease",
    ]
    assert calls[0][1]["p_owner_id"] == calls[1][1]["p_owner_id"]


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
