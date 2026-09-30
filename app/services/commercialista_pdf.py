"""PDF dei documenti per il commercialista, generati dal server (reportlab).

Le pagine dell'Area Commercialista scaricano ancora i PDF costruiti dal browser (jsPDF)
per Prima Nota Cassa, Fatture per cassa e Carnet. Il pacchetto da inviare, invece, non
puo' dipendere dal browser: ogni voce e' costruita qui, con lo stesso stile (verde
salvia dell'intestazione aziendale, tabelle a righe alternate, totali in fondo).

Il generatore e' uno solo e non conosce le singole voci: riceve la struttura prodotta da
``commercialista_pacchetto`` (``sezioni`` con colonne, allineamenti e righe).
"""
from __future__ import annotations

import io
from datetime import datetime
from typing import Any, Dict, List, Sequence
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

AZIENDA = "CERALDI GROUP S.R.L."
INDIRIZZO = "Piazza Carità, 14 - 80134 Napoli (NA)"

# Stessi colori dell'intestazione aziendale dei PDF del browser (salvia scuro).
SALVIA = colors.Color(63 / 255, 90 / 255, 78 / 255)
RIGA_ALTERNATA = colors.Color(246 / 255, 244 / 255, 238 / 255)
BORDO = colors.Color(230 / 255, 227 / 255, 217 / 255)
INCHIOSTRO = colors.Color(20 / 255, 20 / 255, 19 / 255)
AVVISO = colors.Color(138 / 255, 100 / 255, 16 / 255)

# Sopra questo numero di colonne la pagina si mette in orizzontale.
COLONNE_MAX_VERTICALE = 6


def _stili() -> Dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "titolo": ParagraphStyle("titolo", parent=base["Heading1"], fontSize=16, textColor=SALVIA,
                                 spaceAfter=2),
        "sezione": ParagraphStyle("sezione", parent=base["Heading3"], fontSize=11, textColor=SALVIA,
                                  spaceBefore=8, spaceAfter=4),
        "testo": ParagraphStyle("testo", parent=base["Normal"], fontSize=9, textColor=INCHIOSTRO),
        "nota": ParagraphStyle("nota", parent=base["Normal"], fontSize=8, textColor=AVVISO),
        "cella": ParagraphStyle("cella", parent=base["Normal"], fontSize=7.5, leading=9,
                                textColor=INCHIOSTRO),
        "cella_dx": ParagraphStyle("cella_dx", parent=base["Normal"], fontSize=7.5, leading=9,
                                   alignment=TA_RIGHT, textColor=INCHIOSTRO),
        "testata": ParagraphStyle("testata", parent=base["Normal"], fontSize=7.5, leading=9,
                                  textColor=colors.white, fontName="Helvetica-Bold"),
        "testata_dx": ParagraphStyle("testata_dx", parent=base["Normal"], fontSize=7.5, leading=9,
                                     textColor=colors.white, fontName="Helvetica-Bold",
                                     alignment=TA_RIGHT),
    }


def _p(testo: Any, stile: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(str(testo if testo is not None else "")), stile)


def _larghezze(sezione: Dict[str, Any], totale: float) -> List[float]:
    """Larghezze proporzionali ai pesi della sezione (o al contenuto piu' lungo).

    Una colonna con contenuto corto (data, importo) non scende mai sotto lo spazio che le
    serve: si stringono le altre, cosi' una data non va a capo su due righe.
    """
    colonne = sezione["colonne"]
    lunghezze = []
    for i, c in enumerate(colonne):
        lunghezze.append(max([len(str(c))] + [len(str(r[i])) for r in sezione["righe"][:200] if i < len(r)]))
    pesi = sezione.get("pesi") or [min(max(n, 6), 34) for n in lunghezze]
    somma = float(sum(pesi))
    larghezze = [totale * p / somma for p in pesi]
    minimi = [min(n, 16) * 3.9 + 9 for n in lunghezze]
    fisse = [i for i, (w, m) in enumerate(zip(larghezze, minimi)) if w < m]
    if fisse and len(fisse) < len(colonne):
        for i in fisse:
            larghezze[i] = minimi[i]
        libero = totale - sum(minimi[i] for i in fisse)
        altre = [i for i in range(len(colonne)) if i not in fisse]
        peso_altre = float(sum(pesi[i] for i in altre))
        for i in altre:
            larghezze[i] = libero * pesi[i] / peso_altre
    return larghezze


