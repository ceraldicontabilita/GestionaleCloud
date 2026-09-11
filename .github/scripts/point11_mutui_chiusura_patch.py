from pathlib import Path


def replace_once(path, old, new):
    p = Path(path)
    text = p.read_text()
    if old not in text:
        raise SystemExit(f"marker not found in {path}: {old[:180]}")
    p.write_text(text.replace(old, new, 1))


# Mutui: automatic reconciliation only for exactly one candidate.
path = "app/routers/mutui.py"
replace_once(path, '''                movimento = await db.estratto_conto_movimenti.find_one(query_movimenti)
                # Fallback senza filtro descrizione (banche con causali generiche),
                # solo se il match per importo+data è univoco.
                if not movimento:
                    query_no_desc = {k: v for k, v in query_movimenti.items() if k != "$or"}
                    candidati = await db.estratto_conto_movimenti.find(query_no_desc).to_list(2)
                    if len(candidati) == 1:
                        movimento = candidati[0]
''', '''                # Anche una causale esplicita MUTUO/RATA non basta se più
                # movimenti soddisfano importo e finestra temporale: automatico
                # soltanto con candidato univoco.
                candidati_descrittivi = await db.estratto_conto_movimenti.find(
                    query_movimenti
                ).to_list(2)
                movimento = candidati_descrittivi[0] if len(candidati_descrittivi) == 1 else None
                candidati_ambigui = len(candidati_descrittivi) > 1

                # Fallback senza filtro descrizione (banche con causali generiche),
                # soltanto se il percorso descrittivo non era già ambiguo.
                if not movimento and not candidati_ambigui:
                    query_no_desc = {k: v for k, v in query_movimenti.items() if k != "$or"}
                    candidati = await db.estratto_conto_movimenti.find(query_no_desc).to_list(2)
                    if len(candidati) == 1:
                        movimento = candidati[0]
                    elif len(candidati) > 1:
                        candidati_ambigui = True
''')
replace_once(path, '''                        "status": "richiede_riconciliazione_manuale"
                    })
''', '''                        "status": "richiede_riconciliazione_manuale",
                        "motivo": "candidati_ambigui" if candidati_ambigui else "nessun_match_univoco",
                    })
''')
replace_once(path, '''        if not movimento:
            raise HTTPException(status_code=404, detail="Movimento bancario non trovato")

        data_movimento = movimento.get("data_valuta") or movimento.get("data", "")
''', '''        if not movimento:
            raise HTTPException(status_code=404, detail="Movimento bancario non trovato")
        if movimento.get("riconciliato"):
            stesso_collegamento = (
                movimento.get("tipo_documento") == "mutuo"
                and movimento.get("documento_id") == mutuo_id
                and movimento.get("rata_numero") == numero_rata
            )
            if not stesso_collegamento:
                raise HTTPException(
                    status_code=409,
                    detail="Movimento bancario già riconciliato con un altro documento",
                )

        data_movimento = movimento.get("data_valuta") or movimento.get("data", "")
''')

# Chiusura/apertura: Mastercard SumUp is a separate patrimonial cash account.
path = "app/routers/chiusura_esercizio.py"
replace_once(path, '''    query_cassa = filtro_saldo_prima_nota("prima_nota_cassa", data=intervallo_prima_nota)
    query_banca = filtro_saldo_prima_nota("prima_nota_banca", data=intervallo_prima_nota)
    saldo_cassa = (
''', '''    query_cassa = filtro_saldo_prima_nota("prima_nota_cassa", data=intervallo_prima_nota)
    query_banca = filtro_saldo_prima_nota("prima_nota_banca", data=intervallo_prima_nota)
    query_sumup = filtro_saldo_prima_nota("prima_nota_sumup", data=intervallo_prima_nota)
    saldo_cassa = (
''')
replace_once(path, '''    saldo_banca = (
        await aggrega_saldo_prima_nota(
            db, "prima_nota_banca", query_banca, anno=anno_precedente
        )
    )["saldo"]

    data_chiusura = f"{anno_precedente}-12-31"
''', '''    saldo_banca = (
        await aggrega_saldo_prima_nota(
            db, "prima_nota_banca", query_banca, anno=anno_precedente
        )
    )["saldo"]
    saldo_sumup = (
        await aggrega_saldo_prima_nota(
            db, "prima_nota_sumup", query_sumup, anno=anno_precedente
        )
    )["saldo"]

    data_chiusura = f"{anno_precedente}-12-31"
''')
replace_once(path, '''            "saldo_cassa": saldo_cassa,
            "saldo_banca": saldo_banca,
            "debiti_fornitori": debiti_fornitori,
''', '''            "saldo_cassa": saldo_cassa,
            "saldo_banca": saldo_banca,
            "saldo_sumup_mastercard": saldo_sumup,
            "debiti_fornitori": debiti_fornitori,
''')

