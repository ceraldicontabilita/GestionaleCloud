"""A-Cube: webhook protetto, sandbox mai in contabilita', produzione dallo smistatore."""
import asyncio
from types import SimpleNamespace

import pytest

from app.services import acube

UUID = "11111111-2222-4333-8444-555555555555"


class Collezione:
    def __init__(self):
        self.righe = []

    def _trova(self, filtro):
        for r in self.righe:
            if all(r.get(k) == v for k, v in filtro.items()):
                return r
        return None

    async def find_one(self, filtro, proiezione=None):
        r = self._trova(filtro)
        return dict(r) if r else None

    async def update_one(self, filtro, aggiornamento, upsert=False):
        r = self._trova(filtro)
        if r is None:
            if not upsert:
                return
            r = dict(filtro)
            self.righe.append(r)
        r.update(aggiornamento.get("$set", {}))


class Db(dict):
    def __missing__(self, nome):
        self[nome] = Collezione()
        return self[nome]


def _risposta(contenuto=b"", dati=None):
    return SimpleNamespace(content=contenuto, json=lambda: dati, status_code=200)


@pytest.fixture
def finto_acube(monkeypatch):
    xml = acube.xml_di_prova("PROVA-1")
    meta = {"uuid": UUID, "sdi_file_name": "IT01234567890_00001.xml", "marking": "received",
            "created_at": "2026-10-07T10:00:00+00:00",
            "sender": {"business_name": "FORNITORE DI PROVA SANDBOX", "business_vat_number_code": "01234567890"},
            "recipient": {"business_vat_number_code": acube.partita_iva()}}

    async def leggi(uuid, formato="json", client=None):
        assert uuid == UUID
        return _risposta(dati=meta) if formato == "json" else _risposta(contenuto=xml)

    monkeypatch.setattr(acube, "leggi", leggi)
    return meta


def test_sandbox_registra_ma_non_importa(monkeypatch, finto_acube):
    monkeypatch.setenv("ACUBE_ENV", "sandbox")
    chiamato = []

    async def smista(*a, **k):
        chiamato.append(a)
        return {"success": True}

    import app.services.drive_cartella_unica as cu
    monkeypatch.setattr(cu, "_smista", smista)
    db = Db()
    esito = asyncio.run(acube.acquisisci(db, UUID, via="webhook"))
    assert esito["stato"] == "simulata"
    assert chiamato == [], "in sandbox nessuna fattura entra in contabilita'"
    riga = db[acube.REGISTRO].righe[0]
    assert riga["numero"] == "PROVA-1"
    assert riga["totale"] == "12.20"
    assert riga["fornitore"] == "FORNITORE DI PROVA SANDBOX"
    # idempotente
    assert asyncio.run(acube.acquisisci(db, UUID, via="controllo"))["gia_presente"] is True


def test_produzione_passa_dallo_smistatore(monkeypatch, finto_acube):
    monkeypatch.setenv("ACUBE_ENV", "production")
    monkeypatch.delenv("ACUBE_IMPORT", raising=False)
    ricevuti = []

    async def smista(nome, contenuto, contesto, tipo=None):
        ricevuti.append((nome, contesto["channel"]))
        return {"success": True, "invoice_id": "abc", "invoice_number": "PROVA-1"}

    import app.services.drive_cartella_unica as cu
    monkeypatch.setattr(cu, "_smista", smista)
    db = Db()
    esito = asyncio.run(acube.acquisisci(db, UUID, via="webhook"))
    assert esito["stato"] == "importata"
    assert ricevuti == [("IT01234567890_00001.xml", "acube")]
    assert db[acube.REGISTRO].righe[0]["riferimenti"]["invoice_id"] == "abc"


def test_fattura_di_altri_rifiutata(monkeypatch, finto_acube):
    monkeypatch.setenv("ACUBE_ENV", "sandbox")
    finto_acube["recipient"]["business_vat_number_code"] = "99999999999"
    with pytest.raises(acube.AcubeErrore):
        asyncio.run(acube.acquisisci(Db(), UUID, via="webhook"))


def test_uuid_non_valido():
    with pytest.raises(acube.AcubeErrore):
        asyncio.run(acube.acquisisci(Db(), "../../x", via="webhook"))


def test_webhook_richiede_il_segreto():
    db = Db()
    segreto = asyncio.run(acube.segreto_webhook(db, crea=True))
    assert asyncio.run(acube.segreto_webhook(db, crea=True)) == segreto, "il segreto non cambia a ogni chiamata"
    assert asyncio.run(acube.webhook_autorizzato(db, f"Bearer {segreto}")) is True
    assert asyncio.run(acube.webhook_autorizzato(db, "Bearer sbagliato")) is False
    assert asyncio.run(acube.webhook_autorizzato(db, None)) is False
    assert asyncio.run(acube.webhook_autorizzato(Db(), f"Bearer {segreto}")) is False


def test_uuid_dal_corpo():
    assert acube.uuid_dal_corpo({"invoice": {"uuid": UUID, "payload": "x"}}) == UUID
    assert acube.uuid_dal_corpo({"uuid": UUID}) == UUID
    assert acube.uuid_dal_corpo([{"uuid": UUID}]) == UUID
    assert acube.uuid_dal_corpo("x") is None


def test_import_mai_in_sandbox(monkeypatch):
    monkeypatch.setenv("ACUBE_ENV", "sandbox")
    monkeypatch.setenv("ACUBE_IMPORT", "true")
    assert acube.import_attivo() is False
    monkeypatch.setenv("ACUBE_ENV", "production")
    assert acube.import_attivo() is True
    monkeypatch.setenv("ACUBE_IMPORT", "false")
    assert acube.import_attivo() is False


def test_totale_assente_resta_vuoto():
    xml = acube.xml_di_prova("PROVA-2").replace(
        b"<ImportoTotaleDocumento>12.20</ImportoTotaleDocumento>", b"")
    assert "totale" not in {k for k, v in acube.riepilogo_da_xml(xml).items() if v is not None}
