"""Enumerazione degli endpoint realmente montati, su ogni versione di FastAPI.

Dalla 0.121 ``include_router`` non appiattisce piu' le rotte dentro
``app.routes``: le tiene in un ``_IncludedRouter``, e le espone tramite
``effective_route_contexts()``. Chi cerca solo le ``APIRoute`` di primo
livello non trova piu' niente.

Il punto non e' l'incompatibilita' in se', ma come si manifesta: un test che
scorre zero rotte non fallisce, **passa**. Le guardie sui permessi e i
controlli di contratto col frontend diventavano verdi proprio quando avevano
smesso di verificare qualcosa. Per questo qui c'e' un'unica implementazione,
usata da tutti, e con l'assenza di rotte trattata come errore.

I contesti restituiti espongono ``path``, ``methods``, ``dependant`` ed
``endpoint``, come le APIRoute: chi li usa non deve distinguere i due casi.
"""
from fastapi.routing import APIRoute


def route_montate(app):
    """Tutti gli endpoint montati sull'app, annidati compresi."""
    for rotta in getattr(app, "routes", []):
        if isinstance(rotta, APIRoute):
            yield rotta
            continue
        contesti = getattr(rotta, "effective_route_contexts", None)
        if not callable(contesti):
            continue
        for contesto in contesti():
            # Il percorso qui e' gia' completo di prefisso; `original_router`
            # invece li espone senza, e produrrebbe rotte inesistenti.
            if getattr(contesto, "path", None) and getattr(contesto, "methods", None):
                yield contesto


def elenco_route(app):
    """Come ``route_montate``, ma in lista e con la garanzia che non sia vuota."""
    rotte = list(route_montate(app))
    assert rotte, (
        "nessun endpoint montato: l'enumerazione delle rotte non e' compatibile "
        "con questa versione di FastAPI, e senza questo controllo il test "
        "passerebbe senza verificare niente"
    )
    return rotte
