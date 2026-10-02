"""Classificazione dei documenti nella cartella unica: la bolletta, il sollecito e le stampe
dell'home banking che citano la banca o scrivono «estratto conto» non sono estratti conto;
la stampa PDF di una fattura italiana va in ARRETRATO; il ripasso e' una volta sola."""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from mongomock_motor import AsyncMongoMockClient

from app.routers import documenti
from app.services import classificazione_estratti as cls
from app.services import drive_cartella_unica as cu
from tests.documenti.test_drive_cartella_unica import CARTELLE, DriveFinto

_BOLLETTA = (
    "Enel Energia - Mercato libero dell'energia. Importo da pagare 2.264,25 € Scadenza 24/03/2025 "
    "Metodo di pagamento Con addebito automatico su conto corrente presso Banco bpm s.p.a. "
    "Il pagamento avviene il giorno della scadenza. Totale Bolletta 2.264,25 €")
_SOLLECITO = (
    "OGGETTO : INVIO ESTRATTO CONTO - FATTURE SCADUTE Gentile Cliente, siamo a comunicarvi "
    "l'avvenuta scadenza delle seguenti fatture. Totale Scaduto EU 263,12 "
    "Bonifico Bancario IBAN BPER Banca S.p.A.")
_DETTAGLIO_MOVIMENTO = (
    "Gestione Finanziaria Dettaglio movimento Rapporto ABI-Banca: 05034 - BANCO BPM S.P.A. "
    "Data contabile: 01/12/2025 Descrizione: ADDEBITO DIRETTO SDD Data valuta: 01/12/2025 "
    "Importo: -2.038,56")
_ESTRATTO_BPM = (
    "BANCO BPM S.P.A. ESTRATTO CONTO 05034 Saldo iniziale 10.000,00 "
    "01/07/2026 01/07/2026 01/07/2026 -120,00 Saldo finale 9.880,00")


def run(coro):
    return asyncio.run(coro)


@pytest.mark.parametrize("testo", [_BOLLETTA, _DETTAGLIO_MOVIMENTO])
def test_il_nome_della_banca_o_un_solo_movimento_non_fanno_un_estratto(testo):
    # il dettaglio ha data contabile e valuta ma e' la prova di UN movimento
    assert cls.route_da_testo(testo) is None


def test_l_estratto_vero_resta_un_estratto_della_banca():
    assert cls.route_da_testo(_ESTRATTO_BPM) == cls.BANCA
    # il titolo con l'ABI Banco BPM basta, come per il lettore degli estratti
    assert cls.route_da_testo("banco bpm estratto conto 05034 movimenti") == cls.BANCA
    # l'export della banca si riconosce ancora dalle colonne
    assert cls.route_da_testo("data contabile;data valuta;banca;importo") == cls.BANCA
    # un export che cita la banca e ha le colonne contabile/valuta non perde il riconoscimento
    assert cls.route_da_testo("banca nazionale del lavoro data contabile data valuta importo") == cls.BANCA


@pytest.mark.parametrize("testo", [_BOLLETTA, _SOLLECITO, _DETTAGLIO_MOVIMENTO])
def test_un_pdf_che_scrive_estratto_conto_o_cita_la_banca_non_e_un_estratto(monkeypatch, testo):
    monkeypatch.setattr(documenti, "_pdf_text_for_detection", lambda _c: testo)
    assert documenti.detect_document_type("documento.pdf", b"%PDF-1.4 x") != "estratto_conto"


def test_l_estratto_con_i_saldi_e_ancora_un_estratto(monkeypatch):
    monkeypatch.setattr(documenti, "_pdf_text_for_detection", lambda _c: _ESTRATTO_BPM)
    assert documenti.detect_document_type("documento.pdf", b"%PDF-1.4 x") == "estratto_conto"


def test_la_fattura_pdf_italiana_va_in_arretrato_con_il_suo_motivo():
    risultato = {"success": False, "tipo_rilevato": "fattura_pdf",
                 "fuori_contabilita": "copia PDF di una fattura italiana: la fattura entra dall'XML dello SDI"}
    cartella, motivo = cu.esito_del_risultato(risultato)
    assert cartella == cu.ARRETRATO and "fattura" in motivo
    # un errore vero resta un errore
    assert cu.esito_del_risultato({"success": False, "message": "boom"})[0] == cu.ERRORI


def _fa(minuti):
    return (datetime.now(timezone.utc) - timedelta(minutes=minuti)).isoformat()


def test_gli_errori_di_classificazione_si_rileggono_una_volta_sola():
    drive = DriveFinto()
    drive.aggiungi("e1", "bolletta.pdf", b"%PDF-1", "errori")
    drive.aggiungi("f1", "fattura.pdf", b"%PDF-2", "errori")
    drive.aggiungi("x1", "altro.pdf", b"%PDF-3", "errori")
    db = AsyncMongoMockClient()["t"]
    for fid, tipo, motivo in (
        ("e1", "estratto_conto", "Errore import estratto conto: 400: Formato Banco BPM non riconosciuto"),
        ("f1", "fattura_pdf", "Fattura PDF senza partita IVA estera: le fatture italiane arrivano come XML"),
        ("x1", "f24", "Errore import F24: F24 non quadrato o non validato: salvataggio bloccato"),
    ):
        run(db[cu.REGISTRO].insert_one({"id": fid, "nome": f"{fid}.pdf", "cartella": cu.ERRORI,
                                        "esito": "errore", "tipo": tipo, "motivo": motivo,
                                        "aggiornato_il": _fa(600)}))
    assert run(cu.rimetti_in_coda_buste_gia_presenti(db, drive, dict(CARTELLE))) == 2
    assert drive.file["e1"]["parent"] == "inbox" and drive.file["f1"]["parent"] == "inbox"
    assert drive.file["x1"]["parent"] == "errori"      # difetto del lettore F24: non si rilegge

    # riletti con le regole nuove e fermi ancora in ERRORI: la versione li protegge dal ciclo
    for fid, tipo, motivo in (("e1", "estratto_conto", "Formato Banco BPM non riconosciuto"),):
        drive.file[fid]["parent"] = "errori"
        run(db[cu.REGISTRO].update_one({"id": fid}, {"$set": {
            "cartella": cu.ERRORI, "tipo": tipo, "motivo": motivo,
            "regole_classificazione": cu.REGOLE_CLASSIFICAZIONE}}))
    assert run(cu.rimetti_in_coda_buste_gia_presenti(db, drive, dict(CARTELLE))) == 0
