"""Bonifici della carta SumUp che citano in causale le fatture che pagano.

Casi presi dall'estratto reale del 27/09/2026 (dati anonimizzati negli IBAN):
tre fatture Timas in un bonifico, due 2M Italia con numero alfanumerico, e
due bonifici Vandemoortele che si citano a vicenda. Il collegamento vale solo
se il fornitore e' quello del bonifico e la somma torna al centesimo.
"""
import asyncio

from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services.sumup_conto import COLL_MOVIMENTI, abbina_movimenti_sumup

IBAN_TIMAS = "IT95J0306903497100000009170"
IBAN_2M = "IT86U0303240320010000000144"
IBAN_VDM = "IT31V0100501400000000009591"


def _movimento(codice, data, uscita, riferimento, causale, iban):
    return {
        "id": f"sumup_conto:{codice}", "codice_transazione": codice, "data": data,
        "tipo_transazione": "Bonifico bancario in uscita",
        "riferimento": riferimento, "causale": causale,
        "uscita": uscita, "entrata": "0.00", "commissione": "0.00",
        "importo": f"-{uscita}", "segno": "uscita", "conto_contabile": "19.01.05",
        "iban_beneficiario": iban,
    }


def _fattura(fid, numero, data, totale, fornitore, piva, **extra):
    return {
        "id": fid, "invoice_number": numero, "invoice_date": data,
        "supplier_name": fornitore, "supplier_vat": piva,
        "total_amount": totale, "importo_residuo": totale, "importo_pagato": 0.0,
        "pagato": False, "stato_pagamento": "da_pagare", "tipo_documento": "TD01",
        **extra,
    }


def _run(db, fatture, movimenti):
    async def scenario():
        for fattura in fatture:
            await db["invoices"].insert_one(fattura)
        for movimento in movimenti:
            await db[COLL_MOVIMENTI].insert_one(movimento)
        primo = await abbina_movimenti_sumup(db)
        secondo = await abbina_movimenti_sumup(db)
        esito_fatture = {
            f["id"]: f for f in await db["invoices"].find({}, {"_id": 0}).to_list(None)
        }
        banca = await db["prima_nota_banca"].find({}, {"_id": 0}).to_list(None)
        movs = {m["id"]: m for m in await db[COLL_MOVIMENTI].find({}, {"_id": 0}).to_list(None)}
        return primo, secondo, esito_fatture, banca, movs
    return asyncio.run(scenario())


def _quote(fattura):
    return sorted(int(a["quota_cents"]) for a in fattura.get("payment_allocations") or [])


def test_tre_fatture_citate_in_un_bonifico_anche_se_dichiarate_pagate():
    db = ClientArchivioMemoria()["citate_timas"]
    dichiarata = {"pagato": True, "stato_pagamento": "pagata", "in_attesa_riscontro_banca": True}
    fatture = [
        _fattura("t386", "386", "2026-02-20", 153.72, "TIMAS ASCENSORI S.R.L.", "07818970639", **dichiarata),
        _fattura("t738", "738", "2026-04-13", 153.72, "TIMAS ASCENSORI S.R.L.", "07818970639", **dichiarata),
        _fattura("t1436", "1436", "2026-07-17", 153.72, "TIMAS ASCENSORI S.R.L.", "07818970639", **dichiarata),
    ]
    mov = _movimento("COJQMJZZMJ", "2026-09-22", "461.16",
                     "Timas Ascensori Srl IT95J0306903497100000009170",
                     "Pagamento Fatture 386, 738, 1436", IBAN_TIMAS)
    primo, secondo, esito, banca, movs = _run(db, fatture, [mov])

    assert primo["fatture_citate_abbinate"] == 1
    assert all(_quote(esito[f]) == [15372] for f in ("t386", "t738", "t1436"))
    assert {r.get("conto_contabile") for r in banca} == {"19.01.05"}
    assert movs["sumup_conto:COJQMJZZMJ"].get("riconciliato") is True
    assert secondo["fatture_citate_abbinate"] == 0


