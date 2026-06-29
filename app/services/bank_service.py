"""
Bank service.
Business logic for bank account and statement management.
"""
from typing import List, Dict, Any, Optional
from datetime import datetime, date, timezone
import logging

from app.repositories.bank_repository import BankRepository
from app.exceptions import NotFoundError
from app.models.bank import BankStatementCreate, BankStatementUpdate

logger = logging.getLogger(__name__)


class BankService:
    """Service for bank operations."""
    
    def __init__(self, bank_repo: BankRepository):
        self.bank_repo = bank_repo
    
    async def create_statement(
        self,
        statement_data: BankStatementCreate,
        user_id: str
    ) -> str:
        """Create new bank statement."""
        logger.info(f"Creating bank statement: {statement_data.date}")
        
        statement_doc = statement_data.model_dump()
        statement_doc.update({
            "user_id": user_id,
            "created_at": datetime.now(timezone.utc)
        })
        
        return await self.bank_repo.create(statement_doc)
    
    async def get_statement(self, statement_id: str) -> Dict[str, Any]:
        """Get statement by ID."""
        statement = await self.bank_repo.find_by_id(statement_id)
        if not statement:
            raise NotFoundError("Bank statement", statement_id)
        return statement
    
    async def list_statements(
        self,
        user_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """List bank statements with filters."""
        filters = {}
        
        if start_date:
            filters["date"] = {"$gte": start_date.isoformat()}
        if end_date:
            if "date" in filters:
                filters["date"]["$lte"] = end_date.isoformat()
            else:
                filters["date"] = {"$lte": end_date.isoformat()}
        
        return await self.bank_repo.find_by_user(
            user_id,
            filters=filters,
            skip=skip,
            limit=limit
        )
    
    async def update_statement(
        self,
        statement_id: str,
        update_data: BankStatementUpdate
    ) -> bool:
        """Update bank statement."""
        logger.info(f"Updating bank statement: {statement_id}")
        
        update_dict = update_data.model_dump(exclude_unset=True)
        if not update_dict:
            return True
        
        update_dict["updated_at"] = datetime.now(timezone.utc)
        
        return await self.bank_repo.update(statement_id, update_dict)
    
    async def delete_statement(self, statement_id: str) -> bool:
        """Delete bank statement."""
        logger.info(f"Deleting bank statement: {statement_id}")
        return await self.bank_repo.delete(statement_id)
    
    async def get_balance(
        self,
        user_id: str,
        account: Optional[str] = None
    ) -> Dict[str, Any]:
        """Calculate current balance."""
        statements = await self.bank_repo.find_by_user(user_id, limit=10000)
        
        if account:
            statements = [s for s in statements if s.get("account") == account]
        
        total_in = sum(s.get("amount_in", 0) for s in statements)
        total_out = sum(s.get("amount_out", 0) for s in statements)
        balance = total_in - total_out
        
        return {
            "balance": balance,
            "total_in": total_in,
            "total_out": total_out,
            "statement_count": len(statements),
            "account": account
        }
