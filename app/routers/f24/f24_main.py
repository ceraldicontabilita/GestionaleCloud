"""F24 router - F24 tax form management with alerts and reconciliation."""
from fastapi import APIRouter, Depends, Path, status, UploadFile, File, Body, HTTPException
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from uuid import uuid4
import logging
import zipfile
import io
import os

from app.database import Database
from app.utils.dependencies import get_current_user
from app.db_collections import COLL_F24
from app.services.f24_payment_evidence import patch_pagamento_banca

logger = logging.getLogger(__name__)
router = APIRouter()


# ============== UPLOAD MASSIVO F24 ==============
async def _importa_lotto(db, voci, source: str) -> Dict[str, Any]:
    """Ogni PDF passa da `importa_modello_bytes`: lettura, quadratura, dedup per
    contenuto e ricerca di quietanza e addebito. Prima questi due endpoint
    salvavano il PDF in `f24_unificato` senza leggerlo (`status: pending`,
    nessuna riga tributo): gusci vuoti che il registro contava come modelli."""
    from app.services.f24_canonico import importa_modello_bytes

    results = {"total": len(voci), "imported": 0, "duplicates": 0, "errors": 0, "details": []}
    for nome, contenuto in voci:
        if not nome.lower().endswith(".pdf"):
            results["errors"] += 1
            results["details"].append({"file": nome, "status": "error", "message": "Il file non è un PDF"})
            continue
        try:
            esito = await importa_modello_bytes(db, contenuto, os.path.basename(nome), source=source)
        except Exception as exc:  # noqa: BLE001 - un PDF rotto non ferma il lotto
            logger.error("Errore elaborazione %s (%s): %s", nome, type(exc).__name__, exc)
            results["errors"] += 1
            results["details"].append({"file": nome, "status": "error", "message": f"{type(exc).__name__}: {exc}"})
            continue
        if not esito.get("success"):
            results["errors"] += 1
            results["details"].append({"file": nome, "status": "error", "message": esito.get("error")})
        elif esito.get("duplicate"):
            results["duplicates"] += 1
            results["details"].append({"file": nome, "status": "duplicate", "id": esito.get("f24_id"),
                                       "message": "F24 già presente nel sistema"})
        else:
            results["imported"] += 1
            results["details"].append({"file": nome, "status": "imported", "id": esito.get("f24_id"),
                                       "righe_tributo": esito.get("righe_tributo")})
    return results


@router.post(
    "/upload-zip",
    summary="Upload ZIP con PDF F24 massivo"
)
async def upload_f24_zip(
    file: UploadFile = File(...)
) -> Dict[str, Any]:
    """Upload massivo di PDF F24 tramite file ZIP: ogni PDF entra dall'ingresso unico."""
    if not file.filename.lower().endswith('.zip'):
        raise HTTPException(status_code=400, detail="Il file deve essere un archivio ZIP")

    db = Database.get_db()
    try:
        zip_content = await file.read()
        zip_file = zipfile.ZipFile(io.BytesIO(zip_content))
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=400, detail="File ZIP non valido o corrotto") from exc

    pdf_files = [f for f in zip_file.namelist() if f.lower().endswith('.pdf') and not f.startswith('__MACOSX')]
    if not pdf_files:
        zip_file.close()
        raise HTTPException(status_code=400, detail="Nessun file PDF trovato nel ZIP")

    try:
        voci = [(nome, zip_file.read(nome)) for nome in pdf_files]
    finally:
        zip_file.close()
    return await _importa_lotto(db, voci, source="f24_upload_zip")


@router.post(
    "/upload-multiple",
    summary="Upload multiplo PDF F24"
)
async def upload_f24_multiple(
    files: List[UploadFile] = File(...)
) -> Dict[str, Any]:
    """Upload di più PDF F24 in una volta: ogni PDF entra dall'ingresso unico."""
    db = Database.get_db()
    voci = [(f.filename, await f.read()) for f in files]
    return await _importa_lotto(db, voci, source="f24_upload_multiple")


