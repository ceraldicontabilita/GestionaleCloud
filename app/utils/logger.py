"""
Structured logging configuration for the application.
Provides consistent logging across all modules.
"""
import logging
import sys
import json
from datetime import datetime, timezone
from typing import Any, Dict
from pathlib import Path
from app.config import settings


class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging."""
    
    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record as JSON.
        
        Args:
            record: Log record to format
            
        Returns:
            JSON string of log record
        """
        log_data: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }
        
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        # Add extra fields if present
        if hasattr(record, 'user_id'):
            log_data['user_id'] = record.user_id
        if hasattr(record, 'request_id'):
            log_data['request_id'] = record.request_id
        if hasattr(record, 'duration_ms'):
            log_data['duration_ms'] = record.duration_ms
        
        return json.dumps(log_data)


class TextFormatter(logging.Formatter):
    """Custom text formatter for human-readable logs."""
    
    def __init__(self):
        super().__init__(
            fmt='%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )


def setup_logging() -> None:
    """
    Setup application logging based on configuration.
    Called once at application startup.
    """
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper()))
    
    # Remove existing handlers
    root_logger.handlers.clear()
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, settings.LOG_LEVEL.upper()))
    
    # Choose formatter based on config
    if settings.LOG_FORMAT.lower() == "json":
        formatter = JSONFormatter()
    else:
        formatter = TextFormatter()
    
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # File handler (optional)
    if settings.LOG_FILE:
        log_file_path = Path(settings.LOG_FILE)
        log_file_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler(log_file_path)
        file_handler.setLevel(getattr(logging, settings.LOG_LEVEL.upper()))
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    
    # Set levels for third-party loggers
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("motor").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    
    root_logger.info(f"✅ Logging configured: level={settings.LOG_LEVEL}, format={settings.LOG_FORMAT}")


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for a module.
    
    Args:
        name: Logger name (usually __name__)
        
    Returns:
        Logger instance
        
    Example:
        logger = get_logger(__name__)
        logger.info("Message")
    """
    return logging.getLogger(name)


class LoggerAdapter(logging.LoggerAdapter):
    """
    Logger adapter to add contextual information to logs.
    
    Example:
        logger = LoggerAdapter(logging.getLogger(__name__), {"user_id": "123"})
        logger.info("User action", extra={"action": "login"})
    """
    
    def process(self, msg: str, kwargs: Dict[str, Any]) -> tuple:
        """Add contextual data to log record."""
        # Merge context with extra fields
        extra = kwargs.get('extra', {})
        extra.update(self.extra)
        kwargs['extra'] = extra
        return msg, kwargs


def log_function_call(logger: logging.Logger):
    """
    Decorator to log function calls with arguments and execution time.
    
    Args:
        logger: Logger instance to use
        
    Example:
        @log_function_call(logger)
        async def my_function(arg1, arg2):
            ...
    """
    def decorator(func):
        import functools
        import time
        
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            func_name = func.__name__
            start_time = time.time()
            
            logger.debug(f"Calling {func_name} with args={args[:2] if args else []}, kwargs={list(kwargs.keys())[:5]}")
            
            try:
                result = await func(*args, **kwargs)
                duration_ms = (time.time() - start_time) * 1000
                logger.info(f"✅ {func_name} completed in {duration_ms:.2f}ms")
                return result
            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000
                logger.error(f"❌ {func_name} failed after {duration_ms:.2f}ms: {str(e)}", exc_info=True)
                raise
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            func_name = func.__name__
            start_time = time.time()
            
            logger.debug(f"Calling {func_name} with args={args[:2] if args else []}, kwargs={list(kwargs.keys())[:5]}")
            
            try:
                result = func(*args, **kwargs)
                duration_ms = (time.time() - start_time) * 1000
                logger.info(f"✅ {func_name} completed in {duration_ms:.2f}ms")
                return result
            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000
                logger.error(f"❌ {func_name} failed after {duration_ms:.2f}ms: {str(e)}", exc_info=True)
                raise
        
        # Return appropriate wrapper based on whether function is async
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


# Convenience functions for common log patterns
def log_api_request(logger: logging.Logger, method: str, path: str, user_id: str = None):
    """Log API request."""
    extra = {"method": method, "path": path}
    if user_id:
        extra["user_id"] = user_id
    logger.info(f"API Request: {method} {path}", extra=extra)


def log_api_response(logger: logging.Logger, method: str, path: str, status_code: int, duration_ms: float):
    """Log API response."""
    logger.info(
        f"API Response: {method} {path} - {status_code}",
        extra={"method": method, "path": path, "status_code": status_code, "duration_ms": duration_ms}
    )


def log_database_operation(logger: logging.Logger, operation: str, collection: str, doc_id: str = None):
    """Log database operation."""
    msg = f"DB {operation}: {collection}"
    if doc_id:
        msg += f" (id={doc_id})"
    logger.debug(msg, extra={"operation": operation, "collection": collection, "doc_id": doc_id})


def log_file_processing(logger: logging.Logger, filename: str, status: str, details: Dict[str, Any] = None):
    """Log file processing."""
    logger.info(
        f"File {status}: {filename}",
        extra={"filename": filename, "status": status, **(details or {})}
    )
