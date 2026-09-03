"""Registrazione dei router del modulo HR sotto ``/api/hr``.

Stessi prefissi dell'app AppDipendenti originale, spostati di un livello
(``/api/dipendenti-cloud`` -> ``/api/hr/dipendenti-cloud``) per non
sovrapporsi ai router contabili del gestionale (``/api/dipendenti``,
``/api/cedolini``, ``/api/tfr``, ``/api/contabilita`` esistono gia' con un
altro significato). Il frontend HR usa ``/api/hr`` come base.
"""
import logging

from fastapi import Depends, FastAPI

logger = logging.getLogger(__name__)

HR_PREFIX = "/api/hr"

# Percorsi HR raggiungibili senza sessione (login del portale). Letti dal
# middleware globale di autenticazione.
HR_PUBLIC_PATHS = frozenset({
    f"{HR_PREFIX}/auth/dipendenti-attivi",
    f"{HR_PREFIX}/auth/pin-login",
    f"{HR_PREFIX}/auth/pin-login/health",
    f"{HR_PREFIX}/health",
})


def register_hr_routers(app: FastAPI) -> None:
    from app.hr.utils.dependencies import require_admin, require_staff

    p = HR_PREFIX
    STAFF = [Depends(require_staff)]
    ADMIN = [Depends(require_admin)]

    from app.hr.routers import pin_login
    app.include_router(pin_login.router, prefix=f"{p}/auth", tags=["HR · Login portale"])

    from app.hr.routers.employees import (
        dipendenti, buste_paga, employee_contracts, giustificativi, shifts,
        fascicolo_dipendente, accessi,
    )
    app.include_router(dipendenti.router, prefix=f"{p}/dipendenti", tags=["HR · Dipendenti"], dependencies=STAFF)
    app.include_router(accessi.router, prefix=f"{p}/accessi", tags=["HR · Accessi"])  # admin per-endpoint
    app.include_router(buste_paga.router, prefix=p, tags=["HR · Buste Paga"], dependencies=ADMIN)
    app.include_router(employee_contracts.router, prefix=f"{p}/contracts", tags=["HR · Contratti"], dependencies=ADMIN)
    app.include_router(giustificativi.router, prefix=f"{p}/giustificativi", tags=["HR · Giustificativi"], dependencies=STAFF)
    app.include_router(shifts.router, prefix=f"{p}/shifts", tags=["HR · Turni"], dependencies=STAFF)
    app.include_router(fascicolo_dipendente.router, prefix=p, tags=["HR · Fascicolo"], dependencies=STAFF)

    from app.hr.routers import (
        cedolini, tfr, attendance, dimissioni, richieste, portale_buste, turni,
        notifiche, dipendenti_cloud, portale_documenti, timbrature,
    )
    app.include_router(timbrature.router, prefix=f"{p}/timbrature", tags=["HR · Timbrature"])
    app.include_router(richieste.router, prefix=f"{p}/richieste", tags=["HR · Richieste"])
    app.include_router(portale_buste.router, prefix=f"{p}/portale/buste", tags=["HR · Portale Buste"])
    app.include_router(portale_documenti.router, prefix=f"{p}/portale/documenti", tags=["HR · Portale Documenti"])
    app.include_router(turni.router, prefix=f"{p}/turni", tags=["HR · Turni"])
    app.include_router(notifiche.router, prefix=f"{p}/notifiche", tags=["HR · Notifiche"])
    app.include_router(dipendenti_cloud.router, prefix=p, tags=["HR · Dipendenti Cloud"], dependencies=STAFF)
    app.include_router(cedolini.router, prefix=f"{p}/cedolini", tags=["HR · Cedolini"], dependencies=ADMIN)
    app.include_router(tfr.router, prefix=f"{p}/tfr", tags=["HR · TFR"], dependencies=ADMIN)
    app.include_router(attendance.router, prefix=f"{p}/attendance", tags=["HR · Presenze"], dependencies=STAFF)
    app.include_router(dimissioni.router, prefix=f"{p}/dimissioni", tags=["HR · Dimissioni"], dependencies=ADMIN)

    from app.hr.routers import libro_unico_parser, f24_parser, salari_unificati_v2, diagnostica, admin_hr
    app.include_router(libro_unico_parser.router, prefix=f"{p}/paghe", tags=["HR · Libro Unico"], dependencies=ADMIN)
    app.include_router(f24_parser.router, prefix=f"{p}/paghe", tags=["HR · F24 Parser"], dependencies=ADMIN)
    app.include_router(salari_unificati_v2.router, prefix=f"{p}/salari-v2", tags=["HR · Salari V2"], dependencies=ADMIN)
    app.include_router(diagnostica.router, prefix=f"{p}/diagnostica", tags=["HR · Diagnostica"], dependencies=ADMIN)
    app.include_router(admin_hr.router, prefix=f"{p}/admin", tags=["HR · Amministrazione"], dependencies=ADMIN)

    @app.get(f"{p}/health", tags=["HR · Diagnostica"])
    async def hr_health():
        from app.hr.database import Database
        try:
            store = Database.blob_store()
            return {"status": "ok", "modulo": "hr", "blob_persistenti": store.persistent}
        except RuntimeError as exc:
            return {"status": "degraded", "modulo": "hr", "detail": str(exc)}

    logger.info("Router HR registrati sotto %s", p)
