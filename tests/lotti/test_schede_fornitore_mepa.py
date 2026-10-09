"""Schede tecniche ME.PA. dalla posta: PDF originale, allergeni, nutrizionali.

Le mail vere (noreply@ordersender.biz, 17/09/2026) hanno l'oggetto «Mepa -
Scheda prodotto cod. articolo IRCA089» e un corpo che Gmail consegna ancora in
quoted-printable (``=0A``, ``=09``, a capo morbidi) con le entità HTML
(``HOPLA&#39;``). La descrizione dopo il codice è identica alla riga della
fattura ME.PA.: è la chiave che lega scheda, fattura, lotto e ricetta.
"""
import asyncio
import io

import pytest
from fastapi import UploadFile
from mongomock_motor import AsyncMongoMockClient

from app.lotti.servizi import articoli_fattura
from app.lotti.servizi.schede_fornitore import (
    completa_allergeni_con_schede,
    estrai_codice_e_descrizione,
    leggi_allergeni,
    leggi_metadati_tecnici,
    leggi_valori_nutrizionali,
    registra_scheda_tecnica,
)


def run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def db():
    articoli_fattura.invalida_cache()
    yield AsyncMongoMockClient()["Lotti_Test"]
    articoli_fattura.invalida_cache()


CORPO_QP = (
    "=0A=0A=09=0A=09=09=\n=0A=09=09Order Sender Enterprise=0A=09=09=09=09"
    "In allegato la scheda tecnica del prodotto IRCA089 - IRCA=\n CACAO 22/24 CF 1 KG (CT 10CF)"
    "=09=09=09=09=0A=09=09=09=09=09Order Sender E=\nnterprise=0A=0A"
)


def test_corpo_quoted_printable_da_la_descrizione_della_fattura():
    ident = estrai_codice_e_descrizione("Mepa - Scheda prodotto cod. articolo IRCA089", CORPO_QP)
    assert ident == {"codice_articolo": "IRCA089", "descrizione": "IRCA CACAO 22/24 CF 1 KG (CT 10CF)"}


def test_entita_html_decodificate_come_in_fattura():
    corpo = ("<td>In allegato la scheda tecnica del prodotto COOP006 - CREMA VEGETALE "
             "ZUCCHERATA HOPLA&#39; CF 1 LT (CT 12CF)</td><td>Order Sender Enterprise</td>")
    ident = estrai_codice_e_descrizione("Mepa - Scheda prodotto cod. articolo COOP006", corpo)
    assert ident["descrizione"] == "CREMA VEGETALE ZUCCHERATA HOPLA' CF 1 LT (CT 12CF)"


def test_senza_corpo_resta_il_codice_senza_descrizione_inventata():
    ident = estrai_codice_e_descrizione("Mepa - Scheda prodotto cod. articolo PREG079", "")
    assert ident == {"codice_articolo": "PREG079", "descrizione": None}


def test_allergeni_tabella_si_no_e_tracce_separate():
    testo = """ALLERGENI
    Cereali contenenti glutine: SI
    Latte e prodotti a base di latte: SI
    Uova e prodotti a base di uova: NO
    Soia: NO
    Può contenere tracce di frutta a guscio e soia."""
    esito = leggi_allergeni(testo)
    assert esito["allergeni"] == ["glutine", "latte"]
    assert "uova" in esito["allergeni_assenti"] and "soia" in esito["allergeni_assenti"]
    assert set(esito["allergeni_tracce"]) == {"soia", "frutta_guscio"}
    assert esito["allergeni_stato"] == "letti"


def test_scheda_senza_allergeni_non_inventa_niente():
    esito = leggi_allergeni("Scheda prodotto. Conservare in luogo fresco e asciutto.")
    assert esito["allergeni"] == [] and esito["allergeni_stato"] == "da_verificare"


def test_x_di_tabella_senza_coordinate_non_diventa_un_allergene_falso():
    testo = """INGREDIENTI (come da Reg. UE n. 1169/2011)
    Farina di frumento, zucchero, uova in polvere, latte scremato in polvere.
    ALLERGENI  Assenza  Presenza certa (tra gli ingredienti)  Presenza possibile di tracce
    Cereali contenenti glutine X
    Crostacei X
    Uova X
    Soia X
    Latte X
    Senape X"""
    esito = leggi_allergeni(testo)
    assert set(esito["allergeni"]) == {"glutine", "uova", "latte"}
    assert "crostacei" not in esito["allergeni"] and "senape" not in esito["allergeni"]
    assert esito["tabella_colonne_da_verificare"] is True
    assert esito["allergeni_stato"] == "da_verificare"


