from pathlib import Path
import re


def replace_once(path, old, new):
    p = Path(path)
    text = p.read_text()
    if old not in text:
        raise SystemExit(f'marker not found in {path}: {old[:180]}')
    p.write_text(text.replace(old, new, 1))

path = 'app/services/calcolo_imposte.py'
p = Path(path)
text = p.read_text()
text = text.replace(
    '# Aliquote IRAP per regione (2024-2025)',
    '# Aliquote IRAP di riferimento. Campania 4,97% verificata su fonte regionale per il 2026;\n# le altre regioni richiedono verifica annuale prima di uso dichiarativo.'
)
text = text.replace(
    '        OTTIMIZZATO: Usa aggregazione Drive/Sheets per performance.\n',
    '        Usa il Conto Economico canonico come base civilistica. Le classificazioni\n        fiscali restano previsioni gestionali e non sostituiscono la dichiarazione.\n'
)
pattern = re.compile(
    r'        # 1\. Calcola totali costi usando aggregazione \(molto più veloce\).*?        # 2\. Calcola variazioni fiscali\n',
    re.S,
)
match = pattern.search(text)
if not match:
    raise SystemExit('tax source aggregation block not found')
new_block = '''        # 1. Base civilistica: unica fonte = Conto Economico canonico.\n        # Include note di credito, soft-delete, cespiti capitalizzati e quote di\n        # ammortamento registrate secondo le regole del Bilancio.\n        from app.routers.accounting.bilancio import (\n            get_conto_economico,\n            _cespiti_capitalizzati_nel_periodo,\n        )\n        ce = await get_conto_economico(anno=anno, mese=None)\n        totale_ricavi = float(ce["ricavi"]["totale_ricavi"] or 0)\n        totale_costi = float(ce["costi"]["totale_costi"] or 0)\n        utile_civilistico = float(ce["risultato"]["utile_perdita"] or 0)\n\n        # Dettaglio per tipo usato soltanto per le variazioni fiscali automatiche.\n        # Si lavora sull'imponibile, non sul totale lordo IVA, e si escludono\n        # cespiti capitalizzati gia' rimossi dal CE canonico.\n        data_inizio = f"{anno}-01-01"\n        data_fine = f"{anno}-12-31"\n        capitalizzati_per_fattura, _ = await _cespiti_capitalizzati_nel_periodo(\n            db, data_inizio, data_fine\n        )\n        fatture = await db["invoices"].find({\n            "status": {"$nin": ["deleted", "archived"]},\n            "$or": [\n                {"invoice_date": {"$regex": f"^{anno}"}},\n                {"data_ricezione": {"$regex": f"^{anno}"}},\n            ],\n        }, {"_id": 0}).to_list(10000)\n        costi_per_tipo: Dict[str, Dict[str, float]] = {}\n        for fattura in fatture:\n            codice = fattura.get("conto_costo_codice") or "05.01.01"\n            nome = fattura.get("conto_costo_nome") or ""\n            try:\n                imponibile = float(fattura.get("imponibile") or 0)\n                if not imponibile:\n                    imponibile = float(fattura.get("total_amount") or 0) - float(fattura.get("iva") or 0)\n            except (TypeError, ValueError):\n                continue\n            fid = str(fattura.get("id") or fattura.get("invoice_key") or "")\n            imponibile -= float(capitalizzati_per_fattura.get(fid, 0) or 0)\n            if fattura.get("tipo_documento") in ("TD04", "TD08"):\n                imponibile = -imponibile\n            voce = costi_per_tipo.setdefault(codice, {"nome": nome, "importo": 0.0})\n            voce["importo"] += imponibile\n\n        # 2. Calcola variazioni fiscali\n'''
text = text[:match.start()] + new_block + text[match.end():]

old_ded = '''        # Deduzioni IRAP\n        deduzioni_irap = DEDUZIONE_IRAP_BASE\n\n        # Conta dipendenti (semplificato: se ci sono costi personale)\n        if costo_personale > 0:\n            # Stima n. dipendenti da costo medio\n            n_dipendenti_stimato = int(costo_personale / 25000)  # €25k costo medio\n            deduzioni_irap += n_dipendenti_stimato * DEDUZIONE_IRAP_DIPENDENTI\n'''
new_ded = '''        # Deduzioni IRAP: nessuna deduzione viene inventata da una stima del\n        # numero di dipendenti. Il numero reale e' letto solo come informazione;\n        # l'applicabilita' fiscale delle deduzioni richiede requisiti documentati.\n        n_dipendenti_reali = await db["dipendenti"].count_documents({\n            "attivo": {"$ne": False},\n            "merged_into": {"$exists": False},\n        })\n        deduzioni_irap = 0.0\n        logger.info(\n            "IRAP %s: %s dipendenti reali rilevati; deduzioni specifiche non applicate automaticamente",\n            anno, n_dipendenti_reali,\n        )\n'''
if old_ded not in text:
    raise SystemExit('IRAP estimated employees block not found')
