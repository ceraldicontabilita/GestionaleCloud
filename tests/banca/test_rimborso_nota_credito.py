"""Rimborso bancario in entrata <-> nota di credito (titolare, 02/10/2026).

Caso reale: nota di credito TD04 IT656QJABEC di 50,30 EUR del 25/09/2026 di
"Amazon Business EU S.a.r.l, Sede Secondaria" (fornitore con metodo banca)
rimborsata il 28/09 con "BONIF. VS. FAVORE - BON.DA AMAZON BUSINESS EU SARL,
IT BRANCH 408 -3630067-4208347 AMZNBusiness ...". Prima la nota restava in
Cassa provvisoria e il bonifico «Rimborso» senza documento.
"""
import asyncio

from app.services import riconciliazione_bancaria as mod
from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services.identity_matching import soggetto_causale_bancaria
from app.services.rimborsi_note_credito import (
    abbina_rimborso_nota_credito,
    candidati_nota_credito,
)
from app.routers.prima_nota_module import sync as sync_mod

FORNITORE = "Amazon Business EU S.a.r.l, Sede Secondaria"
CAUSALE_BUSINESS = (
    "BONIF. VS. FAVORE - BON.DA AMAZON BUSINESS EU SARL, IT BRANCH 408 -3630067-4208347 "
    "AMZNBusiness 1ELR07BNM6M4743 NR. BONIFICO SEPA: MB0B21551"
)
CAUSALE_PAYMENTS = (
    "BONIF. VS. FAVORE - BON.DA AMAZON PAYMENTS EUROPE S.C.A. AMAZON 4 08-6414508-2938723 "
    "AMZN Mktp IT 3NNKM1DMUB42U NR. BONIFICO SEPA: MB0B23414"
)
CAUSALE_ALTRO = "BONIF. VS. FAVORE - BON.DA BETA FORNITURE SRL RIF. 77"


def _run(coro):
    return asyncio.run(coro)


async def _noop(*args, **kwargs):
    return None


def _nota(fid, numero, importo, data="2026-09-25", fornitore=FORNITORE, piva="13397910962", **extra):
    return {
        "id": fid, "invoice_number": numero, "invoice_date": data, "tipo_documento": "TD04",
        "supplier_name": fornitore, "supplier_vat": piva, "status": "imported",
        "total_amount": importo, "importo_residuo": importo, "importo_pagato": 0.0,
        "stato_pagamento": "da_pagare", **extra,
    }


def _mov(mid, importo, data="2026-09-28", causale=CAUSALE_BUSINESS):
    return {"id": mid, "data": data, "tipo": "entrata", "importo": importo,
            "descrizione_originale": causale, "categoria": "Rimborso", "riconciliato": False}


def _db(monkeypatch, nome):
    db = ClientArchivioMemoria()[nome]
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))
    monkeypatch.setattr(sync_mod.Database, "get_db", staticmethod(lambda: db))
    for nome_fn in ("_propaga_fattura_pagata", "_registra_match_partita_aperta",
                    "_alert_non_riconciliato", "_alert_pagamento_multiplo"):
        monkeypatch.setattr(mod, nome_fn, _noop)
    return db


def test_ordinante_del_bonifico_in_entrata():
    assert soggetto_causale_bancaria(CAUSALE_BUSINESS) == "AMAZON BUSINESS EU SARL, IT BRANCH"
    assert soggetto_causale_bancaria(CAUSALE_PAYMENTS) == "AMAZON PAYMENTS EUROPE S.C.A. AMAZON"
    assert soggetto_causale_bancaria(CAUSALE_ALTRO) == "BETA FORNITURE SRL"


