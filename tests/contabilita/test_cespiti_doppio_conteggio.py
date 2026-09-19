"""Audit 19/09/2026, punto 3 — doppio conteggio costo/cespite.

Prima: quando una riga fattura generava un cespite (`app/handlers/cespiti.py`),
`registra_fattura` registrava COMUNQUE l'intero imponibile come costo pieno,
senza sapere che una parte era già stata capitalizzata a parte nel registro
`cespiti`. Lo stesso importo pesava due volte: costo pieno in conto economico
+ immobilizzazione nell'attivo di bilancio.

Ora `registra_fattura` legge i cespiti già collegati alla fattura (fonte
unica: `classify_asset()`, chiamato una sola volta da
`handler_auto_cespite_da_fattura`) e instrada quella quota su un conto
ATTIVO (`app.routers.cespiti.CATEGORIA_CESPITE_CONTO_ATTIVO`) invece che sul
conto costo — mai su entrambi.
"""
import asyncio

import app.services.registrazione_contabile as motore
from app.services.sheets_document_store import MemorySheetsClient


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _db():
    return MemorySheetsClient()["test"]


def _cespite(fattura_id, categoria, valore, descrizione="Bene"):
    return {
        "id": f"cesp-{fattura_id}-{categoria}",
        "fattura_id": fattura_id,
        "categoria": categoria,
        "valore_acquisto": valore,
        "descrizione": descrizione,
    }


def test_riga_interamente_cespite_non_finisce_anche_sul_conto_costo():
    db = _db()
    _run(db["cespiti"].insert_one(_cespite("F-CESP-1", "attrezzature", 3500.0, "Lavastoviglie industriale")))

    fattura = {
        "id": "F-CESP-1", "total_amount": 4200.0, "total_tax": 700.0,
        "iva_detraibile": 700.0, "imponibile": 3500.0,
        "invoice_date": "2026-05-01", "invoice_number": "10/2026",
        "supplier_name": "Forniture Cucina Srl",
    }
    mov = _run(motore.registra_fattura(db, fattura))["movimento"]

    conti_costo = [r for r in mov["righe"] if r["conto_codice"] == "05.01.01" and r["dare"] > 0]
    assert conti_costo == [], "l'intero imponibile e' un cespite: non deve restare nulla sul conto costo"

    riga_cespite = next(r for r in mov["righe"] if r["conto_codice"] == "01.06.02")
    assert riga_cespite["dare"] == 3500.0
    assert "Lavastoviglie" in riga_cespite["descrizione"]

    assert mov["cespiti_capitalizzati"] == 3500.0
    assert mov["totale_dare"] == mov["totale_avere"] == 4200.0


def test_fattura_mista_costo_e_cespite_si_dividono_senza_sovrapporsi():
    db = _db()
    _run(db["cespiti"].insert_one(_cespite("F-CESP-2", "attrezzature", 3500.0)))

    fattura = {
        # 5000 di imponibile: 3500 e' il cespite gia' registrato, 1500 resta costo.
        "id": "F-CESP-2", "total_amount": 6100.0, "total_tax": 1100.0,
        "iva_detraibile": 1100.0, "imponibile": 5000.0,
        "invoice_date": "2026-05-02",
    }
    mov = _run(motore.registra_fattura(db, fattura))["movimento"]

    righe = {r["conto_codice"]: r for r in mov["righe"]}
    assert righe["05.01.01"]["dare"] == 1500.0
    assert righe["01.06.02"]["dare"] == 3500.0
    assert mov["cespiti_capitalizzati"] == 3500.0
    # né più né meno dell'imponibile totale della fattura
    assert round(righe["05.01.01"]["dare"] + righe["01.06.02"]["dare"], 2) == 5000.0
    assert mov["totale_dare"] == mov["totale_avere"] == 6100.0


def test_fattura_senza_cespiti_si_comporta_come_prima():
    db = _db()
    fattura = {
        "id": "F-NO-CESP", "total_amount": 1220.0, "total_tax": 220.0,
        "iva_detraibile": 220.0, "imponibile": 1000.0, "invoice_date": "2026-05-03",
    }
    mov = _run(motore.registra_fattura(db, fattura))["movimento"]
    righe = {r["conto_codice"]: r for r in mov["righe"]}
    assert righe["05.01.01"]["dare"] == 1000.0
    assert "01.06.02" not in righe
    assert "cespiti_capitalizzati" not in mov


