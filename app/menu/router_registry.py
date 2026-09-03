"""Registrazione dei router del modulo Menu sotto ``/api/menu``.

Tre perimetri, letti anche dal middleware globale di autenticazione:

- ``/api/menu/pubblico``: il menu digitale dei clienti (QR al tavolo). Nessuna
  sessione: lettura del menu, invio dell'ordine, stato del proprio ordine,
  immagini.
- ``/api/menu/staff``: schermate di banco (ordini, cassa, cucina, magazzino
  bar). Qualunque sessione valida, comprese quelle del portale dipendenti.
- ``/api/menu/admin``: gestione del catalogo, sale, immagini, QR, backup e
  migrazione. Solo ``admin``/``operatore`` (ripristino e migrazione: solo
  ``admin``).
"""
from fastapi import Depends, FastAPI

MENU_PREFIX = "/api/menu"
MENU_PUBLIC_PREFIX = MENU_PREFIX + "/pubblico"
MENU_STAFF_PREFIX = MENU_PREFIX + "/staff"
MENU_ADMIN_PREFIX = MENU_PREFIX + "/admin"


def register_menu_routers(app: FastAPI) -> None:
    from app.menu.auth import require_menu_gestione, require_menu_staff
    from app.menu.routers import gestione, pubblico, staff

    app.include_router(pubblico.router, prefix=MENU_PUBLIC_PREFIX, tags=["Menu · Pubblico"])
    app.include_router(staff.router, prefix=MENU_STAFF_PREFIX, tags=["Menu · Staff"], dependencies=[Depends(require_menu_staff)])
    app.include_router(gestione.router, prefix=MENU_ADMIN_PREFIX, tags=["Menu · Gestione"], dependencies=[Depends(require_menu_gestione)])
