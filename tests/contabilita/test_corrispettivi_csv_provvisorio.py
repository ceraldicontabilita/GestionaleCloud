"""CSV AdE dei corrispettivi: dato provvisorio, l'XML lo sovrascrive (importi di prova, struttura reale)."""
import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.services import corrispettivi_service as cs

TESTATA = ("Id invio;Matricola dispositivo;Data e ora rilevazione;Data e ora trasmissione;"
           "Ammontare delle vendite (totale in euro);Imponibile vendite (totale in euro);"
           "Imposta vendite (totale in euro);Periodo di inattivita' da;Periodo di inattivita' a\n")


def _riga(invio, giorno, ammontare, imponibile, imposta):
    return (f"'{invio}';'99MEY026532';{giorno} 21:17:52;{giorno} 21:18:28;"
            f"{ammontare};{imponibile};{imposta};;\n")


CSV = TESTATA + _riga(1, "30/09/2026", "000000002518,15", "000000002518,15", "000000000251,81") \
    + _riga(2, "29/09/2026", "000000002562,27", "000000002562,27", "000000000256,23") \
    + _riga(3, "01/09/2026", "000000002039,82", "000000002039,82", "000000000203,98")


def _run(c):
    return asyncio.run(c)


def _db_con_xml_del_primo():
    db = AsyncMongoMockClient()["t"]
    _run(db["corrispettivi"].insert_one({
        "id": "x1", "data": "2026-09-01", "stato": "definitivo_xml", "source": "xml",
        "corrispettivo_key": "k1", "matricola_rt": "99MEY026532", "totale": 2243.8,
        "totale_imponibile": 2039.82, "totale_iva": 203.98, "pagato_contanti": 639.0}))
    return db


def test_ammontare_e_l_imponibile_e_il_totale_e_derivato():
    letto = cs.leggi_csv_ade(CSV)
    assert letto["errori"] == [] and len(letto["righe"]) == 3
    assert letto["righe"][0]["ammontare_cents"] == 251815 and letto["righe"][0]["imposta_cents"] == 25181
    assert letto["righe"][0]["data"] == "2026-09-30"


def test_giornate_senza_xml_entrano_provvisorie_senza_quote_e_senza_evento():
    db = _db_con_xml_del_primo()
    esito = _run(cs.importa_csv_ade(db, CSV, "settembre.csv"))
    assert esito["nuovi"] == 2 and esito["gia_definitivi"] == 1 and esito["discordanze_con_xml"] == []
    doc = _run(db["corrispettivi"].find_one({"data": "2026-09-30"}))
    assert doc["stato"] == "provvisorio" and doc["source"] == "csv_ade" and doc["matricola_rt"] == "99MEY026532"
    assert doc["totale_imponibile_cents"] == 251815 and doc["totale_iva_cents"] == 25181
    assert doc["totale_cents"] == 251815 + 25181
    assert doc["pagato_contanti"] is None and doc["pagato_elettronico"] is None     # mai per differenza
    assert doc["totale_derivato"] is True and "prima_nota_cassa_id" not in doc
    # la giornata gia' definitiva non e' stata toccata
    assert _run(db["corrispettivi"].count_documents({"data": "2026-09-01"})) == 1


def test_secondo_import_dello_stesso_file_non_crea_niente():
    db = _db_con_xml_del_primo()
    _run(cs.importa_csv_ade(db, CSV, "a.csv"))
    esito = _run(cs.importa_csv_ade(db, CSV, "a.csv"))
    assert esito["nuovi"] == 0 and esito["aggiornati"] == 0 and esito["invariati"] == 2
    assert _run(db["corrispettivi"].count_documents({})) == 3


def test_anteprima_non_scrive():
    db = _db_con_xml_del_primo()
    esito = _run(cs.importa_csv_ade(db, CSV, "a.csv", dry_run=True))
    assert esito["dry_run"] is True and esito["nuovi"] == 2
    assert _run(db["corrispettivi"].count_documents({})) == 1


