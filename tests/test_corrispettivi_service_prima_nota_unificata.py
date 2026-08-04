"""Bug scoperto il 14/07/2026: CorrispettiviService._create_prima_nota_entry
(usato da drive_corrispettivi_ingest.py e da create_manual) era una TERZA
implementazione parallela e diversa della regola contabile corrispettivi
già unificata in corrispettivi_helpers.py::_create_prima_nota_movements.
Leggeva pagato_pos invece di pagato_elettronico e non creava MAI la riga
in prima_nota_banca (mai vista da Coerenza POS). Ora delega alla stessa
implementazione condivisa: questo test verifica che il fix sia effettivo."""
import asyncio
import hashlib

from mongomock_motor import AsyncMongoMockClient

from app.services.corrispettivi_service import (
    CorrispettiviService,
    get_corrispettivi_service,
)


def test_factory_supporta_database_motor_e_riusa_quello_del_job_drive():
    """Regressione produzione: AsyncIOMotorDatabase non consente __setitem__."""
    db = AsyncMongoMockClient()["corrispettivi_drive_test"]

    svc = get_corrispettivi_service(db)

    assert svc.db is db
    assert svc.corrispettivi.name == "corrispettivi"
    assert svc.cash_movements.name == "prima_nota_cassa"


def _matches(doc, query):
    if not query:
        return True
    for k, v in query.items():
        if isinstance(v, dict) and "$nin" in v:
            if doc.get(k) in v["$nin"]:
                return False
        elif isinstance(v, dict) and ("$gte" in v or "$lte" in v):
            pass  # non serve per questi test
        else:
            if doc.get(k) != v:
                return False
    return True


class _FakeCollection:
    def __init__(self, docs=None):
        self.docs = docs or []

    async def find_one(self, query, *a, **k):
        for d in self.docs:
            if _matches(d, query):
                return dict(d)
        return None

    async def insert_one(self, doc, *a, **k):
        self.docs.append(dict(doc))

    async def update_one(self, query, update, *a, **k):
        for d in self.docs:
            if _matches(d, query):
                d.update(update.get("$set", {}))
                return

    async def delete_many(self, query, *a, **k):
        self.docs = [d for d in self.docs if not _matches(d, query)]

    async def find_one_and_update(self, query, update, upsert=False):
        for d in self.docs:
            if _matches(d, query):
                return dict(d)
        if upsert:
            self.docs.append(dict(update.get("$setOnInsert", {})))
        return None

    def find(self, query=None, *a, **k):
        return _FakeCursor([d for d in self.docs if _matches(d, query or {})])


class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    async def to_list(self, n=None):
        return list(self._docs[:n] if n else self._docs)


class _FakeDb:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _FakeCollection())

    def __setitem__(self, name, value):
        self.collections[name] = value


class _MotorLikeDb(_FakeDb):
    def __bool__(self):
        raise NotImplementedError(
            "Database objects do not implement truth value testing or bool()"
        )


def test_costruttore_non_valuta_database_motor_come_booleano():
    db = _MotorLikeDb()

    svc = CorrispettiviService(db=db)

    assert svc.db is db
    assert svc.corrispettivi is db["corrispettivi"]


def test_parser_periodo_inattivo_ade_legge_data_e_matricola_reali():
    xml = b'''<?xml version="1.0" encoding="UTF-8"?>
    <n1:DatiCorrispettivi xmlns:n1="http://ivaservizi.agenziaentrate.gov.it/docs/xsd/corrispettivi/dati/v1.0" versione="COR10">
      <Trasmissione>
        <Progressivo>1354</Progressivo>
        <Dispositivo><Tipo>RT</Tipo><IdDispositivo>99MEY026532</IdDispositivo></Dispositivo>
        <DataOraTrasmissione>2023-01-02T06:27:14+01:00</DataOraTrasmissione>
      </Trasmissione>
      <PeriodoInattivo><Dal>2023-01-01T00:00:00+01:00</Dal><Al>2023-01-01T23:59:59+01:00</Al></PeriodoInattivo>
      <DataOraRilevazione>2023-01-02T06:26:37+01:00</DataOraRilevazione>
      <DatiRT><Totali><NumeroDocCommerciali>0</NumeroDocCommerciali></Totali></DatiRT>
    </n1:DatiCorrispettivi>'''

    parsed = CorrispettiviService(db=_FakeDb())._parse_corrispettivo_xml(xml)

    assert parsed["data"] == "2023-01-02"
    assert parsed["id_dispositivo"] == "99MEY026532"
    assert parsed["progressivo"] == "1354"
    assert parsed["totale"] == 0


