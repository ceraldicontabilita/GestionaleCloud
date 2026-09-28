"""Buste paga: la «STAMPA DI CONTROLLO» si toglie da Drive solo se c'e' la
definitiva identica (codice fiscale, periodo, netto); una busta gia' in
archivio non e' un errore dello smistatore."""
import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.services import cedolini_stampe_controllo as sc
from app.services import drive_cartella_unica as cu
from tests.documenti.test_drive_cartella_unica import CARTELLE, DriveFinto, ambiente  # noqa: F401


def run(coro):
    return asyncio.run(coro)


def test_riconosce_la_stampa_di_controllo_zucchetti():
    assert sc.e_stampa_di_controllo("ELABORAZIONE VERSIONE25.11.00 DI CONTROLLO ROSSI")
    assert sc.e_stampa_di_controllo("STAMPA IMPORTOSBASE DI CONTROLLO")
    assert not sc.e_stampa_di_controllo("ELABORAZIONE VERSIONE25.11.00 CEDOLINO PAGA")
    assert not sc.e_stampa_di_controllo("")


def test_raggruppa_solo_buste_con_lo_stesso_nome():
    files = [
        {"id": "a", "name": "ROSSI MARIO - LUL - 2025-12.pdf"},
        {"id": "b", "name": "ROSSI MARIO - LUL - 2025-12 (dup2).pdf"},
        {"id": "c", "name": "ROSSI MARIO - LUL - 2026-01.pdf"},
        {"id": "d", "name": "fattura (dup1).pdf"},
        {"id": "e", "name": "fattura.pdf"},
    ]
    gruppi = sc.raggruppa(files)
    assert list(gruppi) == ["rossi mario - lul - 2025-12"]
    assert [f["id"] for f in gruppi["rossi mario - lul - 2025-12"]] == ["a", "b"]


BUSTA = ("RSSMRA80A01F839X", 2025, 12, "1408.00")


def test_la_bozza_va_via_solo_con_la_definitiva_identica():
    definitiva, bozza = {"id": "def"}, {"id": "bozza"}
    assert sc.bozze_superate([(definitiva, False, {BUSTA}), (bozza, True, {BUSTA})]) == [
        (bozza, {BUSTA: "def"})]
    # Netto diverso: non e' la stessa busta, la bozza resta.
    altro_netto = (*BUSTA[:3], "1400.00")
    assert sc.bozze_superate([(definitiva, False, {altro_netto}), (bozza, True, {BUSTA})]) == []
    # Solo bozze: nessuna definitiva, restano tutte.
    assert sc.bozze_superate([(definitiva, True, {BUSTA}), (bozza, True, {BUSTA})]) == []
    # Bozza illeggibile (nessuna busta): non si tocca.
    assert sc.bozze_superate([(definitiva, False, {BUSTA}), (bozza, True, set())]) == []


def test_pulisci_archivio_cestina_la_bozza_e_riaggancia_la_busta(ambiente, monkeypatch):  # noqa: F811
    drive, _, _ = ambiente
    db = AsyncMongoMockClient()["t"]
    drive.aggiungi("def", "ROSSI - LUL - 2025-12.pdf", b"%PDF definitiva", "elaborate")
    drive.aggiungi("bozza", "ROSSI - LUL - 2025-12 (dup1).pdf", b"%PDF bozza", "elaborate")
    drive.aggiungi("sola", "BIANCHI - LUL - 2025-12 (dup1).pdf", b"%PDF bozza sola", "elaborate")
    drive.aggiungi("sola2", "BIANCHI - LUL - 2025-12.pdf", b"%PDF bozza sola 2", "elaborate")
    letture = {
        b"%PDF definitiva": (False, {BUSTA}),
        b"%PDF bozza": (True, {BUSTA}),
        b"%PDF bozza sola": (True, {("BNCLRA", 2025, 12, "900.00")}),
        b"%PDF bozza sola 2": (True, {("BNCLRA", 2025, 12, "900.00")}),
    }
    monkeypatch.setattr(sc, "leggi", lambda contenuto: letture[contenuto])
    run(db["cedolini"].insert_one({"id": "c1", "codice_fiscale": BUSTA[0], "anno": 2025,
                                   "mese": 12, "netto": 1408.0, "drive_file_id": "bozza"}))

    esito = run(sc.pulisci_archivio(db))
    assert (esito["gruppi"], esito["tolte"], esito["errori"]) == (2, 1, 0)
    assert drive.cestinati == ["bozza"] and drive.eliminati == []
    assert run(db["cedolini"].find_one({"id": "c1"}))["drive_file_id"] == "def"
    assert run(db[cu.REGISTRO].find_one({"id": "bozza"}))["esito"] == "stampa_controllo_tolta"

    # Secondo giro: gruppi gia' visti e invariati non si riscaricano.
    monkeypatch.setattr(sc, "leggi", lambda contenuto: (_ for _ in ()).throw(AssertionError))
    assert run(sc.pulisci_archivio(db))["controllati"] == 0


