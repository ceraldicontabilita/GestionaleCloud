"""Numero canonico e carnet da 10 assegni (titolare, 28/09/2026).

In archivio c'era «208770369»: lo zero iniziale perso in un export, e il
confronto dei doppioni lo trattava come un assegno diverso da «0208770369».
L'interfaccia chiamava «carnet» il numero intero: 221 carnet da un assegno.
"""
import asyncio

from app.services import assegni_doppioni
from app.services.archivio_documenti_memoria import ArchivioDocumenti
from app.services.carnet_assegni import (
    carnet_del_numero,
    normalizza_numeri,
    numero_canonico,
    riepilogo_carnet,
)


def test_il_numero_riprende_lo_zero_perso():
    assert numero_canonico("208770369") == "0208770369"
    assert numero_canonico(" 0208770368 ") == "0208770368"
    assert numero_canonico("208769182-11") == "0208769182-11"


def test_un_frammento_non_diventa_un_numero():
    assert numero_canonico("328") == "328"
    assert numero_canonico("328-01") == "328-01"
    assert numero_canonico("ASSEGNO") == "ASSEGNO"


def test_il_carnet_va_da_1_a_0():
    assert carnet_del_numero("0208769071") == "0208769071"
    assert carnet_del_numero("0208769080") == "0208769071"
    assert carnet_del_numero("0208769081") == "0208769081"
    assert carnet_del_numero("0208769200") == "0208769191"
    assert carnet_del_numero("208770369") == "0208770361"
    assert carnet_del_numero("328") is None


def test_il_riepilogo_dice_usati_e_buchi_col_piu_recente_primo():
    righe = riepilogo_carnet([
        {"numero": "0208769071", "stato": "incassato", "data_emissione": "2025-04-23"},
        {"numero": "0208769072", "stato": "incassato", "data_emissione": "2025-04-30"},
        {"numero": "0208770361", "stato": "incassato", "data_emissione": "2025-10-01"},
    ])
    assert [r["carnet_id"] for r in righe] == ["0208770361", "0208769071"]
    vecchio = righe[1]
    assert vecchio["ultimo"] == "0208769080" and vecchio["in_archivio"] == 2
    assert vecchio["mancanti"][0] == "0208769073" and len(vecchio["mancanti"]) == 8


def test_lo_zero_perso_non_fa_un_doppione_diverso():
    a = assegni_doppioni.identita({"numero": "208770369", "importo": 300.0})
    b = assegni_doppioni.identita({"numero": "0208770369", "importo": 300.0})
    assert a == b


def test_la_correzione_va_per_id_nello_storico_e_una_volta_sola():
    db = ArchivioDocumenti()

    async def scenario():
        await db["assegni"].insert_many([
            {"id": "a1", "numero": "208770369", "stato": "incassato"},
            {"id": "a2", "numero": "0208770368", "stato": "incassato"},
            {"id": "a3", "numero": "328-01", "stato": "vuoto"},
        ])
        primo = await normalizza_numeri(db)
        secondo = await normalizza_numeri(db)
        a1 = await db["assegni"].find_one({"id": "a1"}, {"_id": 0})
        a3 = await db["assegni"].find_one({"id": "a3"}, {"_id": 0})
        return primo, secondo, a1, a3

    primo, secondo, a1, a3 = asyncio.run(scenario())
    assert primo["corrette"] == 1 and secondo["corrette"] == 0
    assert a1["numero"] == "0208770369"
    assert a1["storico"][-1]["campi"]["numero"] == {"prima": "208770369", "dopo": "0208770369"}
    assert a3["numero"] == "328-01"
