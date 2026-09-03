"""
test_e2e_flussi.py — Collaudo end-to-end su MONGO DI PROVA (tranche 3, 24/07/2026).

Il database è FINTO (mongomock-motor) e si chiama Gestionale_Test: i test non
possono MAI toccare il database di produzione `Gestionale` (nessuna
connessione di rete viene aperta). Ogni test riceve un db vuoto e patcha il
riferimento `db` dei moduli router coinvolti.

Coperti qui: doppio import della stessa fattura (dedup numero+P.IVA),
creazione lotti fornitori da fattura, consumo FIFO (dal lotto più vecchio,
con conversione kg↔g), consumo con quantità insufficiente (mai negativi),
permessi admin/dipendente su endpoint protetto.
"""
import os
os.environ.setdefault("AUTH_SECRET", "test-secret-non-usare-in-prod")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "Gestionale_Test")  # SOLO db di prova

import asyncio
import io
from datetime import datetime, timedelta

import pytest
from mongomock_motor import AsyncMongoMockClient


def run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def dbmock(monkeypatch):
    """Mongo FINTO per tutti i router: qualunque modulo con attributo `db`
    viene puntato su Gestionale_Test (mai il db reale, mai la rete). Il bus
    eventi viene disattivato (i suoi handler toccano altri moduli)."""
    import importlib, pkgutil, sys
    import app.lotti.routers as routers  # noqa
    cli = AsyncMongoMockClient()
    db = cli["Gestionale_Test"]
    # importa e patcha TUTTI i moduli routers.*
    for m in pkgutil.iter_modules(routers.__path__):
        try:
            mod = importlib.import_module(f"app.lotti.routers.{m.name}")
        except Exception:
            continue
        if hasattr(mod, "db"):
            monkeypatch.setattr(mod, "db", db, raising=False)
    import app.lotti.db as dbmod
    monkeypatch.setattr(dbmod, "database", db, raising=False)
    # bus eventi: no-op (gli handler leggono/scrivono db di altri moduli)
    import app.lotti.eventi as eventi
    async def _pub(*a, **k):
        return None
    monkeypatch.setattr(eventi, "publish", _pub, raising=False)
    # servizi (crea_lotto, movimenti lotto…)
    try:
        import app.lotti.servizi as servizi
        for m in pkgutil.iter_modules(servizi.__path__):
            try:
                mod = importlib.import_module(f"app.lotti.servizi.{m.name}")
            except Exception:
                continue
            if hasattr(mod, "db"):
                monkeypatch.setattr(mod, "db", db, raising=False)
    except Exception:
        pass
    return db


# ── XML fattura minimo ma realistico ────────────────────────────────────────
def _xml_fattura(numero="123/A", piva="01234567890", data="2026-07-01"):
    return f"""<?xml version='1.0' encoding='UTF-8'?>
<p:FatturaElettronica xmlns:p='x' versione='FPR12'>
 <FatturaElettronicaHeader>
  <CedentePrestatore>
   <DatiAnagrafici>
    <IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>{piva}</IdCodice></IdFiscaleIVA>
    <Anagrafica><Denominazione>MOLINO TEST SRL</Denominazione></Anagrafica>
   </DatiAnagrafici>
  </CedentePrestatore>
 </FatturaElettronicaHeader>
 <FatturaElettronicaBody>
  <DatiGenerali><DatiGeneraliDocumento>
    <Numero>{numero}</Numero><Data>{data}</Data>
    <ImportoTotaleDocumento>100.00</ImportoTotaleDocumento>
  </DatiGeneraliDocumento></DatiGenerali>
  <DatiBeniServizi>
   <DettaglioLinee>
    <NumeroLinea>1</NumeroLinea>
    <Descrizione>FARINA 00 SACCO KG 25</Descrizione>
    <Quantita>4.00</Quantita>
    <UnitaMisura>KG</UnitaMisura>
    <PrezzoUnitario>20.00</PrezzoUnitario>
    <PrezzoTotale>80.00</PrezzoTotale>
   </DettaglioLinee>
  </DatiBeniServizi>
 </FatturaElettronicaBody>
</p:FatturaElettronica>""".encode()


def _upload(nome, contenuto):
    from starlette.datastructures import UploadFile
    return UploadFile(file=io.BytesIO(contenuto), filename=nome)


