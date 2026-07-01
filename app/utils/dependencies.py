"""
FastAPI dependencies for dependency injection.
Provides reusable dependencies for authentication, database, etc.
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


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Dict[str, Any]:
    """
    Dependency to get current authenticated user from JWT token.

    In produzione ogni richiesta che arriva qui è già passata per
    AuthenticationMiddleware (safety net globale su tutte le rotte /api/*
    non whitelistate), quindi credentials è già garantito non-None. Questo
    controllo fallisce chiuso (401) invece di restituire un utente admin
    fittizio, così una futura rotta whitelistata che usi questa dependency
    non ottiene accesso admin gratuito senza token.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"}
        )

    token = credentials.credentials
    
    try:
        # Decode JWT token
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )
        
        # Extract user data
        user_id: str = payload.get("sub")
        if user_id is None:
            raise AuthenticationError("Invalid token: missing user ID")
        
        # Check token expiration (timezone-aware)
        exp = payload.get("exp")
        if exp and datetime.fromtimestamp(exp, tz=timezone.utc) < datetime.now(timezone.utc):
            raise AuthenticationError("Token has expired")
        
        # Return user data
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
    """
    Dependency to ensure current user has admin role.
    
    Args:
        current_user: User data from get_current_user dependency
        
    Returns:
        User data if user is admin
        
    Raises:
        HTTPException: If user is not admin
        
    Usage:
        @router.delete("/admin-only")
        async def admin_only_route(admin_user: dict = Depends(get_current_admin_user)):
            ...
    """
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    
    return current_user


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False))
) -> Optional[Dict[str, Any]]:
    """
    Dependency to optionally get current user (doesn't fail if no token).
    
    Args:
        credentials: Optional HTTP Bearer token
        
    Returns:
        User data if token provided and valid, None otherwise
        
    Usage:
        @router.get("/public-with-optional-auth")
        async def route(user: Optional[dict] = Depends(get_optional_user)):
            if user:
                # Personalized response
            else:
                # Public response
    """
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
    """
    Dependency factory to check if a feature is enabled.
    
    Args:
        feature_name: Name of the feature to check
        
    Returns:
        Dependency function that raises exception if feature is disabled
        
    Usage:
        @router.post("/send-email", dependencies=[Depends(require_feature("smtp_email"))])
        async def send_email():
            ...
    """
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
    db = Depends(get_database)
):
    """
    Dependency to get database with user context.
    
    Args:
        current_user: Current authenticated user
        db: Database instance
        
    Returns:
        Tuple of (database, user_id)
        
    Usage:
        @router.get("/user-data")
        async def get_user_data(user_db = Depends(get_user_db)):
            db, user_id = user_db
            ...
    """
    return db, current_user["user_id"]


def pagination_params(
    skip: int = 0,
    limit: int = 100,
    sort_by: Optional[str] = None,
    sort_order: str = "asc"
) -> Dict[str, Any]:
    """
    Dependency for pagination parameters.
    
    Args:
        skip: Number of items to skip
        limit: Maximum number of items to return (max 1000)
        sort_by: Field to sort by
        sort_order: Sort order ('asc' or 'desc')
        
    Returns:
        Dictionary with pagination parameters
        
    Usage:
        @router.get("/items")
        async def list_items(pagination: dict = Depends(pagination_params)):
            skip = pagination['skip']
            limit = pagination['limit']
            ...
    """
    # Validate and clamp limit
    if limit > 1000:
        limit = 1000
    if limit < 1:
        limit = 1
    
    # Validate skip
    if skip < 0:
        skip = 0
    
    # Parse sort
    sort = None
    if sort_by:
        direction = 1 if sort_order.lower() == "asc" else -1
        sort = [(sort_by, direction)]
    
    return {
        "skip": skip,
        "limit": limit,
        "sort": sort
    }


def date_range_params(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None
) -> Dict[str, Optional[datetime]]:
    """
    Dependency for date range parameters.
    
    Args:
        date_from: Start date (YYYY-MM-DD)
        date_to: End date (YYYY-MM-DD)
        
    Returns:
        Dictionary with parsed datetime objects
        
    Raises:
        HTTPException: If date format is invalid
        
    Usage:
        @router.get("/reports")
        async def get_report(date_range: dict = Depends(date_range_params)):
            date_from = date_range['date_from']
            date_to = date_range['date_to']
            ...
    """
    from datetime import datetime
    
    result = {
        "date_from": None,
        "date_to": None
    }
    
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
    
    # Validate date range
    if result["date_from"] and result["date_to"]:
        if result["date_from"] > result["date_to"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="date_from must be before or equal to date_to"
            )
    
    return result
