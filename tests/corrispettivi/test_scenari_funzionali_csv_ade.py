"""Collaudo funzionale: il CSV «Corrispettivi» del portale AdE e l'XML che lo sostituisce.

Regola (CLAUDE.md, «Ingresso documenti»): il CSV e' un dato PROVVISORIO.
«Ammontare delle vendite» e' l'**imponibile**, il totale e' derivato, contanti e
POS restano `None` (mai per differenza). Ne' Prima Nota, ne' giornale, ne'
evento finche' non arriva l'XML: data + matricola lo agganciano, lo stato
diventa `definitivo_xml`, importi e quote si sovrascrivono e il CSV resta in
`csv_ade` come storico. Una giornata gia' `definitivo_xml` il CSV non la tocca:
dichiara soltanto la discordanza di imponibile.
"""
from app.services.registrazione_contabile import registra_tutti_corrispettivi

from ._comune import (
    D, MATRICOLA, Importatore, attive, importo_conto, istantanea, nuovo_db, righe, run,
    somma, totali_scrittura, xml_chiusura,
)

TESTATA = ("Id invio;Matricola dispositivo;Data e ora rilevazione;Data e ora trasmissione;"
           "Ammontare delle vendite (totale in euro);Imponibile vendite (totale in euro);"
           "Imposta vendite (totale in euro);Periodo di inattivita' da;Periodo di inattivita' a\n")


def _riga(invio, giorno_it, ammontare, imposta, matricola=MATRICOLA):
    return (f"'{invio}';'{matricola}';{giorno_it} 21:17:52;{giorno_it} 21:18:28;"
            f"{ammontare};{ammontare};{imposta};;\n")


# 10/09/2026: imponibile 909,09, imposta 90,91 (il «totale» 1.000,00 e' derivato)
CSV_10_09 = TESTATA + _riga(7001, "10/09/2026", "000000000909,09", "000000000090,91")


def test_csv_prima_dell_xml_giornata_provvisoria_senza_quote_ne_scritture(monkeypatch):
    db = nuovo_db("s2_csv")
    imp = Importatore(db, monkeypatch)

    esito = imp.importa("corrispettivi_settembre.csv", CSV_10_09)

    assert esito["workflow"] == "CORRISPETTIVI_CSV_PROVVISORIO" and esito["imported"] == 1
    (corr,) = run(attive(db, "corrispettivi"))
    assert corr["stato"] == "provvisorio" and corr["source"] == "csv_ade"
    # «Ammontare delle vendite» e' l'IMPONIBILE: il lordo e' derivato.
    assert D(corr["totale_imponibile"]) == D("909.09") and D(corr["totale_iva"]) == D("90.91")
    assert D(corr["totale"]) == D("1000.00") and corr["totale_derivato"] is True
    # Contanti e POS sconosciuti: mai ricavati per differenza.
    assert corr["pagato_contanti"] is None and corr["pagato_elettronico"] is None
    # Ne' Prima Nota, ne' giornale.
    assert run(attive(db, "prima_nota_cassa")) == []
    assert run(attive(db, "prima_nota_banca")) == []
    assert run(attive(db, "movimenti_contabili")) == []
    assert "prima_nota_cassa_id" not in corr and not corr.get("registrato_contabilita")


def test_csv_provvisorio_non_entra_nemmeno_nel_giro_del_pregresso(monkeypatch):
    """Il giro che registra i corrispettivi mancanti nel giornale lo salta."""
    db = nuovo_db("s2_pregresso")
    Importatore(db, monkeypatch).importa("c.csv", CSV_10_09)

    esito = run(registra_tutti_corrispettivi(db))

    assert esito["corrispettivi_processati"] == 0
    assert run(attive(db, "movimenti_contabili")) == []


