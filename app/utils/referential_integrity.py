"""
Referential Integrity Manager.
Manages database relationships and ensures data consistency.
Implements cascade updates and delete prevention.
"""
from typing import Dict, List, Any
from datetime import datetime, timezone
import logging
from bson import ObjectId

from app.database import Database
from app.exceptions import ValidationError

logger = logging.getLogger(__name__)


class ReferentialIntegrityManager:
    """
    Manages referential integrity across collections.
    
    Provides:
    - Cascade updates when referenced data changes
    - Delete prevention when data is referenced
    - Relationship tracking
    """
    
    # Define relationships: parent -> [children collections with field]
    # Le chiavi sono i nomi delle collezioni MongoDB (canonica italiana).
    # I valori sono le collezioni figlie con il campo che fa da foreign key.
    RELATIONSHIPS = {
        "fornitori": [   # ex "suppliers" — canonica italiana
            ("invoices", "supplier_id", "supplier_name"),
            ("warehouse_products", "supplier_id", "supplier_name")
        ],
        "warehouse_products": [
            ("invoice_products", "product_id", "product_name"),
            ("warehouse_movements", "product_id", "product_name"),
            ("rimanenze", "product_id", "product_name")
        ],
        "employees": [
            ("payslips", "employee_id", "employee_name"),
            ("libretti_sanitari", "employee_id", "employee_name")
        ],
        "invoices": [
            ("accounting_entries", "invoice_id", "invoice_number"),
            ("payments", "invoice_id", "invoice_number"),
            ("bank_statements", "invoice_id", "invoice_number")
        ]
    }
    
    def __init__(self):
        self.db = Database.get_db()
    
    async def check_can_delete(
        self,
        collection_name: str,
        document_id: str,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Check if document can be deleted.
        
        Returns dict with:
        - can_delete: bool
        - references: List of references preventing deletion
        - count: Total reference count
        """
        references = []
        total_count = 0
        
        # Get relationships for this collection
        relationships = self.RELATIONSHIPS.get(collection_name, [])
        
        for child_collection, foreign_key, _ in relationships:
            # Count references in child collection
            collection = self.db[child_collection]
            
            count = await collection.count_documents({
                "user_id": user_id,
                foreign_key: document_id
            })
            
            if count > 0:
                references.append({
                    "collection": child_collection,
                    "field": foreign_key,
                    "count": count
                })
                total_count += count
        
        can_delete = total_count == 0
        
        if not can_delete:
            logger.warning(
                f"Cannot delete {collection_name}/{document_id}: "
                f"{total_count} references found"
            )
        
        return {
            "can_delete": can_delete,
            "references": references,
            "total_count": total_count
        }
    
    async def cascade_update(
        self,
        collection_name: str,
        document_id: str,
        updates: Dict[str, Any],
        user_id: str
    ) -> Dict[str, int]:
        """
        Cascade updates to all related collections.
        
        When a parent document is updated, propagate changes to children.
        
        Args:
            collection_name: Parent collection
            document_id: Parent document ID
            updates: Fields to update
            user_id: User ID for filtering
            
        Returns:
            Dict with count of updated documents per collection
        """
        results = {}
        
        # Get relationships for this collection
        relationships = self.RELATIONSHIPS.get(collection_name, [])
        
        for child_collection, foreign_key, denormalized_field in relationships:
            # Check if we have an update for the denormalized field
            if denormalized_field not in updates:
                continue
            
            collection = self.db[child_collection]
            
            # Update all child documents
            update_result = await collection.update_many(
                {
                    "user_id": user_id,
                    foreign_key: document_id
                },
                {
                    "$set": {
                        denormalized_field: updates[denormalized_field],
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }
                }
            )
            
            count = update_result.modified_count
            if count > 0:
                results[child_collection] = count
                logger.info(
                    f"Cascaded update to {child_collection}: "
                    f"{count} documents updated"
                )
        
        return results
    
    async def get_references(
        self,
        collection_name: str,
        document_id: str,
        user_id: str,
        limit: int = 5
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get sample references for display.
        
        Useful for showing user what would be affected.
        """
        references = {}
        
        relationships = self.RELATIONSHIPS.get(collection_name, [])
        
        for child_collection, foreign_key, _ in relationships:
            collection = self.db[child_collection]
            
            # Get sample documents
            cursor = collection.find(
                {
                    "user_id": user_id,
                    foreign_key: document_id
                },
                limit=limit
            )
            
            docs = []
            async for doc in cursor:
                doc["id"] = str(doc.pop("_id"))
                # Include only essential fields
                essential = {
                    "id": doc["id"],
                    "collection": child_collection
                }
                
                # Add name/number field if available
                for field in ["name", "number", "description", "date"]:
                    if field in doc:
                        essential[field] = doc[field]
                        break
                
                docs.append(essential)
            
            if docs:
                references[child_collection] = docs
        
        return references
    
    async def cascade_delete(
        self,
        collection_name: str,
        document_id: str,
        user_id: str,
        force: bool = False
    ) -> Dict[str, int]:
        """
        Cascade delete to child collections (soft delete).
        
        WARNING: Use with caution!
        Only enabled if force=True.
        
        Args:
            collection_name: Parent collection
            document_id: Parent document ID
            user_id: User ID
            force: Must be True to enable cascade delete
            
        Returns:
            Dict with count of deleted documents per collection
        """
        if not force:
            raise ValidationError(
                "Cascade delete must be explicitly forced",
                "force"
            )
        
        results = {}
        
        relationships = self.RELATIONSHIPS.get(collection_name, [])
        
        for child_collection, foreign_key, _ in relationships:
            collection = self.db[child_collection]
            
            # Soft delete (set inactive/deleted flag)
            delete_result = await collection.update_many(
                {
                    "user_id": user_id,
                    foreign_key: document_id
                },
                {
                    "$set": {
                        "is_active": False,
                        "deleted_at": datetime.now(timezone.utc).isoformat(),
                        "deleted_reason": f"Parent {collection_name} deleted"
                    }
                }
            )
            
            count = delete_result.modified_count
            if count > 0:
                results[child_collection] = count
                logger.warning(
                    f"Cascade deleted in {child_collection}: "
                    f"{count} documents"
                )
        
        return results
    
    async def validate_foreign_key(
        self,
        collection_name: str,
        foreign_key: str,
        foreign_id: str,
        user_id: str
    ) -> bool:
        """
        Validate that foreign key reference exists.
        
        Args:
            collection_name: Parent collection to check
            foreign_key: Foreign key field name
            foreign_id: Foreign key value
            user_id: User ID
            
        Returns:
            True if reference exists, False otherwise
        """
        collection = self.db[collection_name]
        
        try:
            obj_id = ObjectId(foreign_id)
        except Exception:
            return False
        
        doc = await collection.find_one({
            "_id": obj_id,
            "user_id": user_id
        })
        
        return doc is not None
    
    async def get_relationship_summary(
        self,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Get summary of all relationships in database.
        
        Useful for debugging and monitoring.
        """
        summary = {}
        
        for parent_collection, relationships in self.RELATIONSHIPS.items():
            parent_count = await self.db[parent_collection].count_documents({
                "user_id": user_id
            })
            
            children_info = []
            for child_collection, foreign_key, denormalized_field in relationships:
                child_count = await self.db[child_collection].count_documents({
                    "user_id": user_id
                })
                
                children_info.append({
                    "collection": child_collection,
                    "foreign_key": foreign_key,
                    "denormalized_field": denormalized_field,
                    "count": child_count
                })
            
            summary[parent_collection] = {
                "count": parent_count,
                "children": children_info
            }
        
        return summary


# Singleton instance
referential_integrity = ReferentialIntegrityManager()
