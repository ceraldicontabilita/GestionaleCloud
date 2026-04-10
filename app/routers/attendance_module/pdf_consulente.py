"""
ATTENDANCE - PDF Consulente e Note
==================================
Generazione PDF presenze per consulente del lavoro.
Gestione note presenze (protocolli malattia).
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from typing import Dict, Any
from datetime import datetime, timezone
import uuid
import io
import calendar
import logging

from app.database import Database
from .models import MESI
from app.utils.error_handler import handle_errors

logger = logging.getLogger(__name__)
router = APIRouter()


# =============================================================================
# NOTE PRESENZE (Protocolli Malattia, etc.)
# =============================================================================

@router.post("/set-nota-presenza")
@handle_errors
async def set_nota_presenza(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Imposta una nota per una presenza (es. protocollo certificato medico).
    """
    db = Database.get_db()
    
    employee_id = data.get("employee_id")
    data_str = data.get("data")
    protocollo = data.get("protocollo_malattia")
    note = data.get("note")
    
    if not employee_id or not data_str:
        raise HTTPException(400, "employee_id e data sono obbligatori")
    
    update_fields = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if protocollo:
        update_fields["protocollo_malattia"] = protocollo
    if note:
        update_fields["note"] = note
    
    await db["attendance_note_presenze"].update_one(
        {"employee_id": employee_id, "data": data_str},
        {
            "$set": update_fields,
            "$setOnInsert": {
                "id": str(uuid.uuid4()),
                "employee_id": employee_id,
                "data": data_str,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
        },
        upsert=True
    )
    
    return {"success": True, "message": "Nota salvata"}


@router.get("/note-presenze/{anno}/{mese}")
@handle_errors
async def get_note_presenze(anno: int, mese: int) -> Dict[str, Any]:
    """Recupera tutte le note presenze per un mese."""
    db = Database.get_db()
    
    data_inizio = f"{anno}-{mese:02d}-01"
    if mese == 12:
        data_fine = f"{anno + 1}-01-01"
    else:
        data_fine = f"{anno}-{mese + 1:02d}-01"
    
    note = await db["attendance_note_presenze"].find(
        {"data": {"$gte": data_inizio, "$lt": data_fine}},
        {"_id": 0}
    ).to_list(1000)
    
    note_dict = {}
    for n in note:
        emp_id = n["employee_id"]
        data_val = n["data"]
        key = f"{emp_id}_{data_val}"
        note_dict[key] = n
    
    return {"success": True, "note": note_dict}


# =============================================================================
# GENERAZIONE PDF PER CONSULENTE DEL LAVORO
# =============================================================================

@router.post("/genera-pdf-consulente")
@handle_errors
async def genera_pdf_consulente(data: Dict[str, Any]):
    """
    Genera un PDF riepilogativo delle presenze per il consulente del lavoro.
    Include:
    - Riepilogo presenze per dipendente
    - Dettaglio giorni (P, F, M, etc.)
    - Protocolli certificati malattia
    - Acconti mensili
    - Note
    """
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.enums import TA_CENTER
    except ImportError:
        raise HTTPException(500, "reportlab non installato")
    
    db = Database.get_db()
    
    anno = data.get("anno", datetime.now().year)
    mese = data.get("mese", datetime.now().month)
    
    # Recupera dipendenti in carico (escludi cessati)
    dipendenti = await db["dipendenti"].find(
        {
            "$and": [
                {"$or": [{"in_carico": True}, {"in_carico": {"$exists": False}}]},
                {"$or": [{"stato_contratto": {"$ne": "cessato"}}, {"stato_contratto": {"$exists": False}}]}
            ]
        },
        {"_id": 0, "id": 1, "nome": 1, "cognome": 1, "nome_completo": 1, "name": 1}
    ).sort("cognome", 1).to_list(500)
    
    # Recupera presenze del mese
    data_inizio = f"{anno}-{mese:02d}-01"
    if mese == 12:
        data_fine = f"{anno + 1}-01-01"
    else:
        data_fine = f"{anno}-{mese + 1:02d}-01"
    
    presenze_raw = await db["attendance_presenze_calendario"].find(
        {"data": {"$gte": data_inizio, "$lt": data_fine}},
        {"_id": 0}
    ).to_list(10000)
    
    presenze = {}
    dipendenti_con_presenze = set()  # Track which employees have attendance data
    for p in presenze_raw:
        emp_id = p["employee_id"]
        data_val = p["data"]
        key = f"{emp_id}_{data_val}"
        presenze[key] = p.get("stato")
        dipendenti_con_presenze.add(emp_id)  # Mark this employee has data
    
    # Filter dipendenti to only those with attendance data
    dipendenti = [d for d in dipendenti if d.get("id") in dipendenti_con_presenze]
    
    # Recupera note (protocolli malattia)
    note_raw = await db["attendance_note_presenze"].find(
        {"data": {"$gte": data_inizio, "$lt": data_fine}},
        {"_id": 0}
    ).to_list(1000)
    
    note = {}
    for n in note_raw:
        emp_id = n["employee_id"]
        data_val = n["data"]
        key = f"{emp_id}_{data_val}"
        note[key] = n
    
    # Recupera acconti del mese
    acconti_raw = await db["acconti_dipendenti"].find(
        {"anno": anno, "mese": mese},
        {"_id": 0}
    ).to_list(500)
    
    acconti = {a.get("employee_id"): a.get("importo", 0) for a in acconti_raw}
    
    # Calcola giorni del mese
    giorni_mese = calendar.monthrange(anno, mese)[1]
    
    # Genera PDF
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, 
        pagesize=landscape(A4),
        leftMargin=10*mm, 
        rightMargin=10*mm,
        topMargin=15*mm, 
        bottomMargin=15*mm
    )
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "Title", 
        parent=styles["Heading1"],
        fontSize=16, 
        alignment=TA_CENTER, 
        spaceAfter=10
    )
    subtitle_style = ParagraphStyle(
        "Subtitle", 
        parent=styles["Normal"],
        fontSize=10, 
        alignment=TA_CENTER, 
        spaceAfter=15
    )
    
    elements = []
    
    # Titolo
    elements.append(Paragraph(f"RIEPILOGO PRESENZE - {MESI[mese-1].upper()} {anno}", title_style))
    elements.append(Paragraph(f"Generato il {datetime.now().strftime('%d/%m/%Y %H:%M')}", subtitle_style))
    
    # Header tabella - include tutti gli stati + totali retribuiti/non retribuiti
    header = ["Dipendente"] + [str(g) for g in range(1, giorni_mese + 1)] + [
        "P", "A", "F", "PE", "M", "R", "CH", "RS", "T", "X", "-", "FL", "FNL", "Retr", "NoRetr", "Acc.€"
    ]
    
    # Mappa stati a label
    stato_label = {
        "presente": "P", 
        "assente": "A", 
        "ferie": "F", 
        "permesso": "PE",
        "malattia": "M", 
        "rol": "R", 
        "chiuso": "CH",
        "riposo_settimanale": "RS",
        "trasferta": "T", 
        "cessato": "X",
        "riposo": "-",
        "festivita_lavorata": "FL",
        "festivita_non_lavorata": "FNL"
    }
    
    # Stati retribuiti: P, F, PE, M, R, T, FL, FNL
    stati_retribuiti = {"P", "F", "PE", "M", "R", "T", "FL", "FNL"}
    # Stati NON retribuiti: A, CH, RS, X, -
    stati_non_retribuiti = {"A", "CH", "RS", "X", "-"}
    
    table_data = [header]
    note_malattia_list = []
    
    for dip in dipendenti:
        emp_id = dip.get("id")
        nome_val = dip.get("nome", "")
        cognome_val = dip.get("cognome", "")
        nome = dip.get("nome_completo") or dip.get("name") or f"{nome_val} {cognome_val}".strip()
        
        row = [nome[:20]]
        totali = {
            "P": 0, "A": 0, "F": 0, "PE": 0, "M": 0, "R": 0, 
            "CH": 0, "RS": 0, "T": 0, "X": 0, "-": 0, "FL": 0, "FNL": 0
        }
        
        for g in range(1, giorni_mese + 1):
            data_str = f"{anno}-{mese:02d}-{g:02d}"
            key = f"{emp_id}_{data_str}"
            stato = presenze.get(key, "")
            label = stato_label.get(stato, "-")
            row.append(label)
            
            # Conta per stato
            if label in totali:
                totali[label] += 1
            
            # Gestione note malattia
            if label == "M":
                nota = note.get(key)
                if nota and nota.get("protocollo_malattia"):
                    note_malattia_list.append({
                        "dipendente": nome,
                        "data": f"{g:02d}/{mese:02d}/{anno}",
                        "protocollo": nota.get("protocollo_malattia")
                    })
        
        # Calcola giorni retribuiti e non retribuiti
        giorni_retribuiti = sum(totali[s] for s in stati_retribuiti if s in totali)
        giorni_non_retribuiti = sum(totali[s] for s in stati_non_retribuiti if s in totali)
        
        # SKIP dipendenti con solo trattini (nessun dato reale)
        # Un dipendente "in carico" deve avere almeno 1 giorno retribuito o assente/malattia
        ha_dati_reali = (giorni_retribuiti > 0) or (totali["A"] > 0) or (totali["CH"] > 0)
        if not ha_dati_reali:
            continue  # Salta questo dipendente - ha solo riposo/trattini
        
        acconto = acconti.get(emp_id, 0)
        row.extend([
            str(totali["P"]) if totali["P"] else "-",
            str(totali["A"]) if totali["A"] else "-",
            str(totali["F"]) if totali["F"] else "-",
            str(totali["PE"]) if totali["PE"] else "-",
            str(totali["M"]) if totali["M"] else "-",
            str(totali["R"]) if totali["R"] else "-",
            str(totali["CH"]) if totali["CH"] else "-",
            str(totali["RS"]) if totali["RS"] else "-",
            str(totali["T"]) if totali["T"] else "-",
            str(totali["X"]) if totali["X"] else "-",
            str(totali["-"]) if totali["-"] else "-",
            str(totali["FL"]) if totali["FL"] else "-",
            str(totali["FNL"]) if totali["FNL"] else "-",
            str(giorni_retribuiti),
            str(giorni_non_retribuiti),
            f"{acconto:.0f}" if acconto else "-"
        ])
        table_data.append(row)
    
    # Crea tabella - colonne aggiornate per tutti gli stati
    # Dipendente + giorni + 13 stati + Retr + NoRetr + Acconto
    col_widths = [45*mm] + [5*mm] * giorni_mese + [6*mm] * 13 + [8*mm, 8*mm, 12*mm]
    
    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a5f")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("FONTSIZE", (0, 0), (0, -1), 8),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    
    elements.append(table)
    
    # Sezione Protocolli Malattia
    if note_malattia_list:
        elements.append(Spacer(1, 15*mm))
        elements.append(Paragraph("PROTOCOLLI CERTIFICATI MALATTIA", title_style))
        
        note_header = ["Dipendente", "Data", "N. Protocollo INPS"]
        note_data = [note_header]
        for nm in note_malattia_list:
            note_data.append([nm["dipendente"], nm["data"], nm["protocollo"]])
        
        note_table = Table(note_data, colWidths=[80*mm, 40*mm, 80*mm])
        note_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#3b82f6")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ]))
        elements.append(note_table)
    
    # Legenda
    elements.append(Spacer(1, 10*mm))
    legenda = Paragraph(
        "<b>Legenda:</b> P=Presente, F=Ferie, M=Malattia, PE=Permesso, R=ROL, CH=Chiuso, RS=Riposo Sett., T=Trasferta, A=Assente, X=Cessato",
        ParagraphStyle("Legenda", fontSize=8, textColor=colors.grey)
    )
    elements.append(legenda)
    
    # Build PDF
    doc.build(elements)
    buffer.seek(0)
    
    filename = f"Presenze_{MESI[mese-1]}_{anno}.pdf"
    
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
