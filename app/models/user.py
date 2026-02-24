"""
User authentication models.
Pydantic schemas for user registration, login, and token management.
"""
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from typing import Optional
from datetime import datetime


class UserRegister(BaseModel):
    """User registration request."""
    email: EmailStr
    password: str = Field(..., min_length=8)
    name: Optional[str] = None
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "user@example.com",
                "password": "securepassword123",
                "name": "Mario Rossi"
            }
        }
    )


class UserLogin(BaseModel):
    """
    User login request.
    Accepts either email OR username for login.
    """
    username: Optional[str] = None
    email: Optional[str] = None
    password: str
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "user@example.com",
                "password": "securepassword123"
            }
        }
    )
    
    def model_post_init(self, __context):
        """Validate that at least email or username is provided."""
        if not self.email and not self.username:
            raise ValueError("Either email or username must be provided")


class TokenResponse(BaseModel):
    """JWT token response."""
    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str
    name: Optional[str] = None


class UserInDB(BaseModel):
    """User document in database."""
    id: Optional[str] = Field(None, alias="_id")
    email: str
    password_hash: str
    name: Optional[str] = None
    role: str = "user"
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_login: Optional[datetime] = None
    
    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "email": "admin@azienda.com",
                "name": "Admin User",
                "role": "admin",
                "is_active": True
            }
        }
    )


class UserResponse(BaseModel):
    """User response (without sensitive data)."""
    id: str
    email: str
    name: Optional[str] = None
    role: str
    is_active: bool
    created_at: datetime
    last_login: Optional[datetime] = None


class UserUpdate(BaseModel):
    """User update request."""
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Mario Rossi Updated",
                "role": "admin"
            }
        }
    )


class PasswordChange(BaseModel):
    """Password change request."""
    old_password: str
    new_password: str = Field(..., min_length=8)
