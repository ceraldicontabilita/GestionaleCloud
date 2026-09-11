from pathlib import Path


def replace_once(path, old, new):
    p = Path(path)
    text = p.read_text()
    if old not in text:
        raise SystemExit(f'marker not found in {path}: {old[:140]}')
    p.write_text(text.replace(old, new, 1))


def patch_segment(path, start_marker, end_marker, transform):
    p = Path(path)
    text = p.read_text()
    start = text.index(start_marker)
    end = text.index(end_marker, start + len(start_marker))
    segment = text[start:end]
    updated = transform(segment)
    if updated == segment:
        raise SystemExit(f'no changes applied in segment {start_marker} of {path}')
    p.write_text(text[:start] + updated + text[end:])


# 1. Il motore unico conosce un registro finanziario SumUp autonomo.
replace_once(
    'app/services/scritture_contabili.py',
    'REGISTRI = {"cassa": "prima_nota_cassa", "banca": "prima_nota_banca"}',
    'REGISTRI = {"cassa": "prima_nota_cassa", "banca": "prima_nota_banca", "sumup": "prima_nota_sumup"}',
)


# 2. La chiusura POS SumUp apre il credito nel registro SumUp, mai in BPM.
def patch_chiusura(segment):
    marker = '    gestore = normalizza_gestore_pos(gestore)\n'
    if marker not in segment:
        raise SystemExit('normalizzazione gestore non trovata')
    segment = segment.replace(
        marker,
        marker +
        '    registro_finanziario = "sumup" if gestore == conti_pos.SUMUP else "banca"\n'
        '    collection_finanziaria = REGISTRI[registro_finanziario]\n',
        1,
    )
    segment = segment.replace(
        '    banca_mov = await db["prima_nota_banca"].find_one(banca_query)\n',
        '    banca_mov = await db[collection_finanziaria].find_one(banca_query)\n',
    )
    segment = segment.replace(
        '            await db["prima_nota_banca"].update_one(\n',
        '            await db[collection_finanziaria].update_one(\n',
    )
    segment = segment.replace(
        '            await db["prima_nota_banca"].update_one(\n',
        '            await db[collection_finanziaria].update_one(\n',
    )
    segment = segment.replace(
        '            banca_id = await scrivi_movimento(\n                db, "banca", nuovo_movimento_banca\n            )\n',
        '            banca_id = await scrivi_movimento(\n                db, registro_finanziario, nuovo_movimento_banca\n            )\n',
    )
    segment = segment.replace(
        '        "prima_nota_banca_id": banca_id,\n',
        '        "prima_nota_banca_id": banca_id if registro_finanziario == "banca" else None,\n'
        '        "prima_nota_sumup_id": banca_id if registro_finanziario == "sumup" else None,\n',
    )
    if 'db["prima_nota_banca"]' in segment:
        raise SystemExit('riferimento BPM residuo nella chiusura POS')
    return segment


patch_segment(
    'app/services/scritture_contabili.py',
    'async def registra_chiusura_pos_reale(',
    '\n\nasync def registra_corrispettivo(',
    patch_chiusura,
)


# 3. Anche il percorso registra_corrispettivo instrada il circuito SumUp
#    nel registro dedicato; Numia resta in Prima Nota Banca BPM.
def patch_corrispettivo(segment):
    marker = '    for circuito, importo in sorted(reale["per_circuito"].items()):\n        if importo <= 0:\n            continue\n'
    if marker not in segment:
        raise SystemExit('loop circuiti non trovato')
    segment = segment.replace(
        marker,
        marker +
        '        registro_finanziario = "sumup" if circuito == conti_pos.SUMUP else "banca"\n'
        '        collection_finanziaria = REGISTRI[registro_finanziario]\n',
        1,
    )
    segment = segment.replace(
        '        banca_esistente = await db["prima_nota_banca"].find_one(banca_query)\n',
        '        banca_esistente = await db[collection_finanziaria].find_one(banca_query)\n',
    )
    segment = segment.replace(
        '        banca_pos_id, _ = await _scrivi_se_assente(db, "banca", banca_query, {\n',
        '        banca_pos_id, _ = await _scrivi_se_assente(db, registro_finanziario, banca_query, {\n',
    )
    segment = segment.replace(
        '        scritti[circuito] = {"cassa": cassa_pos_id, "banca": banca_pos_id}\n'
        '        esito["prima_nota_cassa_uscita_pos_id"] = cassa_pos_id\n'
        '        esito["prima_nota_banca_id"] = banca_pos_id\n',
        '        scritti[circuito] = {\n'
        '            "cassa": cassa_pos_id,\n'
        '            "sumup" if registro_finanziario == "sumup" else "banca": banca_pos_id,\n'
        '        }\n'
        '        esito["prima_nota_cassa_uscita_pos_id"] = cassa_pos_id\n'
        '        if registro_finanziario == "sumup":\n'
        '            esito["prima_nota_sumup_id"] = banca_pos_id\n'
        '        else:\n'
        '            esito["prima_nota_banca_id"] = banca_pos_id\n',
    )
    return segment


