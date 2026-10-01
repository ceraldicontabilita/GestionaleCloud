"""
Middleware per Performance e Caching.
Implementa:
- Caching in-memory per query frequenti
- Pagination helper
- Query optimizer
"""
import hashlib
import json
import time
from typing import Any, Dict, List, Optional, Callable
from functools import wraps
from datetime import datetime, timedelta, timezone
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
                "expires": datetime.now() + timedelta(seconds=ttl_seconds),
                "set_at": time.monotonic(),
                "set_at_iso": datetime.now(timezone.utc).isoformat(),
            }
    
    async def get_anche_scaduta(self, key: str) -> Optional[Dict[str, Any]]:
        """La voce anche oltre la scadenza (per le istantanee): valore e ora."""
        async with self._lock:
            return self._cache.get(key)

    async def ripristina(self, key: str, value: Any, calcolata_at_iso: str, eta_secondi: float) -> None:
        """Rimette in memoria una copia salvata altrove: nasce gia' scaduta, con la sua eta' vera."""
        async with self._lock:
            self._cache[key] = {
                "value": value,
                "expires": datetime.now(),
                "set_at": time.monotonic() - max(0.0, eta_secondi),
                "set_at_iso": calcolata_at_iso,
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
# ISTANTANEE: RIEPILOGHI SERVITI SUBITO
# ============================================
#
# Le pagine di riepilogo (stato delle fonti, aggiornamento dati, conteggi dei
# provvisori, grafici della Dashboard, IVA) ricalcolavano tutto a ogni
# apertura: da 3 a 35 secondi il 26/09/2026. Il dato non cambia a ogni
# secondo: la stessa cache di sopra lo tiene con l'ora del calcolo.
# - piu' giovane di ``ttl``: si restituisce;
# - piu' vecchio ma entro ``max_eta``: si restituisce subito e si ricalcola in
#   sottofondo, una volta sola anche con dieci richieste;
# - assente o troppo vecchio: si calcola e si aspetta.
# Ogni scrittura riuscita dall'interfaccia svuota le istantanee
# (``IstantaneeMiddleware``): dopo un salvataggio la pagina non mostra il
# riepilogo di prima. Solo riepiloghi in sola lettura.

PREFISSO_ISTANTANEE = "istantanea:"
_ricalcoli: Dict[str, asyncio.Task] = {}
# Sale a ogni svuotamento: un ricalcolo partito prima di una scrittura non
# rimette in memoria il riepilogo di prima, e nessuno si accoda a lui.
_generazione = 0
_TIPI_CHIAVE = (str, int, float, bool, type(None))


def _chiave_istantanea(func: Callable, args: tuple, kwargs: dict) -> str:
    parti = [repr(a) for a in args if isinstance(a, _TIPI_CHIAVE)]
    parti += [f"{k}={v!r}" for k, v in sorted(kwargs.items()) if isinstance(v, _TIPI_CHIAVE)]
    # Legata all'archivio in uso: un riepilogo di un database non vale per un altro.
    try:
        from app.database import Database
        archivio = id(Database.get_db())
    except Exception:  # noqa: BLE001 - senza archivio la chiave resta per funzione
        archivio = 0
    return f"{PREFISSO_ISTANTANEE}{archivio}:{func.__module__}.{func.__qualname__}:{','.join(parti)}"


def _marca_istantanea(valore: Any, calcolata_at: str, eta: float, in_aggiornamento: bool) -> Any:
    if isinstance(valore, dict):
        return {**valore, "istantanea": {
            "calcolata_at": calcolata_at,
            "eta_secondi": round(eta, 1),
            "in_aggiornamento": in_aggiornamento,
        }}
    return valore


# ---------------------------------------------------------------------------
# Copia salvata (01/10/2026): le istantanee stanno in memoria, e a ogni rilascio
# (o riavvio) si perdevano: la prima apertura di ogni pagina pesante ricalcolava
# tutto, a freddo, con la CPU gia' occupata (5-40 s, «il gestionale si sta
# aggiornando»). Con ``persistente=True`` l'ultimo riepilogo calcolato si
# conserva in ``sistema_stato`` (stesso archivio degli altri stati, nessuna
# collezione nuova): dopo un riavvio si serve subito, marcato «in aggiornamento»,
# e si ricalcola in sottofondo. Una scrittura la invalida (``svuotate_at``): mai
# una copia salvata PRIMA dell'ultimo salvataggio dell'utente.
# ---------------------------------------------------------------------------
PREFISSO_PERSISTENTE = "istantanea:"
CHIAVE_SVUOTAMENTO = "istantanee_svuotate"
MAX_BYTE_PERSISTENTE = 200_000
ETA_MAX_PERSISTENTE = 7 * 86400
_svuotate_at_iso = ""
_marcatore_in_corso: Optional[asyncio.Task] = None
_salvataggi: set = set()


def _chiave_persistente(func: Callable, args: tuple, kwargs: dict) -> str:
    parti = [repr(a) for a in args if isinstance(a, _TIPI_CHIAVE)]
    parti += [f"{k}={v!r}" for k, v in sorted(kwargs.items()) if isinstance(v, _TIPI_CHIAVE)]
    testo = f"{func.__module__}.{func.__qualname__}:{','.join(parti)}"
    return PREFISSO_PERSISTENTE + hashlib.sha1(testo.encode()).hexdigest()[:24]


def _archivio_stato():
    from app.database import Database
    return Database.get_db()["sistema_stato"]


async def _salva_persistente(chiave: str, valore: Any, calcolata_at: str) -> None:
    try:
        from fastapi.encoders import jsonable_encoder
        dati = jsonable_encoder(valore)
        if len(json.dumps(dati, default=str)) > MAX_BYTE_PERSISTENTE:
            return
        await _archivio_stato().update_one(
            {"chiave": chiave},
            {"$set": {"chiave": chiave, "valore": dati, "calcolata_at": calcolata_at}},
            upsert=True,
        )
    except Exception as exc:  # noqa: BLE001 - la copia salvata e' un di piu', mai un guasto
        logger.warning("[istantanee] copia salvata non scritta (%s: %s)", type(exc).__name__, exc)


async def _leggi_persistente(chiave: str) -> Optional[Dict[str, Any]]:
    """La copia salvata, solo se piu' recente dell'ultima scrittura e non vecchia di giorni."""
    try:
        archivio = _archivio_stato()
        doc = await archivio.find_one({"chiave": chiave}, {"_id": 0})
        if not doc or not isinstance(doc.get("valore"), dict) or not doc.get("calcolata_at"):
            return None
        marcatore = await archivio.find_one({"chiave": CHIAVE_SVUOTAMENTO}, {"_id": 0}) or {}
        ultima_scrittura = max(_svuotate_at_iso, str(marcatore.get("svuotate_at") or ""))
        if ultima_scrittura and doc["calcolata_at"] <= ultima_scrittura:
            return None
        eta = (datetime.now(timezone.utc) - datetime.fromisoformat(doc["calcolata_at"])).total_seconds()
        if eta < 0 or eta > ETA_MAX_PERSISTENTE:
            return None
        return {"valore": doc["valore"], "calcolata_at": doc["calcolata_at"], "eta": eta}
    except Exception as exc:  # noqa: BLE001
        logger.warning("[istantanee] copia salvata non letta (%s: %s)", type(exc).__name__, exc)
        return None


async def _scrivi_marcatore() -> None:
    """Un colpo solo dopo una raffica di scritture: l'ultimo istante vale per tutte."""
    global _marcatore_in_corso
    try:
        await asyncio.sleep(2)
        await _archivio_stato().update_one(
            {"chiave": CHIAVE_SVUOTAMENTO},
            {"$set": {"chiave": CHIAVE_SVUOTAMENTO, "svuotate_at": _svuotate_at_iso}},
            upsert=True,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[istantanee] marcatore di scrittura non salvato (%s: %s)", type(exc).__name__, exc)
    finally:
        _marcatore_in_corso = None


async def svuota_istantanee() -> None:
    """Dopo una scrittura: via le copie e i ricalcoli gia' partiti."""
    global _generazione, _svuotate_at_iso, _marcatore_in_corso
    _generazione += 1
    _ricalcoli.clear()
    await cache.clear_pattern(PREFISSO_ISTANTANEE)
    _svuotate_at_iso = datetime.now(timezone.utc).isoformat()
    if _marcatore_in_corso is None:
        try:
            _marcatore_in_corso = asyncio.get_running_loop().create_task(_scrivi_marcatore())
        except RuntimeError:
            _marcatore_in_corso = None


def _ricalcola(chiave: str, func: Callable, args: tuple, kwargs: dict, max_eta: float,
               persistente: bool = False) -> asyncio.Task:
    compito = _ricalcoli.get(chiave)
    if compito is not None and not compito.done():
        return compito
    generazione = _generazione

    async def calcola():
        try:
            valore = await func(*args, **kwargs)
            if generazione == _generazione:
                await cache.set(chiave, valore, int(max_eta))
                if persistente and isinstance(valore, dict):
                    salvataggio = asyncio.get_running_loop().create_task(_salva_persistente(
                        _chiave_persistente(func, args, kwargs), valore, datetime.now(timezone.utc).isoformat()))
                    _salvataggi.add(salvataggio)
                    salvataggio.add_done_callback(_salvataggi.discard)
            return valore
        finally:
            if _ricalcoli.get(chiave) is compito:
                _ricalcoli.pop(chiave, None)

    compito = asyncio.get_running_loop().create_task(calcola(), name=chiave[:80])
    _ricalcoli[chiave] = compito
    return compito


def _errore_ricalcolo(compito: asyncio.Task) -> None:
    if not compito.cancelled() and compito.exception() is not None:
        errore = compito.exception()
        logger.warning("[istantanee] ricalcolo non riuscito (%s: %s): resta la copia precedente",
                       type(errore).__name__, errore)


def istantanea(ttl: float = 120, max_eta: float = 1800, persistente: bool = False):
    """Decoratore per un endpoint di riepilogo in sola lettura."""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            chiave = _chiave_istantanea(func, args, kwargs)
            voce = await cache.get_anche_scaduta(chiave)
            if voce is not None:
                eta = time.monotonic() - voce["set_at"]
                if eta < ttl:
                    return _marca_istantanea(voce["value"], voce["set_at_iso"], eta, False)
                if eta < max_eta:
                    _ricalcola(chiave, func, args, kwargs, max_eta, persistente).add_done_callback(_errore_ricalcolo)
                    return _marca_istantanea(voce["value"], voce["set_at_iso"], eta, True)
            if persistente:
                # Dopo un riavvio la memoria e' vuota: si serve l'ultima copia salvata e si ricalcola.
                copia = await _leggi_persistente(_chiave_persistente(func, args, kwargs))
                if copia is not None:
                    await cache.ripristina(chiave, copia["valore"], copia["calcolata_at"], copia["eta"])
                    _ricalcola(chiave, func, args, kwargs, max_eta, persistente).add_done_callback(_errore_ricalcolo)
                    marcata = _marca_istantanea(copia["valore"], copia["calcolata_at"], copia["eta"], True)
                    marcata["istantanea"]["da_copia_salvata"] = True
                    return marcata
            valore = await asyncio.shield(_ricalcola(chiave, func, args, kwargs, max_eta, persistente))
            voce = await cache.get_anche_scaduta(chiave)
            calcolata_at = voce["set_at_iso"] if voce else datetime.now(timezone.utc).isoformat()
            return _marca_istantanea(valore, calcolata_at, 0.0, False)
        return wrapper
    return decorator


class IstantaneeMiddleware:
    """Una scrittura riuscita (POST/PUT/PATCH/DELETE) svuota le istantanee, e
    cosi' una lettura con l'intestazione ``X-Rileggi`` (il pulsante «Rileggi»)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        if scope.get("method") in ("GET", "HEAD", "OPTIONS"):
            # «Rileggi» chiede il dato fresco: niente copia per questa lettura.
            if any(nome.lower() == b"x-rileggi" for nome, _ in scope.get("headers") or []):
                await svuota_istantanee()
            await self.app(scope, receive, send)
            return

        async def invia(messaggio):
            # Si svuota prima che la risposta parta: la lettura che il client
            # fa subito dopo il salvataggio non deve trovare la copia di prima.
            if messaggio.get("type") == "http.response.start" and messaggio.get("status", 500) < 400:
                await svuota_istantanee()
            await send(messaggio)

        await self.app(scope, receive, invia)


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