def test_piu_categorie_di_cespite_nella_stessa_fattura_hanno_conti_distinti():
    db = _db()
    _run(db["cespiti"].insert_one(_cespite("F-CESP-3", "attrezzature", 1000.0)))
    _run(db["cespiti"].insert_one(_cespite("F-CESP-3", "mobili_arredi", 500.0)))

    fattura = {
        "id": "F-CESP-3", "total_amount": 1830.0, "total_tax": 330.0,
        "iva_detraibile": 330.0, "imponibile": 1500.0, "invoice_date": "2026-05-04",
    }
    mov = _run(motore.registra_fattura(db, fattura))["movimento"]
    righe = {r["conto_codice"]: r for r in mov["righe"]}
    assert righe["01.06.02"]["dare"] == 1000.0  # attrezzature
    assert righe["01.06.04"]["dare"] == 500.0   # mobili e arredi
    assert "05.01.01" not in righe
    assert mov["cespiti_capitalizzati"] == 1500.0


def test_cespite_superiore_allimponibile_segnala_anomalia_senza_sballare_la_quadratura():
    """Dato incoerente (es. cespite duplicato/errato): la scrittura resta
    quadrata (mai un buco), ma l'anomalia va SEGNALATA, mai silenziosa."""
    db = _db()
    _run(db["cespiti"].insert_one(_cespite("F-ANOM-1", "attrezzature", 5000.0)))

    fattura = {
        "id": "F-ANOM-1", "total_amount": 3660.0, "total_tax": 660.0,
        "iva_detraibile": 660.0, "imponibile": 3000.0, "invoice_date": "2026-05-05",
    }
    mov = _run(motore.registra_fattura(db, fattura))["movimento"]
    righe = {r["conto_codice"]: r for r in mov["righe"]}
    assert "05.01.01" not in righe
    assert righe["01.06.02"]["dare"] == 3000.0  # capitalizzazione limitata al costo disponibile
    assert mov["totale_dare"] == mov["totale_avere"] == 3660.0

    segnalazioni = _run(db["agenti_segnalazioni"].find(
        {"tipo": "cespite_doppio_conteggio_potenziale"}
    ).to_list(10))
    assert len(segnalazioni) == 1
    assert segnalazioni[0]["fattura_id"] == "F-ANOM-1"


def test_registrazione_idempotente_anche_con_cespite_collegato():
    db = _db()
    _run(db["cespiti"].insert_one(_cespite("F-CESP-IDEM", "forni", 2000.0)))
    fattura = {
        "id": "F-CESP-IDEM", "total_amount": 2440.0, "total_tax": 440.0,
        "iva_detraibile": 440.0, "imponibile": 2000.0, "invoice_date": "2026-05-06",
    }
    r1 = _run(motore.registra_fattura(db, fattura))
    r2 = _run(motore.registra_fattura(db, fattura))
    assert r1["stato"] == "registrato"
    assert r2["stato"] == "gia_registrato"
    assert len(_run(db["movimenti_contabili"].find({}).to_list(10))) == 1


def test_verifica_doppio_conteggio_endpoint_segnala_scritture_pre_fix(monkeypatch):
    """Simula una fattura registrata PRIMA di questa correzione (movimento
    senza `cespiti_capitalizzati` benché esista un cespite collegato): il
    controllo read-only deve vederla, per il titolare/commercialista."""
    import asyncio as _asyncio
    from app.routers import cespiti as cespiti_router
    from app.database import Database

    db = _db()
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))

    _run(db["cespiti"].insert_one(_cespite("F-STORICA-1", "forni", 4000.0)))
    _run(db["movimenti_contabili"].insert_one({
        "id": "mov-storico", "tipo": "fattura_acquisto", "fattura_id": "F-STORICA-1",
        "numero_registrazione": 1,
        # nessun campo cespiti_capitalizzati: e' la scrittura pre-fix, tutto
        # l'imponibile e' finito sul costo pieno.
    }))

    esito = _run(cespiti_router.verifica_doppio_conteggio_costo_cespite())
    assert esito["stato"] == "critico"
    assert esito["num_doppio_conteggio_sospetto"] == 1
    trovato = esito["doppio_conteggio_sospetto"][0]
    assert trovato["fattura_id"] == "F-STORICA-1"
    assert trovato["cespiti_valore_atteso"] == 4000.0
    assert trovato["cespiti_capitalizzati_in_scrittura"] == 0.0
