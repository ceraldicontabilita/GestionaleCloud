"""
Riconciliazione Completa — Ceraldi ERP
========================================
Riconcilia documenti Gmail con estratto conto bancario:
- PagoPA (avvisi pagamento Comune di Napoli)
- Cartelle Agenzia Entrate
- Cartelle Agenzia Riscossione (ADER)
- TARI (tassa rifiuti)
- Confronto POS corrispettivi vs inserimento manuale
"""
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


async def riconcilia_pagopa_con_banca(db) -> Dict[str, Any]:
    """
    Riconcilia avvisi PagoPA (da Gmail Partenopay/Comune di Napoli)
    con movimenti bancari che contengono keyword PagoPA.
    """
    stats = {"analizzati": 0, "riconciliati": 0, "non_trovati": 0}
    
    # Documenti PagoPA da Gmail
    docs = await db["documenti_non_associati"].find(
        {"categoria_mittente": "Comune di Napoli", "riconciliato": {"$ne": True}},
        {"_id": 0, "pdf_data": 0}
    ).to_list(200)
    
    stats["analizzati"] = len(docs)
    
    for doc in docs:
        filename = doc.get("filename", "").lower()
        subject = doc.get("email_subject", "").lower()
        
        # Estrai numero avviso o IUV dal filename
        iuv_match = re.search(r'(\d{15,18})', doc.get("filename", ""))
        importo_match = re.search(r'(\d+[.,]\d{2})', subject)
        
        # Cerca in estratto conto
        search_terms = []
        if iuv_match:
            search_terms.append(iuv_match.group(1))
        search_terms.extend(["pagopa", "partenopay", "comune.*napol"])
        
        for term in search_terms:
            mov = await db["estratto_conto_movimenti"].find_one(
                {"descrizione": {"$regex": term, "$options": "i"}},
                {"_id": 0}
            )
            if mov:
                await db["documenti_non_associati"].update_one(
                    {"id": doc["id"]},
                    {"$set": {
                        "riconciliato": True,
                        "riconciliato_con": "estratto_conto",
                        "movimento_banca_id": mov.get("id"),
                        "data_pagamento": mov.get("data_contabile"),
                        "importo_pagato": abs(float(mov.get("importo", 0))),
                    }}
                )
                stats["riconciliati"] += 1
                break
        else:
            stats["non_trovati"] += 1
    
    logger.info(f"[RICONCILIA-PAGOPA] {stats}")
    return stats


async def riconcilia_cartelle_agenzia_entrate(db) -> Dict[str, Any]:
    """
    Riconcilia cartelle Agenzia Entrate/Riscossione con estratto conto.
    Cerca: numero cartella, importo, keyword ADER/riscossione nella banca.
    """
    stats = {"analizzati": 0, "riconciliati": 0, "non_trovati": 0}
    
    docs = await db["documenti_non_associati"].find(
        {"categoria_mittente": "Agenzia Entrate", "riconciliato": {"$ne": True}},
        {"_id": 0, "pdf_data": 0}
    ).to_list(200)
    
    # Anche cartelle dalla collection dedicata
    cartelle = await db["cartelle_email_attachments"].find(
        {"riconciliato": {"$ne": True}},
        {"_id": 0, "pdf_data": 0}
    ).to_list(200)
    
    all_docs = docs + cartelle
    stats["analizzati"] = len(all_docs)
    
    for doc in all_docs:
        filename = doc.get("filename", "")
        subject = doc.get("email_subject", "")
        
        # Cerca numero cartella o riferimento
        ref_match = re.search(r'(\d{10,20})', filename)
        
        search_terms = ["agenzia.*entrate", "agenzia.*riscossione", "ADER", "equitalia", "riscossione"]
        if ref_match:
            search_terms.insert(0, ref_match.group(1))
        
        found = False
        for term in search_terms:
            mov = await db["estratto_conto_movimenti"].find_one(
                {"descrizione": {"$regex": term, "$options": "i"}, "tipo": "uscita"},
                {"_id": 0}
            )
            if mov:
                coll = "documenti_non_associati" if "categoria_mittente" in doc else "cartelle_email_attachments"
                await db[coll].update_one(
                    {"id": doc["id"]},
                    {"$set": {
                        "riconciliato": True,
                        "riconciliato_con": "estratto_conto",
                        "movimento_banca_id": mov.get("id"),
                        "data_pagamento": mov.get("data_contabile"),
                        "importo_pagato": abs(float(mov.get("importo", 0))),
                    }}
                )
                stats["riconciliati"] += 1
                found = True
                break
        
        if not found:
            stats["non_trovati"] += 1
    
    logger.info(f"[RICONCILIA-ADER] {stats}")
    return stats


