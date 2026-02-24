"""
Accounting extended models.
Chart of accounts and advanced accounting features.
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime


class ChartOfAccount(BaseModel):
    """Chart of accounts entry (Piano dei conti)."""
    
    id: Optional[str] = Field(None, alias="_id")
    user_id: str = Field(default="admin")
    
    # Account details
    code: str = Field(..., description="Account code (e.g., 1.01.01)")
    name: str = Field(..., description="Account name")
    
    # Type
    type: str = Field(
        ...,
        description="Type: attivo, passivo, costi, ricavi"
    )
    
    # Hierarchy
    parent_id: Optional[str] = Field(None, description="Parent account ID")
    level: int = Field(default=0, description="Hierarchy level")
    
    # Status
    is_active: bool = Field(default=True)
    
    # Notes
    description: Optional[str] = None
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict(populate_by_name=True)


class ChartOfAccountCreate(BaseModel):
    """Chart of account creation request."""
    
    code: str = Field(..., min_length=1, max_length=20)
    name: str = Field(..., min_length=1, max_length=200)
    type: str = Field(..., pattern="^(attivo|passivo|costi|ricavi)$")
    parent_id: Optional[str] = None
    description: Optional[str] = None


class ChartOfAccountUpdate(BaseModel):
    """Chart of account update request."""
    
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    type: Optional[str] = Field(None, pattern="^(attivo|passivo|costi|ricavi)$")
    is_active: Optional[bool] = None
    description: Optional[str] = None
