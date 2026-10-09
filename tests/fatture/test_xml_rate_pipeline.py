import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.handlers.scadenziario import handler_crea_scadenza
from app.parsers.fattura_elettronica_parser import parse_fattura_xml
from app.routers.bank.assegni_auto_match import _apply_match, _try_l3
from app.routers.prima_nota_module import sync as sync_mod
from app.routers.fatture_module import pagamento as pagamento_mod
from app.services.scadenze_rate_service import applica_quota_scadenze


XML_RATE = """<?xml version="1.0" encoding="UTF-8"?>
<FatturaElettronica>
 <FatturaElettronicaHeader>
  <CedentePrestatore><DatiAnagrafici><IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>00000000000</IdCodice></IdFiscaleIVA><Anagrafica><Denominazione>FORNITORE TEST</Denominazione></Anagrafica></DatiAnagrafici></CedentePrestatore>
  <CessionarioCommittente><DatiAnagrafici><IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>11111111111</IdCodice></IdFiscaleIVA><Anagrafica><Denominazione>CLIENTE TEST</Denominazione></Anagrafica></DatiAnagrafici></CessionarioCommittente>
 </FatturaElettronicaHeader>
 <FatturaElettronicaBody>
  <DatiGenerali><DatiGeneraliDocumento><TipoDocumento>TD24</TipoDocumento><Divisa>EUR</Divisa><Data>2026-01-15</Data><Numero>TEST-4711</Numero><ImportoTotaleDocumento>12000.01</ImportoTotaleDocumento></DatiGeneraliDocumento></DatiGenerali>
  <DatiBeniServizi><DettaglioLinee><NumeroLinea>1</NumeroLinea><Descrizione>Bene test</Descrizione><PrezzoUnitario>12000.01</PrezzoUnitario><PrezzoTotale>12000.01</PrezzoTotale><AliquotaIVA>0</AliquotaIVA></DettaglioLinee><DatiRiepilogo><AliquotaIVA>0</AliquotaIVA><ImponibileImporto>12000.01</ImponibileImporto><Imposta>0</Imposta></DatiRiepilogo></DatiBeniServizi>
  <DatiPagamento><CondizioniPagamento>TP01</CondizioniPagamento>
   <DettaglioPagamento><ModalitaPagamento>MP02</ModalitaPagamento><DataScadenzaPagamento>2026-02-28</DataScadenzaPagamento><ImportoPagamento>3000.00</ImportoPagamento></DettaglioPagamento>
   <DettaglioPagamento><ModalitaPagamento>MP02</ModalitaPagamento><DataScadenzaPagamento>2026-03-30</DataScadenzaPagamento><ImportoPagamento>3000.00</ImportoPagamento></DettaglioPagamento>
   <DettaglioPagamento><ModalitaPagamento>MP02</ModalitaPagamento><DataScadenzaPagamento>2026-04-30</DataScadenzaPagamento><ImportoPagamento>3000.00</ImportoPagamento></DettaglioPagamento>
   <DettaglioPagamento><ModalitaPagamento>MP02</ModalitaPagamento><DataScadenzaPagamento>2026-05-30</DataScadenzaPagamento><ImportoPagamento>3000.01</ImportoPagamento></DettaglioPagamento>
  </DatiPagamento>
 </FatturaElettronicaBody>
</FatturaElettronica>"""


class MemoryCursor:
    def __init__(self, docs): self.docs = list(docs)
    def sort(self, spec, *_):
        fields = spec if isinstance(spec, list) else [(spec, 1)]
        self.docs.sort(key=lambda d: tuple(d.get(k, "") for k, _ in fields))
        return self
    async def to_list(self, _): return [dict(d) for d in self.docs]


class MemoryCollection:
    def __init__(self): self.docs = []
    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if _match(doc, query): return dict(doc)
        return None
    def find(self, query, projection=None): return MemoryCursor([d for d in self.docs if _match(d, query)])
    async def update_one(self, query, update, upsert=False):
        for doc in self.docs:
            if _match(doc, query):
                for key, value in update.get("$set", {}).items(): doc[key] = value
                for key, value in update.get("$push", {}).items(): doc.setdefault(key, []).append(value)
                return SimpleNamespace(upserted_id=None, matched_count=1)
        if upsert:
            doc = dict(update.get("$setOnInsert", {})); self.docs.append(doc)
            return SimpleNamespace(upserted_id=doc.get("id"), matched_count=0)
        return SimpleNamespace(upserted_id=None, matched_count=0)


class MemoryDb(dict):
    def __getitem__(self, name):
        if name not in self: self[name] = MemoryCollection()
        return dict.__getitem__(self, name)


def _nested(doc, key):
    cur = doc
    for part in key.split("."):
        if isinstance(cur, list): return [x.get(part) for x in cur if isinstance(x, dict)]
        if not isinstance(cur, dict): return None
        cur = cur.get(part)
    return cur


