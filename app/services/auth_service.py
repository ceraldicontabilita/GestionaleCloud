"""
Authentication service.
Handles user registration, login, and JWT token management.
"""
from typing import Dict, Any, Optional
from datetime import datetime, timedelta, timezone
import bcrypt
from jose import jwt
import logging

from app.config import settings
from app.repositories import UserRepository
from app.exceptions import (
    AuthenticationError,
    ValidationError,
    DuplicateError,
    NotFoundError
)
from app.models import UserRegister, UserLogin, TokenResponse

logger = logging.getLogger(__name__)


class AuthService:
    """Service for authentication operations."""
    
    def __init__(self, user_repo: UserRepository):
        """
        Initialize auth service.
        
        Args:
            user_repo: User repository instance
        """
        self.user_repo = user_repo
    
    def _hash_password(self, password: str) -> str:
        """
        Hash password using bcrypt.
        
        Args:
            password: Plain text password
            
        Returns:
            Hashed password
        """
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
        return hashed.decode('utf-8')
    
    def _verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """
        Verify password against hash.
        
        Args:
            plain_password: Plain text password
            hashed_password: Hashed password
            
        Returns:
            True if password matches
        """
        return bcrypt.checkpw(
            plain_password.encode('utf-8'),
            hashed_password.encode('utf-8')
        )
    
    def _create_access_token(
        self,
        user_id: str,
        email: str,
        name: Optional[str],
        role: str
    ) -> str:
        """
        Create JWT access token.
        
        Args:
            user_id: User ID
            email: User email
            name: User name
            role: User role
            
        Returns:
            JWT token string
        """
        expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        expire = datetime.now(timezone.utc) + expires_delta
        
        payload = {
            "sub": user_id,
            "email": email,
            "name": name,
            "role": role,
            "exp": expire,
            "iat": datetime.now(timezone.utc)
        }
        
        token = jwt.encode(
            payload,
            settings.SECRET_KEY,
            algorithm=settings.ALGORITHM
        )
        
        return token
    
    async def register(self, user_data: UserRegister) -> TokenResponse:
        """
        Register a new user.
        
        Args:
            user_data: User registration data
            
        Returns:
            Token response with JWT
            
        Raises:
            DuplicateError: If email already exists
            ValidationError: If data is invalid
        """
        logger.info(f"Registering new user: {user_data.email}")
        
        # Validate password strength
        if len(user_data.password) < 8:
            raise ValidationError("Password must be at least 8 characters long")
        
        # Check if email already exists
        if await self.user_repo.email_exists(user_data.email):
            raise DuplicateError("User", "email", user_data.email)
        
        # Hash password
        password_hash = self._hash_password(user_data.password)
        
        # Create user document
        user_doc = {
            "email": user_data.email.lower(),
            "password_hash": password_hash,
            "name": user_data.name,
            "role": "user",  # Default role
            "is_active": True,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        }
        
        # Save to database
        user_id = await self.user_repo.create_user(user_doc)
        
        # Create JWT token
        token = self._create_access_token(
            user_id=user_id,
            email=user_data.email,
            name=user_data.name,
            role="user"
        )
        
        logger.info(f"✅ User registered successfully: {user_data.email}")
        
        return TokenResponse(
            access_token=token,
            token_type="bearer",
            user_id=user_id,
            email=user_data.email,
            name=user_data.name
        )
    
    async def login(self, credentials: UserLogin) -> TokenResponse:
        """
        Authenticate user and return JWT token.
        Accepts either email OR username.
        
        Args:
            credentials: User login credentials (email or username + password)
            
        Returns:
            Token response with JWT
            
        Raises:
            AuthenticationError: If credentials are invalid
        """
        identifier = credentials.email or credentials.username
        logger.info(f"Login attempt for: {identifier}")
        
        # Find user by email OR username
        user = None
        if credentials.email:
            user = await self.user_repo.find_by_email(credentials.email)
        elif credentials.username:
            user = await self.user_repo.find_by_username(credentials.username)
        
        if not user:
            logger.warning(f"Login failed: user not found - {identifier}")
            raise AuthenticationError("Invalid credentials")
        
        # Check if user is active
        if not user.get("is_active", True):
            logger.warning(f"Login failed: user inactive - {identifier}")
            raise AuthenticationError("Account is disabled")
        
        # Verify password
        if not self._verify_password(credentials.password, user["password_hash"]):
            logger.warning(f"Login failed: invalid password - {identifier}")
            raise AuthenticationError("Invalid credentials")
        
        # Update last login timestamp
        await self.user_repo.update_last_login(user["id"])
        
        # Create JWT token
        token = self._create_access_token(
            user_id=user["id"],
            email=user["email"],
            name=user.get("name"),
            role=user.get("role", "user")
        )
        
        logger.info(f"✅ Login successful: {identifier}")
        
        return TokenResponse(
            access_token=token,
            token_type="bearer",
            user_id=user["id"],
            email=user["email"],
            name=user.get("name")
        )
    
    async def change_password(
        self,
        user_id: str,
        old_password: str,
        new_password: str
    ) -> bool:
        """
        Change user password.
        
        Args:
            user_id: User ID
            old_password: Current password
            new_password: New password
            
        Returns:
            True if password changed successfully
            
        Raises:
            NotFoundError: If user not found
            AuthenticationError: If old password is incorrect
            ValidationError: If new password is invalid
        """
        logger.info(f"Password change request for user: {user_id}")
        
        # Validate new password
        if len(new_password) < 8:
            raise ValidationError("New password must be at least 8 characters long")
        
        # Get user
        user = await self.user_repo.find_by_id(user_id)
        if not user:
            raise NotFoundError("User", user_id)
        
        # Verify old password
        if not self._verify_password(old_password, user["password_hash"]):
            logger.warning(f"Password change failed: invalid old password - {user_id}")
            raise AuthenticationError("Current password is incorrect")
        
        # Hash new password
        new_password_hash = self._hash_password(new_password)
        
        # Update password
        success = await self.user_repo.change_password(user_id, new_password_hash)
        
        if success:
            logger.info(f"✅ Password changed successfully for user: {user_id}")
        
        return success
    
    async def verify_token(self, token: str) -> Dict[str, Any]:
        """
        Verify JWT token and return user data.
        
        Args:
            token: JWT token string
            
        Returns:
            User data from token payload
            
        Raises:
            AuthenticationError: If token is invalid or expired
        """
        try:
            payload = jwt.decode(
                token,
                settings.SECRET_KEY,
                algorithms=[settings.ALGORITHM]
            )
            
            user_id = payload.get("sub")
            if not user_id:
                raise AuthenticationError("Invalid token: missing user ID")
            
            # Check expiration
            exp = payload.get("exp")
            if exp and datetime.fromtimestamp(exp, tz=timezone.utc) < datetime.now(timezone.utc):
                raise AuthenticationError("Token has expired")
            
            return {
                "user_id": user_id,
                "email": payload.get("email"),
                "name": payload.get("name"),
                "role": payload.get("role", "user")
            }
            
        except jwt.JWTError as e:
            logger.error(f"Token verification failed: {e}")
            raise AuthenticationError("Invalid token")
    
    async def get_user_profile(self, user_id: str) -> Dict[str, Any]:
        """
        Get user profile (without sensitive data).
        
        Args:
            user_id: User ID
            
        Returns:
            User profile data
            
        Raises:
            NotFoundError: If user not found
        """
        user = await self.user_repo.find_by_id(user_id)
        
        if not user:
            raise NotFoundError("User", user_id)
        
        # Remove sensitive data
        profile = {
            "id": user["id"],
            "email": user["email"],
            "name": user.get("name"),
            "role": user.get("role", "user"),
            "is_active": user.get("is_active", True),
            "created_at": user.get("created_at"),
            "last_login": user.get("last_login")
        }
        
        return profile
    
    async def deactivate_user(self, user_id: str) -> bool:
        """
        Deactivate a user account (admin only).
        
        Args:
            user_id: User ID to deactivate
            
        Returns:
            True if deactivated successfully
        """
        logger.warning(f"Deactivating user: {user_id}")
        return await self.user_repo.deactivate_user(user_id)
    
    async def activate_user(self, user_id: str) -> bool:
        """
        Activate a user account (admin only).
        
        Args:
            user_id: User ID to activate
            
        Returns:
            True if activated successfully
        """
        logger.info(f"Activating user: {user_id}")
        return await self.user_repo.activate_user(user_id)
