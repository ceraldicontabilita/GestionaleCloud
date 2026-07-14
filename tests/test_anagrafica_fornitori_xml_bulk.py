"""Ricostruzione una tantum dei dati anagrafici fornitori da XML (richiesta
utente 14/07/2026: "esegui script per far ricostruire una tantum i dati
dalle fatture", a fronte di "mancano iban email località nei dati" sulla
pagina Fornitori). Copre sia l'endpoint singolo (_popola_dati_fornitore)
sia quello bulk (popola_tutti_fornitori_da_xml), incluso il fallback su
invoices.xml_raw quando il file XML non è più su disco (/tmp non
sopravvive a riavvii/deploy)."""
import asyncio

from app.routers import anagrafica_fornitori_xml as mod

XML_RONDINELLA = """<?xml version="1.0"?>
<p:FatturaElettronica xmlns:p="ns">
  <FatturaElettronicaHeader>
    <CedentePrestatore>
      <DatiAnagrafici>
        <IdFiscaleIVA><IdCodice>01879020517</IdCodice></IdFiscaleIVA>
        <Anagrafica><Denominazione>RONDINELLA MARKET S.R.L.</Denominazione></Anagrafica>
      </DatiAnagrafici>
      <Sede>
        <Indirizzo>Via Roma 1</Indirizzo>
        <CAP>80100</CAP>
        <Comune>Napoli</Comune>
        <Provincia>NA</Provincia>
      </Sede>
      <Contatti>
        <Telefono>0812345678</Telefono>
        <Email>info@rondinella.it</Email>
      </Contatti>
    </CedentePrestatore>
  </FatturaElettronicaHeader>
</p:FatturaElettronica>
"""


def _matches(doc, query):
    if not query:
        return True
    for k, v in query.items():
        if k == "$or":
            if not any(_matches(doc, q) for q in v):
                return False
        elif isinstance(v, dict) and "$in" in v:
            if doc.get(k) not in v["$in"]:
                return False
        else:
            if doc.get(k) != v:
                return False
    return True


class _FakeCollection:
    def __init__(self, docs=None):
        self.docs = docs or []

    async def find_one(self, query, *a, **k):
        for d in self.docs:
            if _matches(d, query):
                return dict(d)
        return None

    async def update_one(self, query, update, *a, **k):
        for d in self.docs:
            if _matches(d, query):
                d.update(update.get("$set", {}))
                return

    def find(self, query=None, *a, **k):
        return _FakeCursor([d for d in self.docs if _matches(d, query or {})])


class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    def limit(self, n):
        self._docs = self._docs[:n]
        return self

    async def to_list(self, n=None):
        return list(self._docs[:n] if n else self._docs)


class _FakeDb:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _FakeCollection())


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


def test_popola_dati_fornitore_usa_xml_raw_quando_manca_file_su_disco(monkeypatch):
    db = _FakeDb()
    fornitore = {"id": "sup-1", "partita_iva": "01879020517",
                 "ragione_sociale": "RONDINELLA MARKET S.R.L.",
                 "comune": "", "email": "", "telefono": ""}
    db["invoices"].docs = [
        {"supplier_vat": "01879020517", "xml_filename": "IT01879020517_001.xml", "xml_raw": XML_RONDINELLA},
    ]

    esito = _run(mod._popola_dati_fornitore(db, fornitore))

    assert esito["success"] is True
    assert esito["campi_aggiornati"]
    assert "comune" in esito["campi_aggiornati"]
    assert "email" in esito["campi_aggiornati"]
    aggiornato = db["fornitori"].docs  # nessun fornitore in db["fornitori"]: update_one è no-op qui
    # verificato tramite dati_estratti, che è la fonte usata per il $set
    assert esito["dati_estratti"]["comune"] == "Napoli"
    assert esito["dati_estratti"]["email"] == "info@rondinella.it"


def test_popola_dati_fornitore_non_sovrascrive_campi_esistenti(monkeypatch):
    db = _FakeDb()
    fornitore = {"id": "sup-1", "partita_iva": "01879020517",
                 "ragione_sociale": "RONDINELLA MARKET S.R.L.",
                 "comune": "Roma", "email": "", "telefono": ""}  # comune GIA' valorizzato
    db["invoices"].docs = [
        {"supplier_vat": "01879020517", "xml_filename": "IT01879020517_001.xml", "xml_raw": XML_RONDINELLA},
    ]

    esito = _run(mod._popola_dati_fornitore(db, fornitore))

    assert "comune" not in esito["campi_aggiornati"]  # non tocca "Roma"
    assert "email" in esito["campi_aggiornati"]


def test_popola_tutti_aggiorna_solo_fornitori_incompleti(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))

    db["fornitori"].docs = [
        {"id": "sup-1", "partita_iva": "01879020517", "ragione_sociale": "RONDINELLA MARKET S.R.L.",
         "comune": "", "email": "", "telefono": ""},
        {"id": "sup-2", "partita_iva": "99999999999", "ragione_sociale": "COMPLETO SRL",
         "comune": "Milano", "email": "a@b.it", "telefono": "02123", "indirizzo": "x", "cap": "20100", "provincia": "MI"},
    ]
    db["invoices"].docs = [
        {"supplier_vat": "01879020517", "xml_filename": "IT01879020517_001.xml", "xml_raw": XML_RONDINELLA},
    ]

    res = _run(mod.popola_tutti_fornitori_da_xml(limite=500))

    assert res["analizzati"] == 1  # solo sup-1: sup-2 non ha campi mancanti
    assert res["aggiornati"] == 1
    assert db["fornitori"].docs[0]["comune"] == "Napoli"
    assert db["fornitori"].docs[0]["email"] == "info@rondinella.it"
    assert db["fornitori"].docs[1]["comune"] == "Milano"  # invariato