def _match(doc, query):
    for key, expected in query.items():
        actual = _nested(doc, key)
        if isinstance(expected, dict):
            if "$ne" in expected and (expected["$ne"] in actual if isinstance(actual, list) else actual == expected["$ne"]): return False
            if "$exists" in expected and (actual is not None) != expected["$exists"]: return False
        elif isinstance(actual, list):
            if expected not in actual: return False
        elif actual != expected: return False
    return True


def test_parser_conserva_quattro_rate_e_centesimo_finale():
    parsed = parse_fattura_xml(XML_RATE)
    assert [r["importo"] for r in parsed["pagamento_rate"]] == ["3000.00", "3000.00", "3000.00", "3000.01"]
    assert [r["rata_indice"] for r in parsed["pagamento_rate"]] == [0, 1, 2, 3]
    assert parsed["pagamento_rate_totale"] == "12000.01"
    assert parsed["pagamento_rate_coerente"] is True
    assert parsed["pagamento"]["importo"] == "3000.00"


def test_handler_crea_quattro_scadenze_idempotenti():
    parsed = parse_fattura_xml(XML_RATE); db = MemoryDb()
    payload = {"fattura_id": "fatt-test", "numero_documento": "TEST-4711", "importo_totale": 12000.01,
               "data_documento": "2026-01-15", "pagamento_rate": parsed["pagamento_rate"],
               "pagamento_rate_coerente": True, "metodo_pagamento": "assegno"}
    first = asyncio.run(handler_crea_scadenza(payload, db))
    second = asyncio.run(handler_crea_scadenza(payload, db))
    assert first["scadenze_create"] == 4 and second["scadenze_esistenti"] == 4
    assert [d["importo_rata"] for d in db["scadenziario_fornitori"].docs] == ["3000.00", "3000.00", "3000.00", "3000.01"]
    assert all(d["stato"] == "aperta" for d in db["scadenziario_fornitori"].docs)


def test_quattro_assegni_matchano_una_fattura_solo_in_proposta():
    assegni = [{"id": f"a{i}", "numero": str(i), "importo": v} for i, v in enumerate([3000, 3000, 3000, 3000.01])]
    fattura = {"id": "f1", "_residuo": 12000.01, "total_amount": 12000.01, "invoice_number": "TEST-4711"}
    risultati = _try_l3(assegni, [fattura])
    assert len(risultati) == 1
    fattura_match, assegni_match = risultati[0]
    db = MemoryDb()
    proposta = asyncio.run(_apply_match(db, assegni_match, [fattura_match], livello="L3", dry_run=True))
    assert proposta["fattura_id"] == "f1" and len(proposta["assegni"]) == 4
    assert db == {}


def test_quote_chiudono_una_rata_per_volta_e_non_si_riusano():
    db = MemoryDb(); coll = db["scadenziario_fornitori"]
    coll.docs = [{"id": f"r{i}", "fattura_id": "f1", "importo_rata": str(v), "data_scadenza": f"2026-0{i+2}-28", "pagato": False, "blocco_indice": 0, "rata_indice": i}
                 for i, v in enumerate([3000, 3000, 3000, 3000.01])]
    asyncio.run(applica_quota_scadenze(db, fattura_id="f1", quota=3000, evidenza_id="assegno:a1:f1", metodo="assegno", data_pagamento="2026-02-20"))
    asyncio.run(applica_quota_scadenze(db, fattura_id="f1", quota=3000, evidenza_id="assegno:a1:f1", metodo="assegno", data_pagamento="2026-02-20"))
    assert [d["pagato"] for d in coll.docs] == [True, False, False, False]


def test_conferma_provvisoria_blocca_pagamento_totale_rate(monkeypatch):
    db = MemoryDb(); db["invoices"].docs = [{"id": "f1", "total_amount": 12000.01, "pagamento_rate": [{}, {}, {}, {}]}]
    monkeypatch.setattr(sync_mod.Database, "get_db", lambda: db)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(sync_mod.conferma_fattura_provvisoria({"fattura_id": "f1", "metodo": "banca"}))
    assert exc.value.status_code == 409
    assert db["prima_nota_banca"].docs == []


def test_pagamento_manuale_rateizzato_richiede_scadenza(monkeypatch):
    db = MemoryDb(); db["invoices"].docs = [{"id": "f1", "total_amount": 12000.01, "pagamento_rate": [{}, {}, {}, {}]}]
    monkeypatch.setattr(pagamento_mod.Database, "get_db", lambda: db)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(pagamento_mod.paga_fattura_manuale({
            "fattura_id": "f1", "importo": 12000.01, "metodo": "banca",
        }))
    assert exc.value.status_code == 409
