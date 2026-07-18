"""Richiesta utente 16/07/2026: bottone in Admin per l'import "pulito per
anno" — selezioni l'anno e il sistema importa da Drive solo fatture e
corrispettivi di quell'anno. La parte critica è la PROMOZIONE: un file di
un anno diverso da quello attivo viene archiviato e spostato in Elaborate
su Drive, quindi rilanciare il sync dopo aver cambiato anno non lo
ritroverebbe mai — i documenti dell'anno scelto già in archivio vengono
ripresi da lì e fatti entrare nel flusso attivo."""
import asyncio

from app.services import config_import as mod


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


def _match(doc, query):
    for k, v in query.items():
        if isinstance(v, dict):
            if "$regex" in v and not str(doc.get(k, "")).startswith(v["$regex"].lstrip("^")):
                return False
            if "$ne" in v and doc.get(k) == v["$ne"]:
                return False
        else:
            if doc.get(k) != v:
                return False
    return True


class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    async def to_list(self, n=None):
        return list(self._docs[:n] if n else self._docs)


class _Coll:
    def __init__(self, docs=None):
        self.docs = docs or []

    def find(self, query=None, projection=None, *a, **k):
        return _Cursor([dict(d) for d in self.docs if _match(d, query or {})])

    async def find_one(self, query, *a, **k):
        for d in self.docs:
            if _match(d, query):
                return dict(d)
        return None

    async def insert_one(self, doc, *a, **k):
        self.docs.append(dict(doc))

    async def update_one(self, query, update, upsert=False, *a, **k):
        for d in self.docs:
            if _match(d, query):
                d.update(update.get("$set", {}))
                return
        if upsert:
            nuovo = {k2: v2 for k2, v2 in query.items() if not isinstance(v2, dict)}
            nuovo.update(update.get("$set", {}))
            self.docs.append(nuovo)

    async def delete_one(self, query, *a, **k):
        before = len(self.docs)
        self.docs = [d for d in self.docs if not _match(d, query)]

        class _R:
            deleted_count = before - len(self.docs)
        return _R()

    async def delete_many(self, query, *a, **k):
        return await self.delete_one(query)


class _Db:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _Coll())


def test_promozione_corrispettivo_archiviato_entra_in_prima_nota():
    db = _Db()
    db["corrispettivi"].docs = [
        {"id": "c23", "data": "2023-05-10", "stato_import": "archivio_storico",
         "status": "archiviata", "totale": 1000.0,
         "pagato_contanti": 400.0, "pagato_elettronico": 600.0},
    ]

    esito = _run(mod.promuovi_archivio_anno(db, 2023))

    assert esito["corrispettivi_promossi"] == 1
    corr = db["corrispettivi"].docs[0]
    assert corr["stato_import"] == "promosso_da_archivio"
    assert corr["prima_nota_cassa_id"]
    # Movimenti canonici creati: entrata totale + uscita POS in cassa;
    # MODELLO POS 18/07/2026: MAI banca sintetica
    cassa = db["prima_nota_cassa"].docs
    assert any(m["tipo"] == "entrata" and m["importo"] == 1000.0 for m in cassa)
    assert any(m["tipo"] == "uscita" and m["importo"] == 600.0 for m in cassa)
    assert not any(m.get("source") == "corrispettivo_pos" for m in db["prima_nota_banca"].docs)


def test_promozione_salta_giorno_gia_attivo():
    db = _Db()
    db["corrispettivi"].docs = [
        {"id": "attivo", "data": "2023-05-10", "stato_import": "promosso_da_archivio",
         "totale": 1000.0},
        {"id": "arch", "data": "2023-05-10", "stato_import": "archivio_storico",
         "status": "archiviata", "totale": 1000.0},
    ]

    esito = _run(mod.promuovi_archivio_anno(db, 2023))

    assert esito["corrispettivi_promossi"] == 0
    assert esito["corrispettivi_gia_attivi"] == 1
    assert db["prima_nota_cassa"].docs == []  # nessun movimento doppio


def test_promozione_fattura_archiviata_ripassa_dalla_pipeline(monkeypatch):
    db = _Db()
    db["invoices"].docs = [
        {"id": "f23", "invoice_date": "2023-03-01", "stato_import": "archivio_storico",
         "filename": "IT123_fatt.xml", "xml_raw": "<FatturaElettronica>...</FatturaElettronica>"},
        {"id": "f23-noxml", "invoice_date": "2023-04-01", "stato_import": "archivio_storico"},
    ]
    chiamate = []

    async def _fake_process_xml_bytes(db_, content, filename, source, applica_filtro_anno):
        chiamate.append({"filename": filename, "source": source,
                         "applica_filtro_anno": applica_filtro_anno})
        return {"status": "imported"}

    monkeypatch.setattr("app.routers.invoices.fatture_upload.process_xml_bytes",
                        _fake_process_xml_bytes)

    esito = _run(mod.promuovi_archivio_anno(db, 2023))

    assert esito["fatture_promosse"] == 1
    assert esito["fatture_senza_xml"] == 1
    assert chiamate[0]["source"] == "promozione_archivio"
    assert chiamate[0]["applica_filtro_anno"] is False
    # il doc archiviato con XML è stato rimosso PRIMA del reimport (dedup invoice_key)
    assert all(d["id"] != "f23" for d in db["invoices"].docs)
    # quello senza XML resta in archivio, mai eliminato alla cieca
    assert any(d["id"] == "f23-noxml" for d in db["invoices"].docs)


def test_promozione_ignora_anni_diversi():
    db = _Db()
    db["corrispettivi"].docs = [
        {"id": "c24", "data": "2024-02-01", "stato_import": "archivio_storico", "totale": 500.0},
    ]

    esito = _run(mod.promuovi_archivio_anno(db, 2023))

    assert esito["corrispettivi_promossi"] == 0
    assert db["corrispettivi"].docs[0]["stato_import"] == "archivio_storico"  # intoccato
