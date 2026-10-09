import asyncio

from app.services.archivio_documenti_memoria import ClientArchivioMemoria

from app.services.proiezione_bancaria import proietta_movimenti_bancari_semantici


def _run(awaitable):
    return asyncio.run(awaitable)


def test_proiezione_semantica_e_idempotente_senza_match_per_solo_importo():
    db = ClientArchivioMemoria()["proiezione_bancaria_test"]
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


# ── una riga per operazione, non per copia dell'estratto conto ──────────────
# Produzione, 26/09/2026: lo stesso stipendio arrivava dal vecchio archivio e
# da un CSV della banca, e ogni copia scriveva la sua riga (23 stipendi due
# volte, 27.076,00 EUR di uscite in piu').

def _db_dipendente():
    db = ClientArchivioMemoria()["proiezione_copie"]
    _run(db["dipendenti"].insert_one({
        "id": "dip-valerio", "nome": "Valerio", "cognome": "Ceraldi",
        "nome_completo": "Valerio Ceraldi", "codice_fiscale": "CRLVLR88H14F839O",
    }))
    return db


def _stipendio(id_, fonte, data="2026-08-07", importo=1400.0):
    return {"id": id_, "data": data, "tipo": "uscita", "importo": importo,
            "descrizione_originale": "VOSTRA DISPOSIZIONE FAVORE CERALDI VALERIO CRLVLR88H14F839O stipendio",
            "source_filename" if fonte.endswith(".csv") else "fonte": fonte}


def _attive(db):
    return _run(db["prima_nota_banca"].find({"status": {"$nin": ["deleted", "archived"]}}).to_list(100))


def test_due_copie_dello_stesso_stipendio_fanno_una_riga():
    db = _db_dipendente()
    _run(db["estratto_conto_movimenti"].insert_many([
        _stipendio("ec-legacy", "legacy_staging_2026"), _stipendio("ec-csv", "export.csv"),
    ]))
    _run(proietta_movimenti_bancari_semantici(db))
    righe = _attive(db)
    assert len(righe) == 1
    copie = _run(db["estratto_conto_movimenti"].find({}).to_list(10))
    assert {c["prima_nota_banca_id"] for c in copie} == {righe[0]["id"]}


def test_il_doppione_gia_scritto_si_toglie_e_resta_uno():
    db = _db_dipendente()
    _run(db["estratto_conto_movimenti"].insert_many([
        _stipendio("ec-legacy", "legacy_staging_2026"), _stipendio("ec-csv", "export.csv"),
    ]))
    for ec in ("ec-legacy", "ec-csv"):
        _run(db["prima_nota_banca"].insert_one({
            "id": f"pn-{ec}", "data": "2026-08-07", "tipo": "uscita", "importo": 1400.0,
            "categoria": "Stipendi", "dipendente_id": "dip-valerio",
            "source": "proiezione_semantica_ec", "estratto_conto_id": ec,
        }))
    esito = _run(proietta_movimenti_bancari_semantici(db))
    assert esito["doppioni_tolti"] == 1
    assert len(_attive(db)) == 1


def test_due_stipendi_uguali_nello_stesso_export_restano_due():
    db = _db_dipendente()
    _run(db["estratto_conto_movimenti"].insert_many([
        _stipendio("a1", "export.csv"), _stipendio("a2", "export.csv"),
        _stipendio("l1", "legacy_staging_2026"), _stipendio("l2", "legacy_staging_2026"),
    ]))
    _run(proietta_movimenti_bancari_semantici(db))
    assert len(_attive(db)) == 2


def test_la_riga_di_un_altro_canale_conta_e_non_si_tocca():
    db = _db_dipendente()
    _run(db["estratto_conto_movimenti"].insert_one(_stipendio("ec-csv", "export.csv")))
    _run(db["prima_nota_banca"].insert_one({
        "id": "a-mano", "data": "2026-08-07", "tipo": "uscita", "importo": 1400.0,
        "categoria": "Stipendi", "dipendente_id": "dip-valerio", "source": "manuale",
    }))
    esito = _run(proietta_movimenti_bancari_semantici(db))
    assert esito["proiettati"] == 0 and esito["doppioni_tolti"] == 0
    assert [r["id"] for r in _attive(db)] == ["a-mano"]


# Produzione, 27/09/2026: 17 stipendi in due righe. La prima era stata scritta
# col dipendente provvisorio ``salario:nome|cognome`` e finiva in un altro
# gruppo: la copia gemella della stessa operazione ne scriveva una seconda.

