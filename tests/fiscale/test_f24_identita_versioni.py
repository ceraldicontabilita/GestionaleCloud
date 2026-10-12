import asyncio
import copy
import pytest
from app.services.f24_canonico import chiave_f24, salva_f24
from app.services.f24_doppioni import identita_f24
from app.services.f24_versioni import sostituisci_versione
from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from tests.fiscale.test_f24_doppioni import _f24
from tests.runtime.test_supabase_runtime_database import FakeRestSupabase


def test_identita_non_dipende_da_pdf_e_distingue_ente_e_matricola():
    a = _f24("a", "prima.pdf", pdf_hash="a")
    b = _f24("b", "seconda.pdf", pdf_hash="b")
    assert chiave_f24(a) == chiave_f24(b)
    b["sezione_erario"][0]["codice_ente"] = "ALTRO"
    assert chiave_f24(a) != chiave_f24(b)
    a.pop("codice_fiscale")
    assert identita_f24(a) is None


def test_rate_diverse_non_vengono_accorpate():
    a = _f24('a', 'rata1.pdf')
    b = copy.deepcopy(a)
    a['sezione_erario'][0]['rateazione'] = '0102'
    b['sezione_erario'][0]['rateazione'] = '0202'
    assert chiave_f24(a) != chiave_f24(b)


def test_due_processi_importano_un_solo_obbligo_e_un_solo_evento(monkeypatch):
    events = []

    async def event(db, doc, **kw):
        events.append(doc["id"])

    monkeypatch.setattr(
        "app.services.f24_evento_acquisito.pubblica_f24_acquisito", event
    )

    async def scenario():
        shared = {}
        waiting = 0
        gate = asyncio.Event()

        class Process(FakeRestSupabase):
            async def _rpc(self, name, payload):
                nonlocal waiting
                if name == "gc_commit_documents":
                    waiting += 1
                    if waiting == 2:
                        gate.set()
                    await asyncio.wait_for(gate.wait(), 5)
                    change = payload["p_changes"][0]
                    key = change["after"].get("idempotency_key")
                    for existing in shared.get(change["collection"], {}).values():
                        if existing.get("idempotency_key") == key:
                            return {
                                "status": "duplicate",
                                "collection": change["collection"],
                                "rejected": [
                                    {
                                        "idempotency_key": key,
                                        "id_esistente": existing["id"],
                                        "documento_esistente": existing,
                                    }
                                ],
                            }
                return await super()._rpc(name, payload)

        a, b = Process(), Process()
        a.remote = b.remote = shared
        ids = await asyncio.gather(
            salva_f24(a, _f24("a", "prima.pdf", pdf_hash="a")),
            salva_f24(b, _f24("b", "copia.pdf", pdf_hash="b")),
        )
        assert ids[0] == ids[1]
        assert len(shared["f24_unificato"]) == 1
        assert events == [ids[0]]

    asyncio.run(scenario())


def test_versione_con_crediti_corretti_conserva_quietanza_e_annulla_solo_vecchio_debito():
    async def scenario():
        db = ClientArchivioMemoria()["versioni"]
        old = _f24("old", "Maggio.pdf", saldo=9000)
        paid = _f24(
            "paid", "Maggio (3).pdf", saldo=10000, status="pagato", quietanza_id="q"
        )
        await db["f24_unificato"].insert_many([old, paid])
        await db["partite_aperte"].insert_one(
            {
                "id": "pa",
                "tipo": "f24",
                "documento_id": "old",
                "stato": "aperta",
                "residuo": 90,
            }
        )
        await db["alerts"].insert_one(
            {"id": "alert", "entita_id": "old", "stato": "aperto"}
        )
        await sostituisci_versione(db, "old", "paid", actor="test")
        assert (await db["f24_unificato"].find_one({"id": "paid"}))[
            "quietanza_id"
        ] == "q"
        assert (await db["partite_aperte"].find_one({"id": "pa"}))[
            "stato"
        ] == "annullata"
        assert (await db["alerts"].find_one({"id": "alert"}))["risolto"] is True
        # Rileggere la versione superata torna alla vigente e non riapre il debito.
        assert await salva_f24(db, copy.deepcopy(old)) == "paid"
        assert await db["f24_unificato"].count_documents({}) == 2
        result = await sostituisci_versione(db, "old", "paid", actor="test")
        assert result["gia_sostituito"]
        other = _f24(
            "different", "Maggio (2).pdf", righe=(("1001", "03/2026", 2000, 0),)
        )
        await db["f24_unificato"].insert_one(other)
        with pytest.raises(ValueError):
            await sostituisci_versione(db, "different", "paid", actor="test")

    asyncio.run(scenario())