# ── 1. Doppio import stessa fattura → UNA sola in archivio ──────────────────
def test_import_doppio_stessa_fattura_non_duplica(dbmock):
    import app.lotti.routers.fatture as fat
    xml = _xml_fattura()
    r1 = run(fat.importa_fattura_xml(files=[_upload("f1.xml", xml)]))
    n1 = run(dbmock.fatture.count_documents({}))
    assert n1 == 1, f"prima importazione: attesa 1 fattura, trovate {n1} ({r1})"

    run(fat.importa_fattura_xml(files=[_upload("f1_copia.xml", xml)]))
    n2 = run(dbmock.fatture.count_documents({}))
    assert n2 == 1, f"secondo import della STESSA fattura: deve restare 1, trovate {n2}"

    doc = run(dbmock.fatture.find_one({}))
    assert doc["numero_fattura"] == "123/A"
    assert doc.get("prodotti"), "la fattura deve avere le righe prodotto"


def test_import_fattura_crea_lotto_fornitore(dbmock):
    import app.lotti.routers.fatture as fat
    run(fat.importa_fattura_xml(files=[_upload("f1.xml", _xml_fattura())]))
    lotti = run(dbmock.lotti_fornitori.find({}).to_list(10))
    assert lotti, "l'import fattura deve creare i lotti fornitori"
    l = lotti[0]
    assert "FARINA" in (l.get("prodotto_nome") or "").upper()
    assert float(l.get("quantita_disponibile") or 0) > 0


# ── 2. Consumo FIFO: prima il lotto più VECCHIO, con conversione kg↔g ──────
def _data_fattura(giorni_fa: int) -> str:
    """Data in formato fattura (dd/mm/yyyy) relativa a OGGI.

    AUDIT 25/07/2026: prima queste date erano SCRITTE A MANO (01/06/2026 e
    01/07/2026). Col passare del tempo il lotto "vecchio" è uscito dalla
    finestra dei 60 giorni della regola di Enzo e il test ha cominciato a
    fallire pur senza nessuna modifica al codice: un test con la data fissa
    smette di controllare quello che dice di controllare."""
    return (datetime.now() - timedelta(days=giorni_fa)).strftime("%d/%m/%Y")


def _seed_lotti_farina(dbmock):
    """Due lotti ENTRAMBI dentro la finestra dei 60 giorni: qui si controlla
    il FIFO puro (si parte dal più vecchio)."""
    lotti = [
        {"id": "L-vecchio", "prodotto_nome": "Farina 00", "prodotto_nome_norm": "farina 00", "fornitore": "Molino A",
         "quantita_disponibile": 10.0, "unita_misura": "KG",
         "data_fattura": _data_fattura(40), "esaurito": False},
        {"id": "L-nuovo", "prodotto_nome": "Farina 00", "prodotto_nome_norm": "farina 00", "fornitore": "Molino B",
         "quantita_disponibile": 10.0, "unita_misura": "KG",
         "data_fattura": _data_fattura(10), "esaurito": False},
    ]
    run(dbmock.lotti_fornitori.insert_many(lotti))


RICETTA_PANE = {
    "nome": "Pane di prova",
    "ingredienti_dettaglio": [{"nome": "Farina 00", "quantita": 500, "unita_misura": "g"}],
}


def test_fifo_consuma_il_lotto_piu_vecchio(dbmock):
    import app.lotti.routers.lotti_produzione as lp
    _seed_lotti_farina(dbmock)
    esito = run(lp.scala_lotti_fornitori_per_ricetta(RICETTA_PANE, 1, "LOTTO-TEST"))
    assert esito["lotti_scalati"], f"nessun lotto scalato: {esito}"
    assert esito["lotti_scalati"][0]["lotto_id"] == "L-vecchio", "FIFO: deve partire dal più vecchio"

    vecchio = run(dbmock.lotti_fornitori.find_one({"id": "L-vecchio"}))
    nuovo = run(dbmock.lotti_fornitori.find_one({"id": "L-nuovo"}))
    # 500 g = 0.5 KG dal lotto vecchio; il nuovo resta intatto
    assert abs(vecchio["quantita_disponibile"] - 9.5) < 0.01, vecchio
    assert nuovo["quantita_disponibile"] == 10.0
    assert vecchio["storico_utilizzi"][0]["lotto_produzione"] == "LOTTO-TEST"


