"""Fattura estera in PDF (SumUp Limited, Irlanda) caricata da Documenti > Import.

Lo SDI e' solo italiano: SumUp manda la fattura dei lettori come PDF. L'Import
la riconosceva come «fattura» e la leggeva come XML, fallendo. Ora va al
lettore unico delle fatture estere; il lettore di carte e' una piccola
attrezzatura, non una commissione POS.
"""
import asyncio
import base64
import io

from fastapi import UploadFile

from app.routers import documenti
from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services.learning_machine_cdc import classifica_fattura_per_centro_costo

NOME = "SUMUP Fattura ( 1000492833 ).pdf"
PDF = b"%PDF-1.4 fattura sumup"


TESTO_SUMUP = "SumUp Limited Block 8 Harcourt Centre Dublin VAT IE9813461A Fattura 1000492833"


def _importa(monkeypatch, esito, testo=TESTO_SUMUP):
    chiamate = []

    async def scenario():
        db = ClientArchivioMemoria()["fattura_estera_pdf"]
        monkeypatch.setattr(documenti.Database, "get_db", staticmethod(lambda: db))
        monkeypatch.setattr("app.utils.upload_validation.verifica_pdf_reale", lambda *_: None)
        monkeypatch.setattr(documenti, "_pdf_text_for_detection", lambda *_: testo)

        async def lettore(db, pdf_base64, filename, **kwargs):
            chiamate.append((base64.b64decode(pdf_base64), filename, kwargs))
            return esito

        monkeypatch.setattr(
            "app.routers.invoices.fatture_upload.process_fattura_estera_pdf", lettore,
        )
        upload = UploadFile(filename=NOME, file=io.BytesIO(PDF))
        return await documenti.upload_documento_automatico(file=upload)

    return asyncio.run(scenario()), chiamate


def test_il_pdf_della_fattura_va_al_lettore_delle_fatture_estere(monkeypatch):
    risultato, chiamate = _importa(monkeypatch, {
        "status": "imported", "id": "f1", "invoice_number": "1000492833",
        "supplier": "SumUp Limited",
    })
    assert chiamate == [(PDF, NOME, {"source": "documenti_upload_auto"})]
    assert risultato["tipo_rilevato"] == "fattura_estera_pdf"
    assert risultato["imported"] == 1
    assert "1000492833" in risultato["message"]


def test_un_pdf_non_letto_non_e_un_import_riuscito(monkeypatch):
    risultato, _ = _importa(monkeypatch, {"status": "extraction_error", "error": "chiave assente"})
    assert risultato["success"] is False
    assert "chiave assente" in risultato["message"]


def test_il_lettore_sumup_e_una_piccola_attrezzatura_non_una_commissione():
    righe = [{"descrizione": "SumUp Solo", "prezzo_totale": "79.00"}]
    cdc, _, _ = classifica_fattura_per_centro_costo("SumUp Limited", "", righe)
    assert cdc == "5.3_PICCOLE_ATTREZZATURE"

    righe = [{"descrizione": "Lettore di carte SumUp Air"}]
    cdc, _, _ = classifica_fattura_per_centro_costo("SumUp Limited", "", righe)
    assert cdc == "5.3_PICCOLE_ATTREZZATURE"

    # Le commissioni restano commissioni.
    righe = [{"descrizione": "Commissione POS SumUp agosto"}]
    cdc, _, _ = classifica_fattura_per_centro_costo("SumUp Limited", "", righe)
    assert cdc == "11.1_COMMISSIONI_POS"


def test_la_copia_pdf_di_una_fattura_italiana_non_va_all_ai(monkeypatch):
    testo = "Fattura n. 12 Fornitore Srl P.IVA IT01234567890 IBAN IT60X0542811101000000123456"
    risultato, chiamate = _importa(monkeypatch, {"status": "imported"}, testo=testo)
    assert chiamate == []
    assert risultato["success"] is False
    assert "XML" in risultato["message"]


def test_partita_iva_estera_si_riconosce_ma_un_iban_no():
    assert documenti.partita_iva_estera_nel_testo("VAT: IE 9813461A")
    assert documenti.partita_iva_estera_nel_testo("USt-IdNr. DE123456789")
    assert not documenti.partita_iva_estera_nel_testo("IBAN IE29AIBK93115212345678")
    assert not documenti.partita_iva_estera_nel_testo("P.IVA IT01234567890")


