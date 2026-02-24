"""
Server wrapper per compatibilità con supervisor.
Importa l'applicazione FastAPI da main.py.
"""
import sys

# Add /app to Python path so 'backend' package can be found
sys.path.insert(0, '/app')

# Import the FastAPI app from the modular main.py

# The app is now available for uvicorn to run
# Command: uvicorn app.server:app --host 0.0.0.0 --port 8001
