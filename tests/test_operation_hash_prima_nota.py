import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.services.scritture_contabili import calcola_operation_hash, scrivi_movimento


def test_hash_distingue_assegni_che_pagano_stessa_fattura():
    common = {"source": "assegno_estratto_conto", "fattura_id": "INV-1"}
    first = calcola_operation_hash("banca", {**common, "descrizione": "Assegno n. 0208770767"})
    second = calcola_operation_hash("banca", {**common, "descrizione": "Assegno n. 0208770851"})
    assert first and second and first != second


def test_writer_non_inserisce_due_volte_stessa_prova_originaria():
    async def scenario():
        db = AsyncMongoMockClient()["operation_hash"]
        mov = {
            "data": "2026-08-20", "tipo": "uscita", "importo": 51.64,
            "categoria": "Fatture", "descrizione": "Pagamento verbale",
            "source": "estratto_conto_auto", "estratto_conto_id": "EC-123",
        }
        first = await scrivi_movimento(db, "banca", mov)
        second = await scrivi_movimento(db, "banca", mov)
        count = await db.prima_nota_banca.count_documents({})
        return first, second, count

    first, second, count = asyncio.run(scenario())
    assert first == second
    assert count == 1