@router.get(
    "/documents",
    summary="Lista documenti F24 caricati"
)
async def get_f24_documents(
    skip: int = 0,
    limit: int = 100,
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """Lista dei documenti PDF F24 caricati."""
    db = Database.get_db()
    docs = await db["f24_unificato"].find(
        {},
        {"_id": 0}
    ).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    return docs


@router.delete(
    "/documents/{doc_id}",
    summary="Elimina documento F24"
)
async def delete_f24_document(
    doc_id: str = Path(...),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """Elimina un documento F24."""
    db = Database.get_db()

    doc = await db["f24_unificato"].find_one({"id": doc_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Documento non trovato")

    # Architettura Drive/Supabase: elimina solo dal database
    await db["f24_unificato"].delete_one({"id": doc_id})

    return {"success": True, "message": "Documento eliminato"}


# ============== CRUD F24 ==============
@router.get(
    "",
    summary="Get F24 forms"
)
async def get_f24_forms(
    skip: int = 0,
    limit: int = 10000,
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """Get list of F24 forms dalla collezione unificata."""
    db = Database.get_db()

    # Escludi eliminati
    forms_raw = await db[COLL_F24].find(
        {"status": {"$ne": "eliminato"}},
        {"_id": 0}
    ).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)

    # Trasforma nel formato legacy per compatibilità frontend
    forms = []
    for f in forms_raw:
        totali = f.get("totali", {})
        dati = f.get("dati_generali", {})
        forms.append({
            "id": f.get("id"),
            "tipo": "F24",
            "descrizione": dati.get("ragione_sociale", f.get("file_name", "")),
            "importo": totali.get("saldo_netto", 0),
            "scadenza": dati.get("data_scadenza", dati.get("data_versamento", "")),
            "status": f.get("status", "da_pagare"),
            "created_at": f.get("created_at"),
            "sezione_erario": f.get("sezione_erario", []),
            "sezione_inps": f.get("sezione_inps", [])
        })

    return forms


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Create F24 form"
)
async def create_f24(
    data: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """Create new F24 form."""
    db = Database.get_db()

    f24 = {
        "id": str(uuid4()),
        "tipo": data.get("tipo", "F24"),
        "descrizione": data.get("descrizione", ""),
        "importo": float(data.get("importo", 0) or 0),
        "scadenza": data.get("scadenza", ""),
        "periodo_riferimento": data.get("periodo_riferimento", ""),
        "codici_tributo": data.get("codici_tributo", []),
        "sezione": data.get("sezione", "erario"),
        "status": data.get("status", "pending"),
        "notes": data.get("notes", ""),
        "user_id": current_user.get("user_id"),
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    from app.services.f24_canonico import salva_f24

    # `f24.acquisito` lo pubblica `salva_f24` alla prima scrittura, con il
    # payload unico di `f24_evento_acquisito` (importo, scadenza, periodo e
    # codici letti dal modello): lo stesso fatto da ogni ingresso, una volta.
    f24["id"] = await salva_f24(db, f24, source="f24_manual_create")
    f24.pop("_id", None)

    return f24


@router.post(
    "/upload-pdf",
    status_code=status.HTTP_201_CREATED,
    summary="Upload PDF F24 e parsing automatico"
)
async def upload_f24_pdf(
    file: UploadFile = File(...)
) -> Dict[str, Any]:
    """Upload di un PDF F24: stesso ingresso di Documenti > Import, Drive e posta."""
    from app.services.f24_canonico import importa_modello_bytes

    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Solo file PDF supportati")

    db = Database.get_db()
    pdf_bytes = await file.read()
    esito = await importa_modello_bytes(db, pdf_bytes, file.filename, source="f24_upload_pdf")
    if not esito.get("success"):
        return {"success": False, "error": esito.get("error"), "filename": file.filename}
    if esito.get("duplicate"):
        return {
            "success": False,
            "error": "F24 già presente nel sistema",
            "existing_id": esito.get("f24_id"),
            "filename": file.filename,
        }

    modello = await db[COLL_F24].find_one({"id": esito["f24_id"]}, {"_id": 0, "dati_generali": 1, "totali": 1})
    dati = (modello or {}).get("dati_generali") or {}
    totali = (modello or {}).get("totali") or {}
    saldo = totali.get("saldo_netto", totali.get("saldo_finale", 0))
    logger.info("F24 importato: %s - €%.2f", esito["f24_id"], saldo or 0)
    return {
        "success": True,
        "id": esito["f24_id"],
        "scadenza": dati.get("data_versamento"),
        "contribuente": dati.get("ragione_sociale"),
        "saldo_finale": saldo,
        "righe_tributo": esito.get("righe_tributo"),
        "filename": file.filename
    }


@router.post(
    "/upload",
    status_code=status.HTTP_201_CREATED,
    summary="Upload F24 form (legacy)"
)
async def upload_f24(
    file: UploadFile = File(...)
) -> Dict[str, Any]:
    """Upload F24 form file - reindirizza a upload-pdf."""
    return await upload_f24_pdf(file)


# NB: la route GET /{f24_id} è definita in fondo al file, DOPO tutte le
# route statiche: definita qui shadowava GET /quietanze (registrata dopo
# nel file), che rispondeva sempre "F24 non trovato" — bug #14 audit.
async def get_f24(
    f24_id: str = Path(...),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get single F24 form."""
    db = Database.get_db()
    f24 = await db[COLL_F24].find_one({"id": f24_id}, {"_id": 0})
    if not f24:
        return {"error": "F24 non trovato"}
    return f24


@router.put(
    "/{f24_id}",
    summary="Update F24 form"
)
async def update_f24(
    f24_id: str = Path(...),
    data: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """Update F24 form."""
    db = Database.get_db()

    update_data = {k: v for k, v in data.items() if k not in ["id", "_id"]}
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

    await db[COLL_F24].update_one({"id": f24_id}, {"$set": update_data})

    return await get_f24(f24_id, current_user)


@router.delete(
    "/{f24_id}",
    summary="Delete F24 form"
)
async def delete_f24(
    f24_id: str = Path(...),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, str]:
    """Delete an F24 form."""
    db = Database.get_db()
    await db[COLL_F24].delete_one({"id": f24_id})
    return {"message": "F24 deleted", "id": f24_id}


# ============== ALERTS SCADENZE ==============
@router.get(
    "/alerts/scadenze",
    summary="Get F24 deadline alerts"
)
async def get_alerts_scadenze(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """
    Get F24 deadline alerts.
    Returns F24s that are overdue or expiring soon with severity levels.
    """
    db = Database.get_db()
    alerts = []
    today = datetime.now(timezone.utc).date()

    # Get unpaid F24s
    f24_list = await db[COLL_F24].find({"status": {"$ne": "paid"}}, {"_id": 0}).to_list(1000)

    for f24 in f24_list:
        try:
            scadenza_str = f24.get("scadenza") or f24.get("data_versamento")
            if not scadenza_str:
                continue

            # Parse date
            if isinstance(scadenza_str, str):
                scadenza_str = scadenza_str.replace("Z", "+00:00")
                if "T" in scadenza_str:
                    scadenza = datetime.fromisoformat(scadenza_str).date()
                else:
                    try:
                        scadenza = datetime.strptime(scadenza_str, "%d/%m/%Y").date()
                    except ValueError:
                        scadenza = datetime.strptime(scadenza_str, "%Y-%m-%d").date()
            elif isinstance(scadenza_str, datetime):
                scadenza = scadenza_str.date()
            else:
                continue

            giorni_mancanti = (scadenza - today).days

            # Determine severity
            severity = None
            messaggio = ""

            if giorni_mancanti < 0:
                severity = "critical"
                messaggio = f"⚠️ SCADUTO da {abs(giorni_mancanti)} giorni!"
            elif giorni_mancanti == 0:
                severity = "high"
                messaggio = "⏰ SCADE OGGI!"
            elif giorni_mancanti <= 3:
                severity = "high"
                messaggio = f"⚡ Scade tra {giorni_mancanti} giorni"
            elif giorni_mancanti <= 7:
                severity = "medium"
                messaggio = f"📅 Scade tra {giorni_mancanti} giorni"

            if severity:
                alerts.append({
                    "f24_id": f24.get("id"),
                    "tipo": f24.get("tipo", "F24"),
                    "descrizione": f24.get("descrizione", ""),
                    "importo": float(f24.get("importo", 0) or 0),
                    "scadenza": scadenza.isoformat(),
                    "giorni_mancanti": giorni_mancanti,
                    "severity": severity,
                    "messaggio": messaggio,
                    "codici_tributo": f24.get("codici_tributo", [])
                })

        except Exception as e:
            logger.error(f"Error parsing F24 date: {e}")
            continue

    alerts.sort(key=lambda x: x["giorni_mancanti"])
    return alerts


# ============== RICONCILIAZIONE ==============
@router.post(
    "/riconcilia",
    summary="Reconcile F24 with bank movement"
)
async def riconcilia_f24(
    f24_id: str = Body(...),
    movimento_bancario_id: str = Body(...),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """Manual reconciliation of F24 with bank movement."""
    db = Database.get_db()

    f24 = await db[COLL_F24].find_one({"id": f24_id}, {"_id": 0})
    if not f24:
        return {"success": False, "error": "F24 non trovato"}

    movimento = await db["estratto_conto_movimenti"].find_one({"id": movimento_bancario_id}, {"_id": 0})
    if not movimento:
        return {"success": False, "error": "Movimento bancario non trovato"}

    importo_f24 = float(
        f24.get("importo")
        or f24.get("importo_totale")
        or (f24.get("totali") or {}).get("saldo_netto")
        or 0
    )
    importo_mov = abs(float(
        movimento.get("amount")
        or movimento.get("importo")
        or movimento.get("uscite")
        or 0
    ))

    if abs(importo_f24 - importo_mov) > 1:
        return {
            "success": False,
            "error": f"Importi non corrispondenti: F24 €{importo_f24:.2f} vs Movimento €{importo_mov:.2f}",
            "warning": True
        }

    now = datetime.now(timezone.utc).isoformat()

    data_banca = (
        movimento.get("data_contabile")
        or movimento.get("data")
        or movimento.get("booking_date")
        or now
    )
    await db[COLL_F24].update_one(
        {"id": f24_id},
        {"$set": {
            **patch_pagamento_banca(
                movimento_id=movimento_bancario_id,
                data_pagamento=data_banca,
            ),
            "paid_date": data_banca,
            "bank_movement_id": movimento_bancario_id,
            "reconciled_at": now
        }}
    )

    await db["estratto_conto_movimenti"].update_one(
        {"id": movimento_bancario_id},
        {"$set": {
            "reconciled": True,
            "reconciled_with": f24_id,
            "reconciled_type": "f24",
            "reconciled_at": now
        }}
    )

    return {
        "success": True,
        "message": "F24 riconciliato con movimento bancario",
        "f24_id": f24_id,
        "movimento_id": movimento_bancario_id
    }


@router.post(
    "/{f24_id}/mark-paid",
    summary="Mark F24 as paid"
)
async def mark_f24_paid(
    f24_id: str = Path(...),
    paid_date: Optional[str] = None,
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """Registra una dichiarazione manuale, non una prova bancaria."""
    db = Database.get_db()

    now = datetime.now(timezone.utc).isoformat()

    result = await db[COLL_F24].update_one(
        {"id": f24_id},
        {"$set": {
            "status": "da_pagare",
            "stato_pagamento": "DA_VERIFICARE_BANCA",
            "pagato": False,
            "pagato_manualmente": True,
            "pagamento_dichiarato_manualmente": True,
            "data_pagamento_dichiarata": paid_date or now,
            "updated_at": now
        }}
    )

    if result.matched_count == 0:
        return {"success": False, "error": "F24 non trovato"}

    return {
        "success": True,
        "message": "Pagamento dichiarato; resta da verificare sul movimento bancario",
        "stato_pagamento": "DA_VERIFICARE_BANCA",
    }


# ============== CODICI TRIBUTO ==============
# ============== PARSING QUIETANZE F24 ==============
from app.services.f24_parser import generate_f24_summary


@router.post(
    "/quietanze/upload",
    summary="Upload e parsing quietanza F24"
)
async def upload_quietanza_f24(
    file: UploadFile = File(...)
) -> Dict[str, Any]:
    """
    Upload e parsing di una quietanza F24 PDF.
    Estrae automaticamente tutti i dati e li salva nel database.
    Architettura Drive/Supabase: salva PDF come Base64.
    """
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Il file deve essere un PDF")

    content = await file.read()
    db = Database.get_db()
    from app.services.f24_canonico import importa_quietanza

    esito = await importa_quietanza(
        db, content, file.filename, source="f24_quietanze_upload"
    )
    if not esito.get("success"):
        raise HTTPException(status_code=400, detail=esito.get("error", "Parsing fallito"))
    return {
        **esito,
        "message": (
            "Quietanza già presente nel sistema"
            if esito.get("duplicate")
            else "Quietanza F24 elaborata e riconciliata"
        ),
    }


@router.get(
    "/quietanze",
    summary="Lista quietanze F24"
)
async def list_quietanze_f24(
    skip: int = 0,
    limit: int = 50,
    anno: Optional[int] = None,
    mese: Optional[int] = None,
    search: Optional[str] = None
) -> Dict[str, Any]:
    """Lista quietanze F24 con filtri."""
    db = Database.get_db()

    query = {}

    # Filtro per anno
    if anno:
        query["dati_generali.data_pagamento"] = {"$regex": f"^{anno}"}

    # Filtro per anno e mese
    if anno and mese:
        mese_str = f"{mese:02d}"
        query["dati_generali.data_pagamento"] = {"$regex": f"^{anno}-{mese_str}"}

    # Ricerca testuale
    if search:
        query["$or"] = [
            {"dati_generali.codice_fiscale": {"$regex": search, "$options": "i"}},
            {"dati_generali.ragione_sociale": {"$regex": search, "$options": "i"}},
            {"dati_generali.protocollo_telematico": {"$regex": search, "$options": "i"}}
        ]

    # Query con esclusione _id
    from app.db_collections import COLL_QUIETANZE_F24
    from app.document_repository import metadata_projection

    quietanze = await db[COLL_QUIETANZE_F24].find(
        query, metadata_projection(COLL_QUIETANZE_F24)
    ).sort("dati_generali.data_pagamento", -1).skip(skip).limit(limit).to_list(limit)

    totale = await db[COLL_QUIETANZE_F24].count_documents(query)

    # Statistiche
    stats_pipeline = [
        {"$group": {
            "_id": None,
            "totale_pagato": {"$sum": "$totali.saldo_delega"},
            "totale_debiti": {"$sum": "$totali.totale_debito"},
            "totale_crediti": {"$sum": "$totali.totale_credito"},
            "count": {"$sum": 1}
        }}
    ]
    stats_result = await db[COLL_QUIETANZE_F24].aggregate(stats_pipeline).to_list(1)
    stats = stats_result[0] if stats_result else {}

    return {
        "quietanze": quietanze,
        "totale": totale,
        "statistiche": {
            "quietanze_count": stats.get("count", 0),
            "totale_pagato": round(stats.get("totale_pagato", 0), 2),
            "totale_debiti": round(stats.get("totale_debiti", 0), 2),
            "totale_crediti": round(stats.get("totale_crediti", 0), 2)
        }
    }


@router.get(
    "/quietanze/{f24_id}",
    summary="Dettaglio quietanza F24"
)
async def get_quietanza_f24(f24_id: str) -> Dict[str, Any]:
    """Dettaglio completo di una quietanza F24."""
    db = Database.get_db()

    quietanza = await db["quietanze_f24"].find_one({"id": f24_id}, {"_id": 0})
    if not quietanza:
        raise HTTPException(status_code=404, detail="Quietanza non trovata")

    # Genera riepilogo
    quietanza["summary"] = generate_f24_summary(quietanza)

    return quietanza


@router.delete(
    "/quietanze/{f24_id}",
    summary="Elimina quietanza F24"
)
async def delete_quietanza_f24(f24_id: str) -> Dict[str, Any]:
    """Elimina una quietanza F24."""
    db = Database.get_db()

    quietanza = await db["quietanze_f24"].find_one({"id": f24_id})
    if not quietanza:
        raise HTTPException(status_code=404, detail="Quietanza non trovata")

    # Elimina file fisico
    # Architettura Drive/Supabase: elimina solo da database
    await db["quietanze_f24"].delete_one({"id": f24_id})

    return {
        "success": True,
        "message": "Quietanza eliminata con successo"
    }


@router.get(
    "/quietanze/statistiche/tributi",
    summary="Statistiche tributi F24"
)
async def statistiche_tributi_quietanze() -> Dict[str, Any]:
    """Statistiche aggregate per tipo di tributo dalle quietanze."""
    db = Database.get_db()

    # Tributi Erario
    erario_pipeline = [
        {"$unwind": "$sezione_erario"},
        {"$group": {
            "_id": "$sezione_erario.codice_tributo",
            "totale_debito": {"$sum": "$sezione_erario.importo_debito"},
            "totale_credito": {"$sum": "$sezione_erario.importo_credito"},
            "count": {"$sum": 1}
        }},
        {"$sort": {"totale_debito": -1}}
    ]
    erario_stats = await db["quietanze_f24"].aggregate(erario_pipeline).to_list(50)

    # Contributi INPS
    inps_pipeline = [
        {"$unwind": "$sezione_inps"},
        {"$group": {
            "_id": "$sezione_inps.causale",
            "totale_debito": {"$sum": "$sezione_inps.importo_debito"},
            "count": {"$sum": 1}
        }},
        {"$sort": {"totale_debito": -1}}
    ]
    inps_stats = await db["quietanze_f24"].aggregate(inps_pipeline).to_list(20)

    return {
        "erario": [{"codice": s["_id"], "debito": round(s["totale_debito"], 2), "credito": round(s.get("totale_credito", 0), 2), "count": s["count"]} for s in erario_stats],
        "inps": [{"causale": s["_id"], "totale": round(s["totale_debito"], 2), "count": s["count"]} for s in inps_stats]
    }


# ============== FASCICOLO F24 (§21) ==============

def _parse_periodo_mm_aaaa(periodo: str) -> tuple:
    """'MM/AAAA' o 'MM-AAAA' → (mese, anno). Solleva 400 se non valido."""
    import re as _re
    m = _re.match(r"^\s*(\d{1,2})[/-](\d{4})\s*$", periodo or "")
    if not m:
        raise HTTPException(status_code=400,
                            detail="periodo non valido: usa 'MM/AAAA' (es. 06/2026)")
    mese, anno = int(m.group(1)), int(m.group(2))
    if not (1 <= mese <= 12):
        raise HTTPException(status_code=400, detail="mese non valido (1-12)")
    return (mese, anno)


@router.post("/fascicolo/costruisci", summary="Costruisce e salva il fascicolo F24 di un soggetto/periodo (§21)")
async def costruisci_fascicolo_f24(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Materializza il fascicolo mensile: collega F24 (DM10/RC01), quietanze e
    cedolini del periodo e ne classifica i totali. Non crea documenti mancanti."""
    from app.services import fascicolo_f24 as fasc
    cf = (payload.get("codice_fiscale") or "").strip()
    if not cf:
        raise HTTPException(status_code=400, detail="codice_fiscale obbligatorio")
    periodo = _parse_periodo_mm_aaaa(payload.get("periodo", ""))
    db = Database.get_db()
    fascicolo = await fasc.costruisci_e_salva(db, cf, periodo)
    return {"success": True, "fascicolo": fascicolo}


@router.get("/fascicolo/{codice_fiscale}/{mese}/{anno}", summary="Legge il fascicolo F24 materializzato")
async def leggi_fascicolo_f24(codice_fiscale: str, mese: int, anno: int,
                              costruisci_se_assente: bool = True) -> Dict[str, Any]:
    """Ritorna il fascicolo salvato; se assente e richiesto, lo costruisce al volo."""
    from app.services import fascicolo_f24 as fasc
    if not (1 <= mese <= 12):
        raise HTTPException(status_code=400, detail="mese non valido (1-12)")
    db = Database.get_db()
    periodo = (mese, anno)
    fascicolo = await fasc.leggi_fascicolo(db, codice_fiscale, periodo)
    if fascicolo is None and costruisci_se_assente:
        fascicolo = await fasc.costruisci_e_salva(db, codice_fiscale, periodo)
    if fascicolo is None:
        raise HTTPException(status_code=404, detail="Fascicolo non trovato")
    return {"success": True, "fascicolo": fascicolo}


# Interroga avviso bonario + aggancio addebiti/quietanze (PR 11/12): route
# statiche, quindi PRIMA della dinamica qui sotto.
from app.routers.f24.avviso_bonario import router as avviso_bonario_router  # noqa: E402

router.include_router(avviso_bonario_router)

from app.routers.f24.piano_tributi import router as piano_tributi_router  # noqa: E402

router.include_router(piano_tributi_router)

from app.routers.f24.tributi import router as tributi_router  # noqa: E402

router.include_router(tributi_router)

# Registrata per ULTIMA di proposito: una route dinamica a un segmento
# cattura qualunque path statico definito dopo di lei (era il caso di
# GET /quietanze, che non veniva mai raggiunta).
router.add_api_route("/{f24_id}", get_f24, methods=["GET"], summary="Get single F24")
