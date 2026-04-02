"""
IVA Calcolo Router - Calcoli IVA giornalieri, mensili e annuali.

LOGICA CALCOLO IVA (secondo Agenzia delle Entrate):
=====================================================

1. IVA a DEBITO (da versare all'Erario):
   - Somma dell'IVA su tutti i CORRISPETTIVI del periodo
   - I corrispettivi sono le vendite al pubblico (scontrini/ricevute)

2. IVA a CREDITO (da detrarre):
   - Somma dell'IVA su tutte le FATTURE di ACQUISTO ricevute nel periodo
   - La data rilevante è la DATA DI RICEZIONE (data SDI), non la data di emissione
   - Le Note Credito (TD04, TD08) devono essere SOTTRATTE dal totale

3. SALDO IVA:
   - Saldo = IVA Debito - IVA Credito
   - Se positivo -> IVA da VERSARE
   - Se negativo -> IVA a CREDITO (da riportare o chiedere rimborso)

TIPI DOCUMENTO FatturaPA:
- TD01: Fattura
- TD02: Acconto/Anticipo su fattura  
- TD04: Nota di Credito <- DA SOTTRARRE
- TD06: Parcella
- TD08: Nota di Credito Semplificata <- DA SOTTRARRE
- TD24: Fattura Differita

Riferimenti normativi:
- Art. 1 DPR 100/1998
- Art. 19 DPR 633/1972
"""
from fastapi import APIRouter, HTTPException
from typing import Dict, Any
from datetime import date
from calendar import monthrange
import logging

from app.database import Database
from app.utils.error_handler import handle_errors

logger = logging.getLogger(__name__)
router = APIRouter()

# Tipi documento che sono Note Credito (da sottrarre)
NOTE_CREDITO_TYPES = ["TD04", "TD08"]

MESI_ITALIANI = ["", "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
                 "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"]


def format_date_italian(date_str: str) -> str:
    """Converte data ISO in formato italiano gg/mm/aaaa."""
    if not date_str:
        return ""
    try:
        if "T" in date_str:
            date_str = date_str.split("T")[0]
        parts = date_str.split("-")
        if len(parts) == 3:
            return f"{parts[2]}/{parts[1]}/{parts[0]}"
        return date_str
    except (ValueError, TypeError, IndexError):
        return date_str


