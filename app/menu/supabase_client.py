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


# ================== Insert con id assegnato dal database ==================
# CLAUDE.md §5: gli id nuovi nascono dal proprietario canonico, mai max(id)+1.
# Le tabelle menu_categories / menu_subcategories / menu_products hanno l'identity
# BY DEFAULT dalla migrazione 20261007051337_menu_id_dal_database (applicata in
# produzione). Questo e' l'unico percorso con cui ponte Lotti e admin del Menu
# creano righe in quelle tabelle: nessun ripiego su id calcolati dall'app.

def inserisci_con_id_del_database(client, tabella: str, riga: dict) -> int:
    """Inserisce ``riga`` senza ``id`` e restituisce l'id generato dal database.

    ``client`` e' il client PostgREST del modulo chiamante (``supabase``), passato
    esplicitamente cosi' i test possono sostituirlo nel modulo che lo usa.
    PostgREST restituisce la riga inserita (``return=representation``), quindi
    l'id torna nella risposta. Un rifiuto del database (vincolo violato, colonna
    assente, connessione) risale al chiamante cosi' com'e': nessuna riga e' stata
    scritta e non si ritenta. Se invece l'insert riesce ma la risposta non porta
    l'id, la riga esiste gia': si solleva un ``RuntimeError`` e NON si deve
    reinserire."""
    senza_id = {k: v for k, v in riga.items() if k != "id"}
    res = client.table(tabella).insert(senza_id).execute()
    righe = getattr(res, "data", None) or []
    if righe and righe[0].get("id") is not None:
        return int(righe[0]["id"])
    raise RuntimeError(f"{tabella}: l'insert e' riuscito ma non ha restituito l'id generato")
