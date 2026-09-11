from pathlib import Path
import re


def replace_once(path, old, new):
    p = Path(path)
    text = p.read_text()
    if old not in text:
        raise SystemExit(f'marker not found in {path}: {old[:180]}')
    p.write_text(text.replace(old, new, 1))


# ---------------------------------------------------------------------------
# Bilancio: capitalizzazione cespiti + ammortamenti registrati
# ---------------------------------------------------------------------------
path = 'app/routers/accounting/bilancio.py'
p = Path(path)
text = p.read_text()
marker = 'PIVA_AZIENDA = "04523831214"\n\n\n'
helper = r'''PIVA_AZIENDA = "04523831214"


async def _cespiti_capitalizzati_nel_periodo(db, data_inizio: str, data_fine: str):
    """Restituisce il costo storico dei cespiti estratti da righe XML.

    Questi importi sono immobilizzazioni, non costi d'esercizio immediati. La
    fattura resta documento origine, ma il suo imponibile operativo viene
    ridotto della sola quota effettivamente capitalizzata nel registro cespiti.
    """
    righe = await db["cespiti"].find(
        {
            "provenienza": "fattura_xml",
            "data_acquisto": {"$gte": data_inizio, "$lte": data_fine},
            "fattura_id": {"$exists": True},
        },
        {"_id": 0, "fattura_id": 1, "valore_acquisto": 1},
    ).to_list(10000)
    per_fattura = {}
    totale = 0.0
    for riga in righe:
        fattura_id = str(riga.get("fattura_id") or "")
        if not fattura_id:
            continue
        try:
            valore = float(riga.get("valore_acquisto") or 0)
        except (TypeError, ValueError):
            continue
        if valore <= 0:
            continue
        per_fattura[fattura_id] = per_fattura.get(fattura_id, 0.0) + valore
        totale += valore
    return per_fattura, round(totale, 2)


async def _ammortamenti_registrati_periodo(db, anno: int, mese: int = None):
    """Quote realmente registrate nel piano cespiti.

    Il piano viene aggiornato solo da POST /cespiti/registra/{anno}, dopo
    conferma esplicita. Per il CE mensile una quota annuale gia registrata viene
    ripartita in dodicesimi a fini gestionali; nessuna preview non registrata
    entra automaticamente nel risultato contabile.
    """
    cespiti = await db["cespiti"].find(
        {"piano_ammortamento": {"$elemMatch": {"anno": anno}}},
        {"_id": 0, "id": 1, "piano_ammortamento": 1},
    ).to_list(10000)
    quota_annua = 0.0
    for cespite in cespiti:
        for quota in cespite.get("piano_ammortamento") or []:
            if quota.get("anno") != anno:
                continue
            try:
                quota_annua += float(quota.get("quota") or quota.get("quota_anno") or 0)
            except (TypeError, ValueError):
                continue
    quota_periodo = quota_annua / 12 if mese else quota_annua
    return round(quota_periodo, 2), {
        "quota_annua_registrata": round(quota_annua, 2),
        "modalita": "dodicesimo_quota_registrata" if mese else "quota_annua_registrata",
        "solo_quote_registrate": True,
    }


'''
if '_cespiti_capitalizzati_nel_periodo' not in text:
    if marker not in text:
        raise SystemExit('bilancio helper insertion marker not found')
    text = text.replace(marker, helper, 1)
p.write_text(text)

replace_once(path,
'''    totale_note_credito = note_credito[0]["totale_imponibile"] if note_credito else 0
    iva_note_credito = note_credito[0]["totale_iva"] if note_credito else 0
    num_note_credito = note_credito[0]["count"] if note_credito else 0
    
    # === CALCOLI FINALI ===
''',
'''    totale_note_credito = note_credito[0]["totale_imponibile"] if note_credito else 0
    iva_note_credito = note_credito[0]["totale_iva"] if note_credito else 0
    num_note_credito = note_credito[0]["count"] if note_credito else 0

    # Cespiti estratti dalle righe XML: il costo storico non puo essere spesato
    # integralmente nello stesso CE in cui il bene compare tra le immobilizzazioni.
    _, totale_cespiti_capitalizzati = await _cespiti_capitalizzati_nel_periodo(
        db, data_inizio, data_fine
    )
    ammortamenti_registrati, ammortamenti_meta = await _ammortamenti_registrati_periodo(
        db, anno, mese
    )
    
    # === CALCOLI FINALI ===
''')

