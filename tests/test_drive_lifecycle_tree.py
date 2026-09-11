from app.services.drive_lifecycle_tree import (
    discover_inboxes,
    resolve_inboxes_or_legacy,
)


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
        parent_id = None
        marker = "' in parents"
        if marker in query:
            parent_id = query.split("'", 2)[1]
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


def test_scopre_inbox_per_anno_senza_attraversare_elaborate():
    service = _Service({
        "root": [_folder("y2025", "2025"), _folder("y2026", "2026"), _folder("done", "Elaborate")],
        "y2025": [_folder("in25", "DA ELABORARE")],
        "y2026": [_folder("in26", "Da elaborare")],
        "done": [_folder("trap", "DA ELABORARE")],
    })

    result = discover_inboxes(service, "root", max_depth=2)

    assert [(x["inbox_id"], x["lifecycle_parent_id"], x["relative_path"]) for x in result] == [
        ("in25", "y2025", "2025/DA ELABORARE"),
        ("in26", "y2026", "2026/Da elaborare"),
    ]


def test_scopre_inbox_per_dipendente_e_non_accetta_nomi_legacy_prefissati():
    service = _Service({
        "root": [_folder("mario", "ROSSI MARIO"), _folder("legacy", "Cedolini Paga__90 - DA ELABORARE")],
        "mario": [_folder("in-mario", "DA_ELABORARE")],
        "legacy": [_folder("too-deep", "DA ELABORARE")],
    })

    result = discover_inboxes(service, "root", max_depth=2)

    assert len(result) == 1
    assert result[0]["inbox_id"] == "in-mario"
    assert result[0]["lifecycle_parent_id"] == "mario"


def test_fallback_crea_inbox_root_solo_se_non_esistono_inbox_annidate():
    service = _Service({
        "root": [_folder("y2026", "2026")],
        "y2026": [_folder("in26", "DA ELABORARE")],
    })
    created = []

    def create_legacy(_service, parent_id):
        created.append(parent_id)
        return "legacy-inbox"

    result = resolve_inboxes_or_legacy(service, "root", create_legacy, max_depth=2)
    assert result[0]["inbox_id"] == "in26"
    assert created == []

    empty_service = _Service({"root": []})
    fallback = resolve_inboxes_or_legacy(empty_service, "root", create_legacy, max_depth=2)
    assert fallback[0]["inbox_id"] == "legacy-inbox"
    assert fallback[0]["lifecycle_parent_id"] == "root"
    assert fallback[0]["legacy_fallback"] is True
    assert created == ["root"]
