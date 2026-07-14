"""Richiesta utente 14/07/2026: l'ingest automatico da Drive deve importare
nel flusso contabile attivo SOLO le fatture con data fattura nell'anno
corrente; gli anni precedenti vanno in un archivio storico di sola
consultazione (niente Prima Nota/scadenzario/alert/magazzino).
Copre: il dispatch in process_xml_bytes(applica_filtro_anno=True) e il
comportamento non distruttivo/idempotente di archivia_fattura_storica."""
import asyncio
from datetime import datetime, timezone

from app.routers.invoices import fatture_upload as fu_mod


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


class _FakeCollection:
    def __init__(self, docs=None):
        self.docs = docs or []

    async def find_one(self, query, *a, **k):
        for d in self.docs:
            if all(d.get(k2) == v2 for k2, v2 in query.items()):
                return dict(d)
        return None

    async def insert_one(self, doc, *a, **k):
        self.docs.append(dict(doc))


class _FakeDb:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _FakeCollection())


_ANNO_CORRENTE = datetime.now(timezone.utc).year
_ANNO_PASSATO = _ANNO_CORRENTE - 3


def _parsed(anno):
    return {
        "invoice_number": "42", "supplier_vat": "01879020517",
        "supplier_name": "RONDINELLA MARKET S.R.L.",
        "invoice_date": f"{anno}-05-10",
        "total_amount": 100.0, "imponibile": 90.0, "iva": 10.0,
        "tipo_documento": "TD01",
    }


def test_archivia_fattura_storica_non_richiama_flusso_attivo(monkeypatch):
    db = _FakeDb()
    chiamato = {}
    # Se archivia_fattura_storica chiamasse per errore ensure_supplier_exists
    # o auto_registra_prima_nota, questi monkeypatch lo farebbero fallire
    # rumorosamente invece di passare silenziosamente.
    async def _boom(*a, **k):
        chiamato["side_effect"] = True
        raise AssertionError("non deve essere chiamato per una fattura archiviata")
    monkeypatch.setattr(fu_mod, "ensure_supplier_exists", _boom)
    monkeypatch.setattr(fu_mod, "auto_registra_prima_nota", _boom)

    res = _run(fu_mod.archivia_fattura_storica(db, _parsed(_ANNO_PASSATO), "f.xml", "google_drive"))

    assert res["status"] == "archiviata"
    assert "side_effect" not in chiamato
    doc = db["invoices"].docs[0]
    assert doc["stato_import"] == "archivio_storico"
    assert doc["status"] == "archiviata"
    assert doc["supplier_id"] is None
    assert doc["anno"] == _ANNO_PASSATO


def test_archivia_fattura_storica_idempotente():
    db = _FakeDb()
    parsed = _parsed(_ANNO_PASSATO)

    r1 = _run(fu_mod.archivia_fattura_storica(db, parsed, "f.xml", "google_drive"))
    r2 = _run(fu_mod.archivia_fattura_storica(db, parsed, "f.xml", "google_drive"))

    assert r1["status"] == "archiviata"
    assert r2["status"] == "duplicate"
    assert len(db["invoices"].docs) == 1


def test_process_xml_bytes_filtro_anno_route_verso_archivio(monkeypatch):
    monkeypatch.setattr(fu_mod, "parse_fattura_xml", lambda xml: _parsed(_ANNO_PASSATO))
    chiamate = []

    async def fake_archivia(db, parsed, filename, source, xml_raw=None):
        chiamate.append("archivio")
        return {"status": "archiviata"}

    async def fake_import(db, parsed, filename, source, xml_raw=None):
        chiamate.append("attivo")
        return {"status": "imported"}

    monkeypatch.setattr(fu_mod, "archivia_fattura_storica", fake_archivia)
    monkeypatch.setattr(fu_mod, "import_parsed_invoice", fake_import)

    # _FakeDb() senza doc in sistema_stato -> get_anno_importazione_attivo
    # ricade sull'anno solare corrente, che qui coincide con _ANNO_CORRENTE.
    res = _run(fu_mod.process_xml_bytes(
        _FakeDb(), b"<x/>", "f.xml", source="google_drive", applica_filtro_anno=True
    ))

    assert res["status"] == "archiviata"
    assert chiamate == ["archivio"]


