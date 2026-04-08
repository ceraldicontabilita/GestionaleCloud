"""
Fatture Passive — Upload XML manuale + Sync automatica PEC SDI.
Collection: fatture_passive
Prefix: /api/fatture
"""
from fastapi import APIRouter, HTTPException, UploadFile, File, Depends, BackgroundTasks
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId
from datetime import datetime
from typing import Optional
import logging

from app.database import get_database
from app.parsers.fattura_xml import parse_fattura_xml
from app.config import settings
import os

XML_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "uploads", "fatture_xml")
os.makedirs(XML_DIR, exist_ok=True)

router = APIRouter()
logger = logging.getLogger(__name__)


def _oid(doc):
    if doc and "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc


async def _import_xml_bytes(
    xml_bytes: bytes,
    filename: str,
    db: AsyncIOMotorDatabase,
    source: str = "upload",
    message_id: str = "",
) -> dict:
    """
    Logica condivisa tra upload manuale e sync PEC.
    Ritorna: {inserite, duplicate, totale_file, fatture[]}
    """
    try:
        # Prova UTF-8, poi latin-1 per P7M/vecchi file
        for enc in ("utf-8", "latin-1", "cp1252"):
            try:
                xml_str = xml_bytes.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            return {"errore": "Encoding XML non riconosciuto", "inserite": 0, "duplicate": 0}

        fatture = parse_fattura_xml(xml_str)
    except Exception as e:
        return {"errore": f"Errore parsing XML: {e}", "inserite": 0, "duplicate": 0}

    if not fatture:
        return {"errore": "Nessuna fattura nel file", "inserite": 0, "duplicate": 0}

    inserite, duplicate = 0, 0
    for f in fatture:
        if await db["fatture_passive"].find_one({"dedup_key": f["dedup_key"]}):
            duplicate += 1
            continue

        doc = {
            "fornitore_denominazione": f["cedente"].get("denominazione", ""),
            "fornitore_piva": f["cedente"].get("partita_iva", ""),
            "numero": f["numero"],
            "data": f["data"],
            "anno": int(f["data"][:4]) if f["data"] and len(f["data"]) >= 4 else 0,
            "tipo_documento": f["tipo_documento"],
            "importo_totale": f["importo_totale"],
            "imponibile": f["imponibile"],
            "iva": f["iva"],
            "causale": f["causale"],
            "linee": f["linee"],
            "riepilogo_iva": f["riepilogo_iva"],
            "pagamenti": f["pagamenti"],
            "dedup_key": f["dedup_key"],
            "stato": "da_confermare",
            "source": source,  # "upload" | "pec_auto"
            "xml_filename": filename,
            "pec_message_id": message_id,
            "created_at": datetime.utcnow(),
        }
        result_ins = await db["fatture_passive"].insert_one(doc)
        # Salva XML raw su disco per visualizzazione XSL
        try:
            xml_fname = f"{str(result_ins.inserted_id)}.xml"
            with open(os.path.join(XML_DIR, xml_fname), "w", encoding="utf-8") as xf:
                xf.write(xml_str)
            await db["fatture_passive"].update_one(
                {"_id": result_ins.inserted_id},
                {"$set": {"xml_raw_path": xml_fname}}
            )
        except Exception as xe:
            logger.warning(f"Salvataggio XML raw fallito: {xe}")
        inserite += 1

        if f["cedente"].get("partita_iva"):
            await db["fornitori"].update_one(
                {"partita_iva": f["cedente"]["partita_iva"]},
                {"$set": {
                    "denominazione": f["cedente"]["denominazione"],
                    "partita_iva": f["cedente"]["partita_iva"],
                    "updated_at": datetime.utcnow(),
                },
                 "$setOnInsert": {"created_at": datetime.utcnow()}},
                upsert=True,
            )

    return {
        "inserite": inserite,
        "duplicate": duplicate,
        "totale_file": len(fatture),
    }


# ── LISTA / STATS ──────────────────────────────────────────────────────────