async def riconcilia_tari_con_banca(db) -> Dict[str, Any]:
    """
    Riconcilia avvisi TARI (tassa rifiuti) con estratto conto.
    Cerca keyword: TARI, tassa rifiuti, Comune di Napoli.
    """
    stats = {"analizzati": 0, "riconciliati": 0, "non_trovati": 0}
    
    # Cerca documenti TARI in Gmail (possono essere in Comune di Napoli o in cartelle specifiche)
    docs = await db["documenti_non_associati"].find(
        {"$or": [
            {"filename": {"$regex": "tari|TARI", "$options": "i"}},
            {"email_subject": {"$regex": "tari|tassa rifiuti", "$options": "i"}},
        ], "riconciliato": {"$ne": True}},
        {"_id": 0, "pdf_data": 0}
    ).to_list(100)
    
    stats["analizzati"] = len(docs)
    
    # Cerca pagamenti TARI in banca
    movimenti_tari = await db["estratto_conto_movimenti"].find(
        {"descrizione": {"$regex": "TARI|tassa rifiuti|tributi locali", "$options": "i"}},
        {"_id": 0}
    ).to_list(100)
    
    for doc in docs:
        for mov in movimenti_tari:
            await db["documenti_non_associati"].update_one(
                {"id": doc["id"]},
                {"$set": {
                    "riconciliato": True,
                    "riconciliato_con": "estratto_conto",
                    "data_pagamento": mov.get("data_contabile"),
                    "importo_pagato": abs(float(mov.get("importo", 0))),
                }}
            )
            stats["riconciliati"] += 1
            break
        else:
            stats["non_trovati"] += 1
    
    logger.info(f"[RICONCILIA-TARI] {stats}")
    return stats