patch_segment(
    'app/services/scritture_contabili.py',
    'async def registra_corrispettivo(',
    '\n\nasync def _marca_stato_pos(',
    patch_corrispettivo,
)


# 4. Piano dei conti: il registro SumUp ha tesoreria Mastercard dedicata.
replace_once(
    'app/services/mapping_piano_conti.py',
    '_TESORERIA_PER_REGISTRO = {"banca": CONTO_BANCA, "cassa": CONTO_CASSA}',
    '_TESORERIA_PER_REGISTRO = {"banca": CONTO_BANCA, "cassa": CONTO_CASSA, "sumup": conti_pos.CONTO_SUMUP_MASTERCARD}',
)


# 5. Payout, commissioni, chiusure credito e rettifiche SumUp vivono solo
#    nella Prima Nota SumUp.
p = Path('app/services/sumup_payout.py')
text = p.read_text()
text = text.replace('db["prima_nota_banca"]', 'db["prima_nota_sumup"]')
text = text.replace('_scrivi_se_assente(db, "banca",', '_scrivi_se_assente(db, "sumup",')
text = text.replace('_scrivi_se_assente(\n            db, "banca",', '_scrivi_se_assente(\n            db, "sumup",')
text = text.replace('_scrivi_se_assente(\n        db, "banca",', '_scrivi_se_assente(\n        db, "sumup",')
p.write_text(text)


# 6. Costanti comuni e saldi: BPM e Mastercard sono due registri distinti.
replace_once(
    'app/routers/prima_nota_module/common.py',
    'COLLECTION_PRIMA_NOTA_BANCA = "prima_nota_banca"\nCOLLECTION_PRIMA_NOTA_SALARI = "prima_nota_salari"',
    'COLLECTION_PRIMA_NOTA_BANCA = "prima_nota_banca"\nCOLLECTION_PRIMA_NOTA_SUMUP = "prima_nota_sumup"\nCOLLECTION_PRIMA_NOTA_SALARI = "prima_nota_salari"',
)
replace_once(
    'app/routers/prima_nota_module/common.py',
    'if collection == COLLECTION_PRIMA_NOTA_BANCA:',
    'if collection in {COLLECTION_PRIMA_NOTA_BANCA, COLLECTION_PRIMA_NOTA_SUMUP}:',
)
replace_once(
    'app/routers/prima_nota_module/common.py',
    '_COLLECTION_A_TIPO = {"prima_nota_cassa": "cassa", "prima_nota_banca": "banca"}',
    '_COLLECTION_A_TIPO = {"prima_nota_cassa": "cassa", "prima_nota_banca": "banca", "prima_nota_sumup": "sumup"}',
)


def patch_saldi(segment):
    segment = segment.replace(
        '    async def _saldo(query: Dict[str, Any]) -> float:\n',
        '    async def _saldo(query: Dict[str, Any], collection: str = COLLECTION_PRIMA_NOTA_BANCA) -> float:\n',
        1,
    )
    segment = segment.replace('cursore = db["prima_nota_banca"].find(', 'cursore = db[collection].find(', 1)
    segment = segment.replace(
        '"saldo": await _saldo({**ESCLUSIONI_SALDO_REALE, **appartenenza}),',
        '"saldo": await _saldo(\n'
        '                {**ESCLUSIONI_SALDO_REALE, **appartenenza},\n'
        '                COLLECTION_PRIMA_NOTA_SUMUP if codice == conti_pos.CONTO_SUMUP_MASTERCARD else COLLECTION_PRIMA_NOTA_BANCA,\n'
        '            ),',
        1,
    )
    segment = segment.replace(
        '"saldo": await _saldo(aperti),',
        '"saldo": await _saldo(\n'
        '                aperti,\n'
        '                COLLECTION_PRIMA_NOTA_SUMUP if circuito == conti_pos.SUMUP else COLLECTION_PRIMA_NOTA_BANCA,\n'
        '            ),',
        1,
    )
    return segment


patch_segment(
    'app/routers/prima_nota_module/common.py',
    'async def saldi_finanziari(',
    '\n\nasync def calcola_saldo_anni_precedenti',
    patch_saldi,
)


# 7. Endpoint /prima-nota/sumup: legge esclusivamente il registro dedicato.
def patch_sumup_view(segment):
    segment = segment.replace('db[COLLECTION_PRIMA_NOTA_BANCA]', 'db["prima_nota_sumup"]')
    segment = segment.replace('db["prima_nota_banca"]', 'db["prima_nota_sumup"]')
    return segment


patch_segment(
    'app/routers/prima_nota_module/banca.py',
    'async def list_prima_nota_sumup(',
    '\n\nasync def ',
    patch_sumup_view,
)


