# -*- coding: utf-8 -*-
"""
Modulo di calcolo liquidazione IVA mensile + esportazione PDF
Progetto: Azienda Semplice ERP
Autore: Ceraldi Vincenzo
Regime: IVA ordinaria per competenza

Questo modulo calcola la liquidazione IVA mensile secondo le norme italiane:
- IVA a DEBITO: da corrispettivi (vendite al pubblico)
- IVA a CREDITO: da fatture acquisto ricevute nel periodo
- Gestione Note Credito (TD04, TD08): sottratte dal totale
- Deroghe temporali: regola 15 giorni e 12 giorni per fatture mese precedente
"""

from datetime import date, timedelta, datetime
from decimal import Decimal
from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger(__name__)

# Tipi documento Note Credito
NOTE_CREDITO_TYPES = ["TD04", "TD08"]

MESI_ITALIANI = ["", "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
                 "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"]


# -------------------- UTILITIES --------------------

def month_bounds(year: int, month: int) -> tuple:
    """Restituisce primo e ultimo giorno del mese."""
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)
    return start, end


def prev_month(year: int, month: int) -> tuple:
    """Restituisce anno e mese del mese precedente."""
    return (year - 1, 12) if month == 1 else (year, month - 1)


def q2(v) -> Decimal:
    """Arrotonda a 2 decimali."""
    if v is None:
        return Decimal("0.00")
    try:
        return Decimal(str(v)).quantize(Decimal("0.01"))
    except Exception:
        return Decimal("0.00")


def safe_decimal(v) -> Decimal:
    """Converte un valore in Decimal in modo sicuro."""
    if v is None:
        return Decimal(0)
    try:
        return Decimal(str(v))
    except Exception:
        return Decimal(0)


def parse_date(date_str: str) -> Optional[date]:
    """Converte stringa data in oggetto date."""
    if not date_str:
        return None
    try:
        if "T" in date_str:
            date_str = date_str.split("T")[0]
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def is_excluded_by_nature(line: Dict) -> bool:
    """Verifica se la linea è esclusa dalla liquidazione IVA (natura N1-N7)."""
    return bool(line.get("natura"))


def sign_from_doc(inv: Dict) -> Decimal:
    """Determina il segno in base al tipo documento."""
    # TD04 = Nota di Credito -> segno negativo
    return Decimal(-1) if inv.get("tipo_documento") in NOTE_CREDITO_TYPES else Decimal(1)


def within_12_days_rule(op_date: date, reg_date: date, year: int, month: int) -> bool:
    """
    Verifica la regola dei 12 giorni:
    Fattura con data operazione del mese precedente,
    registrata entro il 12 del mese corrente.
    """
    prev_y, prev_m = prev_month(year, month)
    prev_start, prev_end = month_bounds(prev_y, prev_m)
    cutoff = date(year, month, 12)
    return prev_start <= op_date <= prev_end and reg_date <= cutoff


# -------------------- CORE LOGIC --------------------

