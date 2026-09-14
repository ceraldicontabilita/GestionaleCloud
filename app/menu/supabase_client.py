"""
Client Supabase condiviso da tutti i moduli del backend.
Sostituisce la precedente connessione MongoDB (Motor/PyMongo).

Dentro GestionaleCloud le variabili sono namespaced (``MENU_SUPABASE_URL`` /
``MENU_SUPABASE_KEY``) perche' l'app ospite usa gia' ``SUPABASE_URL`` per il
proprio progetto. Il client viene creato al primo uso, non all'import: l'app
ospite deve poter importare il modulo (es. nei test) anche senza le env del
Menu; in quel caso la prima chiamata solleva un RuntimeError esplicito.
"""
import os
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client, Client

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')


def _leggi_env(nome: str) -> str:
    return os.environ.get(nome, '').strip('"').strip("'")


_client: Client | None = None


def get_supabase() -> Client:
    """Restituisce il client (creandolo alla prima chiamata)."""
    global _client
    if _client is None:
        url = _leggi_env('MENU_SUPABASE_URL')
        key = _leggi_env('MENU_SUPABASE_KEY')
        if not url or not key:
            raise RuntimeError(
                "Menu: variabili d'ambiente MENU_SUPABASE_URL / MENU_SUPABASE_KEY non impostate"
            )
        _client = create_client(url, key)
    return _client


class _LazySupabase:
    """Proxy che inoltra ogni attributo (``.table``, ``.storage``, ...) al client
    reale, creato solo al primo accesso. Mantiene invariato l'uso
    ``supabase.table(...)`` in tutti i router originali."""

    def __getattr__(self, name):
        return getattr(get_supabase(), name)


supabase = _LazySupabase()