# 8. Regressioni nuove.
Path('tests/test_point10_sumup_separate_register.py').write_text(r'''import asyncio

from app.routers.prima_nota_module import banca
from app.services import sumup_payout
from app.services.sheets_document_store import MemorySheetsClient
from app.services.scritture_contabili import registra_chiusura_pos_reale


def _run(coro):
    return asyncio.run(coro)


def _sumup_tx():
    return {
        'chiave': 'M:t1', 'transaction_id': 't1', 'tipo': 'PAYMENT',
        'stato': 'SUCCESSFUL', 'data': '2026-08-06', 'importo': 100.0,
        'payout_id': 'P1', 'valuta': 'EUR',
    }


def test_chiusura_sumup_scrive_nel_registro_sumup_non_in_banca():
    db = MemorySheetsClient()['point10_sumup_separate_closure']
    result = _run(registra_chiusura_pos_reale(db, '2026-08-06', 100.0, gestore='sumup'))
    assert _run(db.prima_nota_banca.find({}).to_list(20)) == []
    rows = _run(db.prima_nota_sumup.find({}).to_list(20))
    assert len(rows) == 1
    assert rows[0]['source'] == 'trasferimento_pos'
    assert rows[0]['gestore'] == 'sumup'
    assert result['prima_nota_banca_id'] is None
    assert result['prima_nota_sumup_id'] == rows[0]['id']


def test_payout_sumup_scrive_solo_prima_nota_sumup():
    db = MemorySheetsClient()['point10_sumup_separate_payout']
    _run(db.sumup_transactions.insert_one(_sumup_tx()))
    _run(registra_chiusura_pos_reale(db, '2026-08-06', 100.0, gestore='sumup'))
    result = _run(sumup_payout.registra_payout(db, {
        'id': 'P1', 'amount': 98.0, 'date': '2026-08-07T05:00:00Z',
        'currency': 'EUR', 'status': 'SUCCESSFUL',
    }))
    assert result['stato_riconciliazione'] == 'riconciliato'
    assert _run(db.prima_nota_banca.find({}).to_list(50)) == []
    rows = _run(db.prima_nota_sumup.find({}).to_list(50))
    sources = {r['source'] for r in rows}
    assert {'trasferimento_pos', 'chiusura_credito_pos', 'accredito_payout', 'commissioni_sumup'} <= sources
    accredito = next(r for r in rows if r['source'] == 'accredito_payout')
    assert accredito['conto_contabile'] == '19.01.05'
    assert accredito['accredito_banca_verificato'] is False


def test_numia_resta_nella_prima_nota_banca_bpm():
    db = MemorySheetsClient()['point10_numia_stays_bpm']
    result = _run(registra_chiusura_pos_reale(db, '2026-08-06', 100.0, gestore='numia'))
    banca_rows = _run(db.prima_nota_banca.find({}).to_list(20))
    assert len(banca_rows) == 1
    assert banca_rows[0]['gestore'] == 'numia'
    assert result['prima_nota_banca_id'] == banca_rows[0]['id']
    assert result['prima_nota_sumup_id'] is None
    assert _run(db.prima_nota_sumup.find({}).to_list(20)) == []


def test_endpoint_sumup_legge_il_registro_dedicato(monkeypatch):
    db = MemorySheetsClient()['point10_sumup_endpoint']
    _run(db.prima_nota_sumup.insert_one({
        'id': 'S1', 'data': '2026-08-07', 'tipo': 'entrata', 'importo': 98.0,
        'source': 'accredito_payout', 'conto_contabile': '19.01.05',
        'gestore': 'sumup', 'status': 'active',
    }))
    _run(db.prima_nota_banca.insert_one({
        'id': 'B1', 'data': '2026-08-07', 'tipo': 'entrata', 'importo': 999.0,
        'source': 'accredito_payout', 'conto_contabile': '19.01.05',
        'gestore': 'sumup', 'status': 'active',
    }))
    monkeypatch.setattr(banca.Database, 'get_db', staticmethod(lambda: db))
    result = _run(banca.list_prima_nota_sumup(anno=2026))
    assert result['totale_ricevuto'] == 98.0
    assert result['numero_payout'] == 1
''')


# 9. I test storici SumUp devono interrogare il nuovo registro, mentre il
#    controllo Numia/Nexi continua a usare prima_nota_banca.
def tests_sumup(segment):
    return segment.replace('db.prima_nota_banca', 'db.prima_nota_sumup')

patch_segment(
    'tests/test_sumup_payout.py',
    'def test_l_accredito_e_una_scrittura_composta_che_quadra():',
    '\ndef test_il_payout_non_tocca_i_crediti_nexi():',
    tests_sumup,
)

replace_once(
    'tests/test_point10_pos_paypal_evidence_contract.py',
    "accredito = _run(db.prima_nota_banca.find_one({'source': 'accredito_payout'}))",
    "accredito = _run(db.prima_nota_sumup.find_one({'source': 'accredito_payout'}))",
)


def patch_scheda_test(segment):
    return segment.replace('db["prima_nota_banca"]', 'db["prima_nota_sumup"]')

patch_segment(
    'tests/test_banca_saldo_reale.py',
    'def test_scheda_sumup_espone_solo_payout_ricevuti_aggregati_per_giorno(',
    '\n\ndef ',
    patch_scheda_test,
)
