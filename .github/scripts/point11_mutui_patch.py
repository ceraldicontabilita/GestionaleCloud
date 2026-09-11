from pathlib import Path


def replace_once(path, old, new):
    p = Path(path)
    text = p.read_text()
    if old not in text:
        raise SystemExit(f'marker not found in {path}: {old[:180]}')
    p.write_text(text.replace(old, new, 1))

path = 'app/routers/mutui.py'

# Helper: never auto-select the first of multiple bank movements.
replace_once(path,
'''# ============================================================================
# RICONCILIAZIONE CON ESTRATTO CONTO
# ============================================================================

@router.post("/riconcilia", summary="Riconcilia rate mutui con estratto conto")
''',
'''# ============================================================================
# RICONCILIAZIONE CON ESTRATTO CONTO
# ============================================================================

async def _candidato_bancario_univoco(db, query_descrizione, query_fallback):
    """Restituisce un movimento solo quando il match e' univoco.

    Prima si prova il criterio piu' forte (causale + importo + data). Se produce
    piu' candidati non si degrada al fallback: l'ambiguita' resta da verificare.
    Il fallback senza causale e' ammesso soltanto quando il criterio forte non
    produce alcun candidato ed esso stesso produce esattamente un candidato.
    """
    forti = await db.estratto_conto_movimenti.find(query_descrizione).to_list(2)
    if len(forti) == 1:
        return forti[0], False, "causale_importo_data"
    if len(forti) > 1:
        return None, True, "piu_candidati_con_causale"

    fallback = await db.estratto_conto_movimenti.find(query_fallback).to_list(2)
    if len(fallback) == 1:
        return fallback[0], False, "importo_data_univoco"
    if len(fallback) > 1:
        return None, True, "piu_candidati_importo_data"
    return None, False, "nessun_candidato"


@router.post("/riconcilia", summary="Riconcilia rate mutui con estratto conto")
''')

replace_once(path,
'''                movimento = await db.estratto_conto_movimenti.find_one(query_movimenti)
                # Fallback senza filtro descrizione (banche con causali generiche),
                # solo se il match per importo+data è univoco.
                if not movimento:
                    query_no_desc = {k: v for k, v in query_movimenti.items() if k != "$or"}
                    candidati = await db.estratto_conto_movimenti.find(query_no_desc).to_list(2)
                    if len(candidati) == 1:
                        movimento = candidati[0]

                if movimento:
''',
'''                query_no_desc = {k: v for k, v in query_movimenti.items() if k != "$or"}
                movimento, ambiguo, criterio_match = await _candidato_bancario_univoco(
                    db, query_movimenti, query_no_desc
                )

                if movimento:
''')

replace_once(path,
'''                                "rate.$.note_riconciliazione": "Riconciliazione automatica"
''',
'''                                "rate.$.note_riconciliazione": (
                                    f"Riconciliazione automatica univoca ({criterio_match})"
                                )
''')

replace_once(path,
'''                else:
                    # Nessun match - richiede riconciliazione manuale
                    riconciliazioni["riconciliazioni_manuali_richieste"] += 1
                    riconciliazioni["dettagli"].append({
                        "mutuo_id": mutuo_id,
                        "mutuo_nome": mutuo.get("nome"),
                        "rata_numero": rata["numero_rata"],
                        "data_scadenza": rata["data_scadenza"],
                        "importo": rata["importo_totale"],
                        "status": "richiede_riconciliazione_manuale"
                    })
''',
'''                else:
                    # Nessun match o match ambiguo: nessuna mutazione bancaria.
                    riconciliazioni["riconciliazioni_manuali_richieste"] += 1
                    riconciliazioni["dettagli"].append({
                        "mutuo_id": mutuo_id,
                        "mutuo_nome": mutuo.get("nome"),
                        "rata_numero": rata["numero_rata"],
                        "data_scadenza": rata["data_scadenza"],
                        "importo": rata["importo_totale"],
                        "status": "da_verificare_ambiguita" if ambiguo else "richiede_riconciliazione_manuale",
                        "criterio_match": criterio_match,
                    })
''')