replace_once(path,
'''    # Costi = Acquisti - Note Credito
    costi_netti = totale_acquisti - totale_note_credito
    totale_costi = costi_netti
''',
'''    # Costi = acquisti operativi - note di credito + ammortamenti registrati.
    # Il valore dei cespiti capitalizzati resta nell'attivo e viene spesato nel
    # tempo tramite le quote di ammortamento, mai due volte.
    acquisti_operativi = totale_acquisti - totale_cespiti_capitalizzati
    costi_netti = acquisti_operativi - totale_note_credito
    totale_costi = costi_netti + ammortamenti_registrati
''')

replace_once(path,
'''        "costi": {
            "acquisti": round(totale_acquisti, 2),
            "note_credito": round(totale_note_credito, 2),
            "costi_netti": round(costi_netti, 2),
            "totale_costi": round(totale_costi, 2)
        },
''',
'''        "costi": {
            "acquisti_lordi_da_fatture": round(totale_acquisti, 2),
            "cespiti_capitalizzati_esclusi": round(totale_cespiti_capitalizzati, 2),
            "acquisti_operativi": round(acquisti_operativi, 2),
            "note_credito": round(totale_note_credito, 2),
            "ammortamenti_registrati": round(ammortamenti_registrati, 2),
            "ammortamenti_meta": ammortamenti_meta,
            "costi_netti_prima_ammortamenti": round(costi_netti, 2),
            "totale_costi": round(totale_costi, 2)
        },
''')

replace_once(path,
'''        "note": "Ricavi = Corrispettivi (vendite al pubblico). Costi = Fatture ricevute - Note credito."
''',
'''        "note": (
            "Ricavi = Corrispettivi. Costi = acquisti operativi - note credito + "
            "ammortamenti registrati; i cespiti capitalizzati da righe XML non "
            "sono spesati integralmente all'acquisto."
        )
''')

# Conto economico dettagliato: sottrae la quota capitalizzata dalla categoria
# della fattura e aggiunge B10 ammortamenti registrati.
replace_once(path,
'''    ]).to_list(5000)
    
    # Classifica ogni fattura
''',
'''    ]).to_list(5000)
    capitalizzati_per_fattura, totale_cespiti_capitalizzati_dettaglio = \\
        await _cespiti_capitalizzati_nel_periodo(db, data_inizio, data_fine)
    ammortamenti_registrati_dettaglio, ammortamenti_meta_dettaglio = \\
        await _ammortamenti_registrati_periodo(db, anno, mese)
    
    # Classifica ogni fattura
''')

