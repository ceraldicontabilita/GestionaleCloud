"""
Prima Nota Module - Manutenzione e Fix.
Funzioni di fix, cleanup, recalculate per manutenzione dati.
"""
from fastapi import HTTPException, Query
from typing import Dict, Optional, Any
from datetime import datetime, timezone
import uuid

from app.database import Database
from .common import COLLECTION_PRIMA_NOTA_CASSA, COLLECTION_PRIMA_NOTA_BANCA, logger
from .sync import determina_tipo_movimento_fattura


async def fix_tipo_movimento_fatture() -> Dict:
    """Corregge il tipo movimento per tutti i movimenti collegati a fatture."""
    db = Database.get_db()
    
    fixed_cassa = 0
    fixed_banca = 0
    errors = []
    
    for collection, fixed_counter in [(COLLECTION_PRIMA_NOTA_CASSA, "cassa"), (COLLECTION_PRIMA_NOTA_BANCA, "banca")]:
        movimenti = await db[collection].find(
            {"fattura_id": {"$exists": True, "$ne": None}},
            {"_id": 0}
        ).to_list(10000)
        
        for mov in movimenti:
            try:
                fattura_id = mov.get("fattura_id")
                if not fattura_id:
                    continue
                
                fattura = await db["invoices"].find_one(
                    {"$or": [{"id": fattura_id}, {"invoice_key": fattura_id}]},
                    {"_id": 0}
                )
                
                if not fattura:
                    continue
                
                tipo_corretto, categoria_corretta, _ = determina_tipo_movimento_fattura(fattura)
                
                if mov.get("tipo") != tipo_corretto or mov.get("categoria") != categoria_corretta:
                    await db[collection].update_one(
                        {"id": mov["id"]},
                        {"$set": {
                            "tipo": tipo_corretto,
                            "categoria": categoria_corretta,
                            "tipo_documento": fattura.get("tipo_documento"),
                            "fixed_at": datetime.now(timezone.utc).isoformat()
                        }}
                    )
                    if fixed_counter == "cassa":
                        fixed_cassa += 1
                    else:
                        fixed_banca += 1
                    logger.info(f"Fixed {fixed_counter} {mov['id']}: {mov.get('tipo')} -> {tipo_corretto}")
                    
            except Exception as e:
                errors.append(f"{fixed_counter} {mov.get('id')}: {str(e)}")
    
    return {
        "success": True,
        "message": f"Corretti {fixed_cassa} movimenti cassa e {fixed_banca} movimenti banca",
        "fixed_cassa": fixed_cassa,
        "fixed_banca": fixed_banca,
        "errors": errors[:20]
    }


async def recalculate_all_balances(anno: Optional[int] = Query(None)) -> Dict:
    """Ricalcola i saldi di Prima Nota Cassa e Banca."""
    db = Database.get_db()
    
    query = {}
    if anno:
        query["data"] = {"$regex": f"^{anno}"}
    
    pipeline = lambda: [
        {"$match": {**query, "status": {"$nin": ["deleted", "archived"]}}},
        {"$group": {
            "_id": None,
            "entrate": {"$sum": {"$cond": [{"$eq": ["$tipo", "entrata"]}, "$importo", 0]}},
            "uscite": {"$sum": {"$cond": [{"$eq": ["$tipo", "uscita"]}, "$importo", 0]}},
            "count": {"$sum": 1}
        }}
    ]
    
    cassa_result = await db[COLLECTION_PRIMA_NOTA_CASSA].aggregate(pipeline()).to_list(1)
    banca_result = await db[COLLECTION_PRIMA_NOTA_BANCA].aggregate(pipeline()).to_list(1)
    
    cassa = cassa_result[0] if cassa_result else {"entrate": 0, "uscite": 0, "count": 0}
    banca = banca_result[0] if banca_result else {"entrate": 0, "uscite": 0, "count": 0}
    
    saldo_cassa = cassa.get("entrate", 0) - cassa.get("uscite", 0)
    saldo_banca = banca.get("entrate", 0) - banca.get("uscite", 0)
    
    return {
        "anno": anno or "tutti",
        "cassa": {
            "entrate": round(cassa.get("entrate", 0), 2),
            "uscite": round(cassa.get("uscite", 0), 2),
            "saldo": round(saldo_cassa, 2),
            "movimenti": cassa.get("count", 0)
        },
        "banca": {
            "entrate": round(banca.get("entrate", 0), 2),
            "uscite": round(banca.get("uscite", 0), 2),
            "saldo": round(saldo_banca, 2),
            "movimenti": banca.get("count", 0)
        },
        "totale": {
            "saldo": round(saldo_cassa + saldo_banca, 2),
            "entrate": round(cassa.get("entrate", 0) + banca.get("entrate", 0), 2),
            "uscite": round(cassa.get("uscite", 0) + banca.get("uscite", 0), 2)
        }
    }


