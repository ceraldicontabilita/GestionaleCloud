"""Dopo ogni operazione il runtime non tiene in memoria il lotto di lavoro.

``_documents`` e' il buffer della singola operazione: tenuto dopo, ogni
collezione conservava per sempre il suo ultimo lotto, spesso con il payload
(XML delle fatture, PDF in base64), e il processo cresceva fino all'OOM a
2 GB su Render. Resta solo la cache leggera.
"""
import asyncio

import pytest

from app.services import memoria_processo
from tests.runtime.test_supabase_runtime_database import FailingWriteSupabase
from tests.runtime.test_supabase_runtime_cache import CachingFakeSupabase, _run


def _fake():
    return CachingFakeSupabase({
        "invoices": [
            {"_id": f"f{i}", "id": f"f{i}", "status": "imported", "supplier_vat": "IT1",
             "xml_raw": "<xml>" + "x" * 1000 + "</xml>"}
            for i in range(20)
        ],
        "fornitori": [{"_id": "s1", "partita_iva": "IT1", "nome": "Fornitore"}],
    })


def test_scrittura_con_filtro_non_lascia_il_payload_in_memoria():
    runtime = _fake()

    async def scenario():
        await runtime["invoices"].update_many({"status": "imported"}, {"$set": {"letta": True}})
        return await runtime["invoices"].find_one({"id": "f3"}, {"_id": 0, "letta": 1})

    assert _run(scenario()) == {"letta": True}
    assert runtime["invoices"]._documents == []


def test_lettura_completa_e_distinct_non_lasciano_il_buffer():
    runtime = _fake()

    async def scenario():
        completi = await runtime["invoices"].find({"status": "imported"}).to_list(None)
        stati = await runtime["invoices"].distinct("status")
        return completi, stati

    completi, stati = _run(scenario())
    assert len(completi) == 20 and all(d.get("xml_raw") for d in completi)
    assert stati == ["imported"]
    assert runtime["invoices"]._documents == []


def test_aggregate_con_lookup_unisce_e_poi_rilascia():
    runtime = _fake()

    async def scenario():
        return await runtime["invoices"].aggregate([
            {"$match": {"id": "f1"}},
            {"$lookup": {"from": "fornitori", "localField": "supplier_vat",
                         "foreignField": "partita_iva", "as": "fornitore"}},
        ]).to_list(None)

    righe = _run(scenario())
    assert [f["nome"] for f in righe[0]["fornitore"]] == ["Fornitore"]
    assert runtime["invoices"]._documents == [] and runtime["fornitori"]._documents == []


def test_scrittura_rifiutata_non_lascia_il_buffer():
    runtime = FailingWriteSupabase({"alerts": [{"_id": "a1", "stato": "aperto"}]})

    async def scenario():
        await runtime.hydrate()
        with pytest.raises(RuntimeError, match="rifiutata"):
            await runtime["alerts"].update_one({"_id": "a1"}, {"$set": {"stato": "risolto"}})
        return await runtime["alerts"].find_one({"_id": "a1"})

    assert asyncio.run(scenario())["stato"] == "aperto"
    assert runtime["alerts"]._documents == []


def test_il_giro_della_memoria_misura_e_restituisce():
    esito = memoria_processo.restituisci()
    assert set(esito) == {"rss_prima_mb", "rss_dopo_mb", "oggetti_raccolti", "restituita"}
    assert isinstance(esito["oggetti_raccolti"], int)
    # Su Linux il valore c'e'; altrove la funzione non fa niente ma non si rompe.
    assert memoria_processo.limita_arene() in (True, False)


def test_avvio_e_arresto_del_giro():
    async def scenario():
        memoria_processo.avvia()
        compito = memoria_processo._stato["compito"]
        memoria_processo.arresta()
        await asyncio.sleep(0)
        return compito

    compito = asyncio.run(scenario())
    assert compito is not None and compito.cancelled()
    assert memoria_processo._stato["compito"] is None
