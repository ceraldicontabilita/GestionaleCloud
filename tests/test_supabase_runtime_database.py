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


def test_hydrate_carica_collezioni_e_documenti():
    runtime = FakeRestSupabase({
        "fatture": [{"_id": "f2", "numero": 2}, {"_id": "f1", "numero": 1}],
    })
    result = asyncio.run(runtime.hydrate())
    documents = asyncio.run(runtime["fatture"].find({}).to_list(None))

    assert result["righe"] == 2
    assert {item["_id"] for item in documents} == {"f1", "f2"}


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