def test_numeri_alfanumerici_e_fornitore_diverso_con_lo_stesso_numero():
    db = ClientArchivioMemoria()["citate_2m"]
    fatture = [
        _fattura("m824", "FVL824", "2026-04-30", 135.42, "2M ITALIA S.R.L.", "03614591216"),
        _fattura("m968", "FVL968", "2026-05-18", 180.56, "2M ITALIA S.R.L.", "03614591216"),
        # Stesso numero, altro fornitore: non va toccata.
        _fattura("altro", "FVL824", "2026-04-01", 135.42, "ALTRA DITTA SPA", "09999999999"),
    ]
    mov = _movimento("CD2RXWK34Y", "2026-09-22", "315.98",
                     "2MITALIA S.R.L. IT86U0303240320010000000144",
                     "Saldo fatture fvl824 fvl968", IBAN_2M)
    primo, _, esito, _, _ = _run(db, fatture, [mov])

    assert primo["fatture_citate_abbinate"] == 1
    assert _quote(esito["m824"]) == [13542] and _quote(esito["m968"]) == [18056]
    assert _quote(esito["altro"]) == []


def test_due_bonifici_che_si_citano_pagano_insieme_in_ordine_di_data():
    db = ClientArchivioMemoria()["citate_vandemoortele"]
    vdm = ("VANDEMOORTELE EUROPE NV", "02644480994")
    fatture = [
        _fattura("v15144", "8528015144", "2026-05-28", 64.24, *vdm),
        _fattura("v18470", "8528018470", "2026-06-26", 327.20, *vdm),
        _fattura("v18771", "8528018771", "2026-06-30", 148.83, *vdm),
        _fattura("v20169", "8528020169", "2026-07-14", 396.97, *vdm),
        _fattura("v21612", "8528021612", "2026-07-28", 226.70, *vdm),
    ]
    movimenti = [
        _movimento("CDMV4JMYEV", "2026-08-06", "995.95",
                   "VANDEMOORTELE EUROPE NV IT31V0100501400000000009591",
                   "VANDEMOORTELE FT. 8528015144 FT. 8528018470 FT. 8528018771", IBAN_VDM),
        _movimento("CDZW3KN5KE", "2026-08-11", "167.99",
                   "VANDEMOORTELE EUROPE NV IT31V0100501400000000009591",
                   "Vandemoortele Saldo fatture 8528020169, 8528021612. "
                   "Si aggancia a bonifico del 06/08/26", IBAN_VDM),
    ]
    primo, secondo, esito, _, _ = _run(db, fatture, movimenti)

    assert primo["fatture_citate_abbinate"] == 2
    # Il primo bonifico paga le quattro piu' vecchie e 58,71 della quinta,
    # il secondo il resto: la stessa ripartizione del vecchio archivio.
    assert _quote(esito["v20169"]) == [39697]
    assert _quote(esito["v21612"]) == [5871, 16799]
    assert secondo["fatture_citate_abbinate"] == 0


def test_somma_che_non_torna_non_collega_niente():
    db = ClientArchivioMemoria()["citate_non_torna"]
    fatture = [_fattura("t386", "386", "2026-02-20", 153.72, "TIMAS ASCENSORI S.R.L.", "07818970639")]
    mov = _movimento("COXXXXXXX1", "2026-09-22", "200.00",
                     "Timas Ascensori Srl IT95J0306903497100000009170",
                     "Pagamento Fattura 386", IBAN_TIMAS)
    primo, _, esito, banca, _ = _run(db, fatture, [mov])
    assert primo["fatture_citate_abbinate"] == 0
    assert _quote(esito["t386"]) == [] and banca == []


def test_pagamento_pos_con_la_carta_chiude_le_fatture_senza_riga_dichiarata():
    """Mepa 123833 + 123834, pagate insieme al POS con la Mastercard SumUp.

    La 123833 era in attesa di riscontro senza una riga dichiarata da
    assorbire: restava «in attesa della banca» e candidata per un altro
    movimento dello stesso importo.
    """
    from app.services.bank_payment_allocations import (
        persist_bank_invoice_allocations, validate_bank_invoice_allocations,
    )

    db = ClientArchivioMemoria()["mepa_pos_carta"]
    mepa = ("ME.PA. ALIMENTARI S.R.L.", "05555550635")
    fatture = [
        _fattura("f123833", "123833", "2026-09-01", 392.54, *mepa,
                 in_attesa_riscontro_banca=True, provvisorio=True,
                 residuo_da_pagare=392.54),
        _fattura("f123834", "123834", "2026-09-01", 13.82, *mepa,
                 provvisorio=True, stato_finanziario="pagata_dichiarata_in_attesa_banca"),
    ]
    mov = {
        **_movimento("CDMVQ2WB6Z", "2026-09-01", "406.36",
                     "MEPA ALIMENTARI SRL POZZUOLI IT", "", ""),
        "tipo_transazione": "Pagamento POS",
    }

    async def scenario():
        for fattura in fatture:
            await db["invoices"].insert_one(fattura)
        await db[COLL_MOVIMENTI].insert_one(mov)
        allocazioni = await validate_bank_invoice_allocations(db, mov, [
            {"id": "f123833", "quota_cents": 39254},
            {"id": "f123834", "quota_cents": 1382},
        ])
        await persist_bank_invoice_allocations(db, mov, allocazioni, actor="riconciliazione_ui")
        return {f["id"]: f for f in await db["invoices"].find({}, {"_id": 0}).to_list(None)}

    esito = asyncio.run(scenario())
    for fid in ("f123833", "f123834"):
        fattura = esito[fid]
        assert fattura["pagato"] is True
        assert fattura["in_attesa_riscontro_banca"] is False
        assert fattura["stato_finanziario"] == "riconciliato"
        assert fattura["provvisorio"] is False
        assert fattura["residuo_da_pagare"] == 0
        assert fattura["riscontro_banca_movimento_id"] == "sumup_conto:CDMVQ2WB6Z"
        # Pagata con la carta al POS, non con un bonifico.
        assert fattura["metodo_pagamento"] == "Carta"


