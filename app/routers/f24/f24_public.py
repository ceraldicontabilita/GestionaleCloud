"""
F24 Public Router - Endpoints F24 senza autenticazione
NOTA: Usa f24_commercialista come collezione unica per F24
"""
from fastapi import APIRouter, UploadFile, File, HTTPException, Body, Query
from typing import Dict, Any
from datetime import datetime, timezone
import logging

from app.database import Database
from app.db_collections import COLL_F24
from app.utils.error_handler import handle_errors
from app.services.f24_payment_evidence import stato_evidenza_pagamento

logger = logging.getLogger(__name__)
router = APIRouter()

# Collezione F24 unica
F24_COLLECTION = COLL_F24  # "f24_commercialista"


@router.get("/test")
@handle_errors
async def test_route():
    """Test route."""
    return {"status": "ok"}


@router.get("/models")
@handle_errors
async def list_f24_models(anno: int = None) -> Dict[str, Any]:
    """Lista tutti i modelli F24 - unifica quietanze e f24_unificato."""
    import time
    logger.info(f"=== /models endpoint called (anno={anno}) ===")
    t_start = time.time()

    db = Database.get_db()

    try:
        # Primary: quietanze_f24 (ha dati completi con pagamenti reali)
        q_filter = {}
        if anno:
            q_filter["data_pagamento"] = {"$regex": f"^{anno}"}
        quietanze = await db["quietanze_f24"].find(
            q_filter,
            {"_id": 0, "pdf_data": 0}
        ).sort("created_at", -1).to_list(500)

        # Secondary: f24_unificato (per eventuali F24 non ancora pagati)
        u_filter = {"status": {"$ne": "eliminato"}}
        if anno:
            u_filter["$or"] = [
                {"data_pagamento": {"$regex": f"^{anno}"}},
                {"data_versamento": {"$regex": f"^{anno}"}},
            ]
        f24_uni = await db[F24_COLLECTION].find(
            u_filter,
            {"_id": 0, "pdf_data": 0}
        ).sort("created_at", -1).to_list(100)

        # La quietanza viene mostrata insieme al relativo modello, ma eredita
        # lo stato PAGATO soltanto se quel modello possiede la prova bancaria.
        f24_per_quietanza = {
            str(f.get("quietanza_id")): f
            for f in f24_uni
            if f.get("quietanza_id")
        }

        # Trasforma quietanze nel formato atteso dal frontend
        f24s = []
        seen_ids = set()

        for q in quietanze:
            dati = q.get("dati_generali", {})
            totali = q.get("totali", {})
            data_pag = q.get("data_pagamento") or dati.get("data_pagamento")
            saldo = q.get("saldo", 0) or totali.get("saldo_netto", 0) or totali.get("totale_debito", 0)
            qid = q.get("id", "")
            # Dedup by protocollo_telematico (unique per F24)
            proto = q.get("protocollo_telematico", "")
            dedup_key = proto if proto else f"{data_pag}_{saldo}"
            if dedup_key in seen_ids:
                continue
            seen_ids.add(dedup_key)
            if qid:
                seen_ids.add(qid)

            evidenza = stato_evidenza_pagamento(
                f24_per_quietanza.get(str(qid), q)
            )
            f24s.append({
                "id": qid,
                "tipo_modello": "F24",
                "anno": int(data_pag[:4]) if data_pag and len(data_pag) >= 4 else None,
                "data_scadenza": data_pag,
                "data_versamento": data_pag,
                "saldo_finale": saldo,
                "pagato": evidenza["pagato"],
                "contribuente": dati.get("ragione_sociale", dati.get("codice_fiscale", q.get("codice_fiscale", ""))),
                "file_name": q.get("filename"),
                "status": "pagato" if evidenza["pagato"] else "da_verificare_banca",
                "stato_evidenza_pagamento": evidenza["stato"],
                "pagamento_verificato_banca": evidenza["verificato_banca"],
                "protocollo": q.get("protocollo_telematico", ""),
                "tributi_erario": q.get("sezione_erario", []),
                "tributi_inps": q.get("sezione_inps", []),
                "tributi_regioni": q.get("sezione_regioni", []),
                "tributi_imu": q.get("sezione_tributi_locali", []),
                "totale_debito": totali.get("totale_debito", 0),
                "totale_credito": totali.get("totale_credito", 0),
                "source": "quietanza"
            })

        # Aggiungi f24_unificato (solo quelli non presenti)
        for f in f24_uni:
            fid = f.get("id", "")
            if fid in seen_ids:
                continue
            seen_ids.add(fid)
            totali = f.get("totali", {})
            dati = f.get("dati_generali", {})
            data_vers = f.get("data_versamento") or f.get("data_pagamento") or dati.get("data_versamento")
            saldo = f.get("totale_versato", 0) or totali.get("saldo_netto", 0) or 0

            if not data_vers and not saldo:
                continue  # Skip documenti completamente vuoti

            evidenza = stato_evidenza_pagamento(f)
            f24s.append({
                "id": fid,
                "tipo_modello": "F24",
                "anno": int(data_vers[:4]) if data_vers and len(data_vers) >= 4 else None,
                "data_scadenza": data_vers,
                "data_versamento": data_vers,
                "saldo_finale": saldo,
                "pagato": evidenza["pagato"],
                "contribuente": dati.get("ragione_sociale", dati.get("codice_fiscale", f.get("codice_fiscale", ""))),
                "file_name": f.get("filename") or f.get("file_name"),
                "status": "pagato" if evidenza["pagato"] else f.get("status", "da_pagare"),
                "stato_evidenza_pagamento": evidenza["stato"],
                "pagamento_verificato_banca": evidenza["verificato_banca"],
                "source": "f24_unificato"
            })

        # Sort by date desc
        f24s.sort(key=lambda x: x.get("data_scadenza") or "", reverse=True)

        logger.info(f"F24 models query took {time.time() - t_start:.2f}s for {len(f24s)} items (quietanze: {len(quietanze)}, f24_uni: {len(f24_uni)})")
    except Exception as e:
        logger.error(f"F24 models query error: {e}")
        f24s = []

    return {
        "f24s": f24s,
        "count": len(f24s),
        "totale_da_pagare": sum(f.get("saldo_finale", 0) or 0 for f in f24s if not f.get("pagato")),
        "totale_pagato": sum(f.get("saldo_finale", 0) or 0 for f in f24s if f.get("pagato"))
    }


