import io

import openpyxl

from app.services.pos_terminal_import import parse_pos_terminal_file


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


def test_file_commissioni_non_e_un_export_transazioni():
    # La selezione avviene prima del parser: serve a impedire che i riepiloghi
    # commissioni vengano scambiati per incassi POS reali.
    from app.services.drive_estratti_conto_ingest import _supported_file

    assert _supported_file("pos", "Export_Transazioni_aprile_2026.xlsx") is True
    assert _supported_file("pos", "Commissioni_Aprile_2026.xlsx") is False
