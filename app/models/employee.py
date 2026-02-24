"""
Employee models.
Employee management, payslips, and health booklets for HORECA businesses.
"""
from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import Optional
from datetime import datetime, date as date_type


class Employee(BaseModel):
    """Employee record."""
    
    id: Optional[str] = Field(None, alias="_id")
    user_id: str = Field(default="admin")
    
    # Dati anagrafici
    codice_fiscale: str = Field(
        ...,
        description="Italian tax code (codice fiscale) - unique identifier"
    )
    first_name: str = Field(..., description="First name")
    last_name: str = Field(..., description="Last name")
    full_name: Optional[str] = Field(
        None,
        description="Auto-generated full name"
    )
    
    # Dati lavorativi
    role: str = Field(
        ...,
        description="Job role: cuoco, cameriere, barista, pasticcere, etc."
    )
    hire_date: date_type = Field(..., description="Hire date")
    termination_date: Optional[date_type] = Field(
        None,
        description="Termination date if employee left"
    )
    
    # Contatti
    email: Optional[str] = Field(None, description="Email address")
    phone: Optional[str] = Field(None, description="Phone number")
    address: Optional[str] = Field(None, description="Home address")
    
    # Contratto
    contract_type: Optional[str] = Field(
        None,
        description="Contract type: tempo indeterminato, determinato, etc."
    )
    hourly_rate: Optional[float] = Field(None, description="Hourly rate €/hour")
    monthly_salary: Optional[float] = Field(None, description="Monthly salary if fixed")
    
    # Status
    is_active: bool = Field(default=True, description="Whether employee is active")
    
    # Notes
    notes: Optional[str] = Field(None, description="Additional notes")
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict(populate_by_name=True)


class EmployeeCreate(BaseModel):
    """Employee creation request."""
    
    codice_fiscale: str = Field(..., min_length=16, max_length=16)
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    role: str = Field(..., min_length=1, max_length=100)
    hire_date: date_type
    
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    contract_type: Optional[str] = None
    hourly_rate: Optional[float] = Field(None, ge=0)
    monthly_salary: Optional[float] = Field(None, ge=0)
    notes: Optional[str] = None
    
    @field_validator('codice_fiscale')
    @classmethod
    def validate_cf(cls, v: str) -> str:
        """Validate codice fiscale format."""
        if not v.isalnum():
            raise ValueError("Codice fiscale must be alphanumeric")
        return v.upper()


class EmployeeUpdate(BaseModel):
    """Employee update request."""
    
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    role: Optional[str] = Field(None, min_length=1, max_length=100)
    
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    contract_type: Optional[str] = None
    hourly_rate: Optional[float] = Field(None, ge=0)
    monthly_salary: Optional[float] = Field(None, ge=0)
    
    is_active: Optional[bool] = None
    termination_date: Optional[date_type] = None
    notes: Optional[str] = None


class EmployeeResponse(BaseModel):
    """Employee response model."""
    
    id: str
    user_id: str
    codice_fiscale: str
    first_name: str
    last_name: str
    full_name: str
    role: str
    hire_date: date_type
    termination_date: Optional[date_type]
    email: Optional[str]
    phone: Optional[str]
    is_active: bool
    created_at: datetime


class Payslip(BaseModel):
    """Payslip (busta paga) record."""
    
    id: Optional[str] = Field(None, alias="_id")
    user_id: str = Field(default="admin")
    employee_id: str = Field(..., description="Employee ID reference")
    
    # Periodo
    period: str = Field(
        ...,
        description="Period in MM-YYYY format (e.g., 12-2024)"
    )
    month: int = Field(..., ge=1, le=12, description="Month (1-12)")
    year: int = Field(..., ge=2020, le=2100, description="Year")
    
    # Importi
    gross_salary: float = Field(
        ...,
        ge=0,
        description="Gross salary (retribuzione lorda)"
    )
    net_salary: float = Field(
        ...,
        ge=0,
        description="Net salary (retribuzione netta)"
    )
    
    # Detrazioni
    taxes: Optional[float] = Field(None, ge=0, description="Taxes withheld")
    social_security: Optional[float] = Field(
        None,
        ge=0,
        description="Social security contributions"
    )
    
    # File attachment
    pdf_filename: Optional[str] = Field(None, description="PDF filename if uploaded")
    pdf_path: Optional[str] = Field(None, description="PDF storage path")
    
    # Metadata
    notes: Optional[str] = None
    
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)
    
    model_config = ConfigDict(populate_by_name=True)


class PayslipCreate(BaseModel):
    """Payslip creation request."""
    
    employee_id: str
    period: str = Field(..., pattern=r"^\d{2}-\d{4}$")
    month: int = Field(..., ge=1, le=12)
    year: int = Field(..., ge=2020, le=2100)
    
    gross_salary: float = Field(..., ge=0)
    net_salary: float = Field(..., ge=0)
    
    taxes: Optional[float] = Field(None, ge=0)
    social_security: Optional[float] = Field(None, ge=0)
    
    notes: Optional[str] = None


class PayslipResponse(BaseModel):
    """Payslip response model."""
    
    id: str
    employee_id: str
    period: str
    month: int
    year: int
    gross_salary: float
    net_salary: float
    taxes: Optional[float]
    social_security: Optional[float]
    pdf_filename: Optional[str]
    uploaded_at: datetime


class LibrettoSanitario(BaseModel):
    """Libretto sanitario (health booklet) for food handlers."""
    
    id: Optional[str] = Field(None, alias="_id")
    user_id: str = Field(default="admin")
    employee_id: str = Field(..., description="Employee ID reference")
    
    # Date
    issue_date: date_type = Field(..., description="Issue date (data rilascio)")
    expiry_date: date_type = Field(..., description="Expiry date (data scadenza)")
    
    # Status
    status: str = Field(
        default="valid",
        description="Status: valid, expired, renewed, suspended"
    )
    
    # Dettagli
    issuing_authority: Optional[str] = Field(
        None,
        description="Authority that issued the booklet"
    )
    certificate_number: Optional[str] = Field(
        None,
        description="Certificate number"
    )
    
    # Notes
    notes: Optional[str] = Field(None, description="Additional notes")
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict(populate_by_name=True)


class LibrettoSanitarioCreate(BaseModel):
    """Libretto sanitario creation request."""
    
    employee_id: str
    issue_date: date_type
    expiry_date: date_type
    
    issuing_authority: Optional[str] = None
    certificate_number: Optional[str] = None
    notes: Optional[str] = None


class LibrettoSanitarioUpdate(BaseModel):
    """Libretto sanitario update request."""
    
    expiry_date: Optional[date_type] = None
    status: Optional[str] = Field(
        None,
        pattern="^(valid|expired|renewed|suspended)$"
    )
    
    issuing_authority: Optional[str] = None
    certificate_number: Optional[str] = None
    notes: Optional[str] = None


class LibrettoSanitarioResponse(BaseModel):
    """Libretto sanitario response model."""
    
    id: str
    employee_id: str
    issue_date: date_type
    expiry_date: date_type
    status: str
    issuing_authority: Optional[str]
    certificate_number: Optional[str]
    created_at: datetime


class EmployeeStats(BaseModel):
    """Employee statistics."""
    
    total_employees: int
    active_employees: int
    inactive_employees: int
    by_role: dict
    recent_hires: int
    expiring_libretti: int
