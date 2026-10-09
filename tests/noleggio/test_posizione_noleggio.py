"""Posizione noleggio in partita doppia: costi in DARE, prove in AVERE.

Collaudo del motore `app/services/noleggio/posizione.py` su un archivio in
memoria che riproduce la forma dei dati di produzione (22/09/2026): fatture
noleggio duplicate fra copia `archived` e copia attiva, allocazioni bancarie
confermate, SDD cumulativi che coprono due fatture, verbali della posta con
quietanza PagoPA/PartenoPay, bonifici al Comune di Napoli senza verbale.
"""
import asyncio

import pytest

from app.database import Database
from app.services.archivio_documenti_memoria import ArchivioDocumenti
from app.services.noleggio import posizione as mod
from app.services.noleggio.processors import FILTRO_FATTURA_ATTIVA, scan_fatture_noleggio

ALD = "01924961004"
ARVAL = "04911190488"


def _fattura(_id, uuid, numero, piva, nome, data, totale, linee, **extra):
    return {
        "_id": _id, "id": uuid, "invoice_number": numero, "invoice_date": data,
        "supplier_vat": piva, "supplier_name": nome, "tipo_documento": "TD01",
        "total_amount": totale, "linee": linee, **extra,
    }


def _linea(desc, prezzo, aliquota=22.0):
    return {"descrizione": desc, "prezzo_totale": prezzo, "aliquota_iva": aliquota}


@pytest.fixture
def db(monkeypatch):
    archivio = ArchivioDocumenti("test")
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: archivio))
    return archivio


