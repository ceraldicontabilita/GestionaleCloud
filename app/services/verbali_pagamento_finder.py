"""
Ricerca pagamento verbale multi-fonte (FASE 3):
1. paypal_transactions (IUV / numero_verbale / targa+importo)
2. Gmail ricevute PagoPA (noreply-checkout@ricevute.pagopa.it, noreply_paytech@mooney.it, partenopay@ext.comune.napoli.it)
3. estratto_conto_movimenti (SDD PayPal entro 90gg)
"""
import imaplib
import email as email_lib
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional
from app.services.sheets_document_store import SheetDatabase

from app.config import settings
from app.services.payment_invoice_matching import amounts_equal_to_cent
from app.services.verbali_iuv_extractor import get_iuv_from_verbale

logger = logging.getLogger(__name__)
UPLOAD_DIR = "/tmp/uploads/paypal_ricevute"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Mappatura PSP PayPal (paypal_account_id → nome PSP)
PSP_MAP = {
    "2X2JC2B7ZHST6": "Intesa Sanpaolo",
    "8C4NDFWNCN3JY": "Mooney (PayTipper)",
}


def _documentary_evidence_id(match: Dict[str, Any]) -> Optional[str]:
    """Restituisce l'identita' stabile della prova documentale, se presente."""
    for field in (
        "ricevuta_pagopa_id",
        "paypal_transaction_id",
        "gmail_message_id",
    ):
        value = str(match.get(field) or "").strip()
        if value:
            return value
    return None


def _paypal_candidate_id(doc: Dict[str, Any]) -> Optional[str]:
    """Una transazione senza ID provider non e' collegabile automaticamente."""
    value = str(doc.get("transaction_id") or "").strip()
    return value or None


