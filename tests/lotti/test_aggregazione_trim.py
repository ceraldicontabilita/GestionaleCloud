"""Guardia: `$trim` non deve far morire l'aggregazione.

`$trim` e' un operatore standard di MongoDB, usato in due punti di Lotti per
raggruppare le descrizioni delle righe fattura. Il motore di interrogazione in
memoria non lo implementava, e un operatore sconosciuto non restituisce un
valore sbagliato: **solleva**, e con lui muore l'intera aggregazione.

Il costo, letto negli `scheduler_logs` del 20/09/2026:

    "Although '$trim' is a valid string operator for the aggregation pipeline,
     it is currently not implemented in Mongomock."   x 644

Una ogni 20 minuti dal 03/09 al 20/09, sempre lo stesso errore, sempre
`success: false`, **zero giri riusciti su 644**. E' il job che identifica via
ricerca web le righe fattura senza nome canonico: da li' nasce
`nome_mapping`, e senza mapping i 344 lotti fornitori restano tutti senza
`nome_canonico` — il ramo preciso del FIFO non aggancia piu' niente e la
tracciabilita' ingrediente -> lotto fornitore si regge solo sul ripiego a
espressione regolare.

La stessa riga fermava il raggruppamento degli sconti merce
(`sconti_merce.py`, due `$trim`).
"""
import asyncio

import pytest

from app.services.archivio_documenti_memoria import (
    ClientArchivioMemoria,
    evaluate_expression,
)


CASI = [
    ("spazi ai due lati", {"$trim": {"input": "  pane  "}}, "pane"),
    ("solo a sinistra", {"$ltrim": {"input": "  pane  "}}, "pane  "),
    ("solo a destra", {"$rtrim": {"input": "  pane  "}}, "  pane"),
    ("caratteri scelti", {"$trim": {"input": "**pane**", "chars": "*"}}, "pane"),
    ("niente da togliere", {"$trim": {"input": "pane"}}, "pane"),
    ("stringa vuota", {"$trim": {"input": ""}}, ""),
    ("input nullo resta nullo", {"$trim": {"input": None}}, None),
    ("tabulazioni e a capo", {"$trim": {"input": "\t pane \n"}}, "pane"),
]


@pytest.mark.parametrize("caso,espressione,atteso", CASI, ids=[c[0] for c in CASI])
def test_trim(caso, espressione, atteso):
    assert evaluate_expression(espressione, {}) == atteso


def test_trim_su_un_campo_del_documento():
    """La forma vera usata in produzione: `$trim` sopra `$toLower`/`$ifNull`."""
    espressione = {"$trim": {"input": {"$toLower": {"$ifNull": ["$descrizione", ""]}}}}

    assert evaluate_expression(espressione, {"descrizione": "  PANE Rustico "}) == "pane rustico"
    assert evaluate_expression(espressione, {}) == ""


def test_la_pipeline_vera_delle_righe_fattura_gira():
    """Il controllo che descrive il guasto, non il suo rimedio.

    E' la pipeline di `schede_tecniche.coda_ricerca_web`: se domani qualcuno
    togliesse `$trim` dal motore, questo test direbbe subito che la coda della
    ricerca prodotti e' di nuovo ferma.
    """
    async def scenario():
        db = ClientArchivioMemoria()["collaudo_trim"]
        await db["fatture"].insert_many([
            {"id": "f1", "fornitore": "CILATTE", "prodotti": [
                {"descrizione": "  Ricotta di Pecora  "},
                {"descrizione": "FIORI E PROVOLA"},
            ]},
            {"id": "f2", "fornitore": "CILATTE", "prodotti": [
                {"descrizione": "ricotta di pecora"},
            ]},
        ])

        return await db["fatture"].aggregate([
            {"$unwind": "$prodotti"},
            {"$project": {
                "d": {"$trim": {"input": {"$toLower": {"$ifNull": ["$prodotti.descrizione", ""]}}}},
                "orig": "$prodotti.descrizione",
                "fornitore": 1,
            }},
            {"$match": {"d": {"$ne": ""}}},
            {"$group": {"_id": "$d", "n": {"$sum": 1},
                        "descrizione": {"$first": "$orig"},
                        "fornitore": {"$first": "$fornitore"}}},
            {"$sort": {"n": -1}},
        ]).to_list(100)

    gruppi = asyncio.run(scenario())
    per_chiave = {g["_id"]: g["n"] for g in gruppi}

    assert per_chiave == {"ricotta di pecora": 2, "fiori e provola": 1}, (
        "Senza `$trim` «  Ricotta di Pecora  » e «ricotta di pecora» restano "
        "due righe distinte e ognuna va in coda alla ricerca web per conto suo."
    )
