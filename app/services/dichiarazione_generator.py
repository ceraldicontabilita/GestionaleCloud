"""Genera PDF Dichiarazione Stragiudiziale di Terzo."""
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY


def genera_pdf_dichiarazione(filepath: str, dipendente: dict, pignoramento: dict):
    """Genera PDF precompilato della Dichiarazione Stragiudiziale."""
    doc = SimpleDocTemplate(filepath, pagesize=A4, leftMargin=2*cm, rightMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()

    title_s = ParagraphStyle('T', parent=styles['Heading1'], alignment=TA_CENTER, fontSize=14, spaceAfter=6)
    sub_s = ParagraphStyle('S', parent=styles['Normal'], alignment=TA_CENTER, fontSize=11, fontName='Helvetica-Oblique', spaceAfter=20)
    body_s = ParagraphStyle('B', parent=styles['Normal'], alignment=TA_JUSTIFY, fontSize=10, leading=14, spaceAfter=8)
    field_s = ParagraphStyle('F', parent=styles['Normal'], fontSize=10, leading=16, spaceAfter=4)
    check_s = ParagraphStyle('C', parent=styles['Normal'], fontSize=10, leading=14, spaceAfter=6, leftIndent=20)
    bold_s = ParagraphStyle('Bo', parent=styles['Normal'], fontSize=10, fontName='Helvetica-Bold', spaceAfter=8)

    deb_nome = pignoramento.get("debitore_nome", "N/A")
    deb_cf = pignoramento.get("debitore_cf", "N/A")
    num_doc = pignoramento.get("numero_documento", "N/A")
    data_doc = pignoramento.get("data_documento", "N/A")
    importo = pignoramento.get("importo", "N/A")
    targa = pignoramento.get("targa", "")
    anno = pignoramento.get("anno_riferimento", "")
    pec = pignoramento.get("pec_destinazione", "rcrc-affarilegali@pec.it")

    story = []
    story.append(Paragraph("DICHIARAZIONE STRAGIUDIZIALE DI TERZO", title_s))
    story.append(Paragraph("Ai sensi dell'art. 75 bis del D.P.R. 602/73", sub_s))
    story.append(Spacer(1, 10))

    story.append(Paragraph(
        "Il/La Sottoscritto/a <b>___________________________________________</b> "
        "nato/a a <b>_____________________</b>, il <b>______________</b>,", field_s))
    story.append(Paragraph(
        "residente a <b>_____________________</b> codice fiscale <b>___________________________</b>, in qualità di:", field_s))
    story.append(Spacer(1, 6))
    story.append(Paragraph("<b>&#9746;</b>&nbsp;&nbsp;rappresentante legale della terza pignorata <b>CERALDI GROUP SRL</b>", check_s))
    story.append(Paragraph("&#9744;&nbsp;&nbsp;in proprio", check_s))
    story.append(Spacer(1, 10))

    story.append(Paragraph(
        f"nell'esecuzione presso terzi di <b>{deb_nome}</b> C.F./P.I. <b>{deb_cf}</b>", body_s))
    story.append(Paragraph(
        f"promossa da <b>R.T.I. MUNICIPIA SpA - ABACO SpA</b>, Concessionario della Riscossione Coattiva "
        f"della Regione Campania, visto l'atto di pignoramento presso terzi n. <b>{num_doc}</b> del <b>{data_doc}</b> "
        f"(importo &euro; {importo}),", body_s))
    story.append(Spacer(1, 15))

    story.append(Paragraph("DICHIARA", title_s))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        f"<b>&#9746;</b>&nbsp;&nbsp;di non essere debitore nei confronti di <b>{deb_nome}</b> di alcuna somma di denaro, "
        f"<b>in quanto il rapporto di lavoro con il suddetto è cessato</b>.", check_s))
    story.append(Spacer(1, 10))

    story.append(Paragraph("OVVERO", ParagraphStyle('OV', parent=styles['Heading2'], alignment=TA_CENTER, fontSize=12, fontName='Helvetica-BoldOblique')))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        f"&#9744;&nbsp;&nbsp;di essere debitore nei confronti di <b>{deb_nome}</b> dei seguenti titoli:", check_s))
    story.append(Paragraph("______________________________________________________________", field_s))
    story.append(Spacer(1, 30))

    t = Table([
        ["Luogo/Data", "", "Firma"],
        ["_________________________", "", "___________________________"],
    ], colWidths=[7*cm, 2*cm, 7*cm])
    t.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Oblique'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
    ]))
    story.append(t)
    story.append(Spacer(1, 30))

    story.append(Paragraph(f"<b>Da inviare via PEC a:</b> {pec}", bold_s))
    story.append(Paragraph(f"<b>Riferimento:</b> Pignoramento n. {num_doc} del {data_doc}", body_s))
    if targa:
        story.append(Paragraph(f"<b>Targa:</b> {targa} — Anno: {anno}", body_s))
    story.append(Paragraph(f"<b>Importo:</b> &euro; {importo}", body_s))

    doc.build(story)
