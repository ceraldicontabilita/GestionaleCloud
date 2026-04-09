"""
Connessione dedicata al DB Gestionale (MongoDB Atlas - stesso cluster).
ERP_DB_NAME ora punta a 'Gestionale' (aggiornato da azienda_erp_db).
Usare `erp_db` in tutti i router /api/erp/*.
"""
import os
from motor.motor_asyncio import AsyncIOMotorClient


_MONGO_URL = os.environ['MONGO_URL']
# Default aggiornato: il DB di produzione si chiama "Gestionale"
_ERP_DB_NAME = os.environ.get('ERP_DB_NAME', 'Gestionale')
_erp_client = AsyncIOMotorClient(_MONGO_URL)
erp_db = _erp_client[_ERP_DB_NAME]

AZIENDA_ID = "b0295759-35ce-4b34-a6b4-f01b883234ad"
