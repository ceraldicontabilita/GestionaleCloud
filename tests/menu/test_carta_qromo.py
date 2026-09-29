"""La carta del menu: tre livelli come nella replica Qromo, dati dal repository o dall'admin."""
import asyncio
import json

import pytest

from app.menu import carta_qromo as carta
from app.services.archivio_documenti_memoria import ClientArchivioMemoria


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def db(monkeypatch):
    finto = ClientArchivioMemoria()["carta_test"]

    async def _finto():
        return finto

    monkeypatch.setattr(carta, "_db", _finto)
    return finto


def test_il_seme_ha_la_carta_completa(db):
    dati = _run(carta.carta_pubblica())
    assert len(dati["menus"]) == 11 and len(dati["cats"]) == 68 and len(dati["items"]) == 769
    prodotto = next(i for i in dati["items"] if i["id"] == 152788)
    assert prodotto["p"] == 250 and "gluten" in prodotto["a"] and prodotto["mat"]
    # le foto sono file serviti dal menu, non indirizzi esterni
    foto = [x["pic"] for x in dati["items"] + dati["cats"] + dati["menus"] if x["pic"]]
    assert foto and all(f.startswith("/menu/carta/img/") for f in foto)


def test_ogni_foto_indicata_esiste_nei_file_statici(db):
    from pathlib import Path
    radice = Path(__file__).resolve().parents[2] / "frontend_menu" / "public"
    dati = _run(carta.carta_pubblica())
    mancanti = {x["pic"] for x in dati["items"] + dati["cats"] + dati["menus"]
                if x["pic"] and not (radice / x["pic"].removeprefix("/menu/")).exists()}
    assert not mancanti


def test_la_scelta_dell_admin_cambia_prezzo_e_disponibilita_e_sopravvive_all_import(db):
    _run(carta.imposta_prodotto(152788, carta.SceltaProdotto(prezzo_centesimi=300, disponibile=False), "admin"))
    dati = _run(carta.carta_pubblica())
    p = next(i for i in dati["items"] if i["id"] == 152788)
    assert p["p"] == 300 and p["on"] == 0
    seme = carta._seme()
    _run(carta.importa(carta.Importa(**seme), "admin"))
    p = next(i for i in _run(carta.carta_pubblica())["items"] if i["id"] == 152788)
    assert p["p"] == 300 and p["on"] == 0, "un nuovo import non cancella le scelte"
    _run(carta.toglie_override(152788, "admin"))
    p = next(i for i in _run(carta.carta_pubblica())["items"] if i["id"] == 152788)
    assert p["p"] == 250 and p["on"] == 1


def test_prodotto_inesistente_e_import_incompleto_sono_rifiutati(db):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        _run(carta.imposta_prodotto(1, carta.SceltaProdotto(disponibile=True), "admin"))
    assert e.value.status_code == 404
    with pytest.raises(HTTPException) as e:
        _run(carta.importa(carta.Importa(pub={"menus": []}), "admin"))
    assert e.value.status_code == 422
    assert _run(carta.stato("admin"))["fonte"] == "seme"
