"""Contabili di filiale BPM: prova del versamento, mai un movimento nuovo."""
import asyncio

from app.routers.documenti import detect_document_type
from app.services import contabili_filiale as cf
from app.services import drive_cartella_unica as cu
from app.services.archivio_documenti_memoria import ClientArchivioMemoria

# Testo letto dal PDF reale del 31/10/2025 (Drive), senza la clausola legale.
VERSAMENTO = """COD. DIPENDENZA DEL C/C L'OPERATORE NA-CARITA' 31/10/2025 Op.N.55 06/A4VI 1788 HO23850
Vogliate prendere nota che abbiamo eseguito, sul Vostro conto corrente N.
005462 IMPORTO VALUTA
780 CONTANTI 4.700,00+ 31/10/2025
4.700,00+
CERALDI GROUP S.R.L. Distinta N. 00055
66 x 50 3.300,00 70 x 20 1.400,00 CONTANTE 4.700,00 VERSAMENTO ******4.700,00*
le seguenti operazioni: OPERAZIONE
TOTALE A CREDITO
CONTABILE"""

SPESE = """IL RESPONSABILE COD. DIPENDENZA DEL C/C L'OPERATORE
Vogliate prendere nota che abbiamo eseguito, sul Vostro conto corrente N.
le seguenti operazioni: OPERAZIONE IMPORTO VALUTA
TOTALE
CONTABILE
NAPOLI 31/05/2024 Id.4152L4VI0146 LBAS 1788 HO23850
005462
66C SPESE LIBR.AS. EUR 1,20- 31/05/2024
A DEBITO EUR 1,20-
CERALDI GROUP S.R.L."""


def test_leggi_versamento_e_spese():
    v = cf.leggi(VERSAMENTO)
    assert v["operazione"] == "versamento_contanti" and v["verso"] == "entrata"
    assert v["importo"] == "4700.00" and v["data_operazione"] == "2025-10-31"
    assert v["distinta"] == "00055"
    assert v["operazioni"] == [{"codice": "780", "descrizione": "CONTANTI",
                                "importo": "4700.00", "valuta": "2025-10-31"}]
    s = cf.leggi(SPESE)
    assert s["operazione"] == "operazione_sportello" and s["importo"] == "-1.20"
    assert s["data_operazione"] == "2024-05-31"
    assert cf.riconosci(VERSAMENTO) and cf.riconosci(SPESE)
    assert not cf.riconosci("ESTRATTO CONTO CORRENTE BANCO BPM")


def _scenario(movimenti, testi):
    async def run():
        db = ClientArchivioMemoria()["contabili"]
        for m in movimenti:
            await db["estratto_conto_movimenti"].insert_one(m)
        esiti = [await cf.registra(db, f"c{i}.pdf", t.encode() + bytes([i]), t, drive_file_id=f"drv{i}")
                 for i, t in enumerate(testi)]
        di_nuovo = await cf.registra(db, "c0.pdf", testi[0].encode() + bytes([0]), testi[0])
        movs = {m["id"]: m for m in await db["estratto_conto_movimenti"].find({}, {"_id": 0}).to_list(None)}
        return esiti, di_nuovo, movs
    return asyncio.run(run())


def test_collega_il_versamento_e_le_spese_senza_creare_movimenti():
    movimenti = [
        {"id": "vers", "data": "2025-10-31", "importo": 4700.0, "descrizione_originale": "VERS. CONTANTI - VVVVV"},
        # Stesso importo ma non e' un versamento: non va preso.
        {"id": "bonif", "data": "2025-10-31", "importo": 4700.0,
         "descrizione_originale": "BONIFICO A VOSTRO FAVORE - ROSSI"},
        {"id": "spese", "data": "2024-05-31", "importo": -1.2, "descrizione_originale": "SPESE LIBRETTO ASSEGNI"},
        {"id": "comm", "data": "2024-05-31", "importo": -1.2, "descrizione_originale": "COMMISSIONI BONIFICO"},
    ]
    esiti, di_nuovo, movs = _scenario(movimenti, [VERSAMENTO, SPESE])
    assert esiti[0]["stato"] == "collegata" and esiti[0]["movimento_id"] == "vers"
    assert esiti[1]["stato"] == "collegata" and esiti[1]["movimento_id"] == "spese"
    assert movs["vers"]["contabile_filiale_drive_file_id"] == "drv0"
    assert "contabile_filiale_id" not in movs["bonif"] and "contabile_filiale_id" not in movs["comm"]
    assert len(movs) == 4
    assert di_nuovo["duplicate"] is True


def test_estratto_che_arriva_dopo_e_versamento_gia_preso():
    async def run():
        db = ClientArchivioMemoria()["contabili_dopo"]
        esito = await cf.registra(db, "c.pdf", b"x", VERSAMENTO)
        await db["estratto_conto_movimenti"].insert_one(
            {"id": "vers", "data": "2025-11-02", "importo": 4700.0, "descrizione_originale": "VERSAMENTO CONTANTI"})
        dopo = await cf.ricollega_in_attesa(db)
        await db["estratto_conto_movimenti"].insert_one(
            {"id": "altro", "data": "2025-11-03", "importo": 4700.0, "descrizione_originale": "VERS. CONTANTI"})
        esito2 = await cf.registra(db, "c2.pdf", b"y", VERSAMENTO.replace("00055", "00056"))
        return esito, dopo, esito2
    esito, dopo, esito2 = asyncio.run(run())
    assert esito["stato"] == "in_attesa_estratto"
    assert dopo == {"riprovate": 1, "collegate": 1}
    # Il primo versamento e' gia' preso: resta un solo candidato libero.
    assert esito2["stato"] == "collegata" and esito2["movimento_id"] == "altro"


def test_smistatore_riconosce_la_contabile(monkeypatch):
    from app.routers import documenti

    monkeypatch.setattr(documenti, "_pdf_text_for_detection", lambda contenuto: VERSAMENTO)
    assert detect_document_type("Contabile di filiale_31-10-2025_4700,00.pdf", b"%PDF") == cf.TIPO


def test_file_vecchi_e_stampe_vanno_in_arretrato():
    m = cu.motivo_fuori_contabilita
    assert "fattura XML" in m("IT01879020517_z1Eua.xml.p7m - 000000000011206_01.pdf", anno_attivo=2026)
    assert "formato" in m("nota integrativa 2010.doc", anno_attivo=2026)
    assert "2016" in m("bilancio abbreviato 2016.pdf", anno_attivo=2026)
    assert m("InformativaPrivacy.pdf", anno_attivo=2026) is None
    assert m("verbale 2026.pdf", anno_attivo=2026) is None
    assert cu.esito_del_risultato({"tipo_rilevato": "non_riconosciuto",
                                   "fuori_contabilita": "documento del 2016"}) == (cu.ARRETRATO, "documento del 2016")
    assert cu.esito_del_risultato({"tipo_rilevato": "non_riconosciuto"}) == (cu.ERRORI, cu.NON_RICONOSCIUTO)
