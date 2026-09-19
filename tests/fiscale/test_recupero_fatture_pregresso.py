"""Il recupero del pregresso non deve inventare, duplicare o toccare troppo.

`ripubblica_fattura_created` ripubblica `fattura.created` per le 296 fatture
attive rimaste senza partita aperta, saltando quelle storiche archiviate di
proposito.

Qui si prova cio' che puo' andare storto: toccare una fattura archiviata,
rigiocare l'evento per una fattura che la partita ce l'ha gia', riaprire
l'archivio storico che il titolare ha voluto fermo, scrivere in `dry_run`, e
portarsi dietro una scadenza che il titolare ha deciso di non avere.
"""
import asyncio

from app.services import recupero_fatture_pregresso as recupero


def _run(coroutine):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coroutine)
    finally:
        loop.close()


class _Cursore:
    def __init__(self, docs):
        self._docs = docs

    def __aiter__(self):
        async def gen():
            for doc in self._docs:
                yield dict(doc)
        return gen()


class _Collezione:
    def __init__(self, docs):
        self.docs = docs
        self.aggiornamenti = []

    def find(self, query=None, proj=None):
        query = query or {}
        if not query:
            return _Cursore(self.docs)
        return _Cursore([
            d for d in self.docs
            if all(d.get(k) == v for k, v in query.items())
        ])

    async def update_one(self, filtro, aggiornamento, **k):
        self.aggiornamenti.append((filtro, aggiornamento))
        for doc in self.docs:
            if all(doc.get(k2) == v for k2, v in filtro.items()):
                doc.update(aggiornamento["$set"])
        return None

    async def find_one(self, *a, **k):
        return None


class _Db:
    def __init__(self, fatture, partite=None):
        self.collezioni = {
            "invoices": _Collezione(fatture),
            "partite_aperte": _Collezione(partite or []),
            "sistema_stato": _Collezione([]),
        }

    def __getitem__(self, nome):
        return self.collezioni.setdefault(nome, _Collezione([]))


# ── 2. Replay di `fattura.created` ────────────────────────────────────────

SENZA_PARTITA = {
    "id": "f-orfana", "status": "imported", "invoice_number": "9/26",
    "supplier_name": "ACME SRL", "invoice_date": "2026-03-01",
    "total_amount": 1220.0, "iva": 220.0,
}
CON_PARTITA = dict(SENZA_PARTITA, id="f-con-partita")
STORICA = dict(SENZA_PARTITA, id="f-storica", stato_import="archivio_storico")


def _db_replay(fatture):
    return _Db(fatture, partite=[{
        "documento_id": "f-con-partita", "documento_collection": "invoices",
    }])


def test_rigioca_solo_le_fatture_senza_partita():
    esito = _run(recupero.ripubblica_fattura_created(
        _db_replay([dict(SENZA_PARTITA), dict(CON_PARTITA)]), dry_run=True))

    assert esito["candidate"] == 1


def test_non_riapre_l_archivio_storico():
    """`archivia_fattura_storica` non propaga l'evento per scelta del
    titolare: rigiocarlo trasformerebbe una decisione in un difetto."""
    esito = _run(recupero.ripubblica_fattura_created(
        _db_replay([dict(STORICA)]), dry_run=True))

    assert esito["candidate"] == 0


def test_non_rigioca_le_archiviate():
    esito = _run(recupero.ripubblica_fattura_created(
        _db_replay([dict(SENZA_PARTITA, id="f-a", status="archived")]), dry_run=True))

    assert esito["candidate"] == 0


def test_in_dry_run_non_propaga_nessun_evento(monkeypatch):
    propagati = []

    async def _spia(tipo, payload, db, **k):
        propagati.append(payload)
        return []

    monkeypatch.setattr("app.services.event_bus.propagate_event", _spia)

    esito = _run(recupero.ripubblica_fattura_created(
        _db_replay([dict(SENZA_PARTITA)]), dry_run=True))

    assert esito["ripubblicate"] == 1
    assert propagati == [], "dry_run ha propagato davvero l'evento"


def test_propaga_lo_stesso_payload_dell_import(monkeypatch):
    propagati = []
    moduli = []

    async def _spia(tipo, payload, db, source_module="", **k):
        propagati.append(payload)
        moduli.append(source_module)
        return []

    monkeypatch.setattr("app.services.event_bus.propagate_event", _spia)

    _run(recupero.ripubblica_fattura_created(
        _db_replay([dict(SENZA_PARTITA)]), dry_run=False))

    assert len(propagati) == 1
    evento = propagati[0]
    assert evento["fattura_id"] == "f-orfana"
    assert evento["importo_totale"] == 1220.0
    assert evento["data_documento"] == "2026-03-01"
    assert moduli == ["replay_pregresso"], (
        "L'audit deve poter distinguere un replay da una creazione vera: "
        "la riga nuova porta la data di oggi, non quella dell'import."
    )


def test_un_errore_su_una_fattura_non_ferma_le_altre(monkeypatch):
    async def _esplode(tipo, payload, db, **k):
        if payload["fattura_id"] == "f-rotta":
            raise RuntimeError("handler esploso")
        return []

    monkeypatch.setattr("app.services.event_bus.propagate_event", _esplode)

    esito = _run(recupero.ripubblica_fattura_created(
        _db_replay([dict(SENZA_PARTITA, id="f-rotta"), dict(SENZA_PARTITA)]),
        dry_run=False))

    assert esito["ripubblicate"] == 1 and esito["errori"] == 1
    assert esito["motivi_errore"] and "f-rotta" in esito["motivi_errore"][0]


def test_le_partite_si_leggono_con_un_solo_prefetch():
    """Una interrogazione per fattura, su 873 fatture, e' proibita dal §4."""
    db = _db_replay([dict(SENZA_PARTITA) for _ in range(50)])
    letture = []
    originale = db["partite_aperte"].find
    db["partite_aperte"].find = lambda *a, **k: (letture.append(1), originale(*a, **k))[1]

    _run(recupero.ripubblica_fattura_created(db, dry_run=True))

    assert len(letture) == 1


def test_il_replay_non_porta_nessuna_scadenza(monkeypatch):
    """Decisione del titolare (19/09/2026): «decido io quando pagare, non c'e'
    una data stabilita». La partita fornitore nasce senza termine, anche
    quando la fattura porta ancora la scadenza inventata dal vecchio import.
    """
    propagati = []

    async def _spia(tipo, payload, db, **k):
        propagati.append(payload)
        return []

    monkeypatch.setattr("app.services.event_bus.propagate_event", _spia)

    con_vecchia_scadenza = dict(SENZA_PARTITA, data_scadenza="2026-03-31")
    _run(recupero.ripubblica_fattura_created(
        _db_replay([con_vecchia_scadenza]), dry_run=False))

    assert propagati[0]["data_scadenza"] is None, (
        "Una scadenza sulla partita fornitore fa rinascere l'avviso "
        "FAT_DA_PAGARE_SCADUTA, che il titolare non vuole."
    )


def test_l_import_non_calcola_piu_nessuna_scadenza():
    """Controprova strutturale: niente date di scadenza dedotte dalla fattura."""
    from pathlib import Path

    sorgente = (
        Path(__file__).resolve().parents[2]
        / "app" / "routers" / "invoices" / "fatture_upload.py"
    ).read_text(encoding="utf-8")

    assert "timedelta(days=30)" not in sorgente
    assert "scadenza_sintetica" not in sorgente
    assert sorgente.count("data_scadenza = None") == 2, (
        "Entrambi i percorsi di import devono lasciare la scadenza vuota."
    )
