import asyncio
from datetime import date

from app.services.lipe_verifica import list_lipe_monthly_evidence, parse_lipe_modules, parse_lipe_page
from app.services.sheets_document_store import MemorySheetsClient
from app.services.verifica_coerenza import VerificaCoerenza, stato_temporale_periodo


def test_parser_lipe_conserva_campi_vp_e_testimonianza():
    parsed = parse_lipe_page("""
        VP1 Mese 7
        VP4 IVA esigibile 6.211,86
        VP5 IVA detratta 3.241,46
        VP14 IVA da versare 2.970,40
    """)

    assert parsed["month"] == 7
    assert parsed["values"] == {
        "vp4_cents": 621186,
        "vp5_cents": 324146,
        "vp14_cents": 297040,
    }
    assert "VP4" in parsed["raw_evidence"]
    assert parsed["confidence"] == 1.0


def test_parser_lipe_legge_il_modello_ade_per_coordinate_non_per_ordine_testo():
    def word(text, x0, y0, x1=None, y1=None):
        return {
            "text": text, "x0": x0, "y0": y0,
            "x1": x1 if x1 is not None else x0 + 8,
            "y1": y1 if y1 is not None else y0 + 8,
        }

    layout = [
        word("VP1", 108, 158), word("0", 155, 158), word("2", 170, 158),
        word("VP2", 108, 182), word("10", 376, 183), word(",", 385, 183),
        word("8", 393, 183), word("2", 408, 183),
        word("VP3", 108, 206), word("54.935", 503, 207), word(",", 529, 207),
        word("9", 536, 207), word("5", 551, 207),
        word("VP4", 108, 230), word("10", 376, 231), word(",", 385, 231),
        word("8", 393, 231), word("2", 408, 231),
        word("VP5", 108, 254), word("10.337", 503, 255), word(",", 529, 255),
        word("5", 536, 255), word("6", 551, 255),
        word("VP6", 108, 278), word("10.326", 503, 279), word(",", 529, 279),
        word("7", 536, 279), word("4", 551, 279),
        word("VP8", 108, 326), word("7.732", 503, 327), word(",", 529, 327),
        word("1", 536, 327), word("8", 551, 327),
        word("VP14", 108, 470), word("18.058", 503, 471), word(",", 529, 471),
        word("9", 536, 471), word("2", 551, 471),
    ]
    parsed = parse_lipe_page(
        "VP2 Totale operazioni attive VP3 Totale operazioni passive VP4 IVA esigibile",
        layout_words=layout,
    )

    assert parsed["month"] == 2
    assert parsed["values"] == {
        "vp2_cents": 1082,
        "vp3_cents": 5493595,
        "vp4_cents": 1082,
        "vp5_cents": 1033756,
        "vp6_cents": 1032674,
        "vp8_cents": 773218,
        "vp6_side": "credito",
        "vp14_cents": 1805892,
        "vp14_side": "credito",
    }
    assert parsed["parse_method"] == "pdf_layout"
    assert parsed["quadrature"] == {"vp6": True, "vp14": True}
    assert parsed["confidence"] == 1.0


def test_parser_layout_non_conferma_una_quadratura_errata():
    def word(text, x, y):
        return {"text": text, "x0": x, "y0": y, "x1": x + 8, "y1": y + 8}

    layout = [
        word("VP1", 108, 158), word("0", 155, 158), word("1", 170, 158),
        word("VP4", 108, 230), word("100", 376, 230), word(",", 385, 230),
        word("0", 393, 230), word("0", 408, 230),
        word("VP5", 108, 254), word("20", 503, 254), word(",", 529, 254),
        word("0", 536, 254), word("0", 551, 254),
        word("VP6", 108, 278), word("70", 376, 278), word(",", 385, 278),
        word("0", 393, 278), word("0", 408, 278),
    ]
    parsed = parse_lipe_page("VP1 VP4 VP5 VP6", layout_words=layout)

    assert parsed["quadrature"]["vp6"] is False
    assert parsed["confidence"] == 0.7


def test_lipe_duplicata_resta_ambigua_con_provenienza():
    async def scenario():
        db = MemorySheetsClient().db
        for suffix in ("A", "B"):
            await db.fiscal_documents.insert_one({
                "id": f"LIPE-{suffix}", "company_id": "CERALDI",
                "document_type": "LIPE", "filename": f"LIPE-{suffix}.pdf",
                "source_metadata": {"tax_year": 2026},
            })
            await db.fiscal_pages.insert_one({
                "document_id": f"LIPE-{suffix}", "version_id": f"V-{suffix}",
                "page_number": 1, "text": "VP1 Mese 7\nVP4 100,00\nVP5 20,00",
            })
        result = await list_lipe_monthly_evidence(db, year=2026, company_id="CERALDI")
        assert result[7]["stato"] == "LIPE_AMBIGUA"
        assert {item["document_id"] for item in result[7]["candidati"]} == {"LIPE-A", "LIPE-B"}

    asyncio.run(scenario())


