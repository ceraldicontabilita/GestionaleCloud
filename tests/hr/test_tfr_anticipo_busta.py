"""Anticipo TFR pagato dentro la busta (voce 000081): letto, registrato una volta sola.

Caso reale (02/10/2026): Capezzuto, busta di luglio 2026 (Libro unico del
07/08/2026): «000081 Anticipazione T.F.R. 1.800,00», netto 2.477,00, TFR tassato
a parte. Il lettore non la riconosceva e l'acconto restava solo nel vecchio
database «Presenze»: doveva nascere dalla busta, col motore degli acconti TFR.
"""
import asyncio
from decimal import Decimal

from app.parsers.cedolino_voci import anticipo_tfr_in_busta
from app.services import cedolini_hr_riverifica as rv
from app.services import tfr_anticipo_busta as tab
from app.services.archivio_documenti_memoria import ArchivioDocumenti

#: Il testo come lo restituisce il PDF: l'importo va a capo dopo la descrizione.
TESTO_BUSTA = """
* * Z50022 14ma Mensilita' 8,67192 0,03666 ORE
0,32
*
000081 Anticipazione T.F.R.
1.800,00
*
ZP8140 Rivalutaz. Fondo post 2000 ( 2,50 )
F06992 Imponibile T.F.R. (2) 1.797,50
F07020 IRPEF netta TFR 413,43
TFR a fondi Anticipi
1.800,00
"""

CF = "CPZLSN86D02F839I"


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_la_voce_si_legge_anche_con_l_importo_a_capo():
    voce = anticipo_tfr_in_busta(TESTO_BUSTA)
    assert voce == {"codice": "000081", "descrizione": "ANTICIPAZIONE T.F.R.", "importo": "1.800,00"}


def test_il_progressivo_e_l_imponibile_tfr_non_sono_l_anticipo():
    senza_voce = TESTO_BUSTA.replace("000081 Anticipazione T.F.R.\n1.800,00", "")
    assert anticipo_tfr_in_busta(senza_voce) is None
    assert anticipo_tfr_in_busta("") is None and anticipo_tfr_in_busta(None) is None


def test_importo_italiano_e_mai_zero():
    assert tab.importo_it("1.800,00") == Decimal("1800.00")
    assert tab.importo_it("124,27") == Decimal("124.27")
    assert tab.importo_it("0,00") is None and tab.importo_it("abc") is None and tab.importo_it(None) is None


async def _db():
    db = ArchivioDocumenti()
    await db["dipendenti"].insert_one({
        "id": "43e30e28", "codice_fiscale": CF, "nome_completo": "Alessandro Capezzuto",
        "tfr_accantonato": 2500.0})
    return db


def test_registra_l_acconto_scala_il_fondo_e_scrive_il_giornale():
    async def scenario():
        db = await _db()
        esito = await tab.registra_anticipo_tfr_da_busta(
            db, codice_fiscale=CF, anno=2026, mese=7, importo="1.800,00")
        acconto = await db["acconti_dipendenti"].find_one({"id": f"tfr-busta-{CF}-202607-000081"})
        dip = await db["dipendenti"].find_one({"id": "43e30e28"})
        scritture = await db["movimenti_contabili"].find({"tipo": "acconto_tfr"}).to_list(10)
        return esito, acconto, dip, scritture

    esito, acconto, dip, scritture = _run(scenario())
    assert esito["esito"] == "registrato" and esito["importo"] == "1800.00"
    assert acconto["tipo"] == "tfr" and acconto["importo"] == 1800.0
    assert acconto["data"] == "2026-07-31" and acconto["tfr_registrato"] is True
    assert acconto["source"] == tab.SORGENTE and acconto["dipendente_id"] == "43e30e28"
    assert dip["tfr_accantonato"] == 700.0
    assert len(scritture) == 1
    dare = sum(r.get("dare", 0) for r in scritture[0]["righe"])
    avere = sum(r.get("avere", 0) for r in scritture[0]["righe"])
    assert round(dare, 2) == round(avere, 2) == 1800.0


