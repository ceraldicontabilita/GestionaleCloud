"""Il catalogo bar del vecchio archivio, bundlato come listino per fornitore."""
import asyncio
import json
import os

from mongomock_motor import AsyncMongoMockClient

from app.lotti.servizi import listino_fornitore as lf

PERCORSO = os.path.join(os.path.dirname(__file__), "..", "..", "app", "lotti", "data",
                        "listini_catalogo_ceraldi_2026-07.json")


def _listini():
    with open(PERCORSO, encoding="utf-8") as f:
        return json.load(f)["listini"]


def _importa_tutto(db):
    async def _run():
        esiti = []
        for l in _listini():
            f = l["fornitore"]
            esiti.append(await lf.importa(
                db, lf.leggi_righe(l["tabella"]), fornitore_nome=f["nome"], fornitore_key=f["fornitore_key"],
                piva=f["partita_iva"], url="", data_listino=l["data_listino"],
                file_sha256=l["file_sha256"], nome_file=l["file"]))
        return esiti
    return asyncio.run(_run())


def test_ogni_riga_del_bundle_e_letta_e_i_totali_tornano():
    listini = _listini()
    assert len(listini) == 15
    totale = 0
    for l in listini:
        esito = lf.leggi_righe(l["tabella"])
        assert len(esito.righe) == len(l["tabella"]) - 1, l["fornitore"]["nome"]
        totale += len(esito.righe)
    assert totale == 808


def test_import_idempotente_e_piva_solo_dove_c_e():
    db = AsyncMongoMockClient()["t"]
    primo = _importa_tutto(db)
    assert sum(e["nuovi"] for e in primo) == 808
    secondo = _importa_tutto(db)
    assert sum(e["nuovi"] + e["aggiornati"] for e in secondo) == 0
    senza_piva = sorted(l["fornitore"]["fornitore_key"] for l in _listini() if not l["fornitore"]["partita_iva"])
    assert senza_piva == ["acquaviva", "emiliocristiani"]
