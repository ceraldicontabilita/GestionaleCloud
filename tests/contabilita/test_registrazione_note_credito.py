"""Audit 19/09/2026 — incoerenza tra Prima Nota Cassa/Banca e libro giornale
sulle note di credito ricevute (TD04/TD08, FatturaPA).

Prima Nota Cassa/Banca (`app/routers/prima_nota_module/sync.py::
determina_tipo_movimento_fattura`) tratta già correttamente una nota di
credito ricevuta come categoria "Nota credito fornitore" (riduce quanto
dovuto al fornitore). Il libro giornale in partita doppia
(`app/services/registrazione_contabile.py::registra_fattura`) non leggeva
invece mai `tipo_documento`: registrava OGNI fattura, nota di credito
compresa, come un acquisto normale — DARE costo/IVA a credito, AVERE debito
v/fornitore — raddoppiando anziché ridurre costo, IVA a credito e debito
verso il fornitore.

Questi test dimostrano, con numeri concreti, che una TD04 genera la
scrittura ECONOMICAMENTE INVERSA rispetto a una TD01 di pari importo:
AVERE costo, AVERE IVA a credito, DARE debito v/fornitore.
"""
import asyncio

import app.services.registrazione_contabile as motore
from app.services.archivio_documenti_memoria import MemorySheetsClient


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _db():
    return MemorySheetsClient()["test"]


def _fattura(id_, tipo_documento, imponibile=500.0, iva=110.0):
    totale = round(imponibile + iva, 2)
    return {
        "id": id_,
        "tipo_documento": tipo_documento,
        "total_amount": totale,
        "total_tax": iva,
        "iva_detraibile": iva,
        "imponibile": imponibile,
        "invoice_date": "2026-09-10",
        "invoice_number": "45/2026",
        "supplier_name": "Fornitore Bar Srl",
    }


def test_nota_credito_td04_riduce_costo_iva_e_debito_invece_di_aumentarli():
    """Imponibile 500 + IVA 110 = 610: una TD04 con questi valori deve
    generare l'esatto contrario, riga per riga, di una TD01 identica."""
    db = _db()

    fatt_normale = _fattura("F-TD01-CFR", "TD01")
    nota_credito = _fattura("F-TD04-CFR", "TD04")

    mov_normale = _run(motore.registra_fattura(db, fatt_normale))["movimento"]
    mov_nc = _run(motore.registra_fattura(db, nota_credito))["movimento"]

    righe_normale = {r["conto_codice"]: r for r in mov_normale["righe"]}
    righe_nc = {r["conto_codice"]: r for r in mov_nc["righe"]}

    # Stessi conti (nessuna divergenza di piano dei conti tra TD01 e TD04).
    assert set(righe_normale) == set(righe_nc) == {"05.01.01", "01.04.01", "02.01.01"}

    # Fattura normale: DARE costo 500, DARE IVA a credito 110, AVERE debito 610.
    assert righe_normale["05.01.01"]["dare"] == 500.0 and righe_normale["05.01.01"]["avere"] == 0
    assert righe_normale["01.04.01"]["dare"] == 110.0 and righe_normale["01.04.01"]["avere"] == 0
    assert righe_normale["02.01.01"]["avere"] == 610.0 and righe_normale["02.01.01"]["dare"] == 0

    # Nota di credito: ESATTO CONTRARIO — AVERE costo 500 (lo riduce), AVERE
    # IVA a credito 110 (la riduce), DARE debito v/fornitore 610 (lo riduce).
    assert righe_nc["05.01.01"]["avere"] == 500.0 and righe_nc["05.01.01"]["dare"] == 0
    assert righe_nc["01.04.01"]["avere"] == 110.0 and righe_nc["01.04.01"]["dare"] == 0
    assert righe_nc["02.01.01"]["dare"] == 610.0 and righe_nc["02.01.01"]["avere"] == 0

    # Descrizione chiaramente marcata "Nota di credito", come già fa il
    # ledger di cassa/banca in sync.py per la stessa categoria.
    assert mov_nc["descrizione"].startswith("Nota di credito")
    assert all("Nota di credito" in r["descrizione"] for r in mov_nc["righe"])
    assert mov_nc["nota_di_credito"] is True
    assert "nota_di_credito" not in mov_normale


