"""
Balance Sheet Repository
Repository per generazione bilanci e report contabili
"""
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, date
import logging

from .base_repository import BaseRepository

logger = logging.getLogger(__name__)


class BalanceSheetRepository(BaseRepository):
    """Repository per bilanci e report contabili."""
    
    async def save_balance_sheet(self, balance_data: Dict[str, Any]) -> Dict[str, Any]:
        """Salva bilancio generato."""
        balance_data['generated_at'] = datetime.now(timezone.utc)
        balance_data['created_at'] = datetime.now(timezone.utc)
        
        result = await self.collection.insert_one(balance_data.copy())
        balance_data['_id'] = result.inserted_id
        
        logger.info(f"Saved balance sheet for year {balance_data['year']}")
        return self._doc_to_dict(balance_data)
    
    async def get_balance_sheet_by_year(self, year: int) -> Optional[Dict[str, Any]]:
        """Recupera bilancio salvato per anno."""
        balance = await self.collection.find_one({'year': year})
        return self._doc_to_dict(balance) if balance else None
    
    async def get_latest_balance_sheets(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Recupera ultimi bilanci generati."""
        cursor = self.collection.find().sort('year', -1).limit(limit)
        balances = await cursor.to_list(length=limit)
        
        return [self._doc_to_dict(balance) for balance in balances]


class YearEndRepository(BaseRepository):
    """Repository per operazioni di chiusura anno."""
    
    async def create_year_end_closure(
        self,
        closure_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Crea record chiusura anno."""
        closure_data['created_at'] = datetime.now(timezone.utc)
        closure_data['status'] = 'completed'
        
        result = await self.collection.insert_one(closure_data.copy())
        closure_data['_id'] = result.inserted_id
        
        logger.info(f"Created year-end closure for {closure_data['year']}")
        return self._doc_to_dict(closure_data)
    
    async def get_closure_by_year(self, year: int) -> Optional[Dict[str, Any]]:
        """Recupera chiusura per anno."""
        closure = await self.collection.find_one({'year': year})
        return self._doc_to_dict(closure) if closure else None
    
    async def is_year_closed(self, year: int) -> bool:
        """Verifica se anno è chiuso."""
        closure = await self.collection.find_one({
            'year': year,
            'status': 'completed'
        })
        return closure is not None


class AccountBalanceRepository(BaseRepository):
    """Repository per saldi conti."""
    
    async def calculate_account_balances(
        self,
        as_of_date: date,
        account_ids: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Calcola saldi di tutti i conti alla data.
        Utilizza collection accounting_entries.
        """
        from app.database import Database, Collections
        
        db = Database.get_db()
        entries_collection = db[Collections.ACCOUNTING_ENTRIES]
        
        # Query per recuperare tutte le registrazioni fino alla data
        query = {'date': {'$lte': as_of_date}}
        
        entries = await entries_collection.find(query).to_list(length=None)
        
        # Calcola saldi per account_id
        balances = {}
        
        for entry in entries:
            for line in entry.get('lines', []):
                account_id = line.get('account_id')
                
                # Filtra per account_ids se specificato
                if account_ids and account_id not in account_ids:
                    continue
                
                if account_id not in balances:
                    balances[account_id] = {
                        'account_id': account_id,
                        'account_code': line.get('account_code'),
                        'account_name': line.get('account_name'),
                        'debit': 0.0,
                        'credit': 0.0,
                        'balance': 0.0
                    }
                
                balances[account_id]['debit'] += line.get('debit', 0)
                balances[account_id]['credit'] += line.get('credit', 0)
        
        # Calcola balance finale
        result = []
        for account_id, data in balances.items():
            data['balance'] = data['debit'] - data['credit']
            result.append(data)
        
        # Ordina per account_code
        result.sort(key=lambda x: x['account_code'])
        
        return result
    
    async def get_accounts_by_type(
        self,
        account_type: str,
        as_of_date: date
    ) -> List[Dict[str, Any]]:
        """
        Recupera conti per tipo con saldi.
        account_type: assets, liabilities, equity, revenue, expenses
        """
        from app.database import Database, Collections
        
        db = Database.get_db()
        chart_collection = db[Collections.CHART_OF_ACCOUNTS]
        
        # Recupera conti del tipo
        accounts = await chart_collection.find({
            'type': account_type
        }).to_list(length=None)
        
        if not accounts:
            return []
        
        account_ids = [str(acc['_id']) for acc in accounts]
        
        # Calcola saldi
        balances = await self.calculate_account_balances(as_of_date, account_ids)
        
        return balances
    
    async def get_total_by_type(
        self,
        account_type: str,
        as_of_date: date
    ) -> float:
        """Calcola totale per tipo di conto."""
        balances = await self.get_accounts_by_type(account_type, as_of_date)
        
        total = sum(acc['balance'] for acc in balances)
        return total