async def _semina(db):
    inv = db["invoices"]
    # ALD, GX037HJ: canone di marzo (attiva) + copia archiviata dello stesso
    # documento, che NON deve contare.
    await inv.insert_one(_fattura("row1", "uuid-ald-marzo", "INR0391666", ALD, "ALD Automotive",
                                  "2026-03-17", 850.34, [_linea("GX037HJ Canone di locazione", 697.0)]))
    await inv.insert_one(_fattura("row1old", "old-ald-marzo", "INR0391666", ALD, "ALD Automotive",
                                  "2026-03-17", 850.34, [_linea("GX037HJ Canone di locazione", 697.0)],
                                  status="archived", pagato=True))
    # ALD, GX037HJ: bollo (N1, senza IVA) pagato insieme al canone di aprile
    # da un unico SDD di 977,24 = 850,34 + 126,90.
    await inv.insert_one(_fattura("row2", "uuid-ald-aprile", "INR0537654", ALD, "ALD Automotive",
                                  "2026-04-17", 850.34, [_linea("GX037HJ Canone di locazione", 697.0)]))
    await inv.insert_one(_fattura("row3", "uuid-ald-bollo", "RLR0013933", ALD, "ALD Automotive",
                                  "2026-01-26", 126.90, [_linea("GX037HJ Addebito tassa di proprieta", 126.90, 0.0)]))
    # ARVAL, GW980EP: canone senza nessuna prova → resta aperto.
    await inv.insert_one(_fattura("row4", "uuid-arval", "FC0014536148", ARVAL, "ARVAL",
                                  "2026-09-11", 832.25, [_linea("GW980EP Canone di Locazione", 682.17)]))

    # prove: allocazione singola per il canone di marzo
    await db["bank_payment_allocations"].insert_one({
        "status": "confirmed", "fattura_id": "uuid-ald-marzo", "fattura_numero": "INR0391666",
        "quota_cents": 85034, "movimento_id": "mov-marzo", "data_pagamento": "2026-04-01",
        "metodo_pagamento": "SDD/RID",
    })
    # SDD cumulativo: due allocazioni sullo stesso movimento
    await db["bank_payment_allocations"].insert_one({
        "status": "confirmed", "fattura_id": "uuid-ald-aprile", "fattura_numero": "INR0537654",
        "quota_cents": 85034, "movimento_id": "mov-cumulativo", "data_pagamento": "2026-05-04",
        "metodo_pagamento": "SDD/RID",
    })
    await db["bank_payment_allocations"].insert_one({
        "status": "confirmed", "fattura_id": "uuid-ald-bollo", "fattura_numero": "RLR0013933",
        "quota_cents": 12690, "movimento_id": "mov-cumulativo", "data_pagamento": "2026-05-04",
        "metodo_pagamento": "SDD/RID",
    })
    # la stessa prova scritta anche in Prima Nota Banca: non deve contare due volte
    await db["prima_nota_banca"].insert_one({
        "id": "pn-marzo", "data": "2026-04-01", "importo": 850.34, "fattura_id": "uuid-ald-marzo",
        "estratto_conto_id": "mov-marzo", "pagato_con": "SDD/RID", "numero_fattura": "INR0391666",
        "allocazioni_fatture": [{"fattura_id": "uuid-ald-marzo", "quota_cents": 85034,
                                 "movimento_id": "mov-marzo", "data_pagamento": "2026-04-01"}],
    })
    # Prima Nota SENZA estratto conto: pagamento dichiarato, non provato
    await db["prima_nota_banca"].insert_one({
        "id": "pn-dichiarata", "data": "2026-09-15", "importo": 832.25, "fattura_id": "uuid-arval",
        "pagato_con": "bonifico", "source": "ec_override_metodo_cassa",
    })
    # movimenti bancari: quelli usati dalle prove, uno verso il Comune senza
    # verbale, uno verso Leasys che nessuna relazione spiega
    for m in [
        {"id": "mov-marzo", "data": "2026-04-01", "importo": -850.34,
         "descrizione_originale": "SDD CORE: 4360740000000700913195 ALD AUTOMOTIVE ITALIA SRL"},
        {"id": "mov-cumulativo", "data": "2026-05-04", "importo": -977.24,
         "descrizione_originale": "SDD CORE: 4360740000000700913195 ALD AUTOMOTIVE ITALIA SRL"},
        {"id": "mov-comune", "data": "2026-03-10", "importo": -68.9,
         "descrizione_originale": "VS.DISP. FAVORE COMUNE DI NAPOLI . VIOLAZIONE CDS"},
        {"id": "mov-leasys", "data": "2026-07-17", "importo": -5545.67,
         "descrizione_originale": "VS.DISP. FAVORE leasys Italia Spa - contr 120365273"},
        {"id": "mov-altro", "data": "2026-07-17", "importo": -120.0,
         "descrizione_originale": "SDD CORE ENEL ENERGIA"},
    ]:
        await db["estratto_conto_movimenti"].insert_one(m)

    # veicoli: GX037HJ con storico driver (Rossi fino a marzo, poi Bianchi)
    await db["veicoli_noleggio"].insert_one({
        "targa": "GX037HJ", "marca": "BMW", "modello": "X1", "fornitore_noleggio": "ALD",
        "fornitore_piva": ALD, "driver": "Mario Bianchi", "driver_id": "dip-2",
        "assegnazioni": [
            {"driver": "Luigi Rossi", "driver_id": "dip-1", "dal": "2026-01-01", "al": "2026-03-31"},
            {"driver": "Mario Bianchi", "driver_id": "dip-2", "dal": "2026-04-01", "al": None},
        ],
    })
    await db["dipendenti"].insert_one({"id": "dip-1", "nome": "Luigi", "cognome": "Rossi"})
    await db["dipendenti"].insert_one({"id": "dip-2", "nome": "Mario", "cognome": "Bianchi"})

    # verbali della posta: uno pagato con PartenoPay (importo verificato),
    # uno con importo solo OCR e nessuna prova
    await db["verbali_noleggio"].insert_one({
        "id": "verb-1", "numero_verbale": "24990108761", "targa": "GX037HJ",
        "data_verbale": "2026-03-24", "data_verbale_verificata": True,
        "importo": 36.4, "importo_verificato": True, "importo_stato": "VERIFICATO_DOCUMENTO",
        "stato": "pagato", "pagato_documentalmente": True, "ricevuta_pagopa_id": "ric-1",
        "psp": "PartenoPay", "data_pagamento": "2026-03-12",
    })
    await db["verbali_noleggio"].insert_one({
        "id": "verb-2", "numero_verbale": "26990019358", "targa": "GX037HJ",
        "data_verbale": "2026-09-01", "importo": 124.6, "stato": "notificato",
    })
    await db["verbali_noleggio"].insert_one({
        "id": "verb-3", "numero_verbale": "A25111540620", "stato": "fattura_ricevuta",
        "fornitore": "ALD", "fattura_numero": "FIR0133977",
    })
    await db["trattenute_dipendenti"].insert_one({
        "id": "tr-1", "numero_verbale": "24990108761", "dipendente_id": "dip-1",
        "dipendente_nome": "Luigi Rossi", "importo": 36.4, "stato": "proposta",
    })


def _veicolo(pos, targa):
    return next(v for v in pos["veicoli"] if v["targa"] == targa)


