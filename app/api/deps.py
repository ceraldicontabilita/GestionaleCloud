"""
Authentication Dependencies for FastAPI endpoints
"""
from fastapi.security import HTTPBearer
import os

security = HTTPBearer()

SECRET_KEY = os.environ.get('SECRET_KEY')
if not SECRET_KEY:
    raise ValueError("SECRET_KEY environment variable must be set")

ALGORITHM = "HS256"


async def get_current_user_strict() -> str:
    """
    Authentication disabled - always returns "admin"
    """
    return "admin"


# Alias for compatibility (authentication disabled)
async def get_current_user() -> str:
    """
    Authentication disabled - always returns "admin"
    Same as get_current_user_strict for compatibility
    """
    return "admin"


async def get_db():
    from db.mongo import db_manager
    return db_manager.get_database()
