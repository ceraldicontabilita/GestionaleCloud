"""
Cedolini Riconciliazione Router
Gestisce la riconciliazione pagamenti cedolini con bonifici/assegni.
"""
from fastapi import APIRouter, HTTPException, UploadFile, File, Body, Query
from typing import Dict, Any, Optional
from datetime import datetime, timezone
import uuid
import logging
import io

from app.database import Database
from app.utils.error_handler import handle_errors

logger = logging.getLogger(__name__)
router = APIRouter()

COLLECTION_CEDOLINI = "cedolini"
COLLECTION_BONIFICI = "archivio_bonifici"
COLLECTION_ASSEGNI = "assegni"


def clean_doc(doc: Dict) -> Dict:
    """Rimuove _id da documento MongoDB."""
    if doc and "_id" in doc:
        doc.pop("_id", None)
    return doc


@router.get("/lista-completa")
@handle_errors
async def lista_cedolini_completa(
    anno: Optional[int] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(1000, ge=1, le=5000)
) -> Dict[str, Any]:
    """
    Lista tutti i cedolini con stato pagamento.
    """
    db = Database.get_db()
    
    query = {}
    if anno:
        query["anno"] = {"$in": [anno, str(anno)]}
    
    cedolini = await db[COLLECTION_CEDOLINI].find(query, {"_id": 0}).sort([("anno", -1), ("mese", -1)]).skip(skip).limit(limit).to_list(limit)
    
    return {"cedolini": cedolini, "count": len(cedolini)}