@router.get("/scadenze-prossime")
@handle_errors
async def get_scadenze_prossime_public(
    giorni: int = 60,
    limit: int = 5
) -> Dict[str, Any]:
    """
    Get upcoming F24 deadlines for the dashboard widget (public, no auth).
    Returns the next F24s sorted by due date with summary info.
    """
    from datetime import timezone

    db = Database.get_db()
    today = datetime.now(timezone.utc).date()

    scadenze = []
    totale_importo = 0

    # Get unpaid F24s dalla collezione unificata
    f24_list = await db[F24_COLLECTION].find(
        {"status": {"$nin": ["pagato", "eliminato"]}},
        {"_id": 0}
    ).to_list(500)

    for f24 in f24_list:
        try:
            dati = f24.get("dati_generali", {})
            totali = f24.get("totali", {})

            scadenza_str = dati.get("data_scadenza")
            if not scadenza_str:
                # Usa created_at come fallback
                scadenza_str = f24.get("created_at", "")[:10] if f24.get("created_at") else None
                if not scadenza_str:
                    continue

            if isinstance(scadenza_str, str):
                scadenza_str = scadenza_str.replace("Z", "+00:00")
                if "T" in scadenza_str:
                    scadenza = datetime.fromisoformat(scadenza_str).date()
                else:
                    try:
                        scadenza = datetime.strptime(scadenza_str, "%d/%m/%Y").date()
                    except ValueError:
                        try:
                            scadenza = datetime.strptime(scadenza_str[:10], "%Y-%m-%d").date()
                        except Exception:
                            continue
            elif isinstance(scadenza_str, datetime):
                scadenza = scadenza_str.date()
            else:
                continue

            giorni_mancanti = (scadenza - today).days

            if giorni_mancanti <= giorni:
                importo = float(totali.get("saldo_netto", 0) or 0)
                totale_importo += importo

                # Determina tipo dal primo codice tributo
                tipo_display = "F24"
                sezione_erario = f24.get("sezione_erario", [])
                if sezione_erario and len(sezione_erario) > 0:
                    first_code = sezione_erario[0].get("codice_tributo", "")
                    if first_code.startswith("60"):
                        tipo_display = "IVA"
                    elif first_code.startswith("10"):
                        tipo_display = "IRPEF"

                scadenze.append({
                    "id": f24.get("id"),
                    "tipo": tipo_display,
                    "descrizione": dati.get("ragione_sociale", f24.get("file_name", "")),
                    "importo": importo,
                    "data_scadenza": scadenza.isoformat(),
                    "giorni_mancanti": giorni_mancanti
                })
        except Exception:
            continue

    # Sort by date (closest first)
    scadenze.sort(key=lambda x: x["giorni_mancanti"])

    return {
        "scadenze": scadenze[:limit],
        "totale": len(scadenze),
        "totale_importo": totale_importo
    }


