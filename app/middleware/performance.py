"""
Middleware per Performance e Caching.
Implementa:
- Caching in-memory per query frequenti
- Pagination helper
- Query optimizer
"""
import time
from typing import Any, Dict, List, Optional, Callable
from functools import wraps
from datetime import datetime, timedelta
import asyncio
import logging

logger = logging.getLogger(__name__)

# ============================================
# SIMPLE IN-MEMORY CACHE
# ============================================

class SimpleCache:
    """Cache in-memory semplice con TTL."""
    
    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
    
    async def get(self, key: str) -> Optional[Any]:
        """Recupera valore dalla cache."""
        async with self._lock:
            if key in self._cache:
                entry = self._cache[key]
                if datetime.now() < entry["expires"]:
                    return entry["value"]
                else:
                    del self._cache[key]
            return None
    
    async def set(self, key: str, value: Any, ttl_seconds: int = 60):
        """Salva valore in cache."""
        async with self._lock:
            self._cache[key] = {
                "value": value,
                "expires": datetime.now() + timedelta(seconds=ttl_seconds)
            }
    
    async def delete(self, key: str):
        """Elimina chiave dalla cache."""
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
    
    async def clear_pattern(self, pattern: str):
        """Elimina tutte le chiavi che iniziano con pattern."""
        async with self._lock:
            keys_to_delete = [k for k in self._cache.keys() if k.startswith(pattern)]
            for k in keys_to_delete:
                del self._cache[k]
    
    async def clear_all(self):
        """Svuota tutta la cache."""
        async with self._lock:
            self._cache.clear()
    
    def stats(self) -> Dict[str, Any]:
        """Statistiche cache."""
        return {
            "entries": len(self._cache),
            "keys": list(self._cache.keys())[:10]  # Prime 10 chiavi
        }


# Istanza globale della cache
cache = SimpleCache()


# ============================================
# PAGINATION HELPER
# ============================================

class PaginationParams:
    """Parametri di paginazione standard."""
    
    def __init__(
        self, 
        page: int = 1, 
        page_size: int = 50,
        max_page_size: int = 500
    ):
        self.page = max(1, page)
        self.page_size = min(max(1, page_size), max_page_size)
        self.skip = (self.page - 1) * self.page_size
    
    def to_dict(self) -> Dict[str, int]:
        return {
            "page": self.page,
            "page_size": self.page_size,
            "skip": self.skip
        }


def paginated_response(
    data: List[Any],
    total: int,
    pagination: PaginationParams
) -> Dict[str, Any]:
    """Crea risposta paginata standard."""
    total_pages = (total + pagination.page_size - 1) // pagination.page_size
    
    return {
        "data": data,
        "pagination": {
            "page": pagination.page,
            "page_size": pagination.page_size,
            "total": total,
            "total_pages": total_pages,
            "has_next": pagination.page < total_pages,
            "has_prev": pagination.page > 1
        }
    }


# ============================================
# CACHE DECORATOR
# ============================================

def cached(ttl_seconds: int = 60, key_prefix: str = ""):
    """
    Decorator per cachare risultati di funzioni async.
    
    Usage:
        @cached(ttl_seconds=300, key_prefix="suppliers")
        async def get_suppliers():
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Genera chiave cache
            cache_key = f"{key_prefix}:{func.__name__}:{str(args)}:{str(sorted(kwargs.items()))}"
            
            # Prova a recuperare dalla cache
            cached_value = await cache.get(cache_key)
            if cached_value is not None:
                logger.debug(f"Cache HIT: {cache_key}")
                return cached_value
            
            # Esegui funzione
            logger.debug(f"Cache MISS: {cache_key}")
            result = await func(*args, **kwargs)
            
            # Salva in cache
            await cache.set(cache_key, result, ttl_seconds)
            
            return result
        
        return wrapper
    return decorator


# ============================================
# QUERY PERFORMANCE LOGGING
# ============================================

class QueryTimer:
    """Context manager per misurare tempo query."""
    
    def __init__(self, operation_name: str, threshold_ms: int = 500):
        self.operation_name = operation_name
        self.threshold_ms = threshold_ms
        self.start_time = None
    
    def __enter__(self):
        self.start_time = time.perf_counter()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed_ms = (time.perf_counter() - self.start_time) * 1000
        if elapsed_ms > self.threshold_ms:
            logger.warning(f"⚠️ Slow query: {self.operation_name} took {elapsed_ms:.0f}ms")
        return False


# ============================================
# CONSTANTS
# ============================================

# Default page sizes per tipo di risorsa
DEFAULT_PAGE_SIZES = {
    "invoices": 100,
    "suppliers": 100,
    "employees": 50,
    "corrispettivi": 100,
    "cedolini": 100,
    "prima_nota": 100,
    "documents": 50,
}

# TTL cache in secondi per tipo di risorsa
CACHE_TTL = {
    "suppliers_list": 300,      # 5 minuti
    "employees_list": 300,      # 5 minuti
    "dashboard_stats": 60,      # 1 minuto
    "scadenze_count": 120,      # 2 minuti
}