def test_fifo_lotto_oltre_60_giorni_va_in_riserva(dbmock):
    """REGOLA ENZO 23/07/2026: si parte dal più vecchio DEGLI ULTIMI 60 GIORNI —
    un lotto di mesi fa non rappresenta più il fornitore vero da mettere in
    etichetta. I lotti oltre i 60 giorni non si buttano: restano in coda come
    riserva. Questo comportamento non era coperto da nessun test (l'ha fatto
    emergere l'audit del 25/07/2026)."""
    import app.lotti.routers.lotti_produzione as lp
    run(dbmock.lotti_fornitori.insert_many([
        {"id": "L-antico", "prodotto_nome": "Farina 00", "prodotto_nome_norm": "farina 00",
         "fornitore": "Molino Vecchio", "quantita_disponibile": 10.0, "unita_misura": "KG",
         "data_fattura": _data_fattura(200), "esaurito": False},
        {"id": "L-recente", "prodotto_nome": "Farina 00", "prodotto_nome_norm": "farina 00",
         "fornitore": "Molino Nuovo", "quantita_disponibile": 10.0, "unita_misura": "KG",
         "data_fattura": _data_fattura(15), "esaurito": False},
    ]))
    esito = run(lp.scala_lotti_fornitori_per_ricetta(RICETTA_PANE, 1, "LOTTO-RISERVA"))
    assert esito["lotti_scalati"], f"nessun lotto scalato: {esito}"
    # si parte dal recente, NON dall'antico (che resta riserva)
    assert esito["lotti_scalati"][0]["lotto_id"] == "L-recente", esito
    antico = run(dbmock.lotti_fornitori.find_one({"id": "L-antico"}))
    assert antico["quantita_disponibile"] == 10.0, "il lotto antico non va toccato finché c'è il recente"


def test_fifo_quantita_insufficiente_mai_negativa(dbmock):
    import app.lotti.routers.lotti_produzione as lp
    run(dbmock.lotti_fornitori.insert_one(
        {"id": "L-scarso", "prodotto_nome": "Farina 00", "prodotto_nome_norm": "farina 00", "fornitore": "Molino A",
         "quantita_disponibile": 0.2, "unita_misura": "KG",
         "data_fattura": _data_fattura(45), "esaurito": False}))
    esito = run(lp.scala_lotti_fornitori_per_ricetta(RICETTA_PANE, 1, "LOTTO-TEST2"))
    doc = run(dbmock.lotti_fornitori.find_one({"id": "L-scarso"}))
    assert doc["quantita_disponibile"] >= 0, "la giacenza non può mai andare sotto zero"
    assert doc["esaurito"] is True
    assert esito["lotti_esauriti"], "il lotto finito va segnalato tra gli esauriti"
    # consumato SOLO ciò che c'era (0.2 KG), non i 0.5 richiesti
    assert abs(esito["lotti_scalati"][0]["quantita_consumata"] - 0.2) < 0.01
    # e il MANCANTE viene segnalato (fix 24/07: prima era ignorato in silenzio)
    assert esito["ingredienti_insufficienti"], esito
    manc = esito["ingredienti_insufficienti"][0]
    assert manc["ingrediente"] == "Farina 00" and abs(manc["mancante"] - 300) < 1


def test_fifo_ingrediente_sconosciuto_segnalato(dbmock):
    import app.lotti.routers.lotti_produzione as lp
    ricetta = {"nome": "X", "ingredienti_dettaglio": [{"nome": "Polvere di unicorno", "quantita": 100, "unita_misura": "g"}]}
    esito = run(lp.scala_lotti_fornitori_per_ricetta(ricetta, 1, "L"))
    assert "Polvere di unicorno" in esito["ingredienti_non_trovati"]
    assert not esito["lotti_scalati"]


# ── 3. Permessi: dipendente NO, amministratore SÌ su endpoint protetto ─────
def test_require_admin_blocca_dipendente(dbmock):
    from app.lotti.auth import require_admin, make_token
    from fastapi import HTTPException

    class Req:
        def __init__(self, token):
            self.headers = {"authorization": f"Bearer {token}", "X-Admin-Pin": ""}
            self.state = type("S", (), {})()

    tok_dip = make_token("op1", "Mario", "operatore")
    with pytest.raises(HTTPException) as exc:
        run(require_admin(Req(tok_dip)))
    assert exc.value.status_code == 403

    tok_admin = make_token("enzo", "Enzo", "amministratore")
    assert run(require_admin(Req(tok_admin))) is None  # passa senza eccezioni


