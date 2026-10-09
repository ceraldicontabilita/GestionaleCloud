"""La richiesta dal reparto resta nel carrello fino alla revisione del titolare."""

import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.lotti.routers import ordini_fornitori as ordini


def run(coro):
    return asyncio.run(coro)


def test_richiesta_reparto_non_viene_cancellata_dal_carrello_cataloghi(monkeypatch):
    database = AsyncMongoMockClient().test_richieste_acquisto
    monkeypatch.setattr(ordini, "db", database)
    richiesta = ordini.RichiestaAcquistoReparto(
        prodotto_id="prodotto-1", nome="OLVA THERMO QUICK", quantita=2,
        unita="pz", fornitore="Fornitore A", richiesto_da="Operatore", reparto="pasticceria",
    )

    aggiunta = run(ordini.aggiungi_richiesta_acquisto(richiesta))
    assert aggiunta["richiesta"]["stato"] == "da_valutare"
    run(ordini.set_carrello_sospesi(ordini.CarrelloSospesiPayload(righe=[{"id": "catalogo-1"}])))
    carrello = run(ordini.get_carrello_sospesi())
    assert carrello["righe"] == [{"id": "catalogo-1"}]
    assert [r["id"] for r in carrello["richieste"]] == [aggiunta["richiesta"]["id"]]
    assert carrello["richieste"][0]["reparto"] == "pasticceria"

    async def admin_autorizzato(_request):
        return None

    monkeypatch.setattr(ordini, "require_admin", admin_autorizzato)
    run(ordini.rimuovi_richiesta_acquisto(aggiunta["richiesta"]["id"], None))
    carrello_finale = run(ordini.get_carrello_sospesi())
    assert carrello_finale["richieste"] == []
    assert carrello_finale["righe"] == [{"id": "catalogo-1"}]


def test_ritentare_la_stessa_bozza_non_duplica_l_ordine(monkeypatch):
    database = AsyncMongoMockClient().test_idempotenza_acquisto
    monkeypatch.setattr(ordini, "db", database)
    payload = ordini.OrdineCreateFull(
        source="ordini_app", operatore="Titolare", idempotency_key="carrello:richiesta-1",
        prodotti=[ordini.ProdottoOrdine(
            prodotto_id="prodotto-1", nome="OLVA THERMO QUICK", fornitore="Fornitore A",
            quantita=2, unita="pz",
        )],
    )
    prima = run(ordini.crea_ordine(payload))
    seconda = run(ordini.crea_ordine(payload))
    assert seconda["gia_creata"] is True
    assert seconda["ordine_id"] == prima["ordine_id"]
    assert run(database.ordini_fornitori.count_documents({})) == 1
