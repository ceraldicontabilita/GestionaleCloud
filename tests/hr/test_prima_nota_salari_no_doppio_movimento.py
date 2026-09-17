"""Bug "doppio conteggio reale" trovato nell'audit funzionale del
15/07/2026: salari_unificati_v2.py::processa_cedolino_v2 (canale
cedolini_manager/Drive/email "v2") scrive DIRETTAMENTE un movimento in
prima_nota_salari (source="cedolino_v2", tipo="stipendio", chiave
codice_fiscale+mese+anno) e SUBITO DOPO propaga l'evento CEDOLINO_IMPORTATO.
handler_prima_nota_cedolino (app/handlers/prima_nota.py), registrato su
quello stesso evento, cercava l'anti-duplicato con
{dipendente_id, mese, anno, source="cedolino_auto"} — un filtro che il
record appena scritto da salari_unificati_v2.py non soddisfa mai (source
diverso) — quindi inseriva un SECONDO movimento per lo stesso stipendio:
doppia uscita reale in cassa/bilancio per lo stesso dipendente/mese."""
import asyncio

from app.handlers import prima_nota as mod


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


class _FakeCollection:
    def __init__(self, docs=None):
        self.docs = docs or []

    async def find_one(self, query, *a, **k):
        for d in self.docs:
            if all(d.get(k2) == v2 for k2, v2 in query.items()):
                return dict(d)
        return None

    async def insert_one(self, doc, *a, **k):
        self.docs.append(dict(doc))


class _FakeDb:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _FakeCollection())


def test_non_duplica_movimento_gia_scritto_da_salari_unificati_v2():
    db = _FakeDb()
    # Movimento già scritto direttamente da salari_unificati_v2.py per lo
    # stesso dipendente/mese/anno, con source/tipo diversi da quelli attesi
    # dal vecchio filtro anti-duplicato (source="cedolino_v2", non
    # "cedolino_auto"; tipo="stipendio", non "uscita").
    db["prima_nota_salari"].docs = [
        {"id": "pn-1", "dipendente_id": "dip-1", "mese": 5, "anno": 2026,
         "source": "cedolino_v2", "tipo": "stipendio", "importo_busta": 1500.0},
    ]

    esito = _run(mod.handler_prima_nota_cedolino({
        "dipendente_id": "dip-1", "nome_dipendente": "Mario Rossi",
        "codice_fiscale": "RSSMRA80A01H501U", "netto": 1500.0,
        "mese": 5, "anno": 2026,
    }, db))

    assert esito["skipped"] is True
    assert esito["reason"] == "movimento già presente"
    assert len(db["prima_nota_salari"].docs) == 1  # nessun secondo movimento


def test_crea_movimento_se_davvero_non_esiste():
    db = _FakeDb()

    esito = _run(mod.handler_prima_nota_cedolino({
        "dipendente_id": "dip-2", "nome_dipendente": "Anna Bianchi",
        "codice_fiscale": "BNCNNA85B02H501X", "netto": 1300.0,
        "mese": 6, "anno": 2026,
    }, db))

    assert "movimento_id" in esito
    assert len(db["prima_nota_salari"].docs) == 1
    assert db["prima_nota_salari"].docs[0]["source"] == "cedolino_auto"


def test_dipendente_diverso_o_mese_diverso_non_blocca():
    db = _FakeDb()
    db["prima_nota_salari"].docs = [
        {"id": "pn-1", "dipendente_id": "dip-1", "mese": 5, "anno": 2026,
         "source": "cedolino_v2", "tipo": "stipendio"},
    ]

    esito = _run(mod.handler_prima_nota_cedolino({
        "dipendente_id": "dip-1", "nome_dipendente": "Mario Rossi",
        "codice_fiscale": "RSSMRA80A01H501U", "netto": 1500.0,
        "mese": 6, "anno": 2026,  # mese diverso: nuovo movimento legittimo
    }, db))

    assert "movimento_id" in esito
    assert len(db["prima_nota_salari"].docs) == 2
