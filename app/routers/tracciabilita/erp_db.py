"""
Connessione dedicata a azienda_erp_db (MongoDB Atlas - stesso cluster).
Usare `erp_db` in tutti i router /api/erp/*.
"""
import os
import re
from motor.motor_asyncio import AsyncIOMotorClient
from pathlib import Path


_MONGO_URL = os.environ['MONGO_URL']
_ERP_DB_NAME = os.environ.get('ERP_DB_NAME', 'azienda_erp_db')
# Usa lo stesso cluster Atlas ma DB diverso
_erp_client = AsyncIOMotorClient(_MONGO_URL)
erp_db = _erp_client[_ERP_DB_NAME]

AZIENDA_ID = "b0295759-35ce-4b34-a6b4-f01b883234ad"