# ── 4. TRANCHE 4: blocco richiamo, idempotenza, dedup debole, delete sicura ─
def test_richiamo_blocca_lotto_e_manda_al_banco_rifiuta(dbmock):
    import app.lotti.routers.lotti_produzione as lp
    from fastapi import HTTPException
    run(dbmock.lotti.insert_one({"id": "LP1", "numero_lotto": "SFO-001",
        "prodotto": "Sfogliatella", "quantita": 10, "frigo_numero": "Frigo 1"}))
    r = run(lp.registra_richiamo_eseguito(
        {"ingrediente": "ricotta", "filtri": {}, "lotti_ids": ["LP1"]},
        motivo="allerta fornitore", operatore_id=None, operatore_nome="Enzo"))
    assert r["ok"]
    doc = run(dbmock.lotti.find_one({"id": "LP1"}))
    assert doc["stato"] == "bloccato_richiamo" and doc["richiamo_ref"]
    blocchi = run(dbmock.blocchi_lotti.find({"lotto_id": "LP1"}).to_list(10))
    assert blocchi and blocchi[0]["azione"] == "blocco" and blocchi[0]["motivazione"]
    # manda al banco DEVE rifiutare (423)
    with pytest.raises(HTTPException) as exc:
        run(lp.manda_lotto_al_banco("LP1", pezzi=2, reparto="pasticceria", operatore_id=None, operatore_nome=None, operation_id=None))
    assert exc.value.status_code == 423
    # sblocco amministrativo motivato → registro sblocco
    run(lp.sblocca_lotto_richiamo("LP1", motivo="verifica negativa ASL", note="", operatore="Enzo", _admin=None))
    doc2 = run(dbmock.lotti.find_one({"id": "LP1"}))
    assert doc2["stato"] == "sbloccato"
    blocchi2 = run(dbmock.blocchi_lotti.find({"lotto_id": "LP1"}).to_list(10))
    assert any(b["azione"] == "sblocco" and b["motivazione"] for b in blocchi2)


def test_manda_al_banco_idempotente_con_operation_id(dbmock):
    import app.lotti.routers.lotti_produzione as lp
    run(dbmock.lotti.insert_one({"id": "LP2", "numero_lotto": "PANE-001",
        "prodotto": "Pane", "quantita": 10}))
    r1 = run(lp.manda_lotto_al_banco("LP2", pezzi=2, reparto="pasticceria", operatore_id=None, operatore_nome=None, operation_id="op-abc"))
    r2 = run(lp.manda_lotto_al_banco("LP2", pezzi=2, reparto="pasticceria", operatore_id=None, operatore_nome=None, operation_id="op-abc"))
    doc = run(dbmock.lotti.find_one({"id": "LP2"}))
    assert doc["quantita"] == 8, "il replay NON deve scalare di nuovo"
    assert r2.get("movimento_id") == r1.get("movimento_id") or r2.get("gia_eseguita") or r2 == r1


def test_dedup_senza_piva_conserva_entrambe(dbmock):
    import app.lotti.routers.fatture as fat
    run(dbmock.fatture.create_index([("numero_fattura", 1), ("piva", 1)],
                                    unique=True, name="uniq_numero_piva"))
    xml_a = _xml_fattura(numero="77", piva="").replace(b"MOLINO TEST SRL", b"FORNITORE ALFA")
    xml_b = _xml_fattura(numero="77", piva="").replace(b"MOLINO TEST SRL", b"FORNITORE BETA")
    run(fat.importa_fattura_xml(files=[_upload("a.xml", xml_a)]))
    esito = run(fat.importa_fattura_xml(files=[_upload("b.xml", xml_b)]))
    n = run(dbmock.fatture.count_documents({"numero_fattura": "77"}))
    assert n == 2, f"fornitori DIVERSI senza P.IVA: entrambe conservate, trovate {n} ({esito.get('errori')})"
    dubbia = run(dbmock.fatture.find_one({"verifica_richiesta": True}))
    assert dubbia is not None, "la seconda va marcata 'possibile duplicato — verifica richiesta'"


