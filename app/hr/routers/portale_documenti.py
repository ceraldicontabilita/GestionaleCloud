"""
Portale documenti del dipendente.

Il dipendente vede/scarica SOLO i propri documenti. Può:
  - scaricare i moduli vuoti (contestazione busta, richiesta ferie, richiesta acconto TFR);
  - caricare i propri documenti (contestazione compilata, modulo ferie/TFR, documento di riconoscimento);
  - scaricare ciò che l'azienda ha caricato per lui (Certificazione Unica, Unilav).

L'azienda (admin) carica per un dipendente i documenti riservati (CU, Unilav, ecc.).
Tutti i file sono salvati su Mongo (base64) nella collezione esistente `documenti_cloud`,
così non dipendono dal disco effimero di Render.
"""
import base64
import io
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, HTTPException, Request, Depends, UploadFile, File, Form, Query
from fastapi.responses import StreamingResponse

from app.hr.database import Database
from app.hr.utils.identity import get_identity

logger = logging.getLogger(__name__)
router = APIRouter()

COLL = "documenti_cloud"
MAX_BYTES = 12 * 1024 * 1024  # 12 MB per file

# tipo -> (etichetta, è un modulo scaricabile, il dipendente può caricarlo)
TIPI: Dict[str, Dict[str, Any]] = {
    "contestazione":          {"label": "Contestazione busta paga", "modulo": True,  "upload_dip": True},
    "richiesta_ferie":        {"label": "Richiesta ferie / permessi", "modulo": True, "upload_dip": True},
    "richiesta_acconto_tfr":  {"label": "Richiesta acconto TFR",     "modulo": True,  "upload_dip": True},
    "certificazione_unica":   {"label": "Certificazione Unica (CU)", "modulo": False, "upload_dip": False},
    "unilav":                 {"label": "Unilav",                    "modulo": False, "upload_dip": False},
    "documento_riconoscimento": {"label": "Documento di riconoscimento", "modulo": False, "upload_dip": True},
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_admin(identity: Dict[str, Any]) -> bool:
    return (identity.get("role") or identity.get("ruolo")) == "admin"


@router.get("/tipi", summary="Catalogo tipi documento")
async def tipi_documento(identity: Dict[str, Any] = Depends(get_identity)):
    return [{"tipo": k, **v} for k, v in TIPI.items()]


@router.get("", summary="I miei documenti")
async def i_miei_documenti(identity: Dict[str, Any] = Depends(get_identity)) -> List[Dict[str, Any]]:
    db = Database.get_db()
    docs = await db[COLL].find(
        {"dipendente_id": identity["id"]},
        {"_id": 0, "file_data": 0},  # mai il contenuto nella lista
    ).sort("caricato_il", -1).to_list(500)
    for d in docs:
        info = TIPI.get(d.get("tipo") or "", {})
        d.setdefault("label", info.get("label", d.get("tipo", "Documento")))
    return docs


@router.post("/upload", summary="Carico un mio documento")
async def upload_documento(
    request: Request,
    tipo: str = Form(...),
    file: UploadFile = File(...),
    identity: Dict[str, Any] = Depends(get_identity),
):
    info = TIPI.get(tipo)
    if not info:
        raise HTTPException(400, "Tipo documento non valido")
    if not info["upload_dip"]:
        raise HTTPException(403, "Questo tipo di documento può caricarlo solo l'azienda")
    contenuto = await file.read()
    if not contenuto:
        raise HTTPException(400, "File vuoto")
    if len(contenuto) > MAX_BYTES:
        raise HTTPException(413, "File troppo grande (max 12 MB)")
    doc = {
        "id": str(uuid.uuid4()),
        "dipendente_id": identity["id"],
        "tipo": tipo,
        "label": info["label"],
        "categoria": "caricato_dipendente",
        "nome_file": file.filename or f"{tipo}.pdf",
        "mime": file.content_type or "application/octet-stream",
        "dimensione": len(contenuto),
        "file_data": base64.b64encode(contenuto).decode(),
        "caricato_da": "dipendente",
        "caricato_il": _now(),
    }
    await Database.get_db()[COLL].insert_one(doc)
    return {"ok": True, "id": doc["id"], "nome_file": doc["nome_file"]}


@router.get("/{doc_id}/file", summary="Scarico un mio documento")
async def scarica_documento(doc_id: str, identity: Dict[str, Any] = Depends(get_identity)):
    db = Database.get_db()
    doc = await db[COLL].find_one(
        {"id": doc_id, "dipendente_id": identity["id"]}, {"_id": 0})
    if not doc or not doc.get("file_data"):
        raise HTTPException(404, "Documento non trovato")
    try:
        raw = base64.b64decode(doc["file_data"])
    except Exception:
        raise HTTPException(500, "File corrotto")
    fname = doc.get("nome_file") or f"{doc.get('tipo','documento')}.pdf"
    return StreamingResponse(
        io.BytesIO(raw), media_type=doc.get("mime") or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.delete("/{doc_id}", summary="Elimino un mio documento caricato")
async def elimina_documento(doc_id: str, identity: Dict[str, Any] = Depends(get_identity)):
    db = Database.get_db()
    doc = await db[COLL].find_one({"id": doc_id, "dipendente_id": identity["id"]},
                                  {"_id": 0, "categoria": 1})
    if not doc:
        raise HTTPException(404, "Documento non trovato")
    if doc.get("categoria") != "caricato_dipendente":
        raise HTTPException(403, "Puoi eliminare solo i documenti che hai caricato tu")
    await db[COLL].delete_one({"id": doc_id, "dipendente_id": identity["id"]})
    return {"ok": True}


@router.get("/modulo/{tipo}", summary="Scarico un modulo vuoto da compilare")
async def scarica_modulo(tipo: str, identity: Dict[str, Any] = Depends(get_identity)):
    info = TIPI.get(tipo)
    if not info or not info["modulo"]:
        raise HTTPException(404, "Modulo non disponibile")
    db = Database.get_db()
    dip = await db["dipendenti"].find_one({"id": identity["id"]},
                                          {"_id": 0, "nome": 1, "cognome": 1})
    nome = f"{(dip or {}).get('cognome','')} {(dip or {}).get('nome','')}".strip()
    pdf = _genera_modulo(tipo, info["label"], nome)
    return StreamingResponse(
        io.BytesIO(pdf), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="modulo_{tipo}.pdf"'},
    )


# ---- lato azienda (admin): carica CU / Unilav / qualsiasi documento per un dipendente ----
@router.post("/admin/upload", summary="(Azienda) carico un documento per un dipendente")
async def admin_upload(
    dipendente_id: str = Form(...),
    tipo: str = Form(...),
    file: UploadFile = File(...),
    identity: Dict[str, Any] = Depends(get_identity),
):
    if not _is_admin(identity):
        raise HTTPException(403, "Riservato all'azienda")
    if tipo not in TIPI:
        raise HTTPException(400, "Tipo documento non valido")
    contenuto = await file.read()
    if not contenuto:
        raise HTTPException(400, "File vuoto")
    if len(contenuto) > MAX_BYTES:
        raise HTTPException(413, "File troppo grande (max 12 MB)")
    doc = {
        "id": str(uuid.uuid4()),
        "dipendente_id": dipendente_id,
        "tipo": tipo,
        "label": TIPI[tipo]["label"],
        "categoria": "caricato_azienda",
        "nome_file": file.filename or f"{tipo}.pdf",
        "mime": file.content_type or "application/octet-stream",
        "dimensione": len(contenuto),
        "file_data": base64.b64encode(contenuto).decode(),
        "caricato_da": "azienda",
        "caricato_il": _now(),
    }
    await Database.get_db()[COLL].insert_one(doc)
    return {"ok": True, "id": doc["id"]}


def _genera_modulo(tipo: str, label: str, nome_dip: str) -> bytes:
    """Genera un modulo PDF vuoto da compilare a mano, intestato Ceraldi Group."""
    import fitz
    pdf = fitz.open()
    page = pdf.new_page()
    W = page.rect.width
    y = 60

    def line(txt, size=11, bold=False, gap=None, x=60):
        nonlocal y
        if txt:
            page.insert_text((x, y), txt, fontsize=size,
                             fontname="hebo" if bold else "helv")
        y += (gap if gap is not None else size + 8)

    def field(label_txt, righe=1):
        nonlocal y
        page.insert_text((60, y), label_txt, fontsize=10, fontname="hebo")
        y += 16
        for _ in range(righe):
            page.draw_line((60, y), (W - 60, y), color=(0.6, 0.6, 0.6))
            y += 22

    line("Ceraldi Group S.r.l.", 16, True)
    line(label, 13, True, gap=24)
    line(f"Dipendente: {nome_dip or '________________________'}", 11)
    line("Data: ____ / ____ / ________", 11, gap=22)

    corpi = {
        "contestazione": [
            ("Busta paga contestata (mese/anno):", 1),
            ("Motivo della contestazione:", 5),
            ("Importo/i contestato/i:", 2),
            ("Richiesta del dipendente:", 3),
        ],
        "richiesta_ferie": [
            ("Tipo (ferie / permesso / ROL):", 1),
            ("Dal giorno:", 1),
            ("Al giorno:", 1),
            ("Numero giorni/ore richiesti:", 1),
            ("Note:", 3),
        ],
        "richiesta_acconto_tfr": [
            ("Importo acconto TFR richiesto (€):", 1),
            ("Motivo della richiesta:", 4),
            ("Anzianità di servizio (anni):", 1),
            ("Modalità di erogazione (bonifico/altro):", 1),
        ],
    }
    for etichetta, righe in corpi.get(tipo, [("Descrizione:", 6)]):
        field(etichetta, righe)

    y += 10
    line("Firma del dipendente: ______________________________", 11, gap=30)
    line("Spazio riservato all'azienda", 10, True)
    line("Esito: [ ] Accolta   [ ] Respinta   [ ] In valutazione", 10)
    line("Firma azienda: ______________________________", 11)
    return pdf.tobytes()


# ---------------------------------------------------------------------------
# Regolamento interno aziendale: il dipendente lo scarica e lo accetta (data certa)
# ---------------------------------------------------------------------------
COLL_TEMPLATES = "contract_templates"
COLL_REG_ACC = "regolamento_accettazioni"


@router.get("/regolamento/stato")
async def regolamento_stato(identity: Dict[str, Any] = Depends(get_identity)):
    db = Database.get_db()
    acc = await db[COLL_REG_ACC].find_one({"dipendente_id": identity["id"]}, {"_id": 0})
    disp = await db[COLL_TEMPLATES].find_one({"tipo": "regolamento"}, {"_id": 0, "tipo": 1})
    return {
        "disponibile": bool(disp),
        "accettato": bool(acc),
        "accettato_il": acc.get("accettato_il") if acc else None,
    }


@router.get("/regolamento/file")
async def regolamento_file(identity: Dict[str, Any] = Depends(get_identity)):
    db = Database.get_db()
    doc = await db[COLL_TEMPLATES].find_one({"tipo": "regolamento"}, {"_id": 0, "file_data": 1, "filename": 1})
    if not doc or not doc.get("file_data"):
        raise HTTPException(404, "Regolamento non ancora pubblicato dall'azienda.")
    data = base64.b64decode(doc["file_data"])
    fname = doc.get("filename", "regolamento.docx")
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@router.post("/regolamento/accetta")
async def regolamento_accetta(request: Request, identity: Dict[str, Any] = Depends(get_identity)):
    db = Database.get_db()
    disp = await db[COLL_TEMPLATES].find_one({"tipo": "regolamento"}, {"_id": 0, "tipo": 1})
    if not disp:
        raise HTTPException(404, "Regolamento non ancora pubblicato dall'azienda.")
    quando = datetime.now(timezone.utc).isoformat()
    xff = request.headers.get("x-forwarded-for")
    ip = (xff.split(",")[0].strip() if xff else (request.client.host if request.client else "unknown"))
    await db[COLL_REG_ACC].update_one(
        {"dipendente_id": identity["id"]},
        {"$set": {
            "dipendente_id": identity["id"],
            "accettato_il": quando,
            "ip": ip,
            "user_agent": request.headers.get("user-agent", ""),
        }},
        upsert=True)
    return {"ok": True, "accettato_il": quando}
