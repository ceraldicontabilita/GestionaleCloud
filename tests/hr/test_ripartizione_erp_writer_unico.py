"""Le quote HR aggiornano gli originali ERP senza moltiplicare un bonifico."""
import asyncio

from app.services.archivio_documenti_memoria import ArchivioDocumenti
from app.services import associazione_salari as servizio


def test_quote_parziali_replay_ridistribuzione_e_ritiro(monkeypatch):
    from app.hr.routers import dipendenti_cloud as router

    hr, erp = ArchivioDocumenti("hr"), ArchivioDocumenti("erp")
    monkeypatch.setattr(router, "_db_gestionale", lambda: erp)

    async def scenario():
        await hr.dipendenti.insert_one({"id": "d", "codice_fiscale": "CF", "nome": "Mario", "cognome": "Rossi"})
        for mese in (10, 11):
            await hr.cedolini.insert_one({"id": f"h{mese}", "dipendente_id": "d", "codice_fiscale": "CF",
                "anno": 2025, "mese": mese, "netto": 500, "tipo_cedolino": "ordinario",
                "gestionale_cedolino_id": f"g{mese}"})
            await hr.paghe_mensili.insert_one({"dipendente_id": "d", "anno": 2025, "mese": mese,
                "importo_busta": 500, "cedolino_id": f"h{mese}"})
            await erp.cedolini.insert_one({"id": f"g{mese}", "codice_fiscale": "CF", "anno": 2025,
                "mese": mese, "netto": 500, "tipo_cedolino": "mensile", "pagamenti": []})

        async def conferma(id_, importo, destinazioni=None):
            pagamento = {"id": id_, "data": "2025-12-01", "importo": importo, "dipendente_id": "d"}
            await hr.bonifici_da_associare.update_one({"id": id_}, {"$set": pagamento}, upsert=True)
            piano = await servizio.anteprima(hr, pagamento, "d", destinazioni)
            return await servizio.conferma(hr, pagamento, "d", {"versione": piano["versione"],
                "destinazioni": piano["destinazioni"]}, "Titolare")

        async def importi():
            return [(await erp.cedolini.find_one({"id": f"g{m}"}))["importo_pagato"] for m in (10, 11)]

        primo = await conferma("q1", 800)
        assert await importi() == [500, 300]
        assert sum(await importi()) == 800
        assert len(primo["cedolini_gestionale"]) == 2
        await conferma("q1", 800)  # replay: stessi riferimenti, nessun doppione
        assert await importi() == [500, 300]
        await conferma("q2", 500)
        assert await importi() == [500, 500]  # gli altri 300 restano acconto
        await conferma("q1", 800, [{"anno": 2025, "mese": 11, "importo": 500}])
        assert await importi() == [500, 500]
        await servizio.annulla(hr, primo["pagamento_key"], "Titolare")
        assert await importi() == [500, 0]  # q2 redistribuito al residuo più antico
        ottobre = await erp.cedolini.find_one({"id": "g10"})
        novembre = await erp.cedolini.find_one({"id": "g11"})
        assert ottobre["pagato"] is True and novembre["pagato"] is False
        assert ottobre["pagamenti"][0]["riferimento"] == "hr:bonifici_da_associare:q2"
        assert len(ottobre["pagamenti"]) == 1 and novembre["pagamenti"] == []
        q = await hr.bonifici_da_associare.find_one({"id": "q1"})
        assert q["confermato_manuale"] is False and q["confermato_da"] is None
        assert q["storico"][-1]["azione"] == "ritira_conferma"
        assert await hr.pagamenti_esiti.count_documents({}) == 1

    asyncio.run(scenario())


def test_erp_irraggiungibile_dichiarato_senza_annullare_hr(monkeypatch):
    from app.hr.routers import dipendenti_cloud as router
    monkeypatch.setattr(router, "_db_gestionale", lambda: None)

    async def scenario():
        hr = ArchivioDocumenti("hr")
        await hr.dipendenti.insert_one({"id": "d"})
        await hr.paghe_mensili.insert_one({"dipendente_id": "d", "anno": 2025, "mese": 10, "importo_busta": 100})
        p = {"id": "q", "data": "2025-11-01", "importo": 100}
        piano = await servizio.anteprima(hr, p, "d")
        r = await servizio.conferma(hr, p, "d", {"versione": piano["versione"]})
        assert r["ok"] is True
        assert r["cedolino_gestionale"]["esito"] == "gestionale_non_raggiungibile"
        assert await hr.pagamenti_esiti.count_documents({}) == 1

    asyncio.run(scenario())


def test_mese_manuale_senza_busta_non_paga_arretrati_e_sync_conserva_quote(monkeypatch):
    from app.hr.routers import dipendenti_cloud as router
    from app.hr.services.sincronizza_paghe_mensili import sincronizza

    hr = ArchivioDocumenti("hr")
    monkeypatch.setattr(router, "get_db", lambda: hr)
    monkeypatch.setattr(router, "_db_gestionale", lambda: None)

    async def scenario():
        await hr.dipendenti.insert_one({"id": "d", "nome": "Mario", "cognome": "Rossi"})
        await hr.cedolini.insert_one({"id": "old", "dipendente_id": "d", "anno": 2025,
            "mese": 10, "netto": 100, "tipo_cedolino": "ordinario"})
        await hr.paghe_mensili.insert_one({"dipendente_id": "d", "anno": 2025, "mese": 10,
            "importo_busta": 100, "cedolino_id": "old"})
        await hr.bonifici_da_associare.insert_one({"id": "q", "data": "2025-12-03",
            "importo": 500, "stato": "da_associare", "causale": "bonifico"})
        await router.associa_bonifico("q", {"dipendente_id": "d", "anno": 2025, "mese": 11},
                                     {"role": "admin", "name": "Titolare"})
        ottobre = await hr.paghe_mensili.find_one({"dipendente_id": "d", "anno": 2025, "mese": 10})
        novembre = await hr.paghe_mensili.find_one({"dipendente_id": "d", "anno": 2025, "mese": 11})
        assert ottobre["bonifico_importo"] == 0 and ottobre["saldo"] == 100
        assert novembre["bonifico_importo"] == 500 and novembre["saldo"] is None
        assert novembre["stato_pagamento"] == "in_attesa_busta"
        assert "importo_busta" not in novembre
        await hr.cedolini.insert_one({"id": "new", "dipendente_id": "d", "anno": 2025,
            "mese": 11, "netto": 700, "tipo_cedolino": "ordinario"})
        await sincronizza(hr)
        novembre = await hr.paghe_mensili.find_one({"dipendente_id": "d", "anno": 2025, "mese": 11})
        assert (novembre["bonifico_importo"], novembre["saldo"], novembre["stato_pagamento"]) == (500, 200, "parziale")
        await sincronizza(hr)  # un secondo import non perde né duplica il pagamento
        novembre = await hr.paghe_mensili.find_one({"dipendente_id": "d", "anno": 2025, "mese": 11})
        assert (novembre["bonifico_importo"], novembre["saldo"], novembre["stato_pagamento"]) == (500, 200, "parziale")
        assert await hr.pagamenti_esiti.count_documents({}) == 1

    asyncio.run(scenario())
