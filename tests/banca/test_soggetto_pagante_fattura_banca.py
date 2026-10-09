"""Audit del commercialista 03/09/2026, §1 riga 2 / PR 4, rivisto il 02/10/2026.

Caso reale: fattura IT6IGMSABEI di 11,99 EUR del 13/02/2026 di "Amazon
Business EU S.a.r.l, Sede Secondaria" (P.IVA 13397910962) pagata dall'SDD
del 16/02/2026 "SDD CORE: PK)K,... AMAZON PAYMENTS EUROPE S.C.A. AMAZON
PAYMENTS". Lo stesso giorno tre SDD Amazon (11,99 / 118,96 / 25,60),
l'ultimo intestato ad "AMAZON BUSINESS EU SARL, IT BRANCH".

Regola: senza P.IVA/IBAN/numero fattura in causale il soggetto pagante deve
coincidere con il fornitore; un solo marchio in comune non basta ("ALFA
PAYMENTS EUROPE" per "Alfa Forniture Srl" resta PROPOSTA). Eccezione
dichiarata (titolare, 02/10/2026): il collettore di pagamento di un gruppo
("AMAZON PAYMENTS EUROPE S.C.A." per ogni societa' Amazon) e' lo stesso
soggetto, e l'SDD Amazon si abbina da solo.
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
from app.services.archivio_documenti_memoria import ClientArchivioMemoria

CAUSALE_PAYMENTS = (
    "SDD CORE: PK)K,TLYRBPN8JWYCYKCMKCV(58MO6 AMAZON PAYMENTS EUROPE S.C.A. AMAZON PAYMENTS"
)
# formato BPM dal 2026: prefisso "ADDEBITO DIRETTO SDD" e marchio in coda
CAUSALE_PAYMENTS_BPM = (
    "ADDEBITO DIRETTO SDD - SDD CORE: PK)K,TLYRBPN8JWYCYKCMKCV(58MO6 "
    "Amazon Payments Europe S.C.A. - AMAZON"
)
CAUSALE_BUSINESS = "SDD CORE: PK)K,TLYRBPN8JWYCYKCMKCV(58MO6 AMAZON BUSINESS EU SARL, IT BRANCH"
FORNITORE = "Amazon Business EU S.a.r.l, Sede Secondaria"
FORNITORE_EU = "Amazon EU S.a r.l., Succursale Italiana"

# soggetto diverso col solo marchio in comune: nessun collettore dichiarato
CAUSALE_ALFA = "SDD CORE: MANDATO-ALFA-001 ALFA PAYMENTS EUROPE S.A."
FORNITORE_ALFA = "Alfa Srl"


def _run(coro):
    return asyncio.run(coro)


async def _noop(*args, **kwargs):
    return None


def _fattura(fid, numero, importo, fornitore=FORNITORE, data="2026-02-13", piva="13397910962", **extra):
    return {
        "id": fid, "invoice_number": numero, "invoice_date": data,
        "supplier_name": fornitore, "supplier_vat": piva,
        "total_amount": importo, "importo_residuo": importo, "importo_pagato": 0.0,
        "pagato": False, "stato_pagamento": "da_pagare", **extra,
    }


def test_soggetto_letto_dalla_causale():
    assert soggetto_causale_bancaria(CAUSALE_PAYMENTS) == (
        "AMAZON PAYMENTS EUROPE S.C.A. AMAZON PAYMENTS"
    )
    assert soggetto_causale_bancaria(CAUSALE_PAYMENTS_BPM) == "Amazon Payments Europe S.C.A"
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
    assert soggetto_pagante_coerente(FORNITORE_ALFA, CAUSALE_ALFA) is False
    assert soggetto_pagante_coerente("Alfa Forniture Srl", CAUSALE_ALFA) is False
    # collettore di gruppo dichiarato: ogni societa' Amazon, in entrambi i formati
    assert soggetto_pagante_coerente(FORNITORE, CAUSALE_PAYMENTS) is True
    assert soggetto_pagante_coerente(FORNITORE_EU, CAUSALE_PAYMENTS) is True
    assert soggetto_pagante_coerente(FORNITORE, CAUSALE_PAYMENTS_BPM) is True
    assert soggetto_pagante_coerente(FORNITORE_EU, CAUSALE_PAYMENTS_BPM) is True
    # il collettore non copre chi non porta il marchio del gruppo
    assert soggetto_pagante_coerente(FORNITORE_ALFA, CAUSALE_PAYMENTS) is False
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
        FORNITORE_ALFA, CAUSALE_ALFA, alias=("Alfa Payments Europe",),
    ) is True
    assert alias_fornitore({"nomi_alternativi": ["Amazon Payments Europe"]}) == (
        "Amazon Payments Europe",
    )
    assert alias_fornitore({"alias": "A; B"}) == ("A", "B")
    assert alias_fornitore(None) == ()


def test_evidenza_sdd_con_soggetto_diverso_e_bloccata_non_ammessa():
    evidenza = mod._evidenza_sdd_fattura_banca(
        _fattura("f-alfa", "A-1", 11.99, fornitore=FORNITORE_ALFA, piva="01234567890"),
        CAUSALE_ALFA, 11.99, "2026-02-16",
    )
    assert evidenza["importo_esatto"] is True
    assert evidenza["fornitore_presente"] is True
    assert evidenza["soggetto_coerente"] is False
    assert evidenza["bloccato_da_soggetto"] is True
    assert evidenza["auto_ammesso"] is False

    for causale in (CAUSALE_PAYMENTS, CAUSALE_PAYMENTS_BPM, CAUSALE_BUSINESS):
        coerente = mod._evidenza_sdd_fattura_banca(
            _fattura("f-2560", "IT6IGMZABEI", 25.60), causale, 25.60, "2026-02-16",
        )
        assert coerente["soggetto_coerente"] is True, causale
        assert coerente["bloccato_da_soggetto"] is False, causale
        assert coerente["auto_ammesso"] is True, causale


def test_motore_storico_amazon_si_abbina_da_solo(monkeypatch):
    async def scenario():
        db = ClientArchivioMemoria()["amazon-sdd-storico"]
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
             "importo": 118.96, "descrizione_originale": CAUSALE_PAYMENTS_BPM, "riconciliato": False},
            {"id": "EC-2026-02-16-25.60-ca55986a", "data": "2026-02-16", "tipo": "uscita",
             "importo": 25.60, "descrizione_originale": CAUSALE_BUSINESS, "riconciliato": False},
        ])

        risultato = await mod.riconcilia_movimenti_banca()
        # il secondo giro non deve scrivere una seconda volta
        await mod.riconcilia_movimenti_banca()

        assert risultato["riconciliati_fatture"] == 3
        assert risultato["dubbi"] == 0
        for ec_id, fid in (
            ("EC-2026-02-16-11.99-29944358", "f-1199"),
            ("EC-2026-02-16-118.96-871d7115", "f-11896"),
            ("EC-2026-02-16-25.60-ca55986a", "f-2560"),
        ):
            movimento = await db.estratto_conto_movimenti.find_one({"id": ec_id}, {"_id": 0})
            assert movimento["riconciliato"] is True, ec_id
            assert (await db.invoices.find_one({"id": fid}, {"_id": 0}))["pagato"] is True
        assert await db.operazioni_da_confermare.count_documents({}) == 0
        assert await db.prima_nota_banca.count_documents({}) == 3

    _run(scenario())


def test_motore_storico_soggetto_diverso_resta_proposta_in_scegli_fattura(monkeypatch):
    async def scenario():
        db = ClientArchivioMemoria()["alfa-sdd-storico"]
        monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))
        monkeypatch.setattr(mod, "_propaga_fattura_pagata", _noop)
        monkeypatch.setattr(mod, "_registra_match_partita_aperta", _noop)
        monkeypatch.setattr(mod, "_alert_non_riconciliato", _noop)
        monkeypatch.setattr(mod, "_alert_pagamento_multiplo", _noop)
        await db.invoices.insert_one(
            _fattura("f-alfa", "A-1", 11.99, fornitore=FORNITORE_ALFA, piva="01234567890"),
        )
        await db.estratto_conto_movimenti.insert_one(
            {"id": "EC-2026-02-16-11.99-alfa", "data": "2026-02-16", "tipo": "uscita",
             "importo": 11.99, "descrizione_originale": CAUSALE_ALFA, "riconciliato": False},
        )

        risultato = await mod.riconcilia_movimenti_banca()
        # il secondo giro non deve creare una seconda proposta
        await mod.riconcilia_movimenti_banca()

        assert risultato["riconciliati_fatture"] == 0
        assert risultato["dubbi"] == 1
        movimento = await db.estratto_conto_movimenti.find_one(
            {"id": "EC-2026-02-16-11.99-alfa"}, {"_id": 0},
        )
        assert movimento.get("riconciliato") is not True
        assert (await db.invoices.find_one({"id": "f-alfa"}, {"_id": 0})).get("pagato") is not True
        proposte = await db.operazioni_da_confermare.find(
            {"movimento_ec_id": "EC-2026-02-16-11.99-alfa", "stato": "da_confermare"}, {"_id": 0},
        ).to_list(None)
        assert len(proposte) == 1
        assert proposte[0]["match_type"] == "soggetto_pagante_diverso"
        assert [c["id"] for c in proposte[0]["dettagli"]["fatture_candidate"]] == ["f-alfa"]
        assert "ALFA PAYMENTS" in proposte[0]["dettagli"]["motivo_dubbio"]
        assert await db.prima_nota_banca.count_documents({}) == 0

    _run(scenario())


def test_motore_canonico_token_fornitore_con_soggetto_diverso_e_proposta():
    movimento = {
        "id": "EC-2026-02-16-11.99-alfa", "data": "2026-02-16", "tipo": "uscita",
        "importo": -11.99, "descrizione": CAUSALE_ALFA,
    }
    fattura = _fattura("f-alfa", "A-1", 11.99, fornitore=FORNITORE_ALFA, piva="01234567890")
    evidenza = _identity_evidence(movimento, fattura)
    assert evidenza["proposta"] is True
    assert evidenza["priority"] == 0
    assert evidenza["rule"] == "fornitore+importo:soggetto_pagante_diverso"
    assert evidenza["soggetto_coerente"] is False

    # con la P.IVA in causale l'identita' e' provata: nessuna proposta
    con_piva = _identity_evidence(
        {**movimento, "descrizione": CAUSALE_ALFA + " P.IVA 01234567890"}, fattura,
    )
    assert con_piva["proposta"] is False
    assert con_piva["rule"] == "iban_o_piva+importo"

    # collettore di gruppo: Amazon Payments paga per ogni societa' Amazon
    amazon = _fattura("f-1199", "IT6IGMSABEI", 11.99, fornitore="Amazon EU S.a.r.l.")
    for causale in (CAUSALE_PAYMENTS, CAUSALE_PAYMENTS_BPM):
        collettore = _identity_evidence({**movimento, "descrizione": causale}, amazon)
        assert collettore["proposta"] is False, causale
        assert collettore["rule"] == "fornitore+importo", causale
        assert collettore["soggetto_coerente"] is True, causale

    # un marchio da una sola parola contenuto in un nome piu' lungo ("Amazon
    # EU" in "AMAZON BUSINESS EU SARL") resta un soggetto diverso: proposta
    breve = _identity_evidence({**movimento, "descrizione": CAUSALE_BUSINESS}, amazon)
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
        db = ClientArchivioMemoria()["alfa-sdd-canonico"]
        await db.estratto_conto_movimenti.insert_one({
            "id": "EC-2026-02-16-11.99-alfa", "data": "2026-02-16", "tipo": "uscita",
            "importo": -11.99, "descrizione": CAUSALE_ALFA,
        })
        await db.invoices.insert_one(
            _fattura("f-alfa", "A-1", 11.99, fornitore=FORNITORE_ALFA, piva="01234567890"),
        )

        risultato = await reconcile_deterministic_invoice_allocations(
            db, movement_ids=["EC-2026-02-16-11.99-alfa"],
        )
        await reconcile_deterministic_invoice_allocations(
            db, movement_ids=["EC-2026-02-16-11.99-alfa"],
        )

        assert risultato["allocati_identita"] == 0
        assert risultato["proposte_soggetto_diverso"] == 1
        assert not (await db.invoices.find_one({"id": "f-alfa"})).get("pagato")
        movimento = await db.estratto_conto_movimenti.find_one(
            {"id": "EC-2026-02-16-11.99-alfa"}, {"_id": 0},
        )
        assert not movimento.get("riconciliato")
        proposte = await db.operazioni_da_confermare.find({}, {"_id": 0}).to_list(None)
        assert len(proposte) == 1
        assert proposte[0]["match_type"] == "soggetto_pagante_diverso"
        assert proposte[0]["dettagli"]["fatture_candidate"][0]["id"] == "f-alfa"
        assert proposte[0]["dettagli"]["soggetto_causale"].startswith("ALFA PAYMENTS")

    _run(scenario())
