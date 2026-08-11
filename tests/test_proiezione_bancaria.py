import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.services.proiezione_bancaria import proietta_movimenti_bancari_semantici


def _run(awaitable):
    return asyncio.run(awaitable)


def test_proiezione_semantica_e_idempotente_senza_match_per_solo_importo():
    db = AsyncMongoMockClient()["proiezione_bancaria_test"]
    _run(db["dipendenti"].insert_many([
        {
            "id": "dip-valerio", "nome": "Valerio", "cognome": "Ceraldi",
            "nome_completo": "Valerio Ceraldi",
            "codice_fiscale": "CRLVLR88H14F839O",
        },
        {
            "id": "dip-moscato", "nome": "Emanuele", "cognome": "Moscato",
            "nome_completo": "Emanuele Moscato",
            "codice_fiscale": "MSCMNL88R26F839C",
        },
    ]))
    _run(db["estratto_conto_movimenti"].insert_many([
        {
            "id": "ec-finanziamento", "data": "2026-08-07",
            "tipo": "entrata", "importo": 15000.0,
            "stato_riconciliazione": "in_attesa_documento",
            "descrizione_originale": (
                "BONIF. VS. FAVORE - BON.DA CERALDI MICHELE PANE GIUSEPPINA "
                "- Finanziamento infruttifero alla Ceraldi Group SRL"
            ),
        },
        {
            "id": "ec-stipendio-moscato", "data": "2026-08-07",
            "tipo": "uscita", "importo": 1500.0,
            "stato_riconciliazione": "in_attesa_documento",
            "descrizione_originale": (
                "VOSTRA DISPOSIZIONE FAVORE MOSCATO EMANUELE ADD.TOT stipendio"
            ),
        },
        {
            "id": "ec-stipendio-valerio", "data": "2026-08-07",
            "tipo": "uscita", "importo": 1400.0,
            "stato_riconciliazione": "in_attesa_documento",
            "descrizione_originale": (
                "VOSTRA DISPOSIZIONE FAVORE CERALDI VALERIO "
                "CRLVLR88H14F839O stipendio"
            ),
        },
        {
            "id": "ec-tfr-moscato", "data": "2026-08-07",
            "tipo": "uscita", "importo": 15000.0,
            "stato_riconciliazione": "in_attesa_documento",
            "descrizione_originale": (
                "VOSTRA DISPOSIZIONE FAVORE MOSCATO EMANUELE "
                "MSCMNL88R26F839C TFR"
            ),
        },
        {
            "id": "ec-paypal", "data": "2026-08-07", "tipo": "uscita",
            "importo": 23.10, "stato_riconciliazione": "in_attesa_documento",
            "descrizione_originale": (
                "ADDEBITO DIRETTO SDD - SDD CORE: 49RJ2252ASLM4 "
                "PayPal Europe S.a.r.l. et Cie S.C.A"
            ),
        },
        {
            "id": "ec-generico-stesso-importo", "data": "2026-08-07",
            "tipo": "uscita", "importo": 23.10,
            "stato_riconciliazione": "in_attesa_documento",
            "descrizione_originale": "OPERAZIONE GENERICA SENZA IDENTITA",
        },
        {
            "id": "ec-carnet", "data": "2026-08-08", "tipo": "uscita",
            "importo": 7.50,
            "descrizione_originale": "SPESE - RILASCIO CARNET ASSEGNI",
        },
        {
            "id": "ec-competenze", "data": "2026-08-09", "tipo": "uscita",
            "importo": 18.25,
            "descrizione_originale": "INT. E COMP. - COMPETENZE",
        },
    ]))

    prima = _run(proietta_movimenti_bancari_semantici(db, anno=2026))
    seconda = _run(proietta_movimenti_bancari_semantici(db, anno=2026))

    assert prima["proiettati"] == 7
    assert prima["finanziamenti_soci"] == 1
    assert prima["stipendi"] == 2
    assert prima["tfr"] == 1
    assert prima["paypal_sdd"] == 1
    assert prima["commissioni_bancarie"] == 2
    assert prima["non_classificati"] == 1
    assert seconda["proiettati"] == 0
    assert seconda["gia_presenti"] == 7

    righe_banca = _run(db["prima_nota_banca"].find({}).to_list(100))
    assert len(righe_banca) == 7
    assert {r["categoria"] for r in righe_banca} == {
        "Finanziamento soci", "Stipendi", "TFR", "Pagamento PayPal",
        "Commissioni bancarie",
    }
    assert all(r["natura"] == "movimento_bancario_reale" for r in righe_banca)
    assert len({r["estratto_conto_id"] for r in righe_banca}) == 7

    generico = _run(db["estratto_conto_movimenti"].find_one({
        "id": "ec-generico-stesso-importo",
    }))
    assert generico.get("classificato_contabilmente") is not True
    assert _run(db["estratto_conto_movimenti"].count_documents({
        "classificato_contabilmente": True,
    })) == 7