@router.get("/daily/{date}")
@handle_errors
async def get_iva_daily(date_param: str) -> Dict[str, Any]:
    """IVA giornaliera: debito (corrispettivi) vs credito (fatture).
    
    IMPORTANTE: Usa data_ricezione per le fatture (data SDI), non invoice_date.
    Le Note Credito (TD04, TD08) vengono SOTTRATTE dal totale IVA.
    """
    db = Database.get_db()
    
    try:
        # IVA DEBITO - Corrispettivi
        corrispettivi = await db["corrispettivi"].find({"data": date_param}, {"_id": 0}).to_list(1000)
        iva_debito = sum(float(c.get('totale_iva', 0) or 0) for c in corrispettivi)
        totale_corr = sum(float(c.get('totale', 0) or 0) for c in corrispettivi)
        
        # IVA CREDITO - Fatture RICEVUTE nel giorno (usa data_ricezione, fallback a invoice_date)
        fatture = await db["invoices"].find({
            "$or": [
                {"data_ricezione": date_param},
                {"$and": [{"data_ricezione": {"$exists": False}}, {"invoice_date": date_param}]}
            ]
        }, {"_id": 0}).to_list(1000)
        
        iva_credito = 0
        iva_note_credito = 0
        imponibile_fatture = 0
        imponibile_note_credito = 0
        fatture_details = []
        note_credito_details = []
        
        for f in fatture:
            tipo_doc = f.get('tipo_documento', '')
            is_nota_credito = tipo_doc in NOTE_CREDITO_TYPES
            
            # Usa riepilogo_iva se disponibile (più accurato)
            riepilogo = f.get('riepilogo_iva', [])
            f_iva = 0
            imponibile = 0
            
            if riepilogo:
                for r in riepilogo:
                    # Escludi operazioni con natura (esenti, non imponibili, etc.)
                    if r.get('natura'):
                        continue
                    f_iva += float(r.get('imposta', 0) or 0)
                    imponibile += float(r.get('imponibile', 0) or 0)
            else:
                # Fallback: usa campi diretti
                f_iva = float(f.get('iva', 0) or f.get('vat_amount', 0) or 0)
                imponibile = float(f.get('imponibile', 0) or f.get('taxable_amount', 0) or 0)
                total = float(f.get('total_amount', 0) or f.get('importo_totale', 0) or 0)
                
                # Fallback: stima IVA da aliquota fattura o 22% ordinaria per acquisti
                aliquota = float(f.get('aliquota_iva', 0) or f.get('vat_rate', 0) or 22)
                divisore = 1 + aliquota / 100
                if f_iva == 0 and total > 0:
                    f_iva = total - (total / divisore)
                if imponibile == 0 and total > 0:
                    imponibile = total / divisore
            
            total = float(f.get('total_amount', 0) or f.get('importo_totale', 0) or 0)
            
            detail = {
                "invoice_number": f.get('invoice_number'),
                "supplier_name": f.get('supplier_name', f.get('cedente_denominazione', '')),
                "total_amount": round(total, 2),
                "imponibile": round(imponibile, 2),
                "iva": round(f_iva, 2),
                "tipo_documento": tipo_doc,
                "is_nota_credito": is_nota_credito
            }
            
            if is_nota_credito:
                # Note Credito: da SOTTRARRE
                iva_note_credito += f_iva
                imponibile_note_credito += imponibile
                note_credito_details.append(detail)
            else:
                # Fatture normali: da SOMMARE
                iva_credito += f_iva
                imponibile_fatture += imponibile
                fatture_details.append(detail)
        
        # IVA Credito Netta = Fatture - Note Credito
        iva_credito_netta = iva_credito - iva_note_credito
        imponibile_netto = imponibile_fatture - imponibile_note_credito
        saldo = iva_debito - iva_credito_netta
        
        return {
            "data": format_date_italian(date_param),
            "data_iso": date_param,
            "iva_debito": round(iva_debito, 2),
            "iva_credito_lordo": round(iva_credito, 2),
            "iva_note_credito": round(iva_note_credito, 2),
            "iva_credito": round(iva_credito_netta, 2),  # IVA netta (fatture - note credito)
            "imponibile_fatture": round(imponibile_fatture, 2),
            "imponibile_note_credito": round(imponibile_note_credito, 2),
            "imponibile_netto": round(imponibile_netto, 2),
            "saldo": round(saldo, 2),
            "stato": "Da versare" if saldo > 0 else "A credito" if saldo < 0 else "Pareggio",
            "corrispettivi": {"count": len(corrispettivi), "totale": round(totale_corr, 2)},
            "fatture": {"count": len(fatture_details), "items": fatture_details},
            "note_credito": {"count": len(note_credito_details), "items": note_credito_details}
        }
    except Exception as e:
        logger.error(f"Errore IVA giornaliera: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/monthly/{year}/{month}")