def test_reimport_periodo_inattivo_ripara_solo_il_duplicato_storico():
    xml = b'''<?xml version="1.0" encoding="UTF-8"?>
    <n1:DatiCorrispettivi xmlns:n1="http://ivaservizi.agenziaentrate.gov.it/docs/xsd/corrispettivi/dati/v1.0" versione="COR10">
      <Trasmissione>
        <Progressivo>1354</Progressivo>
        <Dispositivo><Tipo>RT</Tipo><IdDispositivo>99MEY026532</IdDispositivo></Dispositivo>
      </Trasmissione>
      <PeriodoInattivo><Dal>2023-01-01T00:00:00+01:00</Dal><Al>2023-01-01T23:59:59+01:00</Al></PeriodoInattivo>
      <DataOraRilevazione>2023-01-02T06:26:37+01:00</DataOraRilevazione>
      <DatiRT><Totali><NumeroDocCommerciali>0</NumeroDocCommerciali></Totali></DatiRT>
    </n1:DatiCorrispettivi>'''
    db = _FakeDb()
    db["sistema_stato"].docs = [
        {"chiave": "config_import_anno_attivo", "anno": 2026}
    ]
    db["corrispettivi"].docs = [{
        "id": "corr-errato",
        "content_hash": hashlib.sha256(xml).hexdigest(),
        "data": "2026-08-03",
        "totale": 0,
        "entity_status": "active",
        "prima_nota_id": None,
    }]
    svc = CorrispettiviService(db=db)

    esito = _run(svc.process_xml(
        xml, "periodo_inattivo.xml", applica_filtro_anno=True
    ))

    assert esito["status"] == "archiviata"
    corretto = db["corrispettivi"].docs[0]
    assert corretto["data"] == "2023-01-02"
    assert corretto["id_dispositivo"] == "99MEY026532"
    assert corretto["matricola_rt"] == "99MEY026532"
    assert corretto["status"] == "archiviata"
    assert corretto["stato_import"] == "archivio_storico"


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


def test_create_prima_nota_entry_trasferimento_speculare():
    db = _FakeDb()
    svc = CorrispettiviService(db=db)
    corr = {
        "id": "corr-1", "data": "2026-07-14",
        "totale": 1000.0, "pagato_contanti": 600.0, "pagato_elettronico": 400.0,
    }

    prima_nota_id = _run(svc._create_prima_nota_entry(corr))

    assert prima_nota_id is not None
    cassa = db["prima_nota_cassa"].docs
    banca = db["prima_nota_banca"].docs
    assert len(cassa) == 2  # entrata totale + uscita POS
    assert len(banca) == 1  # REGOLA CANONICA: trasferimento speculare
    assert banca[0]["source"] == "trasferimento_pos"
    assert banca[0]["importo"] == 400.0
    entrata_cassa = next(d for d in cassa if d["tipo"] == "entrata")
    uscita_cassa = next(d for d in cassa if d["tipo"] == "uscita")
    assert entrata_cassa["importo"] == 1000.0
    assert uscita_cassa["importo"] == 400.0


def test_create_prima_nota_entry_legge_pagato_pos_come_fallback():
    # I corrispettivi da CorrispettiviService.process_xml storicamente
    # salvano "pagato_pos" (non pagato_elettronico): deve continuare a
    # funzionare come fallback, non solo con il nome campo nuovo.
    db = _FakeDb()
    svc = CorrispettiviService(db=db)
    corr = {"id": "corr-2", "data": "2026-07-14", "totale": 500.0,
            "pagato_contanti": 300.0, "pagato_pos": 200.0}

    _run(svc._create_prima_nota_entry(corr))

    uscite = [m for m in db["prima_nota_cassa"].docs if m["tipo"] == "uscita"]
    assert len(uscite) == 1 and uscite[0]["importo"] == 200.0
    banca = db["prima_nota_banca"].docs
    assert len(banca) == 1 and banca[0]["importo"] == 200.0  # trasferimento


