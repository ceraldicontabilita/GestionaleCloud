"""I test non possono raggiungere i dati aziendali ereditati dalla shell."""
import socket

import pytest


def test_archivio_lotti_della_suite_e_solo_memoria():
    from app.lotti.db import STORAGE
    assert STORAGE == "memoria"


@pytest.mark.parametrize("method", ["connect", "connect_ex"])
def test_connessione_esterna_fermata_prima_della_rete(method):
    with socket.socket() as connection:
        with pytest.raises(RuntimeError, match="connessione esterna vietata"):
            getattr(connection, method)(("192.0.2.1", 443))
