import asyncio
import io
from pathlib import Path

import fitz
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from app.routers import documenti
from tests.document_preview_helpers import confirmed_preview_headers
from app.services.inps_adjustment_parser import parse_nota_rettifica_inps
from app.services.pagopa_receipts import import_receipt, parse_receipt_pdf
from app.services.f24_parser import parse_quietanza_f24
from app.services.parser_f24 import (
    _codice_regione_da_riga,
    _dati_anagrafici_da_coordinate,
    _importo_da_token,
    parse_f24_commercialista,
)


def _pdf(*lines: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    y = 50
    for line in lines:
        page.insert_text((40, y), line, fontsize=10)
        y += 22
    content = doc.tobytes()
    doc.close()
    return content


def test_importi_f24_separati_in_caselle_restano_al_centesimo():
    assert _importo_da_token([(460, "123")]) == 1.23
    assert _importo_da_token([(460, "1234")]) == 12.34
    assert _importo_da_token([(460, "98"), (474, "63")]) == 98.63
    assert _importo_da_token([(355, "3.575"), (391, "00")]) == 3575.0
    assert _importo_da_token([(530, "6.469"), (557, ","), (561, "23")]) == 6469.23


def test_protocollo_ae_ricostruisce_numero_modello_senza_slash_nel_testo():
    content = _pdf(
        "QUIETANZA RICEVUTA DI VERSAMENTO F24",
        "PROTOCOLLO TELEMATICO", "26072135472143961 000001 00,286",
        "Saldo delega 286,00", "ERARIO 1040 06 2026 284,00 0,00",
        "ERARIO 8948 06 2026 2,00 0,00",
    )
    parsed = parse_quietanza_f24(pdf_content=content)
    assert parsed["dati_generali"]["protocollo_telematico"] == "26072135472143961/000001"
    assert parsed["dati_generali"]["numero_modello"] == "000001"


def test_codice_fiscale_non_include_le_lettere_dell_etichetta_frammentata():
    doc = fitz.open()
    page = doc.new_page()
    x = 40
    for token in ("C", "O", "D", "ICE", "FIS", "C", "A", "LE"):
        page.insert_text((x, 110), token, fontsize=7)
        x += 9
    for index, char in enumerate("04523831214"):
        page.insert_text((126 + index * 14, 109), char, fontsize=7)

    assert _dati_anagrafici_da_coordinate(doc)["codice_fiscale"] == "04523831214"
    doc.close()


def test_regione_non_si_perde_per_testo_marginale_e_ravvedimento_e_di_delega():
    row = [
        {"x": 20, "word": "31"}, {"x": 38, "word": "0"},
        {"x": 50, "word": "5"}, {"x": 179, "word": "1993"},
    ]
    assert _codice_regione_da_riga(row) == "05"

    doc = fitz.open()
    page = doc.new_page()
    for x, text in ((38, "0"), (50, "5"), (179, "1993"), (285, "2024"), (373, "28"), (391, "61")):
        page.insert_text((x, 200), text, fontsize=7)
    page.insert_text((250, 240), "SALDO FINALE", fontsize=7)
    page.insert_text((530, 240), "28", fontsize=7)
    page.insert_text((560, 240), "61", fontsize=7)
    content = doc.tobytes()
    doc.close()

    parsed = parse_f24_commercialista(pdf_content=content)
    assert parsed["sezione_regioni"][0]["codice_regione"] == "05"
    assert parsed["sezione_regioni"][0]["importo_debito"] == 28.61
    assert parsed["has_ravvedimento"] is True
    assert parsed["codici_ravvedimento"] == ["1993"]


def test_f24_multipagina_quadra_ogni_modello_e_registra_pagina_bianca():
    doc = fitz.open()
    for model_number, code, amount in ((1, "1040", "210"), (2, "2002", "3.574")):
        page = doc.new_page()
        page.insert_text((40, 40), "CERALDI GROUP S.R.L. - STAMPA DI PROVA", fontsize=7)
        page.insert_text((40, 55), f"MOD NUM: {model_number}", fontsize=7)
        for x, text in ((120, code), (220, "2024"), (350, amount), (391, "00")):
            page.insert_text((x, 180), text, fontsize=7)
        page.insert_text((250, 240), "SALDO FINALE", fontsize=7)
        page.insert_text((530, 240), amount, fontsize=7)
        page.insert_text((570, 240), "00", fontsize=7)
        if model_number == 1:
            doc.new_page()
    content = doc.tobytes()
    doc.close()

    parsed = parse_f24_commercialista(pdf_content=content)

    assert parsed["dati_generali"]["natura_documento"] == "F24_STAMPA_DI_PROVA"
    assert parsed["dati_generali"]["numero_modelli"] == 2
    assert parsed["totali"]["saldo_delega"] == 3784.0
    assert parsed["validazione"]["saldo_quadrato"] is True
    assert parsed["validazione"]["modelli_quadrati"] is True
    assert parsed["validazione"]["pagine_bianche"] == [2]
    assert [item["saldo_quadrato"] for item in parsed["modelli"]] == [True, True]
    assert [item["numero_modello"] for item in parsed["modelli"]] == [1, 2]
    rows = parsed["sezione_erario"]
    assert [(row["codice_tributo"], row["pagina"], row["numero_modello"]) for row in rows] == [
        ("1040", 1, 1), ("2002", 3, 2),
    ]


def test_classificatore_separa_rettifica_avviso_e_ricevuta():
    rettifica = _pdf(
        "INPS - NOTA DI RETTIFICA", "MODELLO DMRA", "Il pagamento avviene con modello F24",
    )
    avviso = _pdf(
        "ENTE CREDITORE - AVVISO DI PAGAMENTO", "QUANTO E QUANDO PAGARE?",
        "Codice Avviso 302000600008408304", "RATA UNICA ENTRO IL 11/04/2026",
    )
    ricevuta = _pdf(
        "ATTESTAZIONE DI PAGAMENTO", "ESITO : Pagamento eseguito",
        "IMPORTO TOTALE PAGATO : 34,90 EUR", "ID UNIVOCO VERSAMENTO : 02000600008408304",
        "DATA RICEVUTA : 18/03/2026 00:31:32",
    )

    assert documenti.detect_document_type("StampaSintesiRettifica_2.pdf", rettifica) == "nota_rettifica_inps"
    assert documenti.detect_document_type("AvvisoDigitale.pdf", avviso) == "avviso_pagopa"
    assert documenti.detect_document_type("RicevutaTelematica.pdf", ricevuta) == "ricevuta_pagopa"
    parsed = parse_receipt_pdf(ricevuta)
    assert parsed["is_payment_receipt"] is True
    assert parsed["importo"] == 34.90
    assert parsed["data_pagamento"] == "2026-03-18"


def test_classificatore_f24_non_dipende_dal_nome_e_normalizza_grafica_spezzata():
    content = _pdf(
        "DELEG A IRREVO CABILE",
        "COD ICE FISCALE 04523831214",
        "SEZIONE ERARIO CODICE TRIBUTO 3918",
        "SALD O FINALE 3.575,00",
    )
    assert documenti.detect_document_type("documento_generico.pdf", content) == "f24"


def test_campioni_f24_reali_esercitano_imu_irap_centesimi_e_provenienza():
    base = Path(r"C:\Users\ceral\Downloads\Dati applicazione\Dati app\f 24\f24 commercialista")
    imu_path = base / "IMU CERALDI GROUP.pdf"
    irap_path = base / "RAVV II ACC IRAP CERALDI.PDF"
    if not imu_path.exists() or not irap_path.exists():
        return
    imu = parse_f24_commercialista(pdf_content=imu_path.read_bytes())
    irap = parse_f24_commercialista(pdf_content=irap_path.read_bytes())
    assert documenti.detect_document_type(imu_path.name, imu_path.read_bytes()) == "f24"
    assert documenti.detect_document_type(irap_path.name, irap_path.read_bytes()) == "f24"
    row = imu["sezione_imu"][0]
    assert row["importo_debito_cents"] == 357500
    assert row["codice_comune"] == "F839"
    assert row["numero_immobili"] == 1
    assert row["has_ravvedimento"] is True
    assert row["field_evidence"]["confidence"] == 1.0
    assert imu["dati_generali"]["taxpayer_id"] == "04523831214"
    assert imu["dati_generali"]["intermediary_id"] is None
    assert imu["dati_generali"]["identita_stato"] == "VERIFICATA"
    assert irap["totali"]["saldo_netto_cents"] == 173636
    assert irap["validazione"]["quadrature_sezioni"]["sezione_regioni"]["net_cents"] == 173636


def test_data_modello_f24_e_data_pagamento_restano_eventi_distinti():
    content = _pdf(
        "CERALDI GROUP S.R.L. STAMPA DI PROVA",
        "Azienda Scadenza 16/05/2026",
        "SALDO FINALE 200,00",
    )
    parsed = parse_f24_commercialista(pdf_content=content)
    assert parsed["dati_generali"]["data_stampa"] == "2026-05-16"
    assert parsed["dati_generali"]["data_versamento_provenienza"] == "MODELLO_NON_PAGAMENTO"


def test_caso_reale_1040_giugno_2026_quietanza_21_luglio():
    path = Path(
        r"C:\Users\ceral\Downloads\CERALDI_GROUP_FISCALE_CODEX_COMPLETO_2020_2026_V2"
        r"\CERALDI_GROUP_FISCALE_CODEX_COMPLETO_2020_2026_V2\02_F24_QUIETANZE\2026"
        r"\2026-07-21__F24_021__quietanza_AE__prot_26072135472143961-000001.pdf"
    )
    if not path.exists():
        return
    parsed = parse_quietanza_f24(pdf_content=path.read_bytes())
    assert parsed["dati_generali"]["data_pagamento"] == "2026-07-21"
    row = next(
        row for row in parsed["sezione_erario"]
        if row.get("codice_tributo") == "1040"
    )
    assert row["periodo_riferimento"] == "06/2026"
    assert row["importo_debito"] == 284.0
    assert parsed["totali"]["saldo_netto"] == 286.0


def test_upload_auto_campioni_reali_imu_e_avviso_solo_su_database_di_test(monkeypatch):
    base = Path(r"C:\Users\ceral\Downloads\Dati applicazione\Dati app\f 24\f24 commercialista")
    imu_path = base / "IMU CERALDI GROUP.pdf"
    avviso_path = Path(r"C:\Users\ceral\Downloads\AvvisoDigitale_302000600008408304.pdf")
    if not imu_path.exists() or not avviso_path.exists():
        return
    db = AsyncMongoMockClient()["upload-auto-real-fixtures"]
    monkeypatch.setattr(documenti.Database, "get_db", staticmethod(lambda: db))
    app = FastAPI()
    app.include_router(documenti.router, prefix="/api/documenti")
    with TestClient(app) as client:
        imu = imu_path.read_bytes()
        first = client.post(
            "/api/documenti/upload-auto",
            files={"file": (imu_path.name, imu, "application/pdf")},
            headers=confirmed_preview_headers(imu, "f24"),
        )
        avviso = avviso_path.read_bytes()
        second = client.post(
            "/api/documenti/upload-auto",
            files={"file": (avviso_path.name, avviso, "application/pdf")},
            headers=confirmed_preview_headers(avviso, "avviso_pagopa"),
        )
    assert first.status_code == second.status_code == 200
    assert first.json()["tipo_rilevato"] == "f24"
    assert first.json()["data"]["validazione"]["saldo_quadrato"] is True
    assert second.json()["tipo_rilevato"] == "avviso_pagopa"
    assert second.json()["payment_evidence"] is False
    assert second.json()["association"]["status"] == "linked"
    verbale = asyncio.run(db["verbali_noleggio"].find_one({}, {"_id": 0}))
    assert verbale["ente_creditore"] == "COMUNE DI NAPOLI"
    assert verbale["stato_pratica"] == "DA_ACQUISIRE_VERBALE"


def test_upload_auto_avviso_non_crea_ricevuta_o_pagamento(monkeypatch):
    db = AsyncMongoMockClient()["upload-auto-avviso"]
    monkeypatch.setattr(documenti.Database, "get_db", staticmethod(lambda: db))
    app = FastAPI()
    app.include_router(documenti.router, prefix="/api/documenti")
    content = _pdf(
        "AVVISO DI PAGAMENTO", "QUANTO E QUANDO PAGARE?",
        "Codice Avviso 302000600008408304", "RATA UNICA ENTRO IL 11/04/2026",
        "VIOLAZIONE CDS - TARGA: GW980EP - DATA: 28/01/2026",
        "VERBALE N.: B26120449023 - C.F.: 00000000000", "34,90", "1M169",
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/documenti/upload-auto",
            files={"file": ("AvvisoDigitale.pdf", content, "application/pdf")},
            headers=confirmed_preview_headers(content, "avviso_pagopa"),
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["tipo_rilevato"] == "avviso_pagopa"
    assert payload["payment_evidence"] is False
    saved = asyncio.run(db["documents_inbox"].find_one({"id": payload["doc_id"]}))
    assert saved["is_payment_evidence"] is False
    assert saved["pagato"] is False and saved["chiuso"] is False
    assert asyncio.run(db["ricevute_pagopa"].count_documents({})) == 0
    verbale = asyncio.run(db["verbali_noleggio"].find_one({}, {"_id": 0}))
    assert verbale["numero_verbale"] == "B26120449023"
    assert verbale["targa"] == "GW980EP"
    assert verbale["data_violazione"] == "2026-01-28"
    assert verbale["data_scadenza"] == "2026-04-11"
    assert verbale["codice_avviso"] == "302000600008408304"
    assert verbale["stato"] == "salvato"
    assert verbale["origine"] == "AVVISO_PAGOPA"
    assert verbale["verbale_originale_acquisito"] is False
    assert verbale["stato_pratica"] == "DA_ACQUISIRE_VERBALE"
    assert verbale.get("pagato") is not True and verbale.get("chiuso") is not True


def test_nota_rettifica_inps_crea_obbligazione_e_non_un_pagamento(monkeypatch):
    content = _pdf(
        "INPS - NOTA DI RETTIFICA - Mod. DMRA",
        "La presente nota di rettifica, emessa il 04/01/2024, si riferisce alla denuncia mensile",
        "di competenza 02/2023 con saldo di EUR 5.532,00.",
        "Matricola azienda 5124776507 Codice fiscale 00000000000",
        "Codice statistico contributivo 70502 Codici autorizzazione 0J",
        "Numero dipendenti occupati 13",
        "Data pagamento F24 16/03/2023 Data di invio flusso UniEmens 23/03/2023",
        "Differenze contributive a debito azienda EUR 1.559,52",
        "Sanzioni civili per differenze contributive EUR 139,29 (n. giorni 326 al tasso 10,00%)",
        "Importo totale a debito dell' azienda EUR 1.698,81 Da versare entro il 05/02/2024",
        "Codice Sede Causale Contributo Matricola Periodo di riferimento Importo",
        "5100 DMRA 5124776507 02/2023 EUR 1.698,81",
        "Il pagamento deve essere effettuato con Mod.F24",
    )
    parsed = parse_nota_rettifica_inps(content)
    assert parsed["document_kind"] == "NOTA_RETTIFICA_INPS"
    assert parsed["is_payment_evidence"] is False
    assert parsed["importo_totale"] == 1698.81
    assert parsed["differenze_contributive"] == 1559.52
    assert parsed["sanzioni_civili"] == 139.29
    assert parsed["istruzioni_f24"]["causale_contributo"] == "DMRA"
    assert parsed["field_evidence"]["importo_totale"]["normalized_value"] == 1698.81
    assert parsed["field_evidence"]["importo_totale"]["parser_version"] == "inps-dmra-v1"
    assert parsed["canonical_relations"]["uniemens"]["status"] == "CITED"
    assert parsed["canonical_relations"]["corrective_f24"]["status"] == "TO_BE_LINKED"

    db = AsyncMongoMockClient()["upload-auto-rettifica"]
    monkeypatch.setattr(documenti.Database, "get_db", staticmethod(lambda: db))
    app = FastAPI()
    app.include_router(documenti.router, prefix="/api/documenti")
    with TestClient(app) as client:
        response = client.post(
            "/api/documenti/upload-auto",
            files={"file": ("StampaSintesiRettifica.pdf", content, "application/pdf")},
            headers=confirmed_preview_headers(content, "nota_rettifica_inps"),
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["tipo_rilevato"] == "nota_rettifica_inps"
    saved = asyncio.run(db["documents_inbox"].find_one({"id": payload["doc_id"]}, {"_id": 0}))
    assert saved["is_payment_evidence"] is False
    assert saved["pagato"] is False and saved["chiuso"] is False
    assert saved["obligation_status"] == "APERTO"
    assert saved["data_scadenza"] == "2024-02-05"
    assert saved["relation_keys"]["matricola_inps"] == "5124776507"


def test_avviso_non_puo_essere_importato_direttamente_come_ricevuta():
    content = _pdf(
        "AVVISO DI PAGAMENTO", "QUANTO E QUANDO PAGARE?",
        "Codice Avviso 302000600008408304", "Importo 34,90 EUR",
    )
    result = asyncio.run(import_receipt(
        AsyncMongoMockClient()["pagopa-avviso-negato"], content=content,
        filename="AvvisoDigitale.pdf", company_id="company-test",
    ))
    assert result["success"] is False
    assert result["document_kind"] == "AVVISO_PAGOPA"


def test_upload_auto_archivia_esito_negativo_senza_segnare_pagato(monkeypatch):
    db = AsyncMongoMockClient()["upload-auto-esito-negativo"]
    monkeypatch.setattr(documenti.Database, "get_db", staticmethod(lambda: db))
    app = FastAPI()
    app.include_router(documenti.router, prefix="/api/documenti")
    content = _pdf(
        "ATTESTAZIONE DI PAGAMENTO", "ESITO : Pagamento non eseguito",
        "IMPORTO TOTALE DA PAGARE : 57,05 EUR",
        "IMPORTO TOTALE PAGATO : ND",
        "ID UNIVOCO VERSAMENTO : 02000600006396668",
        "DATA RICEVUTA : 19/06/2025 20:00:47",
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/documenti/upload-auto",
            files={"file": ("RicevutaTelematica.pdf", content, "application/pdf")},
            headers=confirmed_preview_headers(content, "ricevuta_pagopa"),
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["tipo_rilevato"] == "esito_pagopa_negativo"
    assert payload["payment_evidence"] is False
    saved = asyncio.run(db["documents_inbox"].find_one({"id": payload["doc_id"]}))
    assert saved["evidence_role"] == "esito_negativo"
    assert saved["status"] == "pagamento_non_eseguito"
    assert saved["pagato"] is False and saved["chiuso"] is False
    assert asyncio.run(db["ricevute_pagopa"].count_documents({})) == 0


def test_avviso_e_ricevuta_pagopa_si_collegano_al_verbale_senza_inventare_banca(monkeypatch):
    db = AsyncMongoMockClient()["pagopa-verbale-bidirezionale"]
    monkeypatch.setattr(documenti.Database, "get_db", staticmethod(lambda: db))
    app = FastAPI()
    app.include_router(documenti.router, prefix="/api/documenti")
    avviso = _pdf(
        "AVVISO DI PAGAMENTO", "QUANTO E QUANDO PAGARE?",
        "VIOLAZIONE CDS - TARGA: GW980EP - DATA: 28/01/2026 VERBALE N.: B26120449023",
        "Codice Avviso 302000600008408304", "RATA UNICA 34,90 EUR",
    )
    ricevuta = _pdf(
        "ATTESTAZIONE DI PAGAMENTO", "ESITO : Pagamento eseguito",
        "OGGETTO DEL PAGAMENTO: Violazione CdS - TARGA: GW980EP - DATA: 28/01/2026 VERBALE N.: B26120449023",
        "IMPORTO TOTALE PAGATO : 34,90 EUR",
        "ID UNIVOCO VERSAMENTO : 02000600008408304",
        "DATA RICEVUTA : 12/03/2026 16:18:52",
    )

    with TestClient(app) as client:
        first = client.post(
            "/api/documenti/upload-auto",
            files={"file": ("AvvisoDigitale.pdf", avviso, "application/pdf")},
            headers=confirmed_preview_headers(avviso, "avviso_pagopa"),
        )
        second = client.post(
            "/api/documenti/upload-auto",
            files={"file": ("RicevutaTelematica.pdf", ricevuta, "application/pdf")},
            headers=confirmed_preview_headers(ricevuta, "ricevuta_pagopa"),
        )

    assert first.status_code == second.status_code == 200
    assert first.json()["association"]["status"] == "linked"
    assert second.json()["data"]["riconciliazione_verbale"]["matched"] is True
    verbale = asyncio.run(db["verbali_noleggio"].find_one({"numero_verbale": "B26120449023"}))
    receipt = asyncio.run(db["ricevute_pagopa"].find_one({"numero_verbale": "B26120449023"}))
    assert verbale["stato"] == "pagato"
    assert verbale["stato_pratica"] == "PAGATO_DOCUMENTALE"
    assert verbale["pagato_documentalmente"] is True
    assert verbale["ricevuta_pagopa_id"] == receipt["id"]
    assert receipt["verbale_id"] == verbale["id"]
    assert receipt["versato_documentalmente"] is True
    assert receipt["banca_verificata"] is False
    assert verbale.get("movimento_banca_id") is None


def test_upload_auto_quietanza_reale_generata_attraversa_parser_e_router(monkeypatch):
    db = AsyncMongoMockClient()["upload-auto-quietanza-real-parser"]
    monkeypatch.setattr(documenti.Database, "get_db", staticmethod(lambda: db))
    asyncio.run(db["f24_unificato"].insert_one({
        "id": "f24-1040-06-2026", "status": "da_pagare", "riconciliato": False,
        "codice_fiscale": "00000000000",
        "sezione_erario": [{
            "codice_tributo": "1040", "periodo_riferimento": "06/2026",
            "importo_debito": 284.0,
        }],
        "totali": {"saldo_netto": 284.0},
    }))
    content = _pdf(
        "QUIETANZA", "RICEVUTA DI VERSAMENTO F24",
        "Soggetto: IMPRESA TEST S.R.L. (00000000000)",
        "Protocollo 26072135472143961/000001",
        "Data: 21/07/2026 - Ore: 10:00:00", "Saldo delega 286,00",
        "ERARIO 1040 06 2026 284,00 0,00",
        "ERARIO 8948 06 2026 2,00 0,00", "2 1 0 7 2 0 2 6 05034",
    )
    app = FastAPI()
    app.include_router(documenti.router, prefix="/api/documenti")

    with TestClient(app) as client:
        first = client.post(
            "/api/documenti/upload-auto",
            files={"file": ("quietanza_1040.pdf", content, "application/pdf")},
            headers=confirmed_preview_headers(content, "quietanza_f24"),
        )
        second = client.post(
            "/api/documenti/upload-auto",
            files={"file": ("quietanza_1040.pdf", content, "application/pdf")},
            headers=confirmed_preview_headers(content, "quietanza_f24"),
        )

    assert first.status_code == second.status_code == 200
    payload = first.json()
    assert payload["success"] is True
    assert payload["tipo_rilevato"] == "quietanza_f24"
    assert payload["data"]["protocollo"] == "26072135472143961/000001"
    assert payload["data"]["saldo"] == 286.0
    assert payload["data"]["codici_tributo"] == 2
    assert payload["data"]["f24_matchati"][0]["f24_id"] == "f24-1040-06-2026"
    assert second.json()["duplicate"] is True
    model = asyncio.run(db["f24_unificato"].find_one({"id": "f24-1040-06-2026"}))
    assert model["pagato"] is False
    assert model["pagamento_verificato_banca"] is False
    assert model["data_pagamento_quietanza"] == "2026-07-21"