replace_once(path,
'''        imponibile = fatt.get("imponibile") or (fatt.get("total_amount", 0) - fatt.get("iva", 0))
        iva = fatt.get("iva", 0)
        
        if categoria not in costi_per_categoria:
''',
'''        imponibile = fatt.get("imponibile") or (fatt.get("total_amount", 0) - fatt.get("iva", 0))
        iva = fatt.get("iva", 0)
        fattura_id = str(fatt.get("id") or fatt.get("invoice_key") or "")
        quota_capitalizzata = float(capitalizzati_per_fattura.get(fattura_id, 0) or 0)
        imponibile_operativo = float(imponibile or 0) - quota_capitalizzata
        
        if categoria not in costi_per_categoria:
''')
replace_once(path,
'''        costi_per_categoria[categoria]["imponibile"] += imponibile
''',
'''        costi_per_categoria[categoria]["imponibile"] += imponibile_operativo
''')
replace_once(path,
'''        B14_altri["imponibile"] -
        totale_nc
    )
''',
'''        B14_altri["imponibile"] -
        totale_nc +
        ammortamenti_registrati_dettaglio
    )
''')
replace_once(path,
'''            "B14_oneri_diversi": {
                "imponibile": round(B14_altri["imponibile"], 2),
                "num_fatture": B14_altri["count"]
            },
''',
'''            "B10_ammortamenti": {
                "quota_registrata_periodo": round(ammortamenti_registrati_dettaglio, 2),
                "meta": ammortamenti_meta_dettaglio,
                "cespiti_capitalizzati_esclusi_dagli_acquisti": round(
                    totale_cespiti_capitalizzati_dettaglio, 2
                ),
            },
            "B14_oneri_diversi": {
                "imponibile": round(B14_altri["imponibile"], 2),
                "num_fatture": B14_altri["count"]
            },
''')