async def cleanup_orphan_movements(anno: Optional[int] = Query(None)) -> Dict:
    """Pulisce i movimenti Prima Nota orfani (fattura inesistente)."""
    db = Database.get_db()
    
    query = {"fattura_id": {"$exists": True, "$ne": None}}
    if anno:
        query["data"] = {"$regex": f"^{anno}"}
    
    orphan_cassa = 0
    orphan_banca = 0
    
    for collection, counter_name in [(COLLECTION_PRIMA_NOTA_CASSA, "cassa"), (COLLECTION_PRIMA_NOTA_BANCA, "banca")]:
        movimenti = await db[collection].find(query, {"_id": 0, "id": 1, "fattura_id": 1}).to_list(10000)
        for mov in movimenti:
            fattura_id = mov.get("fattura_id")
            if fattura_id:
                fattura = await db["invoices"].find_one(
                    {"$or": [{"id": fattura_id}, {"invoice_key": fattura_id}]},
                    {"_id": 1}
                )
                if not fattura:
                    await db[collection].delete_one({"id": mov["id"]})
                    if counter_name == "cassa":
                        orphan_cassa += 1
                    else:
                        orphan_banca += 1
    
    return {
        "success": True,
        "message": f"Eliminati {orphan_cassa} movimenti cassa orfani e {orphan_banca} movimenti banca orfani",
        "orphan_cassa_deleted": orphan_cassa,
        "orphan_banca_deleted": orphan_banca,
        "anno_filtro": anno
    }