def test_lo_stipendio_col_dipendente_provvisorio_non_si_raddoppia():
    db = _db_dipendente()
    _run(db["estratto_conto_movimenti"].insert_many([
        _stipendio("ec-legacy", "legacy_staging_2026"), _stipendio("ec-csv", "export.csv"),
    ]))
    _run(db["prima_nota_banca"].insert_one({
        "id": "pn-vecchia", "data": "2026-08-07", "tipo": "uscita", "importo": 1400.0,
        "categoria": "Stipendi", "dipendente_id": "salario:ceraldi|valerio",
        "source": "proiezione_semantica_ec", "estratto_conto_id": "ec-legacy",
    }))
    esito = _run(proietta_movimenti_bancari_semantici(db))
    assert esito["proiettati"] == 0
    assert [r["id"] for r in _attive(db)] == ["pn-vecchia"]
    _run(proietta_movimenti_bancari_semantici(db))
    assert [r["id"] for r in _attive(db)] == ["pn-vecchia"]


def test_la_rata_del_mutuo_entra_in_banca_col_numero_e_senza_quote_inventate():
    db = _db_dipendente()
    _run(db["estratto_conto_movimenti"].insert_many([
        {"id": "m1", "data": "2026-09-24", "tipo": "uscita", "importo": 512.35, "fonte": "enable_banking",
         "descrizione_originale": "RIMBORSO FINANZ. - MUTUO N.1788 4851906 RATA 24/09/2026"},
        {"id": "m2", "data": "2026-06-24", "tipo": "uscita", "importo": 512.39, "fonte": "legacy_staging_2026",
         "descrizione_originale": "MUTUO N.1788 4851906 RATA 24/06/2026"},
        {"id": "m3", "data": "2026-06-24", "tipo": "entrata", "importo": 30000.0,
         "descrizione_originale": "EROGAZIONE MUTUO N.1788 4851906"},
    ]))
    esito = _run(proietta_movimenti_bancari_semantici(db))
    assert esito["rate_mutuo"] == 2
    rate = sorted(_attive(db), key=lambda r: r["data"])
    assert [r["categoria"] for r in rate] == ["Rata mutuo", "Rata mutuo"]
    assert {r["numero_mutuo"] for r in rate} == {"1788 4851906"}
    assert all(r["ripartizione_capitale_interessi"] == "da_verificare" for r in rate)
    assert all("quota_interessi" not in r and "quota_capitale" not in r for r in rate)


# ── quote capitale/interessi dal piano d'ammortamento o dalla quietanza ─────

def _rata(id_, data, importo, scadenza):
    return {"id": id_, "data": data, "tipo": "uscita", "importo": importo, "fonte": "export.csv",
            "descrizione_originale": f"RIMBORSO FINANZ. - MUTUO N.1788 4851906 RATA {scadenza}"}


def _piano(db):
    _run(db["mutui_piani_documentali"].insert_one({
        "id": "piano", "numero_delibera": "904851906", "rate": [
            {"numero_rata": 47, "data_scadenza": "24/08/2026", "importo_totale": 512.36,
             "quota_capitale": 506.53, "quota_interessi": 5.83, "stato": "Pagata"},
            {"numero_rata": 48, "data_scadenza": "24/09/2026", "importo_totale": 512.35,
             "quota_capitale": 506.93, "quota_interessi": 5.42, "stato": "Pagata"},
        ]}))


def test_la_rata_prende_capitale_e_interessi_dal_piano():
    db = _db_dipendente()
    _piano(db)
    _run(db["estratto_conto_movimenti"].insert_one(_rata("r48", "2026-09-24", 512.35, "24/09/2026")))
    _run(proietta_movimenti_bancari_semantici(db))
    riga = _attive(db)[0]
    assert (riga["quota_capitale"], riga["quota_interessi"]) == (506.93, 5.42)
    assert riga["numero_rata"] == 48
    assert riga["ripartizione_capitale_interessi"] == "piano_ammortamento"
    assert riga["ripartizione_conti"] == [
        {"conto": "31.03.05", "importo": 506.93}, {"conto": "75.03.05", "importo": 5.42}]


def test_la_quietanza_vince_sul_piano_e_il_numero_ha_tre_forme():
    db = _db_dipendente()
    _piano(db)
    _run(db["mutui_quietanze"].insert_one({
        "numero_finanziamento": "1788/0004851906", "data_scadenza": "2026-08-24",
        "importo_totale": 512.36, "quota_capitale": 506.53, "quota_interessi": 5.83, "numero_rata": 47}))
    _run(db["estratto_conto_movimenti"].insert_one(_rata("r47", "2026-08-24", 512.36, "24/08/2026")))
    _run(proietta_movimenti_bancari_semantici(db))
    assert _attive(db)[0]["ripartizione_capitale_interessi"] == "quietanza"


