import asyncio

from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services.fornitore_da_fattura_banca import (
    assegna_alla_fattura_arrivata,
    assegna_fornitori_da_fatture,
)

CAUSALE = (
    "ADDEBITO DIRETTO SDD - SDD CORE: PK)K,TLYRBPN8JWYCYKCMKCV(58MO6 "
    "AMAZON PAYMENTS EUROPE S.C.A. AMAZON PAYMENTS"
)


def _fattura(id_, forn_id, nome, importo, data="2026-09-22", **extra):
    return {
        "id": id_, "invoice_number": f"N-{id_}", "invoice_date": data,
        "total_amount": importo, "supplier_id": forn_id, "supplier_name": nome, **extra,
    }


def _movimento(**extra):
    return {
        "id": "m1", "data": "2026-09-24", "importo": 51.72, "tipo": "uscita",
        "descrizione_originale": CAUSALE, **extra,
    }


def _esegui(fatture, movimenti, *, arrivata=None):
    async def scenario():
        db = ClientArchivioMemoria()["fornitore_da_fattura"]
        for f in fatture:
            await db.invoices.insert_one(dict(f))
        for m in movimenti:
            await db.estratto_conto_movimenti.insert_one(dict(m))
        if arrivata:
            esito = await assegna_alla_fattura_arrivata(db, arrivata)
        else:
            esito = await assegna_fornitori_da_fatture(db, [dict(m) for m in movimenti])
        mov = await db.estratto_conto_movimenti.find_one({"id": "m1"}, {"_id": 0})
        return esito, mov

    return asyncio.run(scenario())


AMAZON_BUSINESS = ("45", "Amazon Business EU S.a.r.l, Sede Secondaria")
AMAZON_ITALIA = ("147", "Amazon EU S.a r.l., Succursale Italiana")


def test_importo_e_nome_in_causale_danno_il_fornitore():
    esito, mov = _esegui([_fattura("f1", *AMAZON_BUSINESS, 51.72)], [_movimento()])
    assert esito["assegnati"] == 1
    assert mov["fornitore_id"] == "45"
    assert mov["categoria"] == "Fatture"
    assert "N-f1" in mov["categoria_auto_motivo"]


def test_arrivo_della_fattura_dopo_il_movimento():
    fattura = _fattura("f1", *AMAZON_BUSINESS, 51.72)
    esito, mov = _esegui([fattura], [_movimento()], arrivata=fattura)
    assert esito["assegnati"] == 1
    assert mov["fornitore_id"] == "45"


def test_solo_importo_non_basta():
    esito, mov = _esegui([_fattura("f1", "9", "Rossi Forniture Srl", 51.72)], [_movimento()])
    assert esito["assegnati"] == 0
    assert "fornitore_id" not in mov


def test_due_fornitori_compatibili_restano_al_titolare():
    esito, mov = _esegui(
        [_fattura("f1", *AMAZON_BUSINESS, 51.72), _fattura("f2", *AMAZON_ITALIA, 51.72)],
        [_movimento()],
    )
    assert esito["assegnati"] == 0
    assert "fornitore_id" not in mov


def test_copie_della_stessa_fattura_non_sono_ambiguita():
    esito, mov = _esegui(
        [_fattura("f1", *AMAZON_BUSINESS, 51.72), _fattura("f2", *AMAZON_BUSINESS, 51.72)],
        [_movimento()],
    )
    assert esito["assegnati"] == 1


def test_fattura_archiviata_non_conta():
    esito, _ = _esegui([_fattura("f1", *AMAZON_BUSINESS, 51.72, status="archived")], [_movimento()])
    assert esito["assegnati"] == 0


def test_fattura_fuori_finestra_non_conta():
    esito, _ = _esegui([_fattura("f1", *AMAZON_BUSINESS, 51.72, data="2026-06-01")], [_movimento()])
    assert esito["assegnati"] == 0


def test_secondo_giro_non_riassegna():
    fatture = [_fattura("f1", *AMAZON_BUSINESS, 51.72)]
    esito, mov = _esegui(fatture, [_movimento(categoria="Fatture", fornitore_id="45")])
    assert esito["esaminati"] == 0
