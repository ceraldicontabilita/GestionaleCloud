"""
Prima Nota Module - Sincronizzazione e Import.
Sync corrispettivi, fatture, import CSV/batch.
"""
from fastapi import HTTPException, Query, Body
from typing import Dict, Any, Optional
from datetime import datetime, timezone
import logging
import uuid

from app.database import Database, Collections
from .common import (
    COLLECTION_PRIMA_NOTA_CASSA, COLLECTION_PRIMA_NOTA_BANCA
)

logger = logging.getLogger(__name__)


# Tipi documento fatture attive (vendite - ENTRATE)
TIPI_FATTURA_ATTIVA = ["TD24", "TD25", "TD26", "TD27"]
TIPI_NOTA_CREDITO = ["TD04", "TD08"]


def determina_tipo_movimento_fattura(fattura: Dict) -> tuple:
    """Determina tipo movimento (entrata/uscita) e categoria dalla fattura."""
    tipo_doc = fattura.get("tipo_documento", "TD01").upper()
    supplier_vat = fattura.get("supplier_vat") or fattura.get("cedente_piva") or ""
    
    is_nota_credito = tipo_doc in TIPI_NOTA_CREDITO
    is_fattura_attiva = tipo_doc in TIPI_FATTURA_ATTIVA
    
    if is_nota_credito:
        return ("entrata", "Nota credito fornitore", "Nota credito")
    elif is_fattura_attiva:
        return ("entrata", "Incasso cliente", "Incasso fattura")
    else:
        return ("uscita", "Pagamento fornitore", "Pagamento fattura")


async def registra_pagamento_fattura(
    fattura: Dict,
    metodo_pagamento: str,
    importo_cassa: float = 0,
    importo_banca: float = 0
) -> Dict:
    """Registra automaticamente il pagamento di una fattura.

    IDEMPOTENTE: se esiste già un movimento con stesso fattura_id sulla
    collection di destinazione, NON crea duplicati. Ritorna l'id esistente.
    """
    db = Database.get_db()

    now = datetime.now(timezone.utc).isoformat()
    data_fattura = fattura.get("invoice_date") or fattura.get("data_fattura") or now[:10]
    importo_totale = fattura.get("total_amount") or fattura.get("importo_totale") or 0
    numero_fattura = fattura.get("invoice_number") or fattura.get("numero_fattura") or "N/A"
    fornitore = fattura.get("supplier_name") or fattura.get("cedente_denominazione") or "Fornitore"
    fornitore_piva = fattura.get("supplier_vat") or fattura.get("cedente_piva") or ""
    fattura_id = fattura.get("id") or fattura.get("invoice_key")

    tipo_movimento, categoria, desc_prefisso = determina_tipo_movimento_fattura(fattura)

    risultato = {"cassa": None, "banca": None, "tipo_movimento": tipo_movimento, "duplicato": False}
    descrizione_base = f"{desc_prefisso} {numero_fattura} - {fornitore[:40]}"

    # Riferimento UNIFORME in tutto il modulo: "FATT-{id}"
    # Questo allinea dedup con sync_fatture_pagate e conferma_fattura_provvisoria.
    riferimento = f"FATT-{fattura_id}" if fattura_id else numero_fattura

    movimento_base = {
        "data": data_fattura,
        "tipo": tipo_movimento,
        "categoria": categoria,
        "riferimento": riferimento,
        "numero_fattura": numero_fattura,  # mantenuto per retrocompatibilità UI
        "fornitore_piva": fornitore_piva,
        "fattura_id": fattura_id,
        "tipo_documento": fattura.get("tipo_documento"),
        "source": "fattura_pagata",
        "created_at": now
    }

    async def _insert_idempotente(collection: str, importo: float, desc: str) -> tuple:
        """Inserisce movimento solo se non esiste già per questa fattura.
        Ritorna (id_movimento, was_duplicate)."""
        if fattura_id:
            existing = await db[collection].find_one({
                "$or": [
                    {"fattura_id": fattura_id},
                    {"riferimento": riferimento},
                ],
                "status": {"$nin": ["deleted", "archived"]},
            })
            if existing:
                return (existing.get("id") or str(existing.get("_id")), True)

        mov = {**movimento_base, "id": str(uuid.uuid4()), "importo": float(importo), "descrizione": desc}
        await db[collection].insert_one(mov.copy())
        return (mov["id"], False)

    metodo = (metodo_pagamento or "").lower()

    if metodo in ["cassa", "contanti"]:
        mid, dup = await _insert_idempotente(COLLECTION_PRIMA_NOTA_CASSA, importo_totale, descrizione_base)
        risultato["cassa"] = mid
        risultato["duplicato"] = dup

    elif metodo in ["banca", "bonifico", "assegno", "riba", "carta", "sepa", "mav", "rav", "rid", "f24"]:
        mid, dup = await _insert_idempotente(COLLECTION_PRIMA_NOTA_BANCA, importo_totale, descrizione_base)
        risultato["banca"] = mid
        risultato["duplicato"] = dup

    elif metodo == "misto":
        if importo_cassa > 0:
            mid, dup_c = await _insert_idempotente(
                COLLECTION_PRIMA_NOTA_CASSA, importo_cassa, f"{descrizione_base} (contanti)"
            )
            risultato["cassa"] = mid
            risultato["duplicato"] = risultato["duplicato"] or dup_c
        if importo_banca > 0:
            mid, dup_b = await _insert_idempotente(
                COLLECTION_PRIMA_NOTA_BANCA, importo_banca, f"{descrizione_base} (bonifico)"
            )
            risultato["banca"] = mid
            risultato["duplicato"] = risultato["duplicato"] or dup_b

    return risultato


async def registra_fattura_prima_nota(
    fattura_id: str = Body(...),
    metodo_pagamento: str = Body(None),
    importo_cassa: float = Body(0),
    importo_banca: float = Body(0)
) -> Dict:
    """Registra manualmente il pagamento di una fattura."""
    db = Database.get_db()
    
    fattura = await db[Collections.INVOICES].find_one(
        {"$or": [{"id": fattura_id}, {"invoice_key": fattura_id}]}
    )
    
    if not fattura:
        raise HTTPException(status_code=404, detail="Fattura non trovata")
    
    if not metodo_pagamento:
        fornitore_piva = fattura.get("supplier_vat") or fattura.get("cedente_piva")
        if fornitore_piva:
            fornitore = await db[Collections.SUPPLIERS].find_one({"partita_iva": fornitore_piva}, {"_id": 0})
            if fornitore:
                metodo_fornitore = (fornitore.get("metodo_pagamento") or "").lower()
                metodo_pagamento = "cassa" if metodo_fornitore in ["contanti", "cassa", "cash"] else "banca"
            else:
                metodo_pagamento = "banca"
        else:
            metodo_pagamento = "banca"
    
    risultato = await registra_pagamento_fattura(
        fattura=fattura,
        metodo_pagamento=metodo_pagamento,
        importo_cassa=importo_cassa,
        importo_banca=importo_banca
    )
    
    await db[Collections.INVOICES].update_one(
        {"_id": fattura["_id"]},
        {"$set": {
            "pagato": True,
            "data_pagamento": datetime.now(timezone.utc).isoformat()[:10],
            "metodo_pagamento": metodo_pagamento,
            "prima_nota_cassa_id": risultato.get("cassa"),
            "prima_nota_banca_id": risultato.get("banca")
        }}
    )
    
    return {
        "message": "Pagamento registrato",
        "prima_nota_cassa": risultato.get("cassa"),
        "prima_nota_banca": risultato.get("banca")
    }


