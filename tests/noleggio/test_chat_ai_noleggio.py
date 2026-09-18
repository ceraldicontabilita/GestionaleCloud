"""Test strumenti noleggio del motore AI della chat (chat_ai_engine).

Verifica che i nuovi tool cerca_veicoli_noleggio e cerca_verbali_noleggio
siano presenti nello schema, che l'executor li instradi, che la fusione
posta+fattura dei verbali deduplichi per numero_verbale e che i PDF non
finiscano mai nei risultati. Il repository asincrono è un doppio minimale.
"""
import asyncio
import json
from pathlib import Path

from app.services.chat_ai_engine import (
    KB_PATH,
    MAX_RISULTATI_NOLEGGIO,
    TOOLS_SCHEMA,
    _domini_pertinenti,
    _tool_cerca_veicoli_noleggio,
    _tool_cerca_verbali_noleggio,
    _TOOL_EXECUTORS,
)


# ---------------------------------------------------------------------------
# Finto DB asincrono: registra query/proiezione e restituisce documenti fissi
# (i filtri repository non vengono applicati: qui si testa la logica Python).
# ---------------------------------------------------------------------------

class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *args, **kwargs):
        return self

    async def to_list(self, n):
        return self._docs[:n]


class _FakeCollection:
    def __init__(self, docs):
        self._docs = docs
        self.ultima_query = None
        self.ultima_proiezione = None

    def find(self, query=None, projection=None):
        self.ultima_query = query
        self.ultima_proiezione = projection
        return _FakeCursor(self._docs)


class _FakeDB:
    def __init__(self, dati):
        self.collections = {nome: _FakeCollection(docs) for nome, docs in dati.items()}

    def __getitem__(self, nome):
        return self.collections.setdefault(nome, _FakeCollection([]))


class TestSchemaEdExecutor:
    def test_tool_presenti_nello_schema(self):
        nomi = {t["name"] for t in TOOLS_SCHEMA}
        assert "cerca_veicoli_noleggio" in nomi
        assert "cerca_verbali_noleggio" in nomi

    def test_parametri_schema(self):
        per_nome = {t["name"]: t for t in TOOLS_SCHEMA}
        props_veicoli = per_nome["cerca_veicoli_noleggio"]["input_schema"]["properties"]
        assert {"targa", "stato_contratto", "driver"} <= set(props_veicoli)
        props_verbali = per_nome["cerca_verbali_noleggio"]["input_schema"]["properties"]
        assert {"targa", "numero_verbale", "stato", "anno"} <= set(props_verbali)

    def test_executor_instrada_i_tool(self):
        assert _TOOL_EXECUTORS["cerca_veicoli_noleggio"] is _tool_cerca_veicoli_noleggio
        assert _TOOL_EXECUTORS["cerca_verbali_noleggio"] is _tool_cerca_verbali_noleggio

    def test_ogni_tool_dello_schema_ha_un_executor(self):
        # componi_risposta è gestito a parte nell'agent loop
        for t in TOOLS_SCHEMA:
            if t["name"] != "componi_risposta":
                assert t["name"] in _TOOL_EXECUTORS


class TestCercaVeicoliNoleggio:
    def test_query_e_proiezione(self):
        db = _FakeDB({"veicoli_noleggio": [
            {"targa": "GX037HJ", "marca": "BMW", "modello": "X1",
             "canone_mensile": 650.0, "stato_contratto": "attivo",
             "assegnazioni": [{"driver": "Valerio", "dal": "2024-01-01", "al": None}]},
        ]})
        out = asyncio.run(_tool_cerca_veicoli_noleggio(db, {
            "targa": "gx037hj", "stato_contratto": "attivo", "driver": "Valerio",
        }))
        assert len(out) == 1
        # lo storico assegnazioni deve arrivare al modello
        assert out[0]["assegnazioni"][0]["driver"] == "Valerio"

        coll = db.collections["veicoli_noleggio"]
        assert coll.ultima_query["targa"] == {"$regex": "gx037hj", "$options": "i"}
        assert coll.ultima_query["stato_contratto"] == "attivo"
        assert {"driver": {"$regex": "Valerio", "$options": "i"}} in coll.ultima_query["$or"]
        assert coll.ultima_proiezione["_id"] == 0
        assert coll.ultima_proiezione["assegnazioni"] == 1

    def test_tetto_30_risultati(self):
        db = _FakeDB({"veicoli_noleggio": [{"targa": f"AA{i:03d}AA"} for i in range(80)]})
        out = asyncio.run(_tool_cerca_veicoli_noleggio(db, {"limite": 100}))
        assert len(out) == MAX_RISULTATI_NOLEGGIO == 30


