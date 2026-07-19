"""FASE A del motore unico (decisione utente 18/07/2026):

1. il motore valida le scritture (mai importi non positivi, date rotte,
   movimenti senza source);
2. TEST-GUARDIA: nessun NUOVO file può scrivere direttamente in
   prima_nota_cassa/banca — la lista dei writer storici è congelata e può
   solo restringersi, mai crescere;
3. TEST-GUARDIA: le righe sintetiche 'corrispettivo_pos' non devono più
   nascere (l'entrata banca è l'accredito reale dell'estratto conto) e la
   Coerenza POS non deve leggere prima_nota_banca come fonte accrediti.
"""
import asyncio
import pathlib
import re

import pytest

from app.services.scritture_contabili import (
    ScritturaNonValida,
    _valida,
    registra_corrispettivo,
)

APP = pathlib.Path(__file__).resolve().parents[1] / "app"

# Writer diretti esistenti al momento del congelamento (18/07/2026).
# Questa lista può SOLO restringersi man mano che i flussi migrano al
# motore unico. Se questo test fallisce per un file NUOVO: usare
# app/services/scritture_contabili.scrivi_movimento, non insert diretti.
WRITER_STORICI_CONGELATI = {
    "services/scritture_contabili.py",  # il motore: UNICO punto di insert
}

_RE_WRITE = re.compile(r'\b(?:prima_nota_cassa|prima_nota_banca)"?\]\s*\.\s*insert_(?:one|many)')
# Audit 19/07/2026: la regex sopra cattura solo db["prima_nota_cassa"].insert_
# (accesso a stringa letterale). Non catturava l'accesso per ATTRIBUTO
# (db.prima_nota_banca.insert_one), trovato in un file morto (nessun
# chiamante, rimosso). Aggiunta qui per non perdere protezione in futuro,
# anche se non copre ancora l'accesso tramite variabile calcolata
# (es. coll = db[nome_variabile]; coll.insert_one(...)), il bypass più
# diffuso oggi (rapido.py, prima_nota_module/sync.py e manutenzione.py,
# data_propagation.py, cassa.py, banca.py — vedi memoria/BACKLOG.md):
# richiede analisi AST, non ancora fatta.
_RE_WRITE_ATTR = re.compile(r'\.\s*(?:prima_nota_cassa|prima_nota_banca)\s*\.\s*insert_(?:one|many)')


def _writer_attuali():
    trovati = set()
    for f in APP.rglob("*.py"):
        rel = f.relative_to(APP).as_posix()
        testo = f.read_text(encoding="utf-8")
        if _RE_WRITE.search(testo) or _RE_WRITE_ATTR.search(testo):
            trovati.add(rel)
    return trovati


def test_guardia_nessun_nuovo_writer_diretto():
    nuovi = _writer_attuali() - WRITER_STORICI_CONGELATI
    assert not nuovi, (
        f"NUOVI writer diretti in prima nota: {sorted(nuovi)}. "
        "Usare app/services/scritture_contabili.scrivi_movimento."
    )


def test_guardia_niente_sintetiche_corrispettivo_pos():
    """Nessun file deve più CREARE movimenti con source='corrispettivo_pos'
    (le letture di righe storiche sono ammesse finché la migrazione non è
    completa ovunque)."""
    colpevoli = []
    for f in APP.rglob("*.py"):
        testo = f.read_text(encoding="utf-8")
        # pattern di creazione: la stringa in un dict subito prima di un insert
        for m in re.finditer(r'"source":\s*"corrispettivo_pos"', testo):
            contesto = testo[max(0, m.start() - 600):m.start() + 600]
            # creazione = dict con la categoria sintetica E un insert vicino
            if '"categoria": "Corrispettivi POS"' in contesto and (
                    "insert_one" in contesto or "insert_many" in contesto):
                colpevoli.append(f.relative_to(APP).as_posix())
                break
    assert not colpevoli, f"Righe sintetiche corrispettivo_pos ancora create in: {colpevoli}"


