"""Repository CRUD condiviso dai archivi del runtime."""
from typing import Optional, List, Dict, Any, Generic, TypeVar
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

T = TypeVar('T')


class BaseRepository(Generic[T]):
    """
    Repository generico per i fogli documentali.

    Provides standard methods: create, find_by_id, find_all, update, delete, etc.
    """

    def __init__(self, collection: Any):
        """
        Inizializza il repository con un foglio documentale.

        Args:
            collection: tabella asincrona dell'archivio del runtime
        """
        self.collection = collection

    def _build_id_filter(self, doc_id: Any) -> Dict[str, Any]:
        """Filtro per l'identificativo, valido su entrambi gli archivi.

        I due adattatori tengono la chiave in due campi diversi: il runtime
        dell'ERP (`services/supabase_runtime_database.py`) indicizza i
        documenti per `_id`, quello dell'app HR (`app/hr/db_supabase.py`) per
        `id`. Un filtro su un campo solo funziona di qua e fallisce di la'.

        Misurato il 19/09/2026: l'unico utente HR (`hr.app_users`) non aveva
        MAI ricevuto un `last_login`, perche' la copia HR di questo file
        costruiva un `ObjectId(doc_id)` su un identificativo testuale — un
        `InvalidId` inghiottito dall'`except`, e `update_last_login` che
        tornava False in silenzio a ogni accesso col PIN.
        """
        chiave = str(doc_id)
        return {"$or": [{"_id": chiave}, {"id": chiave}]}

    async def create(self, document: Dict[str, Any]) -> str:
        """
        Create a new document.

        Args:
            document: Document data

        Returns:
            str: Created document ID
        """
        if 'created_at' not in document:
            document['created_at'] = datetime.now(timezone.utc)
        if 'updated_at' not in document:
            document['updated_at'] = datetime.now(timezone.utc)

        result = await self.collection.insert_one(document.copy())
        logger.info(f"Created document in {self.collection.name}: {result.inserted_id}")
        return str(result.inserted_id)

    async def find_by_id(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """
        Find document by ID.

        Args:
            doc_id: identificativo del record

        Returns:
            Document data or None if not found
        """
        try:
            document = await self.collection.find_one(self._build_id_filter(doc_id))

            if document:
                # Su un archivio che non tiene `_id` il vecchio
                # `document.pop('_id')` sollevava KeyError, l'except lo
                # inghiottiva e il documento trovato tornava comunque None.
                chiave = document.pop('_id', None)
                if chiave is not None:
                    document['id'] = str(chiave)

            return document
        except Exception as e:
            logger.error(f"Error finding document by ID {doc_id}: {e}")
            return None

    async def find_one(self, filter_query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Find single document matching filter.

        Args:
            filter_query: filtro documentale

        Returns:
            Document data or None if not found
        """
        document = await self.collection.find_one(filter_query)

        if document and '_id' in document:
            document['id'] = str(document.pop('_id'))

        return document

    async def find_all(
        self,
        filter_query: Optional[Dict[str, Any]] = None,
        skip: int = 0,
        limit: int = 100,
        sort: Optional[List[tuple]] = None
    ) -> List[Dict[str, Any]]:
        """
        Find all documents matching filter with pagination.

        Args:
            filter_query: filtro documentale (None per tutti i record)
            skip: Number of documents to skip
            limit: Maximum number of documents to return
            sort: List of (field, direction) tuples for sorting

        Returns:
            List of documents
        """
        query = filter_query or {}
        cursor = self.collection.find(query).skip(skip).limit(limit)

        if sort:
            cursor = cursor.sort(sort)

        documents = await cursor.to_list(length=limit)

        for doc in documents:
            if '_id' in doc:
                doc['id'] = str(doc.pop('_id'))

        return documents

    async def count(self, filter_query: Optional[Dict[str, Any]] = None) -> int:
        """
        Count documents matching filter.

        Args:
            filter_query: filtro documentale

        Returns:
            Number of matching documents
        """
        query = filter_query or {}
        return await self.collection.count_documents(query)

    async def update(
        self,
        doc_id: str,
        update_data: Dict[str, Any],
        upsert: bool = False
    ) -> bool:
        """
        Update document by ID.

        Args:
            doc_id: Document ID
            update_data: Fields to update
            upsert: Create document if not exists

        Returns:
            True if updated, False otherwise
        """
        update_data['updated_at'] = datetime.now(timezone.utc)

        try:
            result = await self.collection.update_one(
                self._build_id_filter(doc_id),
                {"$set": update_data},
                upsert=upsert
            )

            if result.modified_count > 0 or result.upserted_id:
                logger.info(f"Updated document in {self.collection.name}: {doc_id}")
                return True

            return False
        except Exception as e:
            logger.error(f"Error updating document {doc_id}: {e}")
            return False

    async def update_many(
        self,
        filter_query: Dict[str, Any],
        update_data: Dict[str, Any]
    ) -> int:
        """
        Update multiple documents matching filter.

        Args:
            filter_query: filtro documentale
            update_data: Fields to update

        Returns:
            Number of documents updated
        """
        update_data['updated_at'] = datetime.now(timezone.utc)

        result = await self.collection.update_many(
            filter_query,
            {"$set": update_data}
        )

        logger.info(f"Updated {result.modified_count} documents in {self.collection.name}")
        return result.modified_count

    async def delete(self, doc_id: str) -> bool:
        """
        Delete document by ID.

        Args:
            doc_id: Document ID

        Returns:
            True if deleted, False otherwise
        """
        try:
            result = await self.collection.delete_one(self._build_id_filter(doc_id))

            if result.deleted_count > 0:
                logger.info(f"Deleted document from {self.collection.name}: {doc_id}")
                return True

            return False
        except Exception as e:
            logger.error(f"Error deleting document {doc_id}: {e}")
            return False

    async def delete_many(self, filter_query: Dict[str, Any]) -> int:
        """
        Delete multiple documents matching filter.

        Args:
            filter_query: filtro documentale

        Returns:
            Number of documents deleted
        """
        result = await self.collection.delete_many(filter_query)
        logger.info(f"Deleted {result.deleted_count} documents from {self.collection.name}")
        return result.deleted_count

    async def exists(self, filter_query: Dict[str, Any]) -> bool:
        """
        Check if document exists matching filter.

        Args:
            filter_query: filtro documentale

        Returns:
            True if exists, False otherwise
        """
        count = await self.collection.count_documents(filter_query, limit=1)
        return count > 0

    async def aggregate(self, pipeline: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Execute aggregation pipeline.

        Args:
            pipeline: aggregazione documentale

        Returns:
            List of aggregation results
        """
        cursor = self.collection.aggregate(pipeline)
        results = await cursor.to_list(length=None)

        for result in results:
            if '_id' in result:
                result['id'] = str(result.pop('_id'))

        return results

    async def bulk_create(self, documents: List[Dict[str, Any]]) -> List[str]:
        """
        Create multiple documents in bulk.

        Args:
            documents: List of documents to create

        Returns:
            List of created document IDs
        """
        now = datetime.now(timezone.utc)
        for doc in documents:
            if 'created_at' not in doc:
                doc['created_at'] = now
            if 'updated_at' not in doc:
                doc['updated_at'] = now

        result = await self.collection.insert_many(documents)
        logger.info(f"Created {len(result.inserted_ids)} documents in {self.collection.name}")
        return [str(doc_id) for doc_id in result.inserted_ids]

    async def find_by_user(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 100,
        sort: Optional[List[tuple]] = None
    ) -> List[Dict[str, Any]]:
        """
        Find all documents belonging to a specific user.

        Args:
            user_id: User ID
            skip: Number of documents to skip
            limit: Maximum number of documents to return
            sort: List of (field, direction) tuples for sorting

        Returns:
            List of user documents
        """
        return await self.find_all(
            filter_query={"user_id": user_id},
            skip=skip,
            limit=limit,
            sort=sort
        )

    async def soft_delete(self, doc_id: str) -> bool:
        """
        Soft delete document (mark as deleted instead of removing).

        Args:
            doc_id: Document ID

        Returns:
            True if marked as deleted, False otherwise
        """
        return await self.update(
            doc_id,
            {
                "is_deleted": True,
                "deleted_at": datetime.now(timezone.utc)
            }
        )
