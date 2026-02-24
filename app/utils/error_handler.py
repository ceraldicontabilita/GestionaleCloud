"""
Utilities per gestione errori standardizzata.
"""
from functools import wraps
from fastapi import HTTPException
import logging
import traceback
from typing import Callable, Any

logger = logging.getLogger(__name__)


def handle_errors(func: Callable) -> Callable:
    """
    Decorator per gestione errori standard su endpoint async.
    
    Cattura eccezioni comuni e le converte in HTTPException appropriate.
    
    Usage:
        @router.get("/items")
        @handle_errors
        async def get_items():
            ...
    """
    @wraps(func)
    async def wrapper(*args, **kwargs) -> Any:
        try:
            return await func(*args, **kwargs)
        except HTTPException:
            raise  # Rilancia HTTPException as-is
        except ValueError as e:
            logger.warning(f"{func.__name__}: ValueError - {e}")
            raise HTTPException(status_code=400, detail=str(e))
        except KeyError as e:
            logger.warning(f"{func.__name__}: KeyError - {e}")
            raise HTTPException(status_code=400, detail=f"Campo mancante: {e}")
        except TypeError as e:
            logger.warning(f"{func.__name__}: TypeError - {e}")
            raise HTTPException(status_code=400, detail=f"Tipo non valido: {e}")
        except FileNotFoundError as e:
            logger.warning(f"{func.__name__}: FileNotFoundError - {e}")
            raise HTTPException(status_code=404, detail=f"File non trovato: {e}")
        except PermissionError as e:
            logger.warning(f"{func.__name__}: PermissionError - {e}")
            raise HTTPException(status_code=403, detail=f"Permesso negato: {e}")
        except ConnectionError as e:
            logger.error(f"{func.__name__}: ConnectionError - {e}")
            raise HTTPException(status_code=503, detail="Servizio temporaneamente non disponibile")
        except TimeoutError as e:
            logger.error(f"{func.__name__}: TimeoutError - {e}")
            raise HTTPException(status_code=504, detail="Timeout nella richiesta")
        except Exception as e:
            logger.error(f"{func.__name__}: {type(e).__name__} - {e}")
            logger.error(traceback.format_exc())
            raise HTTPException(status_code=500, detail="Errore interno del server")
    return wrapper


def handle_errors_sync(func: Callable) -> Callable:
    """
    Decorator per gestione errori su funzioni sincrone.
    """
    @wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        try:
            return func(*args, **kwargs)
        except HTTPException:
            raise
        except ValueError as e:
            logger.warning(f"{func.__name__}: ValueError - {e}")
            raise HTTPException(status_code=400, detail=str(e))
        except KeyError as e:
            logger.warning(f"{func.__name__}: KeyError - {e}")
            raise HTTPException(status_code=400, detail=f"Campo mancante: {e}")
        except Exception as e:
            logger.error(f"{func.__name__}: {type(e).__name__} - {e}")
            raise HTTPException(status_code=500, detail="Errore interno del server")
    return wrapper


class APIResponse:
    """Helper per risposte API standardizzate."""
    
    @staticmethod
    def success(data: Any = None, message: str = None, **kwargs) -> dict:
        """Risposta di successo."""
        response = {"success": True}
        if data is not None:
            response["data"] = data
        if message:
            response["message"] = message
        response.update(kwargs)
        return response
    
    @staticmethod
    def error(message: str, code: str = None, details: Any = None) -> dict:
        """Risposta di errore."""
        response = {"success": False, "error": message}
        if code:
            response["error_code"] = code
        if details:
            response["details"] = details
        return response
    
    @staticmethod
    def paginated(items: list, total: int, page: int = 1, per_page: int = 50) -> dict:
        """Risposta paginata."""
        return {
            "success": True,
            "data": items,
            "pagination": {
                "total": total,
                "page": page,
                "per_page": per_page,
                "total_pages": (total + per_page - 1) // per_page
            }
        }