def test_delete_fattura_sicura_e_annullamento(dbmock):
    import app.lotti.routers.fatture as fat
    from fastapi import HTTPException
    run(fat.importa_fattura_xml(files=[_upload("f.xml", _xml_fattura(numero="88"))]))
    f = run(dbmock.fatture.find_one({"numero_fattura": "88"}))
    # lotti mai movimentati → senza conferma 409, con conferma elimina tutto
    with pytest.raises(HTTPException) as exc:
        run(fat.delete_fattura(f["id"], conferma=False, _admin=None))
    assert exc.value.status_code == 409
    run(fat.delete_fattura(f["id"], conferma=True, _admin=None))
    assert run(dbmock.fatture.count_documents({"numero_fattura": "88"})) == 0
    assert run(dbmock.lotti_fornitori.count_documents({"fattura_ref": "88"})) == 0
    # fattura USATA → mai eliminabile, solo annullamento logico
    run(fat.importa_fattura_xml(files=[_upload("g.xml", _xml_fattura(numero="99"))]))
    g = run(dbmock.fatture.find_one({"numero_fattura": "99"}))
    run(dbmock.lotti_fornitori.update_one({"fattura_ref": "99"},
        {"$push": {"storico_utilizzi": {"ricetta": "Pane", "lotto_produzione": "X"}}}))
    with pytest.raises(HTTPException) as exc:
        run(fat.delete_fattura(g["id"], conferma=True, _admin=None))
    assert exc.value.status_code == 409
    run(fat.annulla_fattura(g["id"], motivo="fattura errata", _admin=None))
    g2 = run(dbmock.fatture.find_one({"id": g["id"]}))
    assert g2["annullata"] is True and g2["annullata_motivo"]
    lotti = run(dbmock.lotti_fornitori.find({"fattura_ref": "99"}).to_list(20))
    assert all(l.get("esaurito") for l in lotti), "i lotti dell'annullata escono dal FIFO"


def test_conversione_non_disponibile_non_scala(dbmock):
    import app.lotti.routers.lotti_produzione as lp
    run(dbmock.lotti_fornitori.insert_one(
        {"id": "L-cartoni", "prodotto_nome": "Farina 00", "prodotto_nome_norm": "farina 00",
         "fornitore": "Molino A", "quantita_disponibile": 5, "unita_misura": "CT",
         "data_fattura": _data_fattura(30), "esaurito": False}))
    esito = run(lp.scala_lotti_fornitori_per_ricetta(RICETTA_PANE, 1, "L"))
    doc = run(dbmock.lotti_fornitori.find_one({"id": "L-cartoni"}))
    assert doc["quantita_disponibile"] == 5, "unità incompatibili: il lotto NON va toccato"
    assert not esito["lotti_scalati"]
    assert esito["conversioni_non_disponibili"], esito
    c = esito["conversioni_non_disponibili"][0]
    assert c["unita_lotto"] == "CT" and c["unita_ricetta"] == "g"


def test_cascata_multilotto_usa_il_fattore_di_ogni_lotto(dbmock):
    """Audit quantità/unità §2: due lotti dello STESSO prodotto con
    confezionamento diverso (X24 e X12). Scaricando più pezzi di quanti ne ha
    il lotto più vecchio, la cascata deve scalare il secondo lotto col SUO
    fattore, non con quello del lotto cliccato."""
    import app.lotti.routers.magazzino_unificato as mu
    # più vecchio: 1 cartone da 24 pezzi ; più recente: 3 cartoni da 12
    run(dbmock.lotti_fornitori.insert_many([
        {"id": "LF-24", "prodotto_nome": "ACQUA NAT CL 50 X 24",
         "prodotto_nome_norm": "acqua nat", "fornitore": "Bevande Sud",
         "quantita_disponibile": 1, "unita_misura": "CT",
         "data_fattura": _data_fattura(30), "esaurito": False},
        {"id": "LF-12", "prodotto_nome": "ACQUA NAT CL 50 X 12",
         "prodotto_nome_norm": "acqua nat", "fornitore": "Bevande Sud",
         "quantita_disponibile": 3, "unita_misura": "CT",
         "data_fattura": _data_fattura(21), "esaurito": False},
    ]))

    # disponibili: 24 + 36 = 60 pezzi. Ne scarico 30.
    esito = run(mu.scarico_unificato(mu.ScaricoPayload(
        prodotto_id="LF-24", source="fornitori", quantita=30,
        operatore_nome="Mario", nota="test cascata")))

    assert esito["ok"] is True
    assert esito["stock_nuovo"] == 30, esito  # 60 - 30 pezzi

    vecchio = run(dbmock.lotti_fornitori.find_one({"id": "LF-24"}))
    recente = run(dbmock.lotti_fornitori.find_one({"id": "LF-12"}))
    assert vecchio["quantita_disponibile"] == 0 and vecchio["esaurito"] is True
    # 6 pezzi residui dal secondo lotto = 0,5 cartoni DA 12 (col fattore
    # sbagliato del lotto cliccato sarebbero stati 3 - 6/24 = 2,75)
    assert recente["quantita_disponibile"] == 2.5, recente
    assert sum(m["quantita"] for m in esito["lotti_consumati"]) == 30


