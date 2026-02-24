"""
Ordini Fornitori Router - Gestione ordini ai fornitori.
Refactored from public_api.py
"""
from fastapi import APIRouter, HTTPException, Body
from fastapi.responses import StreamingResponse
from typing import Dict, Any, List
from datetime import datetime, timezone
import uuid
import logging
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER

from app.database import Database
from app.utils.error_handler import handle_errors

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("")
@handle_errors
async def list_ordini(skip: int = 0, limit: int = 10000) -> List[Dict[str, Any]]:
    """Lista ordini fornitori."""
    db = Database.get_db()
    return await db["supplier_orders"].find({}, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)


@router.post("")
@handle_errors
async def create_ordine(data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Crea nuovo ordine fornitore."""
    db = Database.get_db()
    
    # Numero progressivo
    last = await db["supplier_orders"].find_one({}, {"order_number": 1}, sort=[("order_number", -1)])
    try:
        new_num = int(last["order_number"]) + 1 if last and last.get("order_number") else 1
    except (ValueError, TypeError):
        new_num = 1
    
    items = data.get("items", [])
    total = sum(float(i.get("unit_price", 0) or 0) * float(i.get("quantity", 1) or 1) for i in items)
    
    order = {
        "id": str(uuid.uuid4()),
        "order_number": str(new_num).zfill(5),
        "supplier_name": data.get("supplier_name", ""),
        "supplier_vat": data.get("supplier_vat", ""),
        "items": items,
        "subtotal": data.get("subtotal", total),
        "total": total,
        "vat": 0,
        "notes": data.get("notes", ""),
        "status": "bozza",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db["supplier_orders"].insert_one(order.copy())
    order.pop("_id", None)
    return order


@router.get("/stats/summary")
@handle_errors
async def get_stats() -> Dict[str, Any]:
    """Statistiche ordini."""
    db = Database.get_db()
    
    pipeline = [{"$group": {"_id": "$status", "count": {"$sum": 1}, "total": {"$sum": "$total"}}}]
    result = await db["supplier_orders"].aggregate(pipeline).to_list(10)
    
    stats = {"bozza": {"count": 0, "total": 0}, "inviato": {"count": 0, "total": 0},
             "confermato": {"count": 0, "total": 0}, "consegnato": {"count": 0, "total": 0}, "annullato": {"count": 0, "total": 0}}
    
    for r in result:
        s = r.get("_id", "bozza")
        if s in stats:
            stats[s] = {"count": r.get("count", 0), "total": round(r.get("total", 0), 2)}
    
    return {
        "by_status": stats,
        "total_orders": sum(s["count"] for s in stats.values()),
        "total_amount": round(sum(s["total"] for s in stats.values()), 2)
    }


@router.get("/{order_id}")
@handle_errors
async def get_ordine(order_id: str) -> Dict[str, Any]:
    """Ottiene ordine."""
    db = Database.get_db()
    order = await db["supplier_orders"].find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Ordine non trovato")
    return order


@router.put("/{order_id}")
@handle_errors
async def update_ordine(order_id: str, data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Aggiorna ordine."""
    db = Database.get_db()
    
    update = {k: v for k, v in data.items() if k not in ["id", "_id", "order_number"]}
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    result = await db["supplier_orders"].update_one({"id": order_id}, {"$set": update})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Ordine non trovato")
    
    return await get_ordine(order_id)


@router.delete("/{order_id}")
@handle_errors
async def delete_ordine(order_id: str) -> Dict[str, Any]:
    """Elimina ordine."""
    db = Database.get_db()
    result = await db["supplier_orders"].delete_one({"id": order_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Ordine non trovato")
    return {"success": True, "deleted_id": order_id}


@router.patch("/{order_id}/status")
@handle_errors
async def update_status(order_id: str, status: str = Body(..., embed=True)) -> Dict[str, Any]:
    """Cambia stato ordine."""
    valid = ["bozza", "inviato", "confermato", "consegnato", "annullato"]
    if status not in valid:
        raise HTTPException(status_code=400, detail=f"Stato non valido. Usa: {valid}")
    
    db = Database.get_db()
    result = await db["supplier_orders"].update_one(
        {"id": order_id},
        {"$set": {"status": status, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Ordine non trovato")
    
    return await get_ordine(order_id)


def generate_order_pdf(order: Dict[str, Any]) -> BytesIO:
    """Genera PDF ordine fornitore."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.5*cm,
        leftMargin=1.5*cm,
        topMargin=1.5*cm,
        bottomMargin=1.5*cm
    )
    
    styles = getSampleStyleSheet()
    story = []
    
    # Stili personalizzati
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=20,
        textColor=colors.HexColor('#1a365d'),
        spaceAfter=20,
        alignment=TA_CENTER
    )
    
    header_style = ParagraphStyle(
        'Header',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor('#4a5568'),
        alignment=TA_CENTER
    )
    
    # Intestazione azienda
    story.append(Paragraph("<b>CERALDI GROUP S.R.L.</b>", title_style))
    story.append(Paragraph("Via Example, 123 - 80100 Napoli (NA)", header_style))
    story.append(Paragraph("P.IVA: 12345678901 | Tel: 081-1234567 | Email: ordini@ceraldigroup.it", header_style))
    story.append(Spacer(1, 0.5*cm))
    
    # Linea separatrice
    line_data = [[""]]
    line_table = Table(line_data, colWidths=[17*cm])
    line_table.setStyle(TableStyle([
        ('LINEBELOW', (0, 0), (-1, -1), 2, colors.HexColor('#1a365d')),
    ]))
    story.append(line_table)
    story.append(Spacer(1, 0.5*cm))
    
    # Titolo ordine
    order_num = order.get('order_number', 'N/A')
    date_str = datetime.fromisoformat(order.get('created_at', datetime.now(timezone.utc).isoformat())).strftime('%d/%m/%Y')
    
    order_title = ParagraphStyle('OrderTitle', parent=styles['Heading2'], fontSize=16, textColor=colors.HexColor('#2d3748'))
    story.append(Paragraph(f"ORDINE N° {order_num}", order_title))
    story.append(Paragraph(f"Data: {date_str}", styles['Normal']))
    story.append(Spacer(1, 0.3*cm))
    
    # Destinatario
    supplier_name = order.get('supplier_name', 'N/D')
    supplier_vat = order.get('supplier_vat', '')
    
    dest_style = ParagraphStyle('Dest', parent=styles['Normal'], fontSize=11, leftIndent=20)
    story.append(Paragraph("<b>Destinatario:</b>", styles['Heading3']))
    story.append(Paragraph(f"{supplier_name}", dest_style))
    if supplier_vat:
        story.append(Paragraph(f"P.IVA: {supplier_vat}", dest_style))
    story.append(Spacer(1, 0.5*cm))
    
    # Tabella prodotti
    items = order.get('items', [])
    table_data = [['Prodotto', 'Qtà', 'Unità', 'Prezzo Unit.', 'Totale']]
    
    for item in items:
        prod_name = item.get('product_name') or item.get('description', 'Prodotto')
        qty = item.get('quantity', 1)
        unit = item.get('unit', 'PZ')
        unit_price = float(item.get('unit_price', 0) or 0)
        total = unit_price * qty
        
        table_data.append([
            prod_name[:40] + ('...' if len(prod_name) > 40 else ''),
            str(qty),
            unit,
            f"€ {unit_price:.2f}",
            f"€ {total:.2f}"
        ])
    
    # Stile tabella
    col_widths = [7*cm, 1.5*cm, 1.5*cm, 2.5*cm, 2.5*cm]
    table = Table(table_data, colWidths=col_widths)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a365d')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('ALIGN', (0, 1), (0, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('TOPPADDING', (0, 0), (-1, 0), 10),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f7fafc')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e0')),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('TOPPADDING', (0, 1), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#f7fafc'), colors.white]),
    ]))
    story.append(table)
    story.append(Spacer(1, 0.5*cm))
    
    # Totali
    subtotal = float(order.get('subtotal', 0) or 0)
    iva = subtotal * 0.22
    totale = subtotal + iva
    
    totals_data = [
        ['', '', '', 'Imponibile:', f"€ {subtotal:.2f}"],
        ['', '', '', 'IVA (22%):', f"€ {iva:.2f}"],
        ['', '', '', 'TOTALE:', f"€ {totale:.2f}"],
    ]
    
    totals_table = Table(totals_data, colWidths=col_widths)
    totals_table.setStyle(TableStyle([
        ('ALIGN', (3, 0), (3, -1), 'RIGHT'),
        ('ALIGN', (4, 0), (4, -1), 'RIGHT'),
        ('FONTNAME', (3, -1), (4, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (3, -1), (4, -1), 12),
        ('TEXTCOLOR', (3, -1), (4, -1), colors.HexColor('#1a365d')),
        ('LINEABOVE', (3, -1), (4, -1), 1, colors.HexColor('#1a365d')),
    ]))
    story.append(totals_table)
    story.append(Spacer(1, 1*cm))
    
    # Note
    notes = order.get('notes', '')
    if notes:
        story.append(Paragraph("<b>Note:</b>", styles['Heading4']))
        story.append(Paragraph(notes, styles['Normal']))
        story.append(Spacer(1, 0.5*cm))
    
    # Footer
    footer_style = ParagraphStyle('Footer', parent=styles['Normal'], fontSize=9, textColor=colors.grey, alignment=TA_CENTER)
    story.append(Spacer(1, 1*cm))
    story.append(Paragraph("Documento generato automaticamente - CERALDI GROUP S.R.L.", footer_style))
    story.append(Paragraph(f"Generato il {datetime.now().strftime('%d/%m/%Y alle %H:%M')}", footer_style))
    
    doc.build(story)
    buffer.seek(0)
    return buffer


@router.get("/{order_id}/pdf")
@handle_errors
async def download_order_pdf(order_id: str):
    """Genera e scarica PDF ordine."""
    order = await get_ordine(order_id)
    
    pdf_buffer = generate_order_pdf(order)
    
    filename = f"Ordine_{order.get('order_number', order_id)}.pdf"
    
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )


@router.post("/{order_id}/send-email")
@handle_errors
async def send_order_email(order_id: str, data: Dict[str, Any] = Body(default={})) -> Dict[str, Any]:
    """Invia ordine via email al fornitore con PDF allegato."""
    db = Database.get_db()
    
    # Recupera ordine
    order = await get_ordine(order_id)
    
    # Recupera email fornitore
    supplier_email = data.get('email')
    if not supplier_email:
        # Cerca email nel database fornitori
        supplier = await db["suppliers"].find_one({"partita_iva": order.get('supplier_vat')})
        if supplier:
            supplier_email = supplier.get('email')
    
    if not supplier_email:
        raise HTTPException(status_code=400, detail="Email fornitore non trovata. Specificare email nel body.")
    
    # Configurazione SMTP
    smtp_host = os.environ.get('SMTP_HOST', 'smtp.gmail.com')
    smtp_port = int(os.environ.get('SMTP_PORT', 587))
    smtp_user = os.environ.get('SMTP_USER', '')
    smtp_password = os.environ.get('SMTP_PASSWORD', '')
    from_email = os.environ.get('FROM_EMAIL', smtp_user)
    
    if not smtp_user or not smtp_password:
        raise HTTPException(status_code=500, detail="Configurazione SMTP mancante")
    
    # Genera PDF
    pdf_buffer = generate_order_pdf(order)
    
    # Prepara email
    order_num = order.get('order_number', 'N/A')
    supplier_name = order.get('supplier_name', 'Fornitore')
    subtotal = float(order.get('subtotal', 0) or 0)
    iva = subtotal * 0.22
    totale = subtotal + iva
    
    # Corpo email HTML
    items_html = ""
    for item in order.get('items', []):
        prod_name = item.get('product_name') or item.get('description', 'Prodotto')
        qty = item.get('quantity', 1)
        unit = item.get('unit', 'PZ')
        items_html += f"<li>{prod_name} - Qtà: {qty} {unit}</li>"
    
    html_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #333;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
            <h2 style="color: #1a365d; border-bottom: 2px solid #1a365d; padding-bottom: 10px;">
                Ordine N° {order_num}
            </h2>
            
            <p>Gentile {supplier_name},</p>
            
            <p>Vi inviamo in allegato l'ordine n° <strong>{order_num}</strong> con i seguenti prodotti:</p>
            
            <ul style="background: #f7fafc; padding: 15px 15px 15px 35px; border-radius: 5px;">
                {items_html}
            </ul>
            
            <div style="background: #edf2f7; padding: 15px; border-radius: 5px; margin-top: 20px;">
                <table style="width: 100%;">
                    <tr>
                        <td><strong>Imponibile:</strong></td>
                        <td style="text-align: right;">€ {subtotal:.2f}</td>
                    </tr>
                    <tr>
                        <td><strong>IVA (22%):</strong></td>
                        <td style="text-align: right;">€ {iva:.2f}</td>
                    </tr>
                    <tr style="font-size: 18px; color: #1a365d;">
                        <td><strong>TOTALE:</strong></td>
                        <td style="text-align: right;"><strong>€ {totale:.2f}</strong></td>
                    </tr>
                </table>
            </div>
            
            <p style="margin-top: 20px;">
                Vi preghiamo di confermare la ricezione dell'ordine e comunicarci i tempi di consegna previsti.
            </p>
            
            <p>Cordiali saluti,<br>
            <strong>CERALDI GROUP S.R.L.</strong></p>
            
            <hr style="border: none; border-top: 1px solid #cbd5e0; margin: 20px 0;">
            <p style="font-size: 11px; color: #718096;">
                Questa email è stata generata automaticamente dal sistema gestionale.<br>
                Per informazioni: ordini@ceraldigroup.it
            </p>
        </div>
    </body>
    </html>
    """
    
    plain_body = f"""
Ordine N° {order_num}

Gentile {supplier_name},

Vi inviamo in allegato l'ordine n° {order_num}.

Imponibile: € {subtotal:.2f}
IVA (22%): € {iva:.2f}
TOTALE: € {totale:.2f}

Vi preghiamo di confermare la ricezione dell'ordine.

Cordiali saluti,
CERALDI GROUP S.R.L.
    """
    
    try:
        # Crea messaggio
        msg = MIMEMultipart('alternative')
        msg['From'] = from_email
        msg['To'] = supplier_email
        msg['Subject'] = f"Ordine N° {order_num} - CERALDI GROUP S.R.L."
        
        # Corpo testo e HTML
        msg.attach(MIMEText(plain_body, 'plain', 'utf-8'))
        msg.attach(MIMEText(html_body, 'html', 'utf-8'))
        
        # Allegato PDF
        pdf_attachment = MIMEBase('application', 'pdf')
        pdf_attachment.set_payload(pdf_buffer.read())
        encoders.encode_base64(pdf_attachment)
        pdf_attachment.add_header(
            'Content-Disposition',
            f'attachment; filename=Ordine_{order_num}.pdf'
        )
        msg.attach(pdf_attachment)
        
        # Invio
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(from_email, [supplier_email], msg.as_string())
        
        # Aggiorna stato ordine
        await db["supplier_orders"].update_one(
            {"id": order_id},
            {"$set": {
                "status": "inviato",
                "email_sent_to": supplier_email,
                "email_sent_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        
        logger.info(f"Email ordine {order_num} inviata a {supplier_email}")
        
        return {
            "success": True,
            "message": f"Email inviata con successo a {supplier_email}",
            "order_number": order_num,
            "email": supplier_email
        }
        
    except smtplib.SMTPAuthenticationError as e:
        logger.error(f"Errore autenticazione SMTP: {e}")
        raise HTTPException(status_code=500, detail="Errore autenticazione email. Verificare credenziali SMTP.")
    except smtplib.SMTPException as e:
        logger.error(f"Errore SMTP: {e}")
        raise HTTPException(status_code=500, detail=f"Errore invio email: {str(e)}")
    except Exception as e:
        logger.error(f"Errore invio email: {e}")
        raise HTTPException(status_code=500, detail=f"Errore: {str(e)}")