async def trova_pagamento_verbale(db: SheetDatabase, verbale: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    iuv = get_iuv_from_verbale(verbale)
    numero_verbale = verbale.get("numero_verbale")
    targa = verbale.get("targa")
    importo = verbale.get("importo") or verbale.get("importo_addebitato_fornitore") or 0

    has_documentary_evidence = bool(
        verbale.get("pagato_documentalmente")
        or verbale.get("ricevuta_pagopa_id")
        or verbale.get("paypal_transaction_id")
    )
    has_bank_evidence = bool(
        verbale.get("banca_verificata") or verbale.get("movimento_banca_id")
    )

    # Le due attese sono indipendenti: dopo la ricevuta continuiamo a cercare
    # la banca; dopo la banca continuiamo a cercare la ricevuta.
    if not has_documentary_evidence:
        m = await _cerca_in_paypal(db, iuv, numero_verbale, targa, importo)
        if m:
            return m
        m = await _cerca_in_gmail(db, iuv, numero_verbale, importo, verbale)
        if m:
            return m

    if not has_bank_evidence:
        # Importo e data da soli non identificano un pagamento: serve anche un
        # riferimento esplicito del verbale/IUV/targa e un candidato unico.
        return await _cerca_in_estratto_conto(
            db, iuv, numero_verbale, targa, importo, verbale
        )
    return None


async def _cerca_in_paypal(db, iuv, numero_verbale, targa, importo):
    queries = []
    if iuv:
        queries.append({"$or": [
            {"iuv": iuv},  # denormalizzato via bulk-assegna
            {"custom_field": {"$regex": iuv}},
            {"transaction_subject": {"$regex": iuv}},
            {"invoice_id_fornitore": iuv},
            {"ricevuta_dati.iuv": iuv},
        ]})
    if numero_verbale:
        queries.append({"$or": [
            {"numero_verbale_collegato": numero_verbale},  # denormalizzato via bulk-assegna
            {"transaction_subject": {"$regex": re.escape(numero_verbale)}},
            {"ricevuta_dati.verbale": numero_verbale},
        ]})
    if targa and importo and float(importo) > 0:
        imp = float(importo)
        queries.append({
            "$or": [
                {"targa_collegata": targa},
                {"transaction_subject": {"$regex": re.escape(targa), "$options": "i"}},
            ],
            "importo": {"$gte": -imp - 2, "$lte": -imp + 2},
        })
    candidates: Dict[str, Dict[str, Any]] = {}
    for q in queries:
        docs = await db["paypal_transactions"].find(q, {"_id": 0}).limit(20).to_list(20)
        for doc in docs:
            if importo and not amounts_equal_to_cent(doc.get("importo") or doc.get("lordo"), importo):
                continue
            candidate_id = _paypal_candidate_id(doc)
            if not candidate_id:
                continue
            candidates[candidate_id] = doc

    # Il primo risultato del provider non e' una prova di unicita'. Se due
    # transazioni distinte soddisfano le regole, il verbale resta da verificare.
    if len(candidates) != 1:
        return None

    doc = next(iter(candidates.values()))
    return {
        "fonte": "paypal",
        "psp": PSP_MAP.get(
            doc.get("paypal_account_id", ""),
            f"PSP {(doc.get('paypal_account_id') or '?')[:8]}"
        ),
        "importo": abs(doc.get("importo", 0) or doc.get("lordo", 0) or 0),
        "data_pagamento": doc.get("initiation_date"),
        "metodo_pagamento": "PayPal",
        "paypal_transaction_id": doc.get("transaction_id"),
        "pdf_ricevuta_path": doc.get("pdf_ricevuta_path"),
        "iuv_usato": iuv,
        "dettagli_grezzi": {
            "paypal_account_id": doc.get("paypal_account_id"),
            "custom_field": doc.get("custom_field"),
            "transaction_subject": doc.get("transaction_subject"),
        },
    }


async def _cerca_in_gmail(db, iuv, numero_verbale, importo, verbale):
    user = settings.GMAIL_EMAIL or settings.IMAP_USER
    pwd = settings.GMAIL_APP_PASSWORD or settings.IMAP_PASSWORD
    if not user or not pwd:
        return None
    SENDERS = [
        "noreply-checkout@ricevute.pagopa.it",
        "noreply_paytech@mooney.it",
        "partenopay@ext.comune.napoli.it",
        "partenopay@comune.napoli.it",
    ]
    from_clause = " OR ".join(f"from:{s}" for s in SENDERS)
    search_terms = [t for t in [iuv, numero_verbale] if t]
    if not search_terms:
        return None

    try:
        conn = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        conn.login(user, pwd)
        conn.select("INBOX")
    except Exception as e:
        logger.warning("Gmail connect fallito: %s", e)
        return None

    candidates: Dict[str, Dict[str, Any]] = {}
    try:
        for term in search_terms:
            q = f'(X-GM-RAW "({from_clause}) {term}")'
            status, data = conn.search(None, q)
            if status != "OK" or not data or not data[0]:
                continue
            for num in data[0].split():
                try:
                    _, mdata = conn.fetch(num, "(RFC822)")
                    msg = email_lib.message_from_bytes(mdata[0][1])
                except Exception:
                    continue
                from app.services._email_utils import extract_best_body
                body_txt = extract_best_body(msg)
                pdf_a = None
                for p in msg.walk():
                    if p.get_content_type() == "application/pdf":
                        pdf_a = p
                        break
                parsed = _parse_pagopa_body(body_txt)
                if iuv and parsed.get("iuv") and parsed["iuv"] != iuv:
                    continue
                if numero_verbale and parsed.get("verbale") and parsed["verbale"] != numero_verbale:
                    continue
                key = numero_verbale or iuv or "unknown"
                pdf_path = os.path.join(UPLOAD_DIR, f"pagopa_verbale_{key}.pdf")
                if pdf_a:
                    with open(pdf_path, "wb") as f:
                        f.write(pdf_a.get_payload(decode=True))
                else:
                    _genera_pdf_da_testo(body_txt, pdf_path)

                # Prova sempre a leggere il PDF allegato per completare i metadata mancanti
                # (PartenoPay non espone PSP/metodo nel body, li troviamo solo nel PDF attestazione)
                if pdf_a and (not parsed.get("totale") or not parsed.get("iuv")
                              or not parsed.get("psp") or not parsed.get("metodo")):
                    pdf_parsed = _parse_pagopa_pdf(pdf_path)
                    for k, v2 in pdf_parsed.items():
                        if v2 and not parsed.get(k):
                            parsed[k] = v2

                # Default basati sul mittente quando i campi non sono presenti nel body
                sender = (msg.get("From") or "").lower()
                if "partenopay" in sender:
                    default_psp = "PartenoPay (Comune di Napoli)"
                    default_metodo = "PagoPA"
                elif "mooney" in sender:
                    default_psp = "Mooney (PayTipper)"
                    default_metodo = "PagoPA"
                elif "pagopa" in sender:
                    default_psp = "PagoPA"
                    default_metodo = "PagoPA"
                else:
                    default_psp = "PagoPA"
                    default_metodo = "PagoPA"

                if importo and not amounts_equal_to_cent(parsed.get("totale"), importo):
                    continue
                message_id = str(msg.get("Message-ID") or "").strip() or None
                candidate_key = message_id or f"imap:{num.decode(errors='ignore')}"
                candidates[candidate_key] = {
                    "fonte": "gmail",
                    "psp": parsed.get("psp") or default_psp,
                    "importo": parsed.get("totale") or 0,
                    "data_pagamento": parsed.get("data_pagamento"),
                    "metodo_pagamento": parsed.get("metodo") or default_metodo,
                    "paypal_transaction_id": None,
                    "gmail_message_id": message_id,
                    "pdf_ricevuta_path": pdf_path,
                    "iuv_usato": parsed.get("iuv") or iuv,
                    "dettagli_grezzi": parsed,
                }
    finally:
        try:
            conn.logout()
        except Exception:
            pass

    # Anche Gmail puo' contenere piu' ricevute con lo stesso riferimento e
    # importo (reinoltri, tentativi ripetuti, operazioni distinte). In quel
    # caso nessuna viene applicata automaticamente.
    if len(candidates) != 1:
        return None
    return next(iter(candidates.values()))


def _parse_pagopa_body(body):
    """Parser multi-formato email PagoPA: pagopa.it, mooney.it, PartenoPay."""
    out = {}
    def _m(patterns, f=0):
        if isinstance(patterns, str):
            patterns = [patterns]
        for pat in patterns:
            r = re.search(pat, body, f)
            if r:
                return r.group(1).strip()
        return None

    out["iuv"] = _m([
        r'Codice Avviso[:\s]*(\d{18})',
        r'\b([03]\d{17})\b',
    ])
    out["verbale"] = _m([
        r'VERBALE N\.?\s*:\s*([A-Z0-9]+)',
        r'Verbale N\.?\s*:?\s*([A-Z]\d{10,12})',
    ], re.IGNORECASE)
    out["targa"] = _m([
        r'TARGA[:\s]*([A-Z]{2}\d{3}[A-Z]{2})',
        r'TARGA[:\s]*([A-Z0-9]+)',
    ], re.IGNORECASE)
    out["ente_creditore"] = _m([
        r'Ente creditore[:\s]*([^\n]+)',
        r'Ente Beneficiario[:\s]*([^\n]+)',
    ], re.IGNORECASE)
    out["data_infrazione"] = _m([
        r'VERBALE.*?DATA[:\s]*(\d{2}/\d{2}/\d{2,4})',
        r'\bDATA\b[:\s]*(\d{2}/\d{2}/\d{2,4})',
    ], re.IGNORECASE | re.DOTALL)
    out["psp"] = _m([
        r'Gestore della transazione \(PSP\)[:\s]*([^\n]+)',
        r'PSP[:\s]*([^\n]+)',
    ], re.IGNORECASE)
    out["metodo"] = _m([
        r'Metodo di pagamento[:\s]*([^\n]+)',
        r'Tipo pagamento[:\s]*([^\n]+)',
    ], re.IGNORECASE)
    out["codice_transazione"] = _m(
        r'codice transazione[:\s]*([a-f0-9]+)', re.IGNORECASE
    )
    out["data_pagamento"] = _m([
        r'Data e ora[:\s]*([^\n]+)',
        r'Data pagamento[:\s]*(\d{2}/\d{2}/\d{4}(?:[ ,]+\d{2}:\d{2}(?::\d{2})?)?)',
        r'Data del pagamento[:\s]*([^\n]+)',
    ], re.IGNORECASE)

    imp = _m([
        r'Totale[:\s]*([\d.]+,\d{2})\s*€',
        r'Importo\s*\[?€?\]?[:\s]*([\d.]+,\d{2})',
        r'Importo\s+pagato[:\s]*€?\s*([\d.]+,\d{2})',
        r'€\s*([\d.]+,\d{2})',
    ], re.IGNORECASE)
    if imp:
        try:
            out["totale"] = float(imp.replace(".", "").replace(",", "."))
        except ValueError:
            pass
    return out


def _parse_pagopa_pdf(pdf_path):
    """Estrai iuv/totale/data/psp dal PDF allegato quando il body testuale non li contiene."""
    out = {}
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            text = "\n".join((p.extract_text() or "") for p in pdf.pages)
    except Exception:
        return out
    # delega il parsing dei campi al body parser
    parsed = _parse_pagopa_body(text)
    for k, v in parsed.items():
        if v is not None:
            out[k] = v
    # fallback extra: cerca importo generico
    if not out.get("totale"):
        m = re.search(r'€\s*([\d.]+,\d{2})', text)
        if m:
            try:
                out["totale"] = float(m.group(1).replace(".", "").replace(",", "."))
            except ValueError:
                pass
    # fallback: IUV senza prefisso strict
    if not out.get("iuv"):
        m = re.search(r'\b([03]\d{17})\b', text)
        if m:
            out["iuv"] = m.group(1)
    return out


def _genera_pdf_da_testo(testo, path, titolo="Ricevuta"):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import cm
    c = canvas.Canvas(path, pagesize=A4)
    _, h = A4
    c.setFont("Helvetica-Bold", 14)
    c.drawString(2*cm, h-2*cm, titolo)
    c.setFont("Helvetica", 9)
    y = h - 3*cm
    for line in testo.split("\n"):
        if y < 2*cm:
            c.showPage()
            y = h - 2*cm
        c.drawString(2*cm, y, line[:100])
        y -= 0.4*cm
    c.save()


async def _cerca_in_estratto_conto(db, iuv, numero_verbale, targa, importo, verbale):
    if not importo or float(importo) <= 0:
        return None
    imp = float(importo)
    data_v = (
        verbale.get("data_verbale")
        or verbale.get("data_infrazione")
        or verbale.get("data_violazione")
        or verbale.get("data_ricezione_notifica")
    )
    if not data_v:
        return None
    try:
        data_s = str(data_v)[:10]
        if "/" in data_s:
            d, m, y = data_s.split("/")
            data_dt = datetime(int(y), int(m), int(d))
        else:
            data_dt = datetime.fromisoformat(data_s)
    except Exception:
        return None
    after = data_dt.strftime("%Y-%m-%d")
    before = (data_dt + timedelta(days=120)).strftime("%Y-%m-%d")
    riferimenti = [str(v).strip() for v in (iuv, numero_verbale, targa) if str(v or "").strip()]
    if not riferimenti:
        return None
    riferimento_rx = "|".join(re.escape(value) for value in riferimenti)
    movimenti = await db["estratto_conto_movimenti"].find({
        "$or": [
            {"descrizione": {"$regex": riferimento_rx, "$options": "i"}},
            {"descrizione_originale": {"$regex": riferimento_rx, "$options": "i"}},
        ],
        "$and": [
            {"$or": [
                {"importo": {"$gte": imp - 0.004, "$lte": imp + 0.004}},
                {"importo": {"$gte": -imp - 0.004, "$lte": -imp + 0.004}},
            ]},
            {"$or": [
                {"data_contabile": {"$gte": after, "$lte": before}},
                {"data": {"$gte": after, "$lte": before}},
            ]},
        ],
    }).limit(20).to_list(20)
    movimenti = [m for m in movimenti if amounts_equal_to_cent(m.get("importo"), imp)]
    if len(movimenti) != 1:
        return None
    mov = movimenti[0]
    return {
        "fonte": "estratto_conto",
        "psp": "SDD PayPal",
        "importo": abs(mov.get("importo", 0) or 0),
        "data_pagamento": mov.get("data_contabile"),
        "metodo_pagamento": "PayPal (SDD)",
        "paypal_transaction_id": None,
        "movimento_id": str(mov.get("id") or mov.get("_id") or ""),
        "pdf_ricevuta_path": None,
        "iuv_usato": None,
        "dettagli_grezzi": {
            "descrizione": mov.get("descrizione"),
            "movimento_id": str(mov.get("_id")) if mov.get("_id") else None,
        },
    }


async def applica_pagamento_a_verbale(db, verbale_id, match):
    """Collega una prova univoca mantenendo ricevuta e banca indipendenti."""
    verbale = await db["verbali_noleggio"].find_one(
        {"$or": [{"id": verbale_id}, {"numero_verbale": verbale_id}]},
        {"_id": 0},
    )
    if not verbale:
        return False

    verbale_amount = (
        verbale.get("importo") or verbale.get("importo_addebitato_fornitore")
    )
    if not amounts_equal_to_cent(verbale_amount, match.get("importo")):
        return False

    incoming_documentary_id = _documentary_evidence_id(match)
    incoming_bank_id = str(match.get("movimento_id") or "").strip() or None
    if not incoming_documentary_id and not incoming_bank_id:
        return False

    documentary_verified = bool(
        incoming_documentary_id
        or verbale.get("pagato_documentalmente")
        or verbale.get("ricevuta_pagopa_id")
        or verbale.get("paypal_transaction_id")
    )
    bank_verified = bool(
        incoming_bank_id
        or verbale.get("banca_verificata")
        or verbale.get("movimento_banca_id")
    )

    if documentary_verified and bank_verified:
        stato = "riconciliato"
        stato_pratica = "RICONCILIATO_BANCA"
    elif documentary_verified:
        stato = "pagato"
        stato_pratica = "PAGATO_DOCUMENTALE"
    else:
        stato = "pagato_attesa_quietanza"
        stato_pratica = "ATTESA_QUIETANZA"

    pagamento_id = (
        match.get("paypal_transaction_id")
        or match.get("ricevuta_pagopa_id")
        or verbale.get("pagamento_id")
        or incoming_bank_id
    )
    update = {
        "stato": stato,
        "stato_pratica": stato_pratica,
        "pagato_documentalmente": documentary_verified,
        "banca_verificata": bank_verified,
        "fonte_pagamento": (
            match.get("fonte") if incoming_documentary_id
            else verbale.get("fonte_pagamento")
        ),
        "importo": match.get("importo") or None,
        "metodo_pagamento": match.get("metodo_pagamento"),
        "psp": match.get("psp"),
        "data_pagamento": match.get("data_pagamento"),
        "fonte_riconciliazione": match.get("fonte"),
        "riconciliato_paypal": bool(
            verbale.get("riconciliato_paypal") or match.get("fonte") == "paypal"
        ),
        "pdf_ricevuta_path": match.get("pdf_ricevuta_path"),
        "paypal_transaction_id": (
            match.get("paypal_transaction_id") or verbale.get("paypal_transaction_id")
        ),
        "movimento_banca_id": incoming_bank_id or verbale.get("movimento_banca_id"),
        "ricevuta_pagopa_id": (
            match.get("ricevuta_pagopa_id") or verbale.get("ricevuta_pagopa_id")
        ),
        "gmail_message_id": (
            match.get("gmail_message_id") or verbale.get("gmail_message_id")
        ),
        "pagamento_id": pagamento_id,
        "iuv": match.get("iuv_usato"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    update = {k: v for k, v in update.items() if v is not None}
    res = await db["verbali_noleggio"].update_one(
        {"$or": [{"id": verbale_id}, {"numero_verbale": verbale_id}]},
        {"$set": update}
    )
    if res.modified_count > 0 and verbale:
        reverse = {
            "verbale_id": verbale.get("id") or verbale_id,
            "numero_verbale_collegato": verbale.get("numero_verbale") or verbale_id,
        }
        if match.get("paypal_transaction_id"):
            await db["paypal_transactions"].update_one(
                {"transaction_id": match["paypal_transaction_id"]}, {"$set": reverse}
            )
        if match.get("movimento_id"):
            await db["estratto_conto_movimenti"].update_one(
                {"$or": [{"id": match["movimento_id"]}, {"_id": match["movimento_id"]}]},
                {"$set": reverse},
            )
        if match.get("ricevuta_pagopa_id"):
            await db["ricevute_pagopa"].update_one(
                {"id": match["ricevuta_pagopa_id"]}, {"$set": reverse}
            )
    return res.modified_count > 0


async def riconcilia_verbali_strict(db) -> Dict[str, Any]:
    """Riconcilia solo con prove strutturate, mai per importo/data da soli.

    Le fonti ammesse sono quelle verificate da ``trova_pagamento_verbale``:
    IUV o numero verbale (oppure targa esplicita) e importo uguale al
    centesimo. Un candidato assente o ambiguo resta non riconciliato.
    """
    verbali = await db["verbali_noleggio"].find(
        {
            "$and": [
                {"$or": [
                    {"numero_verbale": {"$nin": [None, ""]}},
                    {"iuv": {"$nin": [None, ""]}},
                ]},
                {"$or": [
                    {"pagato_documentalmente": {"$ne": True}},
                    {"banca_verificata": {"$ne": True}},
                ]},
            ],
        },
        {"_id": 0},
    ).to_list(1000)
    stats: Dict[str, Any] = {
        "verbali_da_riconciliare": len(verbali),
        "riconciliati": 0,
        "riconciliati_paypal": 0,
        "riconciliati_pagopa": 0,
        "riconciliati_banca": 0,
        "non_riconciliati": 0,
        "errori": 0,
        "regola": "prova_univoca_riferimento_strutturato_importo_esatto",
    }
    for verbale in verbali:
        try:
            match = await trova_pagamento_verbale(db, verbale)
            if not match:
                stats["non_riconciliati"] += 1
                continue
            verbale_id = verbale.get("id") or verbale.get("numero_verbale")
            if not verbale_id or not await applica_pagamento_a_verbale(db, verbale_id, match):
                stats["non_riconciliati"] += 1
                continue
            stats["riconciliati"] += 1
            fonte = str(match.get("fonte") or "").lower()
            if fonte == "paypal":
                stats["riconciliati_paypal"] += 1
            elif fonte == "gmail":
                stats["riconciliati_pagopa"] += 1
            elif fonte == "estratto_conto":
                stats["riconciliati_banca"] += 1
        except Exception:
            logger.exception(
                "Errore riconciliazione verbale %s",
                verbale.get("numero_verbale") or verbale.get("id"),
            )
            stats["errori"] += 1
    return stats
