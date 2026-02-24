"""
Accounting Entries Repository
Repository per gestione registrazioni in Prima Nota
"""
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, date
import logging
from bson import ObjectId

from .base_repository import BaseRepository
from app.exceptions import NotFoundError, ValidationError

logger = logging.getLogger(__name__)


class AccountingEntriesRepository(BaseRepository):
    """Repository per registrazioni contabili."""
    
    async def create_entry(self, entry_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Crea nuova registrazione in prima nota.
        Valida che dare = avere.
        """
        # Valida bilanciamento
        total_debit = sum(line.get('debit', 0) for line in entry_data.get('lines', []))
        total_credit = sum(line.get('credit', 0) for line in entry_data.get('lines', []))
        
        if abs(total_debit - total_credit) > 0.01:  # Tolleranza per arrotondamenti
            raise ValidationError(
                f"Registrazione non bilanciata: Dare={total_debit}, Avere={total_credit}"
            )
        
        # Aggiungi campi calcolati
        entry_data['total_debit'] = total_debit
        entry_data['total_credit'] = total_credit
        entry_data['balanced'] = True
        entry_data['created_at'] = datetime.now(timezone.utc)
        entry_data['updated_at'] = datetime.now(timezone.utc)
        
        result = await self.collection.insert_one(entry_data.copy())
        entry_data['_id'] = result.inserted_id
        
        logger.info(f"Created accounting entry: {result.inserted_id}")
        return self._doc_to_dict(entry_data)
    
    async def get_entries_by_date_range(
        self,
        start_date: date,
        end_date: date,
        entry_type: Optional[str] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Recupera registrazioni per periodo."""
        query = {
            'date': {
                '$gte': start_date,
                '$lte': end_date
            }
        }
        
        if entry_type:
            query['entry_type'] = entry_type
        
        cursor = self.collection.find(query).sort('date', -1).skip(skip).limit(limit)
        entries = await cursor.to_list(length=limit)
        
        return [self._doc_to_dict(entry) for entry in entries]
    
    async def get_entries_by_account(
        self,
        account_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[Dict[str, Any]]:
        """Recupera registrazioni per conto."""
        query = {
            'lines.account_id': account_id
        }
        
        if start_date and end_date:
            query['date'] = {'$gte': start_date, '$lte': end_date}
        
        cursor = self.collection.find(query).sort('date', -1)
        entries = await cursor.to_list(length=None)
        
        return [self._doc_to_dict(entry) for entry in entries]
    
    async def update_entry(
        self,
        entry_id: str,
        update_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Aggiorna registrazione."""
        # Se ci sono nuove righe, valida bilanciamento
        if 'lines' in update_data:
            total_debit = sum(line.get('debit', 0) for line in update_data['lines'])
            total_credit = sum(line.get('credit', 0) for line in update_data['lines'])
            
            if abs(total_debit - total_credit) > 0.01:
                raise ValidationError(
                    f"Registrazione non bilanciata: Dare={total_debit}, Avere={total_credit}"
                )
            
            update_data['total_debit'] = total_debit
            update_data['total_credit'] = total_credit
            update_data['balanced'] = True
        
        update_data['updated_at'] = datetime.now(timezone.utc)
        
        result = await self.collection.find_one_and_update(
            {'_id': ObjectId(entry_id)},
            {'$set': update_data},
            return_document=True
        )
        
        if not result:
            raise NotFoundError(f"Accounting entry {entry_id} not found")
        
        logger.info(f"Updated accounting entry: {entry_id}")
        return self._doc_to_dict(result)
    
    async def delete_entry(self, entry_id: str) -> bool:
        """Elimina registrazione."""
        result = await self.collection.delete_one({'_id': ObjectId(entry_id)})
        
        if result.deleted_count == 0:
            raise NotFoundError(f"Accounting entry {entry_id} not found")
        
        logger.info(f"Deleted accounting entry: {entry_id}")
        return True
    
    async def bulk_create_entries(
        self,
        entries: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Crea multiple registrazioni."""
        # Valida tutte le registrazioni
        validated_entries = []
        for entry in entries:
            total_debit = sum(line.get('debit', 0) for line in entry.get('lines', []))
            total_credit = sum(line.get('credit', 0) for line in entry.get('lines', []))
            
            if abs(total_debit - total_credit) > 0.01:
                raise ValidationError(
                    f"Registrazione non bilanciata: {entry.get('description')}"
                )
            
            entry['total_debit'] = total_debit
            entry['total_credit'] = total_credit
            entry['balanced'] = True
            entry['created_at'] = datetime.now(timezone.utc)
            entry['updated_at'] = datetime.now(timezone.utc)
            validated_entries.append(entry)
        
        result = await self.collection.insert_many(validated_entries)
        
        logger.info(f"Bulk created {len(result.inserted_ids)} accounting entries")
        
        # Recupera le registrazioni create
        created_entries = await self.collection.find(
            {'_id': {'$in': result.inserted_ids}}
        ).to_list(length=None)
        
        return [self._doc_to_dict(entry) for entry in created_entries]
    
    async def get_account_balance(
        self,
        account_id: str,
        up_to_date: Optional[date] = None
    ) -> Dict[str, float]:
        """Calcola saldo di un conto fino a una certa data."""
        query = {'lines.account_id': account_id}
        
        if up_to_date:
            query['date'] = {'$lte': up_to_date}
        
        entries = await self.collection.find(query).to_list(length=None)
        
        total_debit = 0.0
        total_credit = 0.0
        
        for entry in entries:
            for line in entry.get('lines', []):
                if line.get('account_id') == account_id:
                    total_debit += line.get('debit', 0)
                    total_credit += line.get('credit', 0)
        
        return {
            'account_id': account_id,
            'total_debit': total_debit,
            'total_credit': total_credit,
            'balance': total_debit - total_credit
        }
    
    async def get_trial_balance(
        self,
        balance_date: date
    ) -> List[Dict[str, Any]]:
        """Genera bilancio di verifica."""
        entries = await self.collection.find(
            {'date': {'$lte': balance_date}}
        ).to_list(length=None)
        
        # Raggruppa per account_id
        accounts_balance = {}
        
        for entry in entries:
            for line in entry.get('lines', []):
                account_id = line.get('account_id')
                if account_id not in accounts_balance:
                    accounts_balance[account_id] = {
                        'account_id': account_id,
                        'account_code': line.get('account_code'),
                        'account_name': line.get('account_name'),
                        'debit': 0.0,
                        'credit': 0.0
                    }
                
                accounts_balance[account_id]['debit'] += line.get('debit', 0)
                accounts_balance[account_id]['credit'] += line.get('credit', 0)
        
        # Calcola saldi
        trial_balance = []
        for account in accounts_balance.values():
            account['balance'] = account['debit'] - account['credit']
            trial_balance.append(account)
        
        # Ordina per codice conto
        trial_balance.sort(key=lambda x: x['account_code'])
        
        return trial_balance
