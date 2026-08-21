"""MCP gateway for GestionaleCloud.

The package is intentionally independent from the FastAPI application process:
it calls the existing HTTP API and never opens a Drive/Sheets connection directly.
"""

from typing import Any


def create_server(*args: Any, **kwargs: Any):
    """Load the MCP SDK only when the gateway process is actually created."""
    from .server import create_server as _create_server

    return _create_server(*args, **kwargs)

__all__ = ["create_server"]

__version__ = "1.0.0"
