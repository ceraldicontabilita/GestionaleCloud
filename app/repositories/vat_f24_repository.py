"""
VAT and F24 Repository
Repository per gestione liquidazioni IVA e modelli F24
"""
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, date
import logging
from bson import ObjectId

from .base_repository import BaseRepository
from app.exceptions import NotFoundError

logger = logging.getLogger(__name__)


class VATRepository(BaseRepository):
    """Repository per liquidazioni IVA."""
    
    async def create_liquidation(self, liquidation_data: Dict[str, Any]) -> Dict[str, Any]:
        """Crea liquidazione IVA."""
        liquidation_data['created_at'] = datetime.now(timezone.utc)
        liquidation_data['updated_at'] = datetime.now(timezone.utc)
        
        result = await self.collection.insert_one(liquidation_data.copy())
        liquidation_data['_id'] = result.inserted_id
        
        logger.info(f"Created VAT liquidation: Q{liquidation_data['quarter']}/{liquidation_data['year']}")
        return self._doc_to_dict(liquidation_data)
    
    async def get_liquidation_by_period(self, quarter: int, year: int) -> Optional[Dict[str, Any]]:
        """Recupera liquidazione per trimestre."""
        liquidation = await self.collection.find_one({
            'quarter': quarter,
            'year': year
        })
        
        return self._doc_to_dict(liquidation) if liquidation else None
    
    async def get_liquidations_by_year(self, year: int) -> List[Dict[str, Any]]:
        """Recupera tutte le liquidazioni di un anno."""
        cursor = self.collection.find({'year': year}).sort('quarter', 1)
        liquidations = await cursor.to_list(length=None)
        
        return [self._doc_to_dict(liq) for liq in liquidations]
    
    async def update_liquidation(
        self,
        liquidation_id: str,
        update_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Aggiorna liquidazione."""
        update_data['updated_at'] = datetime.now(timezone.utc)
        
        result = await self.collection.find_one_and_update(
            {'_id': ObjectId(liquidation_id)},
            {'$set': update_data},
            return_document=True
        )
        
        if not result:
            raise NotFoundError(f"VAT liquidation {liquidation_id} not found")
        
        logger.info(f"Updated VAT liquidation: {liquidation_id}")
        return self._doc_to_dict(result)
    
    async def mark_as_paid(
        self,
        liquidation_id: str,
        payment_date: date,
        payment_reference: Optional[str] = None
    ) -> Dict[str, Any]:
        """Marca liquidazione come pagata."""
        update_data = {
            'paid': True,
            'payment_date': payment_date,
            'updated_at': datetime.now(timezone.utc)
        }
        
        if payment_reference:
            update_data['payment_reference'] = payment_reference
        
        result = await self.collection.find_one_and_update(
            {'_id': ObjectId(liquidation_id)},
            {'$set': update_data},
            return_document=True
        )
        
        if not result:
            raise NotFoundError(f"VAT liquidation {liquidation_id} not found")
        
        logger.info(f"Marked VAT liquidation as paid: {liquidation_id}")
        return self._doc_to_dict(result)


class VATRegistryRepository(BaseRepository):
    """Repository per registro IVA."""
    
    async def get_registry_entries(
        self,
        start_date: date,
        end_date: date,
        vat_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Recupera registrazioni IVA per periodo."""
        query = {
            'date': {
                '$gte': start_date,
                '$lte': end_date
            }
        }
        
        if vat_type:
            query['vat_type'] = vat_type
        
        cursor = self.collection.find(query).sort('date', 1)
        entries = await cursor.to_list(length=None)
        
        return [self._doc_to_dict(entry) for entry in entries]
    
    async def calculate_vat_summary(
        self,
        start_date: date,
        end_date: date
    ) -> Dict[str, float]:
        """Calcola riepilogo IVA per periodo."""
        pipeline = [
            {
                '$match': {
                    'date': {'$gte': start_date, '$lte': end_date}
                }
            },
            {
                '$group': {
                    '_id': '$vat_type',
                    'total_taxable': {'$sum': '$taxable'},
                    'total_vat': {'$sum': '$vat_amount'}
                }
            }
        ]
        
        result = await self.collection.aggregate(pipeline).to_list(length=None)
        
        summary = {
            'deductible': 0.0,
            'payable': 0.0,
            'non_deductible': 0.0
        }
        
        for item in result:
            vat_type = item['_id']
            if vat_type in summary:
                summary[vat_type] = item['total_vat']
        
        summary['balance'] = summary['payable'] - summary['deductible']
        
        return summary


class F24Repository(BaseRepository):
    """Repository per modelli F24."""
    
    async def create_f24(self, f24_data: Dict[str, Any]) -> Dict[str, Any]:
        """Crea modello F24."""
        f24_data['created_at'] = datetime.now(timezone.utc)
        f24_data['updated_at'] = datetime.now(timezone.utc)
        
        result = await self.collection.insert_one(f24_data.copy())
        f24_data['_id'] = result.inserted_id
        
        logger.info(f"Created F24: {f24_data['reference_month']}/{f24_data['reference_year']}")
        return self._doc_to_dict(f24_data)
    
    async def get_f24_by_period(
        self,
        month: int,
        year: int
    ) -> List[Dict[str, Any]]:
        """Recupera F24 per periodo."""
        cursor = self.collection.find({
            'reference_month': month,
            'reference_year': year
        }).sort('payment_date', -1)
        
        f24s = await cursor.to_list(length=None)
        return [self._doc_to_dict(f24) for f24 in f24s]
    
    async def get_f24_by_year(self, year: int) -> List[Dict[str, Any]]:
        """Recupera tutti gli F24 di un anno."""
        cursor = self.collection.find({
            'reference_year': year
        }).sort([('reference_month', 1), ('payment_date', -1)])
        
        f24s = await cursor.to_list(length=None)
        return [self._doc_to_dict(f24) for f24 in f24s]
    
    async def update_f24(
        self,
        f24_id: str,
        update_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Aggiorna F24."""
        update_data['updated_at'] = datetime.now(timezone.utc)
        
        result = await self.collection.find_one_and_update(
            {'_id': ObjectId(f24_id)},
            {'$set': update_data},
            return_document=True
        )
        
        if not result:
            raise NotFoundError(f"F24 {f24_id} not found")
        
        logger.info(f"Updated F24: {f24_id}")
        return self._doc_to_dict(result)
    
    async def mark_f24_as_paid(
        self,
        f24_id: str,
        payment_reference: str
    ) -> Dict[str, Any]:
        """Marca F24 come pagato."""
        update_data = {
            'paid': True,
            'payment_reference': payment_reference,
            'updated_at': datetime.now(timezone.utc)
        }
        
        result = await self.collection.find_one_and_update(
            {'_id': ObjectId(f24_id)},
            {'$set': update_data},
            return_document=True
        )
        
        if not result:
            raise NotFoundError(f"F24 {f24_id} not found")
        
        logger.info(f"Marked F24 as paid: {f24_id}")
        return self._doc_to_dict(result)
    
    async def get_unpaid_f24s(self) -> List[Dict[str, Any]]:
        """Recupera F24 non pagati."""
        cursor = self.collection.find({
            'paid': False
        }).sort('payment_date', 1)
        
        f24s = await cursor.to_list(length=None)
        return [self._doc_to_dict(f24) for f24 in f24s]
