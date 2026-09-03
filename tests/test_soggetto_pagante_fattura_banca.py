"""Audit del commercialista 03/09/2026, §1 riga 2 / PR 4.

Caso reale: fattura IT6IGMSABEI di 11,99 EUR del 13/02/2026 di "Amazon
Business EU S.a.r.l, Sede Secondaria" (P.IVA 13397910962) marcata pagata
dall'SDD del 16/02/2026 "SDD CORE: PK)K,... AMAZON PAYMENTS EUROPE S.C.A.
AMAZON PAYMENTS": il solo marchio "AMAZON" + importo. Lo stesso giorno tre
SDD Amazon (11,99 / 118,96 / 25,60), l'ultimo intestato ad "AMAZON BUSINESS
EU SARL, IT BRANCH". Regola: senza P.IVA/IBAN/numero fattura in causale il
soggetto pagante deve coincidere con il fornitore; altrimenti PROPOSTA.
"""
import asyncio

from app.services import riconciliazione_bancaria as mod
from app.services.bank_payment_allocations import (
    _identity_evidence,
    reconcile_deterministic_invoice_allocations,
)
from app.services.identity_matching import (
    alias_fornitore,
    soggetto_causale_bancaria,
    soggetto_pagante_coerente,
)
from app.services.sheets_document_store import MemorySheetsClient

CAUSALE_PAYMENTS = (
    "SDD CORE: PK)K,TLYRBPN8JWYCYKCMKCV(58MO6 AMAZON PAYMENTS EUROPE S.C.A. AMAZON PAYMENTS"
)
CAUSALE_BUSINESS = "SDD CORE: PK)K,TLYRBPN8JWYCYKCMKCV(58MO6 AMAZON BUSINESS EU SARL, IT BRANCH"
FORNITORE = "Amazon Business EU S.a.r.l, Sede Secondaria"


def _run(coro):
    return asyncio.run(coro)


async def _noop(*args, **kwargs):
    return None


def _fattura(fid, numero, importo, fornitore=FORNITORE, data="2026-02-13", **extra):
    return {
        "id": fid, "invoice_number": numero, "invoice_date": data,
        "supplier_name": fornitore, "supplier_vat": "13397910962",
        "total_amount": importo, "importo_residuo": importo, "importo_pagato": 0.0,
        "pagato": False, "stato_pagamento": "da_pagare", **extra,
    }


def test_soggetto_letto_dalla_causale():
    assert soggetto_causale_bancaria(CAUSALE_PAYMENTS) == (
        "AMAZON PAYMENTS EUROPE S.C.A. AMAZON PAYMENTS"
    )
    assert soggetto_causale_bancaria(
        "ADDEBITO DIRETTO SDD - SDD CORE: MANDATO123 Eni Spa - Eni Regolamento Monetario"
    ) == "Eni Spa"
    assert soggetto_causale_bancaria(
        "VS.DISP. RIF. MB0B19307858/90207967 FAVORE CAPEZZUTO ALESSANDRO - ADD.TOT"
    ) == "CAPEZZUTO ALESSANDRO"
    assert soggetto_causale_bancaria("BONIFICO GENERICO 1234") is None
    assert soggetto_causale_bancaria("") is None


def test_coerenza_soggetto_pagante():
    # soggetto diverso: un solo marchio in comune non basta
    assert soggetto_pagante_coerente(FORNITORE, CAUSALE_PAYMENTS) is False
    assert soggetto_pagante_coerente("Amazon EU S.a.r.l.", CAUSALE_PAYMENTS) is False
    # stesso soggetto con forma societaria / sede diverse
    assert soggetto_pagante_coerente(FORNITORE, CAUSALE_BUSINESS) is True
    # abbreviazione del fornitore
    assert soggetto_pagante_coerente(
        "Eni Plenitude S.p.A.",
        "ADDEBITO DIRETTO SDD - SDD CORE: MANDATO123 Eni Spa - Eni Regolamento Monetario",
    ) is True
    assert soggetto_pagante_coerente("FASTWEB SpA", "SDD CORE: FASTWEB-REF FASTWEB") is True
    # nessuna controparte leggibile: nessun giudizio
    assert soggetto_pagante_coerente(FORNITORE, "BONIFICO GENERICO") is None
    # alias dichiarati in anagrafica
    assert soggetto_pagante_coerente(
        FORNITORE, CAUSALE_PAYMENTS, alias=("Amazon Payments Europe",),
    ) is True
    assert alias_fornitore({"nomi_alternativi": ["Amazon Payments Europe"]}) == (
        "Amazon Payments Europe",
    )
    assert alias_fornitore({"alias": "A; B"}) == ("A", "B")
    assert alias_fornitore(None) == ()


