"""
Portale buste paga del dipendente — a norma di consegna.

Il dipendente vede e scarica SOLO le proprie buste. Ogni accesso al documento
è tracciato in modo permanente nell'audit_log (visualizzazione, download,
presa visione) con data/ora esatta e IP. La presa visione/accettazione viene
memorizzata anche in `cedolini_accettazioni` per consultazione rapida.

NB: le meccaniche di tracciamento e consegna sono complete; la validità formale
"a norma di legge" in caso di contenzioso va confermata dal consulente del lavoro.
"""
import base64
import logging
import os
import ssl
import smtplib
import asyncio
import uuid
from email.message import EmailMessage
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import StreamingResponse

from app.hr.database import Database, Collections
from app.hr.utils.identity import get_identity
from app.hr.services.audit_logger import log_evento

logger = logging.getLogger(__name__)
router = APIRouter()

COLL_CED = "cedolini"
COLL_ACCETT = "cedolini_accettazioni"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _dipendente_keys(identity: Dict[str, Any]) -> Tuple[str, Optional[str]]:
    """Ritorna (dipendente_id, codice_fiscale) per filtrare le buste sue."""
    db = Database.get_db()
    dip = await db[Collections.EMPLOYEES].find_one(
        {"id": identity["id"]}, {"_id": 0, "id": 1, "codice_fiscale": 1}
    )
    cf = (dip.get("codice_fiscale") if dip else None) or None
    return identity["id"], cf


def _owner_query(dip_id: str, cf: Optional[str]) -> Dict[str, Any]:
    ors: List[Dict[str, Any]] = [{"dipendente_id": dip_id}]
    if cf:
        ors.append({"codice_fiscale": cf.upper()})
        ors.append({"codice_fiscale": cf})
    return {"$or": ors}


async def _carica_mia_busta(cedolino_id: str, identity: Dict[str, Any], proj=None) -> Dict[str, Any]:
    db = Database.get_db()
    # L'admin (titolare) può aprire la busta di QUALSIASI dipendente dal portale.
    if identity.get("role") == "admin":
        doc = await db[COLL_CED].find_one({"id": cedolino_id}, proj or {"_id": 0})
        if not doc:
            raise HTTPException(404, "Busta paga non trovata")
        return doc
    dip_id, cf = await _dipendente_keys(identity)
    q = {"$and": [{"id": cedolino_id}, _owner_query(dip_id, cf)]}
    doc = await db[COLL_CED].find_one(q, proj or {"_id": 0})
    if not doc:
        # 404 anche se esiste ma non è sua: non riveliamo l'esistenza
        raise HTTPException(404, "Busta paga non trovata")
    return doc


@router.get("", summary="Le mie buste paga (admin: tutte i dipendenti)")
async def le_mie_buste(anno: Optional[int] = None, q: Optional[str] = None,
                       identity: Dict[str, Any] = Depends(get_identity)) -> List[Dict[str, Any]]:
    db = Database.get_db()

    # === ADMIN: vede TUTTE le buste di tutti i dipendenti (filtrabili) ===
    if identity.get("role") == "admin":
        query: Dict[str, Any] = {}
        if anno:
            query["anno"] = {"$in": [anno, str(anno)]}
        if q:
            query["$or"] = [
                {"nome_dipendente": {"$regex": q, "$options": "i"}},
                {"dipendente_nome": {"$regex": q, "$options": "i"}},
            ]
        docs = await db[COLL_CED].find(
            query, {"_id": 0, "pdf_data": 0},
        ).sort([("anno", -1), ("mese", -1)]).to_list(3000)
        accettate = {a["cedolino_id"] async for a in db[COLL_ACCETT].find(
            {"esito": "accettata"}, {"_id": 0, "cedolino_id": 1})}
        out = []
        for c in docs:
            cid = c.get("id", "")
            out.append({
                "id": cid,
                "dipendente_nome": c.get("nome_dipendente") or c.get("dipendente_nome") or "—",
                "mese": c.get("mese"),
                "anno": c.get("anno"),
                "competenza": c.get("competenza"),
                "netto": c.get("netto", 0),
                "lordo": c.get("lordo", 0),
                "filename": c.get("filename") or c.get("pdf_filename"),
                "presa_visione": cid in accettate,
                "admin": True,
            })
        return out

    dip_id, cf = await _dipendente_keys(identity)
    docs = await db[COLL_CED].find(
        _owner_query(dip_id, cf),
        {"_id": 0, "pdf_data": 0},
    ).sort([("anno", -1), ("mese", -1)]).to_list(500)

    accettate = {a["cedolino_id"] async for a in db[COLL_ACCETT].find(
        {"dipendente_id": dip_id}, {"_id": 0, "cedolino_id": 1})}

    out = []
    for c in docs:
        cid = c.get("id", "")
        out.append({
            "id": cid,
            "mese": c.get("mese"),
            "anno": c.get("anno"),
            "competenza": c.get("competenza"),
            "netto": c.get("netto", 0),
            "lordo": c.get("lordo", 0),
            "acconto_cedolino": c.get("acconto_cedolino"),
            "saldo_residuo": c.get("saldo_residuo"),
            "filename": c.get("filename") or c.get("pdf_filename"),
            "ha_pdf": bool(c.get("pdf_data")) if "pdf_data" in c else None,
            "presa_visione": cid in accettate,
        })
    return out