def test_imponibile_diverso_dall_xml_si_dichiara_non_si_corregge():
    db = _db_con_xml_del_primo()
    csv = TESTATA + _riga(3, "01/09/2026", "000000002000,00", "000000002000,00", "000000000200,00")
    esito = _run(cs.importa_csv_ade(db, csv, "a.csv"))
    assert esito["discordanze_con_xml"] == [{"data": "2026-09-01", "imponibile_xml_cents": 203982, "imponibile_csv_cents": 200000}]
    assert _run(db["corrispettivi"].find_one({"data": "2026-09-01"}))["totale_imponibile"] == 2039.82


def test_una_riga_manuale_gia_presente_non_si_sovrascrive():
    db = AsyncMongoMockClient()["t"]
    _run(db["corrispettivi"].insert_one({"id": "m1", "data": "2026-09-30", "stato": "provvisorio",
                                          "source": "manuale_serale", "totale": 2700.0}))
    esito = _run(cs.importa_csv_ade(db, CSV, "a.csv"))
    assert [c["data"] for c in esito["conflitti"]] == ["2026-09-30"]
    assert _run(db["corrispettivi"].count_documents({"data": "2026-09-30"})) == 1


def test_due_chiusure_dello_stesso_giorno_restano_due_righe():
    db = AsyncMongoMockClient()["t"]
    csv = TESTATA + _riga(10, "06/09/2026", "000000001454,09", "000000001454,09", "000000000145,41") \
        + _riga(11, "06/09/2026", "000000000543,09", "000000000543,09", "000000000054,31")
    assert _run(cs.importa_csv_ade(db, csv, "a.csv"))["nuovi"] == 2
    assert _run(db["corrispettivi"].count_documents({"data": "2026-09-06"})) == 2


def test_xml_successivo_promuove_la_riga_provvisoria_e_sovrascrive():
    """Stesso percorso di import dell'XML: data + matricola trovano la riga provvisoria."""
    from app.routers.invoices.corrispettivi_helpers import _find_existing_corrispettivo

    db = AsyncMongoMockClient()["t"]
    _run(cs.importa_csv_ade(db, TESTATA + _riga(1, "30/09/2026", "000000002518,15", "000000002518,15", "000000000251,81"), "a.csv"))
    xml = {"corrispettivo_key": "04523831214_2026-09-30_99MEY026532_2650", "data": "2026-09-30",
           "matricola_rt": "99MEY026532", "totale": 2770.0}
    trovata = _run(_find_existing_corrispettivo(db, xml))
    assert trovata is not None and trovata["stato"] == "provvisorio" and trovata["source"] == "csv_ade"


def test_import_xml_sulla_riga_provvisoria_la_promuove_a_definitivo():
    from app.routers.invoices.corrispettivi_helpers import ingest_corrispettivo_parsed

    db = AsyncMongoMockClient()["t"]
    _run(cs.importa_csv_ade(db, TESTATA + _riga(1, "30/09/2026", "000000002518,15", "000000002518,15", "000000000251,81"), "a.csv"))
    parsed = {"corrispettivo_key": "04523831214_2026-09-30_99MEY026532_2650", "data": "2026-09-30",
              "matricola_rt": "99MEY026532", "totale": 2770.0, "pagato_contanti": 700.0, "pagato_elettronico": 2070.0,
              "totale_imponibile": 2518.15, "totale_iva": 251.81, "numero_documento": "2650"}
    try:
        _run(ingest_corrispettivo_parsed(db, parsed, "x.xml", "xml"))
    except Exception as exc:  # noqa: BLE001 - Prima Nota/giornale non sono l'oggetto di questa prova
        raise AssertionError(f"{type(exc).__name__}: {exc}") from exc
    righe = _run(db["corrispettivi"].find({"data": "2026-09-30"}).to_list(10))
    assert len(righe) == 1
    r = righe[0]
    assert r["stato"] == "definitivo_xml" and r["source"] == "xml" and r["pagato_contanti"] == 700.0
    assert r["totale"] == 2770.0 and r["totale_derivato"] is False and r["csv_ade"]["id_invio"] == "1"


def test_documenti_import_riconosce_il_csv_ade_dei_corrispettivi():
    from app.routers.documenti import detect_document_type

    assert detect_document_type("settembre_corrispettivi.csv", CSV.encode("utf-8")) == "corrispettivi_csv_ade"
    assert detect_document_type("altro.csv", b"a;b;c\n1;2;3\n") != "corrispettivi_csv_ade"