def test_scan_esclude_la_copia_archiviata(db):
    asyncio.run(_semina(db))
    veicoli, _ = asyncio.run(scan_fatture_noleggio(2026))
    numeri = [c["numero_fattura"] for c in veicoli["GX037HJ"]["canoni"]]
    assert numeri.count("INR0391666") == 1
    assert veicoli["GX037HJ"]["totale_canoni"] == pytest.approx(850.34 * 2)
    assert "status" in FILTRO_FATTURA_ATTIVA and "stato_import" in FILTRO_FATTURA_ATTIVA


def test_posizione_quadra_dare_avere_per_targa(db):
    asyncio.run(_semina(db))
    pos = asyncio.run(mod.costruisci_posizione_noleggio(db, anno=2026))
    v = _veicolo(pos, "GX037HJ")
    r = v["riepilogo"]
    # DARE: due canoni + bollo + verbale PartenoPay = 850,34*2 + 126,90 + 36,40
    assert r["dare"] == pytest.approx(1863.98)
    # AVERE: allocazione di marzo + SDD cumulativo (850,34+126,90) + quietanza 36,40
    assert r["avere"] == pytest.approx(1863.98)
    assert r["saldo"] == pytest.approx(0.0)
    assert r["per_categoria"]["bollo"]["saldo"] == pytest.approx(0.0)
    assert r["per_categoria"]["verbali"]["dare"] == pytest.approx(36.4)
    # ogni riga quadra: dare o avere, mai entrambi
    for riga in v["righe"]:
        assert not (riga.get("dare") and riga.get("avere"))
    # la stessa prova in allocazioni e in Prima Nota conta una volta sola
    pagamenti_marzo = [x for x in v["righe"] if x["tipo"] == "pagamento" and x["documento"]["numero"] == "INR0391666"]
    assert len(pagamenti_marzo) == 1 and pagamenti_marzo[0]["prova"]["movimento_id"] == "mov-marzo"


def test_sdd_cumulativo_si_spartisce_al_centesimo(db):
    asyncio.run(_semina(db))
    pos = asyncio.run(mod.costruisci_posizione_noleggio(db, anno=2026))
    v = _veicolo(pos, "GX037HJ")
    bollo = [x for x in v["righe"] if x["categoria"] == "bollo" and x["tipo"] == "pagamento"]
    assert len(bollo) == 1 and bollo[0]["avere"] == pytest.approx(126.90)
    assert bollo[0]["prova"]["movimento_id"] == "mov-cumulativo"
    costo_bollo = next(x for x in v["righe"] if x["categoria"] == "bollo" and x["tipo"] == "costo")
    assert costo_bollo["stato"] == "pagata" and costo_bollo["residuo"] == 0


def test_prima_nota_senza_estratto_non_chiude_il_saldo(db):
    asyncio.run(_semina(db))
    pos = asyncio.run(mod.costruisci_posizione_noleggio(db, anno=2026))
    v = _veicolo(pos, "GW980EP")
    assert v["riepilogo"]["saldo"] == pytest.approx(832.25)
    assert v["riepilogo"]["avere_non_verificato"] == pytest.approx(832.25)
    dichiarate = [x for x in v["righe"] if x["tipo"] == "pagamento_dichiarato"]
    assert len(dichiarate) == 1 and dichiarate[0]["avere"] == 0
    assert pos["controlli"]["pagamenti_dichiarati_non_verificati"] == 1
    assert [f["numero"] for f in pos["controlli"]["fatture_senza_pagamento"]] == ["FC0014536148"]


def test_verbale_con_quietanza_partenopay_e_driver_alla_data(db):
    asyncio.run(_semina(db))
    pos = asyncio.run(mod.costruisci_posizione_noleggio(db, anno=2026))
    v = _veicolo(pos, "GX037HJ")
    schede = {s["numero_verbale"]: s for s in v["verbali"]}
    pagato = schede["24990108761"]
    assert pagato["pagato"] is True
    assert pagato["fonte_quietanza"] == "PartenoPay"
    assert pagato["importo_verificato"] == pytest.approx(36.4)
    # il 24/03 l'auto era di Rossi: la responsabilita' segue lo storico, non il driver attuale
    assert pagato["driver_competente"]["driver_id"] == "dip-1"
    assert pagato["driver_competente"]["fonte"] == "storico_assegnazioni"
    assert pagato["trattenute"][0]["importo"] == 36.4
    aperto = schede["26990019358"]
    assert aperto["pagato"] is False
    assert aperto["importo_verificato"] is None and aperto["importo_da_verificare"] is True
    assert aperto["driver_competente"]["driver_id"] == "dip-2"
    # un importo solo OCR non entra in DARE
    riga = next(x for x in v["righe"] if x["documento"]["numero"] == "26990019358")
    assert riga["dare"] is None and riga["stato"] == "importo_da_verificare"
    assert any(x["numero_verbale"] == "26990019358" for x in pos["controlli"]["verbali_senza_quietanza"])