def test_candidati_identita_importo_e_finestra(monkeypatch):
    async def scenario():
        db = _db(monkeypatch, "rimborsi-candidati")
        await db.invoices.insert_many([
            _nota("nc-1", "IT656QJABEC", 50.30),
            _nota("nc-2", "IT656QJABED", 50.31),                     # un centesimo
            _nota("nc-3", "IT656QJABEE", 50.30, data="2026-07-01"),  # oltre 62 giorni
            _nota("nc-4", "IT656QJABEF", 50.30, data="2026-09-29"),  # dopo il rimborso
            _nota("nc-5", "B-1", 50.30, fornitore="Beta Forniture Srl", piva="01234567890"),
            _nota("nc-6", "IT656QJABEG", 50.30, riconciliato_con_ec="EC-vecchio"),
            {**_nota("nc-7", "F-1", 50.30), "tipo_documento": "TD01"},
        ])
        ids = [n["id"] for n in await candidati_nota_credito(db, _mov("EC-1", 50.30))]
        assert ids == ["nc-1"]
        # il collettore di gruppo (Amazon Payments) vale anche per i rimborsi
        ids = [n["id"] for n in await candidati_nota_credito(db, _mov("EC-2", 50.30, causale=CAUSALE_PAYMENTS))]
        assert ids == ["nc-1"]
        # ordinante di un altro fornitore: la nota Amazon non e' candidata
        ids = [n["id"] for n in await candidati_nota_credito(db, _mov("EC-3", 50.30, causale=CAUSALE_ALTRO))]
        assert ids == ["nc-5"]
        # causale senza ordinante: niente
        assert await candidati_nota_credito(db, _mov("EC-4", 50.30, causale="ACCREDITO GENERICO")) == []

    _run(scenario())


def test_motore_banca_chiude_la_nota_e_ritira_la_cassa_provvisoria(monkeypatch):
    async def scenario():
        db = _db(monkeypatch, "rimborsi-motore")
        await db.invoices.insert_one(_nota(
            "nc-1", "IT656QJABEC", 50.30,
            metodo_pagamento_effettivo="cassa", prima_nota_cassa_id="pnc-1",
        ))
        await db.prima_nota_cassa.insert_one({
            "id": "pnc-1", "data": "2026-09-25", "tipo": "entrata", "importo": 50.30,
            "categoria": "Nota credito fornitore", "fattura_id": "nc-1",
            "source": "auto_metodo_fornitore", "stato": "DA_VERIFICARE", "riconciliato": False,
        })
        # riga dichiarata dal titolare (report «Fatture ricevute»), senza prova
        await db.prima_nota_banca.insert_one({
            "id": "pnb-dich", "data": "2026-09-25", "tipo": "entrata", "importo": 50.30,
            "categoria": "Nota credito fornitore", "fattura_id": "nc-1",
            "source": "report_pagamenti_titolare", "dichiarato_titolare": True,
            "stato": "DA_VERIFICARE", "riconciliato": False,
        })
        await db.estratto_conto_movimenti.insert_one(_mov("EC-1", 50.30))

        risultato = await mod.riconcilia_movimenti_banca()
        secondo = await mod.riconcilia_movimenti_banca()

        assert risultato["riconciliati_fatture"] == 1
        assert risultato["dubbi"] == 0
        assert secondo["riconciliati_fatture"] == 0

        nota = await db.invoices.find_one({"id": "nc-1"}, {"_id": 0})
        assert nota["pagato"] is True
        assert nota["stato_pagamento"] == "pagata"
        assert nota["riconciliato_con_ec"] == "EC-1"
        assert nota["metodo_pagamento_effettivo"] == "banca"
        assert nota["prima_nota_cassa_id"] is None
        assert nota["data_pagamento"] == "2026-09-28"

        mov = await db.estratto_conto_movimenti.find_one({"id": "EC-1"}, {"_id": 0})
        assert mov["riconciliato"] is True
        assert mov["tipo_riconciliazione"] == "rimborso_nota_credito"
        assert mov["fattura_id"] == "nc-1"

        banca = await db.prima_nota_banca.find(
            {"status": {"$nin": ["deleted", "archived"]}}, {"_id": 0},
        ).to_list(None)
        assert len(banca) == 1
        assert banca[0]["tipo"] == "entrata"
        assert banca[0]["importo"] == 50.30
        assert banca[0]["fattura_id"] == "nc-1"
        assert banca[0]["estratto_conto_id"] == "EC-1"
        assert banca[0]["riconciliato"] is True
        assert banca[0]["source"] == "rimborso_nota_credito"
        dichiarata = await db.prima_nota_banca.find_one({"id": "pnb-dich"}, {"_id": 0})
        assert dichiarata["status"] == "deleted"
        assert dichiarata["sostituita_da"] == banca[0]["id"]

        cassa = await db.prima_nota_cassa.find_one({"id": "pnc-1"}, {"_id": 0})
        assert cassa["status"] == "deleted"
        assert cassa["deleted_reason"] == "riscontrata_da_estratto_conto:EC-1"
        assert cassa["sostituita_da"] == banca[0]["id"]
        assert await db.operazioni_da_confermare.count_documents({}) == 0

    _run(scenario())


