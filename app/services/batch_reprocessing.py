"""
Batch Reprocessing Service per F24 e Cedolini
Riprocessa tutti i documenti esistenti con il nuovo parser migliorato.
"""

import asyncio
import base64
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from bson import ObjectId

from app.database import Database
from app.services.enhanced_document_parser import (
    parse_f24_enhanced,
    parse_cedolino_enhanced
)

logger = logging.getLogger(__name__)


class BatchReprocessingService:
    """Servizio per riprocessare batch di documenti con il parser migliorato."""
    
    def __init__(self):
        self.db = None
        self.stats = {
            "f24_total": 0,
            "f24_processed": 0,
            "f24_success": 0,
            "f24_errors": 0,
            "cedolini_total": 0,
            "cedolini_processed": 0,
            "cedolini_success": 0,
            "cedolini_errors": 0,
            "start_time": None,
            "end_time": None,
            "errors": []
        }
    
    async def init_db(self):
        """Inizializza connessione database."""
        self.db = Database.get_db()
        if self.db is None:
            raise Exception("Database non connesso")
    
    async def reprocess_all_f24(self, dry_run: bool = False) -> Dict[str, Any]:
        """
        Riprocessa tutti gli F24 con PDF disponibile.
        
        Args:
            dry_run: Se True, non salva le modifiche (solo test)
        
        Returns:
            Statistiche del riprocessamento
        """
        await self.init_db()
        self.stats["start_time"] = datetime.now(timezone.utc).isoformat()
        
        # Collezioni che contengono F24 con PDF
        collections = ["f24_models", "f24", "f24_uploaded"]
        
        for coll_name in collections:
            try:
                coll = self.db[coll_name]
                
                # Trova tutti i documenti con pdf_data
                cursor = coll.find(
                    {"pdf_data": {"$exists": True, "$ne": None}},
                    {"_id": 1, "pdf_data": 1, "id": 1, "filename": 1}
                )
                
                docs = await cursor.to_list(length=5000)
                self.stats["f24_total"] += len(docs)
                
                logger.info(f"Trovati {len(docs)} F24 con PDF in {coll_name}")
                
                for doc in docs:
                    try:
                        doc_id = doc.get("_id")
                        pdf_data = doc.get("pdf_data")
                        
                        if not pdf_data:
                            continue
                        
                        # Decodifica PDF
                        pdf_bytes = base64.b64decode(pdf_data)
                        
                        # Riprocessa con nuovo parser
                        result = await parse_f24_enhanced(pdf_bytes, "application/pdf")
                        
                        self.stats["f24_processed"] += 1
                        
                        if result.get("success"):
                            self.stats["f24_success"] += 1
                            
                            if not dry_run:
                                # Aggiorna documento con nuovi dati
                                update_data = {
                                    "enhanced_parsing": result,
                                    "enhanced_parsing_date": datetime.now(timezone.utc).isoformat(),
                                    "enhanced_parser_version": "v2"
                                }
                                
                                # Aggiorna anche le sezioni se presenti
                                if result.get("sezione_erario"):
                                    update_data["sezione_erario_enhanced"] = result["sezione_erario"]
                                if result.get("sezione_inps"):
                                    update_data["sezione_inps_enhanced"] = result["sezione_inps"]
                                if result.get("sezione_regioni"):
                                    update_data["sezione_regioni_enhanced"] = result["sezione_regioni"]
                                if result.get("sezione_imu_tributi_locali"):
                                    update_data["sezione_imu_enhanced"] = result["sezione_imu_tributi_locali"]
                                if result.get("totali"):
                                    update_data["totali_enhanced"] = result["totali"]
                                if result.get("validazione"):
                                    update_data["validazione_enhanced"] = result["validazione"]
                                
                                await coll.update_one(
                                    {"_id": doc_id},
                                    {"$set": update_data}
                                )
                                
                            logger.info(f"F24 {doc_id} riprocessato con successo")
                        else:
                            self.stats["f24_errors"] += 1
                            self.stats["errors"].append({
                                "type": "f24",
                                "collection": coll_name,
                                "doc_id": str(doc_id),
                                "error": result.get("error", "Unknown error")
                            })
                            
                    except Exception as e:
                        self.stats["f24_errors"] += 1
                        self.stats["errors"].append({
                            "type": "f24",
                            "collection": coll_name,
                            "doc_id": str(doc.get("_id")),
                            "error": str(e)
                        })
                        logger.error(f"Errore riprocessamento F24 {doc.get('_id')}: {e}")
                        
            except Exception as e:
                logger.error(f"Errore accesso collezione {coll_name}: {e}")
        
        self.stats["end_time"] = datetime.now(timezone.utc).isoformat()
        return self.stats
    
    async def reprocess_all_cedolini(self, dry_run: bool = False) -> Dict[str, Any]:
        """
        Riprocessa tutti i cedolini con PDF disponibile.
        
        Args:
            dry_run: Se True, non salva le modifiche (solo test)
        
        Returns:
            Statistiche del riprocessamento
        """
        await self.init_db()
        
        if not self.stats["start_time"]:
            self.stats["start_time"] = datetime.now(timezone.utc).isoformat()
        
        # Collezioni che contengono cedolini con PDF
        collections = ["cedolini", "payslips", "buste_paga", "extracted_documents"]
        
        for coll_name in collections:
            try:
                coll = self.db[coll_name]
                
                # Trova documenti con PDF (pdf_data o file_base64)
                cursor = coll.find(
                    {"$or": [
                        {"pdf_data": {"$exists": True, "$ne": None}},
                        {"file_base64": {"$exists": True, "$ne": None}},
                        {"pdf_base64": {"$exists": True, "$ne": None}}
                    ]},
                    {"_id": 1, "pdf_data": 1, "file_base64": 1, "pdf_base64": 1, 
                     "id": 1, "filename": 1, "dipendente_nome": 1, "mese": 1, "anno": 1}
                )
                
                docs = await cursor.to_list(length=5000)
                self.stats["cedolini_total"] += len(docs)
                
                logger.info(f"Trovati {len(docs)} cedolini con PDF in {coll_name}")
                
                for doc in docs:
                    try:
                        doc_id = doc.get("_id")
                        
                        # Trova il PDF data
                        pdf_data = doc.get("pdf_data") or doc.get("file_base64") or doc.get("pdf_base64")
                        
                        if not pdf_data:
                            continue
                        
                        # Decodifica PDF
                        pdf_bytes = base64.b64decode(pdf_data)
                        
                        # Riprocessa con nuovo parser
                        result = await parse_cedolino_enhanced(pdf_bytes, "application/pdf")
                        
                        self.stats["cedolini_processed"] += 1
                        
                        if result.get("success"):
                            self.stats["cedolini_success"] += 1
                            
                            if not dry_run:
                                # Aggiorna documento con nuovi dati
                                update_data = {
                                    "enhanced_parsing": result,
                                    "enhanced_parsing_date": datetime.now(timezone.utc).isoformat(),
                                    "enhanced_parser_version": "v2"
                                }
                                
                                # Aggiorna campi specifici se migliorati
                                importi = result.get("importi_finali", {})
                                if importi.get("netto_in_busta") or importi.get("netto_da_pagare"):
                                    update_data["netto_enhanced"] = importi.get("netto_in_busta") or importi.get("netto_da_pagare")
                                if importi.get("totale_competenze"):
                                    update_data["lordo_enhanced"] = importi.get("totale_competenze")
                                if importi.get("totale_trattenute"):
                                    update_data["trattenute_enhanced"] = importi.get("totale_trattenute")
                                
                                # TFR
                                tfr = result.get("tfr", {})
                                if tfr.get("retribuzione_utile_tfr"):
                                    update_data["tfr_retribuzione_utile_enhanced"] = tfr["retribuzione_utile_tfr"]
                                if tfr.get("quota_tfr_mese"):
                                    update_data["tfr_quota_mese_enhanced"] = tfr["quota_tfr_mese"]
                                
                                # Ferie e permessi
                                ferie = result.get("ferie_permessi", {})
                                if ferie:
                                    update_data["ferie_permessi_enhanced"] = ferie
                                
                                # Validazione
                                if result.get("validazione"):
                                    update_data["validazione_enhanced"] = result["validazione"]
                                
                                await coll.update_one(
                                    {"_id": doc_id},
                                    {"$set": update_data}
                                )
                            
                            dipendente = doc.get("dipendente_nome", "Unknown")
                            periodo = f"{doc.get('mese', '?')}/{doc.get('anno', '?')}"
                            logger.info(f"Cedolino {dipendente} {periodo} riprocessato con successo")
                        else:
                            self.stats["cedolini_errors"] += 1
                            self.stats["errors"].append({
                                "type": "cedolino",
                                "collection": coll_name,
                                "doc_id": str(doc_id),
                                "error": result.get("error", "Unknown error")
                            })
                            
                    except Exception as e:
                        self.stats["cedolini_errors"] += 1
                        self.stats["errors"].append({
                            "type": "cedolino",
                            "collection": coll_name,
                            "doc_id": str(doc.get("_id")),
                            "error": str(e)
                        })
                        logger.error(f"Errore riprocessamento cedolino {doc.get('_id')}: {e}")
                        
            except Exception as e:
                logger.error(f"Errore accesso collezione {coll_name}: {e}")
        
        self.stats["end_time"] = datetime.now(timezone.utc).isoformat()
        return self.stats
    
    async def reprocess_all(self, dry_run: bool = False) -> Dict[str, Any]:
        """
        Riprocessa tutti i documenti (F24 + Cedolini).
        
        Args:
            dry_run: Se True, non salva le modifiche (solo test)
        
        Returns:
            Statistiche complete del riprocessamento
        """
        logger.info(f"Avvio riprocessamento batch {'(DRY RUN)' if dry_run else ''}")
        
        # Riprocessa F24
        await self.reprocess_all_f24(dry_run)
        
        # Riprocessa Cedolini
        await self.reprocess_all_cedolini(dry_run)
        
        # Calcola statistiche finali
        self.stats["totale_documenti"] = self.stats["f24_total"] + self.stats["cedolini_total"]
        self.stats["totale_processati"] = self.stats["f24_processed"] + self.stats["cedolini_processed"]
        self.stats["totale_successi"] = self.stats["f24_success"] + self.stats["cedolini_success"]
        self.stats["totale_errori"] = self.stats["f24_errors"] + self.stats["cedolini_errors"]
        self.stats["dry_run"] = dry_run
        
        logger.info(f"Riprocessamento completato: {self.stats['totale_successi']}/{self.stats['totale_processati']} successi")
        
        return self.stats


# Funzione helper per eseguire il batch
async def run_batch_reprocessing(dry_run: bool = False) -> Dict[str, Any]:
    """
    Esegue il riprocessamento batch di tutti i documenti.
    
    Args:
        dry_run: Se True, esegue solo un test senza salvare
    
    Returns:
        Statistiche del riprocessamento
    """
    service = BatchReprocessingService()
    return await service.reprocess_all(dry_run)