def test_secondo_import_dello_stesso_csv_non_crea_niente(monkeypatch):
    db = nuovo_db("s2_csv_bis")
    imp = Importatore(db, monkeypatch)
    imp.importa("c.csv", CSV_10_09)
    prima = run(istantanea(db))

    secondo = imp.importa("c_copia.csv", CSV_10_09)

    assert secondo["imported"] == 0 and secondo["duplicate"] is True
    assert secondo["data"]["nuovi"] == 0
    assert run(istantanea(db)) == prima


def test_l_xml_promuove_la_riga_provvisoria_e_conserva_il_csv(monkeypatch):
    db = nuovo_db("s2_promozione")
    imp = Importatore(db, monkeypatch)
    imp.importa("c.csv", CSV_10_09)
    (provvisoria,) = run(attive(db, "corrispettivi"))

    esito = imp.importa("2700.xml", xml_chiusura())            # contanti 300 + POS 700

    assert esito["imported"] == 1
    (corr,) = run(attive(db, "corrispettivi"))
    assert corr["id"] == provvisoria["id"]                      # stessa giornata, stessa riga
    assert corr["stato"] == "definitivo_xml" and corr["source"] == "xml"
    # Importi e quote sovrascritti dall'XML.
    assert D(corr["pagato_contanti"]) == D("300.00") and D(corr["pagato_elettronico"]) == D("700.00")
    assert D(corr["totale"]) == D("1000.00") and corr["totale_derivato"] is False
    # Il CSV resta come storico.
    assert corr["csv_ade"]["id_invio"] == "7001"
    assert D(corr["csv_ade"]["ammontare_cents"]) == D("90909")
    # Ora, e solo ora, Prima Nota e giornale: contanti in cassa, giornale quadrato.
    assert [D(r["importo"]) for r in run(attive(db, "prima_nota_cassa"))] == [D("300.00")]
    (s,) = run(attive(db, "movimenti_contabili"))
    dare, avere = totali_scrittura(s)
    assert dare == avere == D("1000.00")
    assert importo_conto(s, "04.01.02", "avere") == D("909.09")


def test_due_invii_csv_dello_stesso_giorno_diventano_due_chiusure_xml(monkeypatch):
    """Due chiusure vere: due righe provvisorie, due XML, due righe definitive. Nessuna
    riga provvisoria resta orfana e i ricavi sono la somma delle due."""
    db = nuovo_db("s2_due_invii")
    imp = Importatore(db, monkeypatch)
    csv = (TESTATA + _riga(7101, "06/09/2026", "000000000543,09", "000000000054,31")
           + _riga(7102, "06/09/2026", "000000001454,09", "000000000145,41"))
    assert imp.importa("c.csv", csv)["imported"] == 2

    imp.importa("2637.xml", xml_chiusura(data="2026-09-06", progressivo="2637", contanti="132.30",
                                         elettronico="465.10", imponibile="543.09", imposta="54.31"))
    imp.importa("2638.xml", xml_chiusura(data="2026-09-06", progressivo="2638", contanti="400.00",
                                         elettronico="1199.50", imponibile="1454.09", imposta="145.41"))

    attivi = run(attive(db, "corrispettivi"))
    assert len(attivi) == 2
    assert {r["stato"] for r in attivi} == {"definitivo_xml"}
    assert somma(r["totale"] for r in attivi) == D("2196.90")
    assert sorted(D(r["pagato_contanti"]) for r in attivi) == [D("132.30"), D("400.00")]
    assert len(run(attive(db, "movimenti_contabili"))) == 2
    assert sorted(D(r["importo"]) for r in run(attive(db, "prima_nota_cassa"))) == [D("132.30"), D("400.00")]


