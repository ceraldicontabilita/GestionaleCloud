"""Fatture estere: il titolare sceglie il pagamento PayPal fra i candidati.

PayPal puo' mostrare il marchio di un gruppo al posto del fornitore della
fattura e un numero d'ordine al posto del numero fattura: il motore non
collega da solo, la pagina elenca i candidati (importo al centesimo) e la
scelta del titolare scrive il link col motore unico. Mai un importo diverso.
"""
import asyncio

from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services.paypal_reconciliation_links import (
    candidati_paypal_per_fattura,
    collega_fattura_paypal_appena_importata,
    collega_paypal_scelto_dal_titolare,
)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _fattura():
    return {
        "id": "INV-ESTERA-1", "invoice_number": "2025000001", "invoice_date": "2025-10-07",
        "supplier_name": "FORNITORE ESTERO B.V.", "supplier_vat": "NL000000000B01",
        "total_amount": 100.0, "divisa": "EUR", "pagato": False,
    }


def _tx(transaction_id, importo=-100.0, **extra):
    return {
        "transaction_id": transaction_id, "nome_controparte": "MARCHIO DEL GRUPPO B.V.",
        "invoice_id_fornitore": "ORDINE-77", "importo": importo, "currency": "EUR",
        "data": "2025-10-06", "transaction_status": "S", **extra,
    }


async def _db_con(*transazioni):
    db = ClientArchivioMemoria().db
    await db.invoices.insert_one(_fattura())
    for tx in transazioni:
        await db.paypal_transactions.insert_one(tx)
    return db


def test_il_motore_non_collega_da_solo_ma_elenca_il_candidato():
    async def scenario():
        db = await _db_con(_tx("TX-1"), _tx("TX-ALTRO-IMPORTO", importo=-100.01))
        fattura = await db.invoices.find_one({"id": "INV-ESTERA-1"}, {"_id": 0})

        automatico = await collega_fattura_paypal_appena_importata(db, fattura)
        candidati = await candidati_paypal_per_fattura(db, fattura)

        assert automatico["collegata"] is False
        assert [c["transaction_id"] for c in candidati] == ["TX-1"]
        assert candidati[0]["associabile"] is False
        assert "importo" in candidati[0]["evidenze"]

    _run(scenario())


def test_la_scelta_del_titolare_collega_col_motore_unico():
    async def scenario():
        db = await _db_con(_tx("TX-1"))
        fattura = await db.invoices.find_one({"id": "INV-ESTERA-1"}, {"_id": 0})

        esito = await collega_paypal_scelto_dal_titolare(db, fattura, "TX-1")

        assert esito["collegata"] is True
        assert esito["fattura_associata"]["match"] == "manuale_validato"
        assert "scelta_titolare" in esito["fattura_associata"]["evidenze"]
        salvata = await db.invoices.find_one({"id": "INV-ESTERA-1"}, {"_id": 0})
        assert salvata["paypal_transaction_id"] == "TX-1"
        # Senza addebito in banca la fattura non e' pagata: il PayPal lo dice, la banca lo prova.
        assert salvata["pagato"] is False

    _run(scenario())


def test_la_scelta_non_vale_fuori_dai_candidati():
    async def scenario():
        db = await _db_con(
            _tx("TX-IMPORTO-DIVERSO", importo=-99.99),
            _tx("TX-TROPPO-LONTANA", data="2026-09-01"),
            _tx("TX-ALTRA-VALUTA", currency="USD"),
            _tx("TX-GIA-USATA", fattura_associata={"fattura_id": "ALTRA-FATTURA"}),
        )
        fattura = await db.invoices.find_one({"id": "INV-ESTERA-1"}, {"_id": 0})

        for tx_id in ("TX-IMPORTO-DIVERSO", "TX-TROPPO-LONTANA", "TX-GIA-USATA", "NON-ESISTE"):
            esito = await collega_paypal_scelto_dal_titolare(db, fattura, tx_id)
            assert esito == {"collegata": False, "motivo": "transazione_non_fra_i_candidati"}
        esito = await collega_paypal_scelto_dal_titolare(db, fattura, "TX-ALTRA-VALUTA")
        assert esito == {"collegata": False, "motivo": "valuta_non_coincidente"}
        salvata = await db.invoices.find_one({"id": "INV-ESTERA-1"}, {"_id": 0})
        assert not salvata.get("paypal_transaction_id")

    _run(scenario())


def _movimento_banca(ufficiale=True):
    return {
        "id": "EC-1", "data": "2025-10-08", "tipo": "uscita", "importo": 100.0,
        "paypal_transaction_id": "TX-1", "tipo_riconciliazione": "paypal_evidenze_univoche",
        # L'estratto ufficiale (PDF) ha rimesso riconciliato=False promuovendo il movimento.
        "riconciliato": False, "evidenza_bancaria_ufficiale": ufficiale,
        "in_attesa_estratto_ufficiale": not ufficiale,
    }


def test_scelta_su_addebito_ufficiale_gia_legato_chiude_la_fattura():
    async def scenario():
        db = await _db_con(_tx("TX-1", movimento_banca_id="EC-1", riconciliato_banca=True))
        await db.estratto_conto_movimenti.insert_one(_movimento_banca())
        fattura = await db.invoices.find_one({"id": "INV-ESTERA-1"}, {"_id": 0})

        esito = await collega_paypal_scelto_dal_titolare(db, fattura, "TX-1")

        assert esito["finalizzazione"]["finalizzata"] is True
        salvata = await db.invoices.find_one({"id": "INV-ESTERA-1"}, {"_id": 0})
        assert salvata["pagato"] is True
        assert salvata["stato_finanziario"] == "riconciliato"
        movimento = await db.estratto_conto_movimenti.find_one({"id": "EC-1"}, {"_id": 0})
        assert movimento["riconciliato"] is True

    _run(scenario())


def test_addebito_non_ufficiale_non_chiude_la_fattura():
    async def scenario():
        db = await _db_con(_tx("TX-1", movimento_banca_id="EC-1", riconciliato_banca=True))
        await db.estratto_conto_movimenti.insert_one(_movimento_banca(ufficiale=False))
        fattura = await db.invoices.find_one({"id": "INV-ESTERA-1"}, {"_id": 0})

        esito = await collega_paypal_scelto_dal_titolare(db, fattura, "TX-1")

        assert esito["collegata"] is True
        assert esito["finalizzazione"] == {"finalizzata": False, "motivo": "riscontro_bancario_non_confermato"}
        salvata = await db.invoices.find_one({"id": "INV-ESTERA-1"}, {"_id": 0})
        assert salvata["pagato"] is False

    _run(scenario())
