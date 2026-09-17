"""17/09/2026: cache incrementale del runtime Supabase.

Richiesta del titolare: "il sito deve lasciare i dati scritti, non
ricaricarli ogni volta da Supabase". Qui si prova che, dopo la prima lettura,
una collezione non viene piu' scaricata finche' la sua firma remota non
cambia; che una modifica remota arriva con un delta (solo i documenti
aggiornati); che il payload documentale (XML/PDF) viene scaricato per id
soltanto quando la lettura lo richiede; che le scritture del processo
aggiornano la cache; che senza le RPC nuove si torna alla lettura completa.
"""
import asyncio

from app.services import supabase_runtime_database as srd
from tests.test_supabase_runtime_database import FakeRestSupabase, proietta_come_supabase


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class CachingFakeSupabase(FakeRestSupabase):
    """Fake con updated_at per documento e le due RPC della cache."""

    def __init__(self, remote=None):
        super().__init__(remote)
        self.clock = 0
        self.updated = {
            collection: {doc_id: self._tick() for doc_id in documents}
            for collection, documents in self.remote.items()
        }
        self.calls = []
        self.versions_disponibili = True

    def _tick(self):
        self.clock += 1
        return f"2026-09-17T00:00:{self.clock:02d}+00:00"

    def touch(self, collection, document):
        """Modifica remota fatta da un altro processo."""
        self.remote.setdefault(collection, {})[str(document["_id"])] = dict(document)
        self.updated.setdefault(collection, {})[str(document["_id"])] = self._tick()

    def remove(self, collection, doc_id):
        self.remote.get(collection, {}).pop(doc_id, None)
        self.updated.get(collection, {}).pop(doc_id, None)

    async def _rpc(self, function_name, payload):
        self.calls.append(function_name)
        if function_name == "gc_collection_versions":
            if not self.versions_disponibili:
                raise srd.SupabaseRPCError(function_name, 404, "PGRST202", "assente")
            return [
                {"collection": collection, "row_count": len(documents),
                 "max_updated_at": max(self.updated.get(collection, {}).values(), default=None)}
                for collection, documents in sorted(self.remote.items()) if documents
            ]
        if function_name == "gc_fetch_collection_since":
            since = payload["p_since"]
            rows = [
                (self.updated[payload["p_collection"]][doc_id], doc_id, item)
                for doc_id, item in self.remote.get(payload["p_collection"], {}).items()
                if since is None or self.updated[payload["p_collection"]][doc_id] > since
            ]
            rows.sort()
            page = [
                proietta_come_supabase(item, payload["p_exclude_fields"], self.marcatore_payload)
                for _, _, item in rows
            ]
            start = payload["p_offset"]
            return page[start:start + payload["p_limit"]]
        result = await super()._rpc(function_name, payload)
        if function_name == "gc_upsert_documents":
            for document in payload["p_documents"]:
                self.updated.setdefault(payload["p_collection"], {})[str(document["_id"])] = self._tick()
        if function_name == "gc_delete_documents":
            for doc_id in payload["p_ids"]:
                self.updated.get(payload["p_collection"], {}).pop(str(doc_id), None)
        return result

    def letture_complete(self):
        return [c for c in self.calls if c in {
            "gc_fetch_collection", "gc_fetch_collection_projected",
            "gc_fetch_collection_after", "gc_fetch_collection_after_projected",
        }]


def _fake():
    return CachingFakeSupabase({
        "alerts": [
            {"_id": "a1", "tipo": "scadenza", "stato": "aperto"},
            {"_id": "a2", "tipo": "scadenza", "stato": "chiuso"},
        ],
        "invoices": [
            {"_id": "f1", "id": "f1", "status": "imported", "total_amount": 10.0,
             "xml_raw": "<xml>1</xml>"},
            {"_id": "f2", "id": "f2", "status": "archived", "total_amount": 20.0,
             "xml_raw": "<xml>2</xml>"},
        ],
    })


def test_seconda_lettura_non_scarica_la_collezione():
    runtime = _fake()

    async def scenario():
        prima = await runtime["alerts"].find({"stato": "aperto"}).to_list(None)
        seconda = await runtime["alerts"].find({}).to_list(None)
        conteggio = await runtime["alerts"].count_documents({"tipo": "scadenza"})
        uno = await runtime["alerts"].find_one({"stato": "chiuso"})
        return prima, seconda, conteggio, uno

    prima, seconda, conteggio, uno = _run(scenario())
    assert [d["_id"] for d in prima] == ["a1"] and len(seconda) == 2
    assert conteggio == 2 and uno["_id"] == "a2"
    # una sola lettura completa (la prima); poi solo la firma, una volta
    assert runtime.letture_complete() == ["gc_fetch_collection"]
    assert runtime.calls.count("gc_collection_versions") == 1


