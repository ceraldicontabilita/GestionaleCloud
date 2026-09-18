import asyncio
from app.services.sheets_document_store import MemorySheetsClient

from app.routers.accounting.contabilita_gestionale import (
    _bilancio_verifica_da_registro,
)


def test_non_confonde_compensazione_annuale_con_scritture_in_quadratura():
    async def scenario():
        db = MemorySheetsClient().db
        await db.movimenti_contabili.insert_many([
            {
                "id": "s1",
                "anno": 2026,
                "data": "2026-01-10",
                "righe": [
                    {"conto_codice": "01.01.01", "conto_nome": "Cassa", "dare": 100},
                    {"conto_codice": "04.01.01", "conto_nome": "Ricavi", "avere": 90},
                ],
            },
            {
                "id": "s2",
                "anno": 2026,
                "data": "2026-01-11",
                "righe": [
                    {"conto_codice": "05.01.01", "conto_nome": "Costi", "dare": 90},
                    {"conto_codice": "02.01.01", "conto_nome": "Debiti", "avere": 100},
                ],
            },
        ])
        return await _bilancio_verifica_da_registro(db, 2026, False)

    result = asyncio.run(scenario())

    assert result["totali"]["dare"] == result["totali"]["avere"] == 190
    assert result["qualita_registro"]["quadratura_totali"] is True
    assert result["qualita_registro"]["scritture_sbilanciate"] == 2
    assert result["qualita_registro"]["registro_valido"] is False
    assert result["quadratura"] is False


def test_segnala_righe_invalide_e_scritture_senza_righe():
    async def scenario():
        db = MemorySheetsClient().db
        await db.movimenti_contabili.insert_many([
            {
                "id": "valida-con-riga-errata",
                "anno": 2026,
                "data": "2026-02-10",
                "righe": [
                    {"conto_codice": "01.01.01", "conto_nome": "Cassa", "dare": 50},
                    {"conto_codice": "02.01.01", "conto_nome": "Debiti", "avere": 50},
                    {"conto_codice": "05.01.01", "conto_nome": "Costi", "dare": "non-numero"},
                    {"conto_codice": "", "conto_nome": "Senza conto", "dare": 1},
                ],
            },
            {"id": "vuota", "anno": 2026, "data": "2026-02-11", "righe": []},
        ])
        return await _bilancio_verifica_da_registro(db, 2026, False)

    result = asyncio.run(scenario())

    quality = result["qualita_registro"]
    assert quality["righe_non_numeriche"] == 1
    assert quality["righe_senza_conto"] == 1
    assert quality["scritture_senza_righe"] == 1
    assert quality["registro_valido"] is False
    assert result["completezza_registro"]["completo"] is False


def test_registro_vuoto_non_quadra_ed_espone_lo_stato_onesto():
    """Audit 03/09/2026 §2 (PR 6): 0 scritture non e' una quadratura."""
    async def scenario():
        db = MemorySheetsClient().db
        # documenti sorgente dell'anno, anche gia' "flaggati" registrati:
        # senza scritture il flag non puo' essere vero e vanno contati.
        await db.corrispettivi.insert_many([
            {"id": "c1", "data": "2026-03-22", "totale": 4629.2},
            {"id": "c2", "data": "2026-03-23", "totale": 100.0,
             "registrato_contabilita": True},
            {"id": "c-old", "data": "2025-12-31", "totale": 1.0},
            {"id": "c-del", "data": "2026-01-02", "totale": 1.0,
             "entity_status": "deleted"},
        ])
        await db.invoices.insert_many([
            {"id": "f1", "invoice_date": "2026-02-10", "registrata_contabilita": True},
            {"id": "f2", "data_fattura": "2026-02-11"},
            {"id": "f-del", "invoice_date": "2026-02-12", "status": "deleted"},
        ])
        return await _bilancio_verifica_da_registro(db, 2026, False)

    result = asyncio.run(scenario())

    assert result["quadratura"] is False
    assert result["stato"] == "REGISTRO_VUOTO"
    assert "Nessuna scrittura" in result["messaggio"]
    assert result["qualita_registro"]["registro_valido"] is False
    assert result["qualita_registro"]["registro_vuoto"] is True
    assert result["qualita_registro"]["quadratura_totali"] is False
    assert result["completezza_registro"] == {
        "scritture_registrate": 0,
        "fatture_da_registrare": 2,
        "corrispettivi_da_registrare": 2,
        "documenti_da_registrare": 4,
        "completo": False,
    }


def test_registro_con_scritture_bilanciate_quadra_e_dichiara_lo_stato():
    async def scenario():
        db = MemorySheetsClient().db
        await db.movimenti_contabili.insert_many([
            {
                "id": "s1", "anno": 2026, "data": "2026-03-22",
                "righe": [
                    {"conto_codice": "01.01.01", "conto_nome": "Cassa", "dare": 4629.2},
                    {"conto_codice": "04.01.01", "conto_nome": "Ricavi", "avere": 4629.2},
                ],
            },
        ])
        await db.corrispettivi.insert_one(
            {"id": "c1", "data": "2026-03-22", "totale": 4629.2,
             "registrato_contabilita": True},
        )
        return await _bilancio_verifica_da_registro(db, 2026, False)

    result = asyncio.run(scenario())

    assert result["quadratura"] is True
    assert result["stato"] == "QUADRA"
    assert result["qualita_registro"]["registro_vuoto"] is False
    assert result["completezza_registro"]["completo"] is True
    assert result["completezza_registro"]["documenti_da_registrare"] == 0


def test_registro_che_quadra_ma_con_backlog_non_e_completo():
    async def scenario():
        db = MemorySheetsClient().db
        await db.movimenti_contabili.insert_one({
            "id": "s1", "anno": 2026, "data": "2026-03-22",
            "righe": [
                {"conto_codice": "01.01.01", "conto_nome": "Cassa", "dare": 10},
                {"conto_codice": "04.01.01", "conto_nome": "Ricavi", "avere": 10},
            ],
        })
        await db.corrispettivi.insert_one({"id": "c2", "data": "2026-03-23", "totale": 5})
        return await _bilancio_verifica_da_registro(db, 2026, False)

    result = asyncio.run(scenario())

    assert result["quadratura"] is True
    assert result["stato"] == "QUADRA_INCOMPLETO"
    assert result["completezza_registro"]["completo"] is False
    assert result["completezza_registro"]["corrispettivi_da_registrare"] == 1


def test_espone_il_patrimonio_netto_nel_riepilogo():
    async def scenario():
        db = MemorySheetsClient().db
        await db.movimenti_contabili.insert_one({
            "id": "apertura",
            "anno": 2026,
            "data": "2026-01-01",
            "righe": [
                {"conto_codice": "01.01.02", "conto_nome": "Banca", "dare": 1000},
                {"conto_codice": "03.01.01", "conto_nome": "Capitale", "avere": 1000},
            ],
        })
        return await _bilancio_verifica_da_registro(db, 2026, False)

    result = asyncio.run(scenario())

    assert result["quadratura"] is True
    assert result["riepilogo"]["n_conti_patrimonio_netto"] == 1
    assert {c["tipo"] for c in result["conti"]} == {"attivo", "patrimonio_netto"}
