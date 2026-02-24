"""
Report PDF Router - Generazione report PDF mensili e annuali.
"""
from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from datetime import datetime, timedelta
from io import BytesIO
import logging

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.enums import TA_CENTER

from app.database import Database, Collections

logger = logging.getLogger(__name__)
router = APIRouter()

# Stili personalizzati
def get_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name='TitleCustom',
        parent=styles['Heading1'],
        fontSize=18,
        spaceAfter=20,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#1e293b')
    ))
    styles.add(ParagraphStyle(
        name='SubtitleCustom',
        parent=styles['Heading2'],
        fontSize=14,
        spaceAfter=10,
        textColor=colors.HexColor('#475569')
    ))
    styles.add(ParagraphStyle(
        name='SectionTitle',
        parent=styles['Heading3'],
        fontSize=12,
        spaceBefore=15,
        spaceAfter=8,
        textColor=colors.HexColor('#0f172a'),
        backColor=colors.HexColor('#f1f5f9')
    ))
    return styles


def format_euro(value):
    """Formatta valore in euro."""
    if value is None:
        return "€ 0,00"
    return f"€ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def format_date_it(date_str):
    """Formatta data in italiano."""
    if not date_str:
        return "-"
    try:
        if isinstance(date_str, str):
            dt = datetime.fromisoformat(date_str.replace("Z", ""))
        else:
            dt = date_str
        return dt.strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        return str(date_str)[:10] if date_str else "-"


@router.get("/mensile")
async def generate_report_mensile(
    anno: int = Query(..., description="Anno"),
    mese: int = Query(..., description="Mese (1-12)")
):
    """
    Genera report PDF mensile con:
    - Riepilogo fatture
    - Riepilogo corrispettivi
    - Calcolo IVA
    - Movimenti cassa/banca
    - Scadenze
    """
    db = Database.get_db()
    
    # Calcola periodo
    mese_str = f"{anno}-{mese:02d}"
    mese_nome = ["", "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
                 "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"][mese]
    
    # Recupera dati
    # Fatture del mese
    fatture = await db[Collections.INVOICES].find({
        "invoice_date": {"$regex": f"^{mese_str}"}
    }, {"_id": 0}).to_list(1000)
    
    # Corrispettivi del mese
    corrispettivi = await db["corrispettivi"].find({
        "$or": [
            {"data": {"$regex": f"^{mese_str}"}},
            {"data_trasmissione": {"$regex": f"^{mese_str}"}}
        ]
    }, {"_id": 0}).to_list(1000)
    
    # Movimenti cassa
    mov_cassa = await db["prima_nota_cassa"].find({
        "data": {"$regex": f"^{mese_str}"}
    }, {"_id": 0}).to_list(1000)
    
    # Movimenti banca
    mov_banca = await db["prima_nota_banca"].find({
        "data": {"$regex": f"^{mese_str}"}
    }, {"_id": 0}).to_list(1000)
    
    # Calcoli
    totale_fatture = sum(f.get("total_amount", f.get("totale_fattura", 0)) or 0 for f in fatture)
    iva_fatture = sum(f.get("total_tax", f.get("totale_iva", 0)) or 0 for f in fatture)
    
    totale_corrispettivi = sum(c.get("totale", 0) or 0 for c in corrispettivi)
    iva_corrispettivi = sum(c.get("iva", c.get("totale", 0) / 11) or 0 for c in corrispettivi)
    
    entrate_cassa = sum(m.get("importo", 0) for m in mov_cassa if (m.get("importo", 0) or 0) > 0)
    uscite_cassa = sum(abs(m.get("importo", 0)) for m in mov_cassa if (m.get("importo", 0) or 0) < 0)
    
    entrate_banca = sum(m.get("importo", 0) for m in mov_banca if (m.get("importo", 0) or 0) > 0)
    uscite_banca = sum(abs(m.get("importo", 0)) for m in mov_banca if (m.get("importo", 0) or 0) < 0)
    
    # Genera PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=2*cm, bottomMargin=2*cm)
    styles = get_styles()
    elements = []
    
    # Intestazione
    elements.append(Paragraph("REPORT MENSILE", styles['TitleCustom']))
    elements.append(Paragraph(f"{mese_nome} {anno}", styles['SubtitleCustom']))
    elements.append(Spacer(1, 20))
    
    # Sezione Fatture
    elements.append(Paragraph("📄 FATTURE PASSIVE", styles['SectionTitle']))
    fatture_data = [
        ["Descrizione", "Valore"],
        ["Numero fatture", str(len(fatture))],
        ["Totale imponibile", format_euro(totale_fatture - iva_fatture)],
        ["Totale IVA a credito", format_euro(iva_fatture)],
        ["Totale fatture", format_euro(totale_fatture)],
    ]
    t = Table(fatture_data, colWidths=[10*cm, 5*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a5f')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#f0f9ff')),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 15))
    
    # Sezione Corrispettivi
    elements.append(Paragraph("🧾 CORRISPETTIVI", styles['SectionTitle']))
    corr_data = [
        ["Descrizione", "Valore"],
        ["Numero corrispettivi", str(len(corrispettivi))],
        ["Totale incassato", format_euro(totale_corrispettivi)],
        ["IVA a debito (10%)", format_euro(iva_corrispettivi)],
    ]
    t = Table(corr_data, colWidths=[10*cm, 5*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#166534')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 15))
    
    # Sezione IVA
    saldo_iva = iva_corrispettivi - iva_fatture
    elements.append(Paragraph("💰 RIEPILOGO IVA", styles['SectionTitle']))
    iva_data = [
        ["Descrizione", "Valore"],
        ["IVA a debito (vendite)", format_euro(iva_corrispettivi)],
        ["IVA a credito (acquisti)", format_euro(iva_fatture)],
        ["SALDO IVA", format_euro(saldo_iva)],
    ]
    t = Table(iva_data, colWidths=[10*cm, 5*cm])
    bg_saldo = colors.HexColor('#fef2f2') if saldo_iva > 0 else colors.HexColor('#f0fdf4')
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#7c3aed')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('BACKGROUND', (0, -1), (-1, -1), bg_saldo),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 15))
    
    # Sezione Cassa/Banca
    elements.append(Paragraph("🏦 MOVIMENTI FINANZIARI", styles['SectionTitle']))
    fin_data = [
        ["", "Cassa", "Banca", "Totale"],
        ["Entrate", format_euro(entrate_cassa), format_euro(entrate_banca), format_euro(entrate_cassa + entrate_banca)],
        ["Uscite", format_euro(uscite_cassa), format_euro(uscite_banca), format_euro(uscite_cassa + uscite_banca)],
        ["Saldo", format_euro(entrate_cassa - uscite_cassa), format_euro(entrate_banca - uscite_banca), 
         format_euro((entrate_cassa - uscite_cassa) + (entrate_banca - uscite_banca))],
    ]
    t = Table(fin_data, colWidths=[4*cm, 4*cm, 4*cm, 4*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0369a1')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#f0f9ff')),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 20))
    
    # Footer
    elements.append(Paragraph(
        f"Report generato il {datetime.now().strftime('%d/%m/%Y alle %H:%M')}",
        ParagraphStyle(name='Footer', fontSize=8, textColor=colors.gray, alignment=TA_CENTER)
    ))
    
    doc.build(elements)
    buffer.seek(0)
    
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=report_{mese_str}.pdf"}
    )