async def confronta_pos_corrispettivi(db, anno: int = 2026) -> Dict[str, Any]:
    """
    Confronta il pagamento elettronico dei corrispettivi telematici
    con l'inserimento manuale serale dei POS.
    Evidenzia discrepanze per evitare sanzioni fiscali.
    
    Corrispettivo XML: campo 'pagato_elettronico' (dal registratore telematico)
    Inserimento manuale: movimenti Prima Nota Cassa con categoria 'POS'
    Estratto conto: accrediti POS dalla banca (INC.POS)
    """
    stats = {
        "giorni_analizzati": 0,
        "discrepanze": [],
        "totale_corrispettivo_pos": 0,
        "totale_manuale_pos": 0,
        "totale_banca_pos": 0,
        "differenza_corr_vs_manuale": 0,
        "differenza_corr_vs_banca": 0,
        "giorni_ok": 0,
        "giorni_discrepanza": 0,
    }
    
    # 1. Carica corrispettivi dell'anno
    corrispettivi = await db["corrispettivi"].find(
        {"anno": anno},
        {"_id": 0}
    ).sort("data", 1).to_list(400)
    
    # 2. Carica movimenti POS dalla Prima Nota Cassa
    pn_pos = await db["prima_nota_cassa"].find(
        {"categoria": {"$regex": "POS|pos|Elettronico", "$options": "i"},
         "data": {"$regex": f"^{anno}"}},
        {"_id": 0}
    ).to_list(400)
    
    # 3. Carica accrediti POS dalla banca
    banca_pos = await db["estratto_conto_movimenti"].find(
        {"descrizione": {"$regex": "INC.POS|POS CARTE|NUMIA|SUM UP|SATISPAY", "$options": "i"},
         "data_contabile": {"$regex": f"/{anno}$"}},
        {"_id": 0}
    ).to_list(1000)
    
    # Index per data
    manuale_per_data = {}
    for m in pn_pos:
        data = m.get("data", "")[:10]
        manuale_per_data[data] = manuale_per_data.get(data, 0) + float(m.get("importo", 0))
    
    banca_per_data = {}
    for b in banca_pos:
        data_raw = b.get("data_contabile", "")
        if "/" in data_raw:
            parts = data_raw.split("/")
            data = f"{parts[2]}-{parts[1]}-{parts[0]}" if len(parts) == 3 else data_raw
        else:
            data = data_raw[:10]
        banca_per_data[data] = banca_per_data.get(data, 0) + float(b.get("importo", 0))
    
    # 4. Confronta giorno per giorno
    for corr in corrispettivi:
        data = corr.get("data", "")[:10]
        pos_corr = float(corr.get("pagato_elettronico", 0) or 0)
        pos_manuale = manuale_per_data.get(data, 0)
        pos_banca = banca_per_data.get(data, 0)
        
        stats["giorni_analizzati"] += 1
        stats["totale_corrispettivo_pos"] += pos_corr
        stats["totale_manuale_pos"] += pos_manuale
        stats["totale_banca_pos"] += pos_banca
        
        # Tolleranza: ±5€ per differenze di arrotondamento
        diff_manuale = abs(pos_corr - pos_manuale)
        diff_banca = abs(pos_corr - pos_banca)
        
        if diff_manuale > 5 or (diff_banca > 5 and pos_banca > 0):
            stats["giorni_discrepanza"] += 1
            stats["discrepanze"].append({
                "data": data,
                "corrispettivo_pos": round(pos_corr, 2),
                "manuale_pos": round(pos_manuale, 2),
                "banca_pos": round(pos_banca, 2),
                "differenza_corr_manuale": round(pos_corr - pos_manuale, 2),
                "differenza_corr_banca": round(pos_corr - pos_banca, 2),
                "alert": "⚠️ DISCREPANZA" if diff_manuale > 50 else "⚡ Lieve differenza",
            })
        else:
            stats["giorni_ok"] += 1
    
    stats["totale_corrispettivo_pos"] = round(stats["totale_corrispettivo_pos"], 2)
    stats["totale_manuale_pos"] = round(stats["totale_manuale_pos"], 2)
    stats["totale_banca_pos"] = round(stats["totale_banca_pos"], 2)
    stats["differenza_corr_vs_manuale"] = round(stats["totale_corrispettivo_pos"] - stats["totale_manuale_pos"], 2)
    stats["differenza_corr_vs_banca"] = round(stats["totale_corrispettivo_pos"] - stats["totale_banca_pos"], 2)
    
    logger.info(f"[CONFRONTO-POS] {stats['giorni_analizzati']} giorni, {stats['giorni_discrepanza']} discrepanze")
    return stats


async def riconciliazione_completa(db, anno: int = 2026) -> Dict[str, Any]:
    """Esegue TUTTE le riconciliazioni in sequenza."""
    risultati = {}
    
    risultati["pagopa"] = await riconcilia_pagopa_con_banca(db)
    risultati["agenzia_entrate"] = await riconcilia_cartelle_agenzia_entrate(db)
    risultati["tari"] = await riconcilia_tari_con_banca(db)
    risultati["confronto_pos"] = await confronta_pos_corrispettivi(db, anno)
    
    logger.info(f"[RICONCILIAZIONE-COMPLETA] {risultati}")
    return risultati
