"""Dedup delle chiusure RT per dispositivo, sul motore unico.

Bug del 15/07/2026: il vecchio `CorrispettiviService` (tolto il 02/10/2026,
nessun chiamante) controllava i duplicati solo per data, e una chiusura con la
matricola cambiata dal risigillo triennale spariva come «doppione». Le stesse
prove valgono oggi su `ingest_corrispettivo_parsed`, l'unico che scrive una
chiusura: matricole diverse lo stesso giorno sono due chiusure, lo stesso XML
due volte e' una riga sola.
"""
from decimal import Decimal

from app.parsers.corrispettivi_parser import parse_corrispettivo_xml
from app.routers.invoices.corrispettivi_helpers import ingest_corrispettivo_parsed
from tests.corrispettivi._comune import attive, nuovo_db, run, xml_chiusura

GIORNO = "2026-07-14"


def _importa(db, xml: str, nome: str):
    parsed = parse_corrispettivo_xml(xml)
    assert not parsed.get("error"), parsed
    return run(ingest_corrispettivo_parsed(db, parsed, filename=nome, source="xml"))


def test_matricole_diverse_stessa_data_non_sono_duplicati():
    db = nuovo_db("dedup_matricole")
    vecchia = xml_chiusura(data=GIORNO, progressivo="11", matricola="00011", contanti="300.00",
                           elettronico="200.00", imponibile="454.55", imposta="45.45")
    nuova = xml_chiusura(data=GIORNO, progressivo="12", matricola="00012", contanti="250.00",
                         elettronico="150.00", imponibile="363.64", imposta="36.36")

    esito1 = _importa(db, vecchia, "matricola_vecchia.xml")
    esito2 = _importa(db, nuova, "matricola_nuova.xml")

    assert esito1["action"] == "created"
    assert esito2["action"] == "created", esito2
    righe = run(attive(db, "corrispettivi"))
    assert {r["matricola_rt"] for r in righe} == {"00011", "00012"}
    # In Cassa entra soltanto la quota materialmente incassata in contanti.
    entrate = [Decimal(str(r["importo"])) for r in run(attive(db, "prima_nota_cassa"))
               if r.get("tipo") == "entrata"]
    assert sorted(entrate) == [Decimal("250.0"), Decimal("300.0")]


def test_stesso_dispositivo_stesso_xml_resta_duplicato():
    db = nuovo_db("dedup_stesso_xml")
    xml = xml_chiusura(data=GIORNO, progressivo="11", matricola="00011")

    esito1 = _importa(db, xml, "cassa1.xml")
    esito2 = _importa(db, xml, "cassa1_ridownload.xml")

    assert esito1["action"] == "created"
    assert esito2["action"] == "duplicate"
    assert len(run(attive(db, "corrispettivi"))) == 1
    assert len(run(attive(db, "prima_nota_cassa"))) == 1