Path("tests/test_point11_mutui_chiusura.py").write_text(r'''import asyncio
from pathlib import Path
from types import SimpleNamespace

from app.routers import mutui


def _run(coro):
    return asyncio.run(coro)


class _Cursor:
    def __init__(self, docs):
        self.docs = list(docs)
    async def to_list(self, length=None):
        return list(self.docs if length is None else self.docs[:length])
    def __aiter__(self):
        self._i = 0
        return self
    async def __anext__(self):
        if self._i >= len(self.docs):
            raise StopAsyncIteration
        value = self.docs[self._i]
        self._i += 1
        return value


class _Collection:
    def __init__(self, docs=None):
        self.docs = list(docs or [])
        self.updates = []
    def find(self, *args, **kwargs):
        return _Cursor(self.docs)
    async def find_one(self, query, *args, **kwargs):
        return self.docs[0] if self.docs else None
    async def update_one(self, query, update, *args, **kwargs):
        self.updates.append((query, update))
        return SimpleNamespace(modified_count=1)


class _Db:
    def __init__(self):
        self.mutui = _Collection([{
            "mutuo_id": "M1",
            "nome": "Mutuo test",
            "rate_pagate": 1,
            "rate": [{
                "numero_rata": 1,
                "stato": "Pagata",
                "riconciliata": False,
                "data_scadenza": "10/06/2026",
                "importo_totale": 500.0,
                "quota_capitale": 450.0,
                "quota_interessi": 50.0,
            }],
        }])
        # Due candidati: anche con causale forte non si deve scegliere il primo.
        self.estratto_conto_movimenti = _Collection([
            {"_id": "B1", "data": "2026-06-10", "tipo": "uscita", "importo": 500.0,
             "descrizione": "RATA MUTUO"},
            {"_id": "B2", "data": "2026-06-11", "tipo": "uscita", "importo": 500.0,
             "descrizione": "RATA MUTUO"},
        ])


def test_mutuo_due_candidati_non_riconcilia_automaticamente(monkeypatch):
    db = _Db()
    monkeypatch.setattr(mutui, "get_db", lambda: db)
    out = _run(mutui.riconcilia_mutui_con_estratto_conto())
    data = out["data"]
    assert data["riconciliazioni_automatiche"] == 0
    assert data["riconciliazioni_manuali_richieste"] == 1
    assert data["dettagli"][0]["motivo"] == "candidati_ambigui"
    assert db.estratto_conto_movimenti.updates == []
    # L'unico update sul mutuo è il ricalcolo finale della percentuale,
    # nessuna rata viene associata a B1/B2.
    assert not any(
        "rate.$.movimento_bancario_id" in (update.get("$set") or {})
        for _, update in db.mutui.updates
    )


def test_apertura_esercizio_riporta_sumup_separato_da_bpm():
    source = Path("app/routers/chiusura_esercizio.py").read_text()
    assert 'filtro_saldo_prima_nota("prima_nota_sumup"' in source
    assert 'db, "prima_nota_sumup", query_sumup' in source
    assert '"saldo_sumup_mastercard": saldo_sumup' in source
''')
