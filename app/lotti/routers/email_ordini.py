"""
Router: ordini fornitori — PDF e anagrafica email
- Generazione e download del PDF ordine per fornitore
- Salvataggio/lettura delle email commerciali dei fornitori

NOTA: l'invio automatico via PEC/SMTP/Gmail è stato RIMOSSO. Gli ordini si
inviano manualmente scaricando il PDF (GET /ordini-fornitori/{id}/pdf).
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import io
from datetime import datetime, timezone
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
from typing import Optional

from app.lotti.db import database as db
from app.lotti.azienda import get_azienda

router = APIRouter(prefix="/ordini-fornitori", tags=["Ordini Fornitori PDF"])

AZIENDA_NOME = "Ceraldi Group S.r.l."
AZIENDA_INDIRIZZO = "Piazza Carità 14, 80134 Napoli (NA)"


# ── Modelli ──────────────────────────────────────────────────────────────────


class SaveEmailFornitore(BaseModel):
    nome_fornitore: str
    email: str


# ── Helpers ──────────────────────────────────────────────────────────────────


async def get_email_fornitore(nome_fornitore: str) -> str:
    """Recupera email da fornitori_anagrafica (priorità) poi da email_fornitori (legacy)."""
    doc = await db.fornitori_anagrafica.find_one({"nome": nome_fornitore}, {"_id": 0})
    if doc and doc.get("email"):
        return doc["email"]
    doc2 = await db.email_fornitori.find_one({"nome_fornitore": nome_fornitore}, {"_id": 0})
    if doc2 and doc2.get("email"):
        return doc2["email"]
    return ""


def genera_pdf_ordine_fornitore(ordine: dict, fornitore_nome: str, prodotti: list, azienda=None) -> bytes:
    """Genera PDF ordine per un singolo fornitore."""
    nome_az = (azienda or {}).get("ragione_sociale") or AZIENDA_NOME
    ind_az = (azienda or {}).get("indirizzo") or AZIENDA_INDIRIZZO
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )
    styles = getSampleStyleSheet()
    story = []

    titolo_style = ParagraphStyle(
        "Titolo",
        parent=styles["Heading1"],
        fontSize=18,
        textColor=colors.HexColor("#3f5a4e"),
        spaceAfter=4,
    )
    sottotest_style = ParagraphStyle(
        "Sub",
        parent=styles["Normal"],
        fontSize=9,
        textColor=colors.HexColor("#64748b"),
        spaceAfter=2,
    )
    label_style = ParagraphStyle(
        "Label",
        parent=styles["Normal"],
        fontSize=9,
        textColor=colors.HexColor("#374151"),
        fontName="Helvetica-Bold",
    )

    story.append(Paragraph("ORDINE D'ACQUISTO", titolo_style))
    story.append(Paragraph(f"{nome_az} — {ind_az}", sottotest_style))
    story.append(
        HRFlowable(width="100%", thickness=1, color=colors.HexColor("#5b7a6b"), spaceAfter=10)
    )

    data_ordine = ordine.get("data_ordine", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    ordine_id = ordine.get("id", "")[:8]
    info_data = [
        ["Fornitore:", fornitore_nome],
        ["Data ordine:", data_ordine],
        ["Numero ordine:", f"ORD-{ordine_id.upper()}"],
        ["Reparto:", ordine.get("reparto", "—") or "—"],
    ]
    if ordine.get("note_operatore"):
        info_data.append(["Note:", ordine["note_operatore"]])

    info_table = Table(info_data, colWidths=[4 * cm, 12 * cm])
    info_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#374151")),
                ("TEXTCOLOR", (1, 0), (1, -1), colors.HexColor("#1e293b")),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(info_table)
    story.append(Spacer(1, 0.5 * cm))

    story.append(Paragraph("Prodotti ordinati", label_style))
    story.append(Spacer(1, 0.2 * cm))

    header_row = ["#", "Prodotto", "Qtà", "Unità", "Prezzo unit.", "IVA %", "Imponibile"]
    table_data = [header_row]

    imponibile_tot = 0.0
    iva_tot = 0.0
    righe_senza_iva = 0
    for i, p in enumerate(prodotti, 1):
        prezzo = float(p.get("prezzo_ultimo", 0) or 0)
        qta = float(p.get("quantita", 1) or 1)
        aliquota = float(p.get("iva_pct", 0) or 0)
        riga_imp = prezzo * qta if prezzo > 0 else 0.0
        imponibile_tot += riga_imp
        if riga_imp > 0 and aliquota > 0:
            iva_tot += riga_imp * aliquota / 100.0
        elif riga_imp > 0:
            righe_senza_iva += 1
        table_data.append(
            [
                str(i),
                (p.get("nome") or "—").title(),
                str(p.get("quantita", "1")),
                p.get("unita", "kg"),
                f"€{prezzo:.2f}" if prezzo > 0 else "—",
                f"{aliquota:g}%" if aliquota > 0 else "—",
                f"€{riga_imp:.2f}" if riga_imp > 0 else "—",
            ]
        )
    if imponibile_tot > 0:
        table_data.append(["", "IMPONIBILE", "", "", "", "", f"€{imponibile_tot:.2f}"])
        table_data.append(["", "IVA", "", "", "", "", f"€{iva_tot:.2f}"])
        table_data.append(["", "TOTALE ORDINE", "", "", "", "",
                            f"€{imponibile_tot + iva_tot:.2f}"])

    col_widths = [0.8 * cm, 7.2 * cm, 1.6 * cm, 1.6 * cm, 2.2 * cm, 1.4 * cm, 2.2 * cm]
    prod_table = Table(table_data, colWidths=col_widths, repeatRows=1)
    prod_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#5b7a6b")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ALIGN", (0, 0), (0, -1), "CENTER"),
                ("ALIGN", (2, 0), (6, -1), "RIGHT"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#faf7f0")]),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e6e0d4")),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    if imponibile_tot > 0:
        # ultime 3 righe: IMPONIBILE / IVA / TOTALE ORDINE
        prod_table.setStyle(TableStyle([
            ("FONTNAME", (0, -3), (-1, -1), "Helvetica-Bold"),
            ("BACKGROUND", (0, -3), (-1, -2), colors.HexColor("#f2f6f3")),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#e8efe9")),
        ]))
    story.append(prod_table)
    if righe_senza_iva:
        story.append(Spacer(1, 0.2 * cm))
        story.append(Paragraph(
            f"Nota: {righe_senza_iva} riga/e senza aliquota IVA nota — il totale IVA è parziale.",
            sottotest_style,
        ))
    story.append(Spacer(1, 0.8 * cm))

    story.append(
        HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#e6e0d4"), spaceAfter=6)
    )
    story.append(
        Paragraph(
            f"Generato automaticamente da {nome_az} il {datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')} UTC",
            sottotest_style,
        )
    )

    doc.build(story)
    return buffer.getvalue()


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/{ordine_id}/suppliers-email")
async def get_suppliers_email(ordine_id: str):
    """Ritorna i fornitori presenti nell'ordine con le loro email salvate."""
    ordine = await db.ordini_fornitori.find_one({"id": ordine_id}, {"_id": 0})
    if not ordine:
        raise HTTPException(404, "Ordine non trovato")

    gruppi = {}
    for p in ordine.get("prodotti") or []:
        fn = p.get("fornitore") or "Generico"
        gruppi.setdefault(fn, []).append(p)

    result = []
    for nome_fornitore, prods in gruppi.items():
        email_salvata = await get_email_fornitore(nome_fornitore)
        anag = await db.fornitori_anagrafica.find_one({"nome": nome_fornitore}, {"_id": 0})
        result.append(
            {
                "nome": nome_fornitore,
                "email": email_salvata,
                "cellulare": anag.get("cellulare", "") if anag else "",
                "n_prodotti": len(prods),
                "prodotti": prods,
            }
        )
    return {"ordine_id": ordine_id, "data_ordine": ordine.get("data_ordine"), "fornitori": result}