async def sync_corrispettivi_to_prima_nota() -> Dict:
    """Sincronizza corrispettivi in Prima Nota Cassa."""
    return await _sync_corrispettivi_impl()


async def sync_corrispettivi_anno(anno: int = Query(...)) -> Dict:
    """Sincronizza corrispettivi dell'anno specificato nella Prima Nota Cassa."""
    return await _sync_corrispettivi_impl(anno)


async def _sync_corrispettivi_impl(anno: int = None) -> Dict:
    """Implementazione sync corrispettivi → prima nota cassa."""
    import logging
    from .common import COLLECTION_PRIMA_NOTA_CASSA
    logger = logging.getLogger(__name__)
    db = Database.get_db()
    
    query = {}
    if anno:
        query["anno"] = anno
    
    corrispettivi = await db["corrispettivi"].find(query, {"_id": 0}).to_list(5000)
    
    inseriti = 0
    duplicati = 0
    saltati_importo_zero = []  # diagnostica: quali corrispettivi vengono scartati
    
    for c in corrispettivi:
        corr_id = c.get("id", "")
        
        # Check dedup
        existing = await db[COLLECTION_PRIMA_NOTA_CASSA].find_one({"corrispettivo_id": corr_id})
        if existing:
            duplicati += 1
            continue
        
        data = c.get("data", c.get("data_operazione", ""))
        
        # REGOLA CONTABILE: 
        # ENTRATA = totale corrispettivo (contanti + POS)
        # USCITA = POS verso banca (il POS esce dalla cassa verso la banca)
        # SALDO = solo contanti rimasti in cassa
        contanti = float(c.get("pagato_contanti", 0) or 0)
        # FIX: il DB salva "pagato_pos", il vecchio codice leggeva "pagato_elettronico"
        # Manteniamo entrambi i nomi per retrocompatibilità con vecchi documenti.
        elettronico = float(c.get("pagato_pos", 0) or c.get("pagato_elettronico", 0) or 0)
        totale = float(
            c.get("totale", 0)
            or c.get("totale_complessivo", 0)
            or c.get("importo", 0)
            or c.get("totale_giornaliero", 0)
            or (contanti + elettronico)  # fallback: somma dei metodi di pagamento
            or 0
        )
        
        if totale <= 0:
            # Log diagnostico: aiuta a capire perché alcuni corrispettivi non compaiono in cassa
            saltati_importo_zero.append({
                "id": corr_id,
                "data": data,
                "anno": c.get("anno"),
                "campi_totale": {
                    "totale": c.get("totale"),
                    "totale_complessivo": c.get("totale_complessivo"),
                    "importo": c.get("importo"),
                    "pagato_contanti": c.get("pagato_contanti"),
                    "pagato_pos": c.get("pagato_pos"),
                },
            })
            logger.warning(
                "Corrispettivo %s (data=%s) saltato: totale=0 su tutti i campi noti",
                corr_id, data,
            )
            continue
        
        # ENTRATA CASSA: totale corrispettivo
        movimento = {
            "id": str(__import__("uuid").uuid4()),
            "data": data,
            "tipo": "entrata",
            "categoria": "Corrispettivi",
            "descrizione": f"Corrispettivi {data}",
            "importo": round(totale, 2),
            "corrispettivo_id": corr_id,
            "pagato_contanti": round(contanti, 2),
            "pagato_elettronico": round(elettronico, 2),
            "totale_giornata": round(totale, 2),
            "source": "corrispettivi_sync",
            "created_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        }
        await db[COLLECTION_PRIMA_NOTA_CASSA].insert_one(movimento)
        inseriti += 1
        
        # USCITA CASSA: POS verso banca
        if elettronico > 0:
            existing_pos = await db[COLLECTION_PRIMA_NOTA_CASSA].find_one(
                {"corrispettivo_id": corr_id, "source": "corrispettivi_pos_sync"}
            )
            if not existing_pos:
                movimento_pos = {
                    "id": str(__import__("uuid").uuid4()),
                    "data": data,
                    "tipo": "uscita",
                    "categoria": "POS Verso Banca",
                    "descrizione": f"Pagamento elettronico {data} → Banca",
                    "importo": round(elettronico, 2),
                    "corrispettivo_id": corr_id,
                    "source": "corrispettivi_pos_sync",
                    "created_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
                }
                await db[COLLECTION_PRIMA_NOTA_CASSA].insert_one(movimento_pos)
    
    return {
        "message": f"Sincronizzati {inseriti} corrispettivi in Prima Nota Cassa",
        "inseriti": inseriti,
        "duplicati": duplicati,
        "saltati": len(saltati_importo_zero),
        "saltati_dettaglio": saltati_importo_zero[:50],  # primi 50 per diagnostica
        "anno": anno,
        "ok": True
    }


async def sync_fatture_pagate(anno: int = Query(...)) -> Dict:
    """Sincronizza fatture pagate nella Prima Nota."""
    db = Database.get_db()
    
    date_start = f"{anno}-01-01"
    date_end = f"{anno}-12-31"
    
    fatture = await db["invoices"].find(
        {"invoice_date": {"$gte": date_start, "$lte": date_end}, "stato_pagamento": "pagata"},
        {"_id": 0}
    ).to_list(10000)
    
    if not fatture:
        return {"message": "Nessuna fattura pagata trovata", "importati": 0}
    
    # IMPORTANTE: il dedup NON deve filtrare per categoria.
    # Dopo la PR #1, registra_pagamento_fattura salva con categoria variabile
    # ("Pagamento fornitore", "Incasso cliente", "Nota credito fornitore") e
    # NON "Fatture". Se filtrassimo per categoria="Fatture" come prima, questa
    # funzione non vedrebbe quei movimenti e creerebbe duplicati.
    # Il riferimento è ormai uniforme (FATT-{id}), basta quello.
    existing_cassa = await db[COLLECTION_PRIMA_NOTA_CASSA].find(
        {
            "data": {"$gte": date_start, "$lte": date_end},
            "riferimento": {"$regex": "^FATT-"},
            "status": {"$nin": ["deleted", "archived"]},
        },
        {"riferimento": 1, "fattura_id": 1, "_id": 0}
    ).to_list(10000)
    existing_banca = await db[COLLECTION_PRIMA_NOTA_BANCA].find(
        {
            "data": {"$gte": date_start, "$lte": date_end},
            "riferimento": {"$regex": "^FATT-"},
            "status": {"$nin": ["deleted", "archived"]},
        },
        {"riferimento": 1, "fattura_id": 1, "_id": 0}
    ).to_list(10000)
    existing_refs = set(e.get("riferimento") for e in existing_cassa + existing_banca if e.get("riferimento"))
    # Dedup anche per fattura_id (caso: vecchi movimenti col riferimento nel formato "numero_fattura")
    existing_fids = set(e.get("fattura_id") for e in existing_cassa + existing_banca if e.get("fattura_id"))
    
    importati_cassa = 0
    importati_banca = 0
    totale_cassa = 0
    totale_banca = 0
    
    for fatt in fatture:
        fattura_id = fatt.get('id', '')
        ref = f"FATT-{fattura_id}"

        # Dedup: o per riferimento FATT-, o per fattura_id (in caso di vecchi movimenti)
        if ref in existing_refs or (fattura_id and fattura_id in existing_fids):
            continue
        
        totale = float(fatt.get("total_amount", 0) or 0)
        if totale <= 0:
            continue
        
        metodo = fatt.get("metodo_pagamento", "bonifico").lower()
        fornitore = fatt.get("supplier_name") or fatt.get("cedente_denominazione", "Fornitore")
        
        movimento = {
            "id": str(uuid.uuid4()),
            "data": fatt.get("invoice_date") or fatt.get("data_pagamento"),
            "tipo": "uscita",
            "importo": totale,
            "descrizione": f"Fattura {fatt.get('numero', '')} - {fornitore[:30]}",
            "categoria": "Fatture",
            "riferimento": ref,
            "fattura_id": fattura_id,
            "source": "sync_fatture",
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        if metodo in ["contanti", "cassa"]:
            await db[COLLECTION_PRIMA_NOTA_CASSA].insert_one(movimento.copy())
            importati_cassa += 1
            totale_cassa += totale
        else:
            await db[COLLECTION_PRIMA_NOTA_BANCA].insert_one(movimento.copy())
            importati_banca += 1
            totale_banca += totale
    
    return {
        "message": "Sincronizzazione completata",
        "importati_cassa": importati_cassa,
        "importati_banca": importati_banca,
        "totale_cassa": round(totale_cassa, 2),
        "totale_banca": round(totale_banca, 2),
        "fatture_pagate_anno": len(fatture)
    }


async def get_corrispettivi_sync_status() -> Dict:
    """Verifica stato sincronizzazione corrispettivi."""
    db = Database.get_db()
    
    total_corrispettivi = await db["corrispettivi"].count_documents({})
    synced = await db[COLLECTION_PRIMA_NOTA_CASSA].count_documents({"corrispettivo_id": {"$exists": True, "$ne": None}})
    
    pipeline = [{"$group": {"_id": None, "totale": {"$sum": "$totale"}}}]
    totals = await db["corrispettivi"].aggregate(pipeline).to_list(1)
    
    pipeline_pn = [
        {"$match": {"categoria": "Corrispettivi", "tipo": "entrata"}},
        {"$group": {"_id": None, "totale": {"$sum": "$importo"}}}
    ]
    totals_pn = await db[COLLECTION_PRIMA_NOTA_CASSA].aggregate(pipeline_pn).to_list(1)
    
    return {
        "corrispettivi_totali": total_corrispettivi,
        "corrispettivi_sincronizzati": synced,
        "da_sincronizzare": total_corrispettivi - synced,
        "totale_corrispettivi_euro": totals[0].get("totale", 0) if totals else 0,
        "totale_in_prima_nota_euro": totals_pn[0].get("totale", 0) if totals_pn else 0
    }



async def sync_estratto_conto_to_banca(anno: int = Query(...)) -> Dict:
    """
    Sincronizza movimenti dall'estratto conto bancario alla prima nota banca.
    Importa tutti i movimenti dell'anno specificato.
    """
    db = Database.get_db()
    
    # Trova movimenti dell'anno nell'estratto conto
    # Le date sono in formato DD/MM/YYYY
    anno_str = str(anno)
    
    # Query: data_contabile contiene l'anno (potrebbe essere DD/MM/YYYY o YYYY-MM-DD)
    query = {"$or": [
        {"data_contabile": {"$regex": f"/{anno_str}$"}},  # DD/MM/YYYY
        {"data_contabile": {"$regex": f"^{anno_str}-"}},   # YYYY-MM-DD
    ]}
    
    movimenti_ec = await db["estratto_conto_movimenti"].find(query, {"_id": 0}).to_list(15000)
    
    if not movimenti_ec:
        return {"message": f"Nessun movimento estratto conto per {anno}", "importati": 0}
    
    # Get existing prima nota banca for dedup
    existing_ids = set()
    async for pn in db[COLLECTION_PRIMA_NOTA_BANCA].find(
        {"data": {"$regex": f"^{anno_str}"}},
        {"_id": 0, "estratto_conto_id": 1, "id": 1}
    ):
        if pn.get("estratto_conto_id"):
            existing_ids.add(pn["estratto_conto_id"])
    
    importati = 0
    batch = []
    
    for mov in movimenti_ec:
        ec_id = mov.get("id", "")
        if ec_id in existing_ids:
            continue
        
        # Converti data DD/MM/YYYY → YYYY-MM-DD
        data_raw = mov.get("data_contabile", "")
        if "/" in data_raw:
            parts = data_raw.split("/")
            if len(parts) == 3:
                data_iso = f"{parts[2]}-{parts[1]}-{parts[0]}"
            else:
                data_iso = data_raw
        else:
            data_iso = data_raw
        
        importo = float(mov.get("importo", 0) or 0)
        if importo == 0:
            continue
        
        tipo = "entrata" if importo > 0 else "uscita"
        
        movimento_pn = {
            "id": str(uuid.uuid4()),
            "data": data_iso,
            "tipo": tipo,
            "importo": abs(importo),
            "descrizione": mov.get("descrizione", "")[:200],
            "categoria": mov.get("categoria", "Bancario"),
            "causale": mov.get("causale", ""),
            "beneficiario": mov.get("beneficiario", ""),
            "estratto_conto_id": ec_id,
            "source": "estratto_conto_sync",
            "created_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        }
        
        batch.append(movimento_pn)
        importati += 1
        
        # Insert in batches of 500
        if len(batch) >= 500:
            await db[COLLECTION_PRIMA_NOTA_BANCA].insert_many(batch)
            batch = []
    
    if batch:
        await db[COLLECTION_PRIMA_NOTA_BANCA].insert_many(batch)
    
    return {
        "message": f"Sincronizzati {importati} movimenti estratto conto → prima nota banca {anno}",
        "anno": anno,
        "movimenti_estratto_conto": len(movimenti_ec),
        "gia_sincronizzati": len(existing_ids),
        "importati": importati,
    }



async def get_fatture_provvisorie(anno: int = Query(...)) -> Dict:
    """
    Lista fatture NON ancora registrate in Prima Nota.
    Per ogni fattura, il sistema suggerisce CASSA o BANCA basandosi su:
    1. Metodo pagamento XML (MP01=contanti→cassa, MP05=bonifico→banca)
    2. Ricerca importo nell'estratto conto (se trovato → BANCA confermato)
    """
    db = Database.get_db()
    
    # Fatture dell'anno NON ancora registrate in Prima Nota
    # Logica: esclude fatture con stato_pagamento="pagata" E quelle con prima_nota_id valido
    fatture = await db["invoices"].find(
        {
            "invoice_date": {"$regex": f"^{anno}"},
            "total_amount": {"$gt": 0},
            "stato_pagamento": {"$nin": ["pagata", "paid"]},
            "$or": [
                {"prima_nota_id": None}, {"prima_nota_id": ""},
                {"prima_nota_id": {"$exists": False}},
            ]
        },
        {"_id": 0, "xml_raw": 0, "linee": 0}
    ).sort("invoice_date", -1).to_list(500)
    
    # Movimenti banca per match
    movimenti_banca = {}
    async for m in db["estratto_conto_movimenti"].find(
        {"tipo": "uscita", "data_contabile": {"$regex": f"/{anno}$"}},
        {"_id": 0, "id": 1, "importo": 1, "descrizione": 1, "data_contabile": 1}
    ):
        imp = float(m.get("importo", 0))
        if imp not in movimenti_banca:
            movimenti_banca[imp] = []
        movimenti_banca[imp].append(m)
    
    # Carica metodo pagamento per fornitore (da anagrafica fornitori)
    metodo_per_piva = {}
    async for s in db["fornitori"].find(
        {"metodo_pagamento": {"$exists": True, "$ne": ""}},
        {"_id": 0, "partita_iva": 1, "metodo_pagamento": 1}
    ):
        piva = s.get("partita_iva", "")
        metodo = s.get("metodo_pagamento", "")
        if piva and metodo:
            metodo_per_piva[piva] = metodo
    
    provvisori = []
    for f in fatture:
        importo = float(f.get("total_amount", 0))
        metodo_xml = f.get("payment_method", "")
        metodo_code = f.get("payment_method_code", "")
        piva = f.get("supplier_vat", "")
        
        # PRIORITÀ 0: Se la fattura è stata marcata come sospesa dall'utente
        stato_pag = f.get("stato_pagamento", "")
        if stato_pag == "sospesa":
            suggerimento = "sospesa"
            stato_match = "in_attesa"
        # PRIORITÀ 1 (UNICA): Metodo dal fornitore in anagrafica
        # REGOLA: il metodo XML della fattura NON viene MAI usato
        elif metodo_per_piva.get(piva, ""):
            metodo_fornitore = metodo_per_piva.get(piva, "")
            if metodo_fornitore in ["contanti", "cassa"]:
                suggerimento = "cassa"
                stato_match = "confermato"
            elif metodo_fornitore in ["sospesa", "misto"]:
                suggerimento = "sospesa"
                stato_match = "in_attesa"
            else:
                suggerimento = "banca"
                stato_match = "confermato"
        # NESSUN METODO FORNITORE → sospesa (da decidere manualmente)
        else:
            suggerimento = "sospesa"
            stato_match = "in_attesa"
        
        # Se banca: cerca INTELLIGENTEMENTE nell'estratto conto
        movimento_match = None
        if suggerimento == "banca":
            candidati = movimenti_banca.get(importo, [])
            nome = (f.get("supplier_name") or "").upper()
            numero_fatt = (f.get("invoice_number") or "").upper()
            
            for m in candidati:
                desc = (m.get("descrizione") or "").upper()
                score = 0
                
                # Match per nome fornitore (prime 2 parole)
                nome_parts = [p for p in nome.split()[:3] if len(p) > 3]
                for p in nome_parts:
                    if p in desc:
                        score += 30
                
                # Match per P.IVA
                if piva and piva in desc:
                    score += 50
                
                # Match per numero fattura
                if numero_fatt and len(numero_fatt) > 2 and numero_fatt in desc:
                    score += 40
                
                # Keywords bonifico
                if "VS.DISP" in desc or "BONIFICO" in desc:
                    score += 10
                
                if score >= 30:
                    movimento_match = m
                    stato_match = "confermato"
                    break
            
            if not movimento_match and candidati:
                # Match solo per importo — probabile ma non certo
                movimento_match = candidati[0]
                stato_match = "probabile"
        
        provvisori.append({
            "fattura_id": f.get("id"),
            "fattura_numero": f.get("invoice_number", ""),
            "fattura_data": f.get("invoice_date", ""),
            "fornitore": f.get("supplier_name", ""),
            "fornitore_piva": f.get("supplier_vat", ""),
            "importo": importo,
            "metodo_xml": metodo_xml,
            "suggerimento": suggerimento,
            "stato_match": stato_match,
            "movimento_banca": {
                "data": movimento_match.get("data_contabile", "") if movimento_match else None,
                "descrizione": (movimento_match.get("descrizione", "")[:80]) if movimento_match else None,
                "id": movimento_match.get("id") if movimento_match else None,
            } if movimento_match else None,
        })
    
    # Auto-conferma SOLO se CERTO:
    # 1. CASSA: contanti confermato → auto
    # 2. BANCA: fornitore dice banca + trovato in estratto conto → auto
    # 3. SOSPESA/MISTO/IN_ATTESA → provvisorio
    auto_confermati = 0
    provvisori_finali = []
    
    for p in provvisori:
        suggerimento = p["suggerimento"]
        stato = p["stato_match"]
        fatt_id = p["fattura_id"]
        ref = f"FATT-{fatt_id}"
        
        auto_confirm = False
        
        # CONTANTI: sempre auto-conferma in CASSA
        if suggerimento == "cassa" and stato == "confermato":
            auto_confirm = True
        
        # BANCA: SOLO se verificato al 100% nell'estratto conto
        elif suggerimento == "banca" and stato == "confermato" and p.get("movimento_banca"):
            auto_confirm = True
        
        # SOSPESA, MISTO, IN_ATTESA → provvisorio (utente decide)
        
        if auto_confirm:
            collection = COLLECTION_PRIMA_NOTA_CASSA if suggerimento == "cassa" else COLLECTION_PRIMA_NOTA_BANCA
            existing = await db[collection].find_one({"riferimento": ref})
            
            if not existing:
                data_mov = p.get("fattura_data", "")
                if p.get("movimento_banca") and p["movimento_banca"].get("data"):
                    data_mov = p["movimento_banca"]["data"]
                if "/" in str(data_mov):
                    parts = str(data_mov).split("/")
                    if len(parts) == 3:
                        data_mov = f"{parts[2]}-{parts[1]}-{parts[0]}"
                
                pn_id = str(uuid.uuid4())
                metodo_label = "contanti" if suggerimento == "cassa" else p.get("metodo_xml") or "bonifico"
                await db[collection].insert_one({
                    "id": pn_id,
                    "data": data_mov,
                    "tipo": "uscita",
                    "categoria": "Fatture",
                    "descrizione": f"Fatt. {p['fattura_numero']} - {p['fornitore'][:30]}",
                    "importo": p["importo"],
                    "riferimento": ref,
                    "fattura_id": fatt_id,
                    "metodo_pagamento": metodo_label,
                    "source": "auto_conferma",
                    "created_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
                })
                await db["invoices"].update_one(
                    {"id": fatt_id},
                    {"$set": {
                        "stato_pagamento": "pagata",
                        "prima_nota_id": pn_id,
                        "prima_nota_tipo": suggerimento,
                    }}
                )
                auto_confermati += 1
            else:
                await db["invoices"].update_one(
                    {"id": fatt_id},
                    {"$set": {"stato_pagamento": "pagata", "prima_nota_tipo": suggerimento}}
                )
        else:
            provvisori_finali.append(p)
    
    tot_cassa = sum(p["importo"] for p in provvisori_finali if p["suggerimento"] == "cassa")
    tot_banca = sum(p["importo"] for p in provvisori_finali if p["suggerimento"] == "banca")
    
    return {
        "provvisori": provvisori_finali,
        "totale": len(provvisori_finali),
        "totale_cassa": round(tot_cassa, 2),
        "totale_banca": round(tot_banca, 2),
        "confermati": sum(1 for p in provvisori_finali if p["stato_match"] == "confermato"),
        "probabili": sum(1 for p in provvisori_finali if p["stato_match"] == "probabile"),
        "in_attesa": sum(1 for p in provvisori_finali if p["stato_match"] == "in_attesa"),
        "auto_confermati_banca": auto_confermati,
    }


async def conferma_fattura_provvisoria(data: Dict = Body(...)) -> Dict:
    """
    Conferma una fattura provvisoria: registra in Prima Nota cassa/banca.
    Body: { fattura_id, metodo: "cassa"|"banca"|"sospesa", movimento_banca_id? }
    """
    db = Database.get_db()
    
    fattura_id = data.get("fattura_id")
    metodo = data.get("metodo", "banca")
    
    fattura = await db["invoices"].find_one({"id": fattura_id}, {"_id": 0})
    if not fattura:
        raise HTTPException(status_code=404, detail="Fattura non trovata")
    
    importo = float(fattura.get("total_amount", 0))
    fornitore = fattura.get("supplier_name", "")
    numero = fattura.get("invoice_number", "")
    data_fatt = fattura.get("invoice_date", "")
    
    # SOSPESA: non creare movimento in prima nota, solo aggiorna stato fattura
    if metodo == "sospesa":
        await db["invoices"].update_one(
            {"id": fattura_id},
            {"$set": {
                "stato_pagamento": "sospesa",
                "metodo_pagamento_effettivo": "sospesa",
                "prima_nota_tipo": "sospesa",
            },
            "$unset": {
                "prima_nota_id": "",
            }}
        )
        return {"success": True, "metodo": "sospesa", "importo": importo, "fornitore": fornitore,
                "message": "Fattura sospesa — resta nei provvisori"}
    
    pn_id = str(uuid.uuid4())
    collection = COLLECTION_PRIMA_NOTA_CASSA if metodo == "cassa" else COLLECTION_PRIMA_NOTA_BANCA
    
    # Dedup
    existing = await db[collection].find_one({"riferimento": f"FATT-{fattura_id}"})
    if existing:
        # Already registered - aggiorna fattura con prima_nota_id per escluderla dai provvisori
        await db["invoices"].update_one(
            {"id": fattura_id},
            {"$set": {
                "stato_pagamento": "pagata",
                "prima_nota_tipo": metodo,
                "prima_nota_id": existing.get("id", str(existing.get("_id", ""))),
            }}
        )
        return {"success": True, "message": "Già registrata"}
    
    movimento = {
        "id": pn_id,
        "data": data_fatt,
        "tipo": "uscita",
        "categoria": "Fatture",
        "descrizione": f"Fatt. {numero} - {fornitore[:30]}",
        "importo": importo,
        "riferimento": f"FATT-{fattura_id}",
        "fattura_id": fattura_id,
        "source": "conferma_provvisori",
        "created_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    }
    
    await db[collection].insert_one(movimento)
    
    # Update fattura
    await db["invoices"].update_one(
        {"id": fattura_id},
        {"$set": {
            "stato_pagamento": "pagata",
            "prima_nota_id": pn_id,
            "prima_nota_tipo": metodo,
            "payment_method": "contanti" if metodo == "cassa" else fattura.get("payment_method", "bonifico"),
        }}
    )
    
    return {"success": True, "metodo": metodo, "importo": importo, "fornitore": fornitore}



async def sposta_scrittura_prima_nota(data: Dict = Body(...)) -> Dict:
    """
    Sposta una scrittura da Cassa a Banca o viceversa.
    Quando l'utente cambia il metodo di pagamento, il sistema:
    1. Rimuove dalla collection originale
    2. Inserisce nella nuova collection
    3. Aggiorna la fattura collegata
    """
    db = Database.get_db()
    
    movimento_id = data.get("movimento_id")
    nuova_destinazione = data.get("destinazione")  # "cassa" o "banca"
    
    if nuova_destinazione not in ["cassa", "banca"]:
        raise HTTPException(status_code=400, detail="Destinazione deve essere 'cassa' o 'banca'")
    
    # Cerca il movimento in entrambe le collection
    movimento = None
    origine = None
    for coll in [COLLECTION_PRIMA_NOTA_CASSA, COLLECTION_PRIMA_NOTA_BANCA]:
        mov = await db[coll].find_one({"id": movimento_id})
        if mov:
            movimento = mov
            origine = "cassa" if "cassa" in coll else "banca"
            break
    
    if not movimento:
        raise HTTPException(status_code=404, detail="Movimento non trovato")
    
    if origine == nuova_destinazione:
        return {"success": True, "message": "Già nella destinazione corretta"}
    
    # Rimuovi dalla collection originale
    coll_origine = COLLECTION_PRIMA_NOTA_CASSA if origine == "cassa" else COLLECTION_PRIMA_NOTA_BANCA
    await db[coll_origine].delete_one({"id": movimento_id})
    
    # Inserisci nella nuova collection
    coll_dest = COLLECTION_PRIMA_NOTA_CASSA if nuova_destinazione == "cassa" else COLLECTION_PRIMA_NOTA_BANCA
    movimento.pop("_id", None)
    movimento["spostato_da"] = origine
    movimento["spostato_at"] = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    await db[coll_dest].insert_one(movimento)
    
    # Aggiorna la fattura collegata
    fattura_id = movimento.get("fattura_id")
    if fattura_id:
        metodo_label = "contanti" if nuova_destinazione == "cassa" else "bonifico"
        await db["invoices"].update_one(
            {"id": fattura_id},
            {"$set": {
                "prima_nota_tipo": nuova_destinazione,
                "payment_method": metodo_label,
            }}
        )
    
    return {
        "success": True,
        "spostato": f"{origine} → {nuova_destinazione}",
        "movimento_id": movimento_id,
        "importo": movimento.get("importo"),
    }




async def import_prima_nota_batch(data: Dict = Body(...)) -> Dict:
    """Importa batch di movimenti."""
    db = Database.get_db()
    
    created_cassa = 0
    created_banca = 0
    errors = []
    
    for mov in data.get("cassa", []):
        try:
            movimento = {
                "id": str(uuid.uuid4()),
                "data": mov["data"],
                "tipo": mov["tipo"],
                "importo": float(mov["importo"]),
                "descrizione": mov.get("descrizione", ""),
                "categoria": mov.get("categoria", "Altro"),
                "riferimento": mov.get("riferimento"),
                "fornitore_piva": mov.get("fornitore_piva"),
                "fattura_id": mov.get("fattura_id"),
                "source": mov.get("source", "excel_import"),
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            await db[COLLECTION_PRIMA_NOTA_CASSA].insert_one(movimento.copy())
            created_cassa += 1
        except Exception as e:
            errors.append(f"Cassa: {str(e)}")
    
    for mov in data.get("banca", []):
        try:
            movimento = {
                "id": str(uuid.uuid4()),
                "data": mov["data"],
                "tipo": mov["tipo"],
                "importo": float(mov["importo"]),
                "descrizione": mov.get("descrizione", ""),
                "categoria": mov.get("categoria", "Altro"),
                "riferimento": mov.get("riferimento"),
                "fornitore_piva": mov.get("fornitore_piva"),
                "fattura_id": mov.get("fattura_id"),
                "source": mov.get("source", "excel_import"),
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            await db[COLLECTION_PRIMA_NOTA_BANCA].insert_one(movimento.copy())
            created_banca += 1
        except Exception as e:
            errors.append(f"Banca: {str(e)}")
    
    return {
        "message": "Import completato",
        "cassa_created": created_cassa,
        "banca_created": created_banca,
        "errors": errors[:10]
    }


async def create_movimento_generico(data: Dict = Body(...)) -> Dict:
    """Crea un movimento Prima Nota generico (cassa o banca)."""
    db = Database.get_db()
    
    tipo_nota = data.get("tipo", "banca")
    tipo_movimento = data.get("tipo_movimento", "entrata")
    
    required = ["data", "importo", "descrizione"]
    for field in required:
        if field not in data:
            raise HTTPException(status_code=400, detail=f"Campo obbligatorio mancante: {field}")
    
    movimento = {
        "id": str(uuid.uuid4()),
        "data": data["data"],
        "tipo": tipo_movimento,
        "importo": float(data["importo"]),
        "descrizione": data["descrizione"],
        "categoria": data.get("categoria", "Altro"),
        "riferimento": data.get("riferimento"),
        "fornitore_piva": data.get("fornitore_piva"),
        "fonte": data.get("fonte", "manual_entry"),
        "riconciliato": data.get("riconciliato", False),
        "note": data.get("note"),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    collection = COLLECTION_PRIMA_NOTA_BANCA if tipo_nota == "banca" else COLLECTION_PRIMA_NOTA_CASSA
    await db[collection].insert_one(movimento.copy())
    
    return {"message": f"Movimento {tipo_nota} creato", "id": movimento["id"]}


async def collega_fatture_movimenti() -> Dict:
    """Collega automaticamente fatture ai movimenti."""
    db = Database.get_db()
    
    collegati = 0
    
    for coll in [COLLECTION_PRIMA_NOTA_CASSA, COLLECTION_PRIMA_NOTA_BANCA]:
        cursor = db[coll].find({
            "numero_fattura": {"$exists": True, "$nin": [None, ""]},
            "fattura_id": {"$in": [None, ""]}
        })
        
        async for mov in cursor:
            numero_fattura = mov.get("numero_fattura", "")
            if not numero_fattura:
                continue
            
            fattura = await db["invoices"].find_one({
                "$or": [
                    {"numero": numero_fattura},
                    {"invoice_number": numero_fattura},
                    {"numero_fattura": numero_fattura}
                ]
            }, {"_id": 0, "id": 1})
            
            if fattura:
                await db[coll].update_one(
                    {"id": mov["id"]},
                    {"$set": {"fattura_id": fattura["id"]}}
                )
                collegati += 1
    
    return {"success": True, "movimenti_collegati": collegati}


async def auto_conferma_provvisori_per_metodo(
    anno: int = Query(..., description="Anno da processare"),
) -> Dict[str, Any]:
    """Auto-confermazione bulk delle fatture provvisorie basata sul metodo pagamento
    dell'anagrafica fornitore.

    REGOLE (come da specifiche utente):
      - Fornitore con metodo 'cassa' o 'contanti'
          → tutte le fatture (pagate o no) vanno in Prima Nota CASSA
      - Fornitore con metodo 'banca' o 'bonifico'
          → solo le fatture PAGATE vanno in Prima Nota BANCA
          → le fatture NON pagate restano in Provvisoria (aspettano il match EC)
      - Fornitore con metodo 'paypal', 'carta', 'carta_di_credito', 'misto'
          → restano in Provvisoria (aspettano EC PayPal / carta)
      - Fornitore senza metodo in anagrafica
          → resta in Provvisoria

    Ogni movimento creato viene marcato con source='auto_confirm_provvisoria' in
    modo da essere identificabile per rollback.

    Idempotente: se una fattura è già in Prima Nota (prima_nota_id valorizzato
    oppure esiste un movimento con riferimento FATT-{id}), viene saltata.
    """
    db = Database.get_db()
    now = datetime.now(timezone.utc).isoformat()

    # Carica il dizionario metodo-per-piva dall'anagrafica fornitori
    metodo_per_piva: Dict[str, str] = {}
    async for s in db["fornitori"].find(
        {"metodo_pagamento": {"$exists": True, "$ne": ""}},
        {"_id": 0, "partita_iva": 1, "metodo_pagamento": 1}
    ):
        piva = (s.get("partita_iva") or "").strip()
        metodo = (s.get("metodo_pagamento") or "").strip().lower()
        if piva and metodo:
            metodo_per_piva[piva] = metodo

    # Fatture provvisorie dell'anno
    fatture = await db["invoices"].find(
        {
            "invoice_date": {"$regex": f"^{anno}"},
            "total_amount": {"$gt": 0},
            "$or": [
                {"prima_nota_id": None},
                {"prima_nota_id": ""},
                {"prima_nota_id": {"$exists": False}},
            ],
            "stato_pagamento": {"$nin": ["sospesa"]},  # le sospese non le tocco
        },
        {"_id": 0, "xml_raw": 0, "linee": 0}
    ).to_list(5000)

    report = {
        "anno": anno,
        "totali_provvisorie_analizzate": len(fatture),
        "mosse_cassa": 0,
        "mosse_banca": 0,
        "restate_in_provvisoria_banca_non_pagata": 0,
        "restate_in_provvisoria_paypal_o_carta": 0,
        "restate_in_provvisoria_fornitore_senza_metodo": 0,
        "skipped_gia_in_prima_nota": 0,
        "skipped_errori": [],
        "dettaglio_mosse": [],  # prime 100 per log
    }

    for f in fatture:
        try:
            fid = f.get("id") or f.get("invoice_key")
            if not fid:
                continue

            piva = (f.get("supplier_vat") or f.get("cedente_piva") or "").strip()
            stato_pagamento = (f.get("stato_pagamento") or "").lower()
            pagata = stato_pagamento in ("pagata", "paid")

            # Dedup sicuro: se esiste già un movimento in cassa o banca per
            # questa fattura, non tocco nulla (può esserci stato movimento
            # manuale). Aggiorno solo il flag sulla fattura per toglierla dai
            # provvisori.
            rif = f"FATT-{fid}"
            existing_cassa = await db[COLLECTION_PRIMA_NOTA_CASSA].find_one({
                "$or": [{"riferimento": rif}, {"fattura_id": fid}],
                "status": {"$nin": ["deleted", "archived"]},
            })
            existing_banca = await db[COLLECTION_PRIMA_NOTA_BANCA].find_one({
                "$or": [{"riferimento": rif}, {"fattura_id": fid}],
                "status": {"$nin": ["deleted", "archived"]},
            })
            if existing_cassa or existing_banca:
                existing = existing_cassa or existing_banca
                tipo_pn = "cassa" if existing_cassa else "banca"
                await db["invoices"].update_one(
                    {"id": fid},
                    {"$set": {
                        "prima_nota_id": existing.get("id"),
                        "prima_nota_tipo": tipo_pn,
                        "stato_pagamento": "pagata" if pagata else stato_pagamento,
                    }}
                )
                report["skipped_gia_in_prima_nota"] += 1
                continue

            metodo = metodo_per_piva.get(piva, "")

            # --- APPLICA REGOLE ---
            destinazione = None

            if metodo in ("cassa", "contanti"):
                # Regola: cassa → sempre in Prima Nota Cassa, pagata o no
                destinazione = "cassa"
            elif metodo in ("banca", "bonifico", "riba", "sepa"):
                # Regola: banca → solo se pagata
                if pagata:
                    destinazione = "banca"
                else:
                    report["restate_in_provvisoria_banca_non_pagata"] += 1
                    continue
            elif metodo in ("paypal", "carta", "carta_di_credito", "carta_credito", "misto"):
                # Regola: paypal/carta → sempre in provvisoria, aspettano EC
                report["restate_in_provvisoria_paypal_o_carta"] += 1
                continue
            else:
                # Fornitore senza metodo in anagrafica
                report["restate_in_provvisoria_fornitore_senza_metodo"] += 1
                continue

            # --- CREA MOVIMENTO ---
            collection = COLLECTION_PRIMA_NOTA_CASSA if destinazione == "cassa" else COLLECTION_PRIMA_NOTA_BANCA
            importo = float(f.get("total_amount") or f.get("importo_totale") or 0)
            numero = f.get("invoice_number") or f.get("numero_fattura") or "N/A"
            fornitore = f.get("supplier_name") or f.get("cedente_denominazione") or "Fornitore"
            data_fatt = f.get("invoice_date") or f.get("data_fattura") or now[:10]

            tipo_mov, cat, desc_prefix = determina_tipo_movimento_fattura(f)

            pn_id = str(uuid.uuid4())
            movimento = {
                "id": pn_id,
                "data": data_fatt,
                "tipo": tipo_mov,
                "categoria": cat,
                "descrizione": f"{desc_prefix} {numero} - {fornitore[:40]}",
                "importo": round(importo, 2),
                "riferimento": rif,
                "numero_fattura": numero,
                "fornitore_piva": piva,
                "fattura_id": fid,
                "source": "auto_confirm_provvisoria",  # marker per rollback
                "auto_confirm_meta": {
                    "metodo_fornitore": metodo,
                    "stato_pagamento_al_momento": stato_pagamento,
                    "operazione_id": now,  # stessa per tutti i mov della stessa run
                },
                "created_at": now,
            }
            await db[collection].insert_one(movimento.copy())

            # Aggiorna la fattura
            update_data = {
                "prima_nota_id": pn_id,
                "prima_nota_tipo": destinazione,
                "metodo_pagamento_effettivo": metodo,
            }
            if destinazione == "cassa" or pagata:
                update_data["stato_pagamento"] = "pagata"
                if not f.get("data_pagamento"):
                    update_data["data_pagamento"] = now[:10]

            await db["invoices"].update_one({"id": fid}, {"$set": update_data})

            if destinazione == "cassa":
                report["mosse_cassa"] += 1
            else:
                report["mosse_banca"] += 1

            if len(report["dettaglio_mosse"]) < 100:
                report["dettaglio_mosse"].append({
                    "fattura_id": fid,
                    "numero": numero,
                    "fornitore": fornitore[:60],
                    "metodo_fornitore": metodo,
                    "destinazione": destinazione,
                    "importo": round(importo, 2),
                    "pn_id": pn_id,
                })

        except Exception as e:
            logger.exception(f"Errore auto-conferma fattura {f.get('id')}: {e}")
            report["skipped_errori"].append({
                "fattura_id": f.get("id"),
                "errore": str(e)[:200],
            })

    return {
        "success": True,
        "rollback_endpoint": "POST /api/prima-nota/annulla-auto-conferma (con parametro operazione_id se vuoi annullare solo questa run)",
        **report,
    }


async def annulla_auto_conferma(
    operazione_id: Optional[str] = Query(None, description="Se fornito annulla solo i movimenti di quella operazione; altrimenti annulla TUTTI i movimenti auto-confirm"),
) -> Dict[str, Any]:
    """Rollback dell'operazione auto_conferma_provvisori_per_metodo.

    Se operazione_id è fornito, annulla solo quella run specifica.
    Altrimenti annulla TUTTI i movimenti con source='auto_confirm_provvisoria'.

    Il rollback:
      1. Soft-delete dei movimenti (status='deleted') — reversibile dal DB
      2. Riporta le fatture allo stato prima-nota-id vuoto + stato_pagamento
         al valore precedente (salvato in auto_confirm_meta.stato_pagamento_al_momento)
    """
    db = Database.get_db()
    now = datetime.now(timezone.utc).isoformat()

    filtro: Dict[str, Any] = {
        "source": "auto_confirm_provvisoria",
        "status": {"$nin": ["deleted", "archived"]},
    }
    if operazione_id:
        filtro["auto_confirm_meta.operazione_id"] = operazione_id

    movimenti_cassa = await db[COLLECTION_PRIMA_NOTA_CASSA].find(filtro, {"_id": 0}).to_list(10000)
    movimenti_banca = await db[COLLECTION_PRIMA_NOTA_BANCA].find(filtro, {"_id": 0}).to_list(10000)

    ids_cassa = [m["id"] for m in movimenti_cassa]
    ids_banca = [m["id"] for m in movimenti_banca]
    fatture_ids = list({m.get("fattura_id") for m in (movimenti_cassa + movimenti_banca) if m.get("fattura_id")})

    # Soft-delete movimenti
    if ids_cassa:
        await db[COLLECTION_PRIMA_NOTA_CASSA].update_many(
            {"id": {"$in": ids_cassa}},
            {"$set": {"status": "deleted", "deleted_at": now, "deleted_reason": "rollback_auto_confirm"}}
        )
    if ids_banca:
        await db[COLLECTION_PRIMA_NOTA_BANCA].update_many(
            {"id": {"$in": ids_banca}},
            {"$set": {"status": "deleted", "deleted_at": now, "deleted_reason": "rollback_auto_confirm"}}
        )

    # Ripristina le fatture: ciclo uno per uno per ripristinare il giusto stato_pagamento
    fatture_ripristinate = 0
    for m in movimenti_cassa + movimenti_banca:
        fid = m.get("fattura_id")
        if not fid:
            continue
        stato_originale = (m.get("auto_confirm_meta") or {}).get("stato_pagamento_al_momento", "")
        set_ops = {"prima_nota_id": "", "prima_nota_tipo": ""}
        if stato_originale:
            set_ops["stato_pagamento"] = stato_originale
        await db["invoices"].update_one({"id": fid}, {"$set": set_ops})
        fatture_ripristinate += 1

    return {
        "success": True,
        "operazione_id": operazione_id,
        "movimenti_cassa_annullati": len(ids_cassa),
        "movimenti_banca_annullati": len(ids_banca),
        "fatture_ripristinate_a_provvisoria": fatture_ripristinate,
    }

async def crea_entrata_cassa_da_corrispettivo(
    data: str = Query(..., description="Data corrispettivo YYYY-MM-DD"),
    includi_uscita_pos: bool = Query(True, description="Se True crea anche l'uscita POS (battuto serale)"),
) -> Dict[str, Any]:
    """Crea manualmente l'entrata in Prima Nota Cassa dal corrispettivo XML già importato.

    Utilizzo previsto: l'operatore la sera non ha tempo di inserire l'entrata
    cassa a mano, preme questo bottone (dalla UI) e il sistema crea:
      - Entrata in Prima Nota Cassa = totale corrispettivo (contanti + POS)
      - Uscita in Prima Nota Cassa = pagato_elettronico (solo se includi_uscita_pos=True)

    Idempotente: se esistono già movimenti con source='manuale_da_xml' + corrispettivo_id
    per questa data, non li duplica.

    NOTA: questo endpoint è SOLO per il flusso opzionale manuale. Il flusso
    normale è che l'utente inserisca i movimenti a mano la sera; l'XML serve
    solo per controllo coerenza POS.
    """
    db = Database.get_db()
    now = datetime.now(timezone.utc).isoformat()

    # Cerca il corrispettivo per quella data
    corrispettivo = await db["corrispettivi"].find_one({"data": data}, {"_id": 0})
    if not corrispettivo:
        raise HTTPException(
            status_code=404,
            detail=f"Nessun corrispettivo trovato per la data {data}. Importa prima l'XML del registratore telematico."
        )

    corr_id = corrispettivo.get("id")
    if not corr_id:
        raise HTTPException(status_code=400, detail="Corrispettivo senza id, impossibile deduplicare")

    # Idempotenza: se esiste già un movimento da questo endpoint per il corrispettivo, non duplicare
    existing_entrata = await db[COLLECTION_PRIMA_NOTA_CASSA].find_one({
        "corrispettivo_id": corr_id,
        "source": "manuale_da_xml",
        "tipo": "entrata",
        "status": {"$nin": ["deleted", "archived"]},
    })
    if existing_entrata:
        return {
            "success": True,
            "duplicato": True,
            "message": f"Movimenti per il {data} già creati in precedenza (id: {existing_entrata.get('id')})",
        }

    # Estrai valori dal corrispettivo (tolleranti a schema legacy)
    contanti = float(corrispettivo.get("pagato_contanti", 0) or 0)
    elettronico = float(
        corrispettivo.get("pagato_pos", 0)
        or corrispettivo.get("pagato_elettronico", 0)
        or 0
    )
    totale = float(
        corrispettivo.get("totale", 0)
        or corrispettivo.get("totale_complessivo", 0)
        or (contanti + elettronico)
        or 0
    )

    if totale <= 0:
        raise HTTPException(
            status_code=400,
            detail=f"Corrispettivo {data} ha totale 0. Verifica l'XML importato."
        )

    risultati = {"entrata_cassa_id": None, "uscita_pos_id": None}

    # 1) ENTRATA CASSA = totale corrispettivo
    entrata_id = str(uuid.uuid4())
    movimento_entrata = {
        "id": entrata_id,
        "data": data,
        "tipo": "entrata",
        "categoria": "Corrispettivi",
        "descrizione": f"Corrispettivi {data} (da XML)",
        "importo": round(totale, 2),
        "corrispettivo_id": corr_id,
        "pagato_contanti": round(contanti, 2),
        "pagato_elettronico": round(elettronico, 2),
        "totale_giornata": round(totale, 2),
        "source": "manuale_da_xml",
        "created_at": now,
    }
    await db[COLLECTION_PRIMA_NOTA_CASSA].insert_one(movimento_entrata.copy())
    risultati["entrata_cassa_id"] = entrata_id

    # 2) USCITA CASSA = quota POS (opzionale)
    if includi_uscita_pos and elettronico > 0:
        uscita_id = str(uuid.uuid4())
        movimento_uscita = {
            "id": uscita_id,
            "data": data,
            "tipo": "uscita",
            "categoria": "POS Verso Banca",
            "descrizione": f"Battuto POS {data} (da XML) → Banca",
            "importo": round(elettronico, 2),
            "corrispettivo_id": corr_id,
            "source": "manuale_da_xml",
            "created_at": now,
        }
        await db[COLLECTION_PRIMA_NOTA_CASSA].insert_one(movimento_uscita.copy())
        risultati["uscita_pos_id"] = uscita_id

    return {
        "success": True,
        "duplicato": False,
        "data": data,
        "totale_corrispettivo": round(totale, 2),
        "contanti": round(contanti, 2),
        "elettronico": round(elettronico, 2),
        "include_uscita_pos": includi_uscita_pos and elettronico > 0,
        **risultati,
        "message": f"Movimenti creati in Prima Nota Cassa per il {data}. Sono annullabili normalmente dalla pagina Prima Nota.",
    }
