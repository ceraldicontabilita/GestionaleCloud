"""
CORRISPETTIVI SERVICE - Con Controlli di Sicurezza
==================================================

Servizio unificato per la gestione corrispettivi con:
- Validazione business rules
- Controlli di sicurezza pre-operazione
- Propagazione automatica a Prima Nota Cassa
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import hashlib
import logging
import xml.etree.ElementTree as ET

from app.database import Database
from app.services.business_rules import (
    BusinessRules, 
    CorrispettivoStatus,
    EntityStatus
)

logger = logging.getLogger(__name__)


class CorrispettiviService:
    """
    Servizio corrispettivi con controlli di sicurezza integrati.
    
    FLUSSO:
    1. Upload XML corrispettivo → Parse dati
    2. Verifica duplicato
    3. Salva corrispettivo
    4. Propaga a Prima Nota Cassa (incasso giornaliero)
    """
    
    def __init__(self, db=None):
        self.db = db or Database.get_db()
        self.corrispettivi = self.db["corrispettivi"]
        self.cash_movements = self.db["prima_nota_cassa"]  # Usa collection corretta
        self.prima_nota = self.db["prima_nota"]
    
    # ==================== CREATE ====================
    
    async def process_xml(self, xml_content: bytes, filename: str) -> Dict[str, Any]:
        """
        Processa un file XML corrispettivo.
        """
        logger.info(f"Processing corrispettivo XML: {filename}")
        
        # 1. Parse XML
        try:
            parsed = self._parse_corrispettivo_xml(xml_content)
        except Exception as e:
            logger.error(f"XML parse error: {e}")
            return {"status": "error", "message": f"Errore parsing XML: {str(e)}"}
        
        # 2. Check duplicato
        content_hash = hashlib.sha256(xml_content).hexdigest()
        existing = await self.corrispettivi.find_one({"content_hash": content_hash})
        if existing:
            return {
                "status": "duplicate",
                "corrispettivo_id": str(existing.get("id")),
                "message": "Corrispettivo già presente"
            }
        
        # Check duplicato per data
        existing_date = await self.corrispettivi.find_one({
            "data": parsed["data"],
            "entity_status": {"$ne": EntityStatus.DELETED.value}
        })
        if existing_date:
            return {
                "status": "duplicate",
                "corrispettivo_id": str(existing_date.get("id")),
                "message": f"Corrispettivo per {parsed['data']} già presente"
            }
        
        # 3. Prepara documento
        corr_doc = {
            "id": self._generate_id(),
            "filename": filename,
            "content_hash": content_hash,
            "data": parsed["data"],
            "progressivo": parsed.get("progressivo", ""),
            "id_dispositivo": parsed.get("id_dispositivo", ""),
            
            # Importi
            "totale": parsed["totale"],
            "totale_complessivo": parsed["totale"],
            "pagato_contanti": parsed.get("pagato_contanti", 0),
            "pagato_pos": parsed.get("pagato_pos", 0),
            "non_riscosso": parsed.get("non_riscosso", 0),
            
            # IVA
            "totale_iva": parsed.get("totale_iva", 0),
            "imponibile": parsed.get("imponibile", 0),
            "riepilogo_iva": parsed.get("riepilogo_iva", []),
            
            # Stati
            "status": CorrispettivoStatus.IMPORTED.value,
            "entity_status": EntityStatus.ACTIVE.value,
            
            # Metadata
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            
            # Relazioni
            "prima_nota_id": None
        }
        
        # 4. Salva corrispettivo
        await self.corrispettivi.insert_one(corr_doc.copy())
        corr_id = corr_doc["id"]
        
        # 5. Propaga a Prima Nota Cassa
        prima_nota_id = await self._create_prima_nota_entry(corr_doc)
        if prima_nota_id:
            await self.corrispettivi.update_one(
                {"id": corr_id},
                {"$set": {"prima_nota_id": prima_nota_id}}
            )
        
        logger.info(f"Corrispettivo created: {corr_id}")
        
        return {
            "status": "created",
            "corrispettivo_id": corr_id,
            "data": corr_doc["data"],
            "totale": corr_doc["totale"],
            "prima_nota_id": prima_nota_id,
            "message": "Corrispettivo importato con successo"
        }
    
    async def create_manual(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Crea un corrispettivo manuale (non da XML).
        """
        # Validazioni
        if not data.get("data"):
            return {"status": "error", "message": "Data obbligatoria"}
        if not data.get("totale") or data["totale"] <= 0:
            return {"status": "error", "message": "Totale deve essere maggiore di 0"}
        
        # Check duplicato per data
        existing = await self.corrispettivi.find_one({
            "data": data["data"],
            "entity_status": {"$ne": EntityStatus.DELETED.value}
        })
        if existing:
            return {
                "status": "duplicate",
                "message": f"Corrispettivo per {data['data']} già presente"
            }
        
        corr_doc = {
            "id": self._generate_id(),
            "data": data["data"],
            "totale": data["totale"],
            "totale_complessivo": data["totale"],
            "pagato_contanti": data.get("pagato_contanti", data["totale"]),
            "pagato_pos": data.get("pagato_pos", 0),
            "non_riscosso": data.get("non_riscosso", 0),
            "descrizione": data.get("descrizione", "Corrispettivo manuale"),
            "source": "manual",
            
            "status": CorrispettivoStatus.IMPORTED.value,
            "entity_status": EntityStatus.ACTIVE.value,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "prima_nota_id": None
        }
        
        await self.corrispettivi.insert_one(corr_doc.copy())
        
        # Propaga a Prima Nota
        prima_nota_id = await self._create_prima_nota_entry(corr_doc)
        if prima_nota_id:
            await self.corrispettivi.update_one(
                {"id": corr_doc["id"]},
                {"$set": {"prima_nota_id": prima_nota_id}}
            )
        
        return {
            "status": "created",
            "corrispettivo_id": corr_doc["id"],
            "prima_nota_id": prima_nota_id,
            "message": "Corrispettivo creato"
        }
    
    # ==================== READ ====================
    
    async def get_all(self, filters: Dict[str, Any] = None, 
                      skip: int = 0, limit: int = 100) -> List[Dict[str, Any]]:
        """Recupera tutti i corrispettivi."""
        query = {"entity_status": {"$ne": EntityStatus.DELETED.value}}
        
        if filters:
            if filters.get("year"):
                query["data"] = {"$regex": f"^{filters['year']}"}
            if filters.get("month"):
                year = filters.get("year", datetime.now().year)
                month = str(filters["month"]).zfill(2)
                query["data"] = {"$regex": f"^{year}-{month}"}
        
        cursor = self.corrispettivi.find(query, {"_id": 0}).skip(skip).limit(limit).sort("data", -1)
        return await cursor.to_list(limit)
    
    async def get_by_id(self, corr_id: str) -> Optional[Dict[str, Any]]:
        """Recupera un corrispettivo per ID."""
        return await self.corrispettivi.find_one(
            {"id": corr_id, "entity_status": {"$ne": EntityStatus.DELETED.value}},
            {"_id": 0}
        )
    
    async def get_by_date(self, data: str) -> Optional[Dict[str, Any]]:
        """Recupera un corrispettivo per data."""
        return await self.corrispettivi.find_one(
            {"data": data, "entity_status": {"$ne": EntityStatus.DELETED.value}},
            {"_id": 0}
        )
    
    # ==================== UPDATE ====================
    
    async def update(self, corr_id: str, update_data: Dict[str, Any]) -> Dict[str, Any]:
        """Aggiorna un corrispettivo con validazione."""
        corr = await self.get_by_id(corr_id)
        if not corr:
            return {"status": "error", "message": "Corrispettivo non trovato"}
        
        # Valida modifica
        validation = BusinessRules.can_modify_corrispettivo(corr)
        if not validation.is_valid:
            return {
                "status": "error",
                "message": "Modifica non consentita",
                "errors": validation.errors
            }
        
        # Applica modifica
        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        
        await self.corrispettivi.update_one(
            {"id": corr_id},
            {"$set": update_data}
        )
        
        # Se cambiato totale, aggiorna Prima Nota
        if "totale" in update_data and corr.get("prima_nota_id"):
            await self._update_prima_nota_entry(corr["prima_nota_id"], update_data)
        
        return {"status": "success", "message": "Corrispettivo aggiornato"}
    
    # ==================== DELETE ====================
    
    async def delete(self, corr_id: str, force: bool = False) -> Dict[str, Any]:
        """Elimina (soft-delete) un corrispettivo."""
        corr = await self.get_by_id(corr_id)
        if not corr:
            return {"status": "error", "message": "Corrispettivo non trovato"}
        
        # Valida eliminazione
        validation = BusinessRules.can_delete_corrispettivo(corr)
        if not validation.is_valid:
            return {
                "status": "error",
                "message": "Eliminazione non consentita",
                "errors": validation.errors
            }
        
        # Soft-delete
        await self.corrispettivi.update_one(
            {"id": corr_id},
            {"$set": {
                "entity_status": EntityStatus.DELETED.value,
                "deleted_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        
        # Annulla movimento Prima Nota collegato
        if corr.get("prima_nota_id"):
            await self.cash_movements.update_one(
                {"id": corr["prima_nota_id"]},
                {"$set": {"status": "cancelled"}}
            )
        
        return {"status": "success", "message": "Corrispettivo eliminato"}
    
    # ==================== HELPERS ====================
    
    def _parse_corrispettivo_xml(self, xml_content: bytes) -> Dict[str, Any]:
        """Parse XML corrispettivo formato RT."""
        root = ET.fromstring(xml_content)
        
        # Namespace handling
        ns = {'': root.tag.split('}')[0].strip('{') if '}' in root.tag else ''}
        
        def find_text(element, path, default=""):
            el = element.find(path, ns) if ns[''] else element.find(path)
            return el.text if el is not None and el.text else default
        
        # Estrai dati principali
        data = find_text(root, ".//DataOraRilevazione", "")[:10]
        if not data:
            data = find_text(root, ".//Data", datetime.now().strftime("%Y-%m-%d"))
        
        totale = float(find_text(root, ".//ImportoTotale", "0").replace(",", "."))
        if totale == 0:
            totale = float(find_text(root, ".//Totale", "0").replace(",", "."))
        
        # Estrai pagamenti
        pagato_contanti = 0
        pagato_pos = 0
        
        for pagamento in root.findall(".//Pagamento", ns) or root.findall(".//Pagamento"):
            tipo = find_text(pagamento, "Tipo", "").upper()
            importo = float(find_text(pagamento, "Importo", "0").replace(",", "."))
            
            if "CONTANTI" in tipo or "CASH" in tipo or tipo == "":
                pagato_contanti += importo
            elif "POS" in tipo or "CARTA" in tipo or "ELETTRONICO" in tipo:
                pagato_pos += importo
        
        # Se non ci sono pagamenti dettagliati, tutto contanti
        if pagato_contanti == 0 and pagato_pos == 0:
            pagato_contanti = totale
        
        # Estrai IVA
        riepilogo_iva = []
        totale_iva = 0
        
        for aliquota in root.findall(".//Aliquota", ns) or root.findall(".//AliquotaIVA", ns):
            perc = float(find_text(aliquota, "Percentuale", "22").replace(",", "."))
            impon = float(find_text(aliquota, "Imponibile", "0").replace(",", "."))
            imposta = float(find_text(aliquota, "Imposta", "0").replace(",", "."))
            
            riepilogo_iva.append({
                "aliquota": perc,
                "imponibile": impon,
                "imposta": imposta
            })
            totale_iva += imposta
        
        return {
            "data": data,
            "totale": totale,
            "pagato_contanti": pagato_contanti,
            "pagato_pos": pagato_pos,
            "non_riscosso": max(0, totale - pagato_contanti - pagato_pos),
            "totale_iva": totale_iva,
            "imponibile": totale - totale_iva,
            "riepilogo_iva": riepilogo_iva,
            "progressivo": find_text(root, ".//Progressivo", ""),
            "id_dispositivo": find_text(root, ".//IdDispositivo", "")
        }
    
    async def _create_prima_nota_entry(self, corr: Dict[str, Any]) -> Optional[str]:
        """Crea movimento Prima Nota Cassa per il corrispettivo."""
        try:
            movement_id = self._generate_id()
            
            movement_doc = {
                "id": movement_id,
                "date": corr["data"],
                "data": corr["data"],
                "type": "entrata",
                "tipo": "entrata",
                "amount": corr["totale"],
                "importo": corr["totale"],
                "description": f"Corrispettivo giornaliero {corr['data']}",
                "descrizione": f"Corrispettivo giornaliero {corr['data']}",
                "category": "Corrispettivi",
                "categoria": "Corrispettivi",
                "corrispettivo_id": corr["id"],
                "tipo_conto": "cassa",
                "source": "corrispettivo_import",
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            
            await self.cash_movements.insert_one(movement_doc.copy())
            
            # Anche in prima_nota per compatibilità
            prima_nota_doc = {
                **movement_doc,
                "id": self._generate_id()  # ID diverso per prima_nota
            }
            await self.prima_nota.insert_one(prima_nota_doc.copy())
            
            return movement_id
        except Exception as e:
            logger.error(f"Error creating prima nota entry: {e}")
            return None
    
    async def _update_prima_nota_entry(self, movement_id: str, update_data: Dict[str, Any]):
        """Aggiorna movimento Prima Nota collegato."""
        update_fields = {}
        if "totale" in update_data:
            update_fields["amount"] = update_data["totale"]
            update_fields["importo"] = update_data["totale"]
        
        if update_fields:
            await self.cash_movements.update_one(
                {"id": movement_id},
                {"$set": update_fields}
            )
    
    def _generate_id(self) -> str:
        import uuid
        return str(uuid.uuid4())


# Factory
def get_corrispettivi_service():
    return CorrispettiviService()