def test_dal_pdf_non_si_importa_un_fornitore_italiano(monkeypatch):
    from app.routers.invoices import fatture_upload

    async def estrai(*_a, **_k):
        return {"structured_data": {"success": True, "data": {
            "numero_fattura": "12", "totale": 100.0,
            "fornitore": {"denominazione": "Fornitore Srl", "partita_iva": "IT01234567890"},
        }}}

    monkeypatch.setattr("app.services.document_ai_extractor.process_document_from_base64", estrai)

    async def import_vietato(*_a, **_k):
        raise AssertionError("un fornitore italiano non si importa dal PDF")

    monkeypatch.setattr(fatture_upload, "import_parsed_invoice", import_vietato)
    esito = asyncio.run(fatture_upload.process_fattura_estera_pdf(None, "", "copia.pdf"))
    assert esito["status"] == "fattura_italiana_pdf"


def test_le_righe_lette_dall_ai_arrivano_alla_classificazione_come_testo():
    from app.routers.invoices.fatture_upload import _ai_fattura_a_parsed
    from app.services.eventi_fattura import costruisci_evento_fattura_created

    parsed = _ai_fattura_a_parsed({
        "numero_fattura": "1000492833", "totale": 454.0,
        "fornitore": {"denominazione": "SumUp Limited", "partita_iva": "IE9813461A"},
        "descrizione_righe": ["SumUp Solo", " "],
    })
    # Nessuna riga con importo inventato: magazzino e Lotti non la vedono.
    assert parsed["linee"] == []
    assert parsed["descrizione_righe_ai"] == ["SumUp Solo"]
    evento = costruisci_evento_fattura_created({"id": "f1", "descrizione_righe_ai": ["SumUp Solo"]})
    assert evento["descrizione"] == "SumUp Solo"
    cdc, _, _ = classifica_fattura_per_centro_costo("SumUp Limited", evento["descrizione"], [])
    assert cdc == "5.3_PICCOLE_ATTREZZATURE"
    # Le fatture XML non cambiano: nessuna descrizione in piu'.
    assert costruisci_evento_fattura_created({"id": "f2"})["descrizione"] == ""


RIGHE_SUMUP = [
    "Epson TM-m30III (Wi-Fi/Bluetooth) - Terminal", "Terminal",
    "SumUp Cassa - Cassa Plus", "SumUp Fedeltà",
]


def test_le_righe_vere_della_fattura_sumup_sono_terminali_non_commissioni():
    from app.services.categorizzazione_contabile import categorizza_fattura_completa

    cdc, _, _ = classifica_fattura_per_centro_costo("SumUp Limited", " · ".join(RIGHE_SUMUP), [])
    assert cdc == "5.3_PICCOLE_ATTREZZATURE"
    dettaglio = categorizza_fattura_completa(
        [{"descrizione": d} for d in RIGHE_SUMUP], "SumUp Limited")["dettaglio_linee"]
    assert [r["conto_codice"] for r in dettaglio] == ["05.01.06", "05.01.06", "05.05.02", "05.05.02"]


def test_la_conferma_storna_la_scrittura_su_merci_e_registra_sui_terminali(monkeypatch):
    from app.routers import fatture_estera_verifica as verifica

    db = ClientArchivioMemoria()["verifica_estera"]

    async def scenario():
        await db["invoices"].insert_one({
            "id": "f-sumup", "invoice_number": "1000492833", "invoice_date": "2026-09-22",
            "supplier_name": "SumUp Limited", "supplier_vat": "NL858187498B01",
            "total_amount": 454.0, "imponibile": 454.0, "iva": 0.0, "linee": [],
            "descrizione_righe_ai": RIGHE_SUMUP, "verifica_ai": "in_attesa",
            "status": "imported", "stato_import": "attivo",
        })
        # La scrittura di prima: senza righe XML era finita su Acquisto merci.
        await db["movimenti_contabili"].insert_one({
            "id": "mov-vecchio", "tipo": "fattura_acquisto", "fattura_id": "f-sumup",
            "stato": "registrato", "anno": 2026, "data": "2026-09-22", "numero_registrazione": 1119,
            "idempotency_key": "reg:fattura:f-sumup",
            "righe": [
                {"conto_codice": "05.01.01", "conto_nome": "Acquisto merci", "dare": 454.0, "avere": 0},
                {"conto_codice": "02.01.01", "conto_nome": "Debiti v/fornitori", "dare": 0, "avere": 454.0},
            ],
            "totale_dare": 454.0, "totale_avere": 454.0,
        })
        monkeypatch.setattr(verifica.Database, "get_db", staticmethod(lambda: db))
        esito = await verifica.verifica_fattura("f-sumup", {})
        fattura = await db["invoices"].find_one({"id": "f-sumup"})
        scritture = await db["movimenti_contabili"].find({"fattura_id": "f-sumup"}).to_list(None)
        return esito, fattura, scritture

    esito, fattura, scritture = asyncio.run(scenario())
    assert esito["contabilita"]["giornale"] == "riregistrato", esito
    assert fattura["centro_costo_id"] == "5.3_PICCOLE_ATTREZZATURE"
    vecchia = next(s for s in scritture if s["id"] == "mov-vecchio")
    assert vecchia["stato"] == "stornato"
    valide = [s for s in scritture if s.get("tipo") == "fattura_acquisto" and s.get("stato") != "stornato"]
    assert len(valide) == 1
    dare = {r["conto_codice"]: r["dare"] for r in valide[0]["righe"] if r.get("dare")}
    assert dare == {"05.01.06": 454.0}


