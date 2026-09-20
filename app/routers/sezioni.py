"""Le quattro sezioni del gruppo Ceraldi, in un elenco solo.

Girano tutte nello stesso servizio — `/` il gestionale, `/lotti` il magazzino
HACCP, `/hr` il personale, `/menu` il menu pubblico — ma fino a oggi **nessuna
aveva un collegamento verso le altre**: dal gestionale non si arrivava a Lotti,
da Lotti non si tornava al gestionale, e per passare da una all'altra bisognava
scrivere l'indirizzo a mano. Sembrava un muro, ed era un'assenza.

Qui sta l'elenco, una volta sola. Ogni sezione lo legge e lo disegna **con i
propri stili**: il gestionale col suo layout, le altre tre in salvia su crema.
Il dato e' condiviso, l'aspetto no — che e' esattamente la regola: le app
portate pari pari mantengono il loro aspetto.

Il percorso con la barra finale non e' un dettaglio: `Mount` di Starlette
esige `/lotti/`, e il prefisso nudo cade nella SPA del gestionale.
"""
from fastapi import APIRouter

router = APIRouter()

# `icona` e' il nome di un'icona Lucide, che tutte e quattro le interfacce
# hanno gia': non si passa un'emoji, che su Android rende con i colori di
# sistema e non si puo' controllare.
SEZIONI = [
    {
        "id": "gestionale",
        "nome": "Gestionale",
        "descrizione": "Contabilita', fatture, banca e bilancio",
        "percorso": "/",
        "icona": "Landmark",
    },
    {
        "id": "lotti",
        "nome": "Magazzino e HACCP",
        "descrizione": "Lotti, tracciabilita', temperature e sanificazione",
        "percorso": "/lotti/",
        "icona": "Boxes",
    },
    {
        "id": "hr",
        "nome": "Personale",
        "descrizione": "Dipendenti, cedolini, turni e presenze",
        "percorso": "/hr/",
        "icona": "Users",
    },
    {
        "id": "menu",
        "nome": "Menu",
        "descrizione": "Menu pubblico, prodotti e allergeni",
        "percorso": "/menu/",
        "icona": "UtensilsCrossed",
    },
]


@router.get("")
@router.get("/")
async def elenco_sezioni():
    """Le sezioni raggiungibili, per costruire il passaggio da una all'altra."""
    return {"sezioni": SEZIONI}
