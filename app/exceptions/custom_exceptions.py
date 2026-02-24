"""
Custom exceptions for the application.
Provides specific exception types for different error scenarios.
"""
from typing import Optional, Any, Dict


class AppError(Exception):
    """Base application error."""
    
    def __init__(
        self,
        message: str,
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


class ValidationError(AppError):
    """Validation error (400)."""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=400, details=details)


class AuthenticationError(AppError):
    """Authentication error (401)."""
    
    def __init__(self, message: str = "Authentication failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=401, details=details)


class AuthorizationError(AppError):
    """Authorization error (403)."""
    
    def __init__(self, message: str = "Access forbidden", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=403, details=details)


class NotFoundError(AppError):
    """Resource not found error (404)."""
    
    def __init__(self, resource: str, identifier: Optional[str] = None):
        message = f"{resource} not found"
        if identifier:
            message += f": {identifier}"
        super().__init__(message, status_code=404, details={"resource": resource, "identifier": identifier})


class DuplicateError(AppError):
    """Duplicate resource error (409)."""
    
    def __init__(self, resource: str, field: str, value: Any):
        message = f"{resource} with {field}='{value}' already exists"
        super().__init__(
            message,
            status_code=409,
            details={"resource": resource, "field": field, "value": value}
        )


class DatabaseError(AppError):
    """Database operation error (500)."""
    
    def __init__(self, message: str = "Database operation failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=500, details=details)


class FileProcessingError(AppError):
    """File processing error (422)."""
    
    def __init__(self, filename: str, reason: str):
        message = f"Error processing file '{filename}': {reason}"
        super().__init__(
            message,
            status_code=422,
            details={"filename": filename, "reason": reason}
        )


class ExternalServiceError(AppError):
    """External service error (502)."""
    
    def __init__(self, service: str, message: str):
        full_message = f"External service '{service}' error: {message}"
        super().__init__(
            full_message,
            status_code=502,
            details={"service": service, "message": message}
        )


class BusinessLogicError(AppError):
    """Business logic validation error (422)."""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=422, details=details)


class TransactionError(AppError):
    """Transaction/atomic operation error (500)."""
    
    def __init__(self, message: str = "Transaction failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=500, details=details)


class RateLimitError(AppError):
    """Rate limit exceeded error (429)."""
    
    def __init__(self, message: str = "Rate limit exceeded", retry_after: Optional[int] = None):
        details = {}
        if retry_after:
            details['retry_after'] = retry_after
        super().__init__(message, status_code=429, details=details)


class ConfigurationError(AppError):
    """Configuration/setup error (500)."""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=500, details=details)


# Validation helpers
def validate_required_fields(data: Dict[str, Any], required_fields: list[str]) -> None:
    """
    Validate that all required fields are present in data.
    
    Args:
        data: Data dictionary to validate
        required_fields: List of required field names
        
    Raises:
        ValidationError: If any required field is missing
    """
    missing = [field for field in required_fields if field not in data or data[field] is None]
    if missing:
        raise ValidationError(
            f"Missing required fields: {', '.join(missing)}",
            details={"missing_fields": missing}
        )


def validate_date_format(date_str: str, field_name: str = "date") -> None:
    """
    Validate date string format (YYYY-MM-DD).
    
    Args:
        date_str: Date string to validate
        field_name: Name of the field for error message
        
    Raises:
        ValidationError: If date format is invalid
    """
    from datetime import datetime
    
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        raise ValidationError(
            f"Invalid date format for {field_name}. Expected YYYY-MM-DD, got: {date_str}",
            details={"field": field_name, "value": date_str, "expected_format": "YYYY-MM-DD"}
        )


def validate_numeric_range(
    value: float,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
    field_name: str = "value"
) -> None:
    """
    Validate that a numeric value is within specified range.
    
    Args:
        value: Numeric value to validate
        min_value: Minimum allowed value (inclusive)
        max_value: Maximum allowed value (inclusive)
        field_name: Name of the field for error message
        
    Raises:
        ValidationError: If value is out of range
    """
    if min_value is not None and value < min_value:
        raise ValidationError(
            f"{field_name} must be >= {min_value}, got: {value}",
            details={"field": field_name, "value": value, "min": min_value}
        )
    
    if max_value is not None and value > max_value:
        raise ValidationError(
            f"{field_name} must be <= {max_value}, got: {value}",
            details={"field": field_name, "value": value, "max": max_value}
        )
