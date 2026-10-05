"""Consegna dell'ordine all'albergatore: PDF di ritiro e invio alla sua email.

Alla consegna, in Lotti, l'operatore preme un solo tasto: l'ordine passa a
«consegnato» e all'email dell'albergatore (quella della sua struttura) parte un
PDF con i prodotti ritirati, gli allergeni, i lotti e la fattura da cui nascono
(tracciabilita') e come si e' pagato. L'email non blocca la consegna: se manca o
non parte, l'ordine resta consegnato, l'esito si legge e il PDF si puo' rinviare.
"""

from __future__ import annotations

import asyncio
import io
import logging
from datetime import date, datetime, timezone
from typing import Any, Mapping

from app.lotti.azienda import get_azienda
from app.lotti.db import database as db

logger = logging.getLogger(__name__)


def _euro(valore: Any) -> str:
    try:
        return f"{float(valore):.2f}".replace(".", ",") + " €"
    except (TypeError, ValueError):
        return "—"


def _gg_mm_aaaa(iso: Any) -> str:
    try:
        return date.fromisoformat(str(iso)[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return str(iso or "")


def mascherata(email: str) -> str:
    nome, _, dominio = str(email or "").partition("@")
    return (nome[:2] + "***@" + dominio) if dominio else ""


def costruisci_pdf(ordine: Mapping[str, Any], azienda: Mapping[str, Any]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    salvia, sabbia = colors.HexColor("#3f5a4e"), colors.HexColor("#e6e0d4")
    st = getSampleStyleSheet()
    h = ParagraphStyle("h", parent=st["Title"], fontSize=18, textColor=salvia, alignment=0, spaceAfter=2)
    p = ParagraphStyle("p", parent=st["Normal"], fontSize=9.5, leading=12)
    piccolo = ParagraphStyle("s", parent=p, fontSize=8, textColor=colors.HexColor("#6b6256"))
    esc = lambda v: str(v or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")  # noqa: E731

    righe = [[Paragraph("<b>Qtà</b>", p), Paragraph("<b>Prodotto</b>", p),
              Paragraph("<b>Allergeni</b>", p), Paragraph("<b>Lotto e fattura</b>", p),
              Paragraph("<b>Importo</b>", p)]]
    for r in ordine.get("righe") or []:
        lotti = ", ".join(str(x.get("numero_lotto") or x.get("id") or "") for x in (r.get("lotti_associati") or []))
        fatture = ", ".join(
            f"fatt. {f.get('numero_fattura') or '—'} del {_gg_mm_aaaa(f.get('data_fattura'))}"
            for f in (r.get("fatture_origine") or []))
        trac = esc(lotti) if lotti else "lotto non ancora associato"
        if fatture:
            trac += f"<br/><font size=7>{esc(fatture)}</font>"
        righe.append([
            Paragraph(f"{int(r.get('quantita') or 0)}×", p),
            Paragraph(esc(r.get("nome")), p),
            Paragraph(esc(", ".join(r.get("allergeni") or []) or "—"), p),
            Paragraph(trac, p),
            Paragraph(_euro(r.get("totale")), p),
        ])
    tabella = Table(righe, colWidths=[12 * mm, 52 * mm, 38 * mm, 55 * mm, 22 * mm], repeatRows=1)
    tabella.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), sabbia), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#c9c1b0")),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    pagato = ordine.get("pagamento") == "incassato"
    metodo = "pagato dal borsellino" if ordine.get("pagamento_metodo") == "borsellino" and pagato else (
        "pagato" if pagato else "da incassare in loco")
    firma = Table([[Paragraph("Ritirato da (nome e firma)", piccolo), Paragraph("Consegnato da", piccolo)],
                   ["\n\n", "\n\n"]], colWidths=[90 * mm, 90 * mm])
    firma.setStyle(TableStyle([("BOX", (0, 0), (0, 1), 0.5, colors.HexColor("#c9c1b0")),
                               ("BOX", (1, 0), (1, 1), 0.5, colors.HexColor("#c9c1b0"))]))
    contenuto = [
        Paragraph("Documento di consegna prodotti", h),
        Paragraph(f"{esc(azienda.get('ragione_sociale'))} · {esc(azienda.get('indirizzo'))} · P.IVA {esc(azienda.get('partita_iva'))}", piccolo),
        Spacer(1, 8),
        Paragraph(f"<b>Hotel:</b> {esc(ordine.get('struttura_nome'))} &nbsp;&nbsp; <b>Ordine:</b> {esc(ordine.get('id'))}", p),
        Paragraph(f"<b>Consegna:</b> {_gg_mm_aaaa(ordine.get('data_consegna'))} ore {esc(ordine.get('ora_ritiro'))} "
                  f"&nbsp;&nbsp; <b>Emesso il:</b> {datetime.now().strftime('%d/%m/%Y %H:%M')}", p),
        Spacer(1, 8), tabella, Spacer(1, 8),
        Paragraph(f"<b>Totale {_euro(ordine.get('totale'))}</b> — {esc(metodo)}", p),
    ]
    if ordine.get("nota"):
        contenuto += [Spacer(1, 4), Paragraph(f"<b>Nota dell'hotel:</b> {esc(ordine.get('nota'))}", p)]
    contenuto += [Spacer(1, 16), firma, Spacer(1, 10),
                  Paragraph("Tracciabilità: il lotto dei prodotti del fornitore è formato da nome del prodotto, giorno di "
                            "consegna e numero della fattura di acquisto. Conservare questo documento.", piccolo)]
    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=15 * mm,
                      bottomMargin=15 * mm, title=f"Consegna {ordine.get('id')}").build(contenuto)
    return buf.getvalue()


async def _email_struttura(struttura_id: str) -> str:
    from app.services.colazioni_notifiche import _rpc_runtime

    esito = await _rpc_runtime("bb_ordini_contatti_struttura", {"psid": struttura_id})
    return str((esito or {}).get("email") or "").strip() if isinstance(esito, dict) else ""


async def consegna_e_invia(ordine_id: str, *, solo_pdf: bool = False, da: str = "operatore_lotti") -> dict[str, Any]:
    """Segna l'ordine consegnato (salvo `solo_pdf`) e manda il PDF all'email dell'albergatore."""
    from app.hr.services.email_smtp import invia_email
    from app.lotti.servizi.ordini_hotel import aggiorna_ordine

    ordine = await db.ordini_hotel.find_one({"id": ordine_id}, {"_id": 0})
    if not ordine:
        raise ValueError("Ordine hotel non trovato")
    if ordine.get("stato") == "annullato":
        raise ValueError("L'ordine e' annullato: nessuna consegna")
    if not solo_pdf and ordine.get("stato") != "consegnato":
        ordine = await aggiorna_ordine(ordine_id, stato="consegnato", da=da) or ordine
    esito: dict[str, Any] = {"ordine": ordine, "email_inviata": False, "a": "", "errore": ""}
    try:
        destinatario = await _email_struttura(str(ordine.get("struttura_id") or ""))
        if not destinatario:
            raise RuntimeError("La struttura non ha un indirizzo email: aggiungilo nella scheda dell'hotel")
        pdf = costruisci_pdf(ordine, await get_azienda())
        corpo = (f"Buongiorno,\n\nin allegato il documento di consegna dell'ordine {ordine.get('id')} "
                 f"({_gg_mm_aaaa(ordine.get('data_consegna'))} ore {ordine.get('ora_ritiro')}): prodotti ritirati, "
                 f"allergeni, lotti e fattura di provenienza.\n\nGrazie,\nCeraldi Group\n")
        await asyncio.to_thread(
            invia_email, destinatario, f"Consegna ordine {ordine.get('id')} · {ordine.get('struttura_nome')}", corpo,
            [(pdf, "application", "pdf", f"consegna-{ordine.get('id')}.pdf")])
        esito.update(email_inviata=True, a=mascherata(destinatario))
    except Exception as exc:
        esito["errore"] = str(exc) or type(exc).__name__
        logger.error("[CONSEGNA-HOTEL] PDF dell'ordine %s non inviato: %s: %s", ordine_id, type(exc).__name__, exc)
    ora = datetime.now(timezone.utc).isoformat()
    await db.ordini_hotel.update_one(
        {"id": ordine_id},
        {"$set": {"consegna_pdf": {"inviato": esito["email_inviata"], "a": esito["a"], "quando": ora,
                                    "errore": esito["errore"]}},
         "$push": {"audit": {"quando": ora, "azione": "consegna_pdf", "da": da,
                              "inviato": esito["email_inviata"], "solo_pdf": solo_pdf}}})
    esito["ordine"] = await db.ordini_hotel.find_one({"id": ordine_id}, {"_id": 0}) or ordine
    return esito