def test_il_canone_del_terminale_resta_un_servizio():
    from app.services.categorizzazione_contabile import categorizza_fattura_completa

    dettaglio = categorizza_fattura_completa(
        [{"descrizione": "Canone noleggio terminale POS settembre"}], "Nexi Payments SpA",
    )["dettaglio_linee"]
    assert dettaglio[0]["conto_codice"] != "05.01.06"


def test_la_fattura_in_attesa_si_riallinea_da_sola_e_resta_da_confermare():
    """Importata prima della correzione delle regole, la fattura SumUp era su
    «commissioni POS» e la scrittura su «acquisto merci»: il giro la riallinea
    senza aspettare la conferma, e una seconda passata non tocca niente."""
    from app.routers import fatture_estera_verifica as verifica

    db = ClientArchivioMemoria()["riallinea_estera"]

    async def scenario():
        await db["invoices"].insert_one({
            "id": "f-sumup", "invoice_number": "1000492833", "invoice_date": "2026-09-22",
            "supplier_name": "SumUp Limited", "supplier_vat": "NL858187498B01",
            "total_amount": 454.0, "imponibile": 454.0, "iva": 0.0, "linee": [],
            "descrizione_righe_ai": RIGHE_SUMUP, "verifica_ai": "in_attesa",
            "centro_costo_id": "11.1_COMMISSIONI_POS",
            "status": "imported", "stato_import": "attivo",
        })
        await db["movimenti_contabili"].insert_one({
            "id": "mov-vecchio", "tipo": "fattura_acquisto", "fattura_id": "f-sumup",
            "stato": "registrato", "anno": 2026, "data": "2026-09-22", "numero_registrazione": 1119,
            "idempotency_key": "reg:fattura:f-sumup",
            "righe": [
                {"conto_codice": "05.01.01", "conto_nome": "Acquisto merci", "dare": 454.0, "avere": 0},
                {"conto_codice": "02.01.01", "conto_nome": "Debiti v/fornitori", "dare": 0, "avere": 454.0},
            ],
            "totale_dare": 454.0, "totale_avere": 454.0,
        })
        primo = await verifica.riallinea_fatture_estere_in_attesa(db)
        secondo = await verifica.riallinea_fatture_estere_in_attesa(db)
        fattura = await db["invoices"].find_one({"id": "f-sumup"})
        scritture = await db["movimenti_contabili"].find({"fattura_id": "f-sumup"}).to_list(None)
        return primo, secondo, fattura, scritture

    primo, secondo, fattura, scritture = asyncio.run(scenario())
    assert primo["riregistrate"] == ["f-sumup"] and not primo["errori"]
    assert secondo["riregistrate"] == [] and not secondo["errori"]
    assert fattura["centro_costo_id"] == "5.3_PICCOLE_ATTREZZATURE"
    assert fattura["verifica_ai"] == "in_attesa"
    assert next(s for s in scritture if s["id"] == "mov-vecchio")["stato"] == "stornato"
    valide = [s for s in scritture if s.get("tipo") == "fattura_acquisto" and s.get("stato") != "stornato"]
    assert len(valide) == 1
    assert {r["conto_codice"]: r["dare"] for r in valide[0]["righe"] if r.get("dare")} == {"05.01.06": 454.0}