def test_guardia_coerenza_pos_non_legge_prima_nota_banca():
    """La fonte degli accrediti POS per la Coerenza è l'ESTRATTO CONTO."""
    testo = (APP / "routers" / "pos_corrispettivi_check.py").read_text(encoding="utf-8")
    blocco = testo[testo.find("async def verifica_coerenza_pos_corrispettivi"):
                   testo.find("async def riepilogo_mensile_pos_corrispettivi")]
    accrediti = blocco[blocco.find("accrediti_pos"):blocco.find("chiusure_manuali")]
    assert 'db["estratto_conto_movimenti"]' in accrediti
    assert 'db["prima_nota_banca"]' not in accrediti


def test_guardia_riepilogo_mensile_pos_non_legge_prima_nota_banca():
    """FIX 18/07/2026: riepilogo_mensile_pos_corrispettivi era rimasta
    l'unica funzione del router non migrata (leggeva prima_nota_banca con
    una whitelist categorie senza "Corrispettivi POS", il totale annuo
    risultava incoerente con la vista giornaliera — segnalato dall'utente).
    Stessa fonte delle altre: l'ESTRATTO CONTO."""
    testo = (APP / "routers" / "pos_corrispettivi_check.py").read_text(encoding="utf-8")
    inizio = testo.find("async def riepilogo_mensile_pos_corrispettivi")
    fine = testo.find("\nasync def ", inizio + 10)
    blocco = testo[inizio:fine if fine != -1 else len(testo)]
    pos_query = blocco[blocco.find("pipeline_pos"):blocco.find("pos_result =") + 200]
    assert 'db["estratto_conto_movimenti"]' in pos_query
    assert 'db["prima_nota_banca"]' not in pos_query


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


def test_validazione_scritture():
    with pytest.raises(ScritturaNonValida):
        _valida({"data": "2026-01-01", "importo": 0, "tipo": "entrata",
                 "categoria": "X", "source": "s"})
    with pytest.raises(ScritturaNonValida):
        _valida({"data": "gennaio", "importo": 5, "tipo": "entrata",
                 "categoria": "X", "source": "s"})
    with pytest.raises(ScritturaNonValida):
        _valida({"data": "2026-01-01", "importo": 5, "tipo": "entrata",
                 "categoria": "X"})  # senza source
    _valida({"data": "2026-01-01", "importo": 5, "tipo": "entrata",
             "categoria": "X", "source": "s"})  # valida


class _Coll:
    def __init__(self):
        self.docs = []

    async def find_one(self, *a, **k):
        return None

    def find(self, *a, **k):
        class _C:
            def __aiter__(self):
                return self

            async def __anext__(self):
                raise StopAsyncIteration
        return _C()

    async def insert_one(self, doc):
        self.docs.append(doc)


class _Db(dict):
    def __getitem__(self, k):
        return self.setdefault(k, _Coll())


def test_registra_corrispettivo_trasferimento_speculare():
    """REGOLA CANONICA: uscita cassa POS = entrata banca POS = stessa
    operazione (trasferimento), stesso importo, stesso trasferimento_id."""
    db = _Db()
    esito = _run(registra_corrispettivo(db, {
        "id": "C1", "data": "2026-07-01", "totale": 1000.0,
        "pagato_contanti": 400.0, "pagato_elettronico": 600.0,
        "matricola_rt": "RT1",
    }))
    assert esito["prima_nota_cassa_id"]
    assert esito["prima_nota_cassa_uscita_pos_id"]
    assert esito["prima_nota_banca_id"]
    assert len(db["prima_nota_cassa"].docs) == 2
    assert len(db["prima_nota_banca"].docs) == 1
    uscita = db["prima_nota_cassa"].docs[1]
    banca = db["prima_nota_banca"].docs[0]
    assert uscita["categoria"] == "POS Verso Banca"
    assert uscita["importo"] == 600.0  # fallback XML: nessuna chiusura manuale
    assert uscita["quota_pos_fonte"] == "xml"
    assert banca["source"] == "trasferimento_pos"
    assert banca["importo"] == 600.0
    assert banca["trasferimento_id"] == uscita["trasferimento_id"]
    assert banca["riconciliato"] is False
