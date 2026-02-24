"""
Corrispettivi Router - Gestione corrispettivi telematici.
Refactored from public_api.py
"""
from fastapi import APIRouter, HTTPException, UploadFile, File, Query
from typing import Dict, Any, List
from datetime import datetime, timezone
import uuid
import logging
import zipfile
import io

from app.database import Database
from app.parsers.corrispettivi_parser import parse_corrispettivo_xml
from app.utils.error_handler import handle_errors

logger = logging.getLogger(__name__)
router = APIRouter()



@router.get("/stats")
async def get_corrispettivi_stats(anno: int = Query(None)) -> Dict[str, Any]:
    """Statistiche corrispettivi per anno."""
    from datetime import date as _date
    db = Database.get_db()
    if not anno:
        anno = _date.today().year
    query = {"anno": anno}
    totale = await db["corrispettivi"].count_documents(query)
    pipeline = [
        {"$match": query},
        {"$group": {"_id": None,
            "totale_lordo": {"$sum": "$totale_lordo"},
            "totale_iva": {"$sum": "$totale_iva"},
            "totale_netto": {"$sum": "$totale_netto"},
            "totale_non_riscosso": {"$sum": "$non_riscosso"}
        }}
    ]
    result = await db["corrispettivi"].aggregate(pipeline).to_list(1)
    stats = result[0] if result else {}
    stats.pop("_id", None)
    return {
        "anno": anno, "count": totale,
        "totale_lordo": round(stats.get("totale_lordo", 0), 2),
        "totale_iva": round(stats.get("totale_iva", 0), 2),
        "totale_netto": round(stats.get("totale_netto", 0), 2),
        "totale_non_riscosso": round(stats.get("totale_non_riscosso", 0), 2),
    }

@router.get("")
@handle_errors
async def list_corrispettivi(
    skip: int = 0, 
    limit: int = 500,
    data_da: str = None,
    data_a: str = None,
    anno: int = None
) -> List[Dict[str, Any]]:
    """List corrispettivi con filtro opzionale per data o anno."""
    db = Database.get_db()
    
    query = {}
    
    # Se nessun filtro, usa anno corrente per performance
    if not anno and not data_da and not data_a:
        anno = datetime.now().year
    
    # Filtro per anno (prioritario)
    if anno:
        query["data"] = {"$regex": f"^{anno}"}
    elif data_da or data_a:
        query["data"] = {}
        if data_da:
            query["data"]["$gte"] = data_da
        if data_a:
            query["data"]["$lte"] = data_a
    
    return await db["corrispettivi"].find(query, {"_id": 0}).sort("data", -1).skip(skip).limit(limit).to_list(limit)


@router.post("/ricalcola-iva")
@handle_errors
async def ricalcola_iva_corrispettivi() -> Dict[str, Any]:
    """Ricalcola IVA con scorporo 10%."""
    db = Database.get_db()
    
    corrispettivi = await db["corrispettivi"].find(
        {"$or": [{"totale_iva": 0}, {"totale_iva": None}], "totale": {"$gt": 0}},
        {"_id": 0}
    ).to_list(10000)
    
    updated = 0
    for corr in corrispettivi:
        totale = float(corr.get("totale", 0) or 0)
        if totale <= 0:
            continue
        
        iva = totale - (totale / 1.10)
        imponibile = totale / 1.10
        
        await db["corrispettivi"].update_one(
            {"id": corr.get("id")},
            {"$set": {
                "totale_iva": round(iva, 2),
                "totale_imponibile": round(imponibile, 2),
                "iva_calcolata_scorporo": True
            }}
        )
        updated += 1
    
    return {"updated": updated, "message": f"IVA ricalcolata su {updated} corrispettivi"}


@router.post("/ricalcola-annulli-non-riscosso")
@handle_errors
async def ricalcola_annulli_non_riscosso() -> Dict[str, Any]:
    """Ricalcola pagato_non_riscosso su tutti i corrispettivi esistenti.
    
    Pagato Non Riscosso = totale lordo riepiloghi - (PagatoContanti + PagatoElettronico)
    """
    db = Database.get_db()
    
    corrispettivi = await db["corrispettivi"].find({}, {"_id": 0}).to_list(10000)
    
    updated = 0
    for corr in corrispettivi:
        riepilogo_iva = corr.get("riepilogo_iva", [])
        pagato_contanti = float(corr.get("pagato_contanti", 0) or 0)
        pagato_elettronico = float(corr.get("pagato_elettronico", 0) or 0)
        totale_corrispettivi = pagato_contanti + pagato_elettronico
        
        # Calcola totale lordo dai riepiloghi
        totale_ammontare = sum(float(r.get('ammontare', 0) or 0) for r in riepilogo_iva)
        totale_importo_parziale = sum(float(r.get('importo_parziale', 0) or 0) for r in riepilogo_iva)
        
        # Usa importo_parziale se presente (è già il lordo), altrimenti ammontare + imposta
        if totale_importo_parziale > 0:
            totale_lordo = totale_importo_parziale
        else:
            totale_imposta = sum(float(r.get('imposta', 0) or 0) for r in riepilogo_iva)
            totale_lordo = totale_ammontare + totale_imposta
        
        # Pagato non riscosso = lordo - (contanti + elettronico)
        pagato_non_riscosso = max(0, round(totale_lordo - totale_corrispettivi, 2))
        
        # Inizializza totale_ammontare_annulli a 0 se non presente
        # (verrà aggiornato quando reimportano gli XML)
        update_data = {
            "pagato_non_riscosso": pagato_non_riscosso
        }
        
        if "totale_ammontare_annulli" not in corr:
            update_data["totale_ammontare_annulli"] = 0
        
        await db["corrispettivi"].update_one(
            {"id": corr.get("id")},
            {"$set": update_data}
        )
        updated += 1
    
    return {"updated": updated, "message": f"Ricalcolati annulli/non riscosso su {updated} corrispettivi"}


@router.get("/totals")
@handle_errors
async def get_corrispettivi_totals() -> Dict[str, Any]:
    """Totali corrispettivi."""
    db = Database.get_db()
    
    pipeline = [{"$group": {
        "_id": None,
        "totale_generale": {"$sum": "$totale"},
        "totale_contanti": {"$sum": "$pagato_contanti"},
        "totale_elettronico": {"$sum": "$pagato_elettronico"},
        "totale_iva": {"$sum": "$totale_iva"},
        "count": {"$sum": 1}
    }}]
    
    result = await db["corrispettivi"].aggregate(pipeline).to_list(1)
    
    if result:
        r = result[0]
        totale = float(r.get("totale_generale", 0) or 0)
        iva = float(r.get("totale_iva", 0) or 0)
        if iva == 0 and totale > 0:
            iva = totale - (totale / 1.10)
        
        return {
            "totale_generale": round(totale, 2),
            "totale_contanti": round(float(r.get("totale_contanti", 0) or 0), 2),
            "totale_elettronico": round(float(r.get("totale_elettronico", 0) or 0), 2),
            "totale_iva": round(iva, 2),
            "totale_imponibile": round(totale / 1.10, 2) if totale > 0 else 0,
            "count": r.get("count", 0)
        }
    
    return {"totale_generale": 0, "totale_contanti": 0, "totale_elettronico": 0, "totale_iva": 0, "totale_imponibile": 0, "count": 0}