def test_la_riga_del_vecchio_import_passa_sul_conto_della_carta():
    db = ClientArchivioMemoria()["vecchio_import"]

    async def scenario():
        await db["prima_nota_banca"].insert_one({
            "id": "pn-today", "data": "2026-08-07", "tipo": "uscita", "importo": 214.4,
            "conto_contabile": "19.01.01", "source": "ec_override_metodo_cassa",
            "estratto_conto_id": "sumupbiz_C97WNWYJZM", "fattura_id": "f3397",
        })
        await db[COLL_MOVIMENTI].insert_one(_movimento(
            "C97WNWYJZM", "2026-08-07", "214.40",
            "Today Service S.r.l. IT87M0303203406010000002929",
            "Preventivo N 1908 del 07/08/2026", "IT87M0303203406010000002929",
        ))
        esito = await abbina_movimenti_sumup(db)
        riga = await db["prima_nota_banca"].find_one({"id": "pn-today"})
        mov = await db[COLL_MOVIMENTI].find_one({"id": "sumup_conto:C97WNWYJZM"})
        return esito, riga, mov

    esito, riga, mov = asyncio.run(scenario())
    assert esito["vecchie_righe_riallineate"] == 1
    assert riga["conto_contabile"] == "19.01.05"
    assert riga["estratto_conto_id"] == "sumup_conto:C97WNWYJZM"
    assert mov["prima_nota_banca_id"] == "pn-today" and mov["fattura_id"] == "f3397"


def test_numero_con_zeri_iniziali_o_coda_tagliata_dalla_banca():
    from app.services.bank_payment_allocations import _numero_citato

    leasys = {"invoice_number": "0000202610239916"}
    assert _numero_citato(leasys, {"202610239916"})
    assert _numero_citato(leasys, {"ft0202610239916"})
    # La causale taglia le ultime due cifre: ancora lo stesso numero.
    assert _numero_citato(leasys, {"2026102399"})
    # Tre cifre tagliate o un numero diverso: no.
    assert not _numero_citato(leasys, {"202610239"})
    assert not _numero_citato(leasys, {"202610239917"})
    # Un numero corto non si riconosce per le sole cifre.
    assert not _numero_citato({"invoice_number": "000386"}, {"0386"})
    assert _numero_citato({"invoice_number": "386"}, {"386"})


def test_zeri_iniziali_collegano_solo_il_fornitore_del_bonifico():
    db = ClientArchivioMemoria()["citate_leasys"]
    iban_leasys = "IT60X0542811101000000123456"
    fatture = [
        _fattura("l1", "0000202610239916", "2026-08-01", 512.40, "LEASYS ITALIA S.P.A.", "06714021000"),
        _fattura("x1", "0000202610239916", "2026-08-01", 512.40, "ALTRA DITTA SPA", "09999999999"),
    ]
    mov = _movimento("CDLEASYS01", "2026-09-10", "512.40",
                     f"Leasys Italia SpA {iban_leasys}",
                     "Pagamento fattura 202610239916", iban_leasys)
    primo, _, esito, _, _ = _run(db, fatture, [mov])
    assert primo["fatture_citate_abbinate"] == 1
    assert _quote(esito["l1"]) == [51240]
    assert _quote(esito["x1"]) == []
