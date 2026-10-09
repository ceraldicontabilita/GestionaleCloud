"""Previsioni acquisti sulle righe VERE di `acquisti_prodotti`.

Le righe le scrive `magazzino_handlers._aggiorna_prodotto_esistente` con
`prodotto_id, fattura_id, fornitore_id, quantita, prezzo_unitario,
unita_misura, data`. Fino al 27/09/2026 le statistiche aggregavano su campi
che nessuna riga ha (`anno`, `descrizione_normalizzata`, `totale_linea`,
`data_fattura`) e tornavano vuote. I test usano righe di quella forma.
"""
import asyncio

from app.services.archivio_documenti_memoria import ClientArchivioMemoria

from app.routers import previsioni_acquisti


def _riga(prodotto_id, fattura_id, quantita, prezzo, udm="CF"):
    # Forma esatta di `magazzino_handlers._aggiorna_prodotto_esistente`:
    # `data` e' il momento dell'elaborazione, non la data della fattura.
    return {
        "id": f"r-{prodotto_id}-{fattura_id}", "prodotto_id": prodotto_id,
        "fattura_id": fattura_id, "fornitore_id": "forn-1",
        "quantita": quantita, "prezzo_unitario": prezzo, "unita_misura": udm,
        "data": "2026-09-27T08:00:00+00:00",
    }


async def _popola(db):
    await db["warehouse_inventory"].insert_many([
        {"id": "p-panuozzo", "nome": "Panuozzo", "unita_misura": "CF"},
        {"id": "p-nuovo", "nome": "Prodotto nuovo", "unita_misura": "PZ"},
    ])
    await db["invoices"].insert_many([
        {"id": "F25", "invoice_date": "2025-06-22", "supplier_name": "Forno Srl",
         "tipo_documento": "TD01"},
        {"id": "F26", "invoice_date": "2026-06-22", "supplier_name": "Forno Srl",
         "tipo_documento": "TD01"},
        # Copia archiviata della stessa fattura: non deve raddoppiare.
        {"id": "F26-arch", "invoice_date": "2026-06-22", "supplier_name": "Forno Srl",
         "tipo_documento": "TD01", "status": "archived"},
        {"id": "F26b", "invoice_date": "2026-07-01", "supplier_name": "Altro Srl",
         "tipo_documento": "TD01"},
        # Nota di credito: un reso, non un acquisto.
        {"id": "NC26", "invoice_date": "2026-07-05", "supplier_name": "Forno Srl",
         "tipo_documento": "TD04"},
    ])
    await db["acquisti_prodotti"].insert_many([
        _riga("p-panuozzo", "F25", 42.0, 0),
        _riga("p-panuozzo", "F26", 252.0, 0),
        _riga("p-panuozzo", "F26-arch", 252.0, 0),
        _riga("p-panuozzo", "NC26", 10.0, 0),
        _riga("p-nuovo", "F26b", 10.0, 2.5, "PZ"),
    ])


def test_statistiche_leggono_le_righe_vere_del_magazzino(monkeypatch):
    async def scenario():
        db = ClientArchivioMemoria()["test_previsioni_statistiche"]
        monkeypatch.setattr(
            previsioni_acquisti.Database, "get_db", staticmethod(lambda: db)
        )
        await _popola(db)

        result = await previsioni_acquisti.statistiche_acquisti(
            anno=2026, prodotto=None
        )
        per_id = {row["id"]: row for row in result["statistiche"]}

        panuozzo = per_id["p-panuozzo"]
        assert panuozzo["descrizione"] == "Panuozzo"
        # 252, non 504 (copia archiviata) ne' 262 (nota di credito)
        assert panuozzo["quantita_anno_corrente"] == 252.0
        assert panuozzo["quantita_anno_prec"] == 42.0
        assert panuozzo["differenza_quantita"] == 210.0
        assert panuozzo["variazione_pct"] == 500.0
        assert panuozzo["costo_disponibile"] is False
        # anno e data vengono dalla fattura, non dal momento dell'elaborazione
        assert panuozzo["primo_acquisto"] == "2026-06-22"

        nuovo = per_id["p-nuovo"]
        assert nuovo["variazione_pct"] is None
        assert nuovo["trend"] == "nuovo"
        assert nuovo["costo_disponibile"] is True
        assert nuovo["spesa_totale"] == 25.0  # quantita x prezzo_unitario

    asyncio.run(scenario())