def test_modifica_remota_arriva_con_un_delta(monkeypatch):
    monkeypatch.setattr(srd, "_CACHE_VERSIONS_TTL_SECONDS", 0.0)
    runtime = _fake()

    async def scenario():
        await runtime["alerts"].find({}).to_list(None)
        runtime.touch("alerts", {"_id": "a1", "tipo": "scadenza", "stato": "chiuso"})
        runtime.touch("alerts", {"_id": "a3", "tipo": "nuovo", "stato": "aperto"})
        runtime.calls.clear()
        dopo = await runtime["alerts"].find({}).to_list(None)
        return {d["_id"]: d for d in dopo}

    dopo = _run(scenario())
    assert dopo["a1"]["stato"] == "chiuso" and dopo["a3"]["tipo"] == "nuovo" and len(dopo) == 3
    assert runtime.calls == ["gc_collection_versions", "gc_fetch_collection_since"]


def test_cancellazione_remota_forza_la_rilettura_completa(monkeypatch):
    monkeypatch.setattr(srd, "_CACHE_VERSIONS_TTL_SECONDS", 0.0)
    runtime = _fake()

    async def scenario():
        await runtime["alerts"].find({}).to_list(None)
        runtime.remove("alerts", "a2")
        runtime.touch("alerts", {"_id": "a1", "tipo": "scadenza", "stato": "aperto"})
        runtime.calls.clear()
        return await runtime["alerts"].find({}).to_list(None)

    dopo = _run(scenario())
    assert [d["_id"] for d in dopo] == ["a1"]
    assert "gc_fetch_collection" in runtime.calls


def test_payload_scaricato_per_id_solo_quando_serve():
    runtime = _fake()

    async def scenario():
        leggera = await runtime["invoices"].find(
            {}, {"_id": 0, "xml_raw": 0, "fattura_allegata": 0,
                 "document_original_ref": 0, "foto": 0}).to_list(None)
        chiamate_leggera = list(runtime.calls)
        runtime.calls.clear()
        piena = await runtime["invoices"].find({"status": "imported"}).to_list(None)
        chiamate_piena = list(runtime.calls)
        runtime.calls.clear()
        conteggio = await runtime["invoices"].count_documents({"status": "archived"})
        chiamate_conteggio = list(runtime.calls)
        return leggera, chiamate_leggera, piena, chiamate_piena, conteggio, chiamate_conteggio

    leggera, c1, piena, c2, conteggio, c3 = _run(scenario())
    assert len(leggera) == 2 and all("xml_raw" not in d for d in leggera)
    # prima lettura: firma + lettura completa SENZA payload (proiezione remota)
    assert c1 == ["gc_collection_versions", "gc_fetch_collection_projected"]
    # lettura con payload: la cache sceglie f1, Supabase manda solo f1 per id
    assert [d["_id"] for d in piena] == ["f1"] and piena[0]["xml_raw"] == "<xml>1</xml>"
    assert c2 == ["gc_fetch_documents_exact"]
    # conteggio: tutto dalla cache
    assert conteggio == 1 and c3 == []


def test_scritture_del_processo_aggiornano_la_cache():
    runtime = _fake()

    async def scenario():
        await runtime["alerts"].find({}).to_list(None)
        await runtime["alerts"].insert_one({"_id": "a9", "tipo": "nuovo", "stato": "aperto"})
        await runtime["alerts"].update_one({"_id": "a1"}, {"$set": {"stato": "chiuso"}})
        await runtime["alerts"].delete_one({"_id": "a2"})
        await runtime["invoices"].find({}, {"_id": 0, "xml_raw": 0, "fattura_allegata": 0,
                                            "document_original_ref": 0, "foto": 0}).to_list(None)
        await runtime["invoices"].update_one({"id": "f1"}, {"$set": {"status": "pagata"}})
        runtime.calls.clear()
        alerts = await runtime["alerts"].find({}).to_list(None)
        fatture = await runtime["invoices"].find(
            {"status": "pagata"}, {"_id": 0, "xml_raw": 0, "fattura_allegata": 0,
                                   "document_original_ref": 0, "foto": 0}).to_list(None)
        return alerts, fatture

    alerts, fatture = _run(scenario())
    per_id = {d["_id"]: d for d in alerts}
    assert set(per_id) == {"a1", "a9"} and per_id["a1"]["stato"] == "chiuso"
    assert [d["id"] for d in fatture] == ["f1"] and "xml_raw" not in fatture[0]
    # nessuna lettura da Supabase: la cache era gia' allineata dalle scritture
    assert runtime.calls == []
    # e Supabase ha davvero la versione completa (payload incluso)
    assert runtime.remote["invoices"]["f1"]["xml_raw"] == "<xml>1</xml>"
    assert runtime.remote["invoices"]["f1"]["status"] == "pagata"