text = text.replace(old_ded, new_ded, 1)

# Remove automatic 10% IRAP-to-IRES deduction from DB calculation. It requires
# tax-period conditions and must not silently alter a management estimate.
pattern_ded_irap = re.compile(
    r'        # 5\. Aggiorna variazioni diminuzione IRES con deduzione IRAP\n        if irap_dovuta > 0:.*?            ires_dovuta = reddito_imponibile_ires \* ALIQUOTA_IRES / 100\n\n',
    re.S,
)
if not pattern_ded_irap.search(text):
    raise SystemExit('automatic IRAP deduction block not found')
text = pattern_ded_irap.sub(
    '        # 5. Nessuna deduzione IRAP->IRES automatica: richiede verifica fiscale\n        # del periodo e dei requisiti. Il risultato resta una stima prudenziale.\n\n',
    text,
    count=1,
)
p.write_text(text)

# Router: make quality/source explicit and expose actual employee count separately.
path = 'app/routers/accounting/contabilita_avanzata.py'
replace_once(path,
'''        anno_label = anno if anno else "tutti gli anni"\n\n        # Converti in dict per JSON\n        return {\n''',
'''        anno_label = anno if anno else "anno corrente"\n        dipendenti_reali = await db["dipendenti"].count_documents({\n            "attivo": {"$ne": False},\n            "merged_into": {"$exists": False},\n        })\n\n        # Converti in dict per JSON\n        return {\n''')
replace_once(path,
'''            "totale_imposte": risultato.totale_imposte,\n            "aliquota_effettiva": risultato.aliquota_effettiva,\n            "note": [\n                f"Calcolo basato su fatture e corrispettivi dell'anno {anno_label}",\n                "Variazioni fiscali automatiche per telefonia (20% indeducibile) e carburante auto (80% indeducibile)",\n                f"Aliquota IRAP regione {regione}: {calcolatore.aliquota_irap}%"\n            ]\n''',
'''            "totale_imposte": risultato.totale_imposte,\n            "aliquota_effettiva": risultato.aliquota_effettiva,\n            "qualita_calcolo": {\n                "tipo": "previsionale_gestionale",\n                "base_civilistica": "conto_economico_canonico",\n                "dipendenti_reali_rilevati": dipendenti_reali,\n                "deduzioni_irap_specifiche_applicate_automaticamente": False,\n                "aliquota_irap_verificata_2026": regione.lower().replace(" ", "_") == "campania",\n                "fonte_irap_campania_2026": "Regione Campania - Portale Entrate IRAP, aliquota ordinaria 4,97% al 01/04/2026",\n                "uso_dichiarativo": False,\n            },\n            "note": [\n                f"Base civilistica dal Conto Economico canonico dell'anno {anno_label}",\n                "Deduzioni e agevolazioni con requisiti specifici non sono applicate automaticamente",\n                f"Aliquota IRAP regione {regione}: {calcolatore.aliquota_irap}%",\n                "Calcolo previsionale: validare con il consulente prima di uso dichiarativo"\n            ]\n''')

Path('tests/test_point11_tax_governance.py').write_text(r'''from pathlib import Path\n\n\ndef test_tax_engine_uses_canonical_pnl_and_not_gross_divided_by_110():\n    source = Path('app/services/calcolo_imposte.py').read_text()\n    assert 'get_conto_economico' in source\n    assert 'ce["risultato"]["utile_perdita"]' in source\n    assert 'totale_lordo / 1.10' not in source\n    assert 'costo_personale / 25000' not in source\n    assert 'deduzioni_irap = 0.0' in source\n\n\ndef test_tax_router_marks_result_as_management_estimate():\n    source = Path('app/routers/accounting/contabilita_avanzata.py').read_text()\n    assert '"tipo": "previsionale_gestionale"' in source\n    assert '"base_civilistica": "conto_economico_canonico"' in source\n    assert '"uso_dichiarativo": False' in source\n    assert '"aliquota_irap_verificata_2026"' in source\n''')