@router.get("/{cedolino_id}", summary="Dettaglio busta + registra visualizzazione")
async def dettaglio_busta(cedolino_id: str, request: Request,
                          identity: Dict[str, Any] = Depends(get_identity)):
    doc = await _carica_mia_busta(cedolino_id, identity, proj={"_id": 0, "pdf_data": 0})
    db = Database.get_db()
    await log_evento(
        modulo="cedolini", azione="visualizzazione",
        entita_id=cedolino_id, entita_collection=COLL_CED, db=db,
        fonte="portale", utente=identity["id"],
        dettaglio=f"Visualizzazione busta {doc.get('mese')}/{doc.get('anno')}",
        extra={"ip": _client_ip(request), "user_agent": request.headers.get("user-agent", "")},
    )
    acc = await db[COLL_ACCETT].find_one(
        {"dipendente_id": identity["id"], "cedolino_id": cedolino_id}, {"_id": 0})
    doc["presa_visione"] = bool(acc)
    doc["presa_visione_il"] = acc.get("accettata_il") if acc else None
    return doc


@router.get("/{cedolino_id}/pdf", summary="Scarica il PDF + registra download")
async def scarica_pdf(cedolino_id: str, request: Request,
                      identity: Dict[str, Any] = Depends(get_identity)):
    doc = await _carica_mia_busta(cedolino_id, identity,
                                  proj={"_id": 0, "pdf_data": 1, "filename": 1,
                                        "pdf_filename": 1, "mese": 1, "anno": 1,
                                        "netto": 1, "lordo": 1, "dipendente_nome": 1,
                                        "acconto_cedolino": 1, "saldo_residuo": 1})
    pdf_data = doc.get("pdf_data")
    generato = False
    if pdf_data:
        try:
            pdf_bytes = base64.b64decode(pdf_data)
        except Exception:
            raise HTTPException(500, "PDF corrotto")
    else:
        # Nessun PDF originale (es. busta importata dal Libro Unico): genero un
        # riepilogo leggibile coi dati disponibili, così è comunque scaricabile.
        pdf_bytes = _genera_pdf_riepilogo(doc)
        generato = True

    db = Database.get_db()
    await log_evento(
        modulo="cedolini", azione="download",
        entita_id=cedolino_id, entita_collection=COLL_CED, db=db,
        fonte="portale", utente=identity["id"],
        dettaglio=f"Download busta {doc.get('mese')}/{doc.get('anno')}" + (" (riepilogo generato)" if generato else ""),
        extra={"ip": _client_ip(request), "user_agent": request.headers.get("user-agent", "")},
    )
    fname = doc.get("pdf_filename") or doc.get("filename") or f"busta_{doc.get('mese')}_{doc.get('anno')}.pdf"
    import io
    return StreamingResponse(
        io.BytesIO(pdf_bytes), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


def _genera_pdf_riepilogo(doc: Dict[str, Any]) -> bytes:
    """Genera un PDF di riepilogo della busta dai dati in cedolini quando manca l'originale."""
    import fitz
    pdf = fitz.open()
    page = pdf.new_page()
    mese = str(doc.get("mese", "")).zfill(2)
    anno = doc.get("anno", "")
    righe = [
        ("Ceraldi Group SRL", 20, True),
        ("Riepilogo busta paga", 14, False),
        ("", 8, False),
        (f"Dipendente: {doc.get('dipendente_nome', '') or '-'}", 12, False),
        (f"Periodo: {mese}/{anno}", 12, False),
        (f"Netto: € {float(doc.get('netto') or 0):.2f}", 13, True),
    ]
    if doc.get("lordo"):
        righe.append((f"Lordo: € {float(doc.get('lordo') or 0):.2f}", 11, False))
    if doc.get("acconto_cedolino"):
        righe.append((f"Acconto già erogato: € {float(doc['acconto_cedolino']):.2f}", 11, False))
        righe.append((f"Saldo da pagare: € {float(doc.get('saldo_residuo') or 0):.2f}", 11, False))
    righe.append(("", 10, False))
    righe.append(("Documento di riepilogo generato dal sistema. Il cedolino", 9, False))
    righe.append(("ufficiale completo è quello fornito dal consulente del lavoro.", 9, False))
    y = 70
    for testo, size, grassetto in righe:
        if testo:
            page.insert_text((60, y), testo, fontsize=size,
                             fontname="helv" if not grassetto else "hebo")
        y += size + 10
    return pdf.tobytes()


async def _nome_dipendente(identity, fallback=""):
    db = Database.get_db()
    dip = await db["dipendenti"].find_one({"id": identity["id"]}, {"_id": 0, "nome": 1, "cognome": 1})
    if dip:
        return f"{dip.get('cognome','')} {dip.get('nome','')}".strip() or fallback
    return fallback


async def _invia_pec(oggetto: str, testo: str) -> bool:
    """Invia una mail alla PEC aziendale per lasciare traccia (data certa) di
    accettazione/contestazione busta. Credenziali SOLO da env Render."""
    host = os.environ.get("PEC_HOST") or os.environ.get("SMTP_HOST") or "sendm.cert.legalmail.it"
    port = int(os.environ.get("PEC_PORT") or os.environ.get("SMTP_PORT") or 465)
    user = os.environ.get("PEC_USER") or os.environ.get("SMTP_EMAIL") or os.environ.get("SMTP_USER")
    pwd = os.environ.get("PEC_PASSWORD") or os.environ.get("SMTP_PASSWORD")
    dest = os.environ.get("PEC_DEST") or "ceraldigroupsrl@legalmail.it"
    if not (user and pwd):
        logger.warning("PEC non inviata (credenziali PEC/SMTP mancanti nelle env): %s", oggetto)
        return False

    def _send():
        msg = EmailMessage()
        msg["From"] = user
        msg["To"] = dest
        msg["Subject"] = oggetto
        msg.set_content(testo)
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=20) as s:
                s.login(user, pwd)
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=20) as s:
                s.starttls(context=ssl.create_default_context())
                s.login(user, pwd)
                s.send_message(msg)

    try:
        await asyncio.to_thread(_send)
        logger.info("PEC inviata: %s", oggetto)
        return True
    except Exception as e:
        logger.warning("PEC invio fallito (%s): %s", oggetto, e)
        return False