def test_nota_credito_td08_si_comporta_come_td04():
    """TD08 (nota di credito semplificata) segue la stessa logica di TD04:
    stessa costante `TIPI_NOTA_CREDITO`, stesso comportamento."""
    db = _db()
    mov = _run(motore.registra_fattura(db, _fattura("F-TD08", "TD08")))["movimento"]
    righe = {r["conto_codice"]: r for r in mov["righe"]}
    assert righe["05.01.01"]["avere"] == 500.0
    assert righe["01.04.01"]["avere"] == 110.0
    assert righe["02.01.01"]["dare"] == 610.0


def test_nota_credito_td04_quadra_dare_uguale_avere():
    db = _db()
    mov = _run(motore.registra_fattura(db, _fattura("F-TD04-QUADRA", "TD04")))["movimento"]
    assert mov["totale_dare"] == mov["totale_avere"] == 610.0
    somma_dare = round(sum(r["dare"] for r in mov["righe"]), 2)
    somma_avere = round(sum(r["avere"] for r in mov["righe"]), 2)
    assert somma_dare == somma_avere == 610.0


def test_nota_credito_td04_e_idempotente():
    """Una seconda registrazione della stessa nota di credito non deve
    duplicare la scrittura (stessa garanzia già valida per le fatture TD01)."""
    db = _db()
    fattura = _fattura("F-TD04-IDEM", "TD04")

    primo = _run(motore.registra_fattura(db, fattura))
    secondo = _run(motore.registra_fattura(db, fattura))

    assert primo["stato"] == "registrato"
    assert secondo["stato"] == "gia_registrato"
    scritture = _run(db["movimenti_contabili"].find({}).to_list(10))
    assert len(scritture) == 1
    assert scritture[0]["idempotency_key"] == "reg:fattura:F-TD04-IDEM"


def test_nota_credito_td04_non_genera_mai_un_cespite_anche_se_collegata():
    """Guardia difensiva (audit 19/09/2026 punto 4): anche se un record
    `cespiti` risultasse (per errore a monte) collegato alla stessa
    fattura_id di una nota di credito, la nota di credito non deve MAI
    capitalizzare — riduce un costo già registrato, non ne crea uno nuovo
    da immobilizzare."""
    db = _db()
    _run(db["cespiti"].insert_one({
        "id": "cesp-nc-1",
        "fattura_id": "F-TD04-CESPITE",
        "categoria": "attrezzature",
        "valore_acquisto": 500.0,
        "descrizione": "Forno (da nota di credito, collegamento errato)",
    }))

    nota_credito = _fattura("F-TD04-CESPITE", "TD04")
    mov = _run(motore.registra_fattura(db, nota_credito))["movimento"]

    # Nessuna riga sul conto attivo dei cespiti (01.06.02 = attrezzature).
    assert "01.06.02" not in {r["conto_codice"] for r in mov["righe"]}
    assert "cespiti_capitalizzati" not in mov
    # L'intero imponibile resta sul conto costo, in AVERE (storno pieno).
    righe = {r["conto_codice"]: r for r in mov["righe"]}
    assert righe["05.01.01"]["avere"] == 500.0
    assert mov["totale_dare"] == mov["totale_avere"] == 610.0


def test_nota_credito_td04_via_registra_documento_import_non_alza_debito():
    """Stesso percorso usato dall'import reale (`registra_documento_import`,
    unico aggancio delle pipeline fatture): conferma che il fix vale anche
    da questo ingresso, non solo chiamando `registra_fattura` a mano."""
    db = _db()
    fattura = _fattura("F-TD04-IMPORT", "TD04")
    _run(db["invoices"].insert_one(dict(fattura)))

    esito = _run(motore.registra_documento_import(db, "fattura", fattura))
    assert esito["stato"] == "registrato"

    mov = esito["movimento"]
    righe = {r["conto_codice"]: r for r in mov["righe"]}
    # Il debito v/fornitore e' in DARE (lo riduce), mai in AVERE (lo aumenterebbe).
    assert righe["02.01.01"]["dare"] == 610.0
    assert righe["02.01.01"]["avere"] == 0
