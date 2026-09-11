from app.services import drive_f24_ingest as ing


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


def test_filename_accetta_solo_pdf():
    assert ing.is_f24_filename("F24_ritenute.pdf")
    assert ing.is_f24_filename("MODELLO.PDF")
    assert not ing.is_f24_filename("f24.xml")
    assert not ing.is_f24_filename("")


def test_lista_pdf_non_attraversa_cartelle_laterali():
    service = _Service({
        "inbox": [_pdf("model", "F24.pdf"), _folder("side", "99_DA_VERIFICARE")],
        "side": [_pdf("hidden", "F24_da_verificare.pdf")],
    })

    files = ing._list_pdf_files(service, "inbox")

    assert [item["id"] for item in files] == ["model"]


def test_resolve_state_folder_riusa_elaborate_reale_maiuscola(monkeypatch):
    service = _Service({"root": [_folder("done", "ELABORATE")]})
    created = []
    monkeypatch.setattr(
        ing,
        "_get_or_create_elaborate_folder",
        lambda _service, parent_id: created.append(parent_id) or "new-done",
    )

    assert ing._resolve_state_folder(service, "root", "elaborate") == "done"
    assert created == []


def test_configurazione_richiede_folder_e_credenziali(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "DRIVE_F24_FOLDER_ID", None)
    monkeypatch.setattr(settings, "GOOGLE_DRIVE_SA_FILE", None)
    monkeypatch.setattr(settings, "GOOGLE_DRIVE_SA_JSON", None)
    monkeypatch.setattr(settings, "GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON", None)
    assert ing.is_configured() is False

    monkeypatch.setattr(settings, "DRIVE_F24_FOLDER_ID", "f24-root")
    assert ing.is_configured() is False

    monkeypatch.setattr(settings, "GOOGLE_DRIVE_SA_JSON", '{"type":"service_account"}')
    assert ing.is_configured() is True
