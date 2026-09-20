"""Guardia: chi smista gli esiti dei corrispettivi Drive li conosce tutti.

Regola di CLAUDE.md, nata dalle 19 chiusure RT rimaste ferme in `Errori`:
«Ogni punto che smista un esito deve conoscere tutti gli stati: quello
sconosciuto cade nel ramo errore».

Nei due punti di `drive_corrispettivi_ingest` valeva il contrario. L'`else`
era il ramo del successo:

    if stato == "duplicate": ...
    elif stato == "error":   ...
    else:                    result["imported"] += 1   # <- qualunque cosa

Cosi' uno stato nuovo — `skipped_altro_anno`, introdotto il 20/09/2026 quando
il filtro anno ha smesso di archiviare le giornate degli anni chiusi e ha
iniziato a scartarle — veniva contato come **importato** nel giro dei 15
minuti e come **buco recuperato** nella quadratura, che per di piu' genera un
alert. Numeri inventati su un lavoro mai fatto, e nessun modo di accorgersene.
"""
import asyncio

import pytest

from app.services import drive_corrispettivi_ingest as ingest


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class _ServizioFinto:
    """Restituisce a comando l'esito che vogliamo far smistare."""

    def __init__(self, esito):
        self.esito = esito

    async def process_xml(self, xml_content, filename, applica_filtro_anno=False):
        return dict(self.esito)


class _Collezione:
    async def update_one(self, *a, **k):
        return None

    async def find_one(self, *a, **k):
        return None


class _Db:
    def __getitem__(self, _nome):
        return _Collezione()


@pytest.fixture
def quadratura(monkeypatch):
    """Monta la quadratura su un Drive finto con un solo XML dentro Elaborate."""

    def _monta(esito_process_xml):
        monkeypatch.setattr(ingest, "is_configured", lambda: True)
        monkeypatch.setattr(ingest, "_build_drive_service", lambda: object())
        monkeypatch.setattr(ingest, "_folder_id", lambda: "root")
        monkeypatch.setattr(
            ingest, "discover_lifecycle_folders",
            lambda *a, **k: [{"folder_id": "el26", "relative_path": "2026/Elaborate"}],
        )
        monkeypatch.setattr(
            ingest, "_list_source_files",
            lambda *a, **k: [{"id": "f1", "name": "chiusura.xml"}],
        )
        monkeypatch.setattr(ingest, "_download_bytes", lambda *a, **k: b"<x/>")
        monkeypatch.setattr(
            ingest, "_xml_documents_from_source",
            lambda nome, contenuto: [("chiusura.xml", b"<x/>")],
        )
        monkeypatch.setattr(
            "app.services.corrispettivi_service.get_corrispettivi_service",
            lambda db: _ServizioFinto(esito_process_xml),
        )
        return _run(ingest.verifica_quadratura_elaborate(_Db()))

    return _monta


def test_la_giornata_di_un_anno_chiuso_non_e_un_buco_recuperato(quadratura):
    esito = quadratura({
        "status": "skipped_altro_anno", "anno": 2023, "anno_attivo": 2026,
        "message": "Giornata del 2023, anno attivo 2026: non importata",
    })

    assert esito["recuperati"] == 0, (
        "Una giornata che non deve entrare e' stata contata fra i buchi "
        "recuperati: la quadratura dichiara un lavoro mai fatto e genera "
        "un alert su di esso."
    )
    assert esito["errori"] == 0, "Non e' nemmeno un errore: e' una scelta."
    assert esito["saltati_altro_anno"] == 1


def test_un_esito_sconosciuto_cade_nel_ramo_errore(quadratura):
    """Il contrario di prima, ed e' il punto della regola.

    Uno stato che nessuno ha previsto deve farsi vedere, non passare per
    lavoro riuscito: e' cosi' che uno stato nuovo resta invisibile per
    settimane.
    """
    esito = quadratura({"status": "stato_mai_visto"})

    assert esito["errori"] == 1, (
        "Un esito sconosciuto e' stato contato come recuperato: il ramo di "
        "default deve essere l'errore, mai il successo."
    )
    assert esito["recuperati"] == 0
    assert "stato_mai_visto" in esito["details"][0]["error"]


def test_il_buco_vero_resta_un_buco_recuperato(quadratura):
    """La quadratura deve continuare a fare il suo mestiere."""
    esito = quadratura({"status": "created", "corrispettivo_id": "c1"})

    assert esito["recuperati"] == 1
    assert esito["errori"] == 0


def test_la_giornata_gia_in_archivio_quadra(quadratura):
    esito = quadratura({"status": "duplicate", "corrispettivo_id": "c1"})

    assert esito["quadrati"] == 1
    assert esito["recuperati"] == 0 and esito["errori"] == 0