def compute_vat_liquidation_from_db(
    year: int, 
    month: int, 
    fatture: List[Dict],
    corrispettivi: List[Dict],
    prev_credit_carry: float = 0
) -> Dict[str, Any]:
    """
    Calcola la liquidazione IVA mensile dai dati del database.
    
    Args:
        year: Anno di riferimento
        month: Mese di riferimento (1-12)
        fatture: Lista delle fatture dal database (collezione invoices)
        corrispettivi: Lista dei corrispettivi dal database
        prev_credit_carry: Credito IVA da riportare dal mese precedente
    
    Returns:
        Dict con tutti i dettagli della liquidazione IVA
    """
    period_start, period_end = month_bounds(year, month)
    prev_y, prev_m = prev_month(year, month)
    prev_start, prev_end = month_bounds(prev_y, prev_m)
    fifteenth = date(year, month, 15)

    # Inizializza totali
    iva_debito = Decimal(0)  # Da corrispettivi
    iva_credito = Decimal(0)  # Da fatture acquisto
    
    # Dettagli per aliquota
    sales_detail = {}  # IVA vendite (corrispettivi)
    purchase_detail = {}  # IVA acquisti (fatture)
    
    # Contatori
    fatture_incluse = 0
    fatture_escluse = 0
    note_credito_count = 0
    
    # -------------------- IVA DEBITO (CORRISPETTIVI) --------------------
    for corr in corrispettivi:
        data_corr = parse_date(corr.get("data", ""))
        if not data_corr:
            continue
        
        # Verifica che il corrispettivo sia nel periodo
        if period_start <= data_corr <= period_end:
            # IVA dal corrispettivo
            totale_iva = safe_decimal(corr.get("totale_iva", 0) or 0)
            totale = safe_decimal(corr.get("totale", 0) or 0)
            
            iva_debito += totale_iva
            
            # Stima aliquota media (22% di default)
            aliquota = 22
            if totale > 0 and totale_iva > 0:
                aliquota = round(float(totale_iva / (totale - totale_iva) * 100))
            
            imponibile = totale - totale_iva
            
            sales_detail.setdefault(aliquota, {"imponibile": Decimal(0), "iva": Decimal(0)})
            sales_detail[aliquota]["imponibile"] += imponibile
            sales_detail[aliquota]["iva"] += totale_iva
    
    # -------------------- IVA CREDITO (FATTURE ACQUISTO) --------------------
    for inv in fatture:
        # Data operazione (data fattura) e data registrazione (data ricezione SDI)
        op_date = parse_date(inv.get("invoice_date", ""))
        reg_date = parse_date(inv.get("data_ricezione", "") or inv.get("invoice_date", ""))
        
        if not op_date or not reg_date:
            fatture_escluse += 1
            continue
        
        tipo_doc = inv.get("tipo_documento", "")
        is_nota_credito = tipo_doc in NOTE_CREDITO_TYPES
        sign = Decimal(-1) if is_nota_credito else Decimal(1)
        
        # Verifica criteri temporali per includere la fattura
        same_month = period_start <= op_date <= period_end and reg_date <= period_end
        
        # Deroga 15 giorni: fattura mese precedente registrata entro il 15
        deroga_15 = (
            prev_start <= op_date <= prev_end
            and reg_date <= fifteenth
            and prev_y == year
            and month != 1
        )
        
        # Deroga 12 giorni
        deroga_12 = within_12_days_rule(op_date, reg_date, year, month)
        
        if not (same_month or deroga_15 or deroga_12):
            fatture_escluse += 1
            continue
        
        fatture_incluse += 1
        if is_nota_credito:
            note_credito_count += 1
        
        # Percentuale detraibilità (default 100%)
        detraibilita_percent = safe_decimal(inv.get("detraibilita_percent", 100) or 100)
        perc = detraibilita_percent / Decimal(100)
        
        # Usa IVA dal riepilogo_iva se disponibile
        riepilogo = inv.get("riepilogo_iva", [])
        if riepilogo:
            for r in riepilogo:
                natura = r.get("natura", "")
                if natura:  # Escluso da liquidazione (N1-N7)
                    continue
                
                aliquota = int(float(r.get("aliquota_iva", 0) or 0))
                imponibile = safe_decimal(r.get("imponibile", 0) or 0) * perc * sign
                imposta = safe_decimal(r.get("imposta", 0) or 0) * perc * sign
                
                iva_credito += imposta
                
                purchase_detail.setdefault(aliquota, {"imponibile": Decimal(0), "iva": Decimal(0)})
                purchase_detail[aliquota]["imponibile"] += imponibile
                purchase_detail[aliquota]["iva"] += imposta
        else:
            # Fallback: usa campi fattura
            f_iva = safe_decimal(inv.get("iva", 0) or 0) * perc * sign
            f_imponibile = safe_decimal(inv.get("imponibile", 0) or 0) * perc * sign
            
            # Stima aliquota
            if f_imponibile > 0:
                aliquota = round(float(f_iva / f_imponibile * 100))
            else:
                aliquota = 22
            
            iva_credito += f_iva
            
            purchase_detail.setdefault(aliquota, {"imponibile": Decimal(0), "iva": Decimal(0)})
            purchase_detail[aliquota]["imponibile"] += f_imponibile
            purchase_detail[aliquota]["iva"] += f_iva
    
    # -------------------- CALCOLO FINALE --------------------
    iva_debito = q2(iva_debito)
    iva_credito = q2(iva_credito)
    prev_credit_carry = q2(prev_credit_carry)
    
    # Saldo = Debito - (Credito + Credito precedente)
    net_to_pay = max(Decimal(0), iva_debito - (iva_credito + prev_credit_carry))
    credit_to_carry = max(Decimal(0), (iva_credito + prev_credit_carry) - iva_debito)
    
    return {
        "anno": year,
        "mese": month,
        "mese_nome": MESI_ITALIANI[month],
        "periodo": f"{period_start.strftime('%d/%m/%Y')} - {period_end.strftime('%d/%m/%Y')}",
        "iva_debito": float(iva_debito),
        "iva_credito": float(iva_credito),
        "credito_precedente": float(prev_credit_carry),
        "iva_da_versare": float(q2(net_to_pay)),
        "credito_da_riportare": float(q2(credit_to_carry)),
        "stato": "Da versare" if net_to_pay > 0 else "A credito" if credit_to_carry > 0 else "Pareggio",
        "sales_detail": {
            k: {"imponibile": float(q2(v["imponibile"])), "iva": float(q2(v["iva"]))}
            for k, v in sales_detail.items()
        },
        "purchase_detail": {
            k: {"imponibile": float(q2(v["imponibile"])), "iva": float(q2(v["iva"]))}
            for k, v in purchase_detail.items()
        },
        "statistiche": {
            "fatture_incluse": fatture_incluse,
            "fatture_escluse": fatture_escluse,
            "note_credito": note_credito_count,
            "corrispettivi_count": len(corrispettivi)
        },
        "regime_iva": "ordinaria",
        "calcolato_il": datetime.now().isoformat()
    }


