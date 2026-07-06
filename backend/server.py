"""
Azienda in Cloud ERP - Backend Server Entry Point
This imports the FastAPI app from /app/app/main.py
"""
import sys

sys.path.insert(0, '/app')

try:
    from dotenv import load_dotenv
    load_dotenv('/app/backend/.env', override=False)
except ImportError:
    pass

from app.main import app  # noqa: F401  (export per uvicorn)

# Export app for uvicorn
__all__ = ['app']