def test_ingredienti_e_tracce_restano_distinti_anche_con_tabella_x_ambigua():
    testo = """Ingredienti: zucchero, armelline (27%), mandorle (25%), acqua.
    Può contenere tracce di altra frutta a guscio e soia.
    ALLERGENI Assenza Presenza certa Presenza possibile di tracce
    Frutta a guscio +
    Soia +"""
    esito = leggi_allergeni(testo)
    assert esito["allergeni"] == ["frutta_guscio"]
    assert esito["allergeni_tracce"] == ["soia"]
    assert esito["allergeni_stato"] == "da_verificare"


def test_valori_nutrizionali_solo_dopo_la_tabella_e_come_stringhe():
    testo = """Ingredienti: zucchero, sale, grassi vegetali.
    VALORI NUTRIZIONALI MEDI per 100 g
    Energia 1650 kJ / 394 kcal
    Grassi 12,5 g
    di cui acidi grassi saturi 7,1 g
    Carboidrati 60 g
    di cui zuccheri 45,2 g
    Proteine 5 g
    Sale 0,30 g"""
    v = leggi_valori_nutrizionali(testo)
    assert v["energia_kj"] == "1650" and v["energia_kcal"] == "394"
    assert v["grassi_g"] == "12.5" and v["grassi_saturi_g"] == "7.1"
    assert v["zuccheri_g"] == "45.2" and v["sale_g"] == "0.30"
    assert v["fibre_g"] is None  # assente = vuoto, mai zero


def test_nessuna_tabella_nessun_valore():
    v = leggi_valori_nutrizionali("Ingredienti: sale 2 g, grassi 3 g")
    assert all(x is None for x in v.values())


def test_metadati_tecnici_solo_da_campi_espliciti():
    testo = """PRE GEL S.P.A.
    Scheda Tecnica UNIVERSAL CAKE
    Rev. 3.1 del 11/09/2024
    INGREDIENTI
    Farina di frumento, zucchero, uova in polvere.
    CONSERVAZIONE - SHELF LIFE
    Conservare nell'imballaggio originale in luogo fresco e asciutto.
    18 mesi dalla data di produzione.
    IMBALLAGGIO - PALLETTIZZAZIONE
    Sacco da 10 kg in cartone."""
    m = leggi_metadati_tecnici(testo)
    assert m["produttore_dichiarato"] == "PRE GEL S.P.A"
    assert "Farina di frumento" in m["composizione_dichiarata"]
    assert "luogo fresco e asciutto" in m["conservazione_dichiarata"]
    assert "Sacco da 10 kg" in m["confezionamento_dichiarato"]
    assert m["revisione_dichiarata"] == "Rev. 3.1 del 11/09/2024"
    assert m["data_documento_dichiarata"] == "11/09/2024"


def test_metadati_assenti_restano_vuoti():
    m = leggi_metadati_tecnici("Descrizione libera priva di campi tecnici")
    assert all(v is None for v in m.values())


def test_energia_pregel_kj_kcal_nello_stesso_valore():
    v = leggi_valori_nutrizionali("""DICHIARAZIONE NUTRIZIONALE (per 100 g)
    ENERGIA GRASSI CARBOIDRATI PROTEINE SALE
    527 / 126 (kJ / kcal)""")
    assert v["energia_kj"] == "527" and v["energia_kcal"] == "126"


def test_registra_idempotente_per_codice_e_conserva_i_pdf(db):
    kw = dict(testo_pdf="Allergeni: latte, uova", oggetto="Mepa - Scheda prodotto cod. articolo PREG079",
              corpo="del prodotto PREG079 - PREGEL UNIVERSAL CAKE CF 10 KG Order Sender Enterprise")
    run(registra_scheda_tecnica(db, documento_id="d1", pdf_sha256="a" * 64, **kw))
    run(registra_scheda_tecnica(db, documento_id="d1", pdf_sha256="a" * 64, **kw))
    esito = run(registra_scheda_tecnica(db, documento_id="d2", pdf_sha256="b" * 64, **kw))
    schede = run(db.schede_tecniche.find({}, {"_id": 0}).to_list(None))
    assert len(schede) == 1
    s = schede[0]
    assert s["prodotto_key"] == "pregel universal cake cf 10 kg"
    assert s["codice_articolo"] == "PREG079" and s["url"] == "/lotti/api/schede-tecniche/pdf/d2"
    assert [r["sha256"] for r in s["pdf_ricevuti"]] == ["a" * 64, "b" * 64]
    assert sorted(s["allergeni"]) == ["latte", "uova"] and esito["registrata"] is True


