"""Gestione cedolini HR — re-export del modulo unico.

La logica vive in `app/services/cedolini_manager.py`. Fino al 19/09/2026 qui
c'era una copia piu' vecchia, e la differenza piu' grave era un **motore di
abbinamento parallelo**.

`riconcilia_stipendio_automatico`, in questa copia, cercava da sola in
`estratto_conto_movimenti` il primo movimento con importo entro ±2 € e una
parola del nome (o l'IBAN) nella descrizione, e lo marcava riconciliato. Un
omonimo, due buste uguali nello stesso mese o un bonifico di importo simile
bastavano ad attaccare il movimento sbagliato. La copia ERP non abbina da se':
delega a `stipendi_bonifici.associa_bonifici_stipendi`, il motore canonico che
usa identita' completa, acconti e residuo — l'unico autorizzato (CLAUDE.md,
«un solo sistema per funzione»).

Mancavano inoltre: la chiave documentale del cedolino (`chiave_cedolino` +
hash del PDF), la guardia `PAYROLL_MIN_YEAR = 2018` sullo storico autorizzato,
il parser deterministico multi-template e i controlli di completezza del
riepilogo.

Nota su cosa cambia davvero oggi: l'unico chiamante vivo di questa copia era
`POST /api/salari-v2/riconcilia-banca`, che gira sul database HR. Li' le
tabelle `app_estratto_conto_movimenti` e `app_prima_nota_salari` non esistono
(i dati bancari stanno nello store dell'ERP), quindi quell'endpoint tornava
gia' zero riconciliazioni. Il motore parallelo era un rischio latente, non un
danno in atto: il re-export lo toglie prima che diventi raggiungibile.
"""
from app.services.cedolini_manager import (  # noqa: F401
    PAYROLL_MIN_YEAR,
    get_anagrafica_dipendenti,
    get_riepilogo_dipendente,
    processa_cedolino_completo,
    processa_tutti_cedolini_pdf,
    riconcilia_stipendio_automatico,
)

__all__ = [
    "PAYROLL_MIN_YEAR",
    "get_anagrafica_dipendenti",
    "get_riepilogo_dipendente",
    "processa_cedolino_completo",
    "processa_tutti_cedolini_pdf",
    "riconcilia_stipendio_automatico",
]