# ---------------------------------------------------------------------------
# Centri costo: i report consumano le classificazioni riga-per-riga XML
# ---------------------------------------------------------------------------
path = 'app/routers/accounting/centri_costo.py'
p = Path(path)
text = p.read_text()
insert_marker = '@router.get("/utile-obiettivo/per-cdc")\n'
helpers = r'''def _cdc_operativo_da_learning(codice: str, nome: str = "") -> Optional[str]:
    """Traduce solo categorie learning con significato operativo esplicito.

    Nessun fallback inventato: categorie non mappabili restano DA_VERIFICARE.
    """
    codice = str(codice or "")
    nome_norm = str(nome or "").casefold()
    if codice in CDC_STANDARD:
        return codice
    prefissi = (
        (("1.1_", "1.2_", "1.6_"), "CDC-01"),
        (("1.3_", "1.4_"), "CDC-02"),
        (("1.5_",), "CDC-03"),
        (("1.8_", "13.1_"), "CDC-04"),
        (("4.", "4_"), "CDC-90"),
    )
    for gruppi, cdc in prefissi:
        if codice.startswith(gruppi):
            return cdc
    if any(k in nome_norm for k in ("marketing", "pubblicit", "promozion", "social")):
        return "CDC-92"
    if any(k in nome_norm for k in ("commercialista", "consulenza", "software", "amministr", "cancelleria")):
        return "CDC-91"
    if any(k in nome_norm for k in (
        "energia", "gas", "acqua", "rifiuti", "affitto", "locazione", "condominio",
        "manutenzione", "pulizia", "assicur", "noleggio", "carburante", "telefon",
    )):
        return "CDC-99"
    return None


def _firma_riga(descrizione: str, importo: float):
    return (" ".join(str(descrizione or "").casefold().split()), round(float(importo or 0), 2))


async def _costi_cdc_da_righe_xml(db, anno: int) -> Dict[str, Any]:
    """Costi analitici da classificazioni riga XML, al netto dei cespiti.

    Le righe dubbie o con vocabolario non traducibile non vengono forzate in
    CDC-99: restano esplicitamente DA_VERIFICARE.
    """
    data_start = f"{anno}-01-01"
    data_end = f"{anno}-12-31"
    fatture = await db[Collections.INVOICES].find({
        "status": {"$nin": ["deleted", "archived"]},
        "$or": [
            {"invoice_date": {"$gte": data_start, "$lte": data_end}},
            {"data_ricezione": {"$gte": data_start, "$lte": data_end}},
        ],
    }, {"_id": 0}).to_list(10000)
    cespiti = await db["cespiti"].find({
        "provenienza": "fattura_xml",
        "data_acquisto": {"$gte": data_start, "$lte": data_end},
    }, {"_id": 0, "fattura_id": 1, "descrizione": 1, "valore_acquisto": 1}).to_list(10000)

    asset_signatures = {}
    asset_totals = {}
    for cespite in cespiti:
        fid = str(cespite.get("fattura_id") or "")
        if not fid:
            continue
        valore = float(cespite.get("valore_acquisto") or 0)
        sig = (fid, *_firma_riga(cespite.get("descrizione"), valore))
        asset_signatures[sig] = asset_signatures.get(sig, 0) + 1
        asset_totals[fid] = asset_totals.get(fid, 0.0) + valore

    costi = {cdc: 0.0 for cdc in CDC_STANDARD}
    fatture_per_cdc = {cdc: set() for cdc in CDC_STANDARD}
    da_verificare = 0.0
    righe_da_verificare = 0
    righe_usate = 0
    cespiti_esclusi = 0.0

    for fattura in fatture:
        fid = str(fattura.get("id") or fattura.get("invoice_key") or "")
        segno = -1.0 if fattura.get("tipo_documento") in ("TD04", "TD08") else 1.0
        righe = fattura.get("classificazioni_righe") or []
        if righe:
            for riga in righe:
                importo = float(riga.get("imponibile") or 0)
                sig = (fid, *_firma_riga(riga.get("descrizione"), importo))
                if asset_signatures.get(sig, 0) > 0:
                    asset_signatures[sig] -= 1
                    cespiti_esclusi += importo
                    continue
                cdc = None if riga.get("richiede_verifica") else _cdc_operativo_da_learning(
                    riga.get("centro_costo_id"), riga.get("centro_costo_nome")
                )
                if not cdc:
                    da_verificare += segno * importo
                    righe_da_verificare += 1
                    continue
                costi[cdc] += segno * importo
                fatture_per_cdc[cdc].add(fid)
                righe_usate += 1
            continue

        # Fallback solo per fatture legacy con CDC di testata esplicito e non
        # marcato da verificare. La quota cespite viene comunque esclusa.
        imponibile = float(fattura.get("imponibile") or 0)
        if not imponibile:
            imponibile = float(fattura.get("total_amount") or 0) - float(fattura.get("iva") or 0)
        imponibile -= float(asset_totals.get(fid, 0) or 0)
        cdc = fattura.get("centro_costo")
        if cdc in CDC_STANDARD and not fattura.get("cdc_requires_review"):
            costi[cdc] += segno * imponibile
            fatture_per_cdc[cdc].add(fid)
        else:
            da_verificare += segno * imponibile
            righe_da_verificare += 1

    return {
        "costi": {k: round(v, 2) for k, v in costi.items()},
        "fatture_count": {k: len(v) for k, v in fatture_per_cdc.items()},
        "da_verificare": round(da_verificare, 2),
        "righe_da_verificare": righe_da_verificare,
        "righe_usate": righe_usate,
        "cespiti_esclusi": round(cespiti_esclusi, 2),
        "fonte": "classificazioni_righe_xml",
    }


'''
if '_costi_cdc_da_righe_xml' not in text:
    if insert_marker not in text:
        raise SystemExit('centri costo helper insertion marker not found')
    text = text.replace(insert_marker, helpers + insert_marker, 1)
p.write_text(text)

p = Path(path)
text = p.read_text()
pattern = re.compile(r'@router\.get\("/utile-obiettivo/per-cdc"\)\nasync def get_utile_per_cdc\(.*?\n\n\n# ============== RIBALTAMENTO CDC ==============', re.S)
match = pattern.search(text)
if not match:
    raise SystemExit('get_utile_per_cdc function block not found')
