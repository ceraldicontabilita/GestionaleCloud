import asyncio
from types import SimpleNamespace

from app.handlers import learning as learning_handler
from app.parsers.fattura_elettronica_parser import parse_fattura_xml
from app.routers.invoices.fatture_upload import (
    _analizza_pagamento_xml,
    ensure_supplier_exists,
)


IBAN_TEST = "IT60X0542811101000000123456"

XML = f"""<?xml version="1.0"?>
<FatturaElettronica>
 <FatturaElettronicaHeader>
  <CedentePrestatore>
   <DatiAnagrafici><IdFiscaleIVA><IdCodice>01234567890</IdCodice></IdFiscaleIVA><Anagrafica><Denominazione>FORNITORE MISTO SRL</Denominazione></Anagrafica></DatiAnagrafici>
   <Sede><Indirizzo>Via Nuova 1</Indirizzo><CAP>80100</CAP><Comune>Napoli</Comune><Provincia>NA</Provincia><Nazione>IT</Nazione></Sede>
   <Contatti><Telefono>0811234567</Telefono><Email>amministrazione@example.it</Email></Contatti>
  </CedentePrestatore>
  <RappresentanteFiscale><DatiAnagrafici><IdFiscaleIVA><IdCodice>10987654321</IdCodice></IdFiscaleIVA><Anagrafica><Denominazione>RAPPRESENTANTE SRL</Denominazione></Anagrafica></DatiAnagrafici></RappresentanteFiscale>
  <CessionarioCommittente><DatiAnagrafici><IdFiscaleIVA><IdCodice>11111111111</IdCodice></IdFiscaleIVA><Anagrafica><Denominazione>CLIENTE SRL</Denominazione></Anagrafica></DatiAnagrafici></CessionarioCommittente>
 </FatturaElettronicaHeader>
 <FatturaElettronicaBody>
  <DatiGenerali><DatiGeneraliDocumento><TipoDocumento>TD01</TipoDocumento><Data>2026-08-01</Data><Numero>F-99</Numero><ImportoTotaleDocumento>183.00</ImportoTotaleDocumento></DatiGeneraliDocumento></DatiGenerali>
  <DatiBeniServizi>
   <DettaglioLinee><NumeroLinea>1</NumeroLinea><Descrizione>Bicchieri carta</Descrizione><Quantita>10</Quantita><PrezzoUnitario>10</PrezzoUnitario><PrezzoTotale>100</PrezzoTotale><AliquotaIVA>22</AliquotaIVA></DettaglioLinee>
   <DettaglioLinee><NumeroLinea>2</NumeroLinea><Descrizione>Manutenzione impianto</Descrizione><Quantita>1</Quantita><PrezzoUnitario>50</PrezzoUnitario><PrezzoTotale>50</PrezzoTotale><AliquotaIVA>22</AliquotaIVA></DettaglioLinee>
   <DatiRiepilogo><AliquotaIVA>22</AliquotaIVA><ImponibileImporto>150</ImponibileImporto><Imposta>33</Imposta></DatiRiepilogo>
  </DatiBeniServizi>
  <DatiPagamento><CondizioniPagamento>TP01</CondizioniPagamento><DettaglioPagamento><ModalitaPagamento>MP05</ModalitaPagamento><DataScadenzaPagamento>2026-09-01</DataScadenzaPagamento><ImportoPagamento>183</ImportoPagamento><IBAN>{IBAN_TEST}</IBAN></DettaglioPagamento></DatiPagamento>
 </FatturaElettronicaBody>
</FatturaElettronica>"""


class Cursor:
    def __init__(self, docs): self.docs = list(docs)
    async def to_list(self, _=None): return [dict(doc) for doc in self.docs]


class Collection:
    def __init__(self, docs=None): self.docs = list(docs or [])
    async def find_one(self, query, *args, **kwargs):
        for doc in self.docs:
            ors = query.get("$or") if isinstance(query, dict) else None
            if ors and any(all(doc.get(k) == v for k, v in clause.items()) for clause in ors):
                return dict(doc)
            if not ors and all(doc.get(k) == v for k, v in query.items()):
                return dict(doc)
        return None
    async def update_one(self, query, update, *args, **kwargs):
        for doc in self.docs:
            if doc.get("_id") == query.get("_id") or doc.get("id") == query.get("id"):
                doc.update(update.get("$set", {}))
                return SimpleNamespace(matched_count=1)
        return SimpleNamespace(matched_count=0)
    async def insert_one(self, doc, *args, **kwargs):
        self.docs.append(dict(doc))
        return SimpleNamespace(inserted_id=doc.get("id"))
    def find(self, *args, **kwargs): return Cursor(self.docs)


