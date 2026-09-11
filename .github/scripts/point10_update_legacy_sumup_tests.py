from pathlib import Path


def replace_once(path, old, new):
    p = Path(path)
    text = p.read_text()
    if old not in text:
        raise SystemExit(f'marker not found in {path}: {old[:120]}')
    p.write_text(text.replace(old, new, 1))

# Numia tests: SumUp must be read from the dedicated register.
replace_once(
    'tests/test_accrediti_numia_da_csv.py',
    '''    sumup = _run(db["prima_nota_banca"].find_one(\n        {"source": "trasferimento_pos", "gestore": "sumup"}))\n''',
    '''    sumup = _run(db["prima_nota_sumup"].find_one(\n        {"source": "trasferimento_pos", "gestore": "sumup"}))\n''',
)
replace_once(
    'tests/test_bonifica_accrediti_pos_numia.py',
    '''    sumup = _run(db["prima_nota_banca"].find_one({\n        "source": "trasferimento_pos", "gestore": "sumup",\n    }))\n''',
    '''    sumup = _run(db["prima_nota_sumup"].find_one({\n        "source": "trasferimento_pos", "gestore": "sumup",\n    }))\n''',
)

# Motore unico: Numia/BPM e SumUp hanno registri distinti.
replace_once(
    'tests/test_motore_unico_scritture.py',
    '''    assert len(db["prima_nota_banca"].docs) == 2\n''',
    '''    assert len(db["prima_nota_banca"].docs) == 1\n    assert len(db["prima_nota_sumup"].docs) == 1\n''',
)
replace_once(
    'tests/test_motore_unico_scritture.py',
    '''    crediti = {d["gestore"]: d for d in db["prima_nota_banca"].docs}\n    assert crediti["numia"]["conto_contabile"] == "15.07.01"\n    assert crediti["sumup"]["conto_contabile"] == "15.07.02"\n''',
    '''    crediti_bpm = {d["gestore"]: d for d in db["prima_nota_banca"].docs}\n    crediti_sumup = {d["gestore"]: d for d in db["prima_nota_sumup"].docs}\n    assert crediti_bpm["numia"]["conto_contabile"] == "15.07.01"\n    assert crediti_sumup["sumup"]["conto_contabile"] == "15.07.02"\n''',
)
replace_once(
    'tests/test_motore_unico_scritture.py',
    '''    for circuito, credito in crediti.items():\n''',
    '''    for circuito, credito in {**crediti_bpm, **crediti_sumup}.items():\n''',
)
replace_once(
    'tests/test_motore_unico_scritture.py',
    '''    assert (crediti["numia"]["trasferimento_id"]\n            != crediti["sumup"]["trasferimento_id"])\n''',
    '''    assert (crediti_bpm["numia"]["trasferimento_id"]\n            != crediti_sumup["sumup"]["trasferimento_id"])\n''',
)

# Multi-provider POS tests: SumUp lives in its own register.
replace_once(
    'tests/test_pos_multi_gestore.py',
    '''    banca = _righe_pos(db, "prima_nota_banca", source="trasferimento_pos")\n    assert {b["circuito"]: b["importo"] for b in banca} == {\n        "NUMIA": 500.0, "SUMUP": 100.0}\n''',
    '''    banca = _righe_pos(db, "prima_nota_banca", source="trasferimento_pos")\n    sumup = _righe_pos(db, "prima_nota_sumup", source="trasferimento_pos")\n    assert {b["circuito"]: b["importo"] for b in banca} == {"NUMIA": 500.0}\n    assert {s["circuito"]: s["importo"] for s in sumup} == {"SUMUP": 100.0}\n''',
)
replace_once(
    'tests/test_pos_multi_gestore.py',
    '''    banca = _righe_pos(db, "prima_nota_banca", source="trasferimento_pos")\n    assert banca[0]["in_transito"] is True\n    assert banca[0]["riconciliato"] is False\n    assert banca[0]["giorno_vendita"] == DATA\n''',
    '''    sumup = _righe_pos(db, "prima_nota_sumup", source="trasferimento_pos")\n    assert sumup[0]["in_transito"] is True\n    assert sumup[0]["riconciliato"] is False\n    assert sumup[0]["giorno_vendita"] == DATA\n''',
)

# SumUp sync tests: all financial expectation rows are in prima_nota_sumup.
replace_once(
    'tests/test_sumup_sync.py',
    '''    banca = _run(db.prima_nota_banca.find({}).to_list(50))\n    assert len(cassa) == 1 and cassa[0]["importo"] == 100.0\n    assert len(banca) == 1 and banca[0]["importo"] == 100.0\n    assert banca[0]["record_role"] == "expectation"\n    assert banca[0]["expectation_owner"] == "sumup_api"\n''',
    '''    sumup = _run(db.prima_nota_sumup.find({}).to_list(50))\n    assert len(cassa) == 1 and cassa[0]["importo"] == 100.0\n    assert len(sumup) == 1 and sumup[0]["importo"] == 100.0\n    assert sumup[0]["record_role"] == "expectation"\n    assert sumup[0]["expectation_owner"] == "sumup_api"\n''',
)
replace_once(
    'tests/test_sumup_sync.py',
    '''    assert banca[0]["expectation_status"] == "ATTESO"\n''',
    '''    assert sumup[0]["expectation_status"] == "ATTESO"\n''',
)
replace_once(
    'tests/test_sumup_sync.py',
    '''    banca = _run(db.prima_nota_banca.find_one({"gestore": "sumup"}))\n    assert cassa["importo"] == 116.90\n    assert cassa["quota_pos_fonte"] == "api_sumup"\n    assert banca["importo"] == 116.90\n    assert banca["record_role"] == "expectation"\n    assert banca["expectation_type"] == "pos_bank_credit"\n''',
    '''    sumup = _run(db.prima_nota_sumup.find_one({"gestore": "sumup"}))\n    assert cassa["importo"] == 116.90\n    assert cassa["quota_pos_fonte"] == "api_sumup"\n    assert sumup["importo"] == 116.90\n    assert sumup["record_role"] == "expectation"\n    assert sumup["expectation_type"] == "pos_bank_credit"\n''',
)
replace_once(
    'tests/test_sumup_sync.py',
    '''    assert banca["expectation_owner"] == "sumup_api"\n''',
    '''    assert sumup["expectation_owner"] == "sumup_api"\n''',
)
replace_once(
    'tests/test_sumup_sync.py',
    '''    assert _run(db.prima_nota_banca.find_one({\n        "source": "trasferimento_pos", "gestore": "sumup"\n    }))["importo"] == 100.0\n''',
    '''    assert _run(db.prima_nota_sumup.find_one({\n        "source": "trasferimento_pos", "gestore": "sumup"\n    }))["importo"] == 100.0\n''',
)
