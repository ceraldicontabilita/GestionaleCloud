from pathlib import Path
import re

patcher = Path('.github/scripts/point11_assets_cdc_patch.py')
src = patcher.read_text()
start = src.find("replace_once(path,\n'''    ]).to_list(5000)")
end = src.find("replace_once(path,\n'''        imponibile = fatt.get", start)
if start < 0 or end < 0:
    raise SystemExit('original detailed CE patch block not found')
replacement = r'''p = Path(path)
text = p.read_text()
pattern_dettaglio = re.compile(
    r'(    fatture = await db\[Collections\.INVOICES\]\.find\(\{.*?\n    \}\)\.to_list\(5000\))\n\s*\n    # Classifica ogni fattura',
    re.S,
)
match_dettaglio = pattern_dettaglio.search(text)
if not match_dettaglio:
    raise SystemExit('detailed CE invoices block not found')
inserted = match_dettaglio.group(1) + """
    capitalizzati_per_fattura, totale_cespiti_capitalizzati_dettaglio = \\
        await _cespiti_capitalizzati_nel_periodo(db, data_inizio, data_fine)
    ammortamenti_registrati_dettaglio, ammortamenti_meta_dettaglio = \\
        await _ammortamenti_registrati_periodo(db, anno, mese)

    # Classifica ogni fattura"""
text = text[:match_dettaglio.start()] + inserted + text[match_dettaglio.end():]
p.write_text(text)

'''
src = src[:start] + replacement + src[end:]
exec(compile(src, str(patcher), 'exec'))