def test_process_xml_filtro_anno_archivia_corrispettivo_storico():
    # Richiesta utente 14/07/2026: propagazione dello stesso filtro anno
    # già applicato alle fatture Drive, al canale Drive corrispettivi.
    db = _FakeDb()
    db["sistema_stato"].docs = [{"chiave": "config_import_anno_attivo", "anno": 2026}]
    svc = CorrispettiviService(db=db)
    svc._parse_corrispettivo_xml = lambda xml_content: {
        "data": "2023-05-10", "totale": 800.0,
        "pagato_contanti": 500.0, "pagato_pos": 300.0,
    }

    esito = _run(svc.process_xml(b"<x/>", "corr.xml", applica_filtro_anno=True))

    assert esito["status"] == "archiviata"
    assert esito["prima_nota_id"] is None
    doc = db["corrispettivi"].docs[0]
    assert doc["stato_import"] == "archivio_storico"
    # Un corrispettivo storico non deve MAI toccare Prima Nota.
    assert db["prima_nota_cassa"].docs == []
    assert db["prima_nota_banca"].docs == []


def test_process_xml_filtro_anno_corrente_va_al_flusso_attivo():
    db = _FakeDb()
    db["sistema_stato"].docs = [{"chiave": "config_import_anno_attivo", "anno": 2026}]
    svc = CorrispettiviService(db=db)
    svc._parse_corrispettivo_xml = lambda xml_content: {
        "data": "2026-05-10", "totale": 800.0,
        "pagato_contanti": 500.0, "pagato_pos": 300.0,
    }

    esito = _run(svc.process_xml(b"<x/>", "corr.xml", applica_filtro_anno=True))

    assert esito["status"] == "created"
    assert esito["prima_nota_id"] is not None
    assert len(db["prima_nota_banca"].docs) == 1  # trasferimento speculare


def test_reimport_duplicato_ripara_prima_nota_mancante_senza_duplicare():
    db = AsyncMongoMockClient()["corrispettivi_retry_test"]
    svc = CorrispettiviService(db=db)
    xml = b"<corrispettivo />"
    parsed = {
        "data": "2026-08-03", "totale": 100.0,
        "pagato_contanti": 60.0, "pagato_pos": 40.0,
        "id_dispositivo": "RT001", "progressivo": "1",
        "totale_iva": 9.09, "imponibile": 90.91, "riepilogo_iva": [],
    }
    svc._parse_corrispettivo_xml = lambda _content: dict(parsed)
    _run(db["corrispettivi"].insert_one({
        "id": "corr-retry", "content_hash": hashlib.sha256(xml).hexdigest(),
        "data": "2026-08-03", "totale": 100.0,
        "pagato_contanti": 60.0, "pagato_pos": 40.0,
        "id_dispositivo": "RT001", "entity_status": "active",
        "status": "imported", "prima_nota_id": None,
    }))

    first = _run(svc.process_xml(xml, "retry.xml"))
    second = _run(svc.process_xml(xml, "retry.xml"))

    assert first["status"] == second["status"] == "duplicate"
    assert first["repaired_accounting"] is True
    assert _run(db["prima_nota_cassa"].count_documents({})) == 2
    assert _run(db["prima_nota_banca"].count_documents({})) == 1
    saved = _run(db["corrispettivi"].find_one({"id": "corr-retry"}))
    assert saved["prima_nota_id"]


def _parsed_corr(*, data, ora, totale, contanti, pos, progressivo, docs=1):
    return {
        "data": data,
        "data_ora_rilevazione": f"{data}T{ora}+02:00",
        "data_ora_trasmissione": f"{data}T{ora}+02:00",
        "totale": totale,
        "pagato_contanti": contanti,
        "pagato_pos": pos,
        "id_dispositivo": "99MEY026532",
        "progressivo": progressivo,
        "numero_documenti": docs,
        "totale_iva": round(totale / 11, 2),
        "imponibile": round(totale - (totale / 11), 2),
        "non_riscosso": 0,
        "riepilogo_iva": [],
    }


def test_xml_distinti_stessa_giornata_vengono_sommati_ma_retry_no():
    db = AsyncMongoMockClient()["corrispettivi_multi_close_test"]
    svc = CorrispettiviService(db=db)
    parsed = {
        b"chiusura-1": _parsed_corr(
            data="2026-05-19", ora="20:33:34", totale=3104.40,
            contanti=1077.30, pos=2027.10, progressivo="2534", docs=522,
        ),
        b"chiusura-2": _parsed_corr(
            data="2026-05-19", ora="21:34:50", totale=133.00,
            contanti=0, pos=133.00, progressivo="2535", docs=6,
        ),
    }
    svc._parse_corrispettivo_xml = lambda content: dict(parsed[content])

    first = _run(svc.process_xml(b"chiusura-1", "2534.xml"))
    second = _run(svc.process_xml(b"chiusura-2", "2535.xml"))
    retry = _run(svc.process_xml(b"chiusura-2", "2535-copia.xml"))

    assert first["status"] == "created"
    assert second["status"] == "aggregated"
    assert retry["status"] == "duplicate"
    assert _run(db["corrispettivi"].count_documents({})) == 1
    saved = _run(db["corrispettivi"].find_one({"data": "2026-05-19"}))
    assert saved["chiusure_sommate"] == 2
    assert len(saved["source_hashes"]) == 2
    assert saved["totale"] == 3237.40
    assert saved["pagato_contanti"] == 1077.30
    assert saved["pagato_pos"] == saved["pagato_elettronico"] == 2160.10
    assert saved["numero_documenti"] == 528


