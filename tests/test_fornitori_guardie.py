"""
Guardie anti-fornitori-fantasma in ensure_supplier_exists (fatture_upload).

Caso reale segnalato dall'utente (10/07): in anagrafica comparivano
"Ceraldi Group srl" (l'azienda stessa, cioè il cessionario) con P.IVA di
terzi o addirittura un codice fiscale personale nel campo partita_iva.
"""
import asyncio

from app.routers.invoices.fatture_upload import (
    _norm_nome_azienda,
    _piva_plausibile,
    ensure_supplier_exists,
)


# ── helper puri ──────────────────────────────────────────────────────────

def test_norm_nome_azienda_varianti_srl():
    assert _norm_nome_azienda("Ceraldi Group s.r.l.") == _norm_nome_azienda("CERALDI GROUP SRL")
    assert _norm_nome_azienda("  ceraldi group  SRL ") == "CERALDIGROUPSRL"
    assert _norm_nome_azienda(None) == ""


def test_piva_plausibile():
    assert _piva_plausibile("06714021000")
    assert _piva_plausibile("IT06714021000")
    # Un codice fiscale personale NON è una P.IVA
    assert not _piva_plausibile("PMUGLN65L23F839F")
    assert not _piva_plausibile("")
    assert not _piva_plausibile("1234")


# ── guardie su ensure_supplier_exists ────────────────────────────────────

class _FakeCollection:
    def __init__(self):
        self.inserted = []

    async def find_one(self, *a, **k):
        return None

    async def insert_one(self, doc, session=None):
        self.inserted.append(doc)

    async def update_one(self, *a, **k):
        pass


class _FakeDb:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _FakeCollection())

    def fornitori_inseriti(self):
        return self.collections.get("fornitori", _FakeCollection()).inserted


def test_autofattura_cedente_uguale_cessionario_per_nome():
    """Cedente con lo stesso nome del cessionario (autofattura): nessun fornitore."""
    db = _FakeDb()
    parsed = {
        "supplier_vat": "01879020517",
        "supplier_name": "CERALDI GROUP S.R.L.",
        "cliente": {"denominazione": "Ceraldi Group srl", "partita_iva": "09999999999"},
        "fornitore": {},
    }
    result = asyncio.run(ensure_supplier_exists(db, parsed))
    assert result["supplier_created"] is False
    assert result["supplier_id"] is None
    assert db.fornitori_inseriti() == []


def test_autofattura_cedente_uguale_cessionario_per_piva():
    """Cedente con la stessa P.IVA del cessionario: nessun fornitore."""
    db = _FakeDb()
    parsed = {
        "supplier_vat": "09999999999",
        "supplier_name": "QUALSIASI SRL",
        "cliente": {"denominazione": "ALTRA SRL", "partita_iva": "IT09999999999"},
        "fornitore": {},
    }
    result = asyncio.run(ensure_supplier_exists(db, parsed))
    assert result["supplier_created"] is False
    assert db.fornitori_inseriti() == []


def test_codice_fiscale_non_diventa_partita_iva():
    """Un CF personale nel campo cedente non crea un fornitore."""
    db = _FakeDb()
    parsed = {
        "supplier_vat": "PMUGLN65L23F839F",
        "supplier_name": "DITTA INDIVIDUALE X",
        "cliente": {"denominazione": "Ceraldi Group srl", "partita_iva": "01111111111"},
        "fornitore": {},
    }
    result = asyncio.run(ensure_supplier_exists(db, parsed))
    assert result["supplier_created"] is False
    assert db.fornitori_inseriti() == []


def test_fornitore_normale_viene_creato():
    """Il caso normale (cedente ≠ cessionario, P.IVA valida) crea il fornitore."""
    db = _FakeDb()
    parsed = {
        "supplier_vat": "06714021000",
        "supplier_name": "LEASYS S.p.A.",
        "cliente": {"denominazione": "Ceraldi Group srl", "partita_iva": "01111111111"},
        "fornitore": {"comune": "Roma"},
    }
    result = asyncio.run(ensure_supplier_exists(db, parsed))
    assert result["supplier_created"] is True
    inseriti = db.fornitori_inseriti()
    assert len(inseriti) == 1
    assert inseriti[0]["partita_iva"] == "06714021000"
