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

# Quanti documenti tenere in memoria per volta. Prima se ne caricavano fino a
# 5.000 in una lista sola, ognuno col proprio PDF in base64: poche centinaia
# di cedolini bastavano a esaurire la memoria del servizio e farlo cadere.
DIMENSIONE_BLOCCO = 25
LIMITE_DOCUMENTI = 100000


async def _identificativi(coll, filtro: Dict[str, Any]) -> List[Any]:
    """Solo gli _id: e' una lettura leggera, senza i PDF."""
    cursore = coll.find(filtro, {"_id": 1})
    return [doc["_id"] for doc in await cursore.to_list(length=LIMITE_DOCUMENTI)]


async def _blocco(coll, identificativi: List[Any],
                  proiezione: Dict[str, int]) -> List[Dict[str, Any]]:
    """Carica i documenti di un blocco, PDF compresi."""
    cursore = coll.find({"_id": {"$in": identificativi}}, proiezione)
    return await cursore.to_list(length=len(identificativi))


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
    
    async def _riprocessa_f24(self, coll, coll_name: str, doc: Dict[str, Any],
                              dry_run: bool) -> None:
        """Rilegge un F24 e gli aggiunge i campi del parser migliorato.

        Non inserisce mai un documento nuovo e non tocca i campi originali:
        scrive solo in `enhanced_parsing` e nei `*_enhanced` dello stesso
        documento. Un errore su un documento non ferma gli altri.
        """
        try:
            doc_id = doc.get("_id")
            pdf_data = doc.get("pdf_data")
            if not pdf_data:
                return

            pdf_bytes = base64.b64decode(pdf_data)

            # Conta ogni tentativo, anche se il parser solleva prima
            # di produrre un risultato (evita "42 errori / 0 processati").
            self.stats["f24_processed"] += 1

            result = await parse_f24_enhanced(pdf_bytes, "application/pdf")

            if not result.get("success"):
                self.stats["f24_errors"] += 1
                self.stats["errors"].append({
                    "type": "f24",
                    "collection": coll_name,
                    "doc_id": str(doc_id),
                    "error": result.get("error", "Unknown error"),
                })
                return

            self.stats["f24_success"] += 1
            if not dry_run:
                update_data = {
                    "enhanced_parsing": result,
                    "enhanced_parsing_date": datetime.now(timezone.utc).isoformat(),
                    "enhanced_parser_version": "v2",
                }
                sezioni = {
                    "sezione_erario": "sezione_erario_enhanced",
                    "sezione_inps": "sezione_inps_enhanced",
                    "sezione_regioni": "sezione_regioni_enhanced",
                    "sezione_imu_tributi_locali": "sezione_imu_enhanced",
                    "totali": "totali_enhanced",
                    "validazione": "validazione_enhanced",
                }
                for origine, destinazione in sezioni.items():
                    if result.get(origine):
                        update_data[destinazione] = result[origine]

                await coll.update_one({"_id": doc_id}, {"$set": update_data})

            logger.info(f"F24 {doc_id} riprocessato con successo")

        except Exception as e:
            self.stats["f24_errors"] += 1
            self.stats["errors"].append({
                "type": "f24",
                "collection": coll_name,
                "doc_id": str(doc.get("_id")),
                "error": str(e),
            })
            logger.error(f"Errore riprocessamento F24 {doc.get('_id')}: {e}")

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

                filtro = {"pdf_data": {"$exists": True, "$ne": None}}
                proiezione = {"_id": 1, "pdf_data": 1, "id": 1, "filename": 1}
                identificativi = await _identificativi(coll, filtro)
                self.stats["f24_total"] += len(identificativi)

                logger.info(f"Trovati {len(identificativi)} F24 con PDF in {coll_name}")

                for inizio in range(0, len(identificativi), DIMENSIONE_BLOCCO):
                    gruppo = identificativi[inizio:inizio + DIMENSIONE_BLOCCO]
                    for doc in await _blocco(coll, gruppo, proiezione):
                        await self._riprocessa_f24(coll, coll_name, doc, dry_run)

            except Exception as e:
                logger.error(f"Errore accesso collezione {coll_name}: {e}")
        
        self.stats["end_time"] = datetime.now(timezone.utc).isoformat()
        return self.stats
    
    async def _riprocessa_cedolino(self, coll, coll_name: str, doc: Dict[str, Any],
                                   dry_run: bool) -> None:
        """Rilegge un cedolino e gli aggiunge i campi del parser migliorato.

        Come per gli F24: nessun inserimento, nessuna sovrascrittura dei dati
        originali, e un errore su un documento non ferma gli altri.
        """
        try:
            doc_id = doc.get("_id")
            pdf_data = (doc.get("pdf_data") or doc.get("file_base64")
                        or doc.get("pdf_base64"))
            if not pdf_data:
                return

            pdf_bytes = base64.b64decode(pdf_data)

            # Conta il tentativo prima della chiamata al modello.
            self.stats["cedolini_processed"] += 1

            result = await parse_cedolino_enhanced(pdf_bytes, "application/pdf")

            if not result.get("success"):
                self.stats["cedolini_errors"] += 1
                self.stats["errors"].append({
                    "type": "cedolino",
                    "collection": coll_name,
                    "doc_id": str(doc_id),
                    "error": result.get("error", "Unknown error"),
                })
                return

            self.stats["cedolini_success"] += 1
            if not dry_run:
                update_data = {
                    "enhanced_parsing": result,
                    "enhanced_parsing_date": datetime.now(timezone.utc).isoformat(),
                    "enhanced_parser_version": "v2",
                }

                importi = result.get("importi_finali", {})
                netto = importi.get("netto_in_busta") or importi.get("netto_da_pagare")
                if netto:
                    update_data["netto_enhanced"] = netto
                if importi.get("totale_competenze"):
                    update_data["lordo_enhanced"] = importi["totale_competenze"]
                if importi.get("totale_trattenute"):
                    update_data["trattenute_enhanced"] = importi["totale_trattenute"]

                tfr = result.get("tfr", {})
                if tfr.get("retribuzione_utile_tfr"):
                    update_data["tfr_retribuzione_utile_enhanced"] = tfr["retribuzione_utile_tfr"]
                if tfr.get("quota_tfr_mese"):
                    update_data["tfr_quota_mese_enhanced"] = tfr["quota_tfr_mese"]

                if result.get("ferie_permessi"):
                    update_data["ferie_permessi_enhanced"] = result["ferie_permessi"]
                if result.get("validazione"):
                    update_data["validazione_enhanced"] = result["validazione"]

                await coll.update_one({"_id": doc_id}, {"$set": update_data})

            dipendente = doc.get("dipendente_nome", "Unknown")
            periodo = f"{doc.get('mese', '?')}/{doc.get('anno', '?')}"
            logger.info(f"Cedolino {dipendente} {periodo} riprocessato con successo")

        except Exception as e:
            self.stats["cedolini_errors"] += 1
            self.stats["errors"].append({
                "type": "cedolino",
                "collection": coll_name,
                "doc_id": str(doc.get("_id")),
                "error": str(e),
            })
            logger.error(f"Errore riprocessamento cedolino {doc.get('_id')}: {e}")

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

                filtro = {"$or": [
                    {"pdf_data": {"$exists": True, "$ne": None}},
                    {"file_base64": {"$exists": True, "$ne": None}},
                    {"pdf_base64": {"$exists": True, "$ne": None}},
                ]}
                proiezione = {
                    "_id": 1, "pdf_data": 1, "file_base64": 1, "pdf_base64": 1,
                    "id": 1, "filename": 1, "dipendente_nome": 1, "mese": 1, "anno": 1,
                }
                identificativi = await _identificativi(coll, filtro)
                self.stats["cedolini_total"] += len(identificativi)

                logger.info(f"Trovati {len(identificativi)} cedolini con PDF in {coll_name}")

                for inizio in range(0, len(identificativi), DIMENSIONE_BLOCCO):
                    gruppo = identificativi[inizio:inizio + DIMENSIONE_BLOCCO]
                    for doc in await _blocco(coll, gruppo, proiezione):
                        await self._riprocessa_cedolino(coll, coll_name, doc, dry_run)

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
