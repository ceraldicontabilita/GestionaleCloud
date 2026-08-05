import asyncio
import copy

from app.services.paypal_statement_import import save_parsed_statement


def _match(doc, query):
    if not query:
        return True
    if "$or" in query:
        return any(_match(doc, part) for part in query["$or"])
    return all(doc.get(key) == value for key, value in query.items())


class _Collection:
    def __init__(self, docs=None):
        self.docs = [copy.deepcopy(doc) for doc in (docs or [])]

    async def find_one(self, query, projection=None):
        found = next((doc for doc in self.docs if _match(doc, query)), None)
        if found is None:
            return None
        if not projection:
            return copy.deepcopy(found)
        if projection == {"_id": 0}:
            return {key: copy.deepcopy(value) for key, value in found.items() if key != "_id"}
        return {
            key: copy.deepcopy(value)
            for key, value in found.items()
            if key != "_id" and projection.get(key, 0)
        }

    async def update_one(self, query, update, upsert=False):
        found = next((doc for doc in self.docs if _match(doc, query)), None)
        inserted = False
        if found is None and upsert:
            found = {
                key: copy.deepcopy(value)
                for key, value in query.items()
                if not key.startswith("$")
            }
            self.docs.append(found)
            inserted = True
        if found is None:
            return
        for key, value in update.get("$set", {}).items():
            found[key] = copy.deepcopy(value)
        if inserted:
            for key, value in update.get("$setOnInsert", {}).items():
                found.setdefault(key, copy.deepcopy(value))
        for key, value in update.get("$addToSet", {}).items():
            values = found.setdefault(key, [])
            if value not in values:
                values.append(copy.deepcopy(value))

    async def insert_one(self, doc):
        self.docs.append(copy.deepcopy(doc))


class _Db:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _Collection())

    def __setitem__(self, name, collection):
        self.collections[name] = collection


def _run(coro):
    return asyncio.run(coro)


def _parsed(transaction_id="TX-PAYPAL-1", name="Fornitore dal PDF"):
    return {
        "success": True,
        "tipo_documento": "MSR",
        "account_info": {"codice_conto": "ACCOUNT-1", "email_paypal": "conto@example.test"},
        "periodo": {
            "periodo_inizio": "2026-06-01",
            "periodo_fine": "2026-06-30",
            "mese": 6,
            "anno": 2026,
        },
        "riepilogo_attivita": {"saldo_finale": 10.0},
        "transazioni": [{
            "transaction_id": transaction_id,
            "data": "2026-06-12",
            "nome_controparte": name,
            "lordo": -10.0,
            "netto": -10.0,
            "valuta": "EUR",
        }],
    }


def test_import_collega_transazione_api_esistente_e_conserva_i_suoi_dati():
    db = _Db()
    db["paypal_transactions"] = _Collection([{
        "transaction_id": "TX-PAYPAL-1",
        "source": "paypal_api",
        "nome_controparte": "Nome autorevole API",
        "importo": -10.0,
    }])

    result = _run(save_parsed_statement(
        db,
        _parsed(),
        content=b"%PDF-1.7 test-payload",
        filename="Giugno 2026 MSR.pdf",
        source="drive_paypal_statement",
        drive_file_id="drive-1",
        source_path="Paypal/Giugno 2026 MSR.pdf",
    ))

    assert result["transazioni_inserite"] == 0
    assert result["transazioni_ricollegate"] == 1
    tx = db["paypal_transactions"].docs[0]
    assert tx["source"] == "paypal_api"
    assert tx["nome_controparte"] == "Nome autorevole API"
    assert tx["statement_id"] == result["statement_id"]
    assert tx["document_id"] == result["document_id"]
    assert tx["statement_ids"] == [result["statement_id"]]
    assert tx["document_ids"] == [result["document_id"]]
    assert tx["lordo"] == -10.0

    statement = db["paypal_statements"].docs[0]
    document = db["documents_inbox"].docs[0]
    assert statement["document_id"] == document["id"]
    assert statement["transaction_ids"] == ["TX-PAYPAL-1"]
    assert document["paypal_statement_id"] == statement["id"]
    assert document["paypal_transaction_ids"] == ["TX-PAYPAL-1"]
    assert document["processed"] is True
    assert document["tipo_documento"] == "paypal_statement"


def test_reimport_stesso_pdf_e_idempotente_e_non_duplica_entita():
    db = _Db()
    args = {
        "content": b"%PDF-1.7 same-payload",
        "filename": "Giugno 2026 MSR.pdf",
        "source": "drive_paypal_statement",
        "drive_file_id": "drive-1",
        "source_path": "Paypal/Giugno 2026 MSR.pdf",
    }

    first = _run(save_parsed_statement(db, _parsed(), **args))
    second = _run(save_parsed_statement(db, _parsed(), **args))

    assert first["statement_id"] == second["statement_id"]
    assert first["document_id"] == second["document_id"]
    assert second["documento_duplicato"] is True
    assert second["statement_esistente"] is True
    assert len(db["documents_inbox"].docs) == 1
    assert len(db["paypal_statements"].docs) == 1
    assert len(db["paypal_transactions"].docs) == 1
    assert db["paypal_transactions"].docs[0]["statement_ids"] == [first["statement_id"]]


def test_transazione_senza_id_usa_chiave_stabile_e_non_si_duplica():
    db = _Db()
    parsed = _parsed(transaction_id="")

    first = _run(save_parsed_statement(db, parsed, source="paypal_import_parser"))
    second = _run(save_parsed_statement(db, parsed, source="paypal_import_parser"))

    assert first["statement_id"] == second["statement_id"]
    assert len(db["paypal_transactions"].docs) == 1
    tx = db["paypal_transactions"].docs[0]
    assert tx["source_transaction_key"].startswith("paypal_tx_")
    assert second["transazioni_ricollegate"] == 1
