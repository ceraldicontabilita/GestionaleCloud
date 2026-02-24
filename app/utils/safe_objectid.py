"""
Utility per gestione sicura degli ObjectId MongoDB.
Previene crash su ID non validi forniti dall'utente.
"""

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException
from typing import Optional
import re

# Pattern regex per validare ObjectId (24 caratteri hex)
OBJECTID_PATTERN = re.compile(r'^[0-9a-fA-F]{24}$')


def safe_objectid(value: str, field_name: str = "id") -> ObjectId:
    """
    Converte una stringa in ObjectId in modo sicuro.
    Lancia HTTPException 400 se l'ID non è valido.
    
    Args:
        value: stringa da convertire
        field_name: nome del campo (per messaggio errore)
    
    Returns:
        ObjectId valido
    
    Raises:
        HTTPException 400 se il valore non è un ObjectId valido
    """
    if not value or not isinstance(value, str):
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} non valido: valore vuoto o non stringa"
        )
    
    if not OBJECTID_PATTERN.match(value.strip()):
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} non valido: '{value}' non è un ObjectId MongoDB valido"
        )
    
    try:
        return ObjectId(value.strip())
    except (InvalidId, Exception):
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} non valido: '{value}'"
        )


def try_objectid(value: str) -> Optional[ObjectId]:
    """
    Versione non-throwing: restituisce None se l'ID non è valido.
    Utile per query opzionali.
    """
    try:
        if value and OBJECTID_PATTERN.match(str(value).strip()):
            return ObjectId(str(value).strip())
    except (InvalidId, Exception):
        pass
    return None