def test_cascata_non_tocca_lotti_non_confrontabili(dbmock):
    """Un lotto sfuso a KG dello stesso prodotto non deve entrare nella cascata
    a pezzi: senza il peso reale sarebbe una conversione inventata."""
    import app.lotti.routers.magazzino_unificato as mu
    run(dbmock.lotti_fornitori.insert_many([
        {"id": "LF-ct", "prodotto_nome": "BIRRA CL 33 X 24",
         "prodotto_nome_norm": "birra", "fornitore": "Bevande Sud",
         "quantita_disponibile": 2, "unita_misura": "CT",
         "data_fattura": _data_fattura(26), "esaurito": False},
        {"id": "LF-kg", "prodotto_nome": "BIRRA SFUSA",
         "prodotto_nome_norm": "birra", "fornitore": "Bevande Sud",
         "quantita_disponibile": 20, "unita_misura": "KG",
         "data_fattura": _data_fattura(30), "esaurito": False},
    ]))

    esito = run(mu.scarico_unificato(mu.ScaricoPayload(
        prodotto_id="LF-ct", source="fornitori", quantita=10,
        operatore_nome="Mario", nota="")))

    kg = run(dbmock.lotti_fornitori.find_one({"id": "LF-kg"}))
    assert kg["quantita_disponibile"] == 20, "il lotto a KG resta intatto"
    assert esito["stock_nuovo"] == 38  # 48 pezzi - 10


def test_proponi_ingredienti_a_tutte_le_ricette_vuote(dbmock, monkeypatch):
    """Compilazione di massa (Enzo 25/07/2026): riempie SOLO le ricette senza
    ingredienti, non tocca quelle già compilate né i prodotti di rivendita, e
    marca ciò che ha proposto la macchina."""
    import app.lotti.routers.food_cost as fc
    run(dbmock.ricette.insert_many([
        {"id": "R-vuota1", "nome": "Sfogliatella riccia", "porzioni": 10,
         "ingredienti_dettaglio": [], "ingredienti": []},
        {"id": "R-vuota2", "nome": "Babà al rum", "porzioni": 12,
         "ingredienti_dettaglio": [], "ingredienti": []},
        {"id": "R-piena", "nome": "Pastiera napoletana", "porzioni": 8,
         "ingredienti_dettaglio": [{"nome": "Grano cotto", "quantita": 500, "unita_misura": "g"}],
         "ingredienti": ["Grano cotto"]},
        {"id": "R-rivendita", "nome": "Cornetto Acquaviva", "porzioni": 1,
         "ingredienti_dettaglio": [], "ingredienti": [], "fornitore_rivendita": "Acquaviva"},
    ]))

    elenco = run(fc.ricette_senza_ingredienti())
    assert elenco["da_compilare"] == 2, elenco
    nomi = {r["nome"] for r in elenco["ricette"]}
    assert nomi == {"Sfogliatella riccia", "Babà al rum"}

    esito = run(fc.proponi_ingredienti_tutte(fc.ProponiTutteReq(limite=10), _admin=None))
    assert esito["compilate"] == 2, esito
    assert esito["restanti"] == 0

    v1 = run(dbmock.ricette.find_one({"id": "R-vuota1"}))
    assert v1["ingredienti_dettaglio"], "la ricetta vuota è stata compilata"
    assert v1["ingredienti_origine"] == "automatica"
    assert v1["ingredienti_fonte"], "la fonte della proposta è tracciata"

    piena = run(dbmock.ricette.find_one({"id": "R-piena"}))
    assert piena["ingredienti_dettaglio"] == [
        {"nome": "Grano cotto", "quantita": 500, "unita_misura": "g"}], "MAI sovrascritta"
    assert "ingredienti_origine" not in piena

    riv = run(dbmock.ricette.find_one({"id": "R-rivendita"}))
    assert not riv["ingredienti_dettaglio"], "i prodotti di rivendita restano vuoti"