new_func = r'''@router.get("/utile-obiettivo/per-cdc")
async def get_utile_per_cdc(anno: int = Query(...)) -> Dict[str, Any]:
    """Analisi utile/margine per CDC basata sulle singole righe XML."""
    db = Database.get_db()
    analitica = await _costi_cdc_da_righe_xml(db, anno)
    from app.routers.accounting.bilancio import get_conto_economico
    ce = await get_conto_economico(anno=anno, mese=None)
    ricavi_totali = float(ce["ricavi"]["totale_ricavi"] or 0)

    costi_dict = analitica["costi"]
    costi_totali_validati = sum(costi_dict.values())
    report = []
    for codice, costo in sorted(costi_dict.items(), key=lambda item: -abs(item[1])):
        if abs(costo) < 0.005:
            continue
        info = CDC_STANDARD.get(codice, {"nome": codice, "tipo": "altro"})
        peso_costi = costo / costi_totali_validati if costi_totali_validati > 0 else 0
        ricavi_cdc = ricavi_totali * peso_costi * 1.5 if info.get("tipo") == "operativo" else 0
        margine = ricavi_cdc - costo
        report.append({
            "codice": codice,
            "nome": info.get("nome", codice),
            "tipo": info.get("tipo", "altro"),
            "costi": round(costo, 2),
            "ricavi_stimati": round(ricavi_cdc, 2),
            "ricavi_sono_stima": True,
            "margine": round(margine, 2),
            "margine_percentuale": round((margine / ricavi_cdc * 100), 1) if ricavi_cdc > 0 else 0,
            "fatture_count": analitica["fatture_count"].get(codice, 0),
            "stato": "PROFITTO (stima)" if margine > 0 else "PERDITA (stima)",
        })

    return {
        "anno": anno,
        "centri_costo": report,
        "qualita_costi": analitica,
        "avviso_ricavi": (
            "I COSTI per CDC derivano dalle singole righe XML classificate; righe "
            "ambigue restano DA_VERIFICARE. I RICAVI per CDC restano una stima "
            "finche non esiste una fonte ricavi reale per settore."
        ),
        "totali": {
            "ricavi": round(ricavi_totali, 2),
            "costi_validati": round(costi_totali_validati, 2),
            "costi_da_verificare": analitica["da_verificare"],
            "margine_su_costi_validati": round(ricavi_totali - costi_totali_validati, 2),
        },
    }


# ============== RIBALTAMENTO CDC =============='''
text = text[:match.start()] + new_func + text[match.end():]
p.write_text(text)

replace_once(path,
'''    # 1. Costi per centro di costo
    costi_pipeline = [
        {"$match": {"invoice_date": {"$gte": date_start, "$lte": date_end}}},
        {"$group": {
            "_id": {"$ifNull": ["$centro_costo", "CDC-99"]},
            "totale": {"$sum": "$total_amount"},
            "count": {"$sum": 1}
        }}
    ]
    costi_per_cdc = await db[Collections.INVOICES].aggregate(costi_pipeline).to_list(50)
    costi_dict = {c["_id"]: c["totale"] for c in costi_per_cdc}
''',
'''    # 1. Costi per centro di costo: fonte analitica = righe XML classificate.
    analitica = await _costi_cdc_da_righe_xml(db, anno)
    costi_dict = analitica["costi"]
''')
replace_once(path,
'''    # 3. Ricavi totali e quote-ricavo per settore
    ricavi_result = await db[Collections.CORRISPETTIVI].aggregate([
        {"$match": {"data": {"$gte": date_start, "$lte": date_end}}},
        {"$group": {"_id": None, "totale": {"$sum": "$totale"}}}
    ]).to_list(1)
    ricavi_totali = ricavi_result[0]["totale"] if ricavi_result else 0
''',
'''    # 3. Ricavi totali dalla stessa fonte canonica del Conto Economico.
    from app.routers.accounting.bilancio import get_conto_economico
    ce = await get_conto_economico(anno=anno, mese=None)
    ricavi_totali = float(ce["ricavi"]["totale_ricavi"] or 0)
''')
replace_once(path,
'''        "ribaltamenti": ribaltamenti,
''',
'''        "qualita_costi": analitica,
        "ribaltamenti": ribaltamenti,
''')