class Db(dict):
    def __getitem__(self, key):
        if key not in self: self[key] = Collection()
        return dict.__getitem__(self, key)


def test_parser_conserva_contatti_rappresentante_righe_rate_e_iban():
    parsed = parse_fattura_xml(XML)
    assert parsed["fornitore"]["telefono"] == "0811234567"
    assert parsed["fornitore"]["email"] == "amministrazione@example.it"
    assert parsed["fornitore"]["rappresentante_fiscale"]["partita_iva"] == "10987654321"
    assert [r["descrizione"] for r in parsed["linee"]] == ["Bicchieri carta", "Manutenzione impianto"]
    assert parsed["pagamento_rate"][0]["iban"] == IBAN_TEST


def test_metodo_xml_diverso_diventa_proposta_non_modifica_definitiva():
    parsed = parse_fattura_xml(XML)
    analisi = _analizza_pagamento_xml(parsed, "cassa")
    assert analisi["metodo_pagamento_xml_proposto"] == "banca"
    assert analisi["metodo_pagamento_xml_richiede_conferma"] is True
    assert analisi["iban_pagamento_xml"] == IBAN_TEST


def test_fornitore_completa_solo_campi_vuoti_e_conserva_conflitti_come_proposta():
    parsed = parse_fattura_xml(XML)
    db = Db()
    db["fornitori"].docs = [{
        "_id": "record-1", "id": "sup-1", "partita_iva": "01234567890",
        "piva": "01234567890", "nome": "FORNITORE MISTO SRL",
        "ragione_sociale": "FORNITORE MISTO SRL", "metodo_pagamento": "cassa",
        "indirizzo": "Via Confermata 9", "email": "", "telefono": "", "iban": "",
    }]
    result = asyncio.run(ensure_supplier_exists(db, parsed))
    supplier = db["fornitori"].docs[0]
    assert supplier["email"] == "amministrazione@example.it"
    assert supplier["telefono"] == "0811234567"
    assert supplier["iban"] == IBAN_TEST
    assert supplier["indirizzo"] == "Via Confermata 9"
    assert result["proposte_aggiornamento"]["indirizzo"]["valore_xml"] == "Via Nuova 1"
    assert supplier["metodo_pagamento"] == "cassa"


def test_classificazione_per_riga_supporta_fattura_mista(monkeypatch):
    async def configs(_db): return []
    async def classify(_db, _supplier, _descrizione, righe, configurazioni=None):
        testo = " ".join(r.get("descrizione", "") for r in righe).lower()
        if "bicchieri" in testo:
            return "13.1_IMBALLAGGI", {"nome": "Imballaggi", "deducibilita_ires": 1, "deducibilita_irap": 1, "detraibilita_iva": 1}, 0.9, "test"
        if "manutenzione" in testo:
            return "5.4_MANUTENZIONE_LOCALI", {"nome": "Manutenzione locali", "deducibilita_ires": 1, "deducibilita_irap": 1, "detraibilita_iva": 1}, 0.9, "test"
        return "99_ALTRI_COSTI", {"nome": "Altri costi", "deducibilita_ires": 1, "deducibilita_irap": 1, "detraibilita_iva": 1}, 0.1, "test"

    from app.services import learning_machine_cdc
    monkeypatch.setattr(learning_machine_cdc, "carica_configurazioni_learning", configs)
    monkeypatch.setattr(learning_machine_cdc, "classifica_fattura_con_learning", classify)

    parsed = parse_fattura_xml(XML)
    db = Db()
    db["invoices"].docs = [{"id": "fatt-1"}]
    result = asyncio.run(learning_handler.handler_classifica_cdc({
        "fattura_id": "fatt-1", "fornitore_ragione_sociale": parsed["supplier_name"],
        "righe_linee": parsed["linee"], "imponibile": 150, "iva": 33,
    }, db))
    invoice = db["invoices"].docs[0]
    assert result["classificazione_mista"] is True
    assert [r["centro_costo_id"] for r in invoice["classificazioni_righe"]] == [
        "13.1_IMBALLAGGI", "5.4_MANUTENZIONE_LOCALI",
    ]
    assert invoice["stato_classificazione"] == "classificata"
    assert sum(q["imponibile"] for q in invoice["centri_costo_ripartizione"]) == 150