def test_posizione_driver_segue_le_assegnazioni(db):
    asyncio.run(_semina(db))
    pos = asyncio.run(mod.costruisci_posizione_noleggio(db, anno=2026))
    per_driver = {d["driver_id"]: d for d in pos["driver"] if d.get("driver_id")}
    # Rossi: bollo di gennaio, canone di marzo, verbale di marzo (+ relative prove)
    assert per_driver["dip-1"]["dare"] == pytest.approx(126.90 + 850.34 + 36.4)
    assert per_driver["dip-1"]["saldo"] == pytest.approx(0.0)
    assert per_driver["dip-1"]["verbali"] == 1 and per_driver["dip-1"]["trattenute"] == pytest.approx(36.4)
    # Bianchi: canone di aprile (pagato a maggio: il pagamento segue il costo)
    # e il verbale di settembre aperto
    assert per_driver["dip-2"]["dare"] == pytest.approx(850.34)
    assert per_driver["dip-2"]["avere"] == pytest.approx(850.34)
    assert per_driver["dip-2"]["verbali_aperti"] == 1
    assert "GX037HJ" in per_driver["dip-2"]["veicoli"]


def test_movimenti_senza_relazione_restano_candidati(db):
    asyncio.run(_semina(db))
    pos = asyncio.run(mod.costruisci_posizione_noleggio(db, anno=2026))
    candidati = {c["movimento_id"]: c for c in pos["pagamenti_senza_documento"]}
    assert set(candidati) == {"mov-comune", "mov-leasys"}
    assert candidati["mov-comune"]["per"] == "verbale" and candidati["mov-comune"]["importo"] == pytest.approx(68.9)
    assert candidati["mov-leasys"]["controparte"] == "Leasys"
    # nessun candidato e' finito in AVERE di qualche auto
    for v in pos["veicoli"]:
        for riga in v["righe"]:
            prova = riga.get("prova") or {}
            assert prova.get("movimento_id") not in ("mov-comune", "mov-leasys")
    assert pos["controlli"]["auto_senza_driver"] == ["GW980EP"]
    assert pos["controlli"]["verbali_senza_targa"] == 1


def test_secondo_giro_identico_e_totali_coerenti(db):
    asyncio.run(_semina(db))
    primo = asyncio.run(mod.costruisci_posizione_noleggio(db, anno=2026))
    secondo = asyncio.run(mod.costruisci_posizione_noleggio(db, anno=2026))
    assert primo == secondo
    tot = primo["totali"]
    assert tot["dare"] == pytest.approx(sum(v["riepilogo"]["dare"] for v in primo["veicoli"]))
    assert tot["avere"] == pytest.approx(sum(v["riepilogo"]["avere"] for v in primo["veicoli"]))
    assert tot["saldo"] == pytest.approx(tot["dare"] - tot["avere"])


def test_ripartizione_centesimi_non_perde_niente():
    assert mod.ripartisci_centesimi(1000, [1, 1, 1]) in ([334, 333, 333], [333, 334, 333], [333, 333, 334])
    assert sum(mod.ripartisci_centesimi(97724, [85034, 12690])) == 97724
    assert mod.ripartisci_centesimi(500, [0, 0]) == [500, 0]
    assert mod.ripartisci_centesimi(0, []) == []


def test_fonte_quietanza_letta_dalla_prova():
    assert mod.etichetta_fonte_quietanza({"psp": "Mooney (PayTipper)"}) == "Mooney"
    assert mod.etichetta_fonte_quietanza({"fonte_pagamento": "paypal", "paypal_transaction_id": "T1"}) == "PayPal"
    assert mod.etichetta_fonte_quietanza({"fonte_riconciliazione": "estratto_conto"}) == "Banca BPM"
    assert mod.etichetta_fonte_quietanza({"ricevuta_pagopa_id": "r1"}) == "PagoPA"
    assert mod.etichetta_fonte_quietanza({"stato": "notificato"}) is None