@router.post("/upload")
@handle_errors
async def upload_f24_pdf(
    file: UploadFile = File(..., description="File PDF F24")
) -> Dict[str, Any]:
    """Carica un PDF F24: stesso ingresso di Documenti > Import, Drive e posta.

    Un PDF gia' in archivio risponde 409; uno che non quadra o senza righe
    tributo 422 col motivo, senza scrivere niente.
    """
    esito = await _importa(file, source="f24_public_upload")
    if esito.get("duplicate"):
        raise HTTPException(status_code=409, detail="F24 già presente nel sistema")
    return {**esito, "action": "creato"}


async def _importa(file: UploadFile, *, source: str) -> Dict[str, Any]:
    from app.services.f24_canonico import importa_modello_bytes

    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Solo file PDF supportati")
    pdf_bytes = await file.read()
    db = Database.get_db()
    esito = await importa_modello_bytes(db, pdf_bytes, file.filename, source=source)
    if not esito.get("success"):
        raise HTTPException(status_code=422, detail=esito.get("error") or "Parsing F24 fallito")
    modello = await db[F24_COLLECTION].find_one(
        {"id": esito["f24_id"]},
        {"_id": 0, "dati_generali": 1, "totali": 1, "sezione_erario": 1, "sezione_inps": 1,
         "sezione_inail": 1, "sezione_regioni": 1, "sezione_tributi_locali": 1},
    ) or {}
    dati = modello.get("dati_generali") or {}
    totali = modello.get("totali") or {}
    return {
        "success": True,
        "id": esito["f24_id"],
        "duplicate": bool(esito.get("duplicate")),
        "scadenza": dati.get("data_versamento"),
        "contribuente": dati.get("ragione_sociale"),
        "saldo_finale": totali.get("saldo_netto", totali.get("saldo_finale", 0)),
        "tributi": {
            "erario": len(modello.get("sezione_erario") or []),
            "inps": len(modello.get("sezione_inps") or []) + len(modello.get("sezione_inail") or []),
            "regioni": len(modello.get("sezione_regioni") or []),
            "imu": len(modello.get("sezione_tributi_locali") or []),
        },
        "filename": file.filename,
    }