def test_process_xml_bytes_filtro_anno_corrente_va_al_flusso_attivo(monkeypatch):
    monkeypatch.setattr(fu_mod, "parse_fattura_xml", lambda xml: _parsed(_ANNO_CORRENTE))
    chiamate = []

    async def fake_archivia(db, parsed, filename, source, xml_raw=None):
        chiamate.append("archivio")
        return {"status": "archiviata"}

    async def fake_import(db, parsed, filename, source, xml_raw=None):
        chiamate.append("attivo")
        return {"status": "imported"}

    monkeypatch.setattr(fu_mod, "archivia_fattura_storica", fake_archivia)
    monkeypatch.setattr(fu_mod, "import_parsed_invoice", fake_import)

    res = _run(fu_mod.process_xml_bytes(
        _FakeDb(), b"<x/>", "f.xml", source="google_drive", applica_filtro_anno=True
    ))

    assert res["status"] == "imported"
    assert chiamate == ["attivo"]


def test_process_xml_bytes_senza_filtro_anno_ignora_lanno_di_upload_manuale(monkeypatch):
    # Default applica_filtro_anno=False: upload manuale via UI di una
    # fattura di un anno passato deve restare nel flusso attivo — un
    # utente che carica volontariamente un documento se lo aspetta.
    monkeypatch.setattr(fu_mod, "parse_fattura_xml", lambda xml: _parsed(_ANNO_PASSATO))
    chiamate = []

    async def fake_archivia(*a, **k):
        chiamate.append("archivio")
        return {"status": "archiviata"}

    async def fake_import(*a, **k):
        chiamate.append("attivo")
        return {"status": "imported"}

    monkeypatch.setattr(fu_mod, "archivia_fattura_storica", fake_archivia)
    monkeypatch.setattr(fu_mod, "import_parsed_invoice", fake_import)

    res = _run(fu_mod.process_xml_bytes(None, b"<x/>", "f.xml", source="xml_upload"))

    assert res["status"] == "imported"
    assert chiamate == ["attivo"]


def test_process_xml_bytes_data_illeggibile_resta_nel_flusso_attivo(monkeypatch):
    # Data mancante/malformata: mai archiviare silenziosamente per un XML
    # sospetto, resta nel flusso attivo dove è visibile e correggibile.
    parsed_senza_data = dict(_parsed(_ANNO_PASSATO))
    parsed_senza_data["invoice_date"] = ""
    monkeypatch.setattr(fu_mod, "parse_fattura_xml", lambda xml: parsed_senza_data)
    chiamate = []

    async def fake_archivia(*a, **k):
        chiamate.append("archivio")
        return {"status": "archiviata"}

    async def fake_import(*a, **k):
        chiamate.append("attivo")
        return {"status": "imported"}

    monkeypatch.setattr(fu_mod, "archivia_fattura_storica", fake_archivia)
    monkeypatch.setattr(fu_mod, "import_parsed_invoice", fake_import)

    res = _run(fu_mod.process_xml_bytes(
        _FakeDb(), b"<x/>", "f.xml", source="google_drive", applica_filtro_anno=True
    ))

    assert chiamate == ["attivo"]


def test_process_xml_bytes_rispetta_anno_configurato_non_solo_anno_solare(monkeypatch):
    # Richiesta utente 14/07/2026: l'anno attivo è un'impostazione (vedi
    # app.services.config_import), NON necessariamente l'anno solare del
    # server. Con anno attivo=2024 configurato, una fattura del 2024 deve
    # andare al flusso attivo anche se il calendario segna un altro anno.
    db = _FakeDb()
    db["sistema_stato"].docs = [{"chiave": "config_import_anno_attivo", "anno": 2024}]
    monkeypatch.setattr(fu_mod, "parse_fattura_xml", lambda xml: _parsed(2024))
    chiamate = []

    async def fake_archivia(*a, **k):
        chiamate.append("archivio")
        return {"status": "archiviata"}

    async def fake_import(*a, **k):
        chiamate.append("attivo")
        return {"status": "imported"}

    monkeypatch.setattr(fu_mod, "archivia_fattura_storica", fake_archivia)
    monkeypatch.setattr(fu_mod, "import_parsed_invoice", fake_import)

    res = _run(fu_mod.process_xml_bytes(
        db, b"<x/>", "f.xml", source="google_drive", applica_filtro_anno=True
    ))

    assert res["status"] == "imported"
    assert chiamate == ["attivo"]
