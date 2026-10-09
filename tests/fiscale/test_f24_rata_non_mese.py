"""Il campo «rateazione/mese rif.» del modello F24 ha due forme.

Istruzioni dell'Agenzia delle Entrate: ``00MM`` e' il mese di riferimento,
``NNRR`` (NN diverso da 00) e' la rata NN di RR. Il gestionale prendeva
sempre le ultime due cifre come mese: il saldo IRAP 2024 da 5.164,00 EUR
(«0101», rata unica) risultava di gennaio, la TARI «03/03 2021» di marzo, e
un'analisi per mese spostava tributi annuali su un mese che non esiste.

Casi presi dall'archivio (27/09/2026): 12 righe di modello (3800, 2001,
3812, 6494) e 79 righe di quietanza (2001, 2003, 6099, 3800, 3812, 3944,
3945, 3946, TEFA).
"""
import pytest

from app.engines import tributi_engine as te
from app.services import f24_controllo_incrociato as registro
from app.services.f24_parser import _period_from_words


@pytest.mark.parametrize("valore, mese", [
    ("0012", "12"), ("00/05", "05"), ("0101", "00"), ("0202", "00"),
    ("0303", "00"), ("0000", "00"), ("", "00"), (None, "00"), ("0013", "00"),
])
def test_mese_da_rateazione(valore, mese):
    assert te.mese_da_rateazione(valore) == mese


@pytest.mark.parametrize("valore, atteso", [
    ("00/12 2024", (12, 2024)),
    ("0005 2025", (5, 2025)),
    ("01/01 2022", None),
    ("03/03 2021", None),
    ("00/00 2021", None),
    ("05/2025", (5, 2025)),
])
def test_parse_periodo_non_prende_la_rata_per_un_mese(valore, atteso):
    assert te._parse_periodo(valore) == atteso


def _parole(*token):
    # colonne della quietanza AdE: il periodo sta fra x=300 e x=410
    return [(310.0 + i * 20, t) for i, t in enumerate(token)]


def test_quietanza_rata_unica_resta_annuale():
    esito = _period_from_words(_parole("01/01", "2025"))
    assert esito["periodo_riferimento"] == "2025"
    assert esito["rateazione"] == "0101"
    assert esito["periodo_raw"] == "01/01 2025"


def test_quietanza_terza_rata_non_e_marzo():
    esito = _period_from_words(_parole("03/03", "2021"))
    assert esito["periodo_riferimento"] == "2021"
    assert esito["rateazione"] == "0303"


def test_quietanza_mese_vero_resta_mese():
    assert _period_from_words(_parole("00/12", "2024"))["periodo_riferimento"] == "12/2024"
    assert "rateazione" not in _period_from_words(_parole("00/12", "2024"))
    assert _period_from_words(_parole("12", "2021"))["periodo_riferimento"] == "12/2021"


def test_quietanza_mese_zero_e_solo_anno():
    assert _period_from_words(_parole("00/00", "2021"))["periodo_riferimento"] == "2021"


def test_riga_archiviata_col_mese_sbagliato_si_legge_annuale():
    """Le righe gia' in archivio portano ancora mese '01': il lettore le
    riconosce dalla rateazione e non le mette a gennaio."""
    modello = {"codice_tributo": "3800", "rateazione": "0101", "mese": "01",
               "anno": "2024", "periodo_riferimento": "01/2024"}
    quietanza = {"codice_tributo": "3944", "periodo_raw": "03/03 2021",
                 "periodo_riferimento": "03/2021"}
    assert registro.periodo_riga(modello) == {"mese": None, "anno": 2024}
    assert registro.periodo_riga(quietanza) == {"mese": None, "anno": 2021}


def test_riga_mensile_resta_mensile():
    riga = {"codice_tributo": "1001", "rateazione": "0009", "mese": "09", "anno": "2025"}
    assert registro.periodo_riga(riga) == {"mese": 9, "anno": 2025}


def test_periodo_prevalente_ignora_le_rate():
    f24 = {"sezione_regioni": [
        {"codice_tributo": "3800", "rateazione": "0101", "periodo_riferimento": "01/2024"},
        {"codice_tributo": "3802", "rateazione": "0005", "periodo_riferimento": "05/2024"},
    ]}
    assert te.periodo_prevalente(f24) == (5, 2024)


def test_bonifica_riallinea_le_righe_archiviate_ed_e_idempotente():
    import asyncio

    from app.services.archivio_documenti_memoria import ArchivioDocumenti
    from app.services.bonifiche_automatiche import riallinea_rate_f24

    async def scenario():
        db = ArchivioDocumenti()
        await db["f24_unificato"].insert_one({"id": "F1", "sezione_regioni": [
            {"codice_tributo": "3800", "rateazione": "0101", "mese": "01", "anno": "2024",
             "periodo_riferimento": "01/2024", "importo_debito": 5164.0},
            {"codice_tributo": "3802", "rateazione": "0005", "mese": "05", "anno": "2024",
             "periodo_riferimento": "05/2024"},
        ]})
        await db["quietanze_f24"].insert_one({"id": "Q1", "sezione_tributi_locali": [
            {"codice_tributo": "TEFA", "periodo_raw": "03/03 2021", "periodo_riferimento": "03/2021",
             "importo_debito_cents": 3500},
        ]})
        primo = await riallinea_rate_f24(db)
        secondo = await riallinea_rate_f24(db)
        f1 = await db["f24_unificato"].find_one({"id": "F1"})
        q1 = await db["quietanze_f24"].find_one({"id": "Q1"})
        return primo, secondo, f1, q1

    primo, secondo, f1, q1 = asyncio.run(scenario())
    assert primo == {"documenti": 2, "righe": 2}
    assert secondo == {"documenti": 0, "righe": 0}
    irap, add_reg = f1["sezione_regioni"]
    assert (irap["mese"], irap["periodo_riferimento"], irap["importo_debito"]) == ("00", "2024", 5164.0)
    assert (add_reg["mese"], add_reg["periodo_riferimento"]) == ("05", "05/2024")
    tefa = q1["sezione_tributi_locali"][0]
    assert (tefa["rateazione"], tefa["periodo_riferimento"], tefa["importo_debito_cents"]) == ("0303", "2021", 3500)