def test_reimport_non_cancella_pagamento():
    async def scenario():
        db = ClientArchivioMemoria()["pagamento"]
        paid = _f24(
            "paid",
            "Maggio.pdf",
            status="pagato",
            quietanza_id="q",
            movimento_bancario_id="m",
        )
        await salva_f24(db, paid)
        reread = _f24("copy", "Maggio.pdf", status="da_pagare", quietanza_id=None)
        assert await salva_f24(db, reread) == "paid"
        result = await db["f24_unificato"].find_one({"id": "paid"})
        assert result["status"] == "pagato" and result["quietanza_id"] == "q"

    asyncio.run(scenario())


def test_versioni_con_importi_diversi_richiedono_scelta_esplicita_e_conservano_prove():
    async def scenario():
        db=ClientArchivioMemoria()['f24-scelta']
        old=_f24('old','modello precedente.pdf',righe=(("1001","05/2026",20000,0),))
        good=_f24('good','modello corretto.pdf',righe=(("1001","05/2026",15000,0),),quietanza_id='q')
        await db['f24_unificato'].insert_many([old,good])
        await db['partite_aperte'].insert_one({'id':'pa','tipo':'f24','documento_id':'old','stato':'aperta'})
        with pytest.raises(ValueError):
            await sostituisci_versione(db,'old','good',actor='test')
        with pytest.raises(ValueError):
            await sostituisci_versione(db,'old','good',actor='test',conferma_importi_discordanti=True)
        assert (await db['f24_unificato'].find_one({'id':'old'})).get('sostituito') is not True
        await sostituisci_versione(db,'old','good',actor='titolare',conferma_importi_discordanti=True,motivo='Originali confrontati, vecchia versione errata')
        removed=await db['f24_unificato'].find_one({'id':'old'})
        assert removed['sostituito_da_f24_id']=='good'
        assert removed['decisione_versione']['actor']=='titolare'
        assert (await db['f24_unificato'].find_one({'id':'good'}))['quietanza_id']=='q'
        assert (await db['partite_aperte'].find_one({'id':'pa'}))['stato']=='annullata'
        assert await db['f24_unificato'].count_documents({})==2
        assert await salva_f24(db,copy.deepcopy(old))=='good'
        assert (await sostituisci_versione(db,'old','good',actor='titolare',conferma_importi_discordanti=True,motivo='Conferma'))['gia_sostituito']
    asyncio.run(scenario())


def test_non_si_esclude_un_pagato_o_un_obbligo_diverso_neppure_con_conferma():
    async def scenario():
        db=ClientArchivioMemoria()['f24-guard']
        old=_f24('old','prima.pdf',pagato=True)
        good=_f24('good','dopo.pdf')
        await db['f24_unificato'].insert_many([old,good])
        with pytest.raises(ValueError):
            await sostituisci_versione(db,'old','good',actor='test',conferma_importi_discordanti=True,motivo='test')
        await db['f24_unificato'].update_one({'id':'old'},{'$set':{'pagato':False,'codice_fiscale':'DIFFERENTE'}})
        with pytest.raises(ValueError):
            await sostituisci_versione(db,'old','good',actor='test',conferma_importi_discordanti=True,motivo='test')
        assert await db['partite_aperte'].count_documents({})==0
    asyncio.run(scenario())