@router.post("/{cedolino_id}/presa-visione", summary="Conferma presa visione/accettazione")
async def presa_visione(cedolino_id: str, request: Request,
                        identity: Dict[str, Any] = Depends(get_identity)):
    doc = await _carica_mia_busta(cedolino_id, identity, proj={"_id": 0, "id": 1, "mese": 1, "anno": 1, "netto": 1, "dipendente_nome": 1})
    db = Database.get_db()
    esistente = await db[COLL_ACCETT].find_one(
        {"dipendente_id": identity["id"], "cedolino_id": cedolino_id}, {"_id": 0})
    if esistente:
        return {"ok": True, "gia_accettata": True, "accettata_il": esistente.get("accettata_il")}

    ip = _client_ip(request)
    ua = request.headers.get("user-agent", "")
    quando = _now()
    await db[COLL_ACCETT].insert_one({
        "id": f"acc_{uuid.uuid4().hex[:12]}",
        "dipendente_id": identity["id"],
        "cedolino_id": cedolino_id,
        "esito": "accettata",
        "accettata_il": quando, "ip": ip, "user_agent": ua,
    })
    await log_evento(
        modulo="cedolini", azione="presa_visione",
        entita_id=cedolino_id, entita_collection=COLL_CED, db=db,
        fonte="portale", utente=identity["id"],
        dettaglio=f"Presa visione/accettazione busta {doc.get('mese')}/{doc.get('anno')}",
        extra={"ip": ip, "user_agent": ua},
    )
    nome = await _nome_dipendente(identity, doc.get("dipendente_nome", ""))
    periodo = f"{str(doc.get('mese')).zfill(2)}/{doc.get('anno')}"
    await _invia_pec(
        f"Accettazione busta paga {periodo} — {nome}",
        f"Il dipendente {nome} ha ACCETTATO la busta paga di {periodo}.\n"
        f"Netto: € {float(doc.get('netto') or 0):.2f}\n"
        f"Data e ora accettazione: {quando}\nIP: {ip}\n\n"
        f"Messaggio generato automaticamente dal Portale Dipendenti.")
    return {"ok": True, "gia_accettata": False, "accettata_il": quando}


