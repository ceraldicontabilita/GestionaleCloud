"""Guardia: una giornata gia' in archivio non si conta due volte quando arriva il suo XML.

Collaudo del 20/09/2026 con i valori reali della giornata del 01/08/2026, portato
il 02/10/2026 sul motore unico `ingest_corrispettivo_parsed` (il vecchio
`CorrispettiviService` non aveva chiamanti ed e' stato tolto).

In produzione: 15 giornate di agosto 2026 registrate due volte, 31.356,28 EUR di
ricavi contati due volte. Le giornate arrivate dall'archivio legacy **non hanno**
`id_dispositivo` ne' `progressivo`, mentre l'XML ce li ha sempre.

La distinzione: una riga con `progressivo` o `id_dispositivo` e' una chiusura XML,
e una seconda chiusura dello stesso giorno **resta una seconda riga** (turni,
riaperture: due chiusure vere si sommano nei conti, non in una riga sola). Una
riga senza nessuno dei due non e' una chiusura: e' una giornata registrata senza
documento, e il suo XML la **sostituisce** se i contanti coincidono al centesimo.
"""
from decimal import Decimal

import pytest

from app.parsers.corrispettivi_parser import parse_corrispettivo_xml
from app.routers.invoices.corrispettivi_helpers import ingest_corrispettivo_parsed
from tests.corrispettivi._comune import attive, nuovo_db, run, xml_chiusura

MATRICOLA = "99MEY026532"
GIORNO = "2026-08-01"

# La riga come sta davvero in produzione (id 631, entrata dall'archivio legacy):
# niente progressivo, niente matricola.
RIGA_SENZA_DOCUMENTO = {
    "id": "631", "data": GIORNO, "totale": 2379,
    "pagato_contanti": 758.3, "totale_iva": 216.27, "status": "DA_VERIFICARE",
}


def _xml(progressivo, matricola, contanti, pos, imponibile, imposta, documenti):
    return xml_chiusura(data=GIORNO, progressivo=str(progressivo), matricola=matricola,
                        contanti=contanti, elettronico=pos, imponibile=imponibile,
                        imposta=imposta, documenti_n=documenti)


# La chiusura vera del 01/08/2026: 758,30 contanti + 1.620,70 POS = 2.379,00
CHIUSURA = _xml(2609, MATRICOLA, "758.30", "1620.70", "2162.73", "216.27", 357)
# Una seconda chiusura legittima dello stesso giorno (150,00)
SECONDA_CHIUSURA = _xml(2610, MATRICOLA, "100.00", "50.00", "136.36", "13.64", 20)
# Una chiusura con la matricola cambiata dal risigillo (500,00)
ALTRA_MATRICOLA = _xml(9001, "88ABC000001", "300.00", "200.00", "454.55", "45.45", 40)


def _esegui(nome, righe_iniziali, xml_da_processare):
    db = nuovo_db(nome)
    for riga in righe_iniziali:
        run(db["corrispettivi"].insert_one(dict(riga)))
    esiti = []
    for n, xml in enumerate(xml_da_processare):
        parsed = parse_corrispettivo_xml(xml)
        assert not parsed.get("error"), parsed
        esiti.append(run(ingest_corrispettivo_parsed(db, parsed, filename=f"chiusura_{n}.xml", source="xml")))
    righe = [r for r in run(attive(db, "corrispettivi")) if r.get("data") == GIORNO]
    totale = sum((Decimal(str(r.get("totale") or 0)) for r in righe), Decimal("0"))
    return esiti, righe, totale


# (caso, righe gia' in archivio, XML in arrivo, righe attese, totale atteso)
SCENARI = [
    ("giornata senza documento + il suo XML: sostituisce",
     [RIGA_SENZA_DOCUMENTO], [CHIUSURA], 1, "2379.00"),
    ("due chiusure XML vere dello stesso giorno: due righe, si sommano nei conti",
     [], [CHIUSURA, SECONDA_CHIUSURA], 2, "2529.00"),
    ("matricola cambiata dal risigillo: restano distinte",
     [], [CHIUSURA, ALTRA_MATRICOLA], 2, "2879.00"),
    ("giornata senza documento + due chiusure: sostituisce, poi la seconda si aggiunge",
     [RIGA_SENZA_DOCUMENTO], [CHIUSURA, SECONDA_CHIUSURA], 2, "2529.00"),
    ("stesso XML tre volte: una riga sola",
     [], [CHIUSURA, CHIUSURA, CHIUSURA], 1, "2379.00"),
]


@pytest.mark.parametrize(
    "caso,iniziali,xml,righe_attese,totale_atteso",
    SCENARI, ids=[s[0] for s in SCENARI],
)
def test_corrispettivi_stessa_giornata(caso, iniziali, xml, righe_attese, totale_atteso):
    _esiti, righe, totale = _esegui(f"gsd_{abs(hash(caso))}", iniziali, xml)

    assert len(righe) == righe_attese, (
        f"{caso}: {len(righe)} righe invece di {righe_attese}. "
        "Una giornata in piu' e' un ricavo contato due volte."
    )
    assert totale == Decimal(totale_atteso), (
        f"{caso}: totale {totale} invece di {totale_atteso}."
    )


def test_i_contanti_non_raddoppiano():
    """La riga senza documento si ritira e la chiusura XML porta i suoi importi:
    758,30 di contanti, non 1.516,60."""
    esiti, righe, _totale = _esegui("gsd_contanti", [RIGA_SENZA_DOCUMENTO], [CHIUSURA])

    (riga,) = righe
    assert Decimal(str(riga["pagato_contanti"])) == Decimal("758.3")
    assert Decimal(str(riga["pagato_elettronico"])) == Decimal("1620.7")
    assert esiti[0]["action"] == "created" and esiti[0]["sostituisce"]


def test_l_esito_dice_quale_dei_due_casi_e_avvenuto():
    """Sostituire e aggiungere non sono la stessa cosa: l'esito deve distinguerli."""
    esiti, _righe, _totale = _esegui("gsd_esito_sost", [RIGA_SENZA_DOCUMENTO], [CHIUSURA])
    assert esiti[0]["sostituisce"], esiti[0]

    esiti, _righe, _totale = _esegui("gsd_esito_somma", [], [CHIUSURA, SECONDA_CHIUSURA])
    assert esiti[1]["action"] == "created" and not esiti[1].get("sostituisce")