@router.post("/email-fornitore/salva")
async def salva_email_fornitore(payload: SaveEmailFornitore):
    """Salva o aggiorna l'email commerciale di un fornitore."""
    await db.email_fornitori.update_one(
        {"nome_fornitore": payload.nome_fornitore},
        {
            "$set": {
                "nome_fornitore": payload.nome_fornitore,
                "email": payload.email,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        },
        upsert=True,
    )
    return {"success": True, "nome": payload.nome_fornitore, "email": payload.email}


@router.get("/email-fornitori/lista")
async def lista_email_fornitori():
    """Lista tutte le email salvate per i fornitori."""
    docs = await db.email_fornitori.find({}, {"_id": 0}).to_list(500)
    return docs


@router.get("/{ordine_id}/pdf")
async def scarica_pdf_ordine(ordine_id: str, fornitore: Optional[str] = None):
    """Genera e scarica il PDF dell'ordine (filtrato per fornitore se specificato)."""
    ordine = await db.ordini_fornitori.find_one({"id": ordine_id}, {"_id": 0})
    if not ordine:
        raise HTTPException(404, "Ordine non trovato")

    prodotti = ordine.get("prodotti") or []
    if fornitore:
        prodotti = [p for p in prodotti if (p.get("fornitore") or "") == fornitore]
        nome_fornitore = fornitore
    else:
        nome_fornitore = "Tutti i fornitori"

    pdf_bytes = genera_pdf_ordine_fornitore(ordine, nome_fornitore, prodotti, azienda=await get_azienda())
    filename = f"ordine_{ordine_id[:8]}_{nome_fornitore[:20].replace(' ', '_')}.pdf"

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
