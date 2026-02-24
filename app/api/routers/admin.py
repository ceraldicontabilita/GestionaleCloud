"""
DEPRECATO - Vedere app/routers/admin.py

Questo stub mantiene la compatibilità con eventuali import legacy.
Non aggiungere nuovo codice qui.
"""
# Re-export dal path corretto
try:
    from app.routers.admin import router
except ImportError:
    from routers.admin import router

__all__ = ['router']
