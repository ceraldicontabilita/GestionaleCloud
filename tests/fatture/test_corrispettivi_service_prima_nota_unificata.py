"""Un solo motore scrive le chiusure RT: `ingest_corrispettivo_parsed`.

Il vecchio `CorrispettiviService` (process_xml, create_manual, una terza
Prima Nota propria) era senza chiamanti in produzione e sommava due chiusure
dello stesso giorno in una riga sola: tolto il 02/10/2026. Questa guardia
impedisce che rinasca e che il CSV AdE scriva Prima Nota o giornale.
"""
import pathlib

from app.services import corrispettivi_service as cs
from tests.corrispettivi._comune import nuovo_db, righe, run

RADICE = pathlib.Path(__file__).resolve().parents[2] / "app"


def test_il_servizio_corrispettivi_non_e_un_secondo_motore():
    assert not hasattr(cs, "CorrispettiviService")
    assert not hasattr(cs, "get_corrispettivi_service")
    for sorgente in RADICE.rglob("*.py"):
        testo = sorgente.read_text(encoding="utf-8")
        assert "CorrispettiviService(" not in testo, sorgente
        assert "get_corrispettivi_service(" not in testo, sorgente


def test_il_csv_ade_scrive_solo_la_riga_provvisoria():
    """Niente Prima Nota, niente giornale, niente contanti/POS per differenza."""
    db = nuovo_db("csv_solo_provvisorio")
    csv = ("Id invio;Matricola;Data rilevazione;Data trasmissione;Ammontare delle vendite;"
           "Imponibile al 10%;Imposta;Periodo di inattivita' da;Periodo di inattivita' a\n"
           "1234;99MEY026532;10/09/2026;11/09/2026;000000000909,09;000000000909,09;000000000090,91;;\n")
    esito = run(cs.importa_csv_ade(db, csv, "settembre.csv"))

    assert esito["nuovi"] == 1
    (riga,) = run(righe(db, "corrispettivi"))
    assert riga["stato"] == cs.STATO_PROVVISORIO and riga["source"] == cs.SORGENTE_CSV_ADE
    assert riga["pagato_contanti"] is None and riga["pagato_elettronico"] is None
    assert run(righe(db, "prima_nota_cassa")) == [] and run(righe(db, "movimenti_contabili")) == []
    assert run(cs.importa_csv_ade(db, csv, "settembre (1).csv"))["nuovi"] == 0
