"""Il recupero del pregresso non deve inventare, duplicare o toccare troppo.

Due riparazioni sulle fatture gia' in archivio (19/09/2026):

1. `ricalcola_scadenze` riporta `data_scadenza` alla scadenza dichiarata
   nelle `pagamento_rate` conservate sulla fattura. In produzione riguarda
   414 fatture del canale Drive.
2. `ripubblica_fattura_created` ripubblica l'evento per le 296 fatture
   attive rimaste senza partita aperta, saltando quelle storiche archiviate
   di proposito.

Qui si prova cio' che puo' andare storto: toccare una fattura archiviata,
rigiocare l'evento per una fattura che la partita ce l'ha gia', riaprire
l'archivio storico che il titolare ha voluto fermo, e scrivere in `dry_run`.
"""
import asyncio

import pytest

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


ATTIVA_SCADENZA_SBAGLIATA = {
    "id": "f-1", "status": "imported", "invoice_number": "1/26",
    "supplier_name": "ACME SRL", "invoice_date": "2026-03-01",
    "data_scadenza": "2026-03-31",           # il ripiego +30
    "pagamento_rate": [{"data_scadenza": "2026-06-30"}],   # la scadenza vera
}
ARCHIVIATA = {
    "id": "f-arch", "status": "archived", "invoice_date": "2026-03-01",
    "data_scadenza": "2026-03-31",
    "pagamento_rate": [{"data_scadenza": "2026-06-30"}],
}
ARCHIVIATA_ITALIANO = dict(ARCHIVIATA, id="f-arch-it", status="archiviata")
GIA_CORRETTA = {
    "id": "f-ok", "status": "imported", "invoice_date": "2026-03-01",
    "data_scadenza": "2026-06-30",
    "pagamento_rate": [{"data_scadenza": "2026-06-30"}],
}


# ── 1. Ricalcolo delle scadenze ────────────────────────────────────────────

def test_la_scadenza_torna_quella_dell_xml():
    db = _Db([dict(ATTIVA_SCADENZA_SBAGLIATA)])

    esito = _run(recupero.ricalcola_scadenze(db, dry_run=False))

    assert esito["corrette"] == 1
    assert db["invoices"].docs[0]["data_scadenza"] == "2026-06-30"


def test_in_dry_run_non_si_scrive_niente():
    db = _Db([dict(ATTIVA_SCADENZA_SBAGLIATA)])

    esito = _run(recupero.ricalcola_scadenze(db, dry_run=True))

    assert esito["corrette"] == 1
    assert db["invoices"].aggiornamenti == []
    assert db["invoices"].docs[0]["data_scadenza"] == "2026-03-31"


@pytest.mark.parametrize("archiviata", [ARCHIVIATA, ARCHIVIATA_ITALIANO])
def test_le_archiviate_non_si_toccano(archiviata):
    """In archivio convivono «archived» e «archiviata»: valgono uguale."""
    db = _Db([dict(archiviata)])

    esito = _run(recupero.ricalcola_scadenze(db, dry_run=False))

    assert esito["esaminate"] == 0 and esito["corrette"] == 0
    assert db["invoices"].aggiornamenti == []


def test_una_scadenza_gia_giusta_resta_invariata():
    esito = _run(recupero.ricalcola_scadenze(_Db([dict(GIA_CORRETTA)]), dry_run=False))
    assert esito["invariate"] == 1 and esito["corrette"] == 0


def test_senza_data_e_senza_rate_non_si_inventa_una_scadenza():
    db = _Db([{"id": "f-x", "status": "imported"}])

    esito = _run(recupero.ricalcola_scadenze(db, dry_run=False))

    assert esito["senza_scadenza_determinabile"] == 1
    assert db["invoices"].aggiornamenti == []


def test_il_verso_dello_scostamento_e_quello_giusto():
    """Salvata PRIMA di quella vera = la fattura risultava scaduta in
    anticipo. E' il caso delle 390 misurate in produzione."""
    esito = _run(recupero.ricalcola_scadenze(
        _Db([dict(ATTIVA_SCADENZA_SBAGLIATA)]), dry_run=True))

    assert esito["di_cui_erano_anticipate"] == 1
    assert esito["di_cui_erano_posticipate"] == 0


def test_lo_scostamento_opposto_si_conta_a_parte():
    fattura = dict(ATTIVA_SCADENZA_SBAGLIATA, data_scadenza="2026-08-31")
    esito = _run(recupero.ricalcola_scadenze(_Db([fattura]), dry_run=True))

    assert esito["di_cui_erano_posticipate"] == 1
    assert esito["di_cui_erano_anticipate"] == 0


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
    # La scadenza non c'era sulla fattura: si ricava come all'import.
    assert evento["data_scadenza"] == "2026-03-31"
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