def _tabella(sezione: Dict[str, Any], stili: Dict[str, ParagraphStyle], larghezza: float) -> Table:
    allinea = sezione.get("allinea") or ["l"] * len(sezione["colonne"])
    testata = [_p(c, stili["testata_dx" if a == "r" else "testata"])
               for c, a in zip(sezione["colonne"], allinea)]
    corpo = [[_p(v, stili["cella_dx" if a == "r" else "cella"]) for v, a in zip(riga, allinea)]
             for riga in sezione["righe"]]
    tab = Table([testata] + corpo, colWidths=_larghezze(sezione, larghezza), repeatRows=1)
    stile = [
        ("BACKGROUND", (0, 0), (-1, 0), SALVIA),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, BORDO),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
    for n in range(2, len(corpo) + 1, 2):
        stile.append(("BACKGROUND", (0, n), (-1, n), RIGA_ALTERNATA))
    tab.setStyle(TableStyle(stile))
    return tab


def _riepilogo(righe: Sequence[Sequence[str]], stili: Dict[str, ParagraphStyle],
               larghezza: float) -> Table:
    dati = [[_p(e, stili["testo"]), _p(v, stili["cella_dx"])] for e, v in righe]
    tab = Table(dati, colWidths=[larghezza * 0.7, larghezza * 0.3])
    tab.setStyle(TableStyle([
        ("LINEABOVE", (0, 0), (-1, 0), 0.6, SALVIA),
        ("LINEBELOW", (0, -1), (-1, -1), 0.6, SALVIA),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return tab


def pdf_voce(voce: Dict[str, Any], periodo_etichetta: str, dal: str, al: str) -> bytes:
    """Il PDF di una voce del pacchetto. ``voce`` e' il dizionario di ``commercialista_pacchetto``."""
    sezioni = [s for s in voce.get("sezioni") or [] if s.get("righe")]
    larga = any(len(s["colonne"]) > COLONNE_MAX_VERTICALE for s in sezioni)
    pagina = landscape(A4) if larga else A4
    margine = 14 * mm
    utile = pagina[0] - 2 * margine
    stili = _stili()
    buffer = io.BytesIO()
    generato = datetime.now().strftime("%d/%m/%Y")

    def piede(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.Color(0.5, 0.5, 0.5))
        canvas.drawString(margine, 8 * mm,
                          f"Ceraldi Group S.R.L. - Generato il {generato} - Pagina {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(buffer, pagesize=pagina, leftMargin=margine, rightMargin=margine,
                            topMargin=14 * mm, bottomMargin=16 * mm,
                            title=f"{voce['titolo']} - {periodo_etichetta}", author=AZIENDA)
    elementi: List[Any] = [
        _p(AZIENDA, stili["titolo"]),
        _p(INDIRIZZO, stili["testo"]),
        Spacer(1, 6),
        _p(voce["titolo"].upper(), stili["titolo"]),
        _p(f"Periodo: {periodo_etichetta}", stili["testo"]),
        Spacer(1, 6),
    ]
    if voce.get("riepilogo"):
        elementi += [_riepilogo(voce["riepilogo"], stili, min(utile, 90 * mm)), Spacer(1, 6)]
    for avviso in voce.get("avvisi") or []:
        elementi.append(_p(f"Attenzione: {avviso}", stili["nota"]))
    for sezione in sezioni:
        if sezione.get("titolo"):
            elementi.append(_p(sezione["titolo"], stili["sezione"]))
        elementi.append(_tabella(sezione, stili, utile))
        if sezione.get("totali"):
            elementi += [Spacer(1, 4), _riepilogo(sezione["totali"], stili, min(utile, 90 * mm))]
    if not sezioni:
        elementi.append(_p("Nessun movimento nel periodo.", stili["testo"]))
    doc.build(elementi, onFirstPage=piede, onLaterPages=piede)
    return buffer.getvalue()


def csv_voce(voce: Dict[str, Any]) -> str:
    """Le stesse righe del PDF in CSV (separatore «;», come gli altri export)."""
    import csv

    uscita = io.StringIO()
    scrittore = csv.writer(uscita, delimiter=";")
    for sezione in voce.get("sezioni") or []:
        if sezione.get("titolo"):
            scrittore.writerow([sezione["titolo"]])
        scrittore.writerow(sezione["colonne"])
        scrittore.writerows(sezione["righe"])
        scrittore.writerow([])
    return uscita.getvalue()
