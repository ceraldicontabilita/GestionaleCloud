"""
Buste Paga API - Upload e parsing PDF Libro Unico del Lavoro.

Permette di:
- Caricare PDF buste paga (formato Zucchetti)
- Estrarre automaticamente stipendi e presenze
- Salvare i dati nel database dipendenti
"""
from fastapi import APIRouter, Body, File, HTTPException, Query, UploadFile
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
import logging

from app.hr.database import Database
from app.hr.services.libro_unico_parser import parse_libro_unico_pdf, ParsingError
from app.hr.utils.error_handler import handle_errors

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/buste-paga", tags=["Buste Paga"])


@router.post("/upload")
@handle_errors
async def upload_busta_paga(
    file: UploadFile = File(...),
    competenza_month: Optional[str] = Query(None, description="Mese competenza YYYY-MM (opzionale, auto-detect)")
):
    """
    Carica e parsifica un PDF di busta paga (Libro Unico).
    
    Il sistema rileva automaticamente:
    - Mese di competenza (con confidenza alta/bassa)
    - Tipo busta paga (dipendente/amministratore/tirocinante)
    - Stipendi (netto, acconto, differenza)
    - Presenze (ore ordinarie)
    - Dati contratto (mansione, scadenza)
    
    Args:
        file: File PDF da caricare
        competenza_month: Mese competenza manuale (formato YYYY-MM), se non specificato viene auto-rilevato
    
    Returns:
        Dati estratti dal PDF
    """
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Il file deve essere un PDF")
    
    try:
        # Leggi contenuto PDF
        pdf_bytes = await file.read()
        
        if len(pdf_bytes) == 0:
            raise HTTPException(status_code=400, detail="File PDF vuoto")
        
        logger.info(f"📄 Parsing busta paga: {file.filename} ({len(pdf_bytes)} bytes)")
        
        # Parsifica PDF
        result = parse_libro_unico_pdf(pdf_bytes)
        
        # Override mese competenza se specificato manualmente
        if competenza_month:
            result['competenza_month_year'] = competenza_month
            result['competenza_detected'] = True
            result['competenza_manual'] = True
        
        # Aggiungi metadata
        result['filename'] = file.filename
        result['uploaded_at'] = datetime.now(timezone.utc).isoformat()
        result['pdf_size_bytes'] = len(pdf_bytes)
        
        return {
            "success": True,
            "message": f"Estratti {len(result.get('salaries', []))} dipendenti",
            "data": result
        }
        
    except ParsingError as e:
        logger.error(f"Parsing error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error processing PDF: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Errore elaborazione PDF: {str(e)}")