def _info_vuota():
    return {"allergeni_presenti": [], "allergeni_dettaglio": {}, "testo_etichetta": "Non contiene allergeni dichiarati",
            "contiene_allergeni": False}


def test_etichetta_prende_gli_allergeni_dalla_scheda_solo_con_conferma(db):
    run(registra_scheda_tecnica(
        db, documento_id="d1", pdf_sha256="a" * 64, testo_pdf="Allergeni: latte, uova",
        oggetto="cod. articolo PREG079",
        corpo="del prodotto PREG079 - PREGEL UNIVERSAL CAKE CF 10 KG Order Sender"))
    run(db.nome_mapping.insert_one({"descrizione_key": "pregel universal cake cf 10 kg",
                                    "nome_canc": "Preparato torta", "confermato": False, "fonte": "web",
                                    "ingredienti_ricetta": ["preparato torta"]}))
    # proposta non confermata: il nome «preparato torta» non porta allergeni
    info = run(completa_allergeni_con_schede(db, ["preparato torta"], _info_vuota()))
    assert info["allergeni_presenti"] == []

    run(db.nome_mapping.update_one({"descrizione_key": "pregel universal cake cf 10 kg"},
                                   {"$set": {"confermato": True}}))
    articoli_fattura.invalida_cache()
    info = run(completa_allergeni_con_schede(db, ["preparato torta"], _info_vuota()))
    assert sorted(info["allergeni_presenti"]) == ["latte", "uova"]
    assert info["allergeni_dettaglio"]["latte"]["schede"] == ["PREGEL UNIVERSAL CAKE CF 10 KG"]
    assert info["testo_etichetta"].startswith("Contiene:")


def test_lotto_consumato_con_la_stessa_descrizione_aggancia_la_scheda(db):
    run(registra_scheda_tecnica(
        db, documento_id="d1", pdf_sha256="a" * 64, testo_pdf="Allergeni: latte",
        oggetto="cod. articolo BADA001",
        corpo="del prodotto BADA001 - WHITE CREAM RICOTTA CONGELATA CF 6 KG Order Sender"))
    info = run(completa_allergeni_con_schede(db, ["WHITE CREAM RICOTTA CONGELATA CF 6 KG"], _info_vuota()))
    assert info["allergeni_presenti"] == ["latte"]


def test_ricetta_apre_lo_stesso_originale_da_mapping_confermato(db, monkeypatch):
    from app.lotti.routers import schede_tecniche as router

    monkeypatch.setattr(router, "db", db)
    run(registra_scheda_tecnica(
        db, documento_id="doc-strutto", pdf_sha256="c" * 64,
        testo_pdf="Ingredienti\nGrasso animale.\nAllergeni: nessuno",
        oggetto="cod. articolo MIO002",
        corpo="del prodotto MIO002 - MIO STRUTTO 15 KG Order Sender",
        drive_file_id="DRV-STRUTTO"))
    run(db.nome_mapping.insert_one({
        "descrizione_key": "mio strutto 15 kg", "nome_canc": "Strutto",
        "confermato": True, "alimentare": True, "ingredienti_ricetta": ["strutto"],
    }))
    articoli_fattura.invalida_cache()
    esito = run(router.risolvi_scheda("strutto"))
    assert esito["fonte"] == "mapping_confermato"
    assert esito["scheda"]["documento_id"] == "doc-strutto"
    assert esito["scheda"]["url"] == "/lotti/api/schede-tecniche/pdf/doc-strutto"


def test_guasto_delle_schede_non_blocca_la_produzione():
    class Rotto:
        def __getattr__(self, _):
            raise RuntimeError("archivio giù")

    info = _info_vuota()
    assert run(completa_allergeni_con_schede(Rotto(), ["farina"], info)) == info