def test_senza_rpc_versioni_si_legge_come_prima():
    runtime = _fake()
    runtime.versions_disponibili = False

    async def scenario():
        prima = await runtime["alerts"].find({}).to_list(None)
        seconda = await runtime["alerts"].find({}).to_list(None)
        return prima, seconda

    prima, seconda = _run(scenario())
    assert len(prima) == 2 and len(seconda) == 2
    assert runtime.letture_complete() == ["gc_fetch_collection", "gc_fetch_collection"]
    assert runtime.calls.count("gc_collection_versions") == 1  # disattivata dopo il 404
    assert runtime._cache_enabled is False


def test_variabile_ambiente_spegne_la_cache(monkeypatch):
    monkeypatch.setenv(srd._CACHE_ENV_FLAG, "0")
    runtime = _fake()

    async def scenario():
        await runtime["alerts"].find({}).to_list(None)
        await runtime["alerts"].find({}).to_list(None)

    _run(scenario())
    assert runtime.letture_complete() == ["gc_fetch_collection", "gc_fetch_collection"]
    assert "gc_collection_versions" not in runtime.calls


def test_lettura_dalla_cache_non_aspetta_il_lock_operativo():
    """17/09/2026 sera: con il job di riconciliazione che teneva il lock della
    collezione, anche le liste servite dalla cache restavano bloccate per
    minuti. La lettura leggera passa da un lock proprio."""
    runtime = _fake()

    async def scenario():
        await runtime["alerts"].find({}).to_list(None)  # warm-up
        await runtime["alerts"]._remote_operation_lock.acquire()
        try:
            return await asyncio.wait_for(runtime["alerts"].find({"stato": "aperto"}).to_list(None), 1.0)
        finally:
            runtime["alerts"]._remote_operation_lock.release()

    rows = _run(scenario())
    assert [d["_id"] for d in rows] == ["a1"]


def test_lookup_puntuale_senza_payload_viene_dalla_cache():
    runtime = _fake()

    async def scenario():
        await runtime["alerts"].find({}).to_list(None)
        await runtime["invoices"].find({}, {"_id": 0, "xml_raw": 0, "fattura_allegata": 0,
                                            "document_original_ref": 0, "foto": 0}).to_list(None)
        runtime.calls.clear()
        uno = await runtime["alerts"].find_one({"_id": "a2"})
        leggera = await runtime["invoices"].find_one(
            {"id": "f2"}, {"_id": 0, "xml_raw": 0, "fattura_allegata": 0,
                           "document_original_ref": 0, "foto": 0})
        c_cache = list(runtime.calls)
        piena = await runtime["invoices"].find_one({"id": "f2"})
        c_piena = list(runtime.calls)
        await runtime["alerts"].update_one({"_id": "a2"}, {"$set": {"stato": "aperto"}})
        c_update = list(runtime.calls)
        return uno, leggera, c_cache, piena, c_piena, c_update

    uno, leggera, c_cache, piena, c_piena, c_update = _run(scenario())
    assert uno["_id"] == "a2" and leggera["id"] == "f2" and "xml_raw" not in leggera
    assert c_cache == []  # nessuna RPC: entrambi dalla cache
    assert piena["xml_raw"] == "<xml>2</xml>" and c_piena == ["gc_fetch_documents_exact"]
    # l'update su una collezione senza payload non rilegge il documento da Supabase
    assert c_update == ["gc_fetch_documents_exact", "gc_upsert_documents"]
    assert runtime.remote["alerts"]["a2"]["stato"] == "aperto"