@router.post("/upload-xml")
@handle_errors
async def upload_corrispettivo_xml(
    file: UploadFile = File(...),
    force_update: bool = Query(True, description="Se True, sovrascrive corrispettivo esistente")
) -> Dict[str, Any]:
    """Upload singolo corrispettivo XML. Di default aggiorna i dati esistenti."""
    if not file.filename.lower().endswith('.xml'):
        raise HTTPException(status_code=400, detail="Il file deve essere XML")
    
    try:
        content = await file.read()
        xml_content = None
        for enc in ['utf-8', 'utf-8-sig', 'latin-1', 'iso-8859-1']:
            try:
                xml_content = content.decode(enc)
                break
            except (UnicodeDecodeError, LookupError):
                continue
        
        if not xml_content:
            raise HTTPException(status_code=400, detail="Impossibile decodificare")
        
        parsed = parse_corrispettivo_xml(xml_content)
        if parsed.get("error"):
            raise HTTPException(status_code=400, detail=parsed["error"])
        
        db = Database.get_db()
        
        corrispettivo_key = parsed.get("corrispettivo_key", "")
        data_corrispettivo = parsed.get("data", "")
        
        # LOGICA SOVRASCRIZIONE:
        # 1. Cerca prima per corrispettivo_key esatto (stesso registratore)
        # 2. Se non trova, cerca per DATA (per sovrascrivere dati manuali provvisori)
        existing = None
        existing_manuale = None
        
        if corrispettivo_key:
            existing = await db["corrispettivi"].find_one({
                "corrispettivo_key": corrispettivo_key,
                "status": {"$nin": ["deleted", "archived"]}
            })
        
        # Se non trovato per key, cerca record MANUALE per stessa DATA da sovrascrivere
        if not existing and data_corrispettivo:
            existing_manuale = await db["corrispettivi"].find_one({
                "data": data_corrispettivo,
                "source": "manual",  # Solo record manuali
                "status": {"$nin": ["deleted", "archived"]}
            })
        
        corrispettivo_data = {
            "corrispettivo_key": corrispettivo_key,
            "data": data_corrispettivo,
            "matricola_rt": parsed.get("matricola_rt", ""),
            "numero_documento": parsed.get("numero_documento", ""),
            "partita_iva": parsed.get("partita_iva", ""),
            "totale": float(parsed.get("totale", 0) or 0),
            "pagato_contanti": float(parsed.get("pagato_contanti", 0) or 0),
            "pagato_elettronico": float(parsed.get("pagato_elettronico", 0) or 0),
            "totale_imponibile": float(parsed.get("totale_imponibile", 0) or 0),
            "totale_iva": float(parsed.get("totale_iva", 0) or 0),
            "pagato_non_riscosso": float(parsed.get("pagato_non_riscosso", 0) or 0),
            "totale_ammontare_annulli": float(parsed.get("totale_ammontare_annulli", 0) or 0),
            "numero_documenti": int(parsed.get("numero_documenti", 0) or 0),
            "riepilogo_iva": parsed.get("riepilogo_iva", []),
            "status": "imported",
            "source": "xml",  # Marca come proveniente da XML
            "filename": file.filename,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        action = "created"
        corrispettivo_id = None
        movimento_manuale_eliminato = False
        
        if existing:
            # Stesso corrispettivo (stessa matricola) - AGGIORNA con dati XML
            await db["corrispettivi"].update_one(
                {"corrispettivo_key": corrispettivo_key},
                {"$set": corrispettivo_data}
            )
            corrispettivo_id = existing.get("id")
            action = "updated"
            
        elif existing_manuale:
            # Trovato record MANUALE per stessa data - SOVRASCRIVILO con XML
            corrispettivo_id = existing_manuale.get("id")
            corrispettivo_data["id"] = corrispettivo_id
            corrispettivo_data["sovrascritto_manuale"] = True
            corrispettivo_data["data_sovrascrizione"] = datetime.now(timezone.utc).isoformat()
            
            await db["corrispettivi"].update_one(
                {"id": corrispettivo_id},
                {"$set": corrispettivo_data}
            )
            action = "replaced_manual"
            
            # ELIMINA anche il movimento manuale dalla Prima Nota Cassa
            # (il nuovo movimento XML verrà creato dopo)
            mov_manuale = await db["prima_nota_cassa"].find_one({
                "data": data_corrispettivo,
                "categoria": "Corrispettivi",
                "source": {"$in": ["manual_entry", "manual", "corrispettivo_manuale"]}
            })
            if mov_manuale:
                await db["prima_nota_cassa"].delete_one({"_id": mov_manuale["_id"]})
                movimento_manuale_eliminato = True
                logger.info(f"Eliminato movimento manuale Prima Nota per data {data_corrispettivo}")
            
            # Elimina anche eventuali POS manuali per la stessa data
            pos_manuale = await db["prima_nota_cassa"].find_one({
                "data": data_corrispettivo,
                "categoria": "POS",
                "source": {"$in": ["manual_pos", "manual_entry", "manual"]}
            })
            if pos_manuale:
                await db["prima_nota_cassa"].delete_one({"_id": pos_manuale["_id"]})
                logger.info(f"Eliminato POS manuale Prima Nota per data {data_corrispettivo}")
            
        else:
            # INSERT - Nuovo record
            corrispettivo_data["id"] = str(uuid.uuid4())
            corrispettivo_data["created_at"] = datetime.now(timezone.utc).isoformat()
            await db["corrispettivi"].insert_one(corrispettivo_data.copy())
            corrispettivo_id = corrispettivo_data["id"]
            action = "created"
        
        corrispettivo_data.pop("_id", None)
        corrispettivo_data["id"] = corrispettivo_id
        
        # Propaga corrispettivo a Prima Nota Cassa usando DataPropagationService
        # Per nuovi E per quelli che hanno sostituito record manuali
        propagation_result = {}
        if action in ["created", "replaced_manual"]:
            from app.services.data_propagation import get_propagation_service
            propagation_service = get_propagation_service()
            propagation_result = await propagation_service.propagate_corrispettivo_to_prima_nota(corrispettivo_data)
            
            if propagation_result.get("movement_created"):
                await db["corrispettivi"].update_one(
                    {"id": corrispettivo_id},
                    {"$set": {"prima_nota_id": propagation_result.get("movement_id")}}
                )
        
        action_msg = {
            "created": "importato",
            "updated": "aggiornato",
            "replaced_manual": "sostituito dato manuale"
        }.get(action, action)
        
        return {
            "success": True,
            "action": action,
            "message": f"Corrispettivo del {parsed.get('data')} {action_msg}",
            "corrispettivo": corrispettivo_data,
            "prima_nota_id": propagation_result.get("movement_id"),
            "movimento_manuale_eliminato": movimento_manuale_eliminato if 'movimento_manuale_eliminato' in dir() else False
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload-xml-bulk")
@handle_errors
async def upload_corrispettivi_xml_bulk(
    files: List[UploadFile] = File(...),
    force_update: bool = Query(True, description="Se True, aggiorna corrispettivi esistenti invece di saltarli")
) -> Dict[str, Any]:
    """Upload massivo corrispettivi XML. Di default aggiorna i dati esistenti."""
    if not files:
        raise HTTPException(status_code=400, detail="Nessun file")
    
    results = {"success": [], "errors": [], "duplicates": [], "updated": [], "total": len(files), "imported": 0, "failed": 0, "skipped": 0, "updated_count": 0}
    db = Database.get_db()
    
    for file in files:
        try:
            if not file.filename.lower().endswith('.xml'):
                results["errors"].append({"filename": file.filename, "error": "Non XML"})
                results["failed"] += 1
                continue
            
            content = await file.read()
            xml_content = None
            for enc in ['utf-8', 'utf-8-sig', 'latin-1']:
                try:
                    xml_content = content.decode(enc)
                    break
                except (UnicodeDecodeError, LookupError):
                    continue
            
            if not xml_content:
                results["errors"].append({"filename": file.filename, "error": "Decodifica fallita"})
                results["failed"] += 1
                continue
            
            parsed = parse_corrispettivo_xml(xml_content)
            if parsed.get("error"):
                results["errors"].append({"filename": file.filename, "error": parsed["error"]})
                results["failed"] += 1
                continue
            
            key = parsed.get("corrispettivo_key", "")
            existing = await db["corrispettivi"].find_one({"corrispettivo_key": key}) if key else None
            
            if existing:
                if force_update:
                    # UPSERT - Aggiorna esistente
                    update_data = {
                        "data": parsed.get("data", ""),
                        "matricola_rt": parsed.get("matricola_rt", ""),
                        "partita_iva": parsed.get("partita_iva", ""),
                        "totale": float(parsed.get("totale", 0) or 0),
                        "pagato_contanti": float(parsed.get("pagato_contanti", 0) or 0),
                        "pagato_elettronico": float(parsed.get("pagato_elettronico", 0) or 0),
                        "totale_iva": float(parsed.get("totale_iva", 0) or 0),
                        "pagato_non_riscosso": float(parsed.get("pagato_non_riscosso", 0) or 0),
                        "totale_ammontare_annulli": float(parsed.get("totale_ammontare_annulli", 0) or 0),
                        "numero_documenti": int(parsed.get("numero_documenti", 0) or 0),
                        "riepilogo_iva": parsed.get("riepilogo_iva", []),
                        "filename": file.filename,
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }
                    await db["corrispettivi"].update_one(
                        {"corrispettivo_key": key},
                        {"$set": update_data}
                    )
                    results["updated"].append({"filename": file.filename, "data": parsed.get("data")})
                    results["updated_count"] += 1
                else:
                    results["duplicates"].append({"filename": file.filename, "data": parsed.get("data")})
                    results["skipped"] += 1
                continue
            
            # INSERT - Nuovo corrispettivo
            corr = {
                "id": str(uuid.uuid4()),
                "corrispettivo_key": key,
                "data": parsed.get("data", ""),
                "matricola_rt": parsed.get("matricola_rt", ""),
                "partita_iva": parsed.get("partita_iva", ""),
                "totale": float(parsed.get("totale", 0) or 0),
                "pagato_contanti": float(parsed.get("pagato_contanti", 0) or 0),
                "pagato_elettronico": float(parsed.get("pagato_elettronico", 0) or 0),
                "totale_iva": float(parsed.get("totale_iva", 0) or 0),
                "pagato_non_riscosso": float(parsed.get("pagato_non_riscosso", 0) or 0),
                "totale_ammontare_annulli": float(parsed.get("totale_ammontare_annulli", 0) or 0),
                "numero_documenti": int(parsed.get("numero_documenti", 0) or 0),
                "riepilogo_iva": parsed.get("riepilogo_iva", []),
                "filename": file.filename,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            
            await db["corrispettivi"].insert_one(corr.copy())
            
            # Inserisci anche in prima_nota_cassa per visualizzazione
            movimento_cassa = {
                "id": f"corr_{corr['id']}",
                "data": parsed.get("data", ""),
                "tipo": "entrata",
                "importo": float(parsed.get("totale", 0) or 0),
                "descrizione": f"Corrispettivo {parsed.get('data', '')} - RT {parsed.get('matricola_rt', '')}",
                "categoria": "Corrispettivi",
                "dettaglio": {
                    "matricola_rt": parsed.get("matricola_rt", ""),
                    "contanti": float(parsed.get("pagato_contanti", 0) or 0),
                    "elettronico": float(parsed.get("pagato_elettronico", 0) or 0),
                    "totale_iva": float(parsed.get("totale_iva", 0) or 0),
                    "numero_documenti": int(parsed.get("numero_documenti", 0) or 0)
                },
                "corrispettivo_id": corr["id"],
                "fonte": "xml_import",
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            await db["prima_nota_cassa"].insert_one(movimento_cassa.copy())
            
            results["success"].append({"filename": file.filename, "data": parsed.get("data")})
            results["imported"] += 1
            
        except Exception as e:
            results["errors"].append({"filename": file.filename, "error": str(e)})
            results["failed"] += 1
    
    return results


@router.post("/sincronizza-prima-nota")
@handle_errors
async def sincronizza_corrispettivi_prima_nota() -> Dict[str, Any]:
    """
    Sincronizza i corrispettivi dalla collection 'corrispettivi' alla 'prima_nota_cassa'.
    Usa bulk write per evitare timeout su grandi volumi.
    """
    from pymongo import UpdateOne, InsertOne
    db = Database.get_db()

    corrispettivi = await db["corrispettivi"].find({}, {"_id": 0}).to_list(None)

    # Leggi tutti i movimenti corrispettivi esistenti in prima nota in un colpo solo
    movimenti_map = {}
    async for mov in db["prima_nota_cassa"].find({"categoria": "Corrispettivi"}, {"data": 1, "_id": 1}):
        movimenti_map[mov["data"]] = mov["_id"]

    aggiornati, creati, skipped, errors = 0, 0, 0, []
    bulk_updates = []
    bulk_inserts = []

    for corr in corrispettivi:
        try:
            data_corr = corr.get("data", "")
            if not data_corr:
                skipped += 1
                continue

            dettaglio = {
                "matricola_rt": corr.get("matricola_rt", ""),
                "contanti": float(corr.get("pagato_contanti", 0) or 0),
                "elettronico": float(corr.get("pagato_elettronico", 0) or 0),
                "totale_iva": float(corr.get("totale_iva", 0) or 0),
                "numero_documenti": int(corr.get("numero_documenti", 0) or 0)
            }

            if data_corr in movimenti_map:
                bulk_updates.append(UpdateOne(
                    {"_id": movimenti_map[data_corr]},
                    {"$set": {
                        "dettaglio": dettaglio,
                        "importo": float(corr.get("totale", 0) or 0),
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }}
                ))
                aggiornati += 1
            else:
                bulk_inserts.append({
                    "id": f"corr_{corr.get('id', str(uuid.uuid4()))}",
                    "data": data_corr,
                    "tipo": "entrata",
                    "importo": float(corr.get("totale", 0) or 0),
                    "descrizione": f"Corrispettivo {data_corr} - RT {corr.get('matricola_rt', '')}",
                    "categoria": "Corrispettivi",
                    "dettaglio": dettaglio,
                    "corrispettivo_id": corr.get("id"),
                    "fonte": "sincronizzazione",
                    "created_at": datetime.now(timezone.utc).isoformat()
                })
                creati += 1

        except Exception as e:
            errors.append(str(e))

    # Esegui bulk operations
    if bulk_updates:
        await db["prima_nota_cassa"].bulk_write(bulk_updates, ordered=False)
    if bulk_inserts:
        await db["prima_nota_cassa"].insert_many(bulk_inserts, ordered=False)

    return {
        "success": True,
        "message": f"Sincronizzazione completata: {aggiornati} aggiornati, {creati} creati, {skipped} skippati",
        "aggiornati": aggiornati,
        "creati": creati,
        "skipped": skipped,
        "errors": errors[:10]
    }


@router.delete("/all")
@handle_errors
async def delete_all_corrispettivi(
    force: bool = Query(False, description="Forza eliminazione")
) -> Dict[str, Any]:
    """
    Elimina tutti i corrispettivi NON inviati all'AdE.
    I corrispettivi inviati vengono preservati.
    """
    from app.services.business_rules import EntityStatus
    
    db = Database.get_db()
    
    # Solo soft-delete di quelli non inviati
    result = await db["corrispettivi"].update_many(
        {"status": {"$ne": "sent_ade"}},
        {"$set": {
            "entity_status": EntityStatus.DELETED.value,
            "deleted_at": datetime.now().isoformat()
        }}
    )
    
    return {
        "deleted": result.modified_count,
        "message": f"Archiviati {result.modified_count} corrispettivi (quelli inviati all'AdE sono stati preservati)"
    }


@router.delete("/{corrispettivo_id}")
@handle_errors
async def delete_corrispettivo(
    corrispettivo_id: str,
    force: bool = Query(False, description="Forza eliminazione")
) -> Dict[str, Any]:
    """
    Elimina un corrispettivo con validazione business rules.
    
    **Regole:**
    - Non può eliminare corrispettivi inviati all'AdE
    - Non può eliminare corrispettivi già registrati in Prima Nota
    """
    from app.services.business_rules import BusinessRules, EntityStatus
    
    db = Database.get_db()
    
    # Recupera corrispettivo
    corr = await db["corrispettivi"].find_one({"id": corrispettivo_id})
    if not corr:
        raise HTTPException(status_code=404, detail="Corrispettivo non trovato")
    
    # Valida eliminazione
    validation = BusinessRules.can_delete_corrispettivo(corr)
    
    if not validation.is_valid:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Eliminazione non consentita",
                "errors": validation.errors
            }
        )
    
    # Soft-delete
    await db["corrispettivi"].update_one(
        {"id": corrispettivo_id},
        {"$set": {
            "entity_status": EntityStatus.DELETED.value,
            "deleted_at": datetime.now().isoformat()
        }}
    )
    
    # Annulla movimento Prima Nota collegato se esiste
    if corr.get("prima_nota_id"):
        await db["prima_nota_cassa"].update_one(
            {"id": corr["prima_nota_id"]},
            {"$set": {"stato": "annullato"}}
        )
    
    return {
        "deleted": True,
        "message": "Corrispettivo eliminato (archiviato)"
    }


@router.post("/upload-zip")
@handle_errors
async def upload_corrispettivi_zip(file: UploadFile = File(...)) -> Dict[str, Any]:
    """
    Upload massivo corrispettivi da file ZIP contenente XML.
    Gestisce duplicati automaticamente (salta e continua).
    """
    if not file.filename.lower().endswith('.zip'):
        raise HTTPException(status_code=400, detail="Il file deve essere un archivio ZIP")
    
    results = {
        "success": [],
        "errors": [],
        "duplicates": [],
        "total": 0,
        "imported": 0,
        "failed": 0,
        "skipped_duplicates": 0
    }
    
    db = Database.get_db()
    
    try:
        # Leggi il file ZIP
        content = await file.read()
        zip_buffer = io.BytesIO(content)
        
        with zipfile.ZipFile(zip_buffer, 'r') as zip_file:
            # Filtra solo file XML
            xml_files = [f for f in zip_file.namelist() if f.lower().endswith('.xml') and not f.startswith('__MACOSX')]
            results["total"] = len(xml_files)
            
            for xml_filename in xml_files:
                try:
                    # Leggi il file XML dal ZIP
                    xml_content = None
                    xml_bytes = zip_file.read(xml_filename)
                    
                    # Prova diverse codifiche
                    for enc in ['utf-8', 'utf-8-sig', 'latin-1', 'iso-8859-1']:
                        try:
                            xml_content = xml_bytes.decode(enc)
                            break
                        except (UnicodeDecodeError, LookupError):
                            continue
                    
                    if not xml_content:
                        results["errors"].append({
                            "filename": xml_filename,
                            "error": "Impossibile decodificare il file"
                        })
                        results["failed"] += 1
                        continue
                    
                    # Parsa XML
                    parsed = parse_corrispettivo_xml(xml_content)
                    if parsed.get("error"):
                        results["errors"].append({
                            "filename": xml_filename,
                            "error": parsed["error"]
                        })
                        results["failed"] += 1
                        continue
                    
                    # Controlla duplicati (esclude archiviati/eliminati)
                    key = parsed.get("corrispettivo_key", "")
                    if key:
                        existing = await db["corrispettivi"].find_one({
                            "corrispettivo_key": key,
                            "status": {"$nin": ["deleted", "archived"]}
                        })
                        if existing:
                            results["duplicates"].append({
                                "filename": xml_filename,
                                "data": parsed.get("data"),
                                "matricola": parsed.get("matricola_rt"),
                                "totale": parsed.get("totale", 0)
                            })
                            results["skipped_duplicates"] += 1
                            continue
                    
                    # Inserisci nuovo corrispettivo
                    corr = {
                        "id": str(uuid.uuid4()),
                        "corrispettivo_key": key,
                        "data": parsed.get("data", ""),
                        "matricola_rt": parsed.get("matricola_rt", ""),
                        "partita_iva": parsed.get("partita_iva", ""),
                        "totale": float(parsed.get("totale", 0) or 0),
                        "pagato_contanti": float(parsed.get("pagato_contanti", 0) or 0),
                        "pagato_elettronico": float(parsed.get("pagato_elettronico", 0) or 0),
                        "totale_imponibile": float(parsed.get("totale_imponibile", 0) or 0),
                        "totale_iva": float(parsed.get("totale_iva", 0) or 0),
                        "riepilogo_iva": parsed.get("riepilogo_iva", []),
                        "numero_documenti": parsed.get("numero_documenti", 0),
                        "status": "imported",
                        "source": "zip_upload",
                        "filename": xml_filename,
                        "zip_filename": file.filename,
                        "created_at": datetime.now(timezone.utc).isoformat()
                    }
                    
                    await db["corrispettivi"].insert_one(corr.copy())
                    
                    results["success"].append({
                        "filename": xml_filename,
                        "data": parsed.get("data"),
                        "totale": corr["totale"],
                        "contanti": corr["pagato_contanti"],
                        "elettronico": corr["pagato_elettronico"]
                    })
                    results["imported"] += 1
                    
                except Exception as e:
                    logger.error(f"Errore processando {xml_filename}: {e}")
                    results["errors"].append({
                        "filename": xml_filename,
                        "error": str(e)
                    })
                    results["failed"] += 1
        
        return results
        
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="File ZIP non valido o corrotto")
    except Exception as e:
        logger.error(f"Errore upload ZIP: {e}")
        raise HTTPException(status_code=500, detail=str(e))



# ============== SCARICO AUTOMATICO MAGAZZINO ==============

@router.post("/scarica-magazzino")
@handle_errors
async def scarica_magazzino_da_corrispettivi(
    data: str = Query(..., description="Data del corrispettivo (YYYY-MM-DD)")
) -> Dict[str, Any]:
    """
    Scarica automaticamente gli ingredienti dal magazzino basandosi sui corrispettivi del giorno.
    Collegamento vendite -> ricette -> ingredienti -> magazzino.
    """
    db = Database.get_db()
    
    # 1. Recupera i corrispettivi del giorno
    corrispettivi = await db["corrispettivi"].find(
        {"data": data},
        {"_id": 0}
    ).to_list(100)
    
    if not corrispettivi:
        return {"message": "Nessun corrispettivo trovato per questa data", "scarichi": []}
    
    # 2. Recupera tutte le ricette
    ricette = await db["ricette"].find({}, {"_id": 0}).to_list(500)
    ricette_dict = {r.get("nome", "").lower(): r for r in ricette}
    
    # 3. Per ogni corrispettivo, stima le vendite (per ora usa il totale / prezzo medio ricette)
    scarichi = []
    errori = []
    
    for corr in corrispettivi:
        totale = float(corr.get("totale", 0) or 0)
        if totale <= 0:
            continue
        
        # Stima quantità vendute per categoria
        # In un sistema completo, avremmo i dettagli scontrino
        # Per ora, distribuiamo proporzionalmente sulle ricette
        
        for ricetta in ricette:
            # Stima vendite (1 porzione ogni 100€ di incasso per ora)
            porzioni_stimate = max(1, int(totale / 100))
            
            for ing in ricetta.get("ingredienti", []):
                prod_nome = ing.get("nome", "")
                quantita = float(ing.get("quantita", 0) or 0)
                unita = ing.get("unita", "")
                
                if quantita <= 0:
                    continue
                
                # Cerca il prodotto a magazzino
                prodotto = await db["magazzino_doppia_verita"].find_one(
                    {"nome": {"$regex": prod_nome, "$options": "i"}},
                    {"_id": 0}
                )
                
                if not prodotto:
                    continue
                
                # Quantità da scaricare
                qta_scarico = quantita * porzioni_stimate / len(ricette)
                
                # Aggiorna giacenza teorica
                await db["magazzino_doppia_verita"].update_one(
                    {"id": prodotto.get("id")},
                    {
                        "$inc": {"giacenza_teorica": -qta_scarico},
                        "$push": {
                            "movimenti": {
                                "tipo": "SCARICO_VENDITA",
                                "data": data,
                                "quantita": -qta_scarico,
                                "riferimento": f"Corrispettivo {corr.get('id', 'N/A')}",
                                "timestamp": datetime.now(timezone.utc).isoformat()
                            }
                        }
                    }
                )
                
                scarichi.append({
                    "prodotto": prodotto.get("nome"),
                    "quantita_scaricata": round(qta_scarico, 3),
                    "unita": unita,
                    "ricetta": ricetta.get("nome"),
                    "data": data
                })
    
    return {
        "message": f"Scarico magazzino completato per {data}",
        "totale_scarichi": len(scarichi),
        "scarichi": scarichi[:50],  # Limita output
        "errori": errori
    }


@router.post("/collega-vendite-ricette")
@handle_errors
async def collega_vendite_ricette(
    data_da: str = Query(...),
    data_a: str = Query(...)
) -> Dict[str, Any]:
    """
    Analizza i corrispettivi e stima quali ricette sono state vendute.
    Crea un report del consumo teorico di ingredienti.
    """
    db = Database.get_db()
    
    # Corrispettivi nel periodo
    corrispettivi = await db["corrispettivi"].find(
        {"data": {"$gte": data_da, "$lte": data_a}},
        {"_id": 0}
    ).to_list(10000)
    
    totale_incasso = sum(float(c.get("totale", 0) or 0) for c in corrispettivi)
    
    # Ricette disponibili
    ricette = await db["ricette"].find({}, {"_id": 0}).to_list(500)
    
    # Stima vendite per ricetta (distribuzione proporzionale)
    # In un sistema completo, si userebbe l'analisi degli scontrini
    vendite_stimate = []
    consumo_ingredienti = {}
    
    prezzo_medio = sum(r.get("prezzo_vendita", 2.5) for r in ricette) / max(len(ricette), 1)
    porzioni_totali_stimate = int(totale_incasso / prezzo_medio)
    porzioni_per_ricetta = porzioni_totali_stimate / max(len(ricette), 1)
    
    for ricetta in ricette:
        porzioni = int(porzioni_per_ricetta)
        vendite_stimate.append({
            "ricetta": ricetta.get("nome"),
            "porzioni_stimate": porzioni,
            "food_cost_stimato": round(float(ricetta.get("food_cost", 0) or 0) * porzioni, 2)
        })
        
        # Accumula consumo ingredienti
        for ing in ricetta.get("ingredienti", []):
            nome = ing.get("nome", "")
            qta = float(ing.get("quantita", 0) or 0) * porzioni
            
            if nome in consumo_ingredienti:
                consumo_ingredienti[nome]["quantita"] += qta
            else:
                consumo_ingredienti[nome] = {
                    "nome": nome,
                    "quantita": qta,
                    "unita": ing.get("unita", "")
                }
    
    return {
        "periodo": {"da": data_da, "a": data_a},
        "totale_incasso": round(totale_incasso, 2),
        "corrispettivi_count": len(corrispettivi),
        "porzioni_totali_stimate": porzioni_totali_stimate,
        "vendite_per_ricetta": vendite_stimate[:20],
        "consumo_ingredienti": list(consumo_ingredienti.values())[:30],
        "note": "Stime basate su distribuzione uniforme. Per dati precisi, importare dettagli scontrino."
    }



# ============== IMPORT CSV CORRISPETTIVI ==============

@router.post("/import-csv")
@handle_errors
async def import_corrispettivi_csv(file: UploadFile = File(...)) -> Dict[str, Any]:
    """
    Importa corrispettivi da file CSV (formato Agenzia Entrate).
    Formato atteso:
    - Separatore: ; (punto e virgola)
    - Numeri: "000000003605,60" (virgola decimale)
    - Data: DD/MM/YYYY HH:MM:SS
    - Colonne: Id invio;Matricola;Data rilevazione;Data trasmissione;Totale;Imponibile;IVA
    """
    import re
    
    db = Database.get_db()
    
    try:
        content = await file.read()
        # Prova diverse codifiche
        try:
            text = content.decode('utf-8')
        except Exception:
            text = content.decode('latin-1')
        
        lines = text.strip().split('\n')
        
        # Salta header
        if lines[0].startswith('Id invio') or 'Matricola' in lines[0]:
            lines = lines[1:]
        
        importati = 0
        aggiornati = 0
        errori = []
        totale_importato = 0
        
        for i, line in enumerate(lines):
            try:
                # Parse CSV con ; come separatore
                parts = line.split(';')
                if len(parts) < 7:
                    continue
                
                # Rimuovi apici e parse dei campi
                def clean_value(val):
                    return val.strip().strip("'").strip('"')
                
                def parse_amount(val):
                    """Parse formato "000000003605,60" -> 3605.60"""
                    clean = clean_value(val).replace('.', '').replace(',', '.')
                    # Rimuovi zeri iniziali ma mantieni il valore
                    return float(clean)
                
                id_invio = clean_value(parts[0])
                matricola = clean_value(parts[1])
                data_rilevazione = clean_value(parts[2])
                data_trasmissione = clean_value(parts[3])
                totale = parse_amount(parts[4])
                imponibile = parse_amount(parts[5])
                iva = parse_amount(parts[6])
                
                # Parse data (DD/MM/YYYY HH:MM:SS -> YYYY-MM-DD)
                data_match = re.match(r'(\d{2})/(\d{2})/(\d{4})', data_rilevazione)
                if not data_match:
                    errori.append(f"Riga {i+1}: formato data non valido: {data_rilevazione}")
                    continue
                
                data_iso = f"{data_match.group(3)}-{data_match.group(2)}-{data_match.group(1)}"
                
                if totale <= 0:
                    continue
                
                # Verifica se esiste già (stesso id_invio o stessa data con stesso importo)
                existing = await db["corrispettivi"].find_one({
                    "$or": [
                        {"id_invio": id_invio},
                        {"data": data_iso, "totale": totale}
                    ]
                })
                
                corr_doc = {
                    "id": str(uuid.uuid4()),
                    "id_invio": id_invio,
                    "matricola": matricola,
                    "data": data_iso,
                    "data_rilevazione": data_rilevazione,
                    "data_trasmissione": data_trasmissione,
                    "totale": totale,
                    "totale_imponibile": imponibile,
                    "totale_iva": iva,
                    "aliquota_iva": 10 if imponibile > 0 else 0,
                    "source": "csv_import",
                    "filename": file.filename,
                    "created_at": datetime.now(timezone.utc).isoformat()
                }
                
                if existing:
                    # Aggiorna
                    await db["corrispettivi"].update_one(
                        {"_id": existing["_id"]},
                        {"$set": {
                            "id_invio": id_invio,
                            "totale": totale,
                            "totale_imponibile": imponibile,
                            "totale_iva": iva,
                            "updated_at": datetime.now(timezone.utc).isoformat()
                        }}
                    )
                    aggiornati += 1
                else:
                    # Inserisci nuovo
                    await db["corrispettivi"].insert_one(corr_doc.copy())
                    importati += 1
                
                totale_importato += totale
                
            except Exception as e:
                errori.append(f"Riga {i+1}: {str(e)}")
                continue
        
        return {
            "success": True,
            "message": f"Import completato: {importati} nuovi, {aggiornati} aggiornati",
            "importati": importati,
            "aggiornati": aggiornati,
            "totale_importato": round(totale_importato, 2),
            "errori": errori[:20] if errori else None,
            "errori_count": len(errori)
        }
        
    except Exception as e:
        logger.error(f"Errore import CSV: {e}")
        raise HTTPException(status_code=500, detail=f"Errore parsing CSV: {str(e)}")


@router.get("/template-csv")
@handle_errors
async def get_template_csv():
    """Restituisce un template CSV per l'import dei corrispettivi."""
    from fastapi.responses import Response
    
    template = """Id invio;Matricola dispositivo;Data e ora rilevazione;Data e ora trasmissione;Ammontare delle vendite (totale in euro);Imponibile vendite (totale in euro);Imposta vendite (totale in euro);Periodo di inattivita' da;Periodo di inattivita' a
'1234567890';'99MEY000000';01/01/2024 21:00:00;01/01/2024 21:01:00;"000000001500,00";"000000001363,64";"000000000136,36";;
'1234567891';'99MEY000000';02/01/2024 21:00:00;02/01/2024 21:01:00;"000000002000,00";"000000001818,18";"000000000181,82";;"""
    
    return Response(
        content=template,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=template_corrispettivi.csv"}
    )



@router.post("/elimina-duplicati")
@handle_errors
async def elimina_duplicati_corrispettivi(anno: int = Query(...)) -> Dict[str, Any]:
    """
    Elimina i corrispettivi duplicati per un anno.
    Mantiene solo il record con l'importo più alto per ogni data.
    """
    from collections import defaultdict
    
    db = Database.get_db()
    
    date_start = f"{anno}-01-01"
    date_end = f"{anno}-12-31"
    
    # Recupera tutti i corrispettivi dell'anno
    corrs = await db["corrispettivi"].find(
        {"data": {"$gte": date_start, "$lte": date_end}},
        {"_id": 1, "data": 1, "totale": 1, "source": 1}
    ).to_list(10000)
    
    count_prima = len(corrs)
    
    # Raggruppa per data
    by_date = defaultdict(list)
    for c in corrs:
        by_date[c.get('data')].append(c)
    
    deleted = 0
    date_con_duplicati = 0
    
    for data, items in by_date.items():
        if len(items) > 1:
            date_con_duplicati += 1
            # Ordina per totale decrescente, tieni il primo
            items.sort(key=lambda x: float(x.get('totale', 0) or 0), reverse=True)
            to_delete = items[1:]  # Tutti tranne il primo
            
            for item in to_delete:
                await db["corrispettivi"].delete_one({"_id": item["_id"]})
                deleted += 1
    
    # Conta dopo
    count_dopo = await db["corrispettivi"].count_documents(
        {"data": {"$gte": date_start, "$lte": date_end}}
    )
    
    # Calcola nuovo totale
    pipeline = [
        {"$match": {"data": {"$gte": date_start, "$lte": date_end}}},
        {"$group": {"_id": None, "totale": {"$sum": "$totale"}}}
    ]
    result = await db["corrispettivi"].aggregate(pipeline).to_list(1)
    nuovo_totale = result[0]["totale"] if result else 0
    
    return {
        "success": True,
        "message": f"Eliminati {deleted} duplicati per {anno}",
        "anno": anno,
        "corrispettivi_prima": count_prima,
        "corrispettivi_dopo": count_dopo,
        "duplicati_eliminati": deleted,
        "date_con_duplicati": date_con_duplicati,
        "nuovo_totale": round(nuovo_totale, 2)
    }


@router.delete("/hard-delete/{corrispettivo_id}")
@handle_errors
async def hard_delete_corrispettivo(corrispettivo_id: str) -> Dict[str, Any]:
    """Elimina FISICAMENTE un corrispettivo dal database."""
    db = Database.get_db()
    result = await db["corrispettivi"].delete_one({"id": corrispettivo_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Corrispettivo non trovato")
    return {"deleted": True, "hard_delete": True}


@router.post("/hard-delete-bulk")
@handle_errors
async def hard_delete_corrispettivi_bulk(data: Dict[str, Any]) -> Dict[str, Any]:
    """Elimina FISICAMENTE più corrispettivi dal database."""
    db = Database.get_db()
    ids = data.get("ids", [])
    if not ids:
        raise HTTPException(status_code=400, detail="Nessun ID fornito")
    
    result = await db["corrispettivi"].delete_many({"id": {"$in": ids}})
    return {"deleted": result.deleted_count}



@router.post("/auto-ricostruisci-dati")
@handle_errors
async def auto_ricostruisci_dati_corrispettivi() -> Dict[str, Any]:
    """
    LOGICA INTELLIGENTE: Verifica e corregge automaticamente i corrispettivi.
    
    REGOLE:
    1. Verifica campi mancanti (data, totale, iva)
    2. Ricalcola IVA con scorporo se mancante
    3. Verifica e corregge sincronizzazione con Prima Nota Cassa
    4. Rimuove duplicati evidenti
    """
    db = Database.get_db()
    
    risultati = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "corrispettivi_verificati": 0,
        "iva_ricalcolata": 0,
        "campi_corretti": 0,
        "duplicati_rimossi": 0,
        "errori": []
    }
    
    try:
        # 1. Verifica corrispettivi con IVA mancante o zero
        corr_senza_iva = await db["corrispettivi"].find({
            "$or": [{"totale_iva": 0}, {"totale_iva": None}],
            "totale": {"$gt": 0}
        }, {"_id": 0}).to_list(10000)
        
        risultati["corrispettivi_verificati"] = len(corr_senza_iva)
        
        for corr in corr_senza_iva:
            totale = float(corr.get("totale", 0) or 0)
            if totale > 0:
                # Scorporo IVA 10%
                imponibile = round(totale / 1.10, 2)
                iva = round(totale - imponibile, 2)
                
                try:
                    await db["corrispettivi"].update_one(
                        {"id": corr["id"]},
                        {"$set": {
                            "totale_iva": iva,
                            "totale_imponibile": imponibile,
                            "iva_ricalcolata_auto": True,
                            "updated_at": datetime.now(timezone.utc).isoformat()
                        }}
                    )
                    risultati["iva_ricalcolata"] += 1
                except Exception as e:
                    risultati["errori"].append(f"Errore IVA {corr['id']}: {str(e)}")
        
        # 2. Verifica corrispettivi con data mancante o errata
        corr_senza_data = await db["corrispettivi"].count_documents({
            "$or": [{"data": None}, {"data": ""}, {"data": {"$regex": r"^N/[AD]"}}]
        })
        
        if corr_senza_data > 0:
            # Usa data_trasmissione se disponibile
            await db["corrispettivi"].update_many(
                {"data": None, "data_trasmissione": {"$exists": True}},
                [{"$set": {"data": "$data_trasmissione"}}]
            )
            risultati["campi_corretti"] += corr_senza_data
        
        # 3. Rimuovi duplicati (stesso giorno, stesso totale, stesso punto cassa)
        pipeline = [
            {"$group": {
                "_id": {"data": "$data", "totale": "$totale", "punto_cassa": {"$ifNull": ["$punto_cassa", "default"]}},
                "count": {"$sum": 1},
                "ids": {"$push": "$id"}
            }},
            {"$match": {"count": {"$gt": 1}}}
        ]
        duplicati = await db["corrispettivi"].aggregate(pipeline).to_list(1000)
        
        for dup in duplicati:
            ids = dup.get("ids", [])
            if len(ids) > 1:
                for dup_id in ids[1:]:  # Mantieni il primo
                    try:
                        await db["corrispettivi"].delete_one({"id": dup_id})
                        risultati["duplicati_rimossi"] += 1
                    except Exception as e:
                        risultati["errori"].append(f"Errore rimozione {dup_id}: {str(e)}")
        
    except Exception as e:
        logger.error(f"Errore auto-ricostruzione corrispettivi: {e}")
        risultati["errori"].append(str(e))
    
    return risultati


# ==================== VISUALIZZAZIONE CORRISPETTIVO ====================

def generate_corrispettivo_html(corrispettivo: Dict, movimento: Dict = None) -> str:
    """
    Genera HTML per visualizzare il corrispettivo in formato scontrino.
    """
    # Estrai dati dal corrispettivo o movimento
    data = corrispettivo.get("data", "")
    totale = corrispettivo.get("totale", 0) or corrispettivo.get("importo", 0) or 0
    pagato_contanti = corrispettivo.get("pagato_contanti", 0) or 0
    pagato_elettronico = corrispettivo.get("pagato_elettronico", 0) or 0
    totale_iva = corrispettivo.get("totale_iva", 0) or corrispettivo.get("imposta", 0) or 0
    totale_imponibile = corrispettivo.get("totale_imponibile", 0) or corrispettivo.get("imponibile", 0) or 0
    matricola_rt = corrispettivo.get("matricola_rt", "") or ""
    numero_documenti = corrispettivo.get("numero_documenti", 0) or 0
    
    # Dati aggiuntivi dal movimento prima nota
    if movimento:
        dettaglio = movimento.get("dettaglio", {})
        if dettaglio:
            pagato_contanti = dettaglio.get("contanti", pagato_contanti) or pagato_contanti
            pagato_elettronico = dettaglio.get("elettronico", pagato_elettronico) or pagato_elettronico
            totale_iva = dettaglio.get("totale_iva", totale_iva) or totale_iva
            matricola_rt = dettaglio.get("matricola_rt", matricola_rt) or matricola_rt
            numero_documenti = dettaglio.get("numero_documenti", numero_documenti) or numero_documenti
        totale_iva = movimento.get("imposta", totale_iva) or totale_iva
        totale_imponibile = movimento.get("imponibile", totale_imponibile) or totale_imponibile
    
    # Riepilogo IVA
    riepilogo_iva = corrispettivo.get("riepilogo_iva", []) or []
    dettaglio_iva = corrispettivo.get("dettaglio_iva", []) or movimento.get("dettaglio_iva", []) if movimento else []
    
    # Pagato non riscosso
    pagato_non_riscosso = corrispettivo.get("pagato_non_riscosso", 0) or 0
    
    # Annulli
    totale_annulli = corrispettivo.get("totale_ammontare_annulli", 0) or 0
    
    # Formatta importi
    def fmt_euro(val):
        try:
            return f"€ {float(val):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        except Exception:
            return "€ 0,00"
    
    # Formatta data
    def fmt_data(d):
        if not d:
            return "-"
        try:
            if "T" in str(d):
                d = str(d).split("T")[0]
            parts = str(d).split("-")
            if len(parts) == 3:
                return f"{parts[2]}/{parts[1]}/{parts[0]}"
            return d
        except Exception:
            return d
    
    # Genera righe IVA
    iva_rows = ""
    iva_list = dettaglio_iva or riepilogo_iva
    for iva in iva_list:
        aliquota = iva.get("aliquota", iva.get("aliquota_iva", 0))
        imponibile = iva.get("imponibile", iva.get("ammontare", 0))
        imposta = iva.get("imposta", 0)
        iva_rows += f"""
        <tr>
            <td style="padding: 6px 12px;">Aliquota {aliquota}%</td>
            <td style="padding: 6px 12px; text-align: right;">{fmt_euro(imponibile)}</td>
            <td style="padding: 6px 12px; text-align: right;">{fmt_euro(imposta)}</td>
        </tr>"""
    
    if not iva_rows and totale_imponibile:
        # Default 10%
        iva_rows = f"""
        <tr>
            <td style="padding: 6px 12px;">Aliquota 10%</td>
            <td style="padding: 6px 12px; text-align: right;">{fmt_euro(totale_imponibile)}</td>
            <td style="padding: 6px 12px; text-align: right;">{fmt_euro(totale_iva)}</td>
        </tr>"""
    
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Corrispettivo del {fmt_data(data)}</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ 
            font-family: 'Courier New', monospace; 
            background: #f0f2f5; 
            padding: 20px;
            display: flex;
            justify-content: center;
            align-items: flex-start;
            min-height: 100vh;
        }}
        .scontrino {{
            background: white;
            width: 100%;
            max-width: 420px;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.15);
            border: 1px solid #e0e0e0;
        }}
        .header {{
            text-align: center;
            border-bottom: 2px dashed #333;
            padding-bottom: 20px;
            margin-bottom: 20px;
        }}
        .ragione-sociale {{
            font-size: 18px;
            font-weight: bold;
            color: #1a1a1a;
            margin-bottom: 8px;
        }}
        .info-azienda {{
            font-size: 12px;
            color: #666;
            line-height: 1.6;
        }}
        .tipo-documento {{
            background: #10b981;
            color: white;
            padding: 8px 16px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: bold;
            display: inline-block;
            margin-top: 12px;
        }}
        .section {{
            margin: 20px 0;
            padding: 15px 0;
            border-bottom: 1px dashed #ccc;
        }}
        .section-title {{
            font-size: 11px;
            color: #888;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 12px;
        }}
        .row {{
            display: flex;
            justify-content: space-between;
            padding: 6px 0;
            font-size: 14px;
        }}
        .row.highlight {{
            background: #f8f9fa;
            padding: 10px;
            margin: 8px -10px;
            border-radius: 4px;
        }}
        .label {{ color: #555; }}
        .value {{ font-weight: bold; color: #1a1a1a; }}
        .value.green {{ color: #10b981; }}
        .value.blue {{ color: #3b82f6; }}
        .value.red {{ color: #ef4444; }}
        .totale {{
            text-align: center;
            padding: 20px;
            background: linear-gradient(135deg, #1e3a5f, #2d5a87);
            color: white;
            border-radius: 8px;
            margin: 20px 0;
        }}
        .totale-label {{ font-size: 12px; opacity: 0.9; }}
        .totale-value {{ font-size: 32px; font-weight: bold; margin-top: 8px; }}
        .iva-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 12px;
            margin: 10px 0;
        }}
        .iva-table th {{
            background: #f3f4f6;
            padding: 8px 12px;
            text-align: left;
            font-size: 11px;
            color: #666;
        }}
        .iva-table td {{
            border-bottom: 1px solid #f0f0f0;
        }}
        .footer {{
            text-align: center;
            padding-top: 20px;
            border-top: 2px dashed #333;
            margin-top: 20px;
        }}
        .matricola {{
            background: #f3f4f6;
            padding: 10px 15px;
            border-radius: 6px;
            font-size: 12px;
            margin-bottom: 12px;
        }}
        .matricola-label {{ font-size: 10px; color: #888; }}
        .matricola-value {{ font-weight: bold; color: #333; font-size: 14px; }}
        .data-ora {{
            font-size: 14px;
            color: #333;
            font-weight: bold;
        }}
        .print-btn {{
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 12px 24px;
            background: #10b981;
            color: white;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 14px;
            font-weight: bold;
            z-index: 1000;
        }}
        .print-btn:hover {{ background: #059669; }}
        @media print {{ 
            .print-btn {{ display: none; }} 
            body {{ background: white; padding: 0; }}
            .scontrino {{ box-shadow: none; border: none; }}
        }}
    </style>
</head>
<body>
    <button class="print-btn" onclick="window.print()">🖨️ Stampa</button>
    
    <div class="scontrino">
        <div class="header">
            <div class="ragione-sociale">CERALDI CAFFÈ</div>
            <div class="info-azienda">
                Piazza Carità<br>
                80134 Napoli (NA)<br>
                P.IVA: 04523831214
            </div>
            <div class="tipo-documento">🧾 CORRISPETTIVO GIORNALIERO</div>
        </div>
        
        <div class="totale">
            <div class="totale-label">TOTALE INCASSO</div>
            <div class="totale-value">{fmt_euro(totale)}</div>
        </div>
        
        <div class="section">
            <div class="section-title">📊 Dettaglio Pagamenti</div>
            <div class="row">
                <span class="label">💵 Pagamento Contanti</span>
                <span class="value green">{fmt_euro(pagato_contanti)}</span>
            </div>
            <div class="row">
                <span class="label">💳 Pagamento Elettronico</span>
                <span class="value blue">{fmt_euro(pagato_elettronico)}</span>
            </div>
            {'<div class="row"><span class="label">⏳ Non Riscosso</span><span class="value red">' + fmt_euro(pagato_non_riscosso) + '</span></div>' if pagato_non_riscosso > 0 else ''}
            {'<div class="row"><span class="label">❌ Annulli</span><span class="value red">-' + fmt_euro(totale_annulli) + '</span></div>' if totale_annulli > 0 else ''}
        </div>
        
        <div class="section">
            <div class="section-title">📋 Riepilogo IVA</div>
            <table class="iva-table">
                <thead>
                    <tr>
                        <th>Descrizione</th>
                        <th style="text-align: right;">Imponibile</th>
                        <th style="text-align: right;">Imposta</th>
                    </tr>
                </thead>
                <tbody>
                    {iva_rows}
                    <tr style="font-weight: bold; background: #f8f9fa;">
                        <td style="padding: 10px 12px;">TOTALE</td>
                        <td style="padding: 10px 12px; text-align: right;">{fmt_euro(totale_imponibile)}</td>
                        <td style="padding: 10px 12px; text-align: right;">{fmt_euro(totale_iva)}</td>
                    </tr>
                </tbody>
            </table>
        </div>
        
        <div class="section">
            <div class="section-title">📈 Statistiche</div>
            <div class="row">
                <span class="label">Numero Documenti</span>
                <span class="value">{numero_documenti}</span>
            </div>
        </div>
        
        <div class="footer">
            {f'<div class="matricola"><div class="matricola-label">Matricola RT</div><div class="matricola-value">{matricola_rt}</div></div>' if matricola_rt else ''}
            <div class="data-ora">{fmt_data(data)}</div>
        </div>
    </div>
</body>
</html>"""
    
    return html


@router.get("/view-by-filename")
@handle_errors
async def view_corrispettivo_by_filename(filename: str = Query(...)):
    """
    Visualizza il corrispettivo cercando per filename XML.
    """
    from fastapi.responses import HTMLResponse
    
    db = Database.get_db()
    
    # Cerca il movimento in prima nota cassa con quel filename
    movimento = await db["prima_nota_cassa"].find_one(
        {"xml_filename": filename},
        {"_id": 0}
    )
    
    if not movimento:
        raise HTTPException(status_code=404, detail="Corrispettivo non trovato per questo filename")
    
    # Cerca il corrispettivo associato per data
    corrispettivo = await db["corrispettivi"].find_one(
        {"data": movimento.get("data")},
        {"_id": 0}
    )
    
    # Se non trovato, usa i dati del movimento stesso
    if not corrispettivo:
        corrispettivo = {
            "data": movimento.get("data"),
            "totale": movimento.get("importo"),
            "pagato_contanti": movimento.get("pagato_contanti"),
            "pagato_elettronico": movimento.get("pagato_elettronico"),
            "totale_iva": movimento.get("imposta"),
            "totale_imponibile": movimento.get("imponibile"),
            "dettaglio_iva": movimento.get("dettaglio_iva", []),
            "matricola_rt": movimento.get("dettaglio", {}).get("matricola_rt", ""),
            "numero_documenti": movimento.get("dettaglio", {}).get("numero_documenti", 0)
        }
    
    html_content = generate_corrispettivo_html(corrispettivo, movimento)
    
    return HTMLResponse(content=html_content, status_code=200)


@router.get("/{corrispettivo_id}/view")
@handle_errors
async def view_corrispettivo(corrispettivo_id: str):
    """
    Visualizza il corrispettivo in formato HTML (stile scontrino).
    """
    from fastapi.responses import HTMLResponse
    
    db = Database.get_db()
    
    # Cerca il corrispettivo
    corrispettivo = await db["corrispettivi"].find_one({"id": corrispettivo_id}, {"_id": 0})
    
    if not corrispettivo:
        raise HTTPException(status_code=404, detail="Corrispettivo non trovato")
    
    # Cerca anche il movimento associato in prima nota per dati aggiuntivi
    movimento = await db["prima_nota_cassa"].find_one(
        {"$or": [
            {"corrispettivo_id": corrispettivo_id},
            {"data": corrispettivo.get("data"), "categoria": "Corrispettivi"}
        ]},
        {"_id": 0}
    )
    
    html_content = generate_corrispettivo_html(corrispettivo, movimento)
    
    return HTMLResponse(content=html_content, status_code=200)