async def regenerate_from_invoices(anno: int = Query(...)) -> Dict:
    """Rigenera i movimenti Prima Nota dall'archivio fatture per un anno."""
    db = Database.get_db()
    
    query_delete = {
        "data": {"$regex": f"^{anno}"},
        "source": {"$in": ["fattura_pagata", "fatture_import", "xml_upload"]}
    }
    
    deleted_cassa = await db[COLLECTION_PRIMA_NOTA_CASSA].delete_many(query_delete)
    deleted_banca = await db[COLLECTION_PRIMA_NOTA_BANCA].delete_many(query_delete)
    
    fatture = await db["invoices"].find(
        {"invoice_date": {"$regex": f"^{anno}"}},
        {"_id": 0}
    ).to_list(10000)
    
    created_cassa = 0
    created_banca = 0
    errors = []
    
    for fattura in fatture:
        try:
            metodo = fattura.get("metodo_pagamento", "bonifico")
            tipo_movimento, categoria, desc_prefisso = determina_tipo_movimento_fattura(fattura)
            
            data_fattura = fattura.get("invoice_date") or fattura.get("data_fattura")
            importo = float(fattura.get("total_amount", 0) or fattura.get("importo_totale", 0) or 0)
            numero_fattura = fattura.get("invoice_number") or fattura.get("numero_fattura") or "N/A"
            fornitore = fattura.get("supplier_name") or fattura.get("cedente_denominazione") or "Fornitore"
            fornitore_piva = fattura.get("supplier_vat") or fattura.get("cedente_piva") or ""
            
            if importo <= 0:
                continue
            
            movimento = {
                "id": str(uuid.uuid4()),
                "data": data_fattura,
                "tipo": tipo_movimento,
                "importo": importo,
                "descrizione": f"{desc_prefisso} {numero_fattura} - {fornitore[:40]}",
                "categoria": categoria,
                "riferimento": numero_fattura,
                "fornitore_piva": fornitore_piva,
                "fattura_id": fattura.get("id"),
                "tipo_documento": fattura.get("tipo_documento"),
                "source": "fatture_import",
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            
            if metodo in ["cassa", "contanti"]:
                await db[COLLECTION_PRIMA_NOTA_CASSA].insert_one(movimento.copy())
                created_cassa += 1
            else:
                await db[COLLECTION_PRIMA_NOTA_BANCA].insert_one(movimento.copy())
                created_banca += 1
                
        except Exception as e:
            errors.append(f"Fattura {fattura.get('invoice_number', 'N/A')}: {str(e)}")
    
    return {
        "success": True,
        "anno": anno,
        "fatture_elaborate": len(fatture),
        "movimenti_cassa_creati": created_cassa,
        "movimenti_banca_creati": created_banca,
        "movimenti_cassa_eliminati": deleted_cassa.deleted_count,
        "movimenti_banca_eliminati": deleted_banca.deleted_count,
        "errors": errors[:20]
    }


async def fix_versamenti_duplicati(anno: Optional[int] = Query(None)) -> Dict:
    """Rimuove i versamenti duplicati con importo errato."""
    db = Database.get_db()
    
    query = {"categoria": "Versamento"}
    if anno:
        query["data"] = {"$regex": f"^{anno}"}
    
    versamenti_cassa = await db[COLLECTION_PRIMA_NOTA_CASSA].find(query, {"_id": 0}).to_list(10000)
    
    datetime_format = []
    date_format = []
    
    for v in versamenti_cassa:
        data = v.get("data", "")
        if " " in data:
            datetime_format.append(v)
        else:
            date_format.append(v)
    
    removed = 0
    for v in date_format:
        data_solo = v.get("data", "")[:10]
        corresponding = [d for d in datetime_format if d.get("data", "")[:10] == data_solo]
        
        if corresponding:
            await db[COLLECTION_PRIMA_NOTA_CASSA].delete_one({"id": v["id"]})
            removed += 1
    
    for v in datetime_format:
        data = v.get("data", "")
        if " " in data:
            await db[COLLECTION_PRIMA_NOTA_CASSA].update_one(
                {"id": v["id"]},
                {"$set": {"data": data[:10]}}
            )
    
    return {
        "success": True,
        "anno": anno,
        "versamenti_datetime": len(datetime_format),
        "versamenti_date": len(date_format),
        "duplicati_rimossi": removed,
        "message": f"Rimossi {removed} versamenti duplicati con importo errato"
    }


async def fix_categories_and_duplicates(anno: Optional[int] = Query(None)) -> Dict:
    """Corregge le categorie errate e rimuove i duplicati."""
    db = Database.get_db()
    
    query = {}
    if anno:
        query["data"] = {"$regex": f"^{anno}"}
    
    fixed_categories = 0
    removed_duplicates = 0
    
    movimenti_cassa = await db[COLLECTION_PRIMA_NOTA_CASSA].find(query, {"_id": 0}).to_list(20000)
    
    category_mappings = [
        (["altro"], ["pos"], "POS"),
        (["tasse", "altro"], ["corrispettivo"], "Corrispettivi"),
        (["altro"], ["versamento"], "Versamento"),
    ]
    
    for mov in movimenti_cassa:
        categoria = (mov.get("categoria") or "").lower()
        descrizione = (mov.get("descrizione") or "").lower()
        new_categoria = None
        
        for cat_matches, desc_keywords, new_cat in category_mappings:
            if any(c in categoria for c in cat_matches) and any(k in descrizione for k in desc_keywords):
                new_categoria = new_cat
                break
        
        if new_categoria:
            await db[COLLECTION_PRIMA_NOTA_CASSA].update_one(
                {"id": mov["id"]},
                {"$set": {"categoria": new_categoria}}
            )
            fixed_categories += 1
    
    seen = {}
    for mov in movimenti_cassa:
        key = f"{mov.get('data')}|{mov.get('importo')}|{mov.get('descrizione', '')[:50]}"
        if key in seen:
            await db[COLLECTION_PRIMA_NOTA_CASSA].delete_one({"id": mov["id"]})
            removed_duplicates += 1
        else:
            seen[key] = mov["id"]
    
    return {
        "success": True,
        "anno": anno,
        "fixed_categories": fixed_categories,
        "removed_duplicates": removed_duplicates,
        "movimenti_analizzati": len(movimenti_cassa)
    }


async def sposta_movimento(
    movimento_id: str,
    da: str,
    a: str
) -> Dict:
    """Sposta un movimento da cassa a banca o viceversa."""
    db = Database.get_db()
    
    if da not in ["cassa", "banca"] or a not in ["cassa", "banca"]:
        raise HTTPException(status_code=400, detail="da/a devono essere 'cassa' o 'banca'")
    
    if da == a:
        raise HTTPException(status_code=400, detail="Origine e destinazione uguali")
    
    source_coll = COLLECTION_PRIMA_NOTA_CASSA if da == "cassa" else COLLECTION_PRIMA_NOTA_BANCA
    dest_coll = COLLECTION_PRIMA_NOTA_CASSA if a == "cassa" else COLLECTION_PRIMA_NOTA_BANCA
    
    mov = await db[source_coll].find_one({"id": movimento_id})
    if not mov:
        raise HTTPException(status_code=404, detail=f"Movimento non trovato in {da}")
    
    mov.pop("_id", None)
    mov["moved_from"] = da
    mov["moved_at"] = datetime.now(timezone.utc).isoformat()
    
    await db[dest_coll].insert_one(mov)
    await db[source_coll].delete_one({"id": movimento_id})
    
    return {
        "success": True,
        "message": f"Movimento spostato da {da} a {a}",
        "movimento_id": movimento_id
    }


async def verifica_metodo_fattura(fattura_id: str) -> Dict:
    """Verifica il metodo pagamento di una fattura e fornisce info debug."""
    db = Database.get_db()
    
    fattura = await db["invoices"].find_one(
        {"$or": [{"id": fattura_id}, {"invoice_key": fattura_id}]},
        {"_id": 0}
    )
    
    if not fattura:
        raise HTTPException(status_code=404, detail="Fattura non trovata")
    
    tipo_movimento, categoria, _ = determina_tipo_movimento_fattura(fattura)
    
    fornitore_piva = fattura.get("supplier_vat") or fattura.get("cedente_piva")
    fornitore_info = None
    if fornitore_piva:
        fornitore_info = await db["fornitori"].find_one(
            {"partita_iva": fornitore_piva},
            {"_id": 0, "nome": 1, "metodo_pagamento": 1}
        )
    
    return {
        "fattura_id": fattura_id,
        "tipo_documento": fattura.get("tipo_documento"),
        "metodo_pagamento_fattura": fattura.get("metodo_pagamento"),
        "tipo_movimento_calcolato": tipo_movimento,
        "categoria_calcolata": categoria,
        "fornitore": {
            "partita_iva": fornitore_piva,
            "nome": fornitore_info.get("nome") if fornitore_info else None,
            "metodo_pagamento_anagrafica": fornitore_info.get("metodo_pagamento") if fornitore_info else None
        }
    }


async def verifica_entrate_corrispettivi(anno: int = Query(...)) -> Dict:
    """Verifica entrate corrispettivi in Prima Nota Cassa."""
    db = Database.get_db()
    
    date_start = f"{anno}-01-01"
    date_end = f"{anno}-12-31"
    
    entrate_corr = await db[COLLECTION_PRIMA_NOTA_CASSA].find(
        {
            "data": {"$gte": date_start, "$lte": date_end},
            "categoria": "Corrispettivi",
            "tipo": "entrata"
        },
        {"_id": 0}
    ).to_list(10000)
    
    corrispettivi = await db["corrispettivi"].find(
        {"data": {"$gte": date_start, "$lte": date_end}},
        {"_id": 0}
    ).to_list(10000)
    
    totale_pn = sum(e.get("importo", 0) for e in entrate_corr)
    totale_corr = sum(c.get("totale", 0) for c in corrispettivi)
    
    return {
        "anno": anno,
        "prima_nota": {
            "count": len(entrate_corr),
            "totale": round(totale_pn, 2)
        },
        "corrispettivi": {
            "count": len(corrispettivi),
            "totale": round(totale_corr, 2)
        },
        "differenza": round(totale_pn - totale_corr, 2),
        "status": "OK" if abs(totale_pn - totale_corr) < 1 else "DISCREPANZA"
    }


async def fix_corrispettivi_importo(anno: int = Query(...)) -> Dict:
    """Corregge l'importo dei corrispettivi in Prima Nota Cassa."""
    db = Database.get_db()
    
    date_start = f"{anno}-01-01"
    date_end = f"{anno}-12-31"
    
    entrate = await db[COLLECTION_PRIMA_NOTA_CASSA].find(
        {
            "data": {"$gte": date_start, "$lte": date_end},
            "categoria": "Corrispettivi"
        },
        {"_id": 0}
    ).to_list(10000)
    
    fixed = 0
    for e in entrate:
        corr_id = e.get("corrispettivo_id") or e.get("riferimento", "").replace("CORR-", "")
        if not corr_id:
            continue
        
        corr = await db["corrispettivi"].find_one({"id": corr_id}, {"_id": 0})
        if not corr:
            continue
        
        totale_corretto = float(corr.get("totale", 0) or 0)
        importo_attuale = float(e.get("importo", 0))
        
        if abs(totale_corretto - importo_attuale) > 0.01:
            await db[COLLECTION_PRIMA_NOTA_CASSA].update_one(
                {"id": e["id"]},
                {"$set": {
                    "importo": totale_corretto,
                    "importo_originale": importo_attuale,
                    "fixed_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            fixed += 1
    
    return {
        "success": True,
        "anno": anno,
        "entrate_analizzate": len(entrate),
        "corrette": fixed
    }


async def migrazione_pulisci_bancari_da_cassa() -> Dict[str, Any]:
    """
    MIGRAZIONE ONE-SHOT: Elimina tutti i movimenti bancari dalla prima_nota_cassa.
    
    La Prima Nota Cassa deve contenere SOLO movimenti di denaro CONTANTE:
    - ENTRATE: Corrispettivi giornalieri, incassi contanti, finanziamenti soci in contanti
    - USCITE: Versamenti in banca, fatture pagate in contanti, piccole spese contanti
    
    NON deve contenere:
    - Bonifici, SDD, RID, pagamenti POS bancari, F24, stipendi, 
    - Pagamenti fornitori via banca, commissioni bancarie
    """
    db = Database.get_db()
    
    # Keywords che identificano movimenti BANCARI
    BANCARI_KEYWORDS = [
        'INC.POS CARTE CREDIT', 'INCAS. TRAMITE P.O.S', 'INC.POS',
        'BONIFICO', 'BONIF.', 'BON.DA', 'BONIF. VS.',
        'SEPA', 'SDD', 'RID', 'ADDEBITO DIRETTO',
        'ACCREDITO', 'GIROCONTO',
        'NUMIA', 'NEXI', 'WORLDLINE', 'SUMUP',
        'PRELIEVO ATM', 'PRELIEVO BANCOMAT',
        'Pagamento Fatt.', 'PAGAMENTO FATT.',
        'STIPENDI', 'EMOLUMENTI',
        'F24', 'DELEGA UNICA', 'MOD.F24',
        'CANONE MENSILE', 'COMMISSIONI', 'COMPETENZE E SPESE',
        'IMPOSTA BOLLO',
        'PDV 37',  # terminale POS bancario Ceraldi
    ]
    
    tutti = await db[COLLECTION_PRIMA_NOTA_CASSA].find(
        {"status": {"$nin": ["deleted", "archived"]}},
        {"_id": 1, "descrizione": 1, "categoria": 1, "source": 1, "importo": 1, "data": 1, "tipo": 1}
    ).to_list(100000)
    
    ids_da_eliminare = []
    campione_eliminati = []
    
    for m in tutti:
        desc = (m.get('descrizione') or '')
        desc_upper = desc.upper()
        cat = m.get('categoria', '') or ''
        source = m.get('source', '') or ''
        
        # Corrispettivi: SEMPRE legittimi
        if cat == 'Corrispettivi' or source == 'corrispettivi_sync':
            continue
        
        # Movimenti manuali senza keywords bancari: legittimi
        if source in ('', 'manual', 'user') or source is None:
            if not any(kw.upper() in desc_upper for kw in BANCARI_KEYWORDS):
                continue
        
        # POS manuali (categoria POS senza source csv): legittimi
        if cat == 'POS' and source in ('', 'manual', 'user', None):
            continue
            
        # Versamenti manuali: legittimi  
        if cat in ('Versamento', 'Finanziamento', 'Finanziamento soci') and source in ('', 'manual', 'user', None):
            continue
        
        # CSV import: ELIMINA se ha keywords bancari
        if source == 'csv_import':
            if any(kw.upper() in desc_upper for kw in BANCARI_KEYWORDS):
                ids_da_eliminare.append(m['_id'])
                if len(campione_eliminati) < 10:
                    campione_eliminati.append({
                        "data": m.get("data"), "descrizione": desc[:60], 
                        "importo": m.get("importo"), "source": source, "motivo": "csv_bancario"
                    })
                continue
            else:
                # CSV non bancario: potrebbe essere legittimo, lo teniamo
                continue
        
        # sync_fatture con categoria fornitori/Fatture: ELIMINA (pagato per banca, non contanti)
        if source == 'sync_fatture' and cat in ('fornitori', 'Fatture', 'fornitore'):
            ids_da_eliminare.append(m['_id'])
            if len(campione_eliminati) < 10:
                campione_eliminati.append({
                    "data": m.get("data"), "descrizione": desc[:60],
                    "importo": m.get("importo"), "source": source, "motivo": "fattura_bancaria"
                })
            continue
        
        # Qualsiasi altra source con keywords bancari: ELIMINA
        if any(kw.upper() in desc_upper for kw in BANCARI_KEYWORDS):
            ids_da_eliminare.append(m['_id'])
            if len(campione_eliminati) < 10:
                campione_eliminati.append({
                    "data": m.get("data"), "descrizione": desc[:60],
                    "importo": m.get("importo"), "source": source, "motivo": "keyword_bancario"
                })
    
    deleted_count = 0
    if ids_da_eliminare:
        result = await db[COLLECTION_PRIMA_NOTA_CASSA].delete_many({"_id": {"$in": ids_da_eliminare}})
        deleted_count = result.deleted_count
    
    remaining = await db[COLLECTION_PRIMA_NOTA_CASSA].count_documents(
        {"status": {"$nin": ["deleted", "archived"]}}
    )
    
    logger.info(f"MIGRAZIONE CASSA: Eliminati {deleted_count} movimenti bancari, rimasti {remaining}")
    
    return {
        "success": True,
        "message": f"Migrazione completata: eliminati {deleted_count} movimenti bancari da Prima Nota Cassa",
        "movimenti_eliminati": deleted_count,
        "movimenti_rimasti": remaining,
        "campione_eliminati": campione_eliminati
    }
