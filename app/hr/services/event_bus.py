"""Bus eventi HR — re-export del motore unico di `app/services/event_bus.py`.

Fino al 19/09/2026 questo file era un bus **separato**, con un proprio
registro `_handlers` e una propria `register_all_handlers()`. Quella funzione
non veniva chiamata da nessuna parte — né in `app/hr/main.py`, né altrove, né
all'import — quindi il registro restava vuoto e **ogni `propagate_event`
scritto nel codice HR non raggiungeva alcun handler**. Misurato a runtime:
bus ERP 32 handler registrati, bus HR 0.

Conseguenza concreta, e motivo per cui non era un difetto solo estetico: le
due strade di cessazione in `app/hr/routers/employees/dipendenti.py` (la
spunta «non in carico» nel PUT e il DELETE) non revocano il PIN da sole, si
affidano all'handler `on_dipendente_cessato` — che stava su questo bus morto.
CLAUDE.md impone che la cessazione revochi il PIN. In produzione il buco era
latente (29 cessati, 0 con PIN attivo: le cessazioni erano passate da
`dipendenti_cloud`, che revoca a mano), ma bastava usare l'altra strada.

Ora c'è **un solo bus** (CLAUDE.md, «un solo sistema per funzione»): gli
import esistenti continuano a funzionare e arrivano al registro vivo, quello
popolato da `register_all_handlers()` in `app/main.py`.

Gli `EventTypes` delle due copie erano già allineati al carattere — nessun
tipo presente solo qui, nessuna stringa divergente — quindi il re-export non
cambia il nome di nessun evento.
"""
from app.services.event_bus import (  # noqa: F401
    EventTypes,
    get_registered_events,
    propagate_event,
    register_all_handlers,
    register_handler,
)

__all__ = [
    "EventTypes",
    "get_registered_events",
    "propagate_event",
    "register_all_handlers",
    "register_handler",
]
