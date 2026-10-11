import asyncio

from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services.declaration_dossiers import document_identity, group_annual_dossiers, attach_receipts, list_annual_dossiers
from app.services.f24_controllo_incrociato import _quietanza_legacy

CF = '04523831214'
ID = '18161244457-0000003'


def document(id='declaration', year=2023, cf=CF, ident=ID, **extra):
    return {'id': id, 'company_id': CF, 'document_type': 'MODELLO_770',
            'filename': f'Modello 770 - Anno {year} - {ident}.pdf',
            'codice_fiscale': cf, 'current_version_id': f'v-{id}',
            'quadri': {'anno_imposta': year, 'identificativo': ident}, **extra}


def component(id='st', **metadata):
    return {'id': id, 'filename': '02_Quadro_ST_modulo_1.pdf', 'document_type': 'componente_770',
            'parsed_metadata': {'identificativo_dichiarazione': ID, 'quadro': 'ST', 'modulo': 1, **metadata}}


def group(documents, components=(), versions=(), pages=()):
    return group_annual_dossiers(documents, components, pages, versions)


def test_one_annual_dossier_keeps_submissions_components_and_original_urls():
    docs = [document(), document('integrativa', ident='18292335587-0000001')]
    dossiers, unresolved = group(docs, [component(), component('sx', quadro='SX')])
    assert unresolved == []
    assert len(dossiers) == 1
    dossier = dossiers[0]
    assert dossier['model_years'] == [2024]
    assert dossier['tax_year'] == 2023
    assert dossier['submission_count'] == 2
    assert dossier['original_count'] == 4
    assert {d['pdf_url'] for d in dossier['originals']} == {
        '/api/originale/documento_fiscale/declaration', '/api/originale/documento_fiscale/integrativa',
        '/api/originale/documento/st', '/api/originale/documento/sx'}


def test_email_date_is_not_tax_year_and_component_inherits_from_exact_identifier():
    parent = document()
    fragment = document('fragment', filename='2026-04-17_mail_770_T241029181612444573_04523831214.pdf',
                        quadri={'identificativo': ID}, codice_fiscale=None)
    ds, _ = group([parent, fragment])
    assert len(ds) == 1
    assert ds[0]['tax_year'] == 2023
    assert ds[0]['model_years'] == [2024]


def test_770_model_year_in_filename_is_not_tax_year():
    ds, _ = group([document(filename='770_2023_imposta_2022_T231025144725533601.pdf', quadri={})])
    assert ds[0]['tax_year'] == 2022
    assert ds[0]['model_years'] == [2023]


def test_lipe_reads_printed_tax_year_and_boxed_cf_not_email_year_or_intermediary():
    doc = {'filename': '2023-01-04_mail_liquidazione.pdf', 'document_type': 'LIPE', 'company_id': CF}
    text = ('CONTRIBUENTE Partita IVA Codice fiscale Anno di imposta\n'
            + '\n'.join(CF) + '\n' + '\n'.join(CF) + '\n'
            + 'PNAGPP58D48F839K\n05721481215\n1\n2\n0\n1\n7\n19\n05\n2017\n')
    result = document_identity(doc, text)
    assert result['taxpayer_id'] == CF
    assert result['tax_year'] == 2017
    assert document_identity(doc, text.replace('\n'.join(CF), '\n'.join('12345678901')))['taxpayer_id'] is None


def test_subject_cf_beats_intermediary_and_tax_year_beats_filename():
    doc = {'filename': 'IVA_2008.pdf', 'document_type': 'DICHIARAZIONE_IVA'}
    text = "Responsabile Codice fiscale PRSGTN28M21F839Q\nDATI RELATIVI AL CONTRIBUENTE\nCodice fiscale\n04523831214\npresentato per l'anno d'imposta 2007"
    assert document_identity(doc, text)['taxpayer_id'] == CF
    assert document_identity(doc, text)['tax_year'] == 2007