def test_importo_diverso_dal_piano_resta_da_verificare():
    db = _db_dipendente()
    _piano(db)
    _run(db["estratto_conto_movimenti"].insert_one(_rata("r48", "2026-09-24", 512.00, "24/09/2026")))
    _run(proietta_movimenti_bancari_semantici(db))
    riga = _attive(db)[0]
    assert riga["ripartizione_capitale_interessi"] == "da_verificare"
    assert "quota_capitale" not in riga


def test_la_rata_gia_in_banca_si_aggiorna_quando_arriva_il_piano():
    db = _db_dipendente()
    _run(db["estratto_conto_movimenti"].insert_one(_rata("r48", "2026-09-24", 512.35, "24/09/2026")))
    _run(proietta_movimenti_bancari_semantici(db))
    assert _attive(db)[0]["ripartizione_capitale_interessi"] == "da_verificare"
    _piano(db)
    esito = _run(proietta_movimenti_bancari_semantici(db))
    righe = _attive(db)
    assert len(righe) == 1 and esito["proiettati"] == 0
    assert righe[0]["quota_interessi"] == 5.42


def test_stesso_bonifico_con_dipendente_diverso_nelle_copie_resta_una_riga():
    """Produzione 27/09/2026: 17 stipendi (14.000,00 EUR) contati due volte.
    La copia del vecchio archivio portava il dipendente provvisorio ricavato
    dai salari, l'export quello vero: due gruppi, due righe. Il riferimento
    della disposizione (MB…) li riconosce come lo stesso bonifico."""
    db = _db_dipendente()
    causale = "VS.DISP. RIF. MB0B10283131/90366939 FAVORE CERALDI VALERIO stipendio"
    _run(db["estratto_conto_movimenti"].insert_many([
        {**_stipendio("ec-legacy", "legacy_staging_2026", data="2026-02-03", importo=1000.0),
         "descrizione_originale": causale, "dipendente_id": "salario:ceraldi|valerio"},
        {**_stipendio("ec-csv", "export.csv", data="2026-02-03", importo=1000.0),
         "descrizione_originale": "VOSTRA DISPOSIZIONE - " + causale},
    ]))
    comune = {"data": "2026-02-03", "tipo": "uscita", "importo": 1000.0, "categoria": "Stipendi",
              "source": "proiezione_semantica_ec"}
    _run(db["prima_nota_banca"].insert_many([
        {**comune, "id": "pn-provvisoria", "dipendente_id": "salario:ceraldi|valerio",
         "estratto_conto_id": "ec-legacy", "descrizione": causale},
        {**comune, "id": "pn-vera", "dipendente_id": "dip-valerio",
         "estratto_conto_id": "ec-csv", "descrizione": "VOSTRA DISPOSIZIONE - " + causale},
    ]))
    esito = _run(proietta_movimenti_bancari_semantici(db))
    assert esito["doppioni_tolti"] == 1
    assert [r["id"] for r in _attive(db)] == ["pn-vera"]
    secondo = _run(proietta_movimenti_bancari_semantici(db))
    assert secondo["proiettati"] == 0 and secondo["doppioni_tolti"] == 0
    assert [r["id"] for r in _attive(db)] == ["pn-vera"]


def test_la_commissione_del_bonifico_non_e_uno_stipendio():
    """«VS.DISP. … FAVORE <dipendente> - ADD.SPE» da 1,10 EUR: il nome del
    beneficiario c'e', ma e' la commissione della banca. La riga gia' scritta
    come stipendio si riclassifica con lo stesso id."""
    db = _db_dipendente()
    _run(db["estratto_conto_movimenti"].insert_one({
        "id": "ec-comm", "data": "2026-04-02", "tipo": "uscita", "importo": 1.10,
        "fonte": "legacy_staging_2026",
        "descrizione": "VS.DISP. RIF. MB0B39331260/90552422 FAVORE CERALDI VALERIO - ADD.SPE",
    }))
    _run(db["prima_nota_banca"].insert_one({
        "id": "pn-comm", "data": "2026-04-02", "tipo": "uscita", "importo": 1.10,
        "categoria": "Stipendi", "dipendente_id": "dip-valerio",
        "source": "proiezione_semantica_ec", "estratto_conto_id": "ec-comm",
    }))
    _run(proietta_movimenti_bancari_semantici(db))
    righe = _attive(db)
    assert [r["id"] for r in righe] == ["pn-comm"]
    assert righe[0]["categoria"] == "Commissioni bancarie"
    assert not righe[0].get("dipendente_id")