def test_previsioni_e_prodotti_non_inventano_prezzi(monkeypatch):
    async def scenario():
        db = ClientArchivioMemoria()["test_previsioni_prezzi"]
        monkeypatch.setattr(
            previsioni_acquisti.Database, "get_db", staticmethod(lambda: db)
        )
        await _popola(db)

        previsioni = await previsioni_acquisti.previsioni_acquisti(
            anno_riferimento=2026, settimane_previsione=4
        )
        per_id = {p["id"]: p for p in previsioni["previsioni"]}
        assert per_id["p-panuozzo"]["quantita_anno_rif"] == 252.0
        assert per_id["p-panuozzo"]["costo_stimato"] is None  # nessun prezzo vero
        assert per_id["p-nuovo"]["prezzo_medio"] == 2.5
        assert per_id["p-nuovo"]["fornitori_abituali"] == ["Altro Srl"]
        assert previsioni["prodotti_senza_prezzo"] == 1

        prodotti = await previsioni_acquisti.lista_prodotti(
            anno=2026, fornitore=None, search="panuo", limit=100
        )
        assert [p["id"] for p in prodotti["prodotti"]] == ["p-panuozzo"]

    asyncio.run(scenario())


def test_popola_storico_salta_archiviate_note_credito_e_gia_presenti(monkeypatch):
    async def scenario():
        db = ClientArchivioMemoria()["test_previsioni_popola"]
        monkeypatch.setattr(
            previsioni_acquisti.Database, "get_db", staticmethod(lambda: db)
        )
        await db["warehouse_inventory"].insert_one(
            {"id": "p-farina", "nome": "FARINA 00", "nome_normalizzato": "farina 00"}
        )
        linea = [{"descrizione": "FARINA 00", "quantita": "5", "prezzo_unitario": "1.2",
                  "unita_misura": "KG"}]
        await db["invoices"].insert_many([
            {"id": "A", "invoice_date": "2026-03-01", "tipo_documento": "TD01", "linee": linea},
            {"id": "A-arch", "invoice_date": "2026-03-01", "tipo_documento": "TD01",
             "status": "archived", "linee": linea},
            {"id": "NC", "invoice_date": "2026-03-02", "tipo_documento": "TD04", "linee": linea},
            {"id": "B", "invoice_date": "2026-03-03", "tipo_documento": "TD01", "linee": linea},
        ])
        # B e' gia' nello storico (l'ha scritta il gestore magazzino all'import)
        await db["acquisti_prodotti"].insert_one(_riga("p-farina", "B", 5.0, 1.2, "KG"))

        primo = await previsioni_acquisti.popola_storico_da_fatture()
        assert primo["prodotti_registrati"] == 1
        assert primo["note_credito_escluse"] == 1
        assert primo["fatture_gia_nello_storico"] == 1
        righe = await db["acquisti_prodotti"].find({"fattura_id": "A"}, {"_id": 0}).to_list(None)
        assert len(righe) == 1
        assert righe[0]["prodotto_id"] == "p-farina"
        assert righe[0]["quantita"] == 5.0 and righe[0]["prezzo_unitario"] == 1.2
        assert await db["acquisti_prodotti"].count_documents({"fattura_id": {"$in": ["A-arch", "NC"]}}) == 0

        # Il secondo giro non scrive niente (idempotenza).
        secondo = await previsioni_acquisti.popola_storico_da_fatture()
        assert secondo["prodotti_registrati"] == 0

    asyncio.run(scenario())