# -------------------- PDF EXPORT --------------------

def export_liquidazione_iva_pdf(
    result: Dict[str, Any], 
    azienda_nome: str = "Ceraldi Group Srl",
    output_path: str = None
) -> bytes:
    """
    Genera PDF della liquidazione IVA.
    
    Args:
        result: Risultato di compute_vat_liquidation_from_db
        azienda_nome: Nome azienda
        output_path: Path file output (opzionale)
    
    Returns:
        bytes del PDF generato
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib import colors
    import io
    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=20*mm, bottomMargin=20*mm)
    styles = getSampleStyleSheet()
    story = []
    
    # Stile personalizzato
    title_style = ParagraphStyle(
        'CustomTitle', 
        parent=styles['Title'], 
        fontSize=18, 
        textColor=colors.HexColor('#1e40af'),
        spaceAfter=10
    )
    
    # Titolo
    story.append(Paragraph("<b>📊 Liquidazione IVA Mensile</b>", title_style))
    story.append(Paragraph(f"Azienda: <b>{azienda_nome}</b>", styles["Normal"]))
    story.append(Paragraph(f"Periodo: <b>{result['mese_nome']} {result['anno']}</b>", styles["Normal"]))
    story.append(Paragraph(f"({result['periodo']})", styles["Normal"]))
    story.append(Spacer(1, 15))
    
    # Funzione per formattare euro in italiano
    def fmt_euro(val):
        return f"€ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    
    # Tabella riepilogo
    summary = [
        ["Descrizione", "Importo"],
        ["IVA a Debito (Corrispettivi)", fmt_euro(result['iva_debito'])],
        ["IVA a Credito (Fatture Acquisto)", fmt_euro(result['iva_credito'])],
        ["Credito IVA mese precedente", fmt_euro(result['credito_precedente'])],
        ["", ""],
    ]
    
    if result['iva_da_versare'] > 0:
        summary.append(["🔴 IVA DA VERSARE", fmt_euro(result['iva_da_versare'])])
    else:
        summary.append(["🟢 CREDITO DA RIPORTARE", fmt_euro(result['credito_da_riportare'])])
    
    t = Table(summary, colWidths=[100*mm, 50*mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor('#1e40af')),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor('#f0f9ff')),
    ]))
    story.append(t)
    story.append(Spacer(1, 20))
    
    # Dettaglio IVA Debito per aliquota
    def detail_block(title: str, data: Dict, color: str):
        if not data:
            return
        story.append(Paragraph(f"<b>{title}</b>", styles["Heading3"]))
        rows = [["Aliquota", "Imponibile", "IVA"]]
        for aliquota, values in sorted(data.items()):
            rows.append([
                f"{aliquota}%", 
                fmt_euro(values['imponibile']), 
                fmt_euro(values['iva'])
            ])
        # Totale
        tot_imp = sum(v['imponibile'] for v in data.values())
        tot_iva = sum(v['iva'] for v in data.values())
        rows.append(["TOTALE", fmt_euro(tot_imp), fmt_euro(tot_iva)])
        
        tb = Table(rows, colWidths=[30*mm, 50*mm, 50*mm])
        tb.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(color)),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor('#f5f5f5')),
        ]))
        story.append(tb)
        story.append(Spacer(1, 15))
    
    detail_block("📈 IVA a Debito (Vendite/Corrispettivi)", result.get("sales_detail", {}), '#dc2626')
    detail_block("📉 IVA a Credito (Acquisti)", result.get("purchase_detail", {}), '#16a34a')
    
    # Statistiche
    story.append(Paragraph("<b>📊 Statistiche</b>", styles["Heading3"]))
    stats = result.get("statistiche", {})
    stats_text = f"""
    • Fatture incluse nel calcolo: {stats.get('fatture_incluse', 0)}<br/>
    • Fatture escluse (fuori periodo): {stats.get('fatture_escluse', 0)}<br/>
    • Note credito: {stats.get('note_credito', 0)}<br/>
    • Corrispettivi: {stats.get('corrispettivi_count', 0)}<br/>
    • Regime IVA: {result.get('regime_iva', 'ordinaria').upper()}
    """
    story.append(Paragraph(stats_text, styles["Normal"]))
    story.append(Spacer(1, 20))
    
    # Footer
    footer_style = ParagraphStyle('Footer', parent=styles['Normal'], fontSize=9, textColor=colors.grey)
    story.append(Paragraph(
        f"Documento generato il {datetime.now().strftime('%d/%m/%Y %H:%M')} - Azienda Semplice ERP",
        footer_style
    ))
    
    doc.build(story)
    
    pdf_bytes = buffer.getvalue()
    buffer.close()
    
    # Salva su file se richiesto
    if output_path:
        with open(output_path, 'wb') as f:
            f.write(pdf_bytes)
    
    return pdf_bytes
