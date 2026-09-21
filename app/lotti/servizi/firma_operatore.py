"""FIRMA HACCP — un solo punto per dire CHI ha eseguito un controllo.

Il nome su un registro HACCP non e' un'etichetta: e' l'attestazione che quella
persona ha fatto quel controllo. Gli endpoint delle temperature lo prendevano
come stringa libera dalla query (`operatore=...`), quindi chiunque poteva
scrivere qualunque nome, e nessuno poteva distinguere una firma vera da una
copiata.

Qui la firma nasce dal PIN personale, che e' gia' unico per tutte le app del
gruppo: la fonte e' `pin_hash` sulla scheda HR, lo stesso PIN del portale
dipendenti e del tablet di Lotti (`auth_dipendenti.trova_dipendente_per_pin`).
Chi firma e' quindi la persona che l'anagrafica riconosce, col nome scritto
come in anagrafica, e un cessato non firma piu' niente.

Tre esiti, tutti espliciti nel record salvato:
  - PIN valido        -> `firma_verificata: True`, con `operatore_id` di HR;
  - PIN sbagliato     -> errore, la registrazione NON si salva (una firma
                         falsa e' peggio di una registrazione mancante);
  - nessun PIN        -> `firma_verificata: False`, il nome resta quello
                         dichiarato. Serve ai vecchi tablet e agli inserimenti
                         a mano dell'amministratore, ma si vede che non e'
                         firmata — in stampa lo si puo' dire.

Il PIN non viene mai scritto, ne' registrato, ne' passato altrove: si usa per
riconoscere la persona e si butta.
"""
from typing import Any, Dict, Optional

from fastapi import HTTPException


async def firma_da_pin(
    pin: Optional[str], operatore_dichiarato: str = ""
) -> Dict[str, Any]:
    """Campi di firma da mettere nel record di una rilevazione.

    `pin` vuoto o assente: nessuna verifica, si conserva il nome dichiarato.
    `pin` presente ma non riconosciuto: 401, cosi' la rilevazione non entra
    nel registro con una firma che non regge.
    """
    # Chiamata diretta da codice (test, altri moduli): FastAPI risolve i
    # default `Query(...)` solo quando la richiesta passa dal router, quindi
    # qui puo' arrivare l'oggetto invece della stringa. Vale come «nessun
    # PIN»: la rilevazione resta non firmata, non si tenta una verifica su un
    # valore che non e' un PIN.
    if not isinstance(pin, str):
        pin = ""
    if not isinstance(operatore_dichiarato, str):
        operatore_dichiarato = ""
    pin = pin.strip()
    if not pin:
        return {
            "operatore": operatore_dichiarato,
            "operatore_id": "",
            "firma_verificata": False,
        }

    from app.lotti.routers.tablet_operatori import trova_operatori_per_pin

    trovati = await trova_operatori_per_pin(pin)
    if not trovati:
        raise HTTPException(
            status_code=401,
            detail="PIN non riconosciuto: la rilevazione non e' stata registrata. "
                   "Usa il tuo PIN personale (lo stesso del portale dipendenti).",
        )
    if len(trovati) > 1:
        # Mai due persone in forza con lo stesso PIN (regola HR): se capita,
        # non si sceglie a caso chi ha firmato.
        raise HTTPException(
            status_code=409,
            detail="Questo PIN risulta a piu' persone: chiedi all'amministratore "
                   "di assegnarne uno diverso prima di firmare.",
        )
    operatore = trovati[0]
    return {
        "operatore": operatore.get("nome", "") or operatore_dichiarato,
        "operatore_id": operatore["dipendente_id"],
        "firma_verificata": True,
    }