@router.post("/{cedolino_id}/contesta", summary="Contesta la busta (traccia + PEC)")
async def contesta_busta(cedolino_id: str, request: Request,
                         motivo: Optional[str] = None,
                         identity: Dict[str, Any] = Depends(get_identity)):
    doc = await _carica_mia_busta(cedolino_id, identity, proj={"_id": 0, "id": 1, "mese": 1, "anno": 1, "netto": 1, "dipendente_nome": 1})
    db = Database.get_db()
    ip = _client_ip(request)
    ua = request.headers.get("user-agent", "")
    quando = _now()
    await db[COLL_ACCETT].insert_one({
        "id": f"con_{uuid.uuid4().hex[:12]}",
        "dipendente_id": identity["id"],
        "cedolino_id": cedolino_id,
        "esito": "contestata",
        "motivo": motivo or "",
        "contestata_il": quando, "ip": ip, "user_agent": ua,
    })
    await log_evento(
        modulo="cedolini", azione="contestazione",
        entita_id=cedolino_id, entita_collection=COLL_CED, db=db,
        fonte="portale", utente=identity["id"],
        dettaglio=f"Contestazione busta {doc.get('mese')}/{doc.get('anno')}",
        extra={"ip": ip, "user_agent": ua, "motivo": motivo or ""},
    )
    nome = await _nome_dipendente(identity, doc.get("dipendente_nome", ""))
    periodo = f"{str(doc.get('mese')).zfill(2)}/{doc.get('anno')}"
    await _invia_pec(
        f"CONTESTAZIONE busta paga {periodo} — {nome}",
        f"Il dipendente {nome} ha CONTESTATO la busta paga di {periodo}.\n"
        f"Netto: € {float(doc.get('netto') or 0):.2f}\n"
        f"Data e ora contestazione: {quando}\nIP: {ip}\n"
        f"Motivo indicato: {motivo or '(da modulo allegato)'}\n\n"
        f"Messaggio generato automaticamente dal Portale Dipendenti.")
    return {"ok": True, "contestata_il": quando}


# Dati azienda destinataria della contestazione (configurabili da env Render).
AZIENDA = {
    "ragione_sociale": os.getenv("AZIENDA_RAGIONE_SOCIALE", "Ceraldi Group S.r.l."),
    "sede": os.getenv("AZIENDA_SEDE", "Napoli (NA)"),
    "piva": os.getenv("AZIENDA_PIVA", ""),
}

# Tutte le possibili cause di contestazione (spunta nel modulo).
CAUSE_CONTESTAZIONE = [
    "Ore lavorate non corrette / non corrispondenti a quelle effettive",
    "Giorni lavorati non corretti",
    "Mancata retribuzione di giornata festiva non retribuita",
    "Errata applicazione del regime fiscale (redditi/imposte errati)",
    "Straordinari non retribuiti o non corretti",
    "Maggiorazioni (notturno / festivo / domenicale) non riconosciute",
    "Ferie, permessi o ROL non corretti",
    "Mancata o errata corresponsione di acconti / anticipi",
    "Errato inquadramento o livello contrattuale",
    "Importo netto non corrispondente",
    "TFR o ratei (13ª / 14ª mensilità) errati",
    "Trattenute non dovute o non giustificate",
    "Mancato pagamento / pagamento parziale della retribuzione",
    "Altro (specificare nelle note)",
]


