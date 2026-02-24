"""
Servizio di Automazione Completa - Flusso Documenti
====================================================

Questo servizio gestisce l'automazione completa del flusso documentale:

1. EMAIL ARUBA → OPERAZIONI DA CONFERMARE
   - Scarica notifiche fatture da Aruba
   - Estrae: fornitore, numero fattura, importo
   - Salva in operazioni_da_confermare
   - L'utente decide: Cassa o Banca

2. FATTURE XML → MAGAZZINO + RICETTE
   - Quando arrivano fatture XML, aggiorna automaticamente:
     * Magazzino (prezzi e giacenze)
     * Ricette (food cost con nuovi prezzi)
   - Completa operazioni da confermare se presenti

3. RICONCILIAZIONE AUTOMATICA
   - Cerca match tra operazioni confermate e fatture XML
   - Aggiorna Prima Nota con dati completi

IMPORTANTE: 
- Tutto aggiornato entro 10 minuti (intervallo monitor)
- I duplicati vengono SEMPRE saltati
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, List
import os

logger = logging.getLogger(__name__)


async def fetch_aruba_emails_to_operazioni(db, giorni: int = 30) -> Dict[str, Any]:
    """
    Scarica email da Aruba e crea operazioni da confermare.
    
    Returns:
        Dict con statistiche download
    """
    from app.services.aruba_invoice_parser import fetch_aruba_invoices
    
    email_user = os.environ.get("EMAIL_USER")
    email_password = os.environ.get("EMAIL_APP_PASSWORD") or os.environ.get("EMAIL_PASSWORD")
    
    if not email_user or not email_password:
        logger.warning("Credenziali email non configurate per Aruba")
        return {"success": False, "error": "Credenziali email non configurate"}
    
    try:
        result = await fetch_aruba_invoices(
            db=db,
            email_user=email_user,
            email_password=email_password,
            since_days=giorni
        )
        
        stats = result.get("stats", {})
        logger.info(f"📧 Aruba sync: {stats.get('new_invoices', 0)} nuove, {stats.get('duplicates_skipped', 0)} duplicati")
        
        return result
    except Exception as e:
        logger.error(f"Errore fetch Aruba: {e}")
        return {"success": False, "error": str(e)}


async def aggiorna_prezzi_ricette(db, product_ids: List[str] = None) -> Dict[str, Any]:
    """
    Aggiorna i food cost delle ricette con i nuovi prezzi dal magazzino.
    
    Se product_ids è specificato, aggiorna solo le ricette che usano quei prodotti.
    Altrimenti aggiorna tutte le ricette.
    
    Returns:
        Dict con statistiche aggiornamento
    """
    result = {
        "ricette_aggiornate": 0,
        "ricette_totali": 0,
        "errori": []
    }
    
    try:
        # Trova tutte le ricette attive
        query = {"attivo": True}
        
        ricette = await db["ricette"].find(query, {"_id": 0}).to_list(1000)
        result["ricette_totali"] = len(ricette)
        
        for ricetta in ricette:
            try:
                ricetta_id = ricetta.get("id")
                ingredienti = ricetta.get("ingredienti", [])
                
                if not ingredienti:
                    continue
                
                # Se product_ids specificato, controlla se la ricetta usa quei prodotti
                if product_ids:
                    ingredienti_ids = [ing.get("prodotto_id") for ing in ingredienti]
                    if not any(pid in ingredienti_ids for pid in product_ids):
                        continue
                
                # Calcola nuovo food cost
                nuovo_food_cost = 0.0
                ingredienti_aggiornati = []
                aggiornato = False
                
                for ing in ingredienti:
                    prodotto_id = ing.get("prodotto_id")
                    quantita = ing.get("quantita", 0)
                    
                    # Cerca prezzo aggiornato dal magazzino
                    prodotto = await db["warehouse_inventory"].find_one(
                        {"id": prodotto_id},
                        {"_id": 0, "prezzi": 1, "nome": 1}
                    )
                    
                    if prodotto:
                        prezzo_unitario = prodotto.get("prezzi", {}).get("avg", 0)
                        vecchio_prezzo = ing.get("prezzo_unitario", 0)
                        
                        # Se prezzo cambiato, aggiorna
                        if abs(prezzo_unitario - vecchio_prezzo) > 0.001:
                            aggiornato = True
                            ing["prezzo_unitario"] = prezzo_unitario
                            ing["prezzo_aggiornato_at"] = datetime.now(timezone.utc).isoformat()
                        
                        costo_ingrediente = quantita * prezzo_unitario
                        ing["costo_totale"] = round(costo_ingrediente, 4)
                        nuovo_food_cost += costo_ingrediente
                    
                    ingredienti_aggiornati.append(ing)
                
                # Aggiorna ricetta se ci sono cambiamenti
                if aggiornato:
                    await db["ricette"].update_one(
                        {"id": ricetta_id},
                        {"$set": {
                            "ingredienti": ingredienti_aggiornati,
                            "food_cost": round(nuovo_food_cost, 2),
                            "food_cost_updated_at": datetime.now(timezone.utc).isoformat()
                        }}
                    )
                    result["ricette_aggiornate"] += 1
                    
            except Exception as e:
                result["errori"].append(f"Ricetta {ricetta.get('nome', 'N/A')}: {e}")
        
        if result["ricette_aggiornate"] > 0:
            logger.info(f"🍳 Aggiornate {result['ricette_aggiornate']} ricette con nuovi prezzi")
        
    except Exception as e:
        logger.error(f"Errore aggiornamento ricette: {e}")
        result["errori"].append(str(e))
    
    return result


async def completa_operazione_con_xml(db, fattura_data: Dict[str, Any], fattura_id: str) -> Dict[str, Any]:
    """
    Quando arriva una fattura XML, cerca se esiste un'operazione da confermare
    corrispondente e la completa.
    
    Logica:
    1. Cerca operazione con stesso fornitore + numero fattura + importo simile
    2. Se trovata e confermata → aggiorna Prima Nota con dati completi
    3. Se trovata ma non confermata → aggiorna operazione con ID fattura
    
    Returns:
        Dict con risultato completamento
    """
    result = {
        "operazione_trovata": False,
        "operazione_completata": False,
        "prima_nota_aggiornata": False,
        "operazione_id": None
    }
    
    try:
        # Estrai dati fattura
        fornitore = fattura_data.get("supplier_name", "")
        numero_fattura = fattura_data.get("invoice_number", "")
        importo = float(fattura_data.get("total_amount", 0) or 0)
        
        if not fornitore or not numero_fattura:
            return result
        
        # Cerca operazione corrispondente
        # Match per numero fattura (esatto) e importo (tolleranza ±1€)
        query = {
            "numero_fattura": numero_fattura,
            "$or": [
                {"importo": {"$gte": importo - 1, "$lte": importo + 1}},
                {"netto_pagare": {"$gte": importo - 1, "$lte": importo + 1}}
            ]
        }
        
        operazione = await db["operazioni_da_confermare"].find_one(query, {"_id": 0})
        
        if not operazione:
            # Prova match solo per fornitore + importo
            fornitore_words = fornitore.split()[:2]  # Prime 2 parole
            query_alt = {
                "fornitore": {"$regex": "|".join(fornitore_words[:1]), "$options": "i"},
                "importo": {"$gte": importo - 1, "$lte": importo + 1}
            }
            operazione = await db["operazioni_da_confermare"].find_one(query_alt, {"_id": 0})
        
        if operazione:
            result["operazione_trovata"] = True
            result["operazione_id"] = operazione.get("id")
            
            # Aggiorna operazione con riferimento fattura XML
            await db["operazioni_da_confermare"].update_one(
                {"id": operazione["id"]},
                {"$set": {
                    "fattura_xml_id": fattura_id,
                    "fattura_xml_numero": numero_fattura,
                    "completato_con_xml": True,
                    "completato_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            
            # Se operazione era già confermata, aggiorna Prima Nota
            if operazione.get("stato") == "confermato":
                prima_nota_id = operazione.get("prima_nota_id")
                metodo = operazione.get("metodo_pagamento_confermato") or operazione.get("metodo_pagamento")
                
                if prima_nota_id and metodo:
                    collection = "prima_nota_cassa" if metodo == "cassa" else "prima_nota_banca"
                    
                    await db[collection].update_one(
                        {"id": prima_nota_id},
                        {"$set": {
                            "fattura_xml_id": fattura_id,
                            "completato_con_xml": True,
                            "updated_at": datetime.now(timezone.utc).isoformat()
                        }}
                    )
                    result["prima_nota_aggiornata"] = True
                
                result["operazione_completata"] = True
                logger.info(f"✅ Operazione {operazione['id']} completata con XML fattura {fattura_id}")
        
    except Exception as e:
        logger.error(f"Errore completamento operazione: {e}")
    
    return result


async def processa_fattura_con_automazioni(db, fattura_data: Dict[str, Any], fattura_id: str) -> Dict[str, Any]:
    """
    Processa una fattura XML con TUTTE le automazioni:
    1. Popola magazzino
    2. Aggiorna ricette
    3. Completa operazioni da confermare
    
    Chiamare questa funzione ogni volta che viene caricata una fattura XML.
    
    Returns:
        Dict con risultati di tutte le automazioni
    """
    from app.utils.warehouse_helpers import auto_populate_warehouse_from_invoice
    
    result = {
        "magazzino": None,
        "ricette": None,
        "operazione": None,
        "errori": []
    }
    
    try:
        # 1. Popola magazzino
        try:
            magazzino_result = await auto_populate_warehouse_from_invoice(db, fattura_data, fattura_id)
            result["magazzino"] = magazzino_result
            
            # Raccogli ID prodotti aggiornati per aggiornare ricette
            product_ids = []
            if magazzino_result.get("products_created", 0) > 0 or magazzino_result.get("products_updated", 0) > 0:
                # Trova i prodotti aggiornati da questa fattura
                recent_products = await db["warehouse_inventory"].find(
                    {"ultimo_acquisto": fattura_data.get("data_fattura", "")},
                    {"_id": 0, "id": 1}
                ).to_list(100)
                product_ids = [p["id"] for p in recent_products]
                
        except Exception as e:
            result["errori"].append(f"Magazzino: {e}")
            product_ids = []
        
        # 2. Aggiorna ricette con nuovi prezzi
        try:
            if product_ids:
                ricette_result = await aggiorna_prezzi_ricette(db, product_ids)
                result["ricette"] = ricette_result
        except Exception as e:
            result["errori"].append(f"Ricette: {e}")
        
        # 3. Completa operazioni da confermare
        try:
            operazione_result = await completa_operazione_con_xml(db, fattura_data, fattura_id)
            result["operazione"] = operazione_result
        except Exception as e:
            result["errori"].append(f"Operazione: {e}")
        
        logger.info(f"📦 Fattura {fattura_id} processata - Mag:{result['magazzino']}, Ric:{result['ricette']}")
        
    except Exception as e:
        logger.error(f"Errore automazioni fattura: {e}")
        result["errori"].append(str(e))
    
    return result


async def sync_completo_automatico(db) -> Dict[str, Any]:
    """
    Esegue un ciclo completo di sincronizzazione automatica:
    
    1. Scarica email documenti (F24, buste paga, estratti conto)
    2. Scarica notifiche fatture Aruba → operazioni da confermare
    3. Processa nuovi documenti
    4. Aggiorna ricette se ci sono nuovi prezzi
    
    Chiamato ogni 10 minuti dal monitor.
    """
    results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "email_documenti": None,
        "email_aruba": None,
        "documenti_processati": None,
        "ricette_aggiornate": None,
        "errori": []
    }
    
    try:
        # 1. Scarica documenti email (già implementato nel monitor)
        from app.services.email_monitor_service import sync_email_documents, processa_nuovi_documenti
        
        results["email_documenti"] = await sync_email_documents(db, giorni=1)
        
        # 2. Scarica notifiche Aruba
        results["email_aruba"] = await fetch_aruba_emails_to_operazioni(db, giorni=7)
        
        # 3. Processa documenti
        results["documenti_processati"] = await processa_nuovi_documenti(db)
        
        # 4. Aggiorna tutte le ricette con ultimi prezzi (ogni giorno)
        # Solo se ci sono stati aggiornamenti al magazzino
        mag_result = results.get("documenti_processati", {})
        if mag_result.get("buste_paga", 0) > 0 or mag_result.get("estratti_nexi", 0) > 0:
            results["ricette_aggiornate"] = await aggiorna_prezzi_ricette(db)
        
        logger.info("✅ Sync completo automatico completato")
        
    except Exception as e:
        logger.error(f"Errore sync completo: {e}")
        results["errori"].append(str(e))
    
    return results


# ============== HELPER PER INTEGRAZIONE ==============

async def get_operazioni_pendenti(db, anno: int = None) -> List[Dict[str, Any]]:
    """
    Restituisce operazioni da confermare pendenti.
    """
    query = {"stato": "da_confermare"}
    if anno:
        query["anno"] = anno
    
    operazioni = await db["operazioni_da_confermare"].find(
        query, 
        {"_id": 0}
    ).sort("created_at", -1).to_list(500)
    
    return operazioni


async def conferma_operazione_multipla(
    db, 
    operazione_ids: List[str], 
    metodo: str,
    note: str = None
) -> Dict[str, Any]:
    """
    Conferma multiple operazioni con lo stesso metodo.
    
    Args:
        operazione_ids: Lista ID operazioni
        metodo: "cassa" o "banca"
        note: Note opzionali
    
    Returns:
        Dict con statistiche conferma
    """
    import uuid
    
    result = {
        "confermate": 0,
        "errori": [],
        "prima_nota_ids": []
    }
    
    for op_id in operazione_ids:
        try:
            operazione = await db["operazioni_da_confermare"].find_one(
                {"id": op_id},
                {"_id": 0}
            )
            
            if not operazione:
                result["errori"].append(f"{op_id}: non trovata")
                continue
            
            if operazione.get("stato") == "confermato":
                result["errori"].append(f"{op_id}: già confermata")
                continue
            
            # Crea movimento in Prima Nota
            movimento_id = str(uuid.uuid4())
            importo = operazione.get("importo", 0)
            fornitore = operazione.get("fornitore", "")
            numero_fattura = operazione.get("numero_fattura", "")
            data_documento = operazione.get("data_documento") or datetime.now(timezone.utc).strftime("%Y-%m-%d")
            
            # Cerca fattura collegata per ottenere fattura_id
            fattura_id = None
            fattura = await db["invoices"].find_one({
                "$or": [
                    {"numero_fattura": numero_fattura},
                    {"invoice_number": numero_fattura}
                ]
            }, {"_id": 0, "id": 1})
            if fattura:
                fattura_id = fattura.get("id")
            
            movimento = {
                "id": movimento_id,
                "data": data_documento,
                "tipo": "uscita",
                "importo": abs(importo),
                "descrizione": f"Fattura {numero_fattura} - {fornitore}",
                "categoria": "Pagamento fornitore",
                "fornitore": fornitore,
                "numero_fattura": numero_fattura,
                "fattura_id": fattura_id,
                "data_fattura": data_documento,
                "operazione_aruba_id": op_id,
                "source": "aruba_batch_conferma",
                "note": note,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            
            # Salva nella collection CORRETTA
            if metodo == "cassa":
                collection = "prima_nota_cassa"
            else:
                collection = "prima_nota_banca"
                movimento["metodo_pagamento"] = metodo
            
            await db[collection].insert_one(movimento.copy())
            
            # Aggiorna operazione
            await db["operazioni_da_confermare"].update_one(
                {"id": op_id},
                {"$set": {
                    "stato": "confermato",
                    "metodo_pagamento": metodo,
                    "prima_nota_id": movimento_id,
                    "prima_nota_collection": collection,
                    "confirmed_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            
            # CASCATA: Aggiorna fattura se trovata
            if fattura_id:
                await db["invoices"].update_one(
                    {"id": fattura_id},
                    {"$set": {
                        "stato_pagamento": "pagato",
                        "pagato": True,
                        "data_pagamento": data_documento,
                        "metodo_pagamento": metodo,
                        "prima_nota_id": movimento_id
                    }}
                )
            
            # CASCATA: Aggiorna scadenza se esiste
            await db["scadenze"].update_many(
                {
                    "$or": [
                        {"fattura_id": fattura_id},
                        {"numero_fattura": numero_fattura, "fornitore": {"$regex": fornitore[:20], "$options": "i"}}
                    ],
                    "pagato": {"$ne": True}
                },
                {"$set": {
                    "pagato": True,
                    "data_pagamento": data_documento,
                    "prima_nota_id": movimento_id
                }}
            )
            
            result["confermate"] += 1
            result["prima_nota_ids"].append(movimento_id)
            
        except Exception as e:
            logger.error(f"Errore conferma {op_id}: {e}")
            result["errori"].append(f"{op_id}: {e}")
    
    return result
