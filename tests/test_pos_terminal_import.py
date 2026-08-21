import io
import asyncio
from datetime import datetime

import openpyxl
import pytest

from app.services.pos_terminal_import import (
    importa_pos_terminal_file,
    parse_pos_terminal_file,
)
from app.services.sheets_document_store import MemorySheetsClient


def test_csv_pos_aggrega_solo_operazioni_approvate_e_storni_con_segno():
    content = (
        "Data e ora;Codice autorizzazione;Importo;Tipo transazione;Stato operazione;ID Transazione\n"
        "01/06/2026 09:00:00;A1;10,50;Acquisto;Acquisto approvato;T1\n"
        "01/06/2026 10:00:00;A2;20,00;Acquisto;Acquisto negato;T2\n"
        "01/06/2026 11:00:00;A3;-2,00;Storno;Storno approvato;T3\n"
        "02/06/2026 09:00:00;A4;7,25;Acquisto;Acquisto approvato;T4\n"
    ).encode("utf-8")

    result = parse_pos_terminal_file(content, "Export_Mensile_Giugno_2026.csv")

    assert result["rows"] == 4
    assert result["approved"] == 3
    assert result["daily_totals"] == {"2026-06-01": 8.5, "2026-06-02": 7.25}


def test_xlsx_pos_trova_header_alla_terza_riga():
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["Export terminale POS"])
    sheet.append([])
    sheet.append(["Data e ora", "Importo", "Tipo transazione", "Stato operazione", "ID Transazione"])
    sheet.append(["03/06/2026 08:10:00", 15.4, "Acquisto", "Acquisto approvato", "TX-1"])
    buffer = io.BytesIO()
    workbook.save(buffer)

    result = parse_pos_terminal_file(buffer.getvalue(), "Export_Transazioni_giugno_2026.xlsx")

    assert result["daily_totals"] == {"2026-06-03": 15.4}


def test_csv_pos_deduplica_id_transazione_prima_dei_totali():
    content = (
        "Data e ora;Importo;Tipo transazione;Stato operazione;ID Transazione\n"
        "03/06/2026 08:10:00;15,40;Acquisto;Acquisto approvato;TX-1\n"
        "03/06/2026 08:10:00;15,40;Acquisto;Acquisto approvato;TX-1\n"
    ).encode("utf-8")

    result = parse_pos_terminal_file(content, "Export_Transazioni_giugno_2026.csv")

    assert result["source_rows"] == 2
    assert result["rows"] == 1
    assert result["duplicates"] == 1
    assert result["approved"] == 1
    assert result["daily_totals"] == {"2026-06-03": 15.4}


def test_csv_pos_blocca_stesso_id_con_importi_diversi():
    content = (
        "Data e ora;Importo;Tipo transazione;Stato operazione;ID Transazione\n"
        "03/06/2026 08:10:00;15,40;Acquisto;Acquisto approvato;TX-1\n"
        "03/06/2026 08:10:00;16,40;Acquisto;Acquisto approvato;TX-1\n"
    ).encode("utf-8")

    with pytest.raises(ValueError, match="ID transazione POS contraddittorio TX-1"):
        parse_pos_terminal_file(content, "Export_Transazioni_giugno_2026.csv")


def test_file_commissioni_viene_instradato_senza_essere_un_export_transazioni():
    # Il dispatcher lo accetta, poi il nome lo invia al parser commissioni:
    # non deve mai diventare una chiusura POS reale.
    from app.services.drive_estratti_conto_ingest import _supported_file

    assert _supported_file("pos", "Export_Transazioni_aprile_2026.xlsx") is True
    assert _supported_file("pos", "Commissioni_Aprile_2026.xlsx") is True
    assert _supported_file("mutuo", "Estratto mutuo_31-12-2022.pdf") is True


def test_chiave_operazione_non_dipende_dal_nome_del_file_o_formato_data():
    csv = (
        "Data e ora;Codice autorizzazione;Importo;Tipo transazione;Stato operazione;Numero carta\n"
        "31/05/2026 20:33:50.000;777777;23,10;Acquisto;Acquisto approvato;************1234\n"
    ).encode("utf-8")
    first = parse_pos_terminal_file(csv, "Export_Mensile_Maggio_2026.csv")

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append([
        "Data e ora", "Codice autorizzazione", "Importo", "Tipo transazione",
        "Stato operazione", "Numero carta",
    ])
    sheet.append([
        datetime(2026, 5, 31, 20, 33, 50), "777777", 23.10, "Acquisto",
        "Acquisto approvato", "************1234",
    ])
    buffer = io.BytesIO()
    workbook.save(buffer)
    second = parse_pos_terminal_file(buffer.getvalue(), "Periodo_01-31_maggio.xlsx")

    assert first["transactions"][0]["operation_key"] == second["transactions"][0]["operation_key"]


def test_codice_autorizzazione_riutilizzato_non_unisce_due_id_gestore():
    content = (
        "Data e ora;Codice autorizzazione;Importo;Tipo transazione;Stato operazione;ID Transazione\n"
        "01/06/2026 09:00:00;123456;10,00;Acquisto;Acquisto approvato;TX-A\n"
        "02/06/2026 09:00:00;123456;10,00;Acquisto;Acquisto approvato;TX-B\n"
    ).encode("utf-8")

    result = parse_pos_terminal_file(content, "Export_Mensile_Giugno_2026.csv")

    assert result["rows"] == 2
    assert len({row["operation_key"] for row in result["transactions"]}) == 2


def test_operazioni_identiche_senza_id_preservano_la_molteplicita():
    content = (
        "Data e ora;Codice autorizzazione;Importo;Tipo transazione;Stato operazione;Numero carta\n"
        "01/06/2026 09:00:00;;10,00;Acquisto;Acquisto approvato;************1234\n"
        "01/06/2026 09:00:00;;10,00;Acquisto;Acquisto approvato;************1234\n"
    ).encode("utf-8")

    first = parse_pos_terminal_file(content, "intero.csv")
    second = parse_pos_terminal_file(content, "sovrapposto.csv")

    assert first["rows"] == 2
    assert first["duplicates"] == 0
    assert [row["operation_key"] for row in first["transactions"]] == [
        row["operation_key"] for row in second["transactions"]
    ]


def test_reimport_periodo_sovrapposto_non_duplica_operazioni(monkeypatch):
    async def scenario():
        db = MemorySheetsClient()["pos_overlap_test"]
        content = (
            "Data e ora;Codice autorizzazione;Importo;Tipo transazione;Stato operazione;ID Transazione\n"
            "01/06/2026 09:00:00;A1;10,00;Acquisto;Acquisto approvato;TX-A\n"
            "02/06/2026 09:00:00;A2;20,00;Acquisto;Acquisto approvato;TX-B\n"
        ).encode("utf-8")

        async def no_op_chiusura(*_args, **_kwargs):
            return {"success": True}

        from app.services import scritture_contabili
        monkeypatch.setattr(
            scritture_contabili, "registra_chiusura_pos_reale", no_op_chiusura,
        )

        first = await importa_pos_terminal_file(db, content, "mese_intero.csv")
        second = await importa_pos_terminal_file(db, content, "periodo_sovrapposto.csv")
        count = await db["pos_terminal_transactions"].count_documents({})
        return first, second, count

    first, second, count = asyncio.run(scenario())
    assert first["inserted"] == 2
    assert second["inserted"] == 0
    assert second["unchanged"] == 2
    assert count == 2