@handle_errors
async def get_iva_monthly(year: int, month: int) -> Dict[str, Any]:
    """IVA progressiva giornaliera per mese.
    
    OTTIMIZZATO: Usa aggregazioni MongoDB invece di query giornaliere.
    Le Note Credito (TD04, TD08) vengono SOTTRATTE dal totale IVA credito.
    """
    db = Database.get_db()
    
    try:
        _, num_days = monthrange(year, month)
        month_prefix = f"{year}-{month:02d}"
        
        # STEP 1: Aggregazione corrispettivi per giorno (1 query invece di 31)
        corr_pipeline = [
            {"$match": {"data": {"$regex": f"^{month_prefix}"}}},
            {"$group": {
                "_id": {"$substr": ["$data", 8, 2]},  # Estrai giorno dalla data YYYY-MM-DD
                "iva_debito": {"$sum": {"$toDouble": {"$ifNull": ["$totale_iva", 0]}}}
            }}
        ]
        corr_by_day = {r["_id"]: r["iva_debito"] for r in await db["corrispettivi"].aggregate(corr_pipeline).to_list(100)}
        
        # STEP 2: Carica tutte le fatture del mese in una sola query
        fatture_match = {
            "$or": [
                {"data_ricezione": {"$regex": f"^{month_prefix}"}},
                {"$and": [
                    {"data_ricezione": {"$exists": False}},
                    {"invoice_date": {"$regex": f"^{month_prefix}"}}
                ]}
            ]
        }
        fatture_projection = {
            "_id": 0, "data_ricezione": 1, "invoice_date": 1, "tipo_documento": 1,
            "riepilogo_iva": 1, "iva": 1, "vat_amount": 1, "imponibile": 1,
            "taxable_amount": 1, "total_amount": 1, "importo_totale": 1
        }
        fatture = await db["invoices"].find(fatture_match, fatture_projection).to_list(5000)
        
        # STEP 3: Raggruppa fatture per giorno in memoria (molto più veloce)
        fatture_by_day = {}
        for f in fatture:
            # Determina la data effettiva
            data_eff = f.get("data_ricezione") or f.get("invoice_date") or ""
            if not data_eff.startswith(month_prefix):
                continue
            giorno = data_eff[8:10] if len(data_eff) >= 10 else "01"
            
            if giorno not in fatture_by_day:
                fatture_by_day[giorno] = []
            fatture_by_day[giorno].append(f)
        
        # STEP 4: Calcola IVA per ogni giorno
        daily_data = []
        iva_debito_prog = 0
        iva_credito_prog = 0
        iva_note_credito_prog = 0
        imponibile_prog = 0
        imponibile_nc_prog = 0
        
        for day in range(1, num_days + 1):
            day_str = f"{day:02d}"
            
            # IVA Debito da corrispettivi
            iva_deb = corr_by_day.get(day_str, 0)
            
            # IVA Credito da fatture
            iva_cred = 0
            iva_nc = 0
            imponibile = 0
            imponibile_nc = 0
            
            for f in fatture_by_day.get(day_str, []):
                tipo_doc = f.get('tipo_documento', '')
                is_nota_credito = tipo_doc in NOTE_CREDITO_TYPES
                
                # Calcola IVA dalla fattura
                riepilogo = f.get('riepilogo_iva', [])
                f_iva = 0
                f_imponibile = 0
                
                if riepilogo:
                    for r in riepilogo:
                        if r.get('natura'):
                            continue
                        f_iva += float(r.get('imposta', 0) or 0)
                        f_imponibile += float(r.get('imponibile', 0) or 0)
                else:
                    f_iva = float(f.get('iva', 0) or f.get('vat_amount', 0) or 0)
                    f_imponibile = float(f.get('imponibile', 0) or f.get('taxable_amount', 0) or 0)
                    total = float(f.get('total_amount', 0) or f.get('importo_totale', 0) or 0)
                    
                    aliquota = float(f.get('aliquota_iva', 0) or f.get('vat_rate', 0) or 22)
                    divisore = 1 + aliquota / 100
                    if f_iva == 0 and total > 0:
                        f_iva = total - (total / divisore)
                    if f_imponibile == 0 and total > 0:
                        f_imponibile = total / divisore
                
                if is_nota_credito:
                    iva_nc += f_iva
                    imponibile_nc += f_imponibile
                else:
                    iva_cred += f_iva
                    imponibile += f_imponibile
            
            # IVA Credito Netta del giorno
            iva_cred_netta = iva_cred - iva_nc
            imponibile_netto = imponibile - imponibile_nc
            
            iva_debito_prog += iva_deb
            iva_credito_prog += iva_cred_netta
            iva_note_credito_prog += iva_nc
            imponibile_prog += imponibile
            imponibile_nc_prog += imponibile_nc
            
            daily_data.append({
                "data": f"{day:02d}/{month:02d}/{year}",
                "giorno": day,
                "iva_debito": round(iva_deb, 2),
                "iva_credito_lordo": round(iva_cred, 2),
                "iva_note_credito": round(iva_nc, 2),
                "iva_credito": round(iva_cred_netta, 2),
                "imponibile": round(imponibile, 2),
                "imponibile_nc": round(imponibile_nc, 2),
                "imponibile_netto": round(imponibile_netto, 2),
                "saldo": round(iva_deb - iva_cred_netta, 2),
                "iva_debito_progressiva": round(iva_debito_prog, 2),
                "iva_credito_progressiva": round(iva_credito_prog, 2),
                "saldo_progressivo": round(iva_debito_prog - iva_credito_prog, 2),
                "has_data": iva_deb > 0 or iva_cred > 0 or iva_nc > 0
            })
        
        return {
            "anno": year,
            "mese": month,
            "mese_nome": MESI_ITALIANI[month],
            "daily_data": daily_data,
            "totale_mensile": {
                "iva_debito": round(iva_debito_prog, 2),
                "iva_credito_lordo": round(iva_credito_prog + iva_note_credito_prog, 2),
                "iva_note_credito": round(iva_note_credito_prog, 2),
                "iva_credito": round(iva_credito_prog, 2),
                "imponibile_fatture": round(imponibile_prog, 2),
                "imponibile_note_credito": round(imponibile_nc_prog, 2),
                "imponibile_netto": round(imponibile_prog - imponibile_nc_prog, 2),
                "saldo": round(iva_debito_prog - iva_credito_prog, 2)
            }
        }
    except Exception as e:
        logger.error(f"Errore IVA mensile: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/annual/{year}")
