"""Guardia: una giornata gia' in archivio non si conta due volte quando arriva il suo XML.

Collaudo del 20/09/2026, sul motore vero (`CorrispettiviService`) con i valori
reali della giornata del 01/08/2026 letti da produzione.

Cosa era successo. Il 15/07/2026 la chiave anti-duplicato era stata stretta da
`data` a `data + id_dispositivo`, per una ragione giusta: la matricola del
registratore cambia al risigillo triennale, e senza guardarla la giornata con
la matricola nuova veniva scartata come doppione, sparendo da Prima Nota.

Quella stretta ha aperto il buco opposto. Le giornate arrivate dall'archivio
legacy **non hanno** `id_dispositivo`, mentre l'XML ce l'ha sempre: nessuna
corrispondenza, e la stessa giornata rientrava come riga nuova. In produzione:
15 giornate di agosto 2026 registrate due volte, 31.356,28 EUR di ricavi
contati due volte, 14 scritture in piu' nel libro giornale.

Perche' non basta allargare la chiave — e questa e' la parte che i test
esistenti non coprivano. Trovata la riga, il motore la tratta come una
SECONDA chiusura della stessa giornata e ne somma gli importi: il collaudo ha
misurato **4.758,00 EUR** su una giornata da 2.379,00, con i contanti
raddoppiati a 1.516,60. Il doppio conteggio si sarebbe spostato da due righe a
una sola, dove nessuno lo vede.

La distinzione che serve: una riga con `progressivo` o `id_dispositivo` e' una
chiusura XML, e una seconda chiusura dello stesso giorno **si somma** (turni,
riaperture). Una riga senza nessuno dei due non e' una chiusura: e' una
giornata registrata senza documento, e il suo XML la **sostituisce** — la
stessa logica della promozione «provvisorio -> definitivo_xml».
"""
import asyncio

import pytest

from app.services.archivio_documenti_memoria import MemorySheetsClient
from app.services.corrispettivi_service import CorrispettiviService

MATRICOLA = "99MEY026532"
GIORNO = "2026-08-01"

# La riga come sta davvero in produzione (id 631, entrata dall'archivio legacy):
# niente progressivo, niente matricola, niente `chiusure_xml`.
RIGA_SENZA_DOCUMENTO = {
    "id": "631", "data": GIORNO, "totale": 2379,
    "pagato_contanti": 758.3, "totale_iva": 216.27, "status": "DA_VERIFICARE",
}


def _xml(progressivo, matricola, contanti, pos, imponibile, imposta, documenti, ora):
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<DatiCorrispettivi versione="COR10">\n'
        f"  <Trasmissione><Progressivo>{progressivo}</Progressivo>\n"
        f"    <Dispositivo><Tipo>RT</Tipo><IdDispositivo>{matricola}</IdDispositivo></Dispositivo>\n"
        f"    <DataOraTrasmissione>{GIORNO}T23:59:00</DataOraTrasmissione></Trasmissione>\n"
        f"  <DataOraRilevazione>{GIORNO}T{ora}</DataOraRilevazione>\n"
        "  <DatiRT>\n"
        f"    <Riepilogo><IVA><AliquotaIVA>10.00</AliquotaIVA><Imposta>{imposta}</Imposta></IVA>\n"
        f"      <Ammontare>{imponibile}</Ammontare></Riepilogo>\n"
        f"    <Totali><NumeroDocCommerciali>{documenti}</NumeroDocCommerciali>\n"
        f"      <PagatoContanti>{contanti}</PagatoContanti>\n"
        f"      <PagatoElettronico>{pos}</PagatoElettronico></Totali>\n"
        "  </DatiRT>\n"
        "</DatiCorrispettivi>"
    ).encode()


# La chiusura vera del 01/08/2026: 758,30 contanti + 1.620,70 POS = 2.379,00
CHIUSURA = _xml(2609, MATRICOLA, "758.30", "1620.70", "2162.73", "216.27", 357, "22:30:00")
# Una seconda chiusura legittima dello stesso giorno (150,00)
SECONDA_CHIUSURA = _xml(2610, MATRICOLA, "100.00", "50.00", "136.36", "13.64", 20, "23:50:00")
# Una chiusura con la matricola cambiata dal risigillo (500,00)
ALTRA_MATRICOLA = _xml(9001, "88ABC000001", "300.00", "200.00", "454.55", "45.45", 40, "21:00:00")