def test_chiusura_post_mezzanotte_va_al_giorno_precedente_se_vuoto():
    db = AsyncMongoMockClient()["corrispettivi_after_midnight_test"]
    svc = CorrispettiviService(db=db)
    parsed = {
        b"notte": _parsed_corr(
            data="2026-04-04", ora="00:32:52", totale=4083.60,
            contanti=1104.60, pos=2979.00, progressivo="2488", docs=575,
        ),
        b"sera": _parsed_corr(
            data="2026-04-04", ora="21:37:38", totale=4699.10,
            contanti=1065.80, pos=3633.30, progressivo="2489", docs=593,
        ),
    }
    svc._parse_corrispettivo_xml = lambda content: dict(parsed[content])

    night = _run(svc.process_xml(b"notte", "2488.xml"))
    evening = _run(svc.process_xml(b"sera", "2489.xml"))

    assert night["status"] == evening["status"] == "created"
    previous = _run(db["corrispettivi"].find_one({"data": "2026-04-03"}))
    current = _run(db["corrispettivi"].find_one({"data": "2026-04-04"}))
    assert previous["totale"] == 4083.60
    assert previous["data_rilevazione_xml"] == "2026-04-04"
    assert previous["chiusura_post_mezzanotte"] is True
    assert current["totale"] == 4699.10


def test_chiusura_post_mezzanotte_non_sposta_se_precedente_valorizzato():
    db = AsyncMongoMockClient()["corrispettivi_after_midnight_valued_test"]
    svc = CorrispettiviService(db=db)
    parsed = {
        b"precedente": _parsed_corr(
            data="2026-04-03", ora="21:00:00", totale=100.00,
            contanti=50.00, pos=50.00, progressivo="2487", docs=10,
        ),
        b"notte": _parsed_corr(
            data="2026-04-04", ora="00:32:52", totale=20.00,
            contanti=10.00, pos=10.00, progressivo="2488", docs=2,
        ),
    }
    svc._parse_corrispettivo_xml = lambda content: dict(parsed[content])

    _run(svc.process_xml(b"precedente", "2487.xml"))
    _run(svc.process_xml(b"notte", "2488.xml"))

    previous = _run(db["corrispettivi"].find_one({"data": "2026-04-03"}))
    current = _run(db["corrispettivi"].find_one({"data": "2026-04-04"}))
    assert previous["totale"] == 100.00
    assert current["totale"] == 20.00
    assert current["chiusura_post_mezzanotte"] is False


def test_retry_post_mezzanotte_ignora_precedente_archiviato_e_ripara_data():
    db = AsyncMongoMockClient()["corrispettivi_after_midnight_archived_test"]
    svc = CorrispettiviService(db=db)
    parsed = {
        b"precedente": _parsed_corr(
            data="2026-04-03", ora="21:00:00", totale=100.00,
            contanti=50.00, pos=50.00, progressivo="2487", docs=10,
        ),
        b"notte": _parsed_corr(
            data="2026-04-04", ora="00:32:52", totale=4083.60,
            contanti=1104.60, pos=2979.00, progressivo="2488", docs=575,
        ),
    }
    svc._parse_corrispettivo_xml = lambda content: dict(parsed[content])

    _run(svc.process_xml(b"precedente", "2487.xml"))
    first_night = _run(svc.process_xml(b"notte", "2488.xml"))
    night_id = first_night["corrispettivo_id"]
    assert _run(db["corrispettivi"].find_one({"id": night_id}))["data"] == "2026-04-04"

    _run(db["corrispettivi"].update_one(
        {"data": "2026-04-03"},
        {"$set": {"status": "archived"}},
    ))
    retry = _run(svc.process_xml(b"notte", "2488-copia.xml"))

    assert retry["status"] == "duplicate"
    repaired = _run(db["corrispettivi"].find_one({"id": night_id}))
    assert repaired["data"] == "2026-04-03"
    assert repaired["data_rilevazione_xml"] == "2026-04-04"
    assert repaired["chiusura_post_mezzanotte"] is True
