"""Regressione: gli ingest devono seguire la struttura Drive reale.

Non testa parser/DB: verifica il contratto di discovery condiviso dai tre
scanner operativi senza rete e senza creare cartelle parallele alla radice.
"""
from app.services import (
    drive_cedolini_ingest,
    drive_corrispettivi_ingest,
    drive_invoice_ingest,
)


class _Request:
    def __init__(self, result):
        self._result = result

    def execute(self):
        return self._result


class _Files:
    def __init__(self, children):
        self.children = children
        self.created = []

    def list(self, **kwargs):
        query = kwargs.get("q", "")
        parent_id = query.split("'", 2)[1] if "' in parents" in query else None
        return _Request({"files": list(self.children.get(parent_id, []))})

    def create(self, body, **kwargs):
        self.created.append(body)
        return _Request({"id": f"created-{len(self.created)}"})


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


def _assert_year_scanner_uses_existing_nested_inboxes(module):
    service = _Service({
        "root": [_folder("y2025", "2025"), _folder("y2026", "2026")],
        "y2025": [_folder("in25", "DA ELABORARE")],
        "y2026": [_folder("in26", "DA ELABORARE")],
    })

    contexts = module._inbox_contexts(service, "root")

    assert [(x["inbox_id"], x["lifecycle_parent_id"]) for x in contexts] == [
        ("in25", "y2025"),
        ("in26", "y2026"),
    ]
    # Punto essenziale: nessun nuovo `Da elaborare` viene creato alla radice.
    assert service.resource.created == []


def test_fatture_usano_da_elaborare_per_anno():
    _assert_year_scanner_uses_existing_nested_inboxes(drive_invoice_ingest)


def test_corrispettivi_usano_da_elaborare_per_anno():
    _assert_year_scanner_uses_existing_nested_inboxes(drive_corrispettivi_ingest)


def test_cedolini_usano_da_elaborare_per_dipendente():
    service = _Service({
        "root": [_folder("mario", "ROSSI MARIO"), _folder("anna", "BIANCHI ANNA")],
        "mario": [_folder("in-mario", "DA ELABORARE")],
        "anna": [_folder("in-anna", "DA ELABORARE")],
    })

    contexts = drive_cedolini_ingest._inbox_contexts(service, "root")

    assert [(x["inbox_id"], x["lifecycle_parent_id"]) for x in contexts] == [
        ("in-anna", "anna"),
        ("in-mario", "mario"),
    ]
    assert service.resource.created == []


def test_fallback_legacy_resta_compatibile_se_la_radice_e_vuota():
    for module in (
        drive_invoice_ingest,
        drive_corrispettivi_ingest,
        drive_cedolini_ingest,
    ):
        service = _Service({"root": []})
        contexts = module._inbox_contexts(service, "root")
        assert contexts[0]["legacy_fallback"] is True
        assert contexts[0]["lifecycle_parent_id"] == "root"
        assert service.resource.created[0]["name"] == "Da elaborare"
