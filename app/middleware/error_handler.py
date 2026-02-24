"""
Error handling middleware for FastAPI.
Provides centralized exception handling and error responses.
"""
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
import logging
import uuid

try:
    # Try relative import (when used as package)
    from app.exceptions import (
        AppError,
        ValidationError,
        AuthenticationError,
        AuthorizationError,
        NotFoundError,
        DuplicateError,
        DatabaseError,
        FileProcessingError,
        ExternalServiceError,
        BusinessLogicError,
        TransactionError,
        RateLimitError,
        ConfigurationError
    )
except ImportError:
    # Fallback to absolute import (when main.py is entry point)
    from exceptions import (
        AppError
    )

logger = logging.getLogger(__name__)


def add_exception_handlers(app: FastAPI) -> None:
    """
    Add exception handlers to FastAPI application.
    
    Args:
        app: FastAPI application instance
    """
    
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        """Handle custom AppError exceptions."""
        request_id = str(uuid.uuid4())[:8]
        logger.error(
            f"[{request_id}] AppError: {exc.message}",
            extra={
                "status_code": exc.status_code,
                "details": exc.details,
                "path": request.url.path,
                "method": request.method,
                "request_id": request_id
            }
        )
        
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.__class__.__name__,
                "message": exc.message,
                "details": exc.details,
                "request_id": request_id
            }
        )
    
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        """Handle Pydantic validation errors."""
        request_id = str(uuid.uuid4())[:8]
        logger.warning(
            f"[{request_id}] Validation error: {exc.errors()}",
            extra={
                "path": request.url.path,
                "method": request.method,
                "request_id": request_id
            }
        )
        
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": "ValidationError",
                "message": "Request validation failed",
                "details": exc.errors(),
                "request_id": request_id
            }
        )
    
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        """Handle HTTP exceptions."""
        request_id = str(uuid.uuid4())[:8]
        logger.warning(
            f"[{request_id}] HTTP {exc.status_code}: {exc.detail}",
            extra={
                "path": request.url.path,
                "method": request.method,
                "request_id": request_id
            }
        )
        
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": "HTTPException",
                "message": exc.detail,
                "request_id": request_id
            }
        )
    
    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        """Handle all other unhandled exceptions."""
        request_id = str(uuid.uuid4())[:8]
        logger.error(
            f"[{request_id}] Unhandled exception: {str(exc)}",
            exc_info=True,
            extra={
                "path": request.url.path,
                "method": request.method,
                "request_id": request_id
            }
        )
        
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "InternalServerError",
                "message": "An unexpected error occurred",
                "request_id": request_id
            }
        )