def test_payload_per_id_a_lotti_ridotti_sui_timeout_mai_lettura_completa():
    """Sopra i 1.000 documenti con payload la cache sceglie gli id e Supabase
    li manda per id: un timeout restringe il lotto, non fa mai tornare alla
    lettura completa della collezione (che teneva il lock per decine di minuti)."""
    runtime = CachingFakeSupabase({
        "invoices": [
            {"_id": f"f{i}", "id": f"f{i}", "status": "imported", "xml_raw": f"<xml>{i}</xml>"}
            for i in range(1200)
        ],
    })
    lotti = []
    originale = runtime._rpc

    async def rpc(function_name, payload):
        if function_name == "gc_fetch_documents_exact":
            lotti.append(len(payload["p_values"]))
            if len(payload["p_values"]) > 100:
                raise srd.SupabaseRPCError(
                    function_name, 500, "57014", "canceling statement due to statement timeout")
        return await originale(function_name, payload)

    runtime._rpc = rpc

    async def scenario():
        await runtime["invoices"].find({}, {"_id": 0, "xml_raw": 0, "fattura_allegata": 0,
                                            "document_original_ref": 0, "foto": 0}).to_list(None)
        runtime.calls.clear()
        return await runtime["invoices"].find({"status": "imported"}).to_list(None)

    piene = _run(scenario())
    assert len(piene) == 1200 and all(d["xml_raw"] for d in piene)
    assert runtime.letture_complete() == []
    assert lotti[:4] == [500, 250, 125, 62]
    # dopo 8 lotti riusciti il lotto prova a raddoppiare (124, di nuovo in
    # timeout nel fake) e torna a 62: mai oltre, mai una lettura completa
    assert max(lotti[3:]) <= 124 and lotti.count(124) >= 1


def _inbox():
    return CachingFakeSupabase({
        "documents_inbox": [
            {"_id": "d1", "filename": "a.pdf", "pdf_data": "JVBERi0x"},
            {"_id": "d2", "filename": "b.pdf"},
            {"_id": "d3", "filename": "c.pdf", "pdf_data": None},
            {"_id": "d4", "filename": "d.pdf", "pdf_data": ""},
        ],
    })


_LEGGERA = {"_id": 0, "pdf_data": 0}


def test_filtri_di_presenza_del_payload_serviti_dalla_cache():
    """«Ha il PDF» / «senza PDF» si decidono dal marcatore di presenza:
    nessuna lettura completa con gli allegati, marcatore mai esposto."""
    runtime = _inbox()

    async def scenario():
        await runtime["documents_inbox"].find({}, _LEGGERA).to_list(None)
        runtime.calls.clear()
        con_pdf = await runtime["documents_inbox"].count_documents(
            {"pdf_data": {"$exists": True, "$nin": [None, ""]}})
        senza_chiave = await runtime["documents_inbox"].find(
            {"pdf_data": {"$exists": False}}, _LEGGERA).to_list(None)
        vuoti = await runtime["documents_inbox"].find(
            {"$or": [{"pdf_data": None}, {"pdf_data": ""}, {"pdf_data": {"$exists": False}}]},
            {"_id": 0, "filename": 1}).to_list(None)
        non_nulli = await runtime["documents_inbox"].find({"pdf_data": {"$ne": None}}, _LEGGERA).to_list(None)
        return con_pdf, senza_chiave, vuoti, non_nulli, list(runtime.calls)

    con_pdf, senza_chiave, vuoti, non_nulli, calls = _run(scenario())
    assert con_pdf == 1
    assert [d["filename"] for d in senza_chiave] == ["b.pdf"]
    assert sorted(d["filename"] for d in vuoti) == ["b.pdf", "c.pdf", "d.pdf"]
    assert sorted(d["filename"] for d in non_nulli) == ["a.pdf", "d.pdf"]
    assert calls == []
    for d in senza_chiave + vuoti + non_nulli:
        assert srd._PAYLOAD_STATO_KEY not in d and "pdf_data" not in d


def test_filtro_di_presenza_con_payload_scarica_solo_i_documenti_scelti():
    runtime = _inbox()

    async def scenario():
        await runtime["documents_inbox"].find({}, _LEGGERA).to_list(None)
        runtime.calls.clear()
        pieni = await runtime["documents_inbox"].find(
            {"pdf_data": {"$exists": True, "$nin": [None, ""]}}).to_list(None)
        return pieni, list(runtime.calls)

    pieni, calls = _run(scenario())
    assert [d["_id"] for d in pieni] == ["d1"] and pieni[0]["pdf_data"] == "JVBERi0x"
    # documents_inbox ha due collezioni fisiche: un lookup esatto per ciascuna
    assert set(calls) == {"gc_fetch_documents_exact"} and len(calls) == 2
    assert srd._PAYLOAD_STATO_KEY not in pieni[0]


