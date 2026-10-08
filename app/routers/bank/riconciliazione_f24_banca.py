"""
Router per Riconciliazione F24 con Estratto Conto Bancario
Supporta formato Banco BPM

NOTA: Questo router è registrato con prefix /api/f24-riconciliazione
insieme a f24_riconciliazione.py per gli endpoint banca-specifici.
"""
from fastapi import APIRouter, Body, Depends, UploadFile, File, HTTPException
from typing import Any, Dict, Optional
from datetime import datetime, timezone
from uuid import uuid4
import logging

from app.database import Database
from app.db_collections import (
    COLL_ESTRATTO_CONTO,
    QUERY_F24_PATTERN
)
from app.middleware.error_handler import risposta_errore
from app.utils.dependencies import get_current_admin_user

from app.services.estratto_conto_bpm_parser import parse_estratto_conto_bpm

# NON importare COLL_F24_COMMERCIALISTA da db_collections: lì l'alias punta
# a "f24_unificato" (retrocompatibilità con un'altra pipeline F24), ma il
# flusso "F24 commercialista → Quietanza → Banca" che questo router
# completa lavora sulla stessa collection di f24_riconciliazione.py ed
# email_f24.py: "f24_commercialista". Prima questo file leggeva/scriveva
# silenziosamente un archivio diverso da quello popolato dall'upload F24
# commercialista, quindi la riconciliazione con l'estratto conto non
# trovava mai nulla (bug #6 audit memoria/endpoints/README.md).
COLL_F24_COMMERCIALISTA = "f24_unificato"  # unificato 13/07/2026

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/upload-estratto-bpm")
async def upload_estratto_conto_bpm(file: UploadFile = File(...)):
    """
    Carica e parsa un estratto conto Banco BPM (formato CSV).
    Identifica automaticamente i pagamenti F24.
    """
    if not file.filename.endswith(('.csv', '.CSV')):
        raise HTTPException(status_code=400, detail="Il file deve essere in formato CSV")
    
    try:
        content = await file.read()
        # Prova diverse codifiche
        for encoding in ['utf-8', 'latin-1', 'cp1252']:
            try:
                text_content = content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise HTTPException(status_code=400, detail="Impossibile decodificare il file")
        
        # Parsa estratto conto
        result = parse_estratto_conto_bpm(text_content)
        
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        
        # Salva nel database
        db = Database.get_db()
        documento = {
            "file_name": file.filename,
            "upload_date": datetime.now(timezone.utc),
            "banca": "BANCO BPM",
            "formato": "CSV",
            "conto": result.get("conto", {}),
            "periodo": result.get("periodo", {}),
            "totale_movimenti": result["stats"]["totale_movimenti"],
            "totale_movimenti_f24": result["stats"]["movimenti_f24"],
            "totale_entrate": result["totale_entrate"],
            "totale_uscite": result["totale_uscite"],
            "saldo": result["saldo"],
            "categorie": result["stats"]["categorie"]
        }
        
        await db["estratti_conto"].insert_one(documento.copy())

        # Salva i movimenti F24 nella collezione CANONICA estratto_conto_movimenti
        # (quella letta da /riconcilia-f24), non nella morta movimenti_f24_banca:
        # prima l'import scriveva su movimenti_f24_banca ma la riconciliazione
        # leggeva estratto_conto_movimenti → i movimenti non venivano mai trovati.
        # Vedi P0.7. Dedup per fingerprint per non duplicare se l'estratto è già
        # stato importato dall'importer principale.
        f24_importati = 0
        for mov in result["movimenti_f24"]:
            data_mov = mov.get("data_contabile") or mov.get("data_valuta")
            descr = mov.get("descrizione", "")
            importo = mov.get("importo")
            # Dedup per CHIAVE NATURALE (data + importo assoluto + descrizione):
            # l'importer canonico usa un fingerprint con uuid random, quindi non
            # posso riusare quel campo per il dedup cross-import. Controllo invece
            # se il movimento è già presente per i suoi dati reali, così non
            # duplico ciò che l'importer principale ha già inserito. Vedi P0.7.
            try:
                importo_abs = round(abs(float(importo or 0)), 2)
            except (TypeError, ValueError):
                importo_abs = 0.0
            esiste = await db[COLL_ESTRATTO_CONTO].find_one({
                "data": data_mov,
                "descrizione": descr,
                "$expr": {"$eq": [{"$abs": {"$toDouble": {"$ifNull": ["$importo", 0]}}}, importo_abs]},
            }, {"_id": 1})
            if esiste:
                continue
            record = {
                "id": str(uuid4()),
                "data": data_mov,
                "data_valuta": mov.get("data_valuta"),
                "importo": importo,
                "tipo": mov.get("tipo", "uscita"),
                "descrizione": descr,
                "categoria": mov.get("categoria", "F24"),
                "banca": mov.get("banca", "BPM"),
                "is_f24": True,
                "f24_info": mov.get("f24_info"),
                "source": "estratto_bpm_f24",
                "estratto_file": file.filename,
                "riconciliato": False,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await db[COLL_ESTRATTO_CONTO].insert_one(record.copy())
            f24_importati += 1
        
        return {
            "success": True,
            "message": f"Estratto conto caricato: {result['stats']['totale_movimenti']} movimenti",
            "file_name": file.filename,
            "periodo": result["periodo"],
            "conto": result["conto"],
            "stats": {
                "totale_movimenti": result["stats"]["totale_movimenti"],
                "movimenti_f24": result["stats"]["movimenti_f24"],
                "totale_entrate": result["totale_entrate"],
                "totale_uscite": result["totale_uscite"],
                "saldo": result["saldo"]
            },
            "categorie_principali": dict(sorted(
                result["stats"]["categorie"].items(),
                key=lambda x: x[1],
                reverse=True
            )[:10])
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore upload estratto conto: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/movimenti-f24-banca")
async def get_movimenti_f24_banca(
    data_da: Optional[str] = None,
    data_a: Optional[str] = None,
    limit: int = 100
):
    """
    Recupera i movimenti F24 identificati negli estratti conto.
    Cerca nella collezione estratto_conto_movimenti i movimenti con pattern F24
    (I24 AGENZIA ENTRATE, AGENZIA DELLE ENTRATE, etc.)
    """
    db = Database.get_db()
    
    # Usa query pattern centralizzata
    query = QUERY_F24_PATTERN.copy()
    
    # Filtri opzionali per data
    if data_da or data_a:
        date_filter = {}
        if data_da:
            date_filter["$gte"] = data_da
        if data_a:
            date_filter["$lte"] = data_a
        query["data"] = date_filter
    
    movimenti = await db[COLL_ESTRATTO_CONTO].find(
        query,
        {"_id": 0}
    ).sort("data", -1).limit(limit).to_list(limit)
    
    # Calcola totale (in valore assoluto perché sono uscite negative)
    totale = sum(abs(m.get("importo", 0)) for m in movimenti)
    
    return {
        "movimenti": movimenti,
        "count": len(movimenti),
        "totale": round(totale, 2)
    }


@router.get("/quietanze-banca")
async def quietanze_banca(anno: Optional[int] = None):
    """Quietanze F24 ↔ addebiti I24: riscontri, da verificare, orfani.

    Solo lettura: calcola sul momento con lo stesso motore del giro dei 30
    minuti (`f24_controllo_incrociato.riconcilia_f24_banca`), che e'
    l'unico a scrivere. Ogni riga porta la motivazione del suo esito.
    """
    from app.services.f24_controllo_incrociato import (
        LIVELLI_CONFERMABILI, MOTIVI_CONFERMA_TITOLARE, riconcilia_f24_banca,
    )

    esito = await riconcilia_f24_banca(Database.get_db(), dry_run=True)
    esito["modelli_da_verificare"] = esito["modelli"]["da_verificare"]
    # La tendina dei motivi della conferma: una fonte sola, il motore.
    esito["conferma"] = {"livelli": list(LIVELLI_CONFERMABILI), "motivi": dict(MOTIVI_CONFERMA_TITOLARE)}
    if anno:
        prefisso = str(int(anno))
        for chiave in ("riscontrati", "da_verificare", "quietanze_senza_addebito",
                       "quietanze_senza_estratto", "modelli_da_verificare",
                       "addebiti_senza_quietanza", "quietanze_incomplete", "tributi_ripetuti",
                       "compensate_saldo_zero"):
            esito[chiave] = [r for r in esito.get(chiave, []) if str(r.get("data") or "").startswith(prefisso)]
        esito["anno"] = int(anno)
    return esito


@router.post("/quietanze-banca/{f24_id}/conferma")
async def conferma_quietanza_banca(
    f24_id: str,
    body: Dict[str, Any] = Body(...),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
):
    """Il titolare conferma un addebito PROBABILE o PARZIALE per un F24 (modello o quietanza).

    Body: `{"movimento_id": "...", "motivo": "<chiave di MOTIVI_CONFERMA_TITOLARE>",
    "motivo_testo": "..." (solo per «altro»)}`. Scrive con lo stesso motore del
    CERTO (`conferma_riscontro_titolare`): pagamento sul modello, relazione
    `confirmed` con `actor=titolare` e motivo, differenza registrata per il
    PARZIALE. Un movimento non candidato e' 409; un motivo fuori elenco 422.
    """
    import uuid as _uuid

    from app.services.f24_controllo_incrociato import ConfermaNonAmmessa, conferma_riscontro_titolare

    movimento_id = str(body.get("movimento_id") or "").strip()
    if not movimento_id:
        return risposta_errore(422, message="movimento_id obbligatorio", detail="movimento_id obbligatorio",
                               code="MOVIMENTO_OBBLIGATORIO", correlation_id=_uuid.uuid4().hex[:12])
    try:
        return await conferma_riscontro_titolare(
            Database.get_db(), f24_id=f24_id, movimento_id=movimento_id,
            motivo=str(body.get("motivo") or ""), motivo_testo=body.get("motivo_testo"),
            actor="titolare", utente=str(_admin.get("email") or _admin.get("user_id") or ""),
        )
    except ConfermaNonAmmessa as exc:
        cid = _uuid.uuid4().hex[:12]
        logger.warning("[%s] conferma F24 %s con %s rifiutata: %s", cid, f24_id, movimento_id, exc.code)
        return risposta_errore(exc.stato, message=exc.message, detail=exc.message, details=exc.details,
                               code=exc.code, correlation_id=cid)


@router.get("/modello/{f24_id}/quietanze-candidate")
async def quietanze_candidate_modello(
    f24_id: str, _admin: Dict[str, Any] = Depends(get_current_admin_user),
):
    """Quietanze che pagano righe del modello per stesso codice e periodo, anche con importo diverso.

    Sola lettura (`f24_proposte_quietanza.proponi_quietanze`): per ogni candidata le righe in comune
    con la differenza di importo, le righe non trovate e il link all'originale; niente si collega da solo.
    """
    import uuid as _uuid

    from app.services.f24_proposte_quietanza import CollegamentoNonAmmesso, proposte_per_modello

    try:
        return await proposte_per_modello(Database.get_db(), f24_id)
    except CollegamentoNonAmmesso as exc:
        return risposta_errore(exc.stato, message=exc.message, detail=exc.message, details=exc.details,
                               code=exc.code, correlation_id=_uuid.uuid4().hex[:12])


@router.post("/modello/{f24_id}/quietanze-candidate/conferma")
async def conferma_quietanza_candidata(
    f24_id: str,
    body: Dict[str, Any] = Body(...),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
):
    """Il titolare collega il modello alla quietanza scelta fra le candidate per codice e periodo.

    Body: `{"quietanza_id": "...", "motivo": "<chiave di MOTIVI_COLLEGAMENTO>", "motivo_testo": "..." (solo «altro»)}`.
    Una quietanza non candidata e' 409, un motivo fuori elenco 422. Non prova la banca.
    """
    import uuid as _uuid

    from app.services.f24_proposte_quietanza import CollegamentoNonAmmesso, conferma_collegamento_quietanza

    quietanza_id = str(body.get("quietanza_id") or "").strip()
    cid = _uuid.uuid4().hex[:12]
    if not quietanza_id:
        return risposta_errore(422, message="quietanza_id obbligatorio", detail="quietanza_id obbligatorio",
                               code="QUIETANZA_OBBLIGATORIA", correlation_id=cid)
    try:
        return await conferma_collegamento_quietanza(
            Database.get_db(), f24_id=f24_id, quietanza_id=quietanza_id,
            motivo=str(body.get("motivo") or ""), motivo_testo=body.get("motivo_testo"),
            utente=str(_admin.get("email") or _admin.get("user_id") or ""),
        )
    except CollegamentoNonAmmesso as exc:
        logger.warning("[%s] collegamento F24 %s con quietanza %s rifiutato: %s", cid, f24_id, quietanza_id, exc.code)
        return risposta_errore(exc.stato, message=exc.message, detail=exc.message, details=exc.details,
                               code=exc.code, correlation_id=cid)


@router.get("/stato-riconciliazione")
async def get_stato_riconciliazione():
    """
    Restituisce lo stato attuale della riconciliazione F24.
    """
    db = Database.get_db()
    
    # Conta F24 per stato
    f24_pagati = await db[COLL_F24_COMMERCIALISTA].count_documents({"stato_pagamento": "PAGATO"})
    f24_da_pagare = await db[COLL_F24_COMMERCIALISTA].count_documents({"stato_pagamento": "DA_PAGARE"})
    f24_totali = await db[COLL_F24_COMMERCIALISTA].count_documents({})
    
    # Conta movimenti F24 in banca
    movimenti_f24 = await db[COLL_ESTRATTO_CONTO].count_documents(QUERY_F24_PATTERN)
    
    # Somma importi
    pipeline_f24 = [
        {"$group": {
            "_id": "$stato_pagamento",
            "totale": {"$sum": "$totali.saldo_netto"}
        }}
    ]
    totali_per_stato = {doc["_id"]: doc["totale"] async for doc in db[COLL_F24_COMMERCIALISTA].aggregate(pipeline_f24)}
    
    # Totale movimenti F24 in banca
    pipeline_banca = [
        {"$match": QUERY_F24_PATTERN},
        {"$group": {
            "_id": None,
            "totale": {"$sum": {"$abs": "$importo"}}
        }}
    ]
    totale_banca = 0
    async for doc in db[COLL_ESTRATTO_CONTO].aggregate(pipeline_banca):
        totale_banca = doc.get("totale", 0)
    
    return {
        "f24": {
            "totali": f24_totali,
            "pagati": f24_pagati,
            "da_pagare": f24_da_pagare,
            "non_classificati": f24_totali - f24_pagati - f24_da_pagare
        },
        "importi": {
            "totale_f24_pagati": round(totali_per_stato.get("PAGATO", 0), 2),
            "totale_f24_da_pagare": round(totali_per_stato.get("DA_PAGARE", 0), 2),
            "totale_movimenti_banca": round(totale_banca, 2)
        },
        "movimenti_f24_banca": movimenti_f24,
        "percentuale_riconciliazione": round(f24_pagati / max(f24_totali, 1) * 100, 1)
    }


@router.get("/estratti-conto")
async def get_estratti_conto():
    """
    Lista degli estratti conto caricati.
    """
    db = Database.get_db()
    
    estratti = await db["estratti_conto"].find(
        {},
        {"_id": 0}
    ).sort("upload_date", -1).to_list(100)
    
    return {
        "estratti": estratti,
        "count": len(estratti)
    }