# ---------------------------------------------------------------------------
# Regression tests
# ---------------------------------------------------------------------------
Path('tests/test_point11_assets_cdc.py').write_text(r'''import asyncio

from app.routers.accounting import bilancio, centri_costo


def _run(coro):
    return asyncio.run(coro)


class _Cursor:
    def __init__(self, rows): self.rows = list(rows)
    async def to_list(self, _n): return list(self.rows)


class _Collection:
    def __init__(self, rows=None): self.rows = list(rows or [])
    def find(self, *_args, **_kwargs): return _Cursor(self.rows)


class _DB(dict):
    def __getitem__(self, key):
        return dict.__getitem__(self, key)


def test_cespiti_capitalizzati_e_ammortamenti_registrati():
    db = _DB({
        'cespiti': _Collection([
            {'id': 'c1', 'provenienza': 'fattura_xml', 'fattura_id': 'f1',
             'data_acquisto': '2026-03-10', 'valore_acquisto': 3500.0,
             'piano_ammortamento': [{'anno': 2026, 'quota': 210.0}]},
            {'id': 'c2', 'provenienza': 'fattura_xml', 'fattura_id': 'f1',
             'data_acquisto': '2026-03-10', 'valore_acquisto': 500.0,
             'piano_ammortamento': []},
        ])
    })
    per_fattura, totale = _run(bilancio._cespiti_capitalizzati_nel_periodo(
        db, '2026-01-01', '2026-12-31'))
    assert per_fattura['f1'] == 4000.0
    assert totale == 4000.0
    annuo, meta = _run(bilancio._ammortamenti_registrati_periodo(db, 2026, None))
    mensile, _ = _run(bilancio._ammortamenti_registrati_periodo(db, 2026, 3))
    assert annuo == 210.0
    assert mensile == 17.5
    assert meta['solo_quote_registrate'] is True


def test_cdc_usa_righe_xml_ed_esclude_cespite():
    invoice = {
        'id': 'f1', 'invoice_date': '2026-03-10', 'tipo_documento': 'TD01',
        'classificazioni_righe': [
            {'descrizione': 'Imballaggi carta', 'centro_costo_id': '13.1_IMBALLAGGI',
             'centro_costo_nome': 'Imballaggi e confezioni', 'imponibile': 100.0,
             'richiede_verifica': False},
            {'descrizione': 'Manutenzione locale', 'centro_costo_id': '5.4_MANUTENZIONE_LOCALI',
             'centro_costo_nome': 'Manutenzione locali', 'imponibile': 50.0,
             'richiede_verifica': False},
            {'descrizione': 'Forno industriale 6 teglie', 'centro_costo_id': '5.3_PICCOLE_ATTREZZATURE',
             'centro_costo_nome': 'Attrezzature', 'imponibile': 3500.0,
             'richiede_verifica': False},
            {'descrizione': 'Voce ignota', 'centro_costo_id': '99_ALTRI_COSTI',
             'centro_costo_nome': 'Altro', 'imponibile': 25.0,
             'richiede_verifica': True},
        ],
    }
    asset = {'fattura_id': 'f1', 'descrizione': 'Forno industriale 6 teglie',
             'valore_acquisto': 3500.0, 'provenienza': 'fattura_xml',
             'data_acquisto': '2026-03-10'}
    db = _DB({'invoices': _Collection([invoice]), 'cespiti': _Collection([asset])})
    out = _run(centri_costo._costi_cdc_da_righe_xml(db, 2026))
    assert out['costi']['CDC-04'] == 100.0
    assert out['costi']['CDC-99'] == 50.0
    assert out['cespiti_esclusi'] == 3500.0
    assert out['da_verificare'] == 25.0
    assert out['righe_da_verificare'] == 1


def test_ce_source_non_spesa_due_volte_cespiti():
    source = open('app/routers/accounting/bilancio.py', encoding='utf-8').read()
    assert 'acquisti_operativi = totale_acquisti - totale_cespiti_capitalizzati' in source
    assert 'totale_costi = costi_netti + ammortamenti_registrati' in source
    assert '"B10_ammortamenti"' in source
''')
