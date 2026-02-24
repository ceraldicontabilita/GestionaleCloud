"""
User repository for authentication and user management.
"""
from typing import Optional, Dict, Any
from datetime import datetime, timezone
import logging

from .base_repository import BaseRepository
from app.exceptions import NotFoundError, DuplicateError

logger = logging.getLogger(__name__)


class UserRepository(BaseRepository):
    """Repository for user operations."""
    
    async def find_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """
        Find user by email address.
        
        Args:
            email: User email address
            
        Returns:
            User document or None if not found
        """
        return await self.find_one({"email": email.lower()})
    
    async def find_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """
        Find user by username.
        
        Args:
            username: Username
            
        Returns:
            User document or None if not found
        """
        return await self.find_one({"username": username})
    
    async def email_exists(self, email: str) -> bool:
        """
        Check if email is already registered.
        
        Args:
            email: Email address to check
            
        Returns:
            True if email exists, False otherwise
        """
        return await self.exists({"email": email.lower()})
    
    async def create_user(self, user_data: Dict[str, Any]) -> str:
        """
        Create a new user.
        
        Args:
            user_data: User data including email, password_hash, etc.
            
        Returns:
            Created user ID
            
        Raises:
            DuplicateError: If email already exists
        """
        # Normalize email
        user_data["email"] = user_data["email"].lower()
        
        # Check for duplicate email
        if await self.email_exists(user_data["email"]):
            raise DuplicateError("User", "email", user_data["email"])
        
        # Set defaults
        if "role" not in user_data:
            user_data["role"] = "user"
        if "is_active" not in user_data:
            user_data["is_active"] = True
        
        logger.info(f"Creating new user: {user_data['email']}")
        return await self.create(user_data)
    
    async def update_last_login(self, user_id: str) -> bool:
        """
        Update user's last login timestamp.
        
        Args:
            user_id: User ID
            
        Returns:
            True if updated successfully
        """
        return await self.update(user_id, {"last_login": datetime.now(timezone.utc)})
    
    async def change_password(self, user_id: str, new_password_hash: str) -> bool:
        """
        Change user password.
        
        Args:
            user_id: User ID
            new_password_hash: New password hash
            
        Returns:
            True if updated successfully
            
        Raises:
            NotFoundError: If user not found
        """
        user = await self.find_by_id(user_id)
        if not user:
            raise NotFoundError("User", user_id)
        
        logger.info(f"Changing password for user: {user_id}")
        return await self.update(user_id, {"password_hash": new_password_hash})
    
    async def deactivate_user(self, user_id: str) -> bool:
        """
        Deactivate a user account.
        
        Args:
            user_id: User ID
            
        Returns:
            True if deactivated successfully
        """
        logger.warning(f"Deactivating user: {user_id}")
        return await self.update(user_id, {"is_active": False})
    
    async def activate_user(self, user_id: str) -> bool:
        """
        Activate a user account.
        
        Args:
            user_id: User ID
            
        Returns:
            True if activated successfully
        """
        logger.info(f"Activating user: {user_id}")
        return await self.update(user_id, {"is_active": True})
    
    async def find_active_users(self, skip: int = 0, limit: int = 100):
        """
        Find all active users.
        
        Args:
            skip: Number of users to skip
            limit: Maximum number of users to return
            
        Returns:
            List of active users
        """
        return await self.find_all(
            filter_query={"is_active": True},
            skip=skip,
            limit=limit,
            sort=[("created_at", -1)]
        )
    
    async def find_by_role(self, role: str, skip: int = 0, limit: int = 100):
        """
        Find users by role.
        
        Args:
            role: User role (admin, user, etc.)
            skip: Number of users to skip
            limit: Maximum number of users to return
            
        Returns:
            List of users with specified role
        """
        return await self.find_all(
            filter_query={"role": role},
            skip=skip,
            limit=limit,
            sort=[("created_at", -1)]
        )
    
    async def count_active_users(self) -> int:
        """
        Count active users.
        
        Returns:
            Number of active users
        """
        return await self.count({"is_active": True})
