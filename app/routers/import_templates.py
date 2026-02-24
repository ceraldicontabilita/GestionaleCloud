"""
Import Templates Router
Fornisce template Excel/CSV scaricabili per ogni tipo di importazione.
DEFINITIVI - basati sui file reali della banca.
"""
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
import io
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

router = APIRouter()

def create_styled_workbook():
    """Crea un workbook con stili predefiniti."""
    wb = openpyxl.Workbook()
    return wb

def style_header_row(ws, headers, descriptions=None):
    """Applica stile alle intestazioni."""
    header_fill = PatternFill(start_color="1e3a5f", end_color="1e3a5f", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True, size=11)
    desc_fill = PatternFill(start_color="e8f4f8", end_color="e8f4f8", fill_type="solid")
    desc_font = Font(color="666666", italic=True, size=9)
    border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )
    
    # Intestazioni
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.border = border
        ws.column_dimensions[openpyxl.utils.get_column_letter(col)].width = max(15, len(str(header)) + 5)
    
    # Descrizioni (riga 2)
    if descriptions:
        for col, desc in enumerate(descriptions, 1):
            cell = ws.cell(row=2, column=col, value=desc)
            cell.fill = desc_fill
            cell.font = desc_font
            cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
            cell.border = border
        ws.row_dimensions[2].height = 30

def add_example_row(ws, example_data, start_row=3):
    """Aggiunge una riga di esempio."""
    example_font = Font(color="999999", italic=True)
    for col, value in enumerate(example_data, 1):
        cell = ws.cell(row=start_row, column=col, value=value)
        cell.font = example_font


# =============================================================================
# TEMPLATE DEFINITIVI - INTESTAZIONI ESATTE DAI FILE BANCA
# =============================================================================

@router.get("/corrispettivi")
async def template_corrispettivi():
    """
    Template DEFINITIVO per importazione corrispettivi giornalieri.
    Formato: XLSX del registratore di cassa.
    
    Intestazioni ESATTE:
    - Id invio
    - Matricola dispositivo
    - Data e ora rilevazione
    - Data e ora trasmissione
    - Ammontare delle vendite (totale in euro)
    - Imponibile vendite (totale in euro)
    - Imposta vendite (totale in euro)
    - Periodo di inattivita' da
    - Periodo di inattivita' a
    """
    wb = create_styled_workbook()
    ws = wb.active
    ws.title = "Corrispettivi"
    
    # Intestazioni ESATTE come da file corrispettivi.xlsx
    headers = [
        "Id invio",
        "Matricola dispositivo",
        "Data e ora rilevazione",
        "Data e ora trasmissione",
        "Ammontare delle vendite (totale in euro)",
        "Imponibile vendite (totale in euro)",
        "Imposta vendite (totale in euro)",
        "Periodo di inattivita' da",
        "Periodo di inattivita' a"
    ]
    descriptions = [
        "ID trasmissione",
        "Matricola RT",
        "Data chiusura",
        "Data invio",
        "Totale vendite (€)",
        "Imponibile (€)",
        "IVA (€)",
        "Inizio inattività",
        "Fine inattività"
    ]
    
    style_header_row(ws, headers, descriptions)
    add_example_row(ws, ["'2709633383'", "'99MEY026532'", "2025-01-02 21:05:00", "2025-01-02 21:05:00", 3264.55, 3264.55, 326.45, "", ""])
    
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=template_corrispettivi.xlsx"}
    )


@router.get("/pos")
async def template_pos():
    """
    Template DEFINITIVO per importazione incassi POS giornalieri.
    Formato: XLSX.
    
    Intestazioni ESATTE:
    - DATA
    - CONTO
    - IMPORTO
    """
    wb = create_styled_workbook()
    ws = wb.active
    ws.title = "Incassi POS"
    
    # Intestazioni ESATTE come da file pos.xlsx
    headers = ["DATA", "CONTO", "IMPORTO"]
    descriptions = [
        "Data operazione (YYYY-MM-DD)",
        "Tipo conto (pos)",
        "Importo giornaliero (€)"
    ]
    
    style_header_row(ws, headers, descriptions)
    add_example_row(ws, ["2025-01-01", "pos", 323.50])
    add_example_row(ws, ["2025-01-02", "pos", 1655.60], start_row=4)
    
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=template_pos.xlsx"}
    )


@router.get("/versamenti")
async def template_versamenti():
    """
    Template DEFINITIVO per importazione versamenti in banca.
    Formato: CSV con delimitatore ;
    
    Intestazioni ESATTE:
    - Ragione Sociale
    - Data contabile
    - Data valuta
    - Banca
    - Rapporto
    - Importo
    - Divisa
    - Descrizione
    - Categoria/sottocategoria
    - Hashtag
    """
    # Genera CSV con le intestazioni esatte
    csv_content = """Ragione Sociale;Data contabile;Data valuta;Banca;Rapporto;Importo;Divisa;Descrizione;Categoria/sottocategoria;Hashtag
AZIENDA SRL;29/12/2025;29/12/2025;05034 - BANCO BPM S.P.A.;5462 - 03406 - 178800005462;10460;EUR;VERS. CONTANTI - VVVVV;Ricavi - Deposito contanti;
AZIENDA SRL;22/12/2025;22/12/2025;05034 - BANCO BPM S.P.A.;5462 - 03406 - 178800005462;1660;EUR;VERS. CONTANTI - VVVVV;Ricavi - Deposito contanti;"""
    
    output = io.BytesIO(csv_content.encode('utf-8-sig'))
    output.seek(0)
    
    return StreamingResponse(
        output,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=template_versamenti.csv"}
    )


@router.get("/estratto-conto")
async def template_estratto_conto():
    """
    Template DEFINITIVO per importazione estratto conto bancario.
    Formato: CSV con delimitatore ;
    
    Intestazioni ESATTE:
    - Ragione Sociale
    - Data contabile
    - Data valuta
    - Banca
    - Rapporto
    - Importo
    - Divisa
    - Descrizione
    - Categoria/sottocategoria
    - Hashtag
    """
    # Genera CSV con le intestazioni esatte
    csv_content = """Ragione Sociale;Data contabile;Data valuta;Banca;Rapporto;Importo;Divisa;Descrizione;Categoria/sottocategoria;Hashtag
AZIENDA SRL;08/01/2026;08/01/2026;05034 - BANCO BPM S.P.A.;5462 - 03406 - 178800005462;254,5;EUR;INCAS. TRAMITE P.O.S - NUMIA-PGBNT DEL 07/01/26;Ricavi - Incasso tramite POS;
AZIENDA SRL;08/01/2026;08/01/2026;05034 - BANCO BPM S.P.A.;5462 - 03406 - 178800005462;-1500;EUR;BONIFICO A FAVORE FORNITORE XYZ;Costi - Pagamento fornitore;"""
    
    output = io.BytesIO(csv_content.encode('utf-8-sig'))
    output.seek(0)
    
    return StreamingResponse(
        output,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=template_estratto_conto.csv"}
    )