def test_bozza_del_titolare_va_in_doppioni(ambiente, monkeypatch):  # noqa: F811
    drive, _, _ = ambiente
    drive.cestino_vietato = True
    db = AsyncMongoMockClient()["t"]
    drive.aggiungi("def", "ROSSI - LUL - 2025-12.pdf", b"%PDF definitiva", "elaborate")
    drive.aggiungi("bozza", "ROSSI - LUL - 2025-12 (dup1).pdf", b"%PDF bozza", "elaborate")
    monkeypatch.setattr(sc, "leggi", lambda c: (c == b"%PDF bozza", {BUSTA}))
    assert run(sc.pulisci_archivio(db))["tolte"] == 1
    assert drive.file["bozza"]["parent"] == "doppioni" and drive.eliminati == []


def test_buste_gia_presenti_tornano_in_coda(ambiente):  # noqa: F811
    drive, smistati, esiti = ambiente
    db = AsyncMongoMockClient()["t"]
    drive.aggiungi("g1", "ROSSI - LUL - 2026-03 (dup1).pdf", b"%PDF g1", "errori")
    drive.aggiungi("g2", "rotto.pdf", b"%PDF g2", "errori")
    run(db[cu.REGISTRO].insert_many([
        {"id": "g1", "tipo": "cedolino", "cartella": cu.ERRORI,
         "motivo": "Cedolino non registrato: 1 buste lette"},
        {"id": "g2", "tipo": "cedolino", "cartella": cu.ERRORI,
         "motivo": "Cedolino non registrato: nessuna busta e nessun foglio presenze riconosciuto"},
    ]))
    esiti["ROSSI - LUL - 2026-03 (dup1).pdf"] = {
        "success": True, "duplicate": True, "tipo_rilevato": "cedolino"}

    esito = run(cu.giro(db))
    assert esito["buste_rimesse_in_coda"] == 1
    assert drive.file["g1"]["parent"] == "elaborate"  # riletta: gia' in archivio
    assert drive.file["g2"]["parent"] == "errori"  # errore vero: resta


def test_motore_busta_gia_in_archivio_e_un_successo(monkeypatch):
    import base64

    from app.services import cedolini_manager as cm
    from app.services import cedolini_motore

    monkeypatch.setattr(cedolini_motore, "leggi_pdf", lambda contenuto: {
        "esito": cedolini_motore.ESITO_BUSTE, "motivo": "1 buste lette", "presenze": [],
        "buste": [{"codice_fiscale": BUSTA[0], "anno": 2025, "mese": 12, "netto": 1408.0,
                   "stato_netto": "NETTO_VERIFICATO_DA_CEDOLINO"}]})

    async def gia(db, ced):
        return {"id": "c1"}

    async def niente(*a, **k):
        return None

    monkeypatch.setattr(cm, "_busta_gia_in_archivio", gia)
    monkeypatch.setattr(cm, "_scrivi_scheda", niente)
    db = AsyncMongoMockClient()["t"]
    esito = run(cm.processa_tutti_cedolini_pdf(db, base64.b64encode(b"%PDF").decode(), "a.pdf"))
    assert esito["success"] is True and esito["gia_presenti"] == 1