def test_filtro_sul_contenuto_del_payload_non_usa_la_cache():
    runtime = _inbox()

    async def scenario():
        await runtime["documents_inbox"].find({}, _LEGGERA).to_list(None)
        runtime.calls.clear()
        trovati = await runtime["documents_inbox"].find(
            {"pdf_data": {"$regex": "^JVBER"}}, _LEGGERA).to_list(None)
        return trovati, list(runtime.calls)

    trovati, calls = _run(scenario())
    assert [d["filename"] for d in trovati] == ["a.pdf"]
    # lettura completa CON il payload citato dal filtro, anche se la proiezione lo esclude
    assert set(runtime.letture_complete()) == {"gc_fetch_collection_after"}


def test_senza_marcatore_dalle_rpc_si_torna_alla_lettura_completa():
    """RPC non ancora migrate: il marcatore manca, un filtro di presenza non
    puo' fidarsi della cache e rilegge con il payload (risultato esatto)."""
    runtime = _inbox()
    runtime.marcatore_payload = False

    async def scenario():
        await runtime["documents_inbox"].find({}, _LEGGERA).to_list(None)
        runtime.calls.clear()
        con_pdf = await runtime["documents_inbox"].count_documents(
            {"pdf_data": {"$exists": True, "$nin": [None, ""]}})
        return con_pdf, runtime.letture_complete()

    con_pdf, complete = _run(scenario())
    assert con_pdf == 1
    assert set(complete) == {"gc_fetch_collection_after"}


def test_scritture_locali_aggiornano_il_marcatore_di_presenza():
    runtime = _inbox()

    async def scenario():
        await runtime["documents_inbox"].find({}, _LEGGERA).to_list(None)
        await runtime["documents_inbox"].insert_one(
            {"_id": "d5", "filename": "e.pdf", "pdf_data": "JVBERi0y"})
        await runtime["documents_inbox"].update_one({"_id": "d1"}, {"$set": {"pdf_data": None}})
        runtime.calls.clear()
        con_pdf = await runtime["documents_inbox"].find(
            {"pdf_data": {"$exists": True, "$nin": [None, ""]}}, _LEGGERA).to_list(None)
        return con_pdf, [c for c in runtime.calls if c != "gc_collection_versions"]

    con_pdf, calls = _run(scenario())
    assert [d["filename"] for d in con_pdf] == ["e.pdf"]
    assert calls == []


def test_il_lotto_di_idratazione_viene_ricordato_fra_una_lettura_e_l_altra():
    runtime = CachingFakeSupabase({
        "invoices": [
            {"_id": f"f{i}", "id": f"f{i}", "status": "imported", "xml_raw": f"<xml>{i}</xml>"}
            for i in range(300)
        ],
    })
    lotti = []
    originale = runtime._rpc

    async def rpc(function_name, payload):
        if function_name == "gc_fetch_documents_exact":
            lotti.append(len(payload["p_values"]))
            if len(payload["p_values"]) > 100:
                raise srd.SupabaseRPCError(
                    function_name, 500, "57014", "canceling statement due to statement timeout")
        return await originale(function_name, payload)

    runtime._rpc = rpc

    async def scenario():
        await runtime["invoices"].find({}, {"_id": 0, "xml_raw": 0, "fattura_allegata": 0,
                                            "document_original_ref": 0, "foto": 0}).to_list(None)
        prima = await runtime["invoices"].find({"status": "imported"}).to_list(None)
        lotti_prima = list(lotti)
        lotti.clear()
        seconda = await runtime["invoices"].find({"status": "imported"}).to_list(None)
        return prima, lotti_prima, seconda, list(lotti)

    prima, lotti_prima, seconda, lotti_seconda = _run(scenario())
    assert len(prima) == 300 and len(seconda) == 300
    # il lotto si dimezza dalla misura di tabella (500), non dal lotto richiesto
    assert lotti_prima[:4] == [300, 250, 125, 62]
    # la seconda lettura parte dal lotto che funzionava, senza ripagare i timeout
    assert lotti_seconda[0] == 62 and max(lotti_seconda) <= 124


def test_find_senza_selettore_e_distinct_restano_in_cache():
    """selector=None (find(), distinct, aggregate) vale come {}: dalla cache."""
    runtime = _fake()

    async def scenario():
        await runtime["alerts"].find().to_list(None)
        runtime.calls.clear()
        tutti = await runtime["alerts"].find().to_list(None)
        tipi = await runtime["alerts"].distinct("tipo")
        return tutti, tipi, list(runtime.calls)

    tutti, tipi, calls = _run(scenario())
    assert len(tutti) == 2 and tipi == ["scadenza"]
    assert calls == []