@router.get("")
async def lista_fatture(
    anno: Optional[int] = None,
    fornitore: Optional[str] = None,
    source: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    filtro = {}
    if anno:
        filtro["anno"] = anno
    if fornitore:
        filtro["$or"] = [
            {"fornitore_denominazione": {"$regex": fornitore, "$options": "i"}},
            {"fornitore_piva": fornitore},
        ]
    if source:
        filtro["source"] = source
    cursor = db["fatture_passive"].find(filtro).sort("data", -1).skip(skip).limit(limit)
    result = [_oid(doc) async for doc in cursor]
    totale = await db["fatture_passive"].count_documents(filtro)
    return {"items": result, "totale": totale}


@router.get("/stats")
async def stats_fatture(anno: int = 2026, db: AsyncIOMotorDatabase = Depends(get_database)):
    pipeline = [
        {"$match": {"anno": anno}},
        {"$group": {
            "_id": None,
            "imponibile": {"$sum": "$imponibile"},
            "iva": {"$sum": "$iva"},
            "totale": {"$sum": "$importo_totale"},
            "count": {"$sum": 1},
            "da_pec": {"$sum": {"$cond": [{"$eq": ["$source", "pec_auto"]}, 1, 0]}},
        }}
    ]
    agg = await db["fatture_passive"].aggregate(pipeline).to_list(1)
    return agg[0] if agg else {"imponibile": 0, "iva": 0, "totale": 0, "count": 0, "da_pec": 0}


# ── UPLOAD MANUALE ─────────────────────────────────────────────────────────

@router.post("/upload-xml")
async def upload_fattura_xml(
    file: UploadFile = File(...),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    content = await file.read()
    result = await _import_xml_bytes(
        xml_bytes=content,
        filename=file.filename,
        db=db,
        source="upload",
    )
    if result.get("errore"):
        raise HTTPException(400, result["errore"])
    return {"ok": True, **result}


# ── SYNC AUTOMATICA PEC SDI ────────────────────────────────────────────────

@router.post("/sync-pec")
async def sync_fatture_pec(
    db: AsyncIOMotorDatabase = Depends(get_database),
    dry_run: bool = False,
):
    """
    Scarica fatture XML non lette dalla PEC Aruba (mittente SDI).
    dry_run=true → mostra cosa verrebbe importato senza salvare.
    """
    # Credenziali PEC da variabili d'ambiente
    host = "imaps.pec.aruba.it"
    port = 993
    user = "fatturazioneceraldi@pec.it"
    password = "L)9*kd5+78]?%LmF"

    if not password:
        raise HTTPException(500, "Credenziali PEC non configurate nel .env")

    from app.services.pec_fatture_service import fetch_fatture_from_pec

    try:
        email_items = await fetch_fatture_from_pec(
            host=host,
            port=port,
            user=user,
            password=password,
            mark_seen=not dry_run,
        )
    except Exception as e:
        logger.error(f"Errore connessione PEC: {e}")
        raise HTTPException(503, f"Errore connessione PEC: {e}")

    if not email_items:
        return {
            "ok": True,
            "email_processate": 0,
            "inserite": 0,
            "duplicate": 0,
            "messaggi": [],
        }

    totale_inserite = 0
    totale_duplicate = 0
    log_messaggi = []

    for item in email_items:
        if dry_run:
            log_messaggi.append({
                "filename": item["filename"],
                "from": item["from"],
                "subject": item["subject"][:80],
                "date": item["date"],
                "stato": "dry_run",
            })
            continue

        result = await _import_xml_bytes(
            xml_bytes=item["xml_bytes"],
            filename=item["filename"],
            db=db,
            source="pec_auto",
            message_id=item.get("message_id", ""),
        )

        totale_inserite += result.get("inserite", 0)
        totale_duplicate += result.get("duplicate", 0)

        log_messaggi.append({
            "filename": item["filename"],
            "from": item["from"],
            "subject": item["subject"][:80],
            "date": item["date"],
            "inserite": result.get("inserite", 0),
            "duplicate": result.get("duplicate", 0),
            "errore": result.get("errore"),
        })

    # Salva log sync in DB
    if not dry_run:
        await db["sync_log"].insert_one({
            "tipo": "pec_fatture",
            "timestamp": datetime.utcnow(),
            "email_processate": len(email_items),
            "inserite": totale_inserite,
            "duplicate": totale_duplicate,
            "dettagli": log_messaggi,
        })

    return {
        "ok": True,
        "email_processate": len(email_items),
        "inserite": totale_inserite,
        "duplicate": totale_duplicate,
        "messaggi": log_messaggi,
    }


@router.get("/sync-log")
async def get_sync_log(
    limit: int = 20,
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Storico delle sincronizzazioni PEC."""
    cursor = db["sync_log"].find({"tipo": "pec_fatture"}).sort("timestamp", -1).limit(limit)
    items = [_oid(doc) async for doc in cursor]
    return {"items": items}


# ── DETTAGLIO FATTURA ──────────────────────────────────────────────────────

@router.get("/{fatt_id}/xml-raw")
async def get_fattura_xml_raw(fatt_id: str, db: AsyncIOMotorDatabase = Depends(get_database)):
    """Restituisce l'XML raw per visualizzazione con foglio stile XSL."""
    from fastapi.responses import Response
    doc = await db["fatture_passive"].find_one({"_id": ObjectId(fatt_id)})
    if not doc:
        raise HTTPException(404, "Fattura non trovata")
    xml_path = doc.get("xml_raw_path")
    if xml_path:
        full = os.path.join(XML_DIR, xml_path)
        if os.path.exists(full):
            with open(full, "r", encoding="utf-8") as f:
                xml_content = f.read()
            return Response(content=xml_content, media_type="application/xml",
                          headers={"Access-Control-Allow-Origin": "*"})
    raise HTTPException(404, "XML originale non disponibile")




@router.get("/{fatt_id}/html")
async def visualizza_fattura_html(fatt_id: str, db: AsyncIOMotorDatabase = Depends(get_database)):
    """
    Applica il foglio stile AssoSoftware all'XML della fattura e restituisce HTML.
    Richiede che la fattura abbia xml_filename e che l'XML sia recuperabile.
    """
    from fastapi.responses import HTMLResponse
    from bson import ObjectId
    import os, subprocess, tempfile

    doc = await db["fatture_passive"].find_one({"_id": ObjectId(fatt_id)})
    if not doc:
        raise HTTPException(404, "Fattura non trovata")

    # Cerca l'XML: prima in uploads salvati, poi in DB come campo xml_raw
    xml_content = doc.get("xml_raw", "")

    if not xml_content:
        # Prova a trovare il file XML locale
        upload_dir = os.path.join(os.path.dirname(__file__), "..", "..", "uploads", "fatture")
        xml_filename = doc.get("xml_filename", "")
        if xml_filename and os.path.isdir(upload_dir):
            xml_path = os.path.join(upload_dir, xml_filename)
            if os.path.exists(xml_path):
                with open(xml_path, "rb") as f:
                    xml_content = f.read().decode("utf-8", errors="replace")

    if not xml_content:
        # Fallback: ricostruisce HTML dai dati in DB
        return HTMLResponse(_fattura_html_fallback(doc))

    # Applica XSL con xsltproc
    xsl_path = os.path.join(os.path.dirname(__file__), "..", "static", "FoglioStileAssoSoftware.xsl")
    if not os.path.exists(xsl_path):
        return HTMLResponse(_fattura_html_fallback(doc))

    try:
        with tempfile.NamedTemporaryFile(suffix=".xml", mode="w", encoding="utf-8", delete=False) as tmp:
            tmp.write(xml_content)
            tmp_path = tmp.name

        result = subprocess.run(
            ["xsltproc", xsl_path, tmp_path],
            capture_output=True, text=True, timeout=10
        )
        os.unlink(tmp_path)

        if result.returncode == 0 and result.stdout.strip():
            return HTMLResponse(result.stdout)
        else:
            return HTMLResponse(_fattura_html_fallback(doc))
    except Exception:
        return HTMLResponse(_fattura_html_fallback(doc))


def _fattura_html_fallback(doc: dict) -> str:
    """HTML minimal dai dati MongoDB quando l'XML non è disponibile."""
    def fmt(v):
        if v is None: return "—"
        try: return f"€ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        except: return str(v)

    linee = ""
    for i, l in enumerate(doc.get("linee", []), 1):
        linee += f"""
        <tr>
          <td style="border:1px solid #ddd;padding:8px;text-align:center">{l.get("numero", i)}</td>
          <td style="border:1px solid #ddd;padding:8px">{l.get("descrizione","")}</td>
          <td style="border:1px solid #ddd;padding:8px;text-align:right">{l.get("quantita","")}</td>
          <td style="border:1px solid #ddd;padding:8px;text-align:right">{fmt(l.get("prezzo_unitario"))}</td>
          <td style="border:1px solid #ddd;padding:8px;text-align:right">{l.get("aliquota_iva","")}%</td>
          <td style="border:1px solid #ddd;padding:8px;text-align:right">{fmt(l.get("prezzo_totale"))}</td>
        </tr>"""

    iva_rows = ""
    for r in doc.get("riepilogo_iva", []):
        iva_rows += f"""
        <tr>
          <td style="border:1px solid #ddd;padding:6px;text-align:center">{r.get("aliquota","")}%</td>
          <td style="border:1px solid #ddd;padding:6px;text-align:right">{fmt(r.get("imponibile"))}</td>
          <td style="border:1px solid #ddd;padding:6px;text-align:right">{fmt(r.get("imposta"))}</td>
          <td style="border:1px solid #ddd;padding:6px">{r.get("natura","")}</td>
        </tr>"""

    cedente = doc.get("cedente", {})
    return f"""<!DOCTYPE html><html lang="it"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  body {{ font-family: 'Segoe UI', sans-serif; font-size: 13px; color: #1a1a2e; margin: 0; padding: 20px; background: #f0f4fa; }}
  #fattura-elettronica {{ max-width: 960px; margin: 0 auto; background: #fff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,.08); }}
  .header {{ background: linear-gradient(135deg, #5D29C7 0%, #7C4DDD 100%); color: #fff; padding: 24px 32px; display: flex; justify-content: space-between; align-items: flex-start; }}
  .header h1 {{ margin: 0 0 4px; font-size: 20px; font-weight: 700; }}
  .header .sub {{ font-size: 13px; opacity: .8; }}
  .body {{ padding: 28px 32px; }}
  .row2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-bottom: 24px; }}
  .box {{ background: #f8f9fc; border-radius: 10px; padding: 16px; border: 1px solid #e8ecf0; }}
  .box-label {{ font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .7px; color: #9ca3af; margin-bottom: 8px; }}
  .box p {{ margin: 2px 0; font-size: 13px; }}
  .box .name {{ font-size: 15px; font-weight: 700; color: #1a1a2e; margin-bottom: 4px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  thead th {{ background: #f8f9fc; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .5px; color: #6b7280; padding: 10px 12px; border-bottom: 2px solid #e8ecf0; text-align: left; }}
  .section-title {{ font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: .7px; color: #5D29C7; margin: 24px 0 12px; border-bottom: 2px solid #EDE7FF; padding-bottom: 6px; }}
  .totale-row {{ background: #EDE7FF; font-weight: 700; }}
  .totale-row td {{ padding: 12px; color: #3D1A8F; font-size: 15px; }}
  .badge {{ display:inline-block; padding: 3px 10px; border-radius: 20px; font-size: 11px; font-weight: 700; }}
  .badge-fattura {{ background: #EDE7FF; color: #3D1A8F; }}
  .badge-nc {{ background: #FEE2E2; color: #B71C1C; }}
</style>
</head><body>
<div id="fattura-elettronica">
  <div class="header">
    <div>
      <div class="sub">Documento Fiscale Elettronico</div>
      <h1>N. {doc.get("numero","—")} del {doc.get("data","—")}</h1>
      <span class="badge badge-fattura">{doc.get("tipo_documento","TD01")}</span>
    </div>
    <div style="text-align:right">
      <div class="sub">Totale documento</div>
      <div style="font-size:28px;font-weight:800;margin-top:4px">{fmt(doc.get("importo_totale"))}</div>
    </div>
  </div>
  <div class="body">
    <div class="row2">
      <div class="box">
        <div class="box-label">Cedente / Fornitore</div>
        <p class="name">{cedente.get("denominazione","—")}</p>
        <p>P.IVA: {cedente.get("partita_iva","—")}</p>
        <p>{cedente.get("indirizzo","")} {cedente.get("comune","")}</p>
        <p>Regime: {cedente.get("regime_fiscale","")}</p>
      </div>
      <div class="box">
        <div class="box-label">Cessionario / Acquirente</div>
        <p class="name">CERALDI GROUP S.R.L.</p>
        <p>P.IVA: 04523831214</p>
        <p>Piazza Nazionale 46, 80143 Napoli</p>
      </div>
    </div>

    {"<div class=\"section-title\">Righe documento</div>" if doc.get("linee") else ""}
    {f'<table><thead><tr><th style="width:40px">N.</th><th>Descrizione</th><th style="width:70px;text-align:right">Qtà</th><th style="width:90px;text-align:right">Prezzo unit.</th><th style="width:60px;text-align:right">IVA</th><th style="width:100px;text-align:right">Totale</th></tr></thead><tbody>{linee}</tbody></table>' if doc.get("linee") else ""}

    {"<div class=\"section-title\">Riepilogo IVA</div>" if doc.get("riepilogo_iva") else ""}
    {f'<table><thead><tr><th>Aliquota</th><th style="text-align:right">Imponibile</th><th style="text-align:right">Imposta</th><th>Natura</th></tr></thead><tbody>{iva_rows}</tbody></table>' if doc.get("riepilogo_iva") else ""}

    <div class="section-title">Totali</div>
    <table><tbody>
      <tr><td style="padding:8px 12px;color:#6b7280">Imponibile</td><td style="padding:8px 12px;text-align:right;font-weight:600">{fmt(doc.get("imponibile"))}</td></tr>
      <tr><td style="padding:8px 12px;color:#6b7280">IVA</td><td style="padding:8px 12px;text-align:right;font-weight:600">{fmt(doc.get("iva"))}</td></tr>
      <tr class="totale-row"><td style="border-radius:0 0 0 10px">Totale documento</td><td style="text-align:right;border-radius:0 0 10px 0">{fmt(doc.get("importo_totale"))}</td></tr>
    </tbody></table>
  </div>
</div>
</body></html>"""


@router.get("/{fatt_id}")
async def get_fattura(fatt_id: str, db: AsyncIOMotorDatabase = Depends(get_database)):
    doc = await db["fatture_passive"].find_one({"_id": ObjectId(fatt_id)})
    if not doc:
        raise HTTPException(404, "Fattura non trovata")
    return _oid(doc)