async def _esegui(righe_iniziali, xml_da_processare):
    db = MemorySheetsClient()["collaudo"]
    for riga in righe_iniziali:
        await db["corrispettivi"].insert_one(dict(riga))
    servizio = CorrispettiviService(db)
    esiti = [
        await servizio.process_xml(xml, f"chiusura_{n}.xml")
        for n, xml in enumerate(xml_da_processare)
    ]
    righe = [r async for r in db["corrispettivi"].find({"data": GIORNO})]
    totale = round(sum(float(r.get("totale") or 0) for r in righe), 2)
    return esiti, righe, totale


# (caso, righe gia' in archivio, XML in arrivo, righe attese, totale atteso)
SCENARI = [
    ("giornata senza documento + il suo XML: sostituisce",
     [RIGA_SENZA_DOCUMENTO], [CHIUSURA], 1, 2379.00),
    ("due chiusure XML vere dello stesso giorno: si sommano",
     [], [CHIUSURA, SECONDA_CHIUSURA], 1, 2529.00),
    ("matricola cambiata dal risigillo: restano distinte",
     [], [CHIUSURA, ALTRA_MATRICOLA], 2, 2879.00),
    ("giornata senza documento + due chiusure: sostituisce, poi somma",
     [RIGA_SENZA_DOCUMENTO], [CHIUSURA, SECONDA_CHIUSURA], 1, 2529.00),
    ("stesso XML tre volte: una riga sola",
     [], [CHIUSURA, CHIUSURA, CHIUSURA], 1, 2379.00),
]


@pytest.mark.parametrize(
    "caso,iniziali,xml,righe_attese,totale_atteso",
    SCENARI, ids=[s[0] for s in SCENARI],
)
def test_corrispettivi_stessa_giornata(caso, iniziali, xml, righe_attese, totale_atteso):
    _esiti, righe, totale = asyncio.run(_esegui(iniziali, xml))

    assert len(righe) == righe_attese, (
        f"{caso}: {len(righe)} righe invece di {righe_attese}. "
        "Una giornata in piu' e' un ricavo contato due volte."
    )
    assert totale == pytest.approx(totale_atteso, abs=0.01), (
        f"{caso}: totale {totale:.2f} invece di {totale_atteso:.2f}. "
        "Sommare una giornata a se' stessa nasconde il doppio conteggio "
        "dentro una riga sola, dove nessuno lo vede."
    )


def test_i_contanti_non_raddoppiano():
    """Il controllo che ha bocciato la prima correzione tentata.

    Guardare solo il numero di righe non basta: la variante che allargava la
    sola chiave lasciava una riga sola — con 4.758,00 EUR e 1.516,60 di
    contanti invece di 758,30.
    """
    _esiti, righe, _totale = asyncio.run(_esegui([RIGA_SENZA_DOCUMENTO], [CHIUSURA]))

    (riga,) = righe
    assert float(riga["pagato_contanti"]) == pytest.approx(758.30, abs=0.01)
    assert float(riga["pagato_pos"]) == pytest.approx(1620.70, abs=0.01)
    assert len(riga.get("chiusure_xml") or []) == 1, (
        "La riga senza documento e' stata conservata come componente: i suoi "
        "importi verranno sommati a quelli dell'XML."
    )


def test_l_esito_dice_quale_dei_due_casi_e_avvenuto():
    """Sostituire e sommare non sono la stessa cosa: l'esito deve distinguerli."""
    esiti, _righe, _totale = asyncio.run(_esegui([RIGA_SENZA_DOCUMENTO], [CHIUSURA]))
    assert "sostituita" in esiti[0]["message"], esiti[0]["message"]

    esiti, _righe, _totale = asyncio.run(_esegui([], [CHIUSURA, SECONDA_CHIUSURA]))
    assert "sommata" in esiti[1]["message"], esiti[1]["message"]