def test_la_mail_di_order_sender_arriva_alla_scheda_non_ai_filtri_amministrativi(db, monkeypatch):
    """Dal mittente autorizzato: PDF archiviato (SHA-256) e scheda registrata in Lotti."""
    from email.mime.application import MIMEApplication
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    import app.lotti.db as lotti_db
    from app.services import email_full_download as efd

    erp = AsyncMongoMockClient()["Erp_Test"]
    run(erp.mittenti_email.insert_one({"pattern": "noreply@ordersender.biz", "canale": "gmail",
                                       "tipo_documento": "scheda_tecnica", "attivo": True}))
    monkeypatch.setattr(lotti_db, "database", db, raising=False)
    monkeypatch.setattr("app.services.pdf_text_extraction.extract_pdf_text",
                        lambda _b: "ALLERGENI\nLatte e derivati: SI\n")

    msg = MIMEMultipart()
    msg["From"] = "Order Sender <noreply@ordersender.biz>"
    msg["Subject"] = "Mepa - Scheda prodotto cod. articolo BADA001"
    msg.attach(MIMEText("In allegato la scheda tecnica del prodotto BADA001 - WHITE CREAM RICOTTA "
                        "CONGELATA CF 6 KG Order Sender Enterprise"))
    pdf = MIMEApplication(b"%PDF-1.4 " + b"x" * 800, _subtype="octet-stream")
    pdf.add_header("Content-Disposition", "attachment", filename="Scheda_prodotto_BADA001.pdf")
    msg.attach(pdf)

    downloader = efd.EmailFullDownloader(erp)
    assert run(downloader.process_email(b"42", msg, "INBOX")) == 1
    archiviati = run(erp.schede_tecniche_email_attachments.find({}, {"_id": 0}).to_list(None))
    assert len(archiviati) == 1 and archiviati[0]["category"] == "scheda_tecnica"
    scheda = run(db.schede_tecniche.find_one({}, {"_id": 0}))
    assert scheda["prodotto_key"] == "white cream ricotta congelata cf 6 kg"
    assert scheda["allergeni"] == ["latte"]
    assert scheda["documento_id"] == archiviati[0]["id"]
    import hashlib
    assert scheda["pdf_sha256"] == hashlib.sha256(b"%PDF-1.4 " + b"x" * 800).hexdigest()
    # stessa mail al giro dopo: nessun secondo PDF, nessuna seconda scheda
    assert run(efd.EmailFullDownloader(erp).process_email(b"42", msg, "INBOX")) == 0
    assert run(db.schede_tecniche.count_documents({})) == 1


def test_link_manuale_ed_eliminazione_non_toccano_l_originale_del_fornitore(db, monkeypatch):
    from app.lotti.routers import schede_tecniche as router

    monkeypatch.setattr(router, "db", db)
    run(registra_scheda_tecnica(
        db, documento_id="d1", pdf_sha256="a" * 64, testo_pdf="Allergeni: latte",
        oggetto="cod. articolo BADA001",
        corpo="del prodotto BADA001 - WHITE CREAM RICOTTA CONGELATA CF 6 KG Order Sender"))
    chiave = "white cream ricotta congelata cf 6 kg"
    run(router.salva_scheda({"prodotto_key": chiave, "url": "https://produttore.it/scheda.pdf"}))
    assert run(db.schede_tecniche.count_documents({"prodotto_key": chiave})) == 2
    originale = run(db.schede_tecniche.find_one({"fonte": "email_fornitore"}, {"_id": 0}))
    assert originale["url"] == "/lotti/api/schede-tecniche/pdf/d1"

    run(router.elimina_scheda(prodotto_key=chiave, tipo="tecnica", _admin=None))
    run(router.elimina_scheda(prodotto_key=chiave, tipo="tecnica", _admin=None))
    rimaste = run(db.schede_tecniche.find({"prodotto_key": chiave}, {"_id": 0}).to_list(None))
    assert [s["fonte"] for s in rimaste] == ["email_fornitore"]


def test_elenco_aggancia_la_scheda_al_prodotto_per_nome_di_fattura(db, monkeypatch):
    from app.lotti.routers import schede_tecniche as router

    monkeypatch.setattr(router, "db", db)
    run(db.dizionario_prodotti.insert_one({"id": "p1", "nome_normalizzato": "ricotta white cream",
                                           "nome_originale": "WHITE CREAM RICOTTA CONGELATA CF 6 KG",
                                           "fornitore": "ME.PA. ALIMENTARI S.R.L."}))
    run(registra_scheda_tecnica(
        db, documento_id="d1", pdf_sha256="a" * 64, testo_pdf="Allergeni: latte",
        oggetto="cod. articolo BADA001",
        corpo="del prodotto BADA001 - WHITE CREAM RICOTTA CONGELATA CF 6 KG Order Sender"))
    esito = run(router.lista_prodotti_con_schede(solo_senza=False, q=None, limit=500,
                                                 includi_non_alimentari=False))
    assert esito["totale"] == 1
    riga = esito["prodotti"][0]
    assert riga["ha_scheda"] and riga["schede"][0]["allergeni"] == ["latte"]


