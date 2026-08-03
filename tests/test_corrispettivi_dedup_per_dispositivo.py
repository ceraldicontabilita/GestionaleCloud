"""Bug segnalato dall'utente 15/07/2026 (screenshot: saldo Prima Nota
Banca sballato di decine di migliaia di euro, importi elettronico dei
corrispettivi mancanti sia in Cassa che in Banca).

Causa: CorrispettiviService.process_xml controllava i duplicati SOLO per
data ("un corrispettivo per questa data esiste già → scarta"), ignorando
id_dispositivo (la matricola del registratore telematico che ha emesso il
corrispettivo). Precisazione utente: l'attività ha UN SOLO registratore,
ma la sua matricola può cambiare nel tempo (es. al risigillo triennale
obbligatorio in occasione della verifica fiscale periodica) — senza
guardare la matricola, un corrispettivo con matricola diversa da quella
già vista sulla stessa data veniva scartato come "duplicato" invece di
essere salvato, sparendo del tutto da Prima Nota Cassa/Banca."""
import asyncio

from app.services.corrispettivi_service import CorrispettiviService


class _FakeCollection:
    def __init__(self, docs=None):
        self.docs = docs or []

    async def find_one(self, query, *a, **k):
        for d in self.docs:
            if all(d.get(k) == v for k, v in query.items() if not isinstance(v, dict)):
                # gestisce {"$ne": ...} sul campo entity_status
                ok = True
                for k2, v2 in query.items():
                    if isinstance(v2, dict) and "$ne" in v2:
                        if d.get(k2) == v2["$ne"]:
                            ok = False
                if ok:
                    return dict(d)
        return None

    async def insert_one(self, doc, *a, **k):
        self.docs.append(dict(doc))

    async def update_one(self, query, update, *a, **k):
        for d in self.docs:
            if all(d.get(k) == v for k, v in query.items()):
                d.update(update.get("$set", {}))
                return

    async def find_one_and_update(self, query, update, upsert=False):
        # Stessa identica logica di match di find_one qui sopra (inclusa la
        # gestione di {"$ne": ...}), solo consolidata in un'unica chiamata.
        for d in self.docs:
            if all(d.get(k) == v for k, v in query.items() if not isinstance(v, dict)):
                ok = True
                for k2, v2 in query.items():
                    if isinstance(v2, dict) and "$ne" in v2:
                        if d.get(k2) == v2["$ne"]:
                            ok = False
                if ok:
                    return dict(d)
        if upsert:
            self.docs.append(dict(update.get("$setOnInsert", {})))
        return None

    async def delete_many(self, query, *a, **k):
        def matches(d):
            for k2, v2 in query.items():
                if isinstance(v2, dict) and "$in" in v2:
                    if d.get(k2) not in v2["$in"]:
                        return False
                elif d.get(k2) != v2:
                    return False
            return True
        before = len(self.docs)
        self.docs = [d for d in self.docs if not matches(d)]
        return type("R", (), {"deleted_count": before - len(self.docs)})()


class _FakeDb:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _FakeCollection())

    def __setitem__(self, name, value):
        self.collections[name] = value


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


def _corr_xml(*, id_dispositivo, totale, contanti, pos):
    return f"""<?xml version="1.0"?>
    <RicevutaTelematica>
      <DataOraRilevazione>2026-07-14T20:00:00</DataOraRilevazione>
      <IdDispositivo>{id_dispositivo}</IdDispositivo>
      <ImportoTotale>{totale}</ImportoTotale>
      <Pagamento><Tipo>CONTANTI</Tipo><Importo>{contanti}</Importo></Pagamento>
      <Pagamento><Tipo>POS</Tipo><Importo>{pos}</Importo></Pagamento>
    </RicevutaTelematica>""".encode()


def test_matricole_diverse_stessa_data_non_sono_duplicati():
    # Simula il caso reale segnalato dall'utente: stesso registratore, ma
    # matricola diversa da quella già vista sulla stessa data (es. a
    # cavallo di un risigillo triennale) — non deve essere trattato come
    # un duplicato del corrispettivo già salvato.
    db = _FakeDb()
    svc = CorrispettiviService(db=db)

    xml_matricola_vecchia = _corr_xml(id_dispositivo="00011", totale="500.00", contanti="300.00", pos="200.00")
    xml_matricola_nuova = _corr_xml(id_dispositivo="00012", totale="400.00", contanti="250.00", pos="150.00")

    esito1 = _run(svc.process_xml(xml_matricola_vecchia, "matricola_vecchia.xml"))
    esito2 = _run(svc.process_xml(xml_matricola_nuova, "matricola_nuova.xml"))

    assert esito1["status"] == "created"
    assert esito2["status"] == "created", esito2  # bug: prima risultava "duplicate"

    corrispettivi = db["corrispettivi"].docs
    assert len(corrispettivi) == 2
    assert {c["id_dispositivo"] for c in corrispettivi} == {"00011", "00012"}
    assert {c["matricola_rt"] for c in corrispettivi} == {"00011", "00012"}

    # Entrambi devono aver propagato a Prima Nota (nessuno scartato).
    assert esito1["prima_nota_id"] is not None
    assert esito2["prima_nota_id"] is not None
    cassa = db["prima_nota_cassa"].docs
    entrate = [c for c in cassa if c["tipo"] == "entrata"]
    assert {round(c["importo"], 2) for c in entrate} == {500.0, 400.0}


def test_stesso_dispositivo_stessa_data_resta_duplicato():
    db = _FakeDb()
    svc = CorrispettiviService(db=db)

    xml = _corr_xml(id_dispositivo="00011", totale="500.00", contanti="300.00", pos="200.00")
    xml_ripetuto = _corr_xml(id_dispositivo="00011", totale="500.00", contanti="300.00", pos="200.00")

    esito1 = _run(svc.process_xml(xml, "cassa1.xml"))
    esito2 = _run(svc.process_xml(xml_ripetuto, "cassa1_ridownload.xml"))

    assert esito1["status"] == "created"
    assert esito2["status"] == "duplicate"
    assert len(db["corrispettivi"].docs) == 1
