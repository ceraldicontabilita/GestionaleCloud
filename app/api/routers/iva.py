"""
DEPRECATO - Questo file è stato spostato in app/routers/iva.py

Questo stub mantiene la compatibilità con eventuali import legacy.
Non aggiungere nuovo codice qui.
"""
# Re-export dal path corretto
try:
    from app.routers.iva import iva_router as router
except ImportError:
    from routers.iva import iva_router as router

__all__ = ['router', 'iva_router']