def test_ricostruzione_rilegge_i_pdf_archiviati_senza_duplicare(db, monkeypatch):
    import base64

    from app.database import Database
    from app.lotti.routers import schede_tecniche as router

    erp = AsyncMongoMockClient()["Erp_Test"]
    run(erp.schede_tecniche_email_attachments.insert_one({
        "id": "d1", "pdf_data": base64.b64encode(b"%PDF finto").decode(),
        "email_subject": "Mepa - Scheda prodotto cod. articolo BADA001",
        "email_body": "del prodotto BADA001 - WHITE CREAM RICOTTA CONGELATA CF 6 KG Order Sender"}))
    monkeypatch.setattr(router, "db", db)
    monkeypatch.setattr(Database, "get_db", classmethod(lambda cls: erp))
    monkeypatch.setattr("app.services.pdf_text_extraction.extract_pdf_text", lambda _b: "Allergeni: latte")
    for _ in range(2):
        esito = run(router._ricostruisci_schede(500))
        assert esito["lette"] == 1 and esito["registrate"] == 1 and esito["errori"] == []
    assert run(db.schede_tecniche.count_documents({})) == 1


def test_anteprima_multipla_conta_due_mio002_come_un_originale(db, monkeypatch):
    from app.lotti.routers import schede_tecniche as router

    monkeypatch.setattr(router, "db", db)
    monkeypatch.setattr("app.services.pdf_text_extraction.extract_pdf_text", lambda _b: "Scheda tecnica\nGRANELLA DI ZUCCHERO")
    contenuto = b"%PDF-1.4 stessa scheda"
    files = [
        UploadFile(filename="Scheda_prodotto_MIO002_20260917131156.pdf", file=io.BytesIO(contenuto)),
        UploadFile(filename="Scheda_prodotto_MIO002_20260917131156 (1).pdf", file=io.BytesIO(contenuto)),
    ]
    esito = run(router.anteprima_import_schede(files=files, _admin=None))
    assert esito["files_ricevuti"] == 2 and esito["originali_unici"] == 1
    assert esito["schede"][0]["duplicato_nel_lotto"] is False
    assert esito["schede"][1]["duplicato_nel_lotto"] is True
    assert esito["schede"][0]["sha256"] == esito["schede"][1]["sha256"]


def test_conferma_multipla_riusa_documento_e_drive_per_sha256(db, monkeypatch):
    from app.database import Database
    from app.lotti.routers import schede_tecniche as router

    erp = AsyncMongoMockClient()["Erp_Test"]
    monkeypatch.setattr(router, "db", db)
    monkeypatch.setattr(Database, "get_db", classmethod(lambda cls: erp))
    monkeypatch.setattr("app.services.pdf_text_extraction.extract_pdf_text", lambda _b: "Scheda tecnica\nPRODOTTO SENZA MATCH")
    chiamate = []

    def archivia(doc, tipo):
        chiamate.append((doc, tipo))
        return {"status": "archived", "drive_file_id": "DRV-1", "sha256": __import__("hashlib").sha256(doc["content"]).hexdigest()}

    monkeypatch.setattr("app.services.email_drive_archive.archive_document_copy", archivia)
    contenuto = b"%PDF-1.4 stessa scheda"
    preview_files = [UploadFile(filename=f"Scheda_prodotto_MIO002_20260917131156{suffix}.pdf", file=io.BytesIO(contenuto))
                     for suffix in ("", " (1)")]
    preview = run(router.anteprima_import_schede(files=preview_files, _admin=None))
    confirm_files = [UploadFile(filename=f"Scheda_prodotto_MIO002_20260917131156{suffix}.pdf", file=io.BytesIO(contenuto))
                     for suffix in ("", " (1)")]
    esito = run(router.conferma_import_schede(
        files=confirm_files,
        preview_tokens=[r["preview_token"] for r in preview["schede"]],
        associazioni_confermate=["", ""],
        _admin=None,
    ))
    assert esito["ricevuti"] == 2 and esito["nuovi_originali"] == 1
    assert len(chiamate) == 1
    assert esito["risultati"][0]["documento_id"] == esito["risultati"][1]["documento_id"]
    assert run(erp.schede_tecniche_email_attachments.count_documents({})) == 1


