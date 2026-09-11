from pathlib import Path

p = Path('tests/test_saldi_finanziari.py')
text = p.read_text()
old = '''    _run(db.prima_nota_banca.insert_many([\n        {"id": "bpm", "data": DATA, "tipo": "entrata", "importo": 1000.0,\n         "categoria": "Bonifico", "source": "estratto_conto",\n         "conto_contabile": "19.01.01"},\n        {"id": "msc", "data": DATA, "tipo": "entrata", "importo": 98.0,\n         "categoria": "Accrediti POS", "source": "accredito_payout",\n         "conto_contabile": "19.01.05", "natura": "liquidita"},\n    ]))\n'''
new = '''    _run(db.prima_nota_banca.insert_one(\n        {"id": "bpm", "data": DATA, "tipo": "entrata", "importo": 1000.0,\n         "categoria": "Bonifico", "source": "estratto_conto",\n         "conto_contabile": "19.01.01"}\n    ))\n    _run(db.prima_nota_sumup.insert_one(\n        {"id": "msc", "data": DATA, "tipo": "entrata", "importo": 98.0,\n         "categoria": "Accrediti POS", "source": "accredito_payout",\n         "conto_contabile": "19.01.05", "natura": "liquidita"}\n    ))\n'''
if old not in text:
    raise SystemExit('fixture Mastercard/BPM non trovata')
p.write_text(text.replace(old, new, 1))