def _genera_modulo_contestazione(doc: Dict[str, Any], dip: Dict[str, Any]) -> bytes:
    """Modulo di contestazione busta paga precompilato: azienda + dipendente + busta + cause."""
    import fitz
    pdf = fitz.open()
    page = pdf.new_page()
    W = page.rect.width
    y = 56

    def txt(s, size=11, bold=False, gap=None, x=56, color=(0, 0, 0)):
        nonlocal y
        if s:
            page.insert_text((x, y), s, fontsize=size,
                             fontname="hebo" if bold else "helv", color=color)
        y += (gap if gap is not None else size + 7)

    def riga_firma(label_txt):
        nonlocal y
        page.insert_text((56, y), label_txt, fontsize=10, fontname="helv")
        page.draw_line((150, y + 2), (W - 56, y + 2), color=(0.55, 0.55, 0.55))
        y += 26

    def checkbox(label_txt):
        nonlocal y
        page.draw_rect(fitz.Rect(56, y - 9, 67, y + 2), color=(0.3, 0.3, 0.3), width=0.8)
        page.insert_text((74, y), label_txt, fontsize=10, fontname="helv")
        y += 18

    mese = str(doc.get("mese", "")).zfill(2)
    anno = doc.get("anno", "")
    netto = float(doc.get("netto") or 0)
    nome_dip = (f"{dip.get('cognome', '')} {dip.get('nome', '')}".strip()
                if dip else (doc.get("dipendente_nome") or ""))
    cf_dip = (dip.get("codice_fiscale") if dip else "") or ""

    # Intestazione azienda
    txt(AZIENDA["ragione_sociale"], 15, True, gap=18)
    sub = f"Sede: {AZIENDA['sede']}"
    if AZIENDA["piva"]:
        sub += f"   ·   P.IVA/C.F.: {AZIENDA['piva']}"
    txt(sub, 9, color=(0.35, 0.35, 0.35), gap=8)
    page.draw_line((56, y), (W - 56, y), color=(0.8, 0.8, 0.8))
    y += 22

    txt("MODULO DI CONTESTAZIONE DELLA BUSTA PAGA", 13, True, gap=22)

    txt(f"Spett.le {AZIENDA['ragione_sociale']}", 11, gap=18)
    txt("Il/La sottoscritto/a:", 10, gap=15)
    txt(f"Nome e cognome: {nome_dip or '________________________'}", 11)
    txt(f"Codice fiscale: {cf_dip or '________________________'}", 11, gap=20)

    txt("in qualità di lavoratore/lavoratrice dipendente, contesta formalmente la", 10, gap=14)
    txt("busta paga di seguito identificata:", 10, gap=18)
    txt(f"Periodo (mese/anno): {mese}/{anno}", 11, True)
    txt(f"Importo netto indicato in busta: € {netto:.2f}", 11, True, gap=22)

    txt("Motivo/i della contestazione (barrare le caselle pertinenti):", 11, True, gap=18)
    for c in CAUSE_CONTESTAZIONE:
        checkbox(c)
    y += 6

    txt("Note / descrizione dettagliata:", 10, True, gap=16)
    for _ in range(4):
        page.draw_line((56, y), (W - 56, y), color=(0.7, 0.7, 0.7))
        y += 20
    y += 6

    txt("Importo/i ritenuto/i errato/i (€): ____________________________", 10, gap=18)
    txt("Richiesta del dipendente: ____________________________________", 10, gap=26)

    riga_firma("Luogo e data:")
    riga_firma("Firma del dipendente:")
    y += 6
    txt("Spazio riservato all'azienda", 9, True, color=(0.35, 0.35, 0.35), gap=15)
    txt("Esito:  [ ] Accolta    [ ] Respinta    [ ] In valutazione", 10, gap=16)
    riga_firma("Firma azienda:")
    return pdf.tobytes()


@router.get("/{cedolino_id}/modulo-contestazione", summary="Modulo di contestazione precompilato (PDF)")
async def modulo_contestazione(cedolino_id: str,
                               identity: Dict[str, Any] = Depends(get_identity)):
    doc = await _carica_mia_busta(
        cedolino_id, identity,
        proj={"_id": 0, "id": 1, "mese": 1, "anno": 1, "netto": 1,
              "dipendente_id": 1, "dipendente_nome": 1})
    db = Database.get_db()
    dip = await db[Collections.EMPLOYEES].find_one(
        {"id": doc.get("dipendente_id")},
        {"_id": 0, "nome": 1, "cognome": 1, "codice_fiscale": 1}) or {}
    pdf_bytes = _genera_modulo_contestazione(doc, dip)
    import io
    mese = str(doc.get("mese", "")).zfill(2)
    fname = f"contestazione_busta_{mese}_{doc.get('anno')}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@router.get("/{cedolino_id}/storico-accessi", summary="Storico accessi a questa busta (admin)")
async def storico_accessi(cedolino_id: str,
                          identity: Dict[str, Any] = Depends(get_identity)):
    # admin vede il registro permanente; il dipendente vede solo il proprio
    db = Database.get_db()
    q = {"entita_id": cedolino_id, "entita_collection": COLL_CED}
    if identity.get("role") != "admin":
        await _carica_mia_busta(cedolino_id, identity, proj={"_id": 0, "id": 1})
        q["utente"] = identity["id"]
    return await db["audit_log"].find(q, {"_id": 0}).sort("timestamp", -1).to_list(500)