@router.post("/{cedolino_id}/registra-pagamento")
@handle_errors
async def registra_pagamento_cedolino(
    cedolino_id: str,
    data: Dict[str, Any] = Body(...)
) -> Dict[str, Any]:
    """
    Registra pagamento manuale di un cedolino.
    Crea movimento in Prima Nota (cassa o banca).
    """
    db = Database.get_db()
    
    # Trova cedolino
    cedolino = await db[COLLECTION_CEDOLINI].find_one({"id": cedolino_id})
    if not cedolino:
        raise HTTPException(status_code=404, detail="Cedolino non trovato")
    
    importo = float(data.get("importo_pagato", 0))
    metodo = data.get("metodo_pagamento", "bonifico")
    data_pag = data.get("data_pagamento", datetime.now(timezone.utc).isoformat()[:10])
    note = data.get("note", "")
    
    if importo <= 0:
        raise HTTPException(status_code=400, detail="Importo deve essere > 0")
    
    # === VALIDATORE P0: Salari post luglio 2018 NON possono essere pagati in contanti (PRD sezione validatori P0) ===
    # Legge 205/2017 art. 1 comma 910: dal 1 luglio 2018 vietato pagare stipendi in contanti
    anno_cedolino = int(cedolino.get("anno", 0))
    mese_cedolino = int(cedolino.get("mese", 0))
    
    if metodo.lower() in ["contanti", "cassa", "cash", "contante"]:
        # Dal 1 luglio 2018 vietato pagare stipendi in contanti (L.205/2017 art.1 c.910)
        # Pre luglio 2018 (fino a giugno incluso) = contanti OK
        # Dal luglio 2018 in poi = contanti VIETATI
        if anno_cedolino > 2018 or (anno_cedolino == 2018 and mese_cedolino >= 7):
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "SALARIO_CONTANTI_VIETATO",
                    "message": f"Pagamento in contanti vietato dal 1 luglio 2018 (L.205/2017). Cedolino: {cedolino.get('nome_dipendente', '')} - {mese_cedolino}/{anno_cedolino}",
                    "cedolino_id": cedolino_id,
                    "azione_richiesta": "Utilizzare bonifico bancario o altro metodo tracciabile"
                }
            )
    
    # Aggiorna cedolino
    update = {
        "pagato": True,
        "importo_pagato": importo,
        "metodo_pagamento": metodo,
        "data_pagamento": data_pag,
        "note_pagamento": note,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db[COLLECTION_CEDOLINI].update_one({"id": cedolino_id}, {"$set": update})
    
    # Crea movimento Prima Nota
    nome_dip = cedolino.get("nome_dipendente") or cedolino.get("nome_completo") or "Dipendente"
    periodo = cedolino.get("periodo") or f"{cedolino.get('mese', '')}/{cedolino.get('anno', '')}"
    
    movimento = {
        "id": str(uuid.uuid4()),
        "data": data_pag,
        "tipo": "uscita",
        "importo": importo,
        "descrizione": f"Stipendio {nome_dip} - {periodo}",
        "categoria": "Stipendi",
        "riferimento": f"CED_{cedolino_id[:8]}",
        "cedolino_id": cedolino_id,
        "dipendente_id": cedolino.get("dipendente_id"),
        "codice_fiscale": cedolino.get("codice_fiscale"),
        "note": note,
        "source": "cedolino_pagamento",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    # Inserisci in cassa o banca
    if metodo == "contanti":
        await db["prima_nota_cassa"].insert_one(movimento.copy())
        movimento["_collection"] = "prima_nota_cassa"
    else:
        await db["prima_nota_banca"].insert_one(movimento.copy())
        movimento["_collection"] = "prima_nota_banca"
    
    logger.info(f"Pagamento cedolino {cedolino_id}: €{importo} via {metodo}")
    
    return {
        "success": True,
        "cedolino_id": cedolino_id,
        "movimento_id": movimento["id"],
        "collection": movimento["_collection"]
    }


@router.post("/riconcilia-automatica")
@handle_errors
async def riconcilia_cedolini_automatica(
    data: Dict[str, Any] = Body(...)
) -> Dict[str, Any]:
    """
    Riconcilia automaticamente cedolini non pagati con bonifici/assegni.
    
    Logica:
    1. Per ogni cedolino non pagato post-luglio 2018
    2. Cerca bonifici con:
       - Nome simile (fuzzy match)
       - Importo ±5€
       - Data nel mese successivo al periodo cedolino
    3. Se trovato, collega e marca come pagato
    """
    db = Database.get_db()
    anno = data.get("anno", datetime.now().year)
    
    # Cedolini non pagati dell'anno
    cedolini = await db[COLLECTION_CEDOLINI].find({
        "anno": {"$in": [anno, str(anno)]},
        "pagato": {"$ne": True}
    }, {"_id": 0}).to_list(1000)
    
    # Bonifici disponibili (non già collegati)
    bonifici = await db[COLLECTION_BONIFICI].find({
        "anno": {"$in": [anno, str(anno)]},
        "cedolino_id": {"$exists": False}
    }, {"_id": 0}).to_list(5000)
    
    # Assegni disponibili
    assegni = await db[COLLECTION_ASSEGNI].find({
        "data_emissione": {"$regex": f"^{anno}"},
        "cedolino_id": {"$exists": False}
    }, {"_id": 0}).to_list(2000)
    
    risultato = {
        "bonifici_match": 0,
        "assegni_match": 0,
        "da_verificare": 0,
        "dettagli": []
    }
    
    for ced in cedolini:
        nome_ced = (ced.get("nome_dipendente") or ced.get("nome_completo") or "").upper()
        netto = float(ced.get("netto") or ced.get("netto_mese") or 0)
        mese_ced = int(ced.get("mese") or 0)
        anno_ced = int(ced.get("anno") or 0)
        
        if not nome_ced or netto <= 0:
            continue
        
        # Cerca in bonifici
        match_bonifico = None
        for bon in bonifici:
            beneficiario = (bon.get("beneficiario") or bon.get("descrizione") or "").upper()
            importo_bon = float(bon.get("importo") or 0)
            
            # Match nome (contiene)
            nome_parts = nome_ced.split()
            nome_match = any(part in beneficiario for part in nome_parts if len(part) > 2)
            
            # Match importo (±5€)
            importo_match = abs(importo_bon - netto) <= 5
            
            if nome_match and importo_match:
                match_bonifico = bon
                break
        
        if match_bonifico:
            # Aggiorna cedolino
            await db[COLLECTION_CEDOLINI].update_one(
                {"id": ced["id"]},
                {"$set": {
                    "pagato": True,
                    "metodo_pagamento": "bonifico",
                    "bonifico_id": match_bonifico.get("id"),
                    "importo_pagato": float(match_bonifico.get("importo", netto)),
                    "data_pagamento": match_bonifico.get("data_valuta") or match_bonifico.get("data"),
                    "riconciliato_auto": True,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            # Marca bonifico come usato
            await db[COLLECTION_BONIFICI].update_one(
                {"id": match_bonifico["id"]},
                {"$set": {"cedolino_id": ced["id"]}}
            )
            risultato["bonifici_match"] += 1
            bonifici.remove(match_bonifico)
            continue
        
        # Cerca in assegni
        match_assegno = None
        for ass in assegni:
            beneficiario = (ass.get("beneficiario") or ass.get("intestatario") or "").upper()
            importo_ass = float(ass.get("importo") or 0)
            
            nome_parts = nome_ced.split()
            nome_match = any(part in beneficiario for part in nome_parts if len(part) > 2)
            importo_match = abs(importo_ass - netto) <= 5
            
            if nome_match and importo_match:
                match_assegno = ass
                break
        
        if match_assegno:
            await db[COLLECTION_CEDOLINI].update_one(
                {"id": ced["id"]},
                {"$set": {
                    "pagato": True,
                    "metodo_pagamento": "assegno",
                    "assegno_id": match_assegno.get("id"),
                    "importo_pagato": float(match_assegno.get("importo", netto)),
                    "data_pagamento": match_assegno.get("data_emissione"),
                    "riconciliato_auto": True,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            await db[COLLECTION_ASSEGNI].update_one(
                {"id": match_assegno["id"]},
                {"$set": {"cedolino_id": ced["id"]}}
            )
            risultato["assegni_match"] += 1
            assegni.remove(match_assegno)
            continue
        
        # Nessun match trovato
        risultato["da_verificare"] += 1
        risultato["dettagli"].append({
            "nome": nome_ced,
            "periodo": f"{mese_ced}/{anno_ced}",
            "netto": netto
        })
    
    return risultato


@router.post("/import-excel-storico")
@handle_errors
async def import_excel_storico(file: UploadFile = File(...)) -> Dict[str, Any]:
    """
    Import Excel con storico cedolini già pagati.
    
    Colonne attese:
    - Nome (o Nome Dipendente)
    - Mese
    - Anno
    - Netto (o Importo Netto)
    - Importo Pagato (opzionale, default = Netto)
    - Metodo (opzionale: contanti/bonifico/assegno, default = bonifico)
    """
    try:
        import pandas as pd
    except ImportError:
        raise HTTPException(status_code=500, detail="pandas non installato")
    
    content = await file.read()
    filename = (file.filename or "").lower()
    
    try:
        if filename.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(content))
        else:
            df = pd.read_excel(io.BytesIO(content))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Errore lettura file: {e}")
    
    # Normalizza nomi colonne
    df.columns = [c.lower().strip().replace(' ', '_') for c in df.columns]
    
    # Mappa colonne
    col_nome = next((c for c in df.columns if 'nome' in c), None)
    col_mese = next((c for c in df.columns if 'mese' in c), None)
    col_anno = next((c for c in df.columns if 'anno' in c), None)
    col_netto = next((c for c in df.columns if 'netto' in c or 'importo' in c), None)
    col_pagato = next((c for c in df.columns if 'pagato' in c), None)
    col_metodo = next((c for c in df.columns if 'metodo' in c), None)
    
    if not col_nome or not col_mese or not col_anno or not col_netto:
        raise HTTPException(status_code=400, detail="Colonne richieste: Nome, Mese, Anno, Netto/Importo")
    
    db = Database.get_db()
    risultato = {"imported": 0, "skipped_duplicates": 0, "errors": [], "failed": 0}
    
    # Mappa mesi testuali a numeri
    MESI_MAP = {
        "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4, 
        "maggio": 5, "giugno": 6, "luglio": 7, "agosto": 8,
        "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
        "tredicesima": 13, "quattordicesima": 14
    }
    
    for _, row in df.iterrows():
        try:
            nome = str(row[col_nome]).strip().upper() if pd.notna(row[col_nome]) else ""
            
            # Gestisci mese come testo o numero
            mese_raw = row[col_mese] if pd.notna(row[col_mese]) else ""
            if isinstance(mese_raw, str):
                mese_lower = mese_raw.lower().strip()
                mese = MESI_MAP.get(mese_lower, 0)
                mese_nome = mese_raw.strip().title()
            else:
                mese = int(mese_raw) if mese_raw else 0
                mese_nome = list(MESI_MAP.keys())[mese - 1].title() if 0 < mese <= 14 else str(mese)
            
            anno = int(row[col_anno]) if pd.notna(row[col_anno]) else 0
            netto = float(row[col_netto]) if pd.notna(row[col_netto]) else 0
            pagato = float(row[col_pagato]) if col_pagato and pd.notna(row[col_pagato]) else netto
            metodo = str(row[col_metodo]).lower().strip() if col_metodo and pd.notna(row[col_metodo]) else "bonifico"
            
            if not nome or mese <= 0 or anno <= 0 or netto <= 0:
                continue
            
            # Normalizza metodo
            if metodo in ["cash", "contante", "cassa"]:
                metodo = "contanti"
            elif metodo in ["bank", "banca", "bon"]:
                metodo = "bonifico"
            elif metodo in ["check", "cheque"]:
                metodo = "assegno"
            
            # === VALIDATORE P0: Salari dal luglio 2018 NON pagabili in contanti (L.205/2017) ===
            # Pre luglio 2018 (fino a giugno incluso) = contanti OK
            if metodo == "contanti" and (anno > 2018 or (anno == 2018 and mese >= 7)):
                risultato["errors"].append(f"P0: {nome} {mese}/{anno} - contanti vietati dal 07/2018")
                risultato["failed"] += 1
                continue
            
            # Check duplicato
            existing = await db[COLLECTION_CEDOLINI].find_one({
                "nome_dipendente": {"$regex": nome, "$options": "i"},
                "mese": {"$in": [mese, str(mese), mese_nome]},
                "anno": {"$in": [anno, str(anno)]}
            })
            
            if existing:
                risultato["skipped_duplicates"] += 1
                continue
            
            # Cerca dipendente
            dipendente = await db["employees"].find_one({
                "$or": [
                    {"nome_completo": {"$regex": nome, "$options": "i"}},
                    {"name": {"$regex": nome, "$options": "i"}}
                ]
            }, {"_id": 0, "id": 1, "codice_fiscale": 1})
            
            # Crea cedolino
            cedolino = {
                "id": str(uuid.uuid4()),
                "nome_dipendente": nome.title(),
                "dipendente_id": dipendente.get("id") if dipendente else None,
                "codice_fiscale": dipendente.get("codice_fiscale") if dipendente else "",
                "mese": mese,
                "anno": anno,
                "periodo": f"{mese:02d}/{anno}",
                "netto": netto,
                "netto_mese": netto,
                "pagato": True,
                "importo_pagato": pagato,
                "metodo_pagamento": metodo,
                "source": "excel_storico",
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            
            await db[COLLECTION_CEDOLINI].insert_one(cedolino.copy())
            risultato["imported"] += 1
            
        except Exception as e:
            risultato["errors"].append(str(e))
            risultato["failed"] += 1
    
    return risultato


@router.post("/import-paghe-bonifici")
@handle_errors
async def import_paghe_bonifici(
    file_paghe: UploadFile = File(..., description="File Excel paghe (NOME DIPENDENTE, MESE, ANNO, IMPORTO netto)"),
    file_bonifici: Optional[UploadFile] = File(None, description="File Excel bonifici (NOME DIPENDENTE, MESE, ANNO, IMPORTO erogato)")
) -> Dict[str, Any]:
    """
    Import combinato paghe + bonifici da due file Excel.
    
    - file_paghe: contiene gli importi netti delle buste paga
    - file_bonifici: contiene gli importi effettivamente pagati via bonifico
    
    Il sistema:
    1. Importa tutti i cedolini da file_paghe
    2. Per ogni cedolino, se c'è un bonifico corrispondente (stesso nome/mese/anno), 
       imposta metodo=bonifico e importo_pagato dal file bonifici
    3. Se non c'è bonifico corrispondente, imposta metodo=contanti (pagato in cassa)
    """
    try:
        import pandas as pd
    except ImportError:
        raise HTTPException(status_code=500, detail="pandas non installato")
    
    db = Database.get_db()
    
    # Mappa mesi
    MESI_MAP = {
        "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4, 
        "maggio": 5, "giugno": 6, "luglio": 7, "agosto": 8,
        "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
        "tredicesima": 13, "quattordicesima": 14
    }
    
    # Leggi file paghe
    content_paghe = await file_paghe.read()
    try:
        df_paghe = pd.read_excel(io.BytesIO(content_paghe))
    except Exception as e:
        logger.error(f"Errore lettura file paghe: {e}")
        raise HTTPException(status_code=400, detail="Errore lettura file paghe")
    
    # Leggi file bonifici (se presente)
    bonifici_dict = {}
    if file_bonifici:
        content_bonifici = await file_bonifici.read()
        try:
            df_bonifici = pd.read_excel(io.BytesIO(content_bonifici))
            df_bonifici.columns = [c.lower().strip().replace(' ', '_') for c in df_bonifici.columns]
            
            col_nome_b = next((c for c in df_bonifici.columns if 'nome' in c), None)
            col_mese_b = next((c for c in df_bonifici.columns if 'mese' in c), None)
            col_anno_b = next((c for c in df_bonifici.columns if 'anno' in c), None)
            col_importo_b = next((c for c in df_bonifici.columns if 'importo' in c or 'erogato' in c), None)
            
            if col_nome_b and col_mese_b and col_anno_b and col_importo_b:
                for _, row in df_bonifici.iterrows():
                    try:
                        nome = str(row[col_nome_b]).strip().upper() if pd.notna(row[col_nome_b]) else ""
                        mese_raw = row[col_mese_b]
                        if isinstance(mese_raw, str):
                            mese = MESI_MAP.get(mese_raw.lower().strip(), 0)
                        else:
                            mese = int(mese_raw) if pd.notna(mese_raw) else 0
                        anno = int(row[col_anno_b]) if pd.notna(row[col_anno_b]) else 0
                        importo = float(row[col_importo_b]) if pd.notna(row[col_importo_b]) else 0
                        
                        if nome and mese > 0 and anno > 0 and importo > 0:
                            key = f"{nome}_{mese}_{anno}"
                            bonifici_dict[key] = importo
                    except Exception as e:
                        logger.warning(f"Errore parsing riga bonifici: {e}")
                        continue
        except Exception as e:
            logger.warning(f"Errore lettura file bonifici: {e}")
            pass  # Ignora errori bonifici, procedi solo con paghe
    
    # Normalizza colonne paghe
    df_paghe.columns = [c.lower().strip().replace(' ', '_') for c in df_paghe.columns]
    
    col_nome = next((c for c in df_paghe.columns if 'nome' in c), None)
    col_mese = next((c for c in df_paghe.columns if 'mese' in c), None)
    col_anno = next((c for c in df_paghe.columns if 'anno' in c), None)
    col_netto = next((c for c in df_paghe.columns if 'netto' in c or 'importo' in c), None)
    
    if not col_nome or not col_mese or not col_anno or not col_netto:
        raise HTTPException(status_code=400, detail="Colonne richieste in paghe: Nome, Mese, Anno, Importo")
    
    risultato = {
        "imported": 0, 
        "skipped_duplicates": 0, 
        "bonifici_matched": 0,
        "contanti_assigned": 0,
        "errors": [], 
        "failed": 0
    }
    
    for _, row in df_paghe.iterrows():
        try:
            nome = str(row[col_nome]).strip().upper() if pd.notna(row[col_nome]) else ""
            
            mese_raw = row[col_mese]
            if isinstance(mese_raw, str):
                mese_lower = mese_raw.lower().strip()
                mese = MESI_MAP.get(mese_lower, 0)
                mese_nome = mese_raw.strip().title()
            else:
                mese = int(mese_raw) if pd.notna(mese_raw) else 0
                mese_nome = list(MESI_MAP.keys())[mese - 1].title() if 0 < mese <= 14 else str(mese)
            
            anno = int(row[col_anno]) if pd.notna(row[col_anno]) else 0
            netto = float(row[col_netto]) if pd.notna(row[col_netto]) else 0
            
            if not nome or mese <= 0 or anno <= 0 or netto <= 0:
                continue
            
            # Check duplicato
            existing = await db[COLLECTION_CEDOLINI].find_one({
                "nome_dipendente": {"$regex": nome, "$options": "i"},
                "mese": {"$in": [mese, str(mese), mese_nome]},
                "anno": {"$in": [anno, str(anno)]}
            })
            
            if existing:
                risultato["skipped_duplicates"] += 1
                continue
            
            # Cerca bonifico corrispondente
            key = f"{nome}_{mese}_{anno}"
            importo_bonifico = bonifici_dict.get(key)
            
            if importo_bonifico and importo_bonifico > 0:
                metodo = "bonifico"
                importo_pagato = importo_bonifico
                risultato["bonifici_matched"] += 1
            else:
                # === VALIDATORE P0: Salari dal luglio 2018 NON pagabili in contanti (L.205/2017) ===
                # Pre luglio 2018 (fino a giugno incluso) = contanti OK
                if anno > 2018 or (anno == 2018 and mese >= 7):
                    # Dal 07/2018: se non c'è bonifico, errore (non assegnare contanti)
                    risultato["errors"].append(f"P0: {nome} {mese}/{anno} - nessun bonifico, contanti vietati dal 07/2018")
                    risultato["failed"] += 1
                    continue
                else:
                    # Pre 07/2018: contanti ammessi
                    metodo = "contanti"
                    importo_pagato = netto
                    risultato["contanti_assigned"] += 1
            
            # Cerca dipendente
            dipendente = await db["employees"].find_one({
                "$or": [
                    {"nome_completo": {"$regex": nome, "$options": "i"}},
                    {"name": {"$regex": nome, "$options": "i"}}
                ]
            }, {"_id": 0, "id": 1, "codice_fiscale": 1})
            
            # Crea cedolino
            cedolino = {
                "id": str(uuid.uuid4()),
                "nome_dipendente": nome.title(),
                "dipendente_id": dipendente.get("id") if dipendente else None,
                "codice_fiscale": dipendente.get("codice_fiscale") if dipendente else "",
                "mese": mese,
                "mese_nome": mese_nome,
                "anno": anno,
                "periodo": f"{mese_nome} {anno}",
                "netto": netto,
                "netto_mese": netto,
                "pagato": True,
                "importo_pagato": importo_pagato,
                "metodo_pagamento": metodo,
                "source": "excel_paghe_bonifici",
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            
            await db[COLLECTION_CEDOLINI].insert_one(cedolino.copy())
            risultato["imported"] += 1
            
        except Exception as e:
            risultato["errors"].append(str(e))
            risultato["failed"] += 1
    
    return risultato


@router.post("/migra-da-prima-nota-salari")
@handle_errors
async def migra_da_prima_nota_salari(
    data: Dict[str, Any] = Body(default={})
) -> Dict[str, Any]:
    """
    Migra i pagamenti stipendi dalla Prima Nota Salari ai Cedolini.
    Prende i movimenti tipo 'uscita' (pagamenti effettuati) e li collega ai cedolini.
    
    Questo permette di:
    1. Avere tutti i pagamenti nella nuova sezione Cedolini
    2. Mantenere lo storico dei pagamenti già registrati
    """
    db = Database.get_db()
    anno = data.get("anno")
    
    # Query per movimenti salari (uscite = pagamenti effettuati)
    query = {"tipo": "uscita"}
    if anno:
        query["$or"] = [
            {"data": {"$regex": f"^{anno}"}},
            {"anno": anno},
            {"anno": str(anno)}
        ]
    
    # Leggi movimenti dalla Prima Nota Salari
    movimenti = await db["prima_nota_salari"].find(query, {"_id": 0}).to_list(5000)
    
    risultato = {
        "totale_movimenti": len(movimenti),
        "cedolini_aggiornati": 0,
        "cedolini_creati": 0,
        "skipped": 0,
        "errors": []
    }
    
    for mov in movimenti:
        try:
            nome_dip = mov.get("dipendente_nome") or mov.get("nome_dipendente") or ""
            importo = float(mov.get("importo", 0))
            data_pag = mov.get("data", "")
            descrizione = mov.get("descrizione", "")
            
            if not nome_dip or importo <= 0:
                risultato["skipped"] += 1
                continue
            
            # Estrai mese/anno dalla descrizione o data
            mese = None
            anno_ced = None
            
            # Prova a estrarre da descrizione (es. "Stipendio NOME - Ottobre 2025")
            import re
            mesi_map = {
                'gennaio': 1, 'febbraio': 2, 'marzo': 3, 'aprile': 4,
                'maggio': 5, 'giugno': 6, 'luglio': 7, 'agosto': 8,
                'settembre': 9, 'ottobre': 10, 'novembre': 11, 'dicembre': 12
            }
            for mese_nome, mese_num in mesi_map.items():
                if mese_nome in descrizione.lower():
                    mese = mese_num
                    # Cerca anno
                    anno_match = re.search(r'20\d{2}', descrizione)
                    if anno_match:
                        anno_ced = int(anno_match.group())
                    break
            
            # Se non trovato, usa data pagamento
            if not mese and data_pag:
                try:
                    parts = data_pag.split("-")
                    anno_ced = int(parts[0])
                    mese = int(parts[1])
                except Exception as e:
                    logger.warning(f"Errore parsing data pagamento {data_pag}: {e}")
            
            if not mese or not anno_ced:
                risultato["skipped"] += 1
                continue
            
            # Cerca cedolino esistente
            cedolino = await db[COLLECTION_CEDOLINI].find_one({
                "nome_dipendente": {"$regex": nome_dip, "$options": "i"},
                "mese": {"$in": [mese, str(mese)]},
                "anno": {"$in": [anno_ced, str(anno_ced)]}
            })
            
            if cedolino:
                # Aggiorna cedolino esistente con info pagamento
                if not cedolino.get("pagato"):
                    await db[COLLECTION_CEDOLINI].update_one(
                        {"id": cedolino["id"]},
                        {"$set": {
                            "pagato": True,
                            "importo_pagato": importo,
                            "data_pagamento": data_pag,
                            "metodo_pagamento": "bonifico",  # Default per salari
                            "prima_nota_salari_id": mov.get("id"),
                            "migrato_da_prima_nota": True,
                            "updated_at": datetime.now(timezone.utc).isoformat()
                        }}
                    )
                    risultato["cedolini_aggiornati"] += 1
                else:
                    risultato["skipped"] += 1
            else:
                # Crea nuovo cedolino già pagato
                nuovo = {
                    "id": str(uuid.uuid4()),
                    "nome_dipendente": nome_dip.title(),
                    "dipendente_id": mov.get("dipendente_id"),
                    "mese": mese,
                    "anno": anno_ced,
                    "periodo": f"{mese:02d}/{anno_ced}",
                    "netto": importo,
                    "netto_mese": importo,
                    "pagato": True,
                    "importo_pagato": importo,
                    "data_pagamento": data_pag,
                    "metodo_pagamento": "bonifico",
                    "prima_nota_salari_id": mov.get("id"),
                    "migrato_da_prima_nota": True,
                    "source": "migrazione_prima_nota_salari",
                    "created_at": datetime.now(timezone.utc).isoformat()
                }
                await db[COLLECTION_CEDOLINI].insert_one(nuovo.copy())
                risultato["cedolini_creati"] += 1
                
        except Exception as e:
            risultato["errors"].append(f"{nome_dip}: {str(e)}")
    
    return risultato


@router.get("/riepilogo-pagamenti")
@handle_errors
async def riepilogo_pagamenti_cedolini(
    anno: Optional[int] = Query(None)
) -> Dict[str, Any]:
    """
    Riepilogo pagamenti cedolini per l'anno.
    Mostra totali per metodo pagamento e stato.
    """
    db = Database.get_db()
    
    query = {}
    if anno:
        query["anno"] = {"$in": [anno, str(anno)]}
    
    pipeline = [
        {"$match": query},
        {"$group": {
            "_id": {
                "pagato": "$pagato",
                "metodo": "$metodo_pagamento"
            },
            "count": {"$sum": 1},
            "totale_netto": {"$sum": {"$toDouble": {"$ifNull": ["$netto", "$netto_mese"]}}},
            "totale_pagato": {"$sum": {"$toDouble": {"$ifNull": ["$importo_pagato", 0]}}}
        }}
    ]
    
    results = await db[COLLECTION_CEDOLINI].aggregate(pipeline).to_list(100)
    
    riepilogo = {
        "anno": anno,
        "totale_cedolini": 0,
        "da_pagare": {"count": 0, "totale": 0},
        "pagati": {
            "contanti": {"count": 0, "totale": 0},
            "bonifico": {"count": 0, "totale": 0},
            "assegno": {"count": 0, "totale": 0},
            "totale": {"count": 0, "totale": 0}
        }
    }
    
    for r in results:
        count = r.get("count", 0)
        totale = r.get("totale_pagato", 0) or r.get("totale_netto", 0)
        riepilogo["totale_cedolini"] += count
        
        if not r["_id"].get("pagato"):
            riepilogo["da_pagare"]["count"] += count
            riepilogo["da_pagare"]["totale"] += totale
        else:
            metodo = r["_id"].get("metodo") or "bonifico"
            if metodo in riepilogo["pagati"]:
                riepilogo["pagati"][metodo]["count"] += count
                riepilogo["pagati"][metodo]["totale"] += totale
            riepilogo["pagati"]["totale"]["count"] += count
            riepilogo["pagati"]["totale"]["totale"] += totale
    
    return riepilogo
