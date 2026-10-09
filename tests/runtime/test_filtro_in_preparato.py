"""Un ``$in`` con migliaia di voci si valuta in tempo lineare, con lo stesso esito.

Dai log del 26/09/2026 (sentinella del loop): il salvataggio SumUp cercava le
transazioni gia' in archivio con ``{"chiave": {"$in": [migliaia]}}`` e teneva
fermo tutto il processo 17 s ogni 5 minuti, perche' l'insieme delle voci si
ricostruiva per ogni documento della collezione.
"""
import asyncio
import time

from app.services.archivio_documenti_memoria import (
    ArchivioDocumenti, matches_filter, prepara_filtro,
)
from app.services.payment_invoice_matching import invoice_reference_in_text


def test_il_filtro_preparato_da_lo_stesso_esito():
    selettori = [
        {"x": {"$in": [1, 2, "tre", None]}},
        {"x": {"$in": [[1, 2]]}},
        {"$or": [{"x": {"$in": ["a"]}}, {"y": {"$in": [5]}}]},
        {"x": {"$nin": [1]}, "y": {"$in": [5, 6]}},
        {"tags": {"$in": ["b"]}},
    ]
    documenti = [{"x": 1}, {"x": "tre"}, {"x": None}, {}, {"x": [1, 2]}, {"x": "a"},
                 {"y": 5}, {"x": 2, "y": 6}, {"tags": ["a", "b"]}, {"tags": []}]
    for selettore in selettori:
        preparato = prepara_filtro(selettore)
        for documento in documenti:
            assert matches_filter(documento, preparato) == matches_filter(documento, selettore), (selettore, documento)


def test_la_lista_originale_non_cambia_e_resta_leggibile():
    voci = ["a", "b"]
    preparato = prepara_filtro({"k": {"$in": voci}})
    voci.append("c")
    assert not matches_filter({"k": "c"}, preparato)
    assert matches_filter({"k": "c"}, {"k": {"$in": voci}})


def test_diecimila_voci_su_diecimila_documenti_in_un_attimo():
    db = ArchivioDocumenti("test")
    chiavi = [f"k{i}" for i in range(10000)]

    async def scenario():
        await db["t"].insert_many([{"chiave": c} for c in chiavi])
        inizio = time.monotonic()
        trovati = await db["t"].find({"chiave": {"$in": chiavi[::2]}}, {"_id": 0}).to_list(None)
        return len(trovati), time.monotonic() - inizio

    quanti, secondi = asyncio.run(scenario())
    assert quanti == 5000
    assert secondi < 3, f"$in quadratico: {secondi:.1f} s"


def test_il_numero_di_fattura_si_riconosce_come_prima():
    assert invoice_reference_in_text("12/A", "SALDO FATTURA N. 12/A DEL 01/03")
    assert invoice_reference_in_text("2026-FT-0045", "PAG 2026 FT 0045 FORNITORE")
    assert not invoice_reference_in_text("123", "PAGAMENTO 1234 VARIE")
    assert not invoice_reference_in_text("A77", "BONIFICO SENZA RIFERIMENTI")
