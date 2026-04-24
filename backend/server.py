"""
Azienda in Cloud ERP - Backend Server Entry Point
This imports the FastAPI app from /app/app/main.py
"""
import sys
import os
sys.path.insert(0, '/app')

try:
    from dotenv import load_dotenv
    load_dotenv('/app/backend/.env', override=False)
except ImportError:
    pass

from app.main import app

# Endpoint di debug versione (temporaneo)
from fastapi import Request
from fastapi.responses import JSONResponse
import subprocess

@app.get("/api/version-debug", include_in_schema=False)
async def version_debug():
    try:
        git_log = subprocess.check_output(
            ['git', '-C', '/app', 'log', '--oneline', '-3'],
            stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception as e:
        git_log = str(e)
    
    try:
        with open('/app/app/routers/mutui.py') as f:
            mutui_content = f.read()
        has_noslash = 'get_mutui_noslash' in mutui_content
        has_naive = 'oggi_dt = datetime.now()  # naive' in open('/app/app/routers/fiscalita_italiana.py').read()
    except Exception as e:
        has_noslash = str(e)
        has_naive = str(e)
    
    return {
        "git_log": git_log,
        "mutui_has_noslash_fix": has_noslash,
        "fiscalita_has_naive_fix": has_naive
    }


# Export app for uvicorn
__all__ = ['app']
