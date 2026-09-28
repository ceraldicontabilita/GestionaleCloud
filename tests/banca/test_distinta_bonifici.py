"""Distinta bonifici SEPA: un bonifico per fornitore, IBAN verificato, nessun pagamento."""
import asyncio
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.services import distinta_bonifici as d
from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.utils.iban import iban_mod97_valido

IBAN_A = "IT60X0542811101000000123456"
IBAN_B = "IT95J0306903497100000009170"
IBAN_ORDINANTE = "IT86U0303240320010000000144"
NS = {"p": "urn:iso:std:iso:20022:tech:xsd:pain.001.001.03"}


def _fattura(fid, numero, totale, fornitore, piva, **extra):
    return {
        "id": fid, "invoice_number": numero, "invoice_date": "2026-09-01",
        "supplier_name": fornitore, "supplier_vat": piva, "total_amount": totale,
        "importo_pagato": 0, "pagato": False, "stato_pagamento": "da_pagare",
        "tipo_documento": "TD01", "status": "imported", **extra,
    }


def _componi(fatture, fornitori, ids):
    async def scenario():
        db = ClientArchivioMemoria()["distinta"]
        for f in fatture:
            await db["invoices"].insert_one(f)
        for f in fornitori:
            await db["fornitori"].insert_one(f)
        esito = await d.componi_bonifici(db, ids)
        dopo = await db["invoices"].find({}, {"_id": 0}).to_list(None)
        return esito, dopo
    return asyncio.run(scenario())


def test_mod97():
    assert iban_mod97_valido(IBAN_A) and iban_mod97_valido("GB82 WEST 1234 5698 7654 32")
    assert not iban_mod97_valido("IT61X0542811101000000123456")
    assert not iban_mod97_valido("IT60X054281110100000012345")


def test_un_bonifico_per_fornitore_con_i_numeri_in_causale_e_nessuna_scrittura():
    fatture = [
        _fattura("a1", "386", 153.72, "Timas Ascensori Srl", "07818970639"),
        _fattura("a2", "738", 100.10, "Timas Ascensori Srl", "07818970639"),
        _fattura("b1", "FVL824", 50.00, "2M Italia S.r.l.", "03614591216",
                 pagamento={"iban": IBAN_B}),
    ]
    fornitori = [{"id": "f1", "partita_iva": "07818970639", "iban": IBAN_A}]
    esito, dopo = _componi(fatture, fornitori, ["a1", "a2", "b1"])

    assert esito["numero_bonifici"] == 2 and esito["scartate"] == []
    timas = next(b for b in esito["bonifici"] if b["partita_iva"] == "07818970639")
    assert timas["iban"] == IBAN_A and timas["fonte_iban"] == "anagrafica_fornitore"
    assert timas["importo"] == "253.82"
    assert timas["causale"] == "Saldo fatture 386, 738"
    due_m = next(b for b in esito["bonifici"] if b["partita_iva"] == "03614591216")
    assert due_m["fonte_iban"] == "xml_fattura" and due_m["causale"] == "Saldo fattura FVL824"
    assert Decimal(esito["totale"]) == Decimal("303.82")
    # Comporre la distinta non paga niente.
    assert all(f["pagato"] is False and f["stato_pagamento"] == "da_pagare" for f in dopo)


def test_scarti_dichiarati():
    fatture = [
        _fattura("nc", "NC1", 20.00, "Alfa", "01111111111", tipo_documento="TD04"),
        _fattura("pg", "P1", 20.00, "Alfa", "01111111111", pagato=True, stato_pagamento="pagata"),
        _fattura("ko", "K1", 20.00, "Beta", "02222222222",
                 pagamento={"iban": "IT61X0542811101000000123456"}),
        _fattura("no", "N1", 20.00, "Gamma", "03333333333"),
        _fattura("ar", "A1", 20.00, "Alfa", "01111111111", status="archived"),
    ]
    esito, _ = _componi(fatture, [], ["nc", "pg", "ko", "no", "ar", "manca"])
    motivi = {s["id"]: s["motivo"] for s in esito["scartate"]}
    assert motivi == {
        "nc": "nota_di_credito", "pg": "gia_pagata_o_annullata",
        "ko": "iban_non_valido:xml_fattura", "no": "iban_mancante",
        "ar": "fattura_non_attiva", "manca": "fattura_non_trovata",
    }
    assert esito["bonifici"] == []


def test_iban_da_una_fattura_precedente_e_residuo_al_netto_del_pagato():
    fatture = [
        _fattura("vecchia", "10", 80.00, "Delta", "04444444444", pagamento={"iban": IBAN_B},
                 pagato=True, stato_pagamento="pagata"),
        _fattura("nuova", "11", 100.00, "Delta", "04444444444", importo_pagato=30.00,
                 stato_pagamento="parziale"),
    ]
    esito, _ = _componi(fatture, [], ["nuova"])
    bonifico = esito["bonifici"][0]
    assert bonifico["fonte_iban"] == "fattura_precedente" and bonifico["iban"] == IBAN_B
    assert bonifico["importo"] == "70.00"


def test_xml_pain001_ben_formato_e_testo_sepa():
    bonifici = [{"fornitore": "Caffè & Co. «Srl»", "iban": IBAN_A, "importo": "253.82",
                 "causale": "Saldo fatture 386, 738"}]
    xml = d.xml_pain001(bonifici, iban_ordinante=IBAN_ORDINANTE, nome_ordinante="Ceraldi Group",
                        data_esecuzione="2026-10-01",
                        adesso=datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc))
    radice = ET.fromstring(xml.encode())
    assert radice.find("p:CstmrCdtTrfInitn/p:GrpHdr/p:CtrlSum", NS).text == "253.82"
    tx = radice.find(".//p:CdtTrfTxInf", NS)
    assert tx.find("p:Cdtr/p:Nm", NS).text == "Caffe e Co. Srl"
    assert tx.find("p:Amt/p:InstdAmt", NS).text == "253.82"
    assert tx.find(".//p:IBAN", NS).text == IBAN_A
    assert radice.find(".//p:DbtrAcct/p:Id/p:IBAN", NS).text == IBAN_ORDINANTE


def test_xml_rifiuta_ordinante_sbagliato_o_distinta_vuota():
    with pytest.raises(ValueError):
        d.xml_pain001([{"fornitore": "x", "iban": IBAN_A, "importo": "1.00", "causale": "c"}],
                      iban_ordinante="IT61X0542811101000000123456", nome_ordinante="x",
                      data_esecuzione="2026-10-01")
    with pytest.raises(ValueError):
        d.xml_pain001([], iban_ordinante=IBAN_ORDINANTE, nome_ordinante="x",
                      data_esecuzione="2026-10-01")


def test_causale_lunga_resta_entro_140_caratteri():
    numeri = [f"2026{i:08d}" for i in range(20)]
    causale = d.causale_bonifico(numeri)
    assert len(causale) <= 140 and causale.startswith("Saldo fatture 202600000000")
    assert causale.endswith("e altre " + str(20 - causale.count(",") - 1))


def test_partita_iva_col_prefisso_paese_trova_l_anagrafica():
    fatture = [_fattura("a1", "5", 10.00, "Epsilon", "IT05555555555")]
    esito, _ = _componi(fatture, [{"id": "f", "partita_iva": "05555555555", "iban": IBAN_A}], ["a1"])
    assert esito["bonifici"][0]["fonte_iban"] == "anagrafica_fornitore"