def test_evidenza_sdd_con_soggetto_diverso_e_bloccata_non_ammessa():
    evidenza = mod._evidenza_sdd_fattura_banca(
        _fattura("f-1199", "IT6IGMSABEI", 11.99), CAUSALE_PAYMENTS, 11.99, "2026-02-16",
    )
    assert evidenza["importo_esatto"] is True
    assert evidenza["fornitore_presente"] is True
    assert evidenza["soggetto_coerente"] is False
    assert evidenza["bloccato_da_soggetto"] is True
    assert evidenza["auto_ammesso"] is False

    coerente = mod._evidenza_sdd_fattura_banca(
        _fattura("f-2560", "IT6IGMZABEI", 25.60), CAUSALE_BUSINESS, 25.60, "2026-02-16",
    )
    assert coerente["soggetto_coerente"] is True
    assert coerente["auto_ammesso"] is True


def test_motore_storico_amazon_payments_resta_proposta_in_scegli_fattura(monkeypatch):
    async def scenario():
        db = MemorySheetsClient()["amazon-sdd-storico"]
        monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))
        monkeypatch.setattr(mod, "_propaga_fattura_pagata", _noop)
        monkeypatch.setattr(mod, "_registra_match_partita_aperta", _noop)
        monkeypatch.setattr(mod, "_alert_non_riconciliato", _noop)
        monkeypatch.setattr(mod, "_alert_pagamento_multiplo", _noop)
        await db.invoices.insert_many([
            _fattura("f-1199", "IT6IGMSABEI", 11.99),
            _fattura("f-11896", "IT6IJHJABEI", 118.96),
            _fattura("f-2560", "IT6IGMZABEI", 25.60),
        ])
        await db.estratto_conto_movimenti.insert_many([
            {"id": "EC-2026-02-16-11.99-29944358", "data": "2026-02-16", "tipo": "uscita",
             "importo": 11.99, "descrizione_originale": CAUSALE_PAYMENTS, "riconciliato": False},
            {"id": "EC-2026-02-16-118.96-871d7115", "data": "2026-02-16", "tipo": "uscita",
             "importo": 118.96, "descrizione_originale": CAUSALE_PAYMENTS, "riconciliato": False},
            {"id": "EC-2026-02-16-25.60-ca55986a", "data": "2026-02-16", "tipo": "uscita",
             "importo": 25.60, "descrizione_originale": CAUSALE_BUSINESS, "riconciliato": False},
        ])

        risultato = await mod.riconcilia_movimenti_banca()
        # il secondo giro non deve creare una seconda proposta
        await mod.riconcilia_movimenti_banca()

        assert risultato["riconciliati_fatture"] == 1
        assert risultato["dubbi"] == 2
        for ec_id, fid in (
            ("EC-2026-02-16-11.99-29944358", "f-1199"),
            ("EC-2026-02-16-118.96-871d7115", "f-11896"),
        ):
            movimento = await db.estratto_conto_movimenti.find_one({"id": ec_id}, {"_id": 0})
            assert movimento.get("riconciliato") is not True
            fattura = await db.invoices.find_one({"id": fid}, {"_id": 0})
            assert fattura.get("pagato") is not True
            proposte = await db.operazioni_da_confermare.find(
                {"movimento_ec_id": ec_id, "stato": "da_confermare"}, {"_id": 0},
            ).to_list(None)
            assert len(proposte) == 1
            assert proposte[0]["match_type"] == "soggetto_pagante_diverso"
            candidati = proposte[0]["dettagli"]["fatture_candidate"]
            assert [c["id"] for c in candidati] == [fid]
            assert "AMAZON PAYMENTS" in proposte[0]["dettagli"]["motivo_dubbio"]
        # Amazon Business EU SARL, IT BRANCH = stesso soggetto: automatico
        ok = await db.estratto_conto_movimenti.find_one(
            {"id": "EC-2026-02-16-25.60-ca55986a"}, {"_id": 0},
        )
        assert ok["riconciliato"] is True
        assert (await db.invoices.find_one({"id": "f-2560"}, {"_id": 0}))["pagato"] is True
        assert await db.prima_nota_banca.count_documents({}) == 1

    _run(scenario())


