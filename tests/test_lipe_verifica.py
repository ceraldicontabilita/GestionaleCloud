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
