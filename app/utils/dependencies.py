"""
FastAPI dependencies for dependency injection.
Provides reusable dependencies for authentication, database, etc.
AUTH_DISABLED: se True, tutti gli endpoint protetti usano utente admin di default.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, Dict, Any
from jose import jwt, JWTError
from datetime import datetime, timezone
import logging

from app.config import settings
from app.database import get_database
from app.exceptions import AuthenticationError

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)

# Utente admin di default quando AUTH_DISABLED=True
DEFAULT_ADMIN_USER = {
    "user_id": "admin",
    "email": "admin@ceraldi.it",
    "name": "Admin",
    "role": "admin"
}


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Dict[str, Any]:
    """
    Dependency to get current authenticated user from JWT token.
    Se AUTH_DISABLED=True restituisce utente admin di default senza validare il token.
    """
    # Modalità sviluppo: auth disabilitata
    if settings.AUTH_DISABLED:
        return DEFAULT_ADMIN_USER

    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"}
        )

    token = credentials.credentials

    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )

        user_id: str = payload.get("sub")
        if user_id is None:
            raise AuthenticationError("Invalid token: missing user ID")

        exp = payload.get("exp")
        if exp and datetime.fromtimestamp(exp, tz=timezone.utc) < datetime.now(timezone.utc):
            raise AuthenticationError("Token has expired")

        return {
            "user_id": user_id,
            "email": payload.get("email"),
            "name": payload.get("name"),
            "role": payload.get("role", "user")
        }

    except JWTError as e:
        logger.error(f"JWT validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"}
        )
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"}
        )


async def get_current_admin_user(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """Dependency to ensure current user has admin role."""
    if settings.AUTH_DISABLED:
        return DEFAULT_ADMIN_USER
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False))
) -> Optional[Dict[str, Any]]:
    """Dependency to optionally get current user (non fallisce se nessun token)."""
    if settings.AUTH_DISABLED:
        return DEFAULT_ADMIN_USER

    if not credentials:
        return None

    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )
        user_id = payload.get("sub")
        if not user_id:
            return None
        return {
            "user_id": user_id,
            "email": payload.get("email"),
            "name": payload.get("name"),
            "role": payload.get("role", "user")
        }
    except JWTError:
        return None


def require_feature(feature_name: str):
    """Dependency factory to check if a feature is enabled."""
    from app.config import FEATURES

    def check_feature():
        if not FEATURES.get(feature_name, False):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Feature '{feature_name}' is not enabled"
            )

    return check_feature


async def get_user_db(
    current_user: Dict[str, Any] = Depends(get_current_user),
    db=Depends(get_database)
):
    """Dependency to get database with user context."""
    return db, current_user["user_id"]


def pagination_params(
    skip: int = 0,
    limit: int = 100,
    sort_by: Optional[str] = None,
    sort_order: str = "asc"
) -> Dict[str, Any]:
    """Dependency for pagination parameters."""
    if limit > 1000:
        limit = 1000
    if limit < 1:
        limit = 1
    if skip < 0:
        skip = 0
    sort = None
    if sort_by:
        direction = 1 if sort_order.lower() == "asc" else -1
        sort = [(sort_by, direction)]
    return {"skip": skip, "limit": limit, "sort": sort}


def date_range_params(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None
) -> Dict[str, Optional[datetime]]:
    """Dependency for date range parameters."""
    from datetime import datetime

    result = {"date_from": None, "date_to": None}

    if date_from:
        try:
            result["date_from"] = datetime.strptime(date_from, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid date_from format. Expected YYYY-MM-DD, got: {date_from}"
            )

    if date_to:
        try:
            result["date_to"] = datetime.strptime(date_to, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid date_to format. Expected YYYY-MM-DD, got: {date_to}"
            )

    if result["date_from"] and result["date_to"]:
        if result["date_from"] > result["date_to"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="date_from must be before or equal to date_to"
            )

    return result