def test_il_secondo_passaggio_non_scala_ne_scrive_di_nuovo():
    async def scenario():
        db = await _db()
        for _ in range(3):
            esito = await tab.registra_anticipo_tfr_da_busta(
                db, codice_fiscale=CF, anno="2026", mese="7", importo="1.800,00")
        return esito, await db["dipendenti"].find_one({"id": "43e30e28"}), \
            await db["acconti_dipendenti"].find({}).to_list(10), \
            await db["movimenti_contabili"].find({"tipo": "acconto_tfr"}).to_list(10)

    esito, dip, acconti, scritture = _run(scenario())
    assert esito["esito"] == "gia_registrato"
    assert dip["tfr_accantonato"] == 700.0  # scalato una volta sola
    assert len(acconti) == 1 and len(scritture) == 1


def test_un_acconto_inserito_ma_senza_giornale_si_completa_senza_duplicare():
    """Interrotto fra l'inserimento e il motore: il ripasso lo porta a termine."""
    async def scenario():
        db = await _db()
        await db["acconti_dipendenti"].insert_one({
            "id": f"tfr-busta-{CF}-202607-000081", "dipendente_id": "43e30e28", "tipo": "tfr",
            "importo": 1800.0, "data": "2026-07-31", "note": "", "created_at": "2026-08-07T00:00:00"})
        esito = await tab.registra_anticipo_tfr_da_busta(
            db, codice_fiscale=CF, anno=2026, mese=7, importo="1.800,00")
        return esito, await db["acconti_dipendenti"].find({}).to_list(10), \
            await db["movimenti_contabili"].find({"tipo": "acconto_tfr"}).to_list(10)

    esito, acconti, scritture = _run(scenario())
    assert esito["esito"] == "registrato"
    assert len(acconti) == 1 and acconti[0]["tfr_registrato"] is True and len(scritture) == 1


def test_casi_che_non_si_registrano():
    async def scenario():
        db = await _db()
        return [
            await tab.registra_anticipo_tfr_da_busta(db, codice_fiscale=CF, anno=2026, mese=7, importo="0,00"),
            await tab.registra_anticipo_tfr_da_busta(db, codice_fiscale=CF, anno=2026, mese=13, importo="10,00"),
            await tab.registra_anticipo_tfr_da_busta(db, codice_fiscale="XXXXXX00X00X000X", anno=2026,
                                                     mese=7, importo="1.800,00"),
            await db["acconti_dipendenti"].find({}).to_list(10),
        ]

    importo, periodo, sconosciuto, acconti = _run(scenario())
    assert importo["esito"] == "importo_illeggibile"
    assert periodo["esito"] == "periodo_illeggibile"
    assert sconosciuto["esito"] == "dipendente_non_trovato"
    assert acconti == []


def test_registra_dalla_busta_ignora_le_buste_senza_anticipo():
    async def scenario():
        db = await _db()
        senza = await tab.registra_dalla_busta(db, {"codice_fiscale": CF, "anno": 2026, "mese": 6,
                                                    "dati_chiave": {"rateo_13ma_importo": "124,27"}})
        con = await tab.registra_dalla_busta(db, {"codice_fiscale": CF, "anno": 2026, "mese": 7,
                                                  "dati_chiave": {"anticipo_tfr_busta": "1.800,00",
                                                                  "anticipo_tfr_voce": "000081"}})
        return senza, con

    senza, con = _run(scenario())
    assert senza is None and con["esito"] == "registrato"


def test_il_ripasso_hr_conserva_i_campi_dell_anticipo_nei_dati_chiave():
    """La riga HR non li aveva: il ripasso (v4) li scrive accanto ai ratei, senza perdere il resto."""
    riga = {"id": "r1", "cf": CF, "anno": "2026", "mese": "7", "tipo": "ordinario", "netto": "2477",
            "dati_chiave": {"rateo_13ma_importo": "124,27"}}
    busta = {"codice_fiscale": CF, "anno": 2026, "mese": 7, "tipo_cedolino": "mensile", "netto": 2477.0,
             "stato_netto": "NETTO_VERIFICATO_DA_CEDOLINO",
             "dati_chiave": {"rateo_13ma_importo": "124,27", "anticipo_tfr_busta": "1.800,00",
                             "anticipo_tfr_voce": "000081"}}
    esito = rv.busta_della_riga(riga, [busta])
    assert esito["ratei"]["anticipo_tfr_busta"] == "1.800,00"
    patch = rv.correzione(riga, esito, "2026-10-02T03:00")
    assert patch["dati_chiave"] == {"rateo_13ma_importo": "124,27", "anticipo_tfr_busta": "1.800,00",
                                    "anticipo_tfr_voce": "000081"}
    assert patch["netto_riverificato_versione"] == "riverifica_pdf_v4"