# Manual reconciliation: real EC movement must not already belong elsewhere.
replace_once(path,
'''        if not movimento:
            raise HTTPException(status_code=404, detail="Movimento bancario non trovato")

        data_movimento = movimento.get("data_valuta") or movimento.get("data", "")

        # Aggiorna rata
''',
'''        if not movimento:
            raise HTTPException(status_code=404, detail="Movimento bancario non trovato")
        if movimento.get("tipo") != "uscita":
            raise HTTPException(status_code=409, detail="La rata mutuo richiede un movimento bancario di uscita")
        if movimento.get("riconciliato") is True:
            stesso_collegamento = (
                movimento.get("tipo_documento") == "mutuo"
                and str(movimento.get("documento_id") or "") == str(mutuo_id)
                and int(movimento.get("rata_numero") or -1) == int(numero_rata)
            )
            if not stesso_collegamento:
                raise HTTPException(
                    status_code=409,
                    detail="Movimento bancario gia riconciliato con un altro documento",
                )

        data_movimento = movimento.get("data_valuta") or movimento.get("data", "")

        # Aggiorna rata
''')

Path('tests/test_point11_mutui_reconciliation.py').write_text(r'''import asyncio

from app.routers import mutui


def _run(coro):
    return asyncio.run(coro)


class _Cursor:
    def __init__(self, rows): self.rows = list(rows)
    async def to_list(self, _n): return list(self.rows)[:_n]


class _Movimenti:
    def __init__(self, strong, fallback):
        self.strong = list(strong)
        self.fallback = list(fallback)
        self.calls = 0
    def find(self, query):
        self.calls += 1
        return _Cursor(self.strong if '$or' in query else self.fallback)


class _DB:
    def __init__(self, strong, fallback):
        self.estratto_conto_movimenti = _Movimenti(strong, fallback)


def test_match_forte_univoco():
    db = _DB([{'id': 'm1'}], [{'id': 'm1'}])
    movimento, ambiguo, criterio = _run(mutui._candidato_bancario_univoco(db, {'$or': []}, {}))
    assert movimento['id'] == 'm1'
    assert ambiguo is False
    assert criterio == 'causale_importo_data'
    assert db.estratto_conto_movimenti.calls == 1


def test_due_match_forti_non_sceglie_il_primo_e_non_fa_fallback():
    db = _DB([{'id': 'm1'}, {'id': 'm2'}], [{'id': 'm3'}])
    movimento, ambiguo, criterio = _run(mutui._candidato_bancario_univoco(db, {'$or': []}, {}))
    assert movimento is None
    assert ambiguo is True
    assert criterio == 'piu_candidati_con_causale'
    assert db.estratto_conto_movimenti.calls == 1


def test_fallback_solo_se_univoco():
    db = _DB([], [{'id': 'm3'}])
    movimento, ambiguo, criterio = _run(mutui._candidato_bancario_univoco(db, {'$or': []}, {}))
    assert movimento['id'] == 'm3'
    assert ambiguo is False
    assert criterio == 'importo_data_univoco'

    db2 = _DB([], [{'id': 'm3'}, {'id': 'm4'}])
    movimento, ambiguo, criterio = _run(mutui._candidato_bancario_univoco(db2, {'$or': []}, {}))
    assert movimento is None
    assert ambiguo is True
    assert criterio == 'piu_candidati_importo_data'


def test_source_manual_rejects_reused_or_non_outgoing_movements():
    source = open('app/routers/mutui.py', encoding='utf-8').read()
    assert 'Movimento bancario gia riconciliato con un altro documento' in source
    assert 'La rata mutuo richiede un movimento bancario di uscita' in source
    assert '.find_one(query_movimenti)' not in source
''')
