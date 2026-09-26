"""Un solo motore di abbinamento bonifico→stipendio, anche dal lato HR.

Fino al 19/09/2026 `app/hr/services/cedolini_manager.py` aveva la sua
`riconcilia_stipendio_automatico`: cercava da sola in
`estratto_conto_movimenti` il primo movimento con importo entro ±2 € e una
parola del nome (o l'IBAN) nella descrizione, e lo marcava riconciliato. Un
omonimo, due buste uguali nello stesso mese o un bonifico di importo simile
bastavano ad attaccare il movimento sbagliato.

La copia ERP non abbina da se': delega a
`stipendi_bonifici.associa_bonifici_stipendi`, il motore canonico che usa
identita' completa, acconti e residuo.
"""
import asyncio

from app.hr.services import cedolini_manager as copia_hr
from app.services import cedolini_manager as motore


def _run(coroutine):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coroutine)
    finally:
        loop.close()


class _DbSpia:
    """Registra le collection toccate.

    Non solleva: la funzione ha un `except Exception` che inghiottirebbe
    l'errore e tornerebbe False lo stesso, facendo passare il test per il
    motivo sbagliato. Qui si guarda cosa ha letto, non cosa ha restituito.
    """

    def __init__(self):
        self.accessi = []

    def __getitem__(self, nome):
        self.accessi.append(nome)
        raise RuntimeError("collection non disponibile nel test")

    def __getattr__(self, nome):
        return self[nome]


def test_la_copia_hr_e_un_re_export_del_modulo_unico():
    for nome in (
        "riconcilia_stipendio_automatico",
        "processa_tutti_cedolini_pdf",
        "get_anagrafica_dipendenti",
        "get_riepilogo_dipendente",
    ):
        assert getattr(copia_hr, nome) is getattr(motore, nome), (
            f"{nome} sul lato HR non e' la funzione del modulo unico."
        )


def test_senza_riga_di_prima_nota_non_si_abbina_nulla():
    """Nessun movimento_id, nessun abbinamento: il motore canonico parte da li'.

    La copia HR invece frugava comunque nell'estratto conto, quindi poteva
    riconciliare anche senza una riga di Prima Nota a cui agganciarsi.
    """
    db = _DbSpia()
    esito = _run(copia_hr.riconcilia_stipendio_automatico(
        db, "ROSSI MARIO", 1500.0, 3, 2026, "", "IT60X0542811101000000123456",
    ))

    assert esito is False
    assert db.accessi == [], (
        "Senza riga di Prima Nota la funzione ha letto comunque il database "
        f"({db.accessi}): sta abbinando per conto suo."
    )


def test_la_guardia_sullo_storico_autorizzato_e_condivisa():
    """PAYROLL_MIN_YEAR non c'era affatto sul lato HR."""
    assert copia_hr.PAYROLL_MIN_YEAR == motore.PAYROLL_MIN_YEAR == 2018