@router.post("/salva")
@handle_errors
async def salva_buste_paga(
    competenza_month: str,
    salaries: List[Dict[str, Any]],
    presenze: Optional[List[Dict[str, Any]]] = None
):
    """
    Salva i dati delle buste paga nel database.
    
    Args:
        competenza_month: Mese competenza (YYYY-MM)
        salaries: Lista stipendi estratti
        presenze: Lista presenze estratte (opzionale)
    """
    try:
        db = Database.get_db()
        
        # Crea record per ogni dipendente
        saved_count = 0
        for salary in salaries:
            nome = salary.get('nome', '')
            if not nome:
                continue
            
            # Trova presenze corrispondenti
            presenza = None
            if presenze:
                presenza = next((p for p in presenze if p.get('nome') == nome), None)
            
            # Documento da salvare
            doc = {
                "competenza": competenza_month,
                "nome": nome,
                "netto": salary.get('netto', 0),
                "acconto": salary.get('acconto', 0),
                "differenza": salary.get('differenza', 0),
                "note": salary.get('note', ''),
                "ore_ordinarie": presenza.get('ore_ordinarie', 0) if presenza else 0,
                "ferie": presenza.get('ferie', 0) if presenza else 0,
                "permessi": presenza.get('permessi', 0) if presenza else 0,
                "malattia": presenza.get('malattia', 0) if presenza else 0,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            
            # Upsert per evitare duplicati
            await db.buste_paga.update_one(
                {"competenza": competenza_month, "nome": nome},
                {"$set": doc},
                upsert=True
            )
            saved_count += 1
        
        return {
            "success": True,
            "message": f"Salvate {saved_count} buste paga per {competenza_month}",
            "saved_count": saved_count
        }
        
    except Exception as e:
        logger.error(f"Error saving buste paga: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/lista")
@handle_errors
async def lista_buste_paga(
    competenza: Optional[str] = None,
    nome: Optional[str] = None,
    limit: int = Query(100, le=500)
):
    """
    Ottieni lista buste paga salvate.
    
    Args:
        competenza: Filtro per mese competenza (YYYY-MM)
        nome: Filtro per nome dipendente
        limit: Limite risultati
    """
    try:
        db = Database.get_db()
        
        query = {}
        if competenza:
            query["competenza"] = competenza
        if nome:
            query["nome"] = {"$regex": nome, "$options": "i"}
        
        buste = await db.buste_paga.find(query, {"_id": 0}).sort("competenza", -1).limit(limit).to_list(length=limit)
        
        return {"buste_paga": buste, "count": len(buste)}
        
    except Exception as e:
        logger.error(f"Error fetching buste paga: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/riepilogo-mensile/{competenza}")
@handle_errors
async def riepilogo_mensile(competenza: str):
    """Ottieni riepilogo mensile buste paga.

    Sorgenti dati (unificate in un'unica lista buste):
    1. Documenti in `buste_paga` con competenza=YYYY-MM (import manuale)
    2. Documenti in `cedolini` con anno=YYYY, mese=MM (cedolini parsati PDF)

    Per ogni dipendente calcola anche gli acconti erogati nello stesso
    mese dalla collezione `acconti_dipendenti`, permettendo alla UI di
    mostrare la differenza (netto - acconti) come "da pagare".

    Args:
        competenza: Mese competenza in formato YYYY-MM
    """
    try:
        # Validazione formato
        import re
        if not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", competenza):
            raise HTTPException(
                status_code=400,
                detail="Competenza deve essere in formato YYYY-MM (es. 2026-04)",
            )
        anno, mese = competenza.split("-")
        anno_int = int(anno)
        mese_int = int(mese)

        db = Database.get_db()

        # 1) Buste paga da import manuale (se presenti)
        buste_manuali = await db.buste_paga.find(
            {"competenza": competenza}, {"_id": 0}
        ).to_list(length=None)

        # 2) Cedolini parsati dal PDF (bacino principale)
        cedolini_docs = await db.cedolini.find(
            {"anno": anno_int, "mese": mese_int},
            {"_id": 0, "pdf_data": 0},
        ).to_list(length=None)

        # 3) Acconti erogati nel mese — per dipendente
        acconti_mese = await db.acconti_dipendenti.find(
            {"anno": anno_int, "mese": mese_int},
            {"_id": 0, "dipendente_id": 1, "dipendente_nome": 1, "importo": 1},
        ).to_list(length=None)

        # Aggrega acconti per dipendente_id e per nome (fallback)
        acconti_by_id: Dict[str, float] = {}
        acconti_by_nome: Dict[str, float] = {}
        for a in acconti_mese:
            imp = float(a.get("importo") or 0)
            dip_id = a.get("dipendente_id")
            dip_nome = (a.get("dipendente_nome") or "").strip().lower()
            if dip_id:
                acconti_by_id[dip_id] = acconti_by_id.get(dip_id, 0) + imp
            if dip_nome:
                acconti_by_nome[dip_nome] = acconti_by_nome.get(dip_nome, 0) + imp

        # Unifica le fonti in un'unica lista "buste" normalizzata
        buste: List[Dict[str, Any]] = []

        # Dalla collezione buste_paga
        for b in buste_manuali:
            buste.append(
                {
                    "nome": b.get("nome") or b.get("dipendente_nome") or "",
                    "dipendente_id": b.get("dipendente_id") or b.get("employee_id"),
                    "competenza": competenza,
                    "ore_ordinarie": float(b.get("ore_ordinarie") or 0),
                    "netto": float(b.get("netto") or 0),
                    "acconto": float(b.get("acconto") or 0),
                    "differenza": float(b.get("differenza") or 0),
                    "fonte": "buste_paga",
                }
            )

        # Dai cedolini parsati (dedupe rispetto a buste_manuali tramite chiave nome+competenza)
        chiavi_manuali = {
            (b.get("nome", "").strip().lower(), competenza) for b in buste_manuali
        }
        for c in cedolini_docs:
            nome = (
                c.get("dipendente_nome")
                or c.get("nome_dipendente")
                or ""
            ).strip()
            if (nome.lower(), competenza) in chiavi_manuali:
                continue  # già contato da buste_manuali
            emp_id = c.get("employee_id") or c.get("dipendente_id")
            netto = float(c.get("netto") or 0)

            # Cerca acconto: prima per id, poi per nome
            acconto = 0.0
            if emp_id and emp_id in acconti_by_id:
                acconto = acconti_by_id[emp_id]
            elif nome and nome.lower() in acconti_by_nome:
                acconto = acconti_by_nome[nome.lower()]

            buste.append(
                {
                    "nome": nome,
                    "dipendente_id": emp_id,
                    "competenza": competenza,
                    "ore_ordinarie": float(
                        c.get("ore_ordinarie") or c.get("ore_lavorate") or 0
                    ),
                    "netto": netto,
                    "acconto": round(acconto, 2),
                    "differenza": round(netto - acconto, 2),
                    "fonte": "cedolini",
                }
            )

        # Totali
        totale_netto = sum(b["netto"] for b in buste)
        totale_acconti = sum(b["acconto"] for b in buste)
        totale_differenza = sum(b["differenza"] for b in buste)
        totale_ore = sum(b["ore_ordinarie"] for b in buste)

        # Ordinamento stabile per cognome
        buste.sort(key=lambda x: (x.get("nome") or "").lower())

        return {
            "competenza": competenza,
            "dipendenti": len(buste),
            "totale_netto": round(totale_netto, 2),
            "totale_acconti": round(totale_acconti, 2),
            "totale_differenza": round(totale_differenza, 2),
            "totale_ore": round(totale_ore, 2),
            "buste": buste,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching riepilogo: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/competenze")
@handle_errors
async def lista_competenze():
    """Ottieni lista di tutti i mesi di competenza disponibili.

    Legge sia dalla collezione `buste_paga` (import manuale) sia da `cedolini`
    (cedolini parsati da PDF), deduplicando e ordinando dal più recente.
    La collezione `buste_paga` usa il campo stringa `competenza: "YYYY-MM"`,
    mentre `cedolini` usa due campi numerici separati `anno` e `mese` — li
    trasformiamo entrambi nello stesso formato stringa.
    """
    try:
        db = Database.get_db()
        competenze_set = set()

        # Dalla collezione buste_paga (se presente)
        for c in await db.buste_paga.distinct("competenza"):
            if isinstance(c, str) and len(c) >= 7:
                competenze_set.add(c[:7])

        # Dalla collezione cedolini (bacino principale)
        pipeline = [
            {"$match": {"anno": {"$exists": True}, "mese": {"$exists": True}}},
            {"$group": {"_id": {"anno": "$anno", "mese": "$mese"}}},
        ]
        async for row in db.cedolini.aggregate(pipeline):
            anno = row["_id"].get("anno")
            mese = row["_id"].get("mese")
            try:
                anno_int = int(anno)
                mese_int = int(mese)
                if 1900 <= anno_int <= 2100 and 1 <= mese_int <= 12:
                    competenze_set.add(f"{anno_int:04d}-{mese_int:02d}")
            except (TypeError, ValueError):
                continue

        competenze = sorted(competenze_set, reverse=True)
        return {"competenze": competenze}
    except Exception as e:
        logger.error(f"Error fetching competenze: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{competenza}/{nome}")
@handle_errors
async def elimina_busta_paga(competenza: str, nome: str):
    """Elimina una busta paga specifica."""
    try:
        db = Database.get_db()
        result = await db.buste_paga.delete_one({"competenza": competenza, "nome": nome})
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Busta paga non trovata")
        
        return {"success": True, "message": f"Busta paga di {nome} per {competenza} eliminata"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting busta paga: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))