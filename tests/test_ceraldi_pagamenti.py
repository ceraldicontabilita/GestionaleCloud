"""Pagamenti sul ledger reale, senza avviare API, credenziali o servizi esterni."""
import ast
import importlib
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]


# Evita gli initializer che avviano scheduler/autenticazione. I motori di
# dominio e il ledger vengono importati dai loro file reali, senza sostituirli.
for package in ("app", "app.services", "app.utils", "app.routers", "app.routers.prima_nota_module"):
    if package not in sys.modules:
        module = ModuleType(package)
        module.__path__ = [str(ROOT / package.replace(".", "/"))]
        sys.modules[package] = module


class ServiceHTTPException(Exception):
    def __init__(self, status_code, detail):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


if "fastapi" not in sys.modules:
    try:
        importlib.import_module("fastapi")
    except ModuleNotFoundError:
        module = ModuleType("fastapi")
        module.HTTPException = ServiceHTTPException
        sys.modules["fastapi"] = module


def isolated_functions(name, path, functions, assignments=(), imports=()):
    """Compila i corpi originali; esclude soltanto startup/router e modelli HTTP."""
    source = ROOT / path
    nodes = ast.parse(source.read_text()).body
    body = [ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)]
    for node in nodes:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in functions:
            body.append(node)
        elif isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id in assignments for target in node.targets):
            body.append(node)
        elif isinstance(node, ast.Import):
            body.append(node)
        elif isinstance(node, ast.ImportFrom) and node.module in imports:
            body.append(node)
    module = ModuleType(name)
    sys.modules[name] = module
    exec(compile(ast.fix_missing_locations(ast.Module(body=body, type_ignores=[])), str(source), "exec"), module.__dict__)
    return module


isolated_functions(
    "app.routers.prima_nota_module.sync", "app/routers/prima_nota_module/sync.py",
    {"_normalizza_piva", "determina_tipo_movimento_fattura", "costruisci_campi_movimento_fattura"},
    {"PIVA_AZIENDA", "TIPI_FATTURA_ATTIVA"}, {"typing", "app.constants.tipi_documento"},
)
isolated_functions(
    "app.services.riconciliazione_bancaria", "app/services/riconciliazione_bancaria.py",
    {"classifica_strumento_bancario", "extract_assegno_number"}, imports={"typing"},
)
payments = isolated_functions(
    "ceraldi_test_invoice_payments", "app/services/invoice_payments.py",
    {node.name for node in ast.parse((ROOT / "app/services/invoice_payments.py").read_text()).body
     if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))},
    {"COL_SCADENZIARIO", "COL_FATTURE_RICEVUTE"},
    {"datetime", "typing", "fastapi", "app.services.archivio_documenti_memoria",
     "app.services.scritture_contabili", "app.services.prima_nota_integrity", "app.utils.id_fattura",
     "app.services.stato_pagamento_fattura", "app.constants.fattura_attiva"},
)
memory = importlib.import_module("app.services.archivio_documenti_memoria")
engine = importlib.import_module("app.services.bank_payment_allocations")
HTTPException = sys.modules["fastapi"].HTTPException


def request(**fields):
    return SimpleNamespace(**{
        "fattura_id": "fattura-001", "scadenza_id": None, "importo": 100.0,
        "metodo": "banca", "data_pagamento": "2026-10-08", "fornitore": "Alfa SRL",
        "numero_fattura": "ALFA-2026-000001", "idempotency_key": None, **fields,
    })

