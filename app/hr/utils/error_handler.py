"""
Utilities per gestione errori standardizzata.

Fornisce:
- handle_errors: decorator per endpoint FastAPI async
- handle_errors_sync: decorator per funzioni sincrone
- APIResponse: helper per risposte API consistenti

Gestisce automaticamente:
- HTTPException (rilanciate as-is)
- AppError (custom exceptions con status_code)
- ValueError → 400
- KeyError → 400
- TypeError → 400
- FileNotFoundError → 404
- PermissionError → 403
- ConnectionError → 503
- TimeoutError → 504
- Exception generiche → 500
"""
from functools import wraps
from fastapi import HTTPException
import logging
import traceback
from typing import Callable, Any, Optional, Dict, List

logger = logging.getLogger(__name__)


def handle_errors(func: Callable) -> Callable:
    """
    Decorator per gestione errori standard su endpoint async.
    
    Cattura eccezioni comuni e le converte in HTTPException appropriate.
    Gestisce anche le AppError custom dell'applicazione.
    
    Usage:
        @router.get("/items")
        @handle_errors
        async def get_items():
            ...
    """
    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
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
            # Gestisci AppError custom (se importabile)
            if hasattr(e, 'status_code') and hasattr(e, 'message'):
                logger.warning(f"{func.__name__}: {type(e).__name__} - {e.message}")
                raise HTTPException(
                    status_code=e.status_code,
                    detail=e.message
                )
            logger.error(f"{func.__name__}: {type(e).__name__} - {e}")
            logger.error(traceback.format_exc())
            raise HTTPException(status_code=500, detail="Errore interno del server")
    return wrapper


def handle_errors_sync(func: Callable) -> Callable:
    """
    Decorator per gestione errori su funzioni sincrone.
    
    Versione sincrona di handle_errors per funzioni non-async.
    """
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
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
            if hasattr(e, 'status_code') and hasattr(e, 'message'):
                logger.warning(f"{func.__name__}: {type(e).__name__} - {e.message}")
                raise HTTPException(
                    status_code=e.status_code,
                    detail=e.message
                )
            logger.error(f"{func.__name__}: {type(e).__name__} - {e}")
            raise HTTPException(status_code=500, detail="Errore interno del server")
    return wrapper


class APIResponse:
    """Helper per risposte API standardizzate nel formato del gestionale."""
    
    @staticmethod
    def success(data: Any = None, message: Optional[str] = None, **kwargs: Any) -> Dict[str, Any]:
        """
        Genera una risposta di successo standardizzata.
        
        Args:
            data: Dati da includere nella risposta
            message: Messaggio opzionale
            **kwargs: Campi aggiuntivi
        
        Returns:
            Dict con success=True e dati forniti
        """
        response: Dict[str, Any] = {"success": True}
        if data is not None:
            response["data"] = data
        if message:
            response["message"] = message
        response.update(kwargs)
        return response
    
    @staticmethod
    def error(message: str, code: Optional[str] = None, details: Any = None) -> Dict[str, Any]:
        """
        Genera una risposta di errore standardizzata.
        
        Args:
            message: Messaggio di errore
            code: Codice errore opzionale (es. 'ERR_VALIDATION')
            details: Dettagli aggiuntivi sull'errore
        
        Returns:
            Dict con success=False e dettagli errore
        """
        response: Dict[str, Any] = {"success": False, "error": message}
        if code:
            response["error_code"] = code
        if details:
            response["details"] = details
        return response
    
    @staticmethod
    def paginated(items: List[Any], total: int, page: int = 1, per_page: int = 50) -> Dict[str, Any]:
        """
        Genera una risposta paginata standardizzata.
        
        Args:
            items: Lista di elementi della pagina corrente
            total: Numero totale di elementi
            page: Pagina corrente (default 1)
            per_page: Elementi per pagina (default 50)
        
        Returns:
            Dict con dati paginati e metadati di paginazione
        """
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
