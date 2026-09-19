"""Fase 2 — un solo event bus, e la cessazione revoca davvero il PIN.

Fino al 19/09/2026 convivevano tre bus. Quello HR
(`app/hr/services/event_bus.py`) aveva 20 registrazioni di handler dentro
`register_all_handlers()`, ma quella funzione **non veniva chiamata da
nessuna parte**: non da `app/hr/main.py`, non altrove, non all'import. Il suo
registro restava vuoto, quindi ogni `propagate_event` scritto nel codice HR
non raggiungeva alcun handler. Il terzo bus (`app/hr/core/event_bus.py`) non
aveva nemmeno una registrazione scritta.

Il danno concreto non era teorico: due strade di cessazione in
`app/hr/routers/employees/dipendenti.py` — la spunta «non in carico» nel PUT
e il DELETE — non revocano il PIN da sole e si affidano all'handler
`on_dipendente_cessato`, che stava su quel bus morto. CLAUDE.md impone che la
cessazione revochi il PIN e che un cessato non ne abbia mai uno valido.
"""
import asyncio

import pytest


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ──────────────────────────────────────────────────────────────────────
# Un solo bus
# ──────────────────────────────────────────────────────────────────────

def test_il_bus_hr_e_lo_stesso_oggetto_del_bus_erp():
    """Non due registri che si ignorano: lo stesso identico registro."""
    from app.hr.services import event_bus as bus_hr
    from app.services import event_bus as bus_erp

    assert bus_hr.propagate_event is bus_erp.propagate_event
    assert bus_hr.register_handler is bus_erp.register_handler
    assert bus_hr.EventTypes is bus_erp.EventTypes


def test_il_terzo_bus_non_esiste_piu():
    with pytest.raises(ImportError):
        import app.hr.core.event_bus  # noqa: F401


def test_un_handler_registrato_riceve_gli_eventi_pubblicati_dal_codice_hr():
    """Il difetto in una riga: prima questo non succedeva mai.

    Il publisher e' quello che usa il codice HR, l'handler e' registrato sul
    bus canonico. Con i due registri separati l'handler non veniva mai
    chiamato.
    """
    from app.hr.services.event_bus import propagate_event as publish_hr
    from app.services.event_bus import EventTypes, register_handler, _handlers

    ricevuti = []

    async def _spia(event, db):
        ricevuti.append(event)
        return {"ok": True}

    register_handler(EventTypes.DIPENDENTE_CESSATO, _spia)
    try:
        _run(publish_hr(
            EventTypes.DIPENDENTE_CESSATO,
            {"dipendente_id": "ZZZ-TEST", "nome_completo": "ZZZ TEST"},
            None,
            source_module="test",
        ))
        assert [e["dipendente_id"] for e in ricevuti] == ["ZZZ-TEST"]
    finally:
        _handlers[EventTypes.DIPENDENTE_CESSATO].remove(_spia)


# ──────────────────────────────────────────────────────────────────────
# La cessazione revoca il PIN
# ──────────────────────────────────────────────────────────────────────

class _Coll:
    def __init__(self, docs=None):
        self.docs = docs or []
        self.aggiornati = []

    async def update_many(self, query, update):
        self.aggiornati.append((query, update))

        class _R:
            modified_count = 1
        return _R()

    async def find_one(self, *a, **k):
        return None

    async def count_documents(self, *a, **k):
        return 0

    def find(self, *a, **k):
        class _C:
            def __aiter__(self_inner):
                async def _gen():
                    for d in []:
                        yield d
                return _gen()

            async def to_list(self_inner, n):
                return []
        return _C()

    async def insert_one(self, doc):
        self.docs.append(doc)


class _Db:
    def __init__(self):
        self.colls = {}

    def __getitem__(self, nome):
        return self.colls.setdefault(nome, _Coll())


def test_cessazione_revoca_il_pin_e_chiude_i_contratti(monkeypatch):
    """CLAUDE.md, «Personale»: «la cessazione revoca il PIN», «mai un cessato».

    Prima della Fase 2 la revoca viveva solo nella copia HR dell'handler, su
    un bus mai collegato: il PIN restava attivo per chi veniva cessato dalla
    spunta «non in carico» o dal DELETE.
    """
    from app.services.handlers import dipendente_handlers as h

    revocati = []

    async def _rimuovi_pin(dip_id):
        revocati.append(dip_id)
        return True

    import app.hr.services.auth_dipendenti as auth
    monkeypatch.setattr(auth, "rimuovi_pin", _rimuovi_pin)

    async def _noop_alert(*a, **k):
        return None

    async def _noop_log(*a, **k):
        return None

    import app.services.alert_engine as alert_engine
    import app.services.audit_logger as audit_logger
    monkeypatch.setattr(alert_engine, "genera_alert", _noop_alert)
    monkeypatch.setattr(audit_logger, "log_evento", _noop_log)

    db = _Db()
    esito = _run(h.on_dipendente_cessato(
        {"dipendente_id": "DIP-1", "nome_completo": "ZZZ TEST",
         "data_cessazione": "2026-09-30"},
        db,
    ))

    assert revocati == ["DIP-1"], "il PIN del cessato non e' stato revocato"
    assert esito["azioni"]["pin_revocato"] is True
    assert esito["azioni"]["contratti_terminati"] == 1

    query_contratti = db["employee_contracts"].aggiornati[0][0]
    assert query_contratti["dipendente_id"] == "DIP-1"
    set_contratti = db["employee_contracts"].aggiornati[0][1]["$set"]
    assert set_contratti["data_fine"] == "2026-09-30"
    assert set_contratti["stato"] == "terminato"


def test_un_errore_nella_revoca_non_ferma_il_resto_della_chiusura(monkeypatch):
    """La revoca e' il primo passo: se fallisce non deve impedire la chiusura
    di contratti, richieste e partite — altrimenti un dipendente resterebbe
    mezzo cessato."""
    from app.services.handlers import dipendente_handlers as h

    async def _esplode(dip_id):
        raise RuntimeError("servizio PIN non raggiungibile")

    import app.hr.services.auth_dipendenti as auth
    monkeypatch.setattr(auth, "rimuovi_pin", _esplode)

    async def _noop(*a, **k):
        return None

    import app.services.alert_engine as alert_engine
    import app.services.audit_logger as audit_logger
    monkeypatch.setattr(alert_engine, "genera_alert", _noop)
    monkeypatch.setattr(audit_logger, "log_evento", _noop)

    db = _Db()
    esito = _run(h.on_dipendente_cessato(
        {"dipendente_id": "DIP-2", "nome_completo": "ZZZ TEST 2"}, db,
    ))

    assert esito["azioni"]["pin_revocato"] is False
    assert esito["azioni"]["contratti_terminati"] == 1
