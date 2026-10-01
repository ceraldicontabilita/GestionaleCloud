"""`pdf_data` del verbale (AV3-09) e' payload: le liste non lo idratano mai,
si legge per id; «senza PDF» si decide dal marcatore, non dal contenuto."""
from app.document_repository import DOCUMENT_PAYLOAD_FIELDS, metadata_projection
from tests.runtime.test_supabase_runtime_cache import CachingFakeSupabase, _run


def _verbali():
    return CachingFakeSupabase({
        "verbali_noleggio": [
            {"_id": "v1", "id": "v1", "numero_verbale": "A1", "pdf_data": "JVBERi0x", "pdf_hash": "h1"},
            {"_id": "v2", "id": "v2", "numero_verbale": "A2"},
            {"_id": "v3", "id": "v3", "numero_verbale": "A3", "pdf_data": ""},
        ],
    })


def test_pdf_data_e_payload_della_collezione():
    assert "pdf_data" in DOCUMENT_PAYLOAD_FIELDS["verbali_noleggio"]
    assert metadata_projection("verbali_noleggio")["pdf_data"] == 0


def test_la_lista_dei_verbali_non_idrata_pdf_data():
    runtime = _verbali()

    async def scenario():
        lista = await runtime["verbali_noleggio"].find({}, metadata_projection("verbali_noleggio")).to_list(None)
        prima = list(runtime.calls)
        runtime.calls.clear()
        ancora = await runtime["verbali_noleggio"].find(
            {"numero_verbale": "A1"}, metadata_projection("verbali_noleggio")).to_list(None)
        return lista, prima, ancora, list(runtime.calls)

    lista, prima, ancora, dopo = _run(scenario())
    assert len(lista) == 3 and all("pdf_data" not in d for d in lista + ancora)
    assert "gc_fetch_documents_exact" not in prima + dopo
    assert [d["pdf_hash"] for d in ancora] == ["h1"]  # l'impronta resta nella versione leggera


def test_senza_pdf_si_decide_dal_marcatore_e_il_pdf_si_legge_per_id():
    runtime = _verbali()

    async def scenario():
        await runtime["verbali_noleggio"].find({}, metadata_projection("verbali_noleggio")).to_list(None)
        runtime.calls.clear()
        senza = await runtime["verbali_noleggio"].find(
            {"$or": [{"pdf_data": {"$exists": False}}, {"pdf_data": None}, {"pdf_data": ""}]},
            {"_id": 0, "numero_verbale": 1}).to_list(None)
        chiamate_filtro = list(runtime.calls)
        runtime.calls.clear()
        uno = await runtime["verbali_noleggio"].find_one({"id": "v1"})
        return senza, chiamate_filtro, uno, list(runtime.calls)

    senza, chiamate_filtro, uno, chiamate_id = _run(scenario())
    assert sorted(d["numero_verbale"] for d in senza) == ["A2", "A3"]
    assert chiamate_filtro == []
    assert uno["pdf_data"] == "JVBERi0x"
    assert chiamate_id == ["gc_fetch_documents_exact"]