def test_motore_canonico_token_fornitore_con_soggetto_diverso_e_proposta():
    movimento = {
        "id": "EC-2026-02-16-11.99-29944358", "data": "2026-02-16", "tipo": "uscita",
        "importo": -11.99, "descrizione": CAUSALE_PAYMENTS,
    }
    fattura = _fattura("f-1199", "IT6IGMSABEI", 11.99, fornitore="Amazon EU S.a.r.l.")
    evidenza = _identity_evidence(movimento, fattura)
    assert evidenza["proposta"] is True
    assert evidenza["priority"] == 0
    assert evidenza["rule"] == "fornitore+importo:soggetto_pagante_diverso"
    assert evidenza["soggetto_coerente"] is False

    # con la P.IVA in causale l'identita' e' provata: nessuna proposta
    con_piva = _identity_evidence(
        {**movimento, "descrizione": CAUSALE_PAYMENTS + " P.IVA 13397910962"}, fattura,
    )
    assert con_piva["proposta"] is False
    assert con_piva["rule"] == "iban_o_piva+importo"

    # un marchio da una sola parola contenuto in un nome piu' lungo ("Amazon
    # EU" in "AMAZON BUSINESS EU SARL") resta un soggetto diverso: proposta
    breve = _identity_evidence({**movimento, "descrizione": CAUSALE_BUSINESS}, fattura)
    assert breve["proposta"] is True

    # stesso soggetto (forma societaria e sede diverse): regola ordinaria
    stesso = _identity_evidence(
        {**movimento, "descrizione": CAUSALE_BUSINESS},
        _fattura("f-1199", "IT6IGMSABEI", 11.99, fornitore=FORNITORE),
    )
    assert stesso["proposta"] is False
    assert stesso["rule"] == "fornitore+importo"


def test_motore_canonico_scrive_la_proposta_e_non_applica():
    async def scenario():
        db = MemorySheetsClient()["amazon-sdd-canonico"]
        await db.estratto_conto_movimenti.insert_one({
            "id": "EC-2026-02-16-11.99-29944358", "data": "2026-02-16", "tipo": "uscita",
            "importo": -11.99, "descrizione": CAUSALE_PAYMENTS,
        })
        await db.invoices.insert_one(
            _fattura("f-1199", "IT6IGMSABEI", 11.99, fornitore="Amazon EU S.a.r.l."),
        )

        risultato = await reconcile_deterministic_invoice_allocations(
            db, movement_ids=["EC-2026-02-16-11.99-29944358"],
        )
        await reconcile_deterministic_invoice_allocations(
            db, movement_ids=["EC-2026-02-16-11.99-29944358"],
        )

        assert risultato["allocati_identita"] == 0
        assert risultato["proposte_soggetto_diverso"] == 1
        assert not (await db.invoices.find_one({"id": "f-1199"})).get("pagato")
        movimento = await db.estratto_conto_movimenti.find_one(
            {"id": "EC-2026-02-16-11.99-29944358"}, {"_id": 0},
        )
        assert not movimento.get("riconciliato")
        proposte = await db.operazioni_da_confermare.find({}, {"_id": 0}).to_list(None)
        assert len(proposte) == 1
        assert proposte[0]["match_type"] == "soggetto_pagante_diverso"
        assert proposte[0]["dettagli"]["fatture_candidate"][0]["id"] == "f-1199"
        assert proposte[0]["dettagli"]["soggetto_causale"].startswith("AMAZON PAYMENTS")

    _run(scenario())