class ManualPaymentTests(unittest.IsolatedAsyncioTestCase):
    async def seed(self, **invoice_fields):
        db = memory.ArchivioDocumenti()
        await db["invoices"].insert_one({
            "id": "fattura-001", "invoice_number": "ALFA-2026-000001",
            "supplier_name": "Alfa SRL", "supplier_vat": "00123456789",
            "tipo_documento": "TD01", "total_amount": 100.0,
            "importo_pagato": 0.0, "importo_residuo": 100.0, "pagato": False,
            "payment_status": "unpaid", **invoice_fields,
        })
        await db["scadenziario_fornitori"].insert_one({
            "id": "rata-001", "fattura_id": "fattura-001", "importo_rata": 100.0,
            "importo_pagato": 0.0, "importo_residuo": 100.0, "pagato": False,
            "stato": "da_pagare", "data_scadenza": "2026-10-08",
        })
        return db

    async def bank_evidence(self, db, **fields):
        await db["estratto_conto_movimenti"].insert_one({
            "id": "EC-001", "data": "2026-10-09", "tipo": "uscita", "importo": -100.0,
            "descrizione": "Bonifico Alfa SRL fattura ALFA-2026-000001",
            "livello_evidenza": "ufficiale", "evidenza_bancaria_ufficiale": True,
            "riconciliato": False, **fields,
        })

    async def test_bank_declaration_is_pending_idempotent_and_changes_no_paid_fields(self):
        db = await self.seed()
        before_invoice = await db["invoices"].find_one({"id": "fattura-001"})
        before_due = await db["scadenziario_fornitori"].find_one({"id": "rata-001"})
        req = request(scadenza_id="rata-001")
        result = await payments.register_manual_invoice_payment(db, req)
        replay = await payments.register_manual_invoice_payment(db, req)
        self.assertEqual(result["stato"], "DA_VERIFICARE")
        self.assertFalse(result["pagamento_confermato"])
        self.assertTrue(result["in_attesa_estratto_ufficiale"])
        self.assertTrue(replay["idempotent_replay"])
        self.assertEqual(result["movimento_id"], replay["movimento_id"])
        self.assertEqual(await db["prima_nota_banca"].count_documents({}), 1)
        invoice = await db["invoices"].find_one({"id": "fattura-001"})
        for field in ("pagato", "payment_status", "importo_pagato", "importo_residuo"):
            self.assertEqual(invoice[field], before_invoice[field])
        self.assertNotIn("data_pagamento", invoice)
        self.assertEqual(await db["scadenziario_fornitori"].find_one({"id": "rata-001"}), before_due)
        row = await db["prima_nota_banca"].find_one({"id": result["movimento_id"]})
        self.assertEqual(row["stato"], "DA_VERIFICARE")
        self.assertTrue(row["dichiarato_titolare"])
        self.assertTrue(row["provvisorio"])

    async def test_official_reconciliation_absorbs_declaration_once_and_updates_rates_relations(self):
        db = await self.seed()
        proposal = await payments.register_manual_invoice_payment(db, request(scadenza_id="rata-001"))
        await self.bank_evidence(db)
        req = SimpleNamespace(fattura_id="fattura-001", movimento_id="EC-001", override_reason=None)
        with patch.object(engine, "_propaga_fattura_pagata", new=AsyncMock()) as events:
            first = await payments.reconcile_invoice_bank_movement(db, req)
            second = await payments.reconcile_invoice_bank_movement(db, req)
            self.assertTrue(first["success"])
            self.assertTrue(second["idempotent_replay"])
            self.assertEqual(events.await_count, 1)
        invoice = await db["invoices"].find_one({"id": "fattura-001"})
        self.assertTrue(invoice["pagato"])
        self.assertEqual(invoice["importo_pagato"], 100.0)
        self.assertEqual(invoice["importo_residuo"], 0.0)
        self.assertFalse(invoice["in_attesa_riscontro_banca"])
        due = await db["scadenziario_fornitori"].find_one({"id": "rata-001"})
        self.assertTrue(due["pagato"])
        self.assertEqual(due["importo_pagato"], 100.0)
        self.assertEqual(await db["bank_payment_allocations"].count_documents({}), 1)
        self.assertGreater(await db["entity_relations"].count_documents({}), 0)
        old = await db["prima_nota_banca"].find_one({"id": proposal["movimento_id"]})
        self.assertEqual(old["status"], "deleted")
        active = await db["prima_nota_banca"].find({"status": {"$nin": ["deleted", "archived"]}}).to_list(10)
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["estratto_conto_id"], "EC-001")
        self.assertTrue(active[0]["riconciliato"])

    async def test_conflicting_declaration_does_not_create_a_second_operation_or_movement(self):
        db = await self.seed()
        first = await payments.register_manual_invoice_payment(db, request())
        repeated = await payments.register_manual_invoice_payment(db, request(idempotency_key="different-browser-click"))
        self.assertEqual(first["movimento_id"], repeated["movimento_id"])
        count = await db["pagamenti_operazioni"].count_documents({})
        with self.assertRaises(HTTPException) as raised:
            await payments.register_manual_invoice_payment(
                db, request(importo=50.0, idempotency_key="different-amount-key"),
            )
        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(await db["pagamenti_operazioni"].count_documents({}), count)
        self.assertEqual(await db["prima_nota_banca"].count_documents({}), 1)

    async def test_partial_cash_then_bank_keeps_total_paid_and_numeric_invoice_identity(self):
        db = await self.seed()
        await db["invoices"].update_one({"id": "fattura-001"}, {"$set": {"id": 17000001}})
        await db["scadenziario_fornitori"].update_one({"id": "rata-001"}, {"$set": {"fattura_id": 17000001}})
        await payments.register_manual_invoice_payment(db, request(
            fattura_id="17000001", metodo="cassa", importo=40.0, idempotency_key="cash-partial-stable",
        ))
        await payments.register_manual_invoice_payment(db, request(
            fattura_id="17000001", importo=60.0, idempotency_key="bank-partial-stable",
        ))
        invoice = await db["invoices"].find_one({"id": 17000001})
        self.assertEqual(invoice["importo_pagato"], 40.0)
        self.assertEqual(invoice["importo_residuo"], 60.0)
        await self.bank_evidence(db, importo=-60.0)
        req = SimpleNamespace(fattura_id="17000001", movimento_id="EC-001", override_reason=None)
        with patch.object(engine, "_propaga_fattura_pagata", new=AsyncMock()):
            await payments.reconcile_invoice_bank_movement(db, req)
        invoice = await db["invoices"].find_one({"id": 17000001})
        self.assertEqual(invoice["id"], 17000001)
        self.assertEqual(invoice["importo_pagato"], 100.0)
        self.assertEqual(invoice["importo_residuo"], 0.0)
        self.assertTrue(invoice["pagato"])
        self.assertEqual(await db["prima_nota_banca"].count_documents({"status": {"$nin": ["deleted", "archived"]}}), 1)

    async def test_incoming_provisional_quarantined_and_incompatible_bank_evidence_are_rejected(self):
        for fields in (
            {"tipo": "entrata", "importo": 100.0},
            {"livello_evidenza": "provvisoria", "evidenza_bancaria_ufficiale": False},
            {"in_attesa_estratto_ufficiale": True}, {"in_quarantena": True},
            {"provvisorio": True}, {"status": "deleted"}, {"beneficiario": "Beta Trasporti SRL"},
        ):
            with self.subTest(fields=fields):
                db = await self.seed()
                await self.bank_evidence(db, **fields)
                req = SimpleNamespace(fattura_id="fattura-001", movimento_id="EC-001",
                                      override_reason="Conferma esplicita del titolare")
                with self.assertRaises(HTTPException) as raised:
                    await payments.reconcile_invoice_bank_movement(db, req)
                self.assertEqual(raised.exception.status_code, 409)
                self.assertFalse((await db["invoices"].find_one({"id": "fattura-001"}))["pagato"])
                self.assertEqual(await db["bank_payment_allocations"].count_documents({}), 0)
                self.assertEqual(await db["prima_nota_banca"].count_documents({}), 0)

    async def test_cash_payment_still_closes_invoice_and_rate_once(self):
        db = await self.seed()
        req = request(metodo="cassa", scadenza_id="rata-001")
        first = await payments.register_manual_invoice_payment(db, req)
        second = await payments.register_manual_invoice_payment(db, req)
        self.assertTrue(first["pagamento_confermato"])
        self.assertFalse(first["in_attesa_estratto_ufficiale"])
        self.assertEqual(first["stato"], "confermato")
        self.assertTrue(second["idempotent_replay"])
        invoice = await db["invoices"].find_one({"id": "fattura-001"})
        self.assertTrue(invoice["pagato"])
        self.assertEqual(invoice["importo_pagato"], 100.0)
        self.assertTrue((await db["scadenziario_fornitori"].find_one({"id": "rata-001"}))["pagato"])
        self.assertEqual(await db["prima_nota_cassa"].count_documents({}), 1)
        self.assertEqual(await db["prima_nota_banca"].count_documents({}), 0)

    async def test_paid_or_inactive_invoice_creates_no_bank_declaration(self):
        for fields in ({"stato": "pagata"}, {"paid": True}, {"stato": "annullata"}, {"status": "archived"}):
            with self.subTest(fields=fields):
                db = await self.seed(**fields)
                with self.assertRaises(HTTPException) as raised:
                    await payments.register_manual_invoice_payment(db, request())
                self.assertEqual(raised.exception.status_code, 409)
                self.assertEqual(await db["prima_nota_banca"].count_documents({}), 0)
                self.assertEqual(await db["pagamenti_operazioni"].count_documents({}), 0)

    async def test_missing_invoice_number_requires_auditable_override_even_with_official_bank(self):
        db = await self.seed()
        await self.bank_evidence(db, descrizione="Bonifico Alfa SRL per fornitura")
        req = SimpleNamespace(fattura_id="fattura-001", movimento_id="EC-001", override_reason=None)
        with self.assertRaises(HTTPException) as raised:
            await payments.reconcile_invoice_bank_movement(db, req)
        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(await db["bank_payment_allocations"].count_documents({}), 0)
        req.override_reason = "Conferma del titolare: distinta riferita a fattura ALFA-2026-000001"
        with patch.object(engine, "_propaga_fattura_pagata", new=AsyncMock()):
            await payments.reconcile_invoice_bank_movement(db, req)
        audit = await db["audit_riconciliazioni"].find_one({"fattura_id": "fattura-001"})
        self.assertEqual(audit["override_reason"], req.override_reason)
        self.assertFalse(audit["numero_in_causale"])


if __name__ == "__main__":
    unittest.main()