@handle_errors
async def get_iva_annual(year: int) -> Dict[str, Any]:
    """Riepilogo IVA annuale.
    
    Le Note Credito (TD04, TD08) vengono SOTTRATTE dal totale IVA credito.
    """
    db = Database.get_db()
    
    # Tipi documento Note Credito
    NOTE_CREDITO_TYPES = ["TD04", "TD08"]
    
    try:
        monthly_data = []
        
        for month in range(1, 13):
            month_prefix = f"{year}-{month:02d}"
            
            # Fatture normali (credito) - usa data_ricezione con fallback a invoice_date
            fatt_pipe = [
                {"$match": {
                    "$or": [
                        {"data_ricezione": {"$regex": f"^{month_prefix}"}},
                        {"$and": [
                            {"data_ricezione": {"$exists": False}},
                            {"invoice_date": {"$regex": f"^{month_prefix}"}}
                        ]}
                    ],
                    "tipo_documento": {"$nin": NOTE_CREDITO_TYPES}
                }},
                {"$group": {
                    "_id": None, 
                    "total_iva": {"$sum": "$iva"}, 
                    "total_amount": {"$sum": "$total_amount"},
                    "total_imponibile": {"$sum": "$imponibile"},
                    "count": {"$sum": 1}
                }}
            ]
            fatt_res = await db["invoices"].aggregate(fatt_pipe).to_list(1)
            
            if fatt_res:
                iva_cred = float(fatt_res[0].get('total_iva', 0) or 0)
                tot_fatt = float(fatt_res[0].get('total_amount', 0) or 0)
                imponibile_fatt = float(fatt_res[0].get('total_imponibile', 0) or 0)
                fatt_count = fatt_res[0].get('count', 0)
                # NON stimare IVA - usa solo i valori dal DB
            else:
                iva_cred, fatt_count, imponibile_fatt, tot_fatt = 0, 0, 0, 0
            
            # Note Credito (da sottrarre) - usa data_ricezione con fallback
            nc_pipe = [
                {"$match": {
                    "$or": [
                        {"data_ricezione": {"$regex": f"^{month_prefix}"}},
                        {"$and": [
                            {"data_ricezione": {"$exists": False}},
                            {"invoice_date": {"$regex": f"^{month_prefix}"}}
                        ]}
                    ],
                    "tipo_documento": {"$in": NOTE_CREDITO_TYPES}
                }},
                {"$group": {
                    "_id": None, 
                    "total_iva": {"$sum": "$iva"}, 
                    "total_amount": {"$sum": "$total_amount"},
                    "total_imponibile": {"$sum": "$imponibile"},
                    "count": {"$sum": 1}
                }}
            ]
            nc_res = await db["invoices"].aggregate(nc_pipe).to_list(1)
            
            if nc_res:
                iva_nc = float(nc_res[0].get('total_iva', 0) or 0)
                tot_nc = float(nc_res[0].get('total_amount', 0) or 0)
                imponibile_nc = float(nc_res[0].get('total_imponibile', 0) or 0)
                nc_count = nc_res[0].get('count', 0)
            else:
                iva_nc, nc_count, imponibile_nc, tot_nc = 0, 0, 0, 0
            
            # Corrispettivi (debito)
            corr_pipe = [
                {"$match": {"data": {"$regex": f"^{month_prefix}"}}},
                {"$group": {"_id": None, "total_iva": {"$sum": "$totale_iva"}, "count": {"$sum": 1}}}
            ]
            corr_res = await db["corrispettivi"].aggregate(corr_pipe).to_list(1)
            
            iva_deb = float(corr_res[0].get('total_iva', 0) or 0) if corr_res else 0
            corr_count = corr_res[0].get('count', 0) if corr_res else 0
            
            # IVA Credito Netta = Fatture - Note Credito
            iva_cred_netta = iva_cred - iva_nc
            imponibile_netto = imponibile_fatt - imponibile_nc
            saldo = iva_deb - iva_cred_netta
            
            monthly_data.append({
                "mese": month,
                "mese_nome": MESI_ITALIANI[month],
                "iva_credito_lordo": round(iva_cred, 2),
                "iva_note_credito": round(iva_nc, 2),
                "iva_credito": round(iva_cred_netta, 2),  # Netto
                "iva_debito": round(iva_deb, 2),
                "imponibile_fatture": round(imponibile_fatt, 2),
                "imponibile_note_credito": round(imponibile_nc, 2),
                "imponibile_netto": round(imponibile_netto, 2),
                "saldo": round(saldo, 2),
                "stato": "Da versare" if saldo > 0 else "A credito" if saldo < 0 else "Pareggio",
                "fatture_count": fatt_count,
                "note_credito_count": nc_count,
                "corrispettivi_count": corr_count
            })
        
        tot_cred = sum(m['iva_credito'] for m in monthly_data)
        tot_nc = sum(m['iva_note_credito'] for m in monthly_data)
        tot_deb = sum(m['iva_debito'] for m in monthly_data)
        tot_saldo = tot_deb - tot_cred
        
        return {
            "anno": year,
            "monthly_data": monthly_data,
            "totali": {
                "iva_credito_lordo": round(tot_cred + tot_nc, 2),
                "iva_note_credito": round(tot_nc, 2),
                "iva_credito": round(tot_cred, 2),  # Netto
                "iva_debito": round(tot_deb, 2),
                "saldo": round(tot_saldo, 2),
                "stato": "Da versare" if tot_saldo > 0 else "A credito"
            }
        }
    except Exception as e:
        logger.error(f"Errore IVA annuale: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/today")
