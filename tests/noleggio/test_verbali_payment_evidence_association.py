import asyncio
from email.message import EmailMessage
from types import SimpleNamespace

from app.services import verbali_pagamento_finder as mod


class _Cursor:
    def __init__(self, docs):
        self.docs = list(docs)

    def limit(self, _value):
        return self

    async def to_list(self, value):
        return list(self.docs[:value])


class _Collection:
    def __init__(self, docs=None):
        self.docs = list(docs or [])

    def find(self, _query, _projection=None):
        return _Cursor(self.docs)

    async def find_one(self, query, _projection=None):
        alternatives = query.get("$or", [query])
        for item in self.docs:
            if any(all(item.get(key) == value for key, value in option.items())
                   for option in alternatives):
                return item
        return None

    async def update_one(self, query, update):
        item = await self.find_one(query)
        if item is None:
            return SimpleNamespace(modified_count=0)
        item.update(update.get("$set", {}))
        return SimpleNamespace(modified_count=1)


class _Db:
    def __init__(self, **collections):
        self.collections = {
            name: _Collection(docs) for name, docs in collections.items()
        }

    def __getitem__(self, name):
        return self.collections.setdefault(name, _Collection())


def _run(coro):
    return asyncio.run(coro)


def test_paypal_non_sceglie_il_primo_di_due_candidati():
    db = _Db(paypal_transactions=[
        {"transaction_id": "tx-1", "importo": -50, "transaction_subject": "A123"},
        {"transaction_id": "tx-2", "importo": -50, "transaction_subject": "A123"},
    ])

    result = _run(mod._cerca_in_paypal(db, None, "A123", None, 50))

    assert result is None


def test_paypal_deduplica_lo_stesso_candidato_trovato_da_piu_regole():
    db = _Db(paypal_transactions=[
        {"transaction_id": "tx-1", "importo": -50, "transaction_subject": "A123"},
    ])

    result = _run(mod._cerca_in_paypal(db, "012345678901234567", "A123", None, 50))

    assert result["paypal_transaction_id"] == "tx-1"
    assert result["importo"] == 50


def test_gmail_non_sceglie_il_primo_di_due_ricevute(monkeypatch, tmp_path):
    def message(message_id):
        item = EmailMessage()
        item["From"] = "partenopay@comune.napoli.it"
        item["Message-ID"] = message_id
        item.set_content(
            "Codice Avviso: 012345678901234567\n"
            "Totale: 50,00 €\n"
            "Data pagamento: 21/08/2026"
        )
        return item.as_bytes()

    messages = {b"1": message("<one@example.test>"), b"2": message("<two@example.test>")}

    class _Imap:
        def login(self, *_args):
            return "OK", []

        def select(self, *_args):
            return "OK", []

        def search(self, *_args):
            return "OK", [b"1 2"]

        def fetch(self, number, *_args):
            return "OK", [(None, messages[number])]

        def logout(self):
            return "OK", []

    monkeypatch.setattr(mod.imaplib, "IMAP4_SSL", lambda *_args: _Imap())
    monkeypatch.setattr(mod.settings, "GMAIL_EMAIL", "test@example.test")
    monkeypatch.setattr(mod.settings, "GMAIL_APP_PASSWORD", "not-a-real-secret")
    monkeypatch.setattr(mod, "UPLOAD_DIR", str(tmp_path))

    result = _run(mod._cerca_in_gmail(
        _Db(), "012345678901234567", None, 50, {"importo": 50},
    ))

    assert result is None


def test_sola_banca_non_diventa_pagamento_documentale():
    verbale = {"id": "v1", "numero_verbale": "A123", "importo": 50}
    db = _Db(verbali_noleggio=[verbale])

    applied = _run(mod.applica_pagamento_a_verbale(db, "v1", {
        "fonte": "estratto_conto",
        "importo": 50,
        "movimento_id": "mov-1",
    }))

    assert applied is True
    assert verbale["pagato_documentalmente"] is False
    assert verbale["banca_verificata"] is True
    assert verbale["stato"] == "pagato_attesa_quietanza"
    assert verbale["stato_pratica"] == "ATTESA_QUIETANZA"


def test_ricevuta_e_banca_completano_attese_separate():
    verbale = {"id": "v1", "numero_verbale": "A123", "importo": 50}
    db = _Db(verbali_noleggio=[verbale])

    assert _run(mod.applica_pagamento_a_verbale(db, "v1", {
        "fonte": "ricevuta_pagopa",
        "importo": 50,
        "ricevuta_pagopa_id": "ric-1",
    })) is True
    assert verbale["pagato_documentalmente"] is True
    assert verbale["banca_verificata"] is False
    assert verbale["stato_pratica"] == "PAGATO_DOCUMENTALE"

    assert _run(mod.applica_pagamento_a_verbale(db, "v1", {
        "fonte": "estratto_conto",
        "importo": 50,
        "movimento_id": "mov-1",
    })) is True
    assert verbale["pagato_documentalmente"] is True
    assert verbale["banca_verificata"] is True
    assert verbale["stato"] == "riconciliato"
    assert verbale["stato_pratica"] == "RICONCILIATO_BANCA"
    assert verbale["ricevuta_pagopa_id"] == "ric-1"
    assert verbale["movimento_banca_id"] == "mov-1"


def test_importo_discordante_non_modifica_il_verbale():
    verbale = {"id": "v1", "numero_verbale": "A123", "importo": 50}
    db = _Db(verbali_noleggio=[verbale])

    applied = _run(mod.applica_pagamento_a_verbale(db, "v1", {
        "fonte": "ricevuta_pagopa",
        "importo": 49.99,
        "ricevuta_pagopa_id": "ric-1",
    }))

    assert applied is False
    assert "pagato_documentalmente" not in verbale


def test_percorso_pdf_locale_senza_id_prova_non_autorizza_il_match():
    verbale = {"id": "v1", "numero_verbale": "A123", "importo": 50}
    db = _Db(verbali_noleggio=[verbale])

    applied = _run(mod.applica_pagamento_a_verbale(db, "v1", {
        "fonte": "gmail",
        "importo": 50,
        "pdf_ricevuta_path": "/tmp/ricevuta.pdf",
    }))

    assert applied is False
    assert "pagato_documentalmente" not in verbale


def test_dopo_la_ricevuta_cerca_ancora_la_banca(monkeypatch):
    calls = []

    async def fail_documentary(*_args, **_kwargs):
        raise AssertionError("La prova documentale esistente non va ricercata di nuovo")

    async def bank(*_args, **_kwargs):
        calls.append("bank")
        return {"fonte": "estratto_conto", "importo": 50, "movimento_id": "mov-1"}

    monkeypatch.setattr(mod, "_cerca_in_paypal", fail_documentary)
    monkeypatch.setattr(mod, "_cerca_in_gmail", fail_documentary)
    monkeypatch.setattr(mod, "_cerca_in_estratto_conto", bank)

    result = _run(mod.trova_pagamento_verbale(_Db(), {
        "id": "v1",
        "numero_verbale": "A123",
        "importo": 50,
        "pagato_documentalmente": True,
        "banca_verificata": False,
    }))

    assert result["movimento_id"] == "mov-1"
    assert calls == ["bank"]