def test_different_taxpayer_stays_separate_even_with_same_year():
    ds, unlinked = group([document(), document('other', cf='12345678901')], [component()])
    assert len(ds) == 2
    assert len(unlinked) == 1  # conflicting owner: cannot inherit an arbitrary CF
    assert all(d['original_count'] == 1 for d in ds)


def test_fragment_only_can_form_dossier_with_explicit_identity():
    ds, unlinked = group([], [component(codice_fiscale=CF, anno_imposta=2023)])
    assert len(ds) == 1 and not unlinked
    assert ds[0]['original_count'] == 1


def test_unknown_or_conflicting_components_remain_accessible_without_false_link():
    ds, unlinked = group([document()], [component('unknown', identificativo_dichiarazione='00000000001-0000001'),
                                       component('conflict', anno_imposta=2021)])
    assert ds[0]['original_count'] == 1
    assert {u['id'] for u in unlinked} == {'unknown', 'conflict'}


def test_only_exact_hash_duplicates_collapse_and_retain_copy_links():
    ds, _ = group([document(), document('copy'), document('different')], versions=[
        {'id': 'v-declaration', 'sha256': 'same', 'page_count': 10},
        {'id': 'v-copy', 'sha256': 'same', 'page_count': 10},
        {'id': 'v-different', 'sha256': 'other', 'page_count': 12}])
    assert ds[0]['original_count'] == 2
    assert len(next(o for o in ds[0]['originals'] if o['sha256'] == 'same')['copies']) == 1


def receipt(id='q', cf=CF, year='2023', code='1001', status=None):
    return _quietanza_legacy({'id': id, 'filename': f'{id}.pdf', 'codice_fiscale': cf,
                             'data_pagamento': '2024-01-16', 'saldo': 100, 'status': status,
                             'sezione_erario': [{'codice_tributo': code, 'anno': year, 'mese': '12', 'importo_debito': 100}]})


def test_receipts_link_without_f24_or_bank_only_same_taxpayer_tax_year_and_code():
    ds, _ = group([document()])
    attach_receipts(ds, [receipt(), receipt('foreign', cf='99999999999'), receipt('next-year', year='2024'),
                        receipt('vat', code='6001'), receipt('quarantine', status='quarantena')])
    assert ds[0]['receipt_count'] == 1
    q = ds[0]['quietanze'][0]
    assert q['quietanze'][0]['pdf_url'] == '/api/originale/quietanza/q'
    assert q['data'] == '2024-01-16'
    assert q['tax_rows'][0]['anno'] == 2023
    assert q['senza_modello'] is True


def test_770_uses_codes_read_in_st_beyond_static_catalog():
    ds, _ = group([document(quadri={'anno_imposta':2023, 'identificativo': ID, 'st_righe':[{'codice_tributo':'1035'}]})])
    attach_receipts(ds, [receipt(code='1035')])
    assert ds[0]['receipt_count'] == 1


def test_listing_is_read_only_and_includes_existing_company_components(monkeypatch):
    async def run():
        db = ClientArchivioMemoria()['fascicoli']
        await db['fiscal_documents'].insert_one(document())
        await db['documents_inbox'].insert_one(component())
        await db['documents_inbox'].insert_one({**component('foreign'), 'company_id': 'other'})
        async def receipts(_db): return [receipt()]
        monkeypatch.setattr('app.services.declaration_dossiers.reg.carica_quietanze', receipts)
        a = await list_annual_dossiers(db, company_id=CF, year=2023)
        b = await list_annual_dossiers(db, company_id=CF, year=2023)
        assert a == b
        assert a['items'][0]['original_count'] == 2
        assert a['items'][0]['receipt_count'] == 1
        assert await db['fiscal_documents'].count_documents({}) == 1
        assert (await list_annual_dossiers(db, company_id=CF, year=2024))['items'] == []
    asyncio.run(run())