@handle_errors
async def get_iva_today() -> Dict[str, Any]:
    """IVA di oggi."""
    today = date.today().isoformat()
    return await get_iva_daily(today)



# ============== EXPORT PDF IVA ==============

from fastapi.responses import StreamingResponse
import io
from app.utils.error_handler import handle_errors

@router.get("/export/pdf/trimestrale/{year}/{quarter}")
@handle_errors
async def export_iva_trimestrale_pdf(year: int, quarter: int) -> StreamingResponse:
    """
    Esporta il riepilogo IVA trimestrale in PDF.
    
    Args:
        year: Anno (es. 2025)
        quarter: Trimestre (1-4)
    
    Returns:
        PDF con riepilogo IVA trimestrale
    """
    if quarter < 1 or quarter > 4:
        raise HTTPException(status_code=400, detail="Trimestre deve essere 1-4")
    
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.units import cm
    except ImportError:
        raise HTTPException(status_code=500, detail="reportlab non installato. Esegui: pip install reportlab")
    
    # Calcola mesi del trimestre
    start_month = (quarter - 1) * 3 + 1
    end_month = quarter * 3
    trimestre_nome = f"Q{quarter} {year} ({MESI_ITALIANI[start_month]} - {MESI_ITALIANI[end_month]})"
    
    # Raccogli dati IVA per ogni mese del trimestre
    db = Database.get_db()
    monthly_data = []
    tot_debito = 0
    tot_credito = 0
    tot_nc = 0
    
    for month in range(start_month, end_month + 1):
        month_prefix = f"{year}-{month:02d}"
        
        # Corrispettivi (IVA Debito)
        corr_result = await db["corrispettivi"].aggregate([
            {"$match": {"data": {"$regex": f"^{month_prefix}"}}},
            {"$group": {"_id": None, "total_iva": {"$sum": "$totale_iva"}, "totale": {"$sum": "$totale"}}}
        ]).to_list(1)
        iva_deb = corr_result[0].get("total_iva", 0) if corr_result else 0
        
        # Fatture normali (IVA Credito)
        fatt_result = await db["invoices"].aggregate([
            {"$match": {
                "$or": [
                    {"data_ricezione": {"$regex": f"^{month_prefix}"}},
                    {"$and": [
                        {"data_ricezione": {"$exists": False}},
                        {"invoice_date": {"$regex": f"^{month_prefix}"}}
                    ]}
                ],
                "tipo_documento": {"$nin": NOTE_CREDITO_TYPES}
            }},
            {"$group": {"_id": None, "total_iva": {"$sum": "$iva"}}}
        ]).to_list(1)
        iva_cred = fatt_result[0].get("total_iva", 0) if fatt_result else 0
        
        # Note Credito (da sottrarre)
        nc_result = await db["invoices"].aggregate([
            {"$match": {
                "$or": [
                    {"data_ricezione": {"$regex": f"^{month_prefix}"}},
                    {"$and": [
                        {"data_ricezione": {"$exists": False}},
                        {"invoice_date": {"$regex": f"^{month_prefix}"}}
                    ]}
                ],
                "tipo_documento": {"$in": NOTE_CREDITO_TYPES}
            }},
            {"$group": {"_id": None, "total_iva": {"$sum": "$iva"}}}
        ]).to_list(1)
        iva_nc = nc_result[0].get("total_iva", 0) if nc_result else 0
        
        iva_cred_netta = iva_cred - iva_nc
        saldo = iva_deb - iva_cred_netta
        
        monthly_data.append({
            "mese": MESI_ITALIANI[month],
            "iva_debito": round(iva_deb, 2),
            "iva_credito": round(iva_cred_netta, 2),
            "iva_nc": round(iva_nc, 2),
            "saldo": round(saldo, 2)
        })
        
        tot_debito += iva_deb
        tot_credito += iva_cred_netta
        tot_nc += iva_nc
    
    # Genera PDF
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=2*cm, bottomMargin=2*cm)
    elements = []
    styles = getSampleStyleSheet()
    
    # Titolo
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=18, textColor=colors.HexColor('#1e40af'), spaceAfter=20)
    elements.append(Paragraph("📊 Riepilogo IVA Trimestrale", title_style))
    elements.append(Paragraph(f"<b>{trimestre_nome}</b>", styles['Heading2']))
    elements.append(Spacer(1, 20))
    
    # Tabella dati mensili
    table_data = [["Mese", "IVA Debito", "IVA Credito", "Note Credito", "Saldo"]]
    for m in monthly_data:
        stato = "📈" if m['saldo'] > 0 else "📉"
        table_data.append([
            m['mese'],
            f"€ {m['iva_debito']:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
            f"€ {m['iva_credito']:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
            f"€ {m['iva_nc']:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
            f"{stato} € {m['saldo']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        ])
    
    # Riga totali
    saldo_totale = tot_debito - tot_credito
    stato_totale = "DA VERSARE" if saldo_totale > 0 else "A CREDITO"
    table_data.append([
        "TOTALE TRIMESTRE",
        f"€ {tot_debito:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
        f"€ {tot_credito:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
        f"€ {tot_nc:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
        f"€ {abs(saldo_totale):,.2f} ({stato_totale})".replace(",", "X").replace(".", ",").replace("X", ".")
    ])
    
    table = Table(table_data, colWidths=[4*cm, 3.5*cm, 3.5*cm, 3.5*cm, 4*cm])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e40af')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#f0f9ff')),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e5e7eb')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#f8fafc')])
    ]))
    elements.append(table)
    
    elements.append(Spacer(1, 30))
    
    # Box riepilogativo
    summary_style = ParagraphStyle('Summary', parent=styles['Normal'], fontSize=12, leading=18)
    if saldo_totale > 0:
        summary = f"""
        <b>📋 Riepilogo Trimestrale:</b><br/>
        • IVA a Debito (Corrispettivi): <b>€ {tot_debito:,.2f}</b><br/>
        • IVA a Credito (Fatture): <b>€ {tot_credito:,.2f}</b><br/>
        • Note Credito: <b>€ {tot_nc:,.2f}</b><br/><br/>
        <font color="red"><b>⚠️ IVA DA VERSARE: € {saldo_totale:,.2f}</b></font><br/>
        <i>Da versare entro il 16 del mese successivo al trimestre</i>
        """.replace(",", "X").replace(".", ",").replace("X", ".")
    else:
        summary = f"""
        <b>📋 Riepilogo Trimestrale:</b><br/>
        • IVA a Debito (Corrispettivi): <b>€ {tot_debito:,.2f}</b><br/>
        • IVA a Credito (Fatture): <b>€ {tot_credito:,.2f}</b><br/>
        • Note Credito: <b>€ {tot_nc:,.2f}</b><br/><br/>
        <font color="green"><b>✅ IVA A CREDITO: € {abs(saldo_totale):,.2f}</b></font><br/>
        <i>Credito da riportare al periodo successivo o richiedere rimborso</i>
        """.replace(",", "X").replace(".", ",").replace("X", ".")
    
    elements.append(Paragraph(summary, summary_style))
    
    # Footer
    elements.append(Spacer(1, 40))
    footer_style = ParagraphStyle('Footer', parent=styles['Normal'], fontSize=9, textColor=colors.gray)
    from datetime import datetime
    elements.append(Paragraph(f"Documento generato il {datetime.now().strftime('%d/%m/%Y %H:%M')} - Azienda Semplice ERP", footer_style))
    
    doc.build(elements)
    buffer.seek(0)
    
    filename = f"IVA_Trimestrale_Q{quarter}_{year}.pdf"
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/export/pdf/annuale/{year}")
@handle_errors
async def export_iva_annuale_pdf(year: int) -> StreamingResponse:
    """Esporta il riepilogo IVA annuale completo in PDF."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.units import cm
    except ImportError:
        raise HTTPException(status_code=500, detail="reportlab non installato")
    
    # Ottieni dati annuali
    annual_data = await get_iva_annual(year)
    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=2*cm, bottomMargin=2*cm)
    elements = []
    styles = getSampleStyleSheet()
    
    # Titolo
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=18, textColor=colors.HexColor('#1e40af'), spaceAfter=20)
    elements.append(Paragraph(f"📊 Riepilogo IVA Annuale {year}", title_style))
    elements.append(Spacer(1, 20))
    
    # Tabella mensile
    table_data = [["Mese", "IVA Debito", "IVA Credito", "Note Credito", "Saldo"]]
    for m in annual_data['monthly_data']:
        stato = "📈" if m['saldo'] > 0 else "📉"
        table_data.append([
            m['mese'],
            f"€ {m['iva_debito']:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
            f"€ {m['iva_credito']:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
            f"€ {m['iva_note_credito']:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
            f"{stato} € {m['saldo']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        ])
    
    # Totali
    tot = annual_data['totali']
    table_data.append([
        "TOTALE ANNO",
        f"€ {tot['iva_debito']:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
        f"€ {tot['iva_credito']:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
        f"€ {tot['iva_note_credito']:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
        f"€ {abs(tot['saldo']):,.2f} ({tot['stato']})".replace(",", "X").replace(".", ",").replace("X", ".")
    ])
    
    table = Table(table_data, colWidths=[3.5*cm, 3.2*cm, 3.2*cm, 3.2*cm, 4*cm])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e40af')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#f0f9ff')),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e5e7eb')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#f8fafc')])
    ]))
    elements.append(table)
    
    # Footer
    elements.append(Spacer(1, 40))
    footer_style = ParagraphStyle('Footer', parent=styles['Normal'], fontSize=9, textColor=colors.gray)
    from datetime import datetime
    elements.append(Paragraph(f"Documento generato il {datetime.now().strftime('%d/%m/%Y %H:%M')} - Azienda Semplice ERP", footer_style))
    
    doc.build(elements)
    buffer.seek(0)
    
    filename = f"IVA_Annuale_{year}.pdf"
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
