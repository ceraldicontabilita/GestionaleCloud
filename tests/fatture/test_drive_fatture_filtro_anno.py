"""Nel gestionale entra SOLO l'anno attivo.

Il 14/07/2026 il titolare aveva chiesto che gli anni precedenti finissero in
un archivio di sola consultazione dentro `invoices`. Il 20/09/2026 ha
cambiato idea: quell'archivio erano 1.127 fatture e 52 MB che non entravano
in nessun conto, non generavano nessun alert e non stavano nel libro
giornale, ma riempivano le liste. Adesso una fattura di un altro anno non
entra affatto: l'originale resta su Drive, che e' la fonte documentale, e il
file va comunque in `Elaborate`.

Per rivedere un anno intero: cambiare l'anno attivo e rilanciare la
ricostruzione Drive, che rilegge tutti gli XML dal cursore."""
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

    async def update_one(self, query, update, *a, **k):
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                doc.update(update.get("$set", {}))
                break


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


def test_provenienza_canonica_non_viene_sovrascritta_e_le_fonti_si_accodano():
    existing = {
        "drive_file_id": "drive-originale",
        "file_hash": "a" * 64,
        "source_occurrences": [{"parent_id": "folder-a", "path": "A"}],
        "source_documents": [{"drive_file_id": "drive-originale", "file_hash": "a" * 64}],
    }
    incoming = {
        "drive_file_id": "drive-secondo",
        "file_hash": "b" * 64,
        "source_occurrences": [{"parent_id": "folder-b", "path": "B"}],
        "source_documents": [{"drive_file_id": "drive-secondo", "file_hash": "b" * 64}],
    }

    merged = fu_mod._source_metadata_fields(incoming, existing)

    assert merged["drive_file_id"] == "drive-originale"
    assert merged["file_hash"] == "a" * 64
    assert len(merged["source_occurrences"]) == 2
    assert len(merged["source_documents"]) == 2


def test_una_fattura_di_un_altro_anno_non_entra_affatto(monkeypatch):
    """Dal 20/09/2026 nel gestionale resta SOLO l'anno attivo.

    Prima queste fatture entravano in `invoices` marcate `archivio_storico`
    (richiesta del titolare del 14/07/2026, «consultabile per visione
    personale»): erano 1.127 documenti e 52 MB che non entravano in nessun
    conto, non generavano nessun alert e non erano nel libro giornale, ma
    riempivano le liste — e tornavano da soli a ogni ricostruzione Drive,
    quindi cancellarli non sarebbe bastato. L'originale non si perde: l'XML
    resta su Drive, che è la fonte documentale.
    """
    monkeypatch.setattr(fu_mod, "parse_fattura_xml", lambda xml: _parsed(_ANNO_PASSATO))
    chiamate = []

    async def fake_import(db, parsed, filename, source, xml_raw=None, **kwargs):
        chiamate.append("attivo")
        return {"status": "imported"}

    monkeypatch.setattr(fu_mod, "import_parsed_invoice", fake_import)

    # _FakeDb() senza doc in sistema_stato -> get_anno_importazione_attivo
    # ricade sull'anno solare corrente, che qui coincide con _ANNO_CORRENTE.
    res = _run(fu_mod.process_xml_bytes(
        _FakeDb(), b"<x/>", "f.xml", source="google_drive", applica_filtro_anno=True
    ))

    assert res["status"] == "skipped_altro_anno"
    assert res["anno"] == _ANNO_PASSATO
    assert chiamate == [], "non deve scrivere niente"
    assert not hasattr(fu_mod, "archivia_fattura_storica"), (
        "l'archivio storico non esiste piu': niente codice morto"
    )


def test_lo_stato_nuovo_manda_il_file_in_elaborate_non_in_errori():
    """Uno stato che l'ingest non conosce finisce nel ramo «errore»: il file
    andrebbe in `Errori` e verrebbe riletto per sempre. Con 1.129 XML
    pre-2026 su Drive sarebbe una cartella Errori piena di file sani."""
    import inspect
    from app.services import drive_invoice_ingest

    sorgente = inspect.getsource(drive_invoice_ingest)
    # I tre punti che smistano l'esito: giro 15 minuti, quadratura, ricostruzione
    assert sorgente.count('"skipped_altro_anno"') == 3, (
        "ogni punto che smista lo stato dell'import deve conoscere "
        "`skipped_altro_anno`, altrimenti manda il file in Errori"
    )


def test_process_xml_bytes_filtro_anno_corrente_va_al_flusso_attivo(monkeypatch):
    monkeypatch.setattr(fu_mod, "parse_fattura_xml", lambda xml: _parsed(_ANNO_CORRENTE))
    chiamate = []


    async def fake_import(db, parsed, filename, source, xml_raw=None, **kwargs):
        chiamate.append("attivo")
        return {"status": "imported"}

    monkeypatch.setattr(fu_mod, "import_parsed_invoice", fake_import)

    res = _run(fu_mod.process_xml_bytes(
        _FakeDb(), b"<x/>", "f.xml", source="google_drive", applica_filtro_anno=True
    ))

    assert res["status"] == "imported"
    assert chiamate == ["attivo"]


def test_replay_storico_salva_fattura_senza_riattivare_derivati(monkeypatch):
    db = _FakeDb()

    async def fake_supplier(*_args, **_kwargs):
        return {
            "supplier_id": "FORN-1",
            "supplier_created": False,
            "metodo_pagamento": "banca",
        }

    async def side_effect_vietato(*_args, **_kwargs):
        raise AssertionError("il replay storico non deve attivare derivati")

    monkeypatch.setattr(fu_mod, "ensure_supplier_exists", fake_supplier)
    monkeypatch.setattr(fu_mod, "auto_registra_prima_nota", side_effect_vietato)
    monkeypatch.setattr(fu_mod, "_collega_nota_credito", side_effect_vietato)
    monkeypatch.setattr(
        fu_mod, "riprocessa_estratto_dopo_import_fattura",
        side_effect_vietato,
    )

    result = _run(fu_mod.import_parsed_invoice(
        db,
        _parsed(_ANNO_CORRENTE),
        "recupero.xml",
        "ricostruzione_drive",
        replay_storico=True,
    ))

    assert result["status"] == "imported"
    assert result["replay_storico"] is True
    invoice = db["invoices"].docs[0]
    assert invoice["supplier_id"] == "FORN-1"
    assert invoice["replay_storico"] is True
    assert invoice["stato_derivati"] == "da_ricalcolare"


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

    monkeypatch.setattr(fu_mod, "import_parsed_invoice", fake_import)

    res = _run(fu_mod.process_xml_bytes(
        db, b"<x/>", "f.xml", source="google_drive", applica_filtro_anno=True
    ))

    assert res["status"] == "imported"
    assert chiamate == ["attivo"]
