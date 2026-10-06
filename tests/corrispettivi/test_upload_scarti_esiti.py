"""Gli upload RT espongono gli scarti come errori, senza contarli importati.

Si usa il parser e il writer reali con l'archivio di test in memoria; nessuna
scrittura di produzione e nessuna sostituzione dell'esito del motore.
"""

import io
import zipfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import Database
from app.routers.invoices.corrispettivi import router
from tests.corrispettivi._comune import attive, nuovo_db, run, xml_chiusura


@pytest.fixture
def api(monkeypatch):
    db = nuovo_db("upload-scarti")
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))
    app = FastAPI()
    app.include_router(router, prefix="/api/corrispettivi")
    with TestClient(app) as client:
        yield client, db


def _scarti():
    non_quadrato = xml_chiusura(progressivo="9001", imponibile="1000.00", imposta="100.00")
    componente_netta = xml_chiusura(progressivo="9002", imponibile="1000.00",
        importo_parziale="909.09").replace('</Riepilogo>',
        '<NonRiscossoServizi>90.91</NonRiscossoServizi></Riepilogo>')
    return [
        ("scarto.xml", non_quadrato, "non_riscosso_non_dichiarato"),
        ("servizi.xml", componente_netta, "componenti_fiscali_da_verificare"),
    ]


@pytest.mark.parametrize("nome,xml,motivo", _scarti())
def test_upload_singolo_dichiara_insuccesso_e_motivo_senza_registrare(api, nome, xml, motivo):
    client, db = api
    response = client.post('/api/corrispettivi/upload-xml',
        files={"file": (nome, xml.encode(), "application/xml")})

    assert response.status_code == 200
    esito = response.json()
    assert esito["success"] is False
    assert esito["action"] == "scartato" and esito["motivo"] == motivo
    assert motivo in esito["message"]
    assert esito["corrispettivo_id"] is None
    for registro in ('corrispettivi', 'prima_nota_cassa', 'prima_nota_banca', 'movimenti_contabili'):
        assert run(attive(db, registro)) == []


def _lotto():
    return ([("valido.xml", xml_chiusura(progressivo="9000", importo_parziale="909.09"))]
            + [(nome, xml) for nome, xml, _ in _scarti()])


@pytest.mark.parametrize("canale", ["upload-xml-bulk", "upload-zip"])
def test_lotto_misto_conta_solo_la_giornata_valida_e_ripetuto_non_crea_doppioni(api, canale):
    client, db = api
    lotto = _lotto()
    if canale == 'upload-xml-bulk':
        files = [("files", (nome, xml.encode(), "application/xml")) for nome, xml in lotto]
    else:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as archivio:
            for nome, xml in lotto:
                archivio.writestr(nome, xml.encode())
        files = {"file": ("lotto.zip", buffer.getvalue(), "application/zip")}

    for giro in range(2):
        response = client.post(f'/api/corrispettivi/{canale}', files=files)
        assert response.status_code == 200, response.text
        esito = response.json()
        assert esito["total"] == 3 and esito["failed"] == 2
        assert esito["imported"] == (1 if giro == 0 else 0)
        assert len(esito["success"]) == (1 if giro == 0 else 0)
        assert len(esito["duplicates"]) == (0 if giro == 0 else 1)
        assert {r["filename"]: r["motivo"] for r in esito["errors"]} == {
            nome: motivo for nome, _, motivo in _scarti()}
        assert len(run(attive(db, 'corrispettivi'))) == 1
        assert len(run(attive(db, 'prima_nota_cassa'))) == 1
        assert len(run(attive(db, 'prima_nota_banca'))) == 1
        assert len(run(attive(db, 'movimenti_contabili'))) == 1