def test_conferma_multipart_accetta_lista_associazioni_da_browser(db, monkeypatch):
    """La richiesta multipart reale deve legare i campi ripetuti a ``list[str]``."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.database import Database
    from app.lotti.routers import schede_tecniche as router

    erp = AsyncMongoMockClient()["Erp_Test"]
    run(db.dizionario_prodotti.insert_one({
        "id": "p-browser", "nome_originale": "MIO STRUTTO 15 KG",
        "nome_normalizzato": "Mio Strutto 15 kg",
    }))
    monkeypatch.setattr(router, "db", db)
    monkeypatch.setattr(Database, "get_db", classmethod(lambda cls: erp))
    monkeypatch.setattr(
        "app.services.pdf_text_extraction.extract_pdf_text",
        lambda _b: "Scheda tecnica\nPRODOTTO",
    )
    monkeypatch.setattr(
        "app.services.email_drive_archive.archive_document_copy",
        lambda _doc, _tipo: {"status": "archived", "drive_file_id": "DRV-BROWSER"},
    )
    contenuto = b"%PDF-1.4 scheda multipart browser"
    preview = run(router.anteprima_import_schede(
        files=[UploadFile(filename="Scheda_prodotto_MIO002_20260917.pdf", file=io.BytesIO(contenuto))],
        _admin=None,
    ))

    app = FastAPI()
    app.include_router(router.router, prefix="/lotti/api")
    app.dependency_overrides[router.require_admin] = lambda: {"role": "admin"}
    response = TestClient(app).post(
        "/lotti/api/schede-tecniche/importa/conferma",
        files=[("files", ("Scheda_prodotto_MIO002_20260917.pdf", contenuto, "application/pdf"))],
        data={
            "preview_tokens": [preview["schede"][0]["preview_token"]],
            "associazioni_confermate": ["MIO STRUTTO 15 KG"],
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["risultati"][0]["associazione"]["stato"] == "confermata_titolare"


def test_correzione_associazione_accetta_solo_nome_esatto_esistente(db, monkeypatch):
    from app.database import Database
    from app.lotti.routers import schede_tecniche as router

    erp = AsyncMongoMockClient()["Erp_Test"]
    run(db.dizionario_prodotti.insert_one({
        "id": "p1", "nome_originale": "MIO STRUTTO 15 KG", "nome_normalizzato": "Mio Strutto 15 kg",
    }))
    monkeypatch.setattr(router, "db", db)
    monkeypatch.setattr(Database, "get_db", classmethod(lambda cls: erp))
    monkeypatch.setattr("app.services.pdf_text_extraction.extract_pdf_text", lambda _b: "Scheda tecnica\nPRODOTTO")
    monkeypatch.setattr("app.services.email_drive_archive.archive_document_copy", lambda _doc, _tipo: {
        "status": "archived", "drive_file_id": "DRV-MIO",
    })
    contenuto = b"%PDF-1.4 scheda strutto"
    preview = run(router.anteprima_import_schede(
        files=[UploadFile(filename="Scheda_prodotto_MIO002_20260917.pdf", file=io.BytesIO(contenuto))],
        _admin=None,
    ))
    esito = run(router.conferma_import_schede(
        files=[UploadFile(filename="Scheda_prodotto_MIO002_20260917.pdf", file=io.BytesIO(contenuto))],
        preview_tokens=[preview["schede"][0]["preview_token"]],
        associazioni_confermate=["MIO STRUTTO 15 KG"],
        _admin=None,
    ))
    assert esito["risultati"][0]["associazione"]["stato"] == "confermata_titolare"
    salvata = run(db.schede_tecniche.find_one({}, {"_id": 0}))
    assert salvata["nome_prodotto"] == "MIO STRUTTO 15 KG"


def test_correzione_associazione_rifiuta_nome_non_esistente(db, monkeypatch):
    from app.lotti.routers import schede_tecniche as router

    monkeypatch.setattr(router, "db", db)
    with pytest.raises(Exception) as exc:
        run(router._conferma_associazione_esatta("PRODOTTO INVENTATO"))
    assert getattr(exc.value, "status_code", None) == 409