def test_pulizia_notturna_archivia_e_non_cancella(dbmock):
    """Audit import/database §2.2: il job delle 01:30 non deve più cancellare
    fisicamente i lotti scaduti — il registro ASL va conservato 5 anni."""
    import app.lotti.routers.scheduler as sch
    run(dbmock.ricette.insert_one({"id": "R1", "nome": "Pastiera", "ingredienti": ["Grano cotto"]}))
    run(dbmock.lotti.insert_many([
        # scaduto da oltre 30 giorni e prodotto non più in ricetta → archiviabile
        {"id": "L-vecchio", "prodotto": "Torta dismessa", "numero_lotto": "TD-001",
         "data_scadenza": "2020-01-15"},
        # scaduto ma il prodotto è ancora in ricetta → intoccato
        {"id": "L-inricetta", "prodotto": "Pastiera", "numero_lotto": "PAS-001",
         "data_scadenza": "2020-01-15"},
    ]))
    # movimento che cita il lotto vecchio: non deve restare orfano
    run(dbmock.movimenti_lotto.insert_one({"lotto_id": "L-vecchio", "tipo": "creazione"}))

    run(sch.job_pulisci_lotti_scaduti())

    vecchio = run(dbmock.lotti.find_one({"id": "L-vecchio"}))
    assert vecchio is not None, "il lotto NON deve sparire dal database"
    assert vecchio["archiviato"] is True
    assert vecchio["archiviato_motivo"]
    in_ricetta = run(dbmock.lotti.find_one({"id": "L-inricetta"}))
    assert "archiviato" not in in_ricetta, "prodotto ancora in ricetta: non si tocca"

    log = run(dbmock.scheduler_logs.find_one({"job": "pulizia_lotti_scaduti"}))
    assert log["lotti_archiviati"] == 1

    # secondo giro: già archiviato, non lo riconta
    run(sch.job_pulisci_lotti_scaduti())
    logs = run(dbmock.scheduler_logs.find({"job": "pulizia_lotti_scaduti"}).to_list(10))
    assert logs[-1]["lotti_archiviati"] == 0


def test_etichetta_mostra_la_data_della_fattura(dbmock):
    """Richiesta Enzo 25/07/2026: sull'etichetta c'era il numero della fattura
    ma non la data — davanti all'ASL il numero da solo non basta a datare la
    materia prima."""
    import app.lotti.routers.stampa as st
    run(dbmock.lotti.insert_one({
        "id": "L-etic", "numero_lotto": "SFOGL-999", "prodotto": "Sfogliatella riccia",
        "data_produzione": "2026-07-02", "data_scadenza": "2026-07-05",
        "quantita": 1, "unita_misura": "pz", "frigo_numero": "Congelatore 1",
        "ingredienti_dettaglio": [{"nome": "semola", "quantita": 500, "unita_misura": "g"}],
        "lotti_fornitori": {"lotti_scalati": [{
            "ingrediente": "semola", "prodotto": "SEMOLA RIMACINATA",
            "fornitore": "SAIMA S.p.A.", "fattura_ref": "1/56437",
            "data_fattura": "12/06/2026", "lotto_id_fornitore": "FAT-1/56437",
            "quantita_consumata": 0.5, "quantita_rimasta": 24.5, "unita": "kg",
        }]},
    }))

    html = run(st.stampa_lotto("SFOGL-999"))
    testo = html if isinstance(html, str) else getattr(html, "body", b"").decode("utf-8", "ignore")
    assert "1/56437" in testo, "il numero fattura c'era già"
    assert "12/06/2026" in testo, "manca la DATA della fattura sull'etichetta"
    assert "del 12/06/2026" in testo