class TestCercaVerbaliNoleggio:
    def _db(self):
        return _FakeDB({
            "verbali_noleggio": [
                {"numero_verbale": "V-100", "targa": "GG782PN", "data_verbale": "2025-03-10",
                 "importo": 90.0, "stato": "pagato", "conducente": "Vincenzo",
                 "trattenuta_stato": "proposta", "pdf_ricevuta_path": "x.pdf"},
            ],
            "verbali_noleggio_completi": [
                # stesso verbale visto anche in fattura -> va deduplicato
                {"numero_verbale": "V-100", "targa": "GG782PN", "data_verbale": "2025-03-10",
                 "importo": 90.0, "stato_pagamento": "pagato", "numero_fattura": "FT-9"},
                # verbale presente solo in fattura
                {"numero_verbale": "V-200", "targa": "GG782PN", "data_verbale": "2025-05-02",
                 "importo": 42.0, "stato_pagamento": "da_pagare"},
            ],
        })

    def test_dedup_per_numero_verbale(self):
        out = asyncio.run(_tool_cerca_verbali_noleggio(self._db(), {"targa": "GG782PN"}))
        per_numero = {v["numero_verbale"]: v for v in out}
        assert set(per_numero) == {"V-100", "V-200"}
        assert per_numero["V-100"]["fonte"] == "posta+fattura"
        assert per_numero["V-100"]["pagato"] is True
        assert per_numero["V-100"]["conducente"] == "Vincenzo"
        assert per_numero["V-100"]["fattura_numero"] == "FT-9"
        assert per_numero["V-200"]["fonte"] == "fattura"
        assert per_numero["V-200"]["pagato"] is False

    def test_mai_pdf_nei_risultati(self):
        db = self._db()
        out = asyncio.run(_tool_cerca_verbali_noleggio(db, {}))
        for v in out:
            assert "pdf_data" not in v
            assert "pdf_allegati" not in v
            assert "quietanza_pdf" not in v
        # e la proiezione del repository li esclude alla fonte
        proj = db.collections["verbali_noleggio"].ultima_proiezione
        assert proj["pdf_data"] == 0 and proj["pdf_allegati"] == 0 and proj["quietanza_pdf"] == 0

    def test_filtro_anno_su_entrambe_le_fonti(self):
        db = self._db()
        asyncio.run(_tool_cerca_verbali_noleggio(db, {"anno": 2025}))
        q_posta = db.collections["verbali_noleggio"].ultima_query
        assert {"data_verbale": {"$regex": "^2025"}} in q_posta["$or"]
        assert db.collections["verbali_noleggio_completi"].ultima_query["anno"] == 2025


class TestDominioNoleggio:
    def test_parole_chiave_selezionano_il_dominio(self):
        for domanda in ("Quanto costa la BMW X1 al mese?",
                        "La Stelvio GG782PN è ancora attiva?",
                        "Che canone paghiamo per la Mazda?"):
            assert "noleggio" in _domini_pertinenti(domanda)

    def test_dominio_presente_in_kb(self):
        kb = json.loads(Path(KB_PATH).read_text(encoding="utf-8"))
        dominio = kb["domini"]["noleggio"]
        assert "veicoli_noleggio" in dominio["entita"]
        assert dominio["domande"]  # struttura come gli altri domini
