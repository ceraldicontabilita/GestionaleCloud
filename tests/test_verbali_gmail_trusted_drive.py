import asyncio
from email.message import EmailMessage

from mongomock_motor import AsyncMongoMockClient

from app.services import mittenti
from app.services import verbali_gmail_scanner as scanner


def _message(from_value: str, subject: str = "Verbale n. 123") -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = from_value
    msg["Subject"] = subject
    msg["Date"] = "Wed, 05 Aug 2026 10:00:00 +0200"
    msg.set_content("Numero verbale: A1234567890 del 05/08/2026")
    return msg


def test_parse_richiede_mittente_attendibile_anche_con_keyword():
    msg = _message("sconosciuto@example.com", "Verbale e sanzione amministrativa")
    assert scanner._parse_email_verbale(msg, {"notifica.pl.napoli@pec.it"}) is None


def test_parse_accetta_mittente_originale_nell_involucro_pec():
    msg = _message(
        '"Per conto di: notifica.pl.napoli@pec.it" posta-certificata@pec.aruba.it'
    )
    parsed = scanner._parse_email_verbale(msg, {"notifica.pl.napoli@pec.it"})
    assert parsed is not None


def test_trasportatore_aruba_non_e_un_mittente_builtin():
    patterns = {item["pattern"] for item in mittenti.BUILTIN_MITTENTI}
    assert "posta-certificata@pec.aruba.it" not in patterns
    assert "notifica.pl.napoli@pec.it" in patterns
    assert "asianapoli.protocollo@pec.it" in patterns


class _Result:
    def __init__(self, inserted):
        self.upserted_id = "new" if inserted else None


class _Collection:
    def __init__(self):
        self.docs = {}

    async def update_one(self, query, update, upsert=False):
        key = (query["pattern"], query["canale"])
        inserted = key not in self.docs
        if inserted:
            self.docs[key] = dict(update["$setOnInsert"])
        return _Result(inserted)


class _Db:
    def __init__(self):
        self.collection = _Collection()

    def __getitem__(self, name):
        assert name == "mittenti_email"
        return self.collection


def test_builtin_idempotenti_e_non_sovrascrivono():
    db = _Db()
    first = asyncio.run(mittenti.assicura_mittenti_builtin(db))
    first_doc = next(iter(db.collection.docs.values()))
    first_doc["attivo"] = False
    second = asyncio.run(mittenti.assicura_mittenti_builtin(db))
    assert first["inseriti"] == len(mittenti.BUILTIN_MITTENTI)
    assert second["inseriti"] == 0
    assert first_doc["attivo"] is False


def test_preparser_non_crea_verbale_anonimo_senza_identita():
    db = AsyncMongoMockClient()["verbali-test"]
    result = asyncio.run(scanner._upsert_verbale(db, {
        "data_ricezione_notifica": "2026-05-14T09:12:30+02:00",
        "email_subject": "POSTA CERTIFICATA: notifica con allegato",
    }))

    assert result == "ignored"
    assert asyncio.run(db["verbali_noleggio"].count_documents({})) == 0