def test_lipe_da_ocr_resta_da_verificare_anche_con_i_campi_presenti():
    async def scenario():
        db = MemorySheetsClient().db
        await db.fiscal_documents.insert_one({
            "id": "LIPE-OCR", "company_id": "CERALDI", "document_type": "LIPE",
            "filename": "LIPE_2026.pdf", "source_metadata": {"tax_year": 2026},
        })
        await db.fiscal_pages.insert_one({
            "document_id": "LIPE-OCR", "version_id": "V-OCR", "page_number": 1,
            "text": "VP1 Mese 7\nVP4 100,00\nVP5 20,00", "ocr_used": True,
            "text_source": "rapidocr_locale", "ocr_confidence": 0.91,
        })
        result = await list_lipe_monthly_evidence(db, year=2026, company_id="CERALDI")
        assert result[7]["stato"] == "LIPE_DA_VERIFICARE"
        assert result[7]["vp4_cents"] == 10000
        assert result[7]["ocr_used"] is True
        assert result[7]["confidence"] == 0.91

    asyncio.run(scenario())


def test_pagina_con_piu_moduli_non_confonde_i_mesi():
    parsed = parse_lipe_modules(
        "Anno 2026\nVP1 Mese 1\nVP4 100,00\nVP5 20,00\n"
        "VP1 Mese 2\nVP4 200,00\nVP5 30,00"
    )
    assert [item["month"] for item in parsed] == [1, 2]
    assert [item["values"]["vp4_cents"] for item in parsed] == [10000, 20000]


def test_mesi_correnti_e_futuri_non_diventano_omissioni():
    today = date(2026, 8, 21)
    assert stato_temporale_periodo(2026, 8, "NON_CALCOLATO", "2026-09-16", oggi=today) == "IN_FORMAZIONE"
    assert stato_temporale_periodo(2026, 9, "NON_CALCOLATO", "2026-10-16", oggi=today) == "NON_ANCORA_DOVUTO"
    assert stato_temporale_periodo(2026, 7, "NON_CALCOLATO", "2026-08-20", oggi=today) == "DA_COMPLETARE"
    assert stato_temporale_periodo(2026, 7, "CALCOLATA", "2026-08-20", oggi=today) == "CALCOLATO"


def test_verifica_annuale_non_segnala_i_cinque_mesi_non_maturati(monkeypatch):
    async def scenario():
        db = MemorySheetsClient().db
        verifier = VerificaCoerenza(db)

        async def credito(_anno, month):
            calculated = month <= 7
            return {
                "iva_credito_fatture_cents": 10000 if calculated else None,
                "stato_calcolo": "CALCOLATA" if calculated else "NON_CALCOLATO",
                "scadenza_nominale": f"2026-{min(month + 1, 12):02d}-16",
                "scadenza_legale": "2026-08-20" if month == 7 else "2026-12-31",
            }

        async def debito(_anno, month):
            return {"iva_debito_corrispettivi_cents": 20000 if month <= 7 else None}

        async def f24(_anno, month):
            return {"stato": "f24_ricevuto" if month <= 7 else "in_attesa_f24"}

        async def f24_banca(_anno):
            return {"f24_totale": 0, "f24_pagati": 0, "pagamenti_banca_f24": 0, "differenza": 0}

        monkeypatch.setattr(verifier, "verifica_iva_credito_mensile", credito)
        monkeypatch.setattr(verifier, "verifica_iva_debito_mensile", debito)
        monkeypatch.setattr(verifier, "trova_f24_iva_mensile", f24)
        monkeypatch.setattr(verifier, "verifica_f24_vs_pagamenti", f24_banca)

        result = await verifier.verifica_completa(2026, oggi=date(2026, 8, 21))
        assert result["verifiche"]["iva_annuale"]["mesi_non_calcolati"] == 0
        assert result["verifiche"]["iva_annuale"]["mesi_in_formazione"] == 1
        assert result["verifiche"]["iva_annuale"]["mesi_non_ancora_dovuti"] == 4
        assert not any(item["sottocategoria"] == "Copertura annuale" for item in result["discrepanze"])

    asyncio.run(scenario())
