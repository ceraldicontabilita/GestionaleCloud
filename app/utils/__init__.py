"""
Utilities package.
Provides helper functions and dependencies.
"""
from .logger import setup_logging, get_logger, LoggerAdapter, log_function_call
from .dependencies import (
    get_current_user,
    get_current_admin_user,
    get_optional_user,
    require_feature,
    get_user_db,
    pagination_params,
    date_range_params
)

__all__ = [
    "setup_logging",
    "get_logger",
    "LoggerAdapter",
    "log_function_call",
    "get_current_user",
    "get_current_admin_user",
    "get_optional_user",
    "require_feature",
    "get_user_db",
    "pagination_params",
    "date_range_params"
]