@router.get("/dipendenti")
async def generate_report_dipendenti(
    anno: int = Query(None, description="Anno (opzionale)"),
    mese: int = Query(None, description="Mese (opzionale)")
):
    """
    Genera report PDF dipendenti con:
    - Anagrafica
    - Contratti attivi
    - Libretti sanitari
    - Buste paga (se specificato mese)
    """
    db = Database.get_db()
    
    # Recupera dati
    dipendenti = await db[Collections.EMPLOYEES].find(
        {"status": {"$in": ["attivo", "active", None]}},
        {"_id": 0}
    ).sort("nome_completo", 1).to_list(500)
    
    contratti = await db["contratti_dipendenti"].find(
        {"stato": "attivo"},
        {"_id": 0}
    ).to_list(500)
    
    libretti = await db["libretti_sanitari"].find({}, {"_id": 0}).to_list(500)
    
    # Mappa per lookup veloce
    contratti_map = {c.get("dipendente_id"): c for c in contratti}
    libretti_map = {lib.get("dipendente_id"): lib for lib in libretti}
    
    # Genera PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=2*cm, bottomMargin=2*cm)
    styles = get_styles()
    elements = []
    
    # Intestazione
    periodo = f" - {mese}/{anno}" if anno and mese else ""
    elements.append(Paragraph(f"REPORT DIPENDENTI{periodo}", styles['TitleCustom']))
    elements.append(Paragraph(f"Totale: {len(dipendenti)} dipendenti attivi", styles['SubtitleCustom']))
    elements.append(Spacer(1, 20))
    
    # Tabella dipendenti
    data = [["Nome", "Mansione", "Contratto", "Libretto Sanitario"]]
    
    for dip in dipendenti:
        nome = dip.get("nome_completo") or f"{dip.get('nome', '')} {dip.get('cognome', '')}".strip()
        mansione = dip.get("mansione", "-")
        
        # Contratto
        contratto = contratti_map.get(dip.get("id"))
        if contratto:
            tipo = contratto.get("tipo_contratto", "").replace("_", " ").title()
            contratto_str = f"{tipo}"
            if contratto.get("data_fine"):
                contratto_str += f" (fino al {format_date_it(contratto.get('data_fine'))})"
        else:
            contratto_str = "Non registrato"
        
        # Libretto
        libretto = libretti_map.get(dip.get("id"))
        if libretto:
            scadenza = libretto.get("data_scadenza")
            if scadenza:
                libretto_str = f"Scade: {format_date_it(scadenza)}"
                if datetime.strptime(scadenza[:10], "%Y-%m-%d") < datetime.now():
                    libretto_str += " ⚠️ SCADUTO"
            else:
                libretto_str = "Da compilare"
        else:
            libretto_str = "Non presente"
        
        data.append([nome, mansione, contratto_str, libretto_str])
    
    t = Table(data, colWidths=[5*cm, 3*cm, 4*cm, 4*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a5f')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(t)
    
    # Footer
    elements.append(Spacer(1, 30))
    elements.append(Paragraph(
        f"Report generato il {datetime.now().strftime('%d/%m/%Y alle %H:%M')}",
        ParagraphStyle(name='Footer', fontSize=8, textColor=colors.gray, alignment=TA_CENTER)
    ))
    
    doc.build(elements)
    buffer.seek(0)
    
    filename = f"report_dipendenti_{anno}_{mese:02d}.pdf" if anno and mese else "report_dipendenti.pdf"
    
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/scadenze")
async def generate_report_scadenze(giorni: int = Query(30, description="Giorni per scadenze")):
    """
    Genera report PDF delle scadenze imminenti:
    - Fatture da pagare
    - Contratti in scadenza
    - Libretti sanitari in scadenza
    - F24 da versare
    """
    db = Database.get_db()
    
    oggi = datetime.now()
    limite = (oggi + timedelta(days=giorni)).strftime('%Y-%m-%d')
    oggi_str = oggi.strftime('%Y-%m-%d')
    
    # Fatture da pagare
    fatture_scadenza = await db[Collections.INVOICES].find({
        "data_scadenza": {"$lte": limite},
        "stato_pagamento": {"$in": ["non_pagata", "da_pagare", None]}
    }, {"_id": 0}).sort("data_scadenza", 1).to_list(100)
    
    # Contratti in scadenza
    contratti_scadenza = await db["contratti_dipendenti"].find({
        "data_fine": {"$lte": limite, "$gte": oggi_str},
        "stato": "attivo"
    }, {"_id": 0}).sort("data_fine", 1).to_list(100)
    
    # Libretti in scadenza
    libretti_scadenza = await db["libretti_sanitari"].find({
        "data_scadenza": {"$lte": limite}
    }, {"_id": 0}).sort("data_scadenza", 1).to_list(100)
    
    # F24 da pagare
    f24_scadenza = await db["f24_unificato"].find({
        "data_scadenza": {"$lte": limite},
        "pagato": {"$ne": True}
    }, {"_id": 0}).sort("data_scadenza", 1).to_list(100)
    
    # Genera PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=2*cm, bottomMargin=2*cm)
    styles = get_styles()
    elements = []
    
    elements.append(Paragraph("SCADENZE IMMINENTI", styles['TitleCustom']))
    elements.append(Paragraph(f"Prossimi {giorni} giorni (fino al {format_date_it(limite)})", styles['SubtitleCustom']))
    elements.append(Spacer(1, 20))
    
    # Fatture
    if fatture_scadenza:
        elements.append(Paragraph(f"📄 FATTURE DA PAGARE ({len(fatture_scadenza)})", styles['SectionTitle']))
        data = [["Fornitore", "Numero", "Importo", "Scadenza"]]
        for f in fatture_scadenza[:20]:
            data.append([
                f.get("supplier_name", "-")[:30],
                f.get("invoice_number", "-"),
                format_euro(f.get("total_amount", 0)),
                format_date_it(f.get("data_scadenza"))
            ])
        t = Table(data, colWidths=[6*cm, 3*cm, 3*cm, 3*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#dc2626')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
            ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 15))
    
    # Contratti
    if contratti_scadenza:
        elements.append(Paragraph(f"📋 CONTRATTI IN SCADENZA ({len(contratti_scadenza)})", styles['SectionTitle']))
        data = [["Dipendente", "Tipo", "Scadenza"]]
        for c in contratti_scadenza:
            data.append([
                c.get("dipendente_nome", "-"),
                c.get("tipo_contratto", "-").replace("_", " ").title(),
                format_date_it(c.get("data_fine"))
            ])
        t = Table(data, colWidths=[7*cm, 5*cm, 3*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#ca8a04')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 15))
    
    # Libretti
    if libretti_scadenza:
        elements.append(Paragraph(f"🏥 LIBRETTI SANITARI ({len(libretti_scadenza)})", styles['SectionTitle']))
        data = [["Dipendente", "Scadenza", "Stato"]]
        for lib in libretti_scadenza:
            scaduto = lib.get("data_scadenza") and lib.get("data_scadenza") < oggi_str
            data.append([
                lib.get("dipendente_nome", "-"),
                format_date_it(lib.get("data_scadenza")),
                "SCADUTO" if scaduto else "In scadenza"
            ])
        t = Table(data, colWidths=[7*cm, 4*cm, 4*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#ef4444')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 15))
    
    # F24
    if f24_scadenza:
        elements.append(Paragraph(f"💳 F24 DA VERSARE ({len(f24_scadenza)})", styles['SectionTitle']))
        data = [["Tipo", "Importo", "Scadenza"]]
        for f in f24_scadenza:
            data.append([
                f.get("tipo", f.get("descrizione", "-")),
                format_euro(f.get("totale", f.get("saldo_finale", 0))),
                format_date_it(f.get("data_scadenza"))
            ])
        t = Table(data, colWidths=[7*cm, 4*cm, 4*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#7c3aed')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ]))
        elements.append(t)
    
    if not any([fatture_scadenza, contratti_scadenza, libretti_scadenza, f24_scadenza]):
        elements.append(Paragraph("✅ Nessuna scadenza nei prossimi giorni!", styles['SubtitleCustom']))
    
    # Footer
    elements.append(Spacer(1, 30))
    elements.append(Paragraph(
        f"Report generato il {datetime.now().strftime('%d/%m/%Y alle %H:%M')}",
        ParagraphStyle(name='Footer', fontSize=8, textColor=colors.gray, alignment=TA_CENTER)
    ))
    
    doc.build(elements)
    buffer.seek(0)
    
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=report_scadenze_{oggi_str}.pdf"}
    )


@router.get("/magazzino")
async def generate_report_magazzino():
    """Genera report PDF del magazzino con prodotti e valori."""
    db = Database.get_db()
    
    # Recupera prodotti
    products = await db["warehouse_inventory"].find({}, {"_id": 0}).sort("nome", 1).to_list(5000)
    
    # Calcoli
    totale_prodotti = len(products)
    valore_totale = sum((p.get("prezzi", {}).get("avg", 0) or 0) * (p.get("giacenza", 0) or 0) for p in products)
    
    # Raggruppa per categoria
    by_category = {}
    for p in products:
        cat = p.get("categoria", "altro")
        if cat not in by_category:
            by_category[cat] = {"count": 0, "value": 0}
        by_category[cat]["count"] += 1
        by_category[cat]["value"] += (p.get("prezzi", {}).get("avg", 0) or 0) * (p.get("giacenza", 0) or 0)
    
    # Genera PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=2*cm, bottomMargin=2*cm)
    styles = get_styles()
    elements = []
    
    elements.append(Paragraph("REPORT MAGAZZINO", styles['TitleCustom']))
    elements.append(Paragraph(f"{totale_prodotti} prodotti - Valore: {format_euro(valore_totale)}", styles['SubtitleCustom']))
    elements.append(Spacer(1, 20))
    
    # Riepilogo categorie
    elements.append(Paragraph("📊 RIEPILOGO PER CATEGORIA", styles['SectionTitle']))
    data = [["Categoria", "Prodotti", "Valore"]]
    for cat, vals in sorted(by_category.items(), key=lambda x: -x[1]["value"]):
        data.append([cat.title(), str(vals["count"]), format_euro(vals["value"])])
    data.append(["TOTALE", str(totale_prodotti), format_euro(valore_totale)])
    
    t = Table(data, colWidths=[8*cm, 3*cm, 4*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0369a1')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#f0f9ff')),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
    ]))
    elements.append(t)
    
    # Footer
    elements.append(Spacer(1, 30))
    elements.append(Paragraph(
        f"Report generato il {datetime.now().strftime('%d/%m/%Y alle %H:%M')}",
        ParagraphStyle(name='Footer', fontSize=8, textColor=colors.gray, alignment=TA_CENTER)
    ))
    
    doc.build(elements)
    buffer.seek(0)
    
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=report_magazzino_{datetime.now().strftime('%Y%m%d')}.pdf"}
    )