def test_pulisci_archivio_senza_tetto_controlla_tutti_i_gruppi(ambiente, monkeypatch):  # noqa: F811
    drive, _, _ = ambiente
    db = AsyncMongoMockClient()["t"]
    for i in range(30):
        drive.aggiungi(f"a{i}", f"P{i} - LUL - 2025-12.pdf", f"%PDF a{i}".encode(), "elaborate")
        drive.aggiungi(f"b{i}", f"P{i} - LUL - 2025-12 (dup1).pdf", f"%PDF b{i}".encode(), "elaborate")
    monkeypatch.setattr(sc, "leggi", lambda c: (c.startswith(b"%PDF b"), {BUSTA}))
    esito = run(sc.pulisci_archivio(db, gruppi_per_giro=None))
    assert (esito["controllati"], esito["tolte"]) == (30, 30)


def test_la_coda_legge_prima_le_buste():
    coda = [
        {"id": "p", "name": "estratto.pdf"},
        {"id": "x", "name": "fattura.xml", "createdTime": "2026-09-01"},
        {"id": "b", "name": "ROSSI - CEDOLINO-LUL - 2025-12 (dup1).pdf"},
        {"id": "l", "name": "Libro unico.pdf"},
    ]
    assert [f["id"] for f in cu.ordina_coda(coda)] == ["b", "l", "x", "p"]


def test_buste_in_parallelo_senza_doppioni(ambiente):  # noqa: F811
    drive, smistati, _ = ambiente
    db = AsyncMongoMockClient()["t"]
    drive.aggiungi("c1", "ROSSI - LUL - 2025-12.pdf", b"%PDF busta", "inbox")
    drive.aggiungi("c2", "ROSSI - LUL - 2025-12 (dup1).pdf", b"%PDF busta", "inbox")
    for i in range(4):
        drive.aggiungi(f"v{i}", f"VERDI{i} - LUL - 2025-12.pdf", f"%PDF v{i}".encode(), "inbox")
    esito = run(cu.giro(db))
    assert esito["letti"] == 6
    assert esito["doppioni_cestinati"] == 1 and esito["elaborati"] == 5
    assert len(smistati) == 5


def test_guasto_di_rete_torna_in_coda(ambiente):  # noqa: F811
    drive, _, _ = ambiente
    db = AsyncMongoMockClient()["t"]
    drive.aggiungi("s1", "ROSSI - LUL - 2025-11.pdf", b"%PDF s1", "errori")
    run(db[cu.REGISTRO].insert_one({"id": "s1", "cartella": cu.ERRORI, "esito": "errore",
                                    "motivo": "SSLError: [SSL: WRONG_VERSION_NUMBER] wrong version"}))
    assert run(cu.giro(db))["buste_rimesse_in_coda"] == 1
    assert drive.file["s1"]["parent"] == "elaborate"


def test_busta_parcheggiata_fra_gli_estratti_torna_in_coda(ambiente):  # noqa: F811
    drive, _, _ = ambiente
    db = AsyncMongoMockClient()["t"]
    cu_arretrato = "arretrato"
    drive.aggiungi("t1", "Ceraldi Vincenzo - Tredicesima 2020.pdf", b"%PDF t1", cu_arretrato)
    drive.aggiungi("e1", "Estratto conto 2021.pdf", b"%PDF e1", cu_arretrato)
    run(db[cu.REGISTRO].insert_many([
        {"id": "t1", "nome": "Ceraldi Vincenzo - Tredicesima 2020.pdf", "cartella": cu.ARRETRATO,
         "tipo": "estratto_conto"},
        {"id": "e1", "nome": "Estratto conto 2021.pdf", "cartella": cu.ARRETRATO,
         "tipo": "estratto_conto"},
    ]))
    assert run(cu.giro(db))["buste_rimesse_in_coda"] == 1
    assert drive.file["t1"]["parent"] == "elaborate"
    assert drive.file["e1"]["parent"] == cu_arretrato
