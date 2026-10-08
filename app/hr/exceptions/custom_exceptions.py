"""Gerarchia delle eccezioni applicative — re-export del modulo unico.

La logica vive in `app.exceptions.custom_exceptions`. Fino al 19/09/2026 qui c'era una copia
**identica byte a byte** al lato ERP. Con il re-export le due gerarchie
diventano una sola classe per eccezione: un `except NotFoundError` scritto sul
lato ERP intercetta ora anche quella sollevata dal ramo HR, cosa che prima non
accadeva perche' erano due classi omonime e distinte.

Un modulo che non contiene logica non puo' divergere: e' questo il punto del
re-export. Il fork `app/hr` non nasceva per avere due comportamenti, ma per
avere due percorsi di import, e quelli restano.
"""
from app.exceptions.custom_exceptions import (  # noqa: F401
    AppError,
    AuthenticationError,
    AuthorizationError,
    BusinessLogicError,
    ConfigurationError,
    DatabaseError,
    DuplicateError,
    ExternalServiceError,
    FileProcessingError,
    NotFoundError,
    RateLimitError,
    TransactionError,
    ValidationError,
    validate_date_format,
    validate_numeric_range,
    validate_required_fields,
)

__all__ = [
    "AppError",
    "AuthenticationError",
    "AuthorizationError",
    "BusinessLogicError",
    "ConfigurationError",
    "DatabaseError",
    "DuplicateError",
    "ExternalServiceError",
    "FileProcessingError",
    "NotFoundError",
    "RateLimitError",
    "TransactionError",
    "ValidationError",
    "validate_date_format",
    "validate_numeric_range",
    "validate_required_fields",
]