def test_due_note_uguali_dello_stesso_fornitore_in_ordine_di_data(monkeypatch):
    async def scenario():
        db = _db(monkeypatch, "rimborsi-doppie")
        await db.invoices.insert_many([
            _nota("nc-a", "IT63NHOABEC", 59.48, data="2026-07-01"),
            _nota("nc-b", "IT63NTEABEC", 59.48, data="2026-07-01"),
        ])
        await db.estratto_conto_movimenti.insert_many([
            _mov("EC-a", 59.48, data="2026-07-02"),
            _mov("EC-b", 59.48, data="2026-07-02"),
        ])
        risultato = await mod.riconcilia_movimenti_banca()
        assert risultato["riconciliati_fatture"] == 2
        chiuse = {
            (await db.invoices.find_one({"id": i}, {"_id": 0}))["riconciliato_con_ec"]
            for i in ("nc-a", "nc-b")
        }
        assert chiuse == {"EC-a", "EC-b"}
        assert await db.prima_nota_banca.count_documents({}) == 2

    _run(scenario())


def test_stesso_importo_di_fornitori_diversi_nessuna_scelta(monkeypatch):
    async def scenario():
        db = _db(monkeypatch, "rimborsi-ambigui")
        await db.invoices.insert_many([
            _nota("nc-1", "IT656QJABEC", 50.30),
            _nota("nc-2", "IT656QJABEX", 50.30, fornitore="Amazon EU S.a r.l., Succursale Italiana", piva="99999999999"),
        ])
        mov = _mov("EC-1", 50.30, causale=CAUSALE_PAYMENTS)
        await db.estratto_conto_movimenti.insert_one(mov)
        assert await abbina_rimborso_nota_credito(db, mov) is None
        assert await db.prima_nota_banca.count_documents({}) == 0
        assert not (await db.invoices.find_one({"id": "nc-1"})).get("pagato")

    _run(scenario())


def test_una_cassa_confermata_non_si_ritira(monkeypatch):
    async def scenario():
        db = _db(monkeypatch, "rimborsi-cassa-confermata")
        await db.invoices.insert_one(_nota("nc-1", "IT656QJABEC", 50.30))
        await db.prima_nota_cassa.insert_one({
            "id": "pnc-ok", "data": "2026-09-25", "tipo": "entrata", "importo": 50.30,
            "fattura_id": "nc-1", "source": "fattura_pagata", "provvisorio": False,
        })
        mov = _mov("EC-1", 50.30)
        await db.estratto_conto_movimenti.insert_one(mov)
        dettagli = await abbina_rimborso_nota_credito(db, mov)
        assert dettagli["prima_nota_cassa_ritirate"] == []
        cassa = await db.prima_nota_cassa.find_one({"id": "pnc-ok"}, {"_id": 0})
        assert cassa.get("status") != "deleted"

    _run(scenario())
