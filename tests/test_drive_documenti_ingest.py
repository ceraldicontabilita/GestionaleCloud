"""
Ingest generico documenti fiscali da Drive.

Verifica canali, tassonomia, guardie e soprattutto i limiti di scansione del
lifecycle: Bonifici dipendenti puo' scendere fino al fascicolo dipendente,
Verbali e canali fiscali lavorano solo sulla DA ELABORARE diretta.
"""
import asyncio

from app.services import drive_documenti_ingest as d


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_canali_definiti():
    assert set(d.CANALI) == {
        "bonifico", "dichiarazione_iva", "cartella_esattoriale", "avviso_bonario",
        "verbale",
    }


def test_build_doc_categoria_corretta():
    for canale in d.CANALI:
        doc = d._build_inbox_doc(b"%PDF-1.4 x", "f.pdf", canale)
        assert doc["category"] == canale
        assert doc["pdf_data"] and doc["file_hash"] and doc["id"]
        assert doc["fonte"] == f"drive_{canale}"


def test_profondita_lifecycle_per_canale():
    # BONIFICI DIPENDENTI/<dipendente>/DA ELABORARE
    assert d._lifecycle_depth("bonifico") == 2
    # VERBALI_AUTO/DA ELABORARE: non entra in 01_VERBALI/02_NOTIFICHE/...
    assert d._lifecycle_depth("verbale") == 1
    assert d._lifecycle_depth("dichiarazione_iva") == 1
    assert d._lifecycle_depth("cartella_esattoriale") == 1
    assert d._lifecycle_depth("avviso_bonario") == 1


def test_sync_canale_sconosciuto():
    res = _run(d.sync(None, "pippo"))
    assert res["status"] == "error"


def test_sync_disabilitato_non_tocca_db():
    res = _run(d.sync(None, "dichiarazione_iva"))
    assert res["status"] in ("disabled", "not_configured")


def test_sync_tutti_vuoto_se_spenti():
    res = _run(d.sync_tutti(None))
    assert res["status"] == "ok"
    assert res["canali"] == {}


class _Request:
    def __init__(self, result):
        self.result = result

    def execute(self):
        return self.result


class _Files:
    def __init__(self, children):
        self.children = children

    def list(self, **kwargs):
        query = kwargs.get("q", "")
        parent_id = query.split("'", 2)[1] if "' in parents" in query else None
        return _Request({"files": list(self.children.get(parent_id, []))})


class _Service:
    def __init__(self, children):
        self.resource = _Files(children)

    def files(self):
        return self.resource


def _folder(folder_id, name):
    return {
        "id": folder_id,
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
    }


def _pdf(file_id, name):
    return {"id": file_id, "name": name, "mimeType": "application/pdf"}


def test_lista_pdf_e_solo_diretta_non_ricorsiva():
    service = _Service({
        "inbox": [_pdf("p1", "verbale.pdf"), _folder("nested", "01_VERBALI")],
        "nested": [_pdf("p2", "storico.pdf")],
    })

    result = d._list_pdf_files_direct(service, "inbox")

    assert [item["id"] for item in result] == ["p1"]


def test_resolve_state_folder_riusa_elaborate_maiuscola_senza_crearne_unaltra(monkeypatch):
    service = _Service({"employee": [_folder("done", "ELABORATE")]})
    created = []

    monkeypatch.setattr(
        d,
        "_get_or_create_elaborate_folder",
        lambda _service, parent_id: created.append(parent_id) or "new-done",
    )

    folder_id = d._resolve_state_folder(service, "employee", "elaborate")

    assert folder_id == "done"
    assert created == []


def test_resolver_bonifico_puo_trovare_inbox_dipendente_ma_verbale_non_scende_nelle_viste():
    from app.services.drive_lifecycle_tree import discover_inboxes

    bonifici = _Service({
        "bonifici": [_folder("mario", "ROSSI MARIO")],
        "mario": [_folder("mario-in", "DA ELABORARE")],
    })
    assert [x["inbox_id"] for x in discover_inboxes(
        bonifici, "bonifici", max_depth=d._lifecycle_depth("bonifico")
    )] == ["mario-in"]

    verbali = _Service({
        "verbali": [_folder("direct", "DA ELABORARE"), _folder("archive", "01_VERBALI")],
        "archive": [_folder("trap", "DA ELABORARE")],
    })
    assert [x["inbox_id"] for x in discover_inboxes(
        verbali, "verbali", max_depth=d._lifecycle_depth("verbale")
    )] == ["direct"]