def test_compilazione_di_massa_porta_la_base_a_un_chilo(dbmock):
    """Enzo 25/07/2026: le ricette compilate in automatico devono uscire con
    dosi da laboratorio — l'ingrediente base a 1 kg — e vanno compilate anche
    quelle che hanno gli ingredienti ma nessuna quantità."""
    import app.lotti.routers.food_cost as fc
    run(dbmock.ricette.insert_many([
        {"id": "R-vuota", "nome": "Sfogliatella riccia", "porzioni": 10,
         "ingredienti_dettaglio": [], "ingredienti": []},
        # ha gli ingredienti ma tutte le dosi a zero: prima veniva ignorata
        {"id": "R-senzaqta", "nome": "Babà al rum", "porzioni": 8,
         "ingredienti": ["Farina 00", "Uova"],
         "ingredienti_dettaglio": [
             {"nome": "Farina 00", "quantita": 0, "unita_misura": "g"},
             {"nome": "Uova", "quantita": 0, "unita_misura": "pz"}]},
    ]))

    elenco = run(fc.ricette_senza_ingredienti())
    motivi = {r["nome"]: r["motivo"] for r in elenco["ricette"]}
    assert motivi["Sfogliatella riccia"] == "senza_ingredienti"
    assert motivi["Babà al rum"] == "senza_quantita"
    assert elenco["da_compilare"] == 2

    run(fc.proponi_ingredienti_tutte(fc.ProponiTutteReq(limite=10), _admin=None))

    for rid in ("R-vuota", "R-senzaqta"):
        doc = run(dbmock.ricette.find_one({"id": rid}))
        det = doc["ingredienti_dettaglio"]
        assert det, rid
        pesabili = [i for i in det
                    if (i.get("unita_misura") or "g").lower() in ("g", "gr", "ml", "kg", "l")
                    and float(i.get("quantita") or 0) > 0]
        if pesabili:
            massimo = max(float(i["quantita"]) * (1000 if (i.get("unita_misura") or "g").lower() in ("kg", "l") else 1)
                          for i in pesabili)
            assert abs(massimo - 1000) < 1, f"{rid}: la base deve stare a 1 kg, trovato {massimo}"
            assert doc.get("dose_riferimento", "").startswith("1 kg di ")


def test_dose_di_produzione_riscala_sulla_farina(dbmock):
    """Enzo 25/07/2026: il pasticciere dice quanta farina usa oggi (6,5 kg per
    i cornetti) e tutti gli altri ingredienti si adeguano da soli."""
    import app.lotti.routers.food_cost as fc
    run(dbmock.ricette.insert_one({
        "id": "R-cornetti", "nome": "Cornetti", "porzioni": 20,
        "ingredienti_dettaglio": [
            {"nome": "Farina 00", "quantita": 1, "unita_misura": "kg"},
            {"nome": "Burro", "quantita": 250, "unita_misura": "g"},
            {"nome": "Uova", "quantita": 4, "unita_misura": "pz"},
        ],
    }))

    out = run(fc.dose_produzione("R-cornetti", fc.DoseProduzioneReq(quantita_base=6.5, unita="kg")))
    assert out["base"] == "Farina 00" and out["fattore"] == 6.5
    per_nome = {i["nome"]: i["quantita"] for i in out["ingredienti"]}
    assert per_nome["Farina 00"] == 6.5      # 6,5 kg, resta in kg
    assert per_nome["Burro"] == 1625         # 250 g × 6,5
    assert per_nome["Uova"] == 26            # 4 pz × 6,5
    assert out["porzioni_stimate"] == 130    # 20 × 6,5


def test_dose_di_produzione_riso_per_gli_arancini(dbmock):
    import app.lotti.routers.food_cost as fc
    run(dbmock.ricette.insert_one({
        "id": "R-aranc", "nome": "Arancini", "porzioni": 10,
        "ingredienti_dettaglio": [
            {"nome": "Riso", "quantita": 500, "unita_misura": "g"},
            {"nome": "Ragù", "quantita": 300, "unita_misura": "g"},
            {"nome": "Pangrattato", "quantita": 150, "unita_misura": "g"},
        ],
    }))
    out = run(fc.dose_produzione("R-aranc", fc.DoseProduzioneReq(quantita_base=3, unita="kg")))
    assert out["base"] == "Riso" and out["fattore"] == 6.0
    per_nome = {i["nome"]: i["quantita"] for i in out["ingredienti"]}
    assert per_nome == {"Riso": 3000, "Ragù": 1800, "Pangrattato": 900}


def test_dose_di_produzione_senza_dosi_lo_dice(dbmock):
    import app.lotti.routers.food_cost as fc
    from fastapi import HTTPException
    run(dbmock.ricette.insert_one({
        "id": "R-vuoto", "nome": "Senza dosi", "porzioni": 1,
        "ingredienti_dettaglio": [{"nome": "Cornetti", "quantita": 10, "unita_misura": "pz"}],
    }))
    with pytest.raises(HTTPException) as exc:
        run(fc.dose_produzione("R-vuoto", fc.DoseProduzioneReq(quantita_base=1, unita="kg")))
    assert exc.value.status_code == 400
    assert "ingrediente di riferimento" in str(exc.value.detail)
