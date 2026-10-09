import asyncio
import base64

from app.services import notifiche_pec_verbali as mod
from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services.verbali_pdf_service import collect_verbale_pdfs

OGGETTO = (
    "POSTA CERTIFICATA: Notifica di atto amministrativo relativo ad\r\n una sanzione "
    "amministrativa prevista dal codice della strada Atto\r\n 20240160976 del 15/03/2024 [upec7468533]"
)
MITTENTE = '"Per conto di: notifica.pl.napoli@pec.it" <posta-certificata@pec.aruba.it>'
DATA = "Thu, 18 Apr 2024 17:22:30 +0200"
TESTO = ("Verbale n. A24110662140 - cronologico Registro n. 20240160976 data verbale 15/03/2024 "
         "In data 15/03/2024 ... targato GG782PN")


def _run(coro):
    return asyncio.run(coro)


def test_metadati_e_scadenze_dalla_data_della_pec():
    meta = mod.metadati_notifica(OGGETTO, MITTENTE, DATA)
    assert meta["upec_id"] == "7468533"
    assert meta["numero_registro"] == "20240160976"
    assert meta["ente_mittente"] == "notifica.pl.napoli@pec.it"
    assert meta["data_notifica"] == "2024-04-18"
    assert mod.scadenze_da_notifica(meta["data_notifica"]) == {
        "pagamento_ridotto": "2024-04-23",
        "ricorso_giudice_di_pace": "2024-05-18",
        "ricorso_prefetto": "2024-06-17",
    }
    assert mod.scadenze_da_notifica(None) == {}
    assert mod.metadati_notifica(OGGETTO, MITTENTE, "boh")["data_notifica"] is None


def test_numero_verbale_letto_dalla_copia_conforme():
    letto = mod.numero_da_copia_conforme(TESTO)
    assert letto == {"numero_verbale": "A24110662140", "numero_registro": "20240160976",
                     "data_verbale": "15/03/2024"}
    assert mod.numero_da_copia_conforme("nessun verbale")["numero_verbale"] is None


def _db_con_pec(numero_verbale_reale=True):
    db = ClientArchivioMemoria()["notifiche-pec"]
    contenuto = base64.b64encode(b"%PDF-finto").decode()

    async def prepara():
        await db["verbali_email_attachments"].insert_one({
            "id": "att1", "filename": "COPIACONFORMEPEC_7468533.pdf", "pdf_hash": "h1",
            "pdf_data": contenuto, "email_subject": OGGETTO, "email_from": MITTENTE, "email_date": DATA})
        await db["verbali_email_attachments"].insert_one({
            "id": "att2", "filename": "RELATAPEC_7468533.pdf", "pdf_hash": "h2",
            "pdf_data": contenuto, "email_subject": OGGETTO, "email_from": MITTENTE, "email_date": DATA})
        # riga nata dalla sola PEC: non e' il verbale
        await db["verbali_noleggio"].insert_one(
            {"id": "orfano", "numero_verbale": "A24110662140", "source": "gmail_scan", "stato": "salvato"})
        if numero_verbale_reale:
            await db["verbali_noleggio"].insert_one(
                {"id": "v1", "numero_verbale": "A24110662140", "targa": "GG782PN", "source": "documenti_upload_auto"})

    _run(prepara())
    return db


def test_aggancia_al_verbale_vero_e_non_duplica(monkeypatch):
    monkeypatch.setattr("app.services.verbali_document_import._extract_text", lambda _c: TESTO)
    db = _db_con_pec()

    anteprima = _run(mod.aggancia_notifiche_pec(db, dry_run=True))
    assert anteprima["agganciate"] == 1
    assert _run(db["verbali_noleggio"].find_one({"id": "v1"})).get("notifiche_pec") is None

    primo = _run(mod.aggancia_notifiche_pec(db, dry_run=False))
    assert primo["agganciate"] == 1 and primo["da_agganciare"] == 0
    verbale = _run(db["verbali_noleggio"].find_one({"id": "v1"}))
    assert verbale["data_notifica"] == "2024-04-18"
    assert verbale["scadenze_ricorso"]["ricorso_prefetto"] == "2024-06-17"
    assert [a["id"] for a in verbale["notifiche_pec"][0]["allegati"]] == ["att1", "att2"]

    secondo = _run(mod.aggancia_notifiche_pec(db, dry_run=False))
    assert secondo["agganciate"] == 0 and secondo["gia_agganciate"] == 1
    assert len(_run(db["verbali_noleggio"].find_one({"id": "v1"}))["notifiche_pec"]) == 1

    # gli allegati compaiono nel fascicolo del verbale
    pdfs = _run(collect_verbale_pdfs(db, verbale, include_content=False))
    assert [p["filename"] for p in pdfs if p["tipo"] == "notifica_pec"] == [
        "COPIACONFORMEPEC_7468533.pdf", "RELATAPEC_7468533.pdf"]


def test_senza_verbale_resta_da_agganciare_e_non_ne_crea(monkeypatch):
    monkeypatch.setattr("app.services.verbali_document_import._extract_text", lambda _c: TESTO)
    db = _db_con_pec(numero_verbale_reale=False)
    esito = _run(mod.aggancia_notifiche_pec(db, dry_run=False))
    assert esito["da_agganciare"] == 1 and esito["agganciate"] == 0
    assert esito["elenco_da_agganciare"] == [
        {"upec_id": "7468533", "numero_verbale": "A24110662140", "motivo": "senza_verbale"}]
    assert esito["senza_verbale"] == 1 and esito["ambigue"] == 0
    att = _run(db["verbali_email_attachments"].find_one({"id": "att1"}))
    assert att["notifica_stato"] == "da_agganciare" and att["numero_verbale_letto"] == "A24110662140"
    assert len(_run(db["verbali_noleggio"].find({}).to_list(10))) == 1