def test_csv_su_giornata_gia_definitiva_non_la_tocca_e_dichiara_la_discordanza(monkeypatch):
    db = nuovo_db("s2_definitiva")
    imp = Importatore(db, monkeypatch)
    imp.importa("2700.xml", xml_chiusura())
    prima = run(istantanea(db))
    (xml_corr,) = run(attive(db, "corrispettivi"))

    # Stesso giorno, imponibile DIVERSO (1.000,00 contro 909,09).
    csv_diverso = TESTATA + _riga(7001, "10/09/2026", "000000001000,00", "000000000100,00")
    esito = imp.importa("c.csv", csv_diverso)

    dati = esito["data"]
    assert dati["nuovi"] == 0 and dati["gia_definitivi"] == 1
    assert dati["discordanze_con_xml"] == [
        {"data": "2026-09-10", "imponibile_xml_cents": 90909, "imponibile_csv_cents": 100000}]
    # Niente e' cambiato: ne' la riga, ne' i registri.
    assert run(istantanea(db)) == prima
    (dopo,) = run(attive(db, "corrispettivi"))
    assert dopo == xml_corr
    assert D(dopo["totale_imponibile"]) == D("909.09") and dopo["stato"] == "definitivo_xml"


def test_csv_uguale_all_xml_non_dichiara_discordanza(monkeypatch):
    db = nuovo_db("s2_uguale")
    imp = Importatore(db, monkeypatch)
    imp.importa("2700.xml", xml_chiusura())

    esito = imp.importa("c.csv", CSV_10_09)

    assert esito["data"]["gia_definitivi"] == 1 and esito["data"]["discordanze_con_xml"] == []


def test_csv_su_riga_manuale_e_un_conflitto_non_una_sovrascrittura(monkeypatch):
    db = nuovo_db("s2_manuale")
    run(db["corrispettivi"].insert_one({
        "id": "m1", "data": "2026-09-10", "stato": "provvisorio", "source": "manuale_serale",
        "totale": 1000.0, "status": "imported"}))
    imp = Importatore(db, monkeypatch)

    esito = imp.importa("c.csv", CSV_10_09)

    assert [c["data"] for c in esito["data"]["conflitti"]] == ["2026-09-10"]
    (corr,) = run(attive(db, "corrispettivi"))
    assert corr["id"] == "m1" and corr["source"] == "manuale_serale"
    assert run(righe(db, "corrispettivi")) == [{k: v for k, v in corr.items()}]


def test_csv_dichiara_il_periodo_di_inattivita_come_chiusura_non_come_mancanza(monkeypatch):
    db = nuovo_db("s2_inattivita")
    imp = Importatore(db, monkeypatch)
    csv = TESTATA + (f"'7201';'{MATRICOLA}';09/03/2026 21:17:52;09/03/2026 21:18:28;"
                     "000000000000,00;000000000000,00;000000000000,00;26/01/2026;08/03/2026\n")

    imp.importa("c.csv", csv)

    from app.services.chiusure_attivita import giorni_chiusi

    chiusi = run(giorni_chiusi(db, "2026-01-20", "2026-03-10"))
    assert "2026-02-14" in chiusi and "2026-01-26" in chiusi and "2026-03-08" in chiusi
    assert "2026-01-25" not in chiusi and "2026-03-09" not in chiusi


def test_csv_con_giornate_di_un_altro_anno_importa_solo_l_anno_attivo(monkeypatch):
    """Dello storico interessano solo cedolini e F24: un corrispettivo di un anno diverso da
    quello attivo non entra, come per l'XML. Il CSV del portale puo' coprire piu' anni."""
    db = nuovo_db("s2_altro_anno")
    imp = Importatore(db, monkeypatch)
    csv = (TESTATA + _riga(7301, "31/12/2025", "000000000500,00", "000000000050,00")
           + _riga(7302, "02/01/2026", "000000000909,09", "000000000090,91"))

    esito = imp.importa("c.csv", csv)

    assert esito["data"]["nuovi"] == 1 and esito["data"]["fuori_anno"] == 1
    assert esito["data"]["anno_attivo"] == 2026
    assert "1 righe di un anno diverso dal 2026" in esito["message"]
    assert [r["data"] for r in run(attive(db, "corrispettivi"))] == ["2026-01-02"]