@router.get("/pdf/{f24_id}")
async def get_f24_pdf(f24_id: str):
    """Alias: l'originale si apre da `/api/originale/f24/{id}` (DRV-04)."""
    from app.routers.originale import reindirizza_a_originale

    return reindirizza_a_originale("f24", f24_id)


@router.put("/models/{f24_id}/pagato")
@handle_errors
async def mark_f24_pagato(f24_id: str) -> Dict[str, str]:
    """Registra la dichiarazione manuale; la banca resta da verificare."""
    db = Database.get_db()

    result = await db[F24_COLLECTION].update_one(
        {"id": f24_id},
        {"$set": {
            "status": "da_pagare",
            "stato_pagamento": "DA_VERIFICARE_BANCA",
            "pagato": False,
            "pagato_manualmente": True,
            "pagamento_dichiarato_manualmente": True,
            "pagamento_verificato_banca": False,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="F24 non trovato")

    return {
        "message": "Pagamento dichiarato; resta da verificare sul movimento bancario",
        "id": f24_id,
    }


@router.put("/models/{f24_id}")
@handle_errors
async def update_f24_model(f24_id: str, data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Aggiorna un modello F24."""
    db = Database.get_db()

    update_data = {"updated_at": datetime.now(timezone.utc).isoformat()}

    # Campi modificabili (mappo al nuovo schema)
    if "data_scadenza" in data:
        update_data["dati_generali.data_scadenza"] = data["data_scadenza"]
    if "contribuente" in data:
        update_data["dati_generali.ragione_sociale"] = data["contribuente"]
    if "pagato" in data:
        update_data["status"] = "da_pagare"
        update_data["pagato"] = False
        update_data["pagamento_verificato_banca"] = False
        update_data["pagamento_dichiarato_manualmente"] = bool(data["pagato"])
        update_data["pagato_manualmente"] = bool(data["pagato"])
        update_data["stato_pagamento"] = (
            "DA_VERIFICARE_BANCA" if data["pagato"] else "DA_PAGARE"
        )
    if "note" in data:
        update_data["note"] = data["note"]
    if "saldo_finale" in data:
        update_data["totali.saldo_netto"] = data["saldo_finale"]

    result = await db[F24_COLLECTION].update_one(
        {"id": f24_id},
        {"$set": update_data}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="F24 non trovato")

    return {"message": "F24 aggiornato", "id": f24_id}


@router.delete("/models/{f24_id}")
@handle_errors
async def delete_f24_model(f24_id: str) -> Dict[str, str]:
    """Elimina un modello F24 (soft delete)."""
    db = Database.get_db()

    # Soft delete invece di hard delete
    result = await db[F24_COLLECTION].update_one(
        {"id": f24_id},
        {"$set": {"status": "eliminato", "eliminato_at": datetime.now(timezone.utc).isoformat()}}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="F24 non trovato")

    return {"message": "F24 eliminato", "id": f24_id}


@router.post("/upload-overwrite")
@handle_errors
async def upload_f24_pdf_overwrite(
    file: UploadFile = File(..., description="File PDF F24"),
    overwrite: bool = Query(False, description="Rileggi sul posto se il PDF è già in archivio")
) -> Dict[str, Any]:
    """Carica un PDF F24 rileggendolo sul posto se e' gia' in archivio.

    L'ingresso unico riconosce lo stesso PDF dalla sua impronta e ne rinfresca
    le righe lette senza creare un secondo modello ne' toccare la provenienza:
    con `overwrite=False` un PDF gia' presente si ferma prima, come `/upload`.
    """
    if not overwrite:
        esito = await _importa(file, source="f24_public_overwrite")
        if esito.get("duplicate"):
            return {"success": False, "error": "F24 già presente. Usa overwrite=True per rileggerlo.",
                    "existing_id": esito.get("id"), "filename": file.filename}
        return {**esito, "action": "creato"}
    esito = await _importa(file, source="f24_public_overwrite")
    return {**esito, "action": "aggiornato" if esito.get("duplicate") else "creato"}
