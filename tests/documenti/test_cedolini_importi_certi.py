import fitz
from app.parsers import busta_paga_multi_template as parser
from app.services import cedolini_motore as motore

CF_A='RSSMRA80A01H501U'
CF_B='VRDLGU80A01H501S'

def pdf(*pages):
    document=fitz.open()
    for cells in pages:
        page=document.new_page(width=595,height=842)
        for x,y,text in cells:
            page.insert_text((x,y),text,fontsize=8)
    content=document.tobytes()
    document.close()
    return content

def salary(cf=CF_A, net='950,00', period='Maggio 2024', extra=()):
    cells=[(20,20,'COGNOMEsEsNOME'),(20,35,'PERIODOsDIsRETRIBUZIONE'),
           (20,50,period),(20,65,cf),(450,700,'NETTOsDELsMESE')]
    if net is not None: cells.append((480,712,net))
    return cells+list(extra)

def presence(cf=CF_A):
    return [(20,20,'Autorizzazione Inail n. 301 del 15/01/2009'),
            (20,40,'GIUSTIFICATIVI TIMBRATURE'),(20,60,'Maggio 2024'),(20,80,cf)]

def test_teamsystem_does_not_certify_an_unrelated_last_amount():
    content=pdf([(20,20,'Teamsystem S.p.A.'),(20,40,'MAGGIO 2024'),(20,60,CF_A),
                 (400,130,'NETTO BUSTA'),(20,220,'PROGRESSIVO'),(20,235,'777,00')])
    parsed=parser.parse_busta_paga_from_bytes(content)
    assert parsed['totali'].get('netto') is None, parsed['totali']

def test_different_net_cells_on_continuations_require_review():
    parsed=parser.parse_busta_paga_from_bytes(pdf(salary(net='950,00'),salary(net='900,00')))
    assert parsed['totali'].get('netto') is None, parsed['totali']
    assert parsed['totali']['stato_netto']=='MULTIPLE_NETS_DA_VERIFICARE'

def test_tfr_progressive_is_not_an_explicit_advance():
    parsed={}
    parser._acconti_e_anticipazioni(parsed,'TFR a fondi Anticipi\n80,00')
    assert parsed.get('acconti',{}).get('tfr_anticipo_erogato') is None, parsed

def test_presence_only_is_not_a_salary():
    read=motore.leggi_pdf(pdf(presence()))
    assert read['esito']=='presenze' and read['buste']==[]

def test_presence_then_salary_then_totals_continuation():
    content=pdf(presence(), salary(net=None,extra=[(20,120,'000306 Recupero acconto 300,00')]),
                [(450,700,'NETTOsDELsMESE'),(480,712,'950,00'),(20,150,'Quota mese 50,00')])
    read=motore.leggi_pdf(content)
    assert len(read['buste'])==1, read
    busta=read['buste'][0]
    assert busta['netto']==950 and busta['tfr_quota']==50, busta
    assert busta['dati_chiave']['acconto_recuperato_busta']=='300,00', busta
    assert (busta['source_page_start'],busta['source_page_end'])==(1,3)

def test_collective_pages_are_split_by_person_and_period():
    read=motore.leggi_pdf(pdf(presence(),salary(),presence(CF_B),salary(CF_B,net='800,00')))
    assert [(b['codice_fiscale'],b['netto']) for b in read['buste']]==[(CF_A,950),(CF_B,800)], read
    assert [(b['source_page_start'],b['source_page_end']) for b in read['buste']]==[(1,2),(3,4)]

def test_repeated_same_net_is_counted_once():
    read=motore.leggi_pdf(pdf(salary(),salary()))
    assert len(read['buste'])==1 and read['buste'][0]['netto']==950,read


def test_explicit_tfr_advance_under_50_is_kept_separate_from_progressive():
    parsed={}
    parser._acconti_e_anticipazioni(parsed,'000081 Anticipazione T.F.R.\n35,00\nTFR a fondi Anticipi\n1.000,00')
    assert parsed['acconti']['tfr_anticipo_erogato']==35
    assert parsed['acconti']['tfr_anticipo_voce']=='000081'
    assert parsed['acconti']['tfr_anticipi_residuo']==1000


def test_classic_additional_salary_uses_the_same_content_type_rule():
    text="Software payroll\nSETTEMBRE 2021\n852 14A MENSILITA' 57,33+ 8,08017 463,24+\n999 RETRIBUZIONE T.F.R. 100,00 463,24+"
    assert parser.parse_template_zucchetti_classic(text)['tipo_cedolino']=='quattordicesima'
    assert parser.parse_template_zucchetti_classic(text+"\n001 RETRIBUZIONE ORDINARIA 100,00+")['tipo_cedolino']=='mensile'


def test_replaying_a_collective_preserves_bytes_voices_and_source_pages():
    original=pdf(presence(),salary(extra=[(20,120,'000306 Recupero acconto 300,00')]),
                 presence(CF_B),salary(CF_B,net='800,00'))
    first=motore.leggi_pdf(original)['buste']
    second=motore.leggi_pdf(original)['buste']
    assert len(first)==len(second)==2
    for before,after in zip(first,second):
        for key in ('_pdf_data','impronta_busta','voci','source_page_start','source_page_end'):
            assert before.get(key)==after.get(key),key
    assert first[0]['dati_chiave']['acconto_recuperato_busta']=='300,00'
    assert [(b['source_page_start'],b['source_page_end']) for b in first]==[(1,2),(3,4)]


def test_net_proof_survives_voices_and_uses_the_original_document_page():
    original=pdf(presence(),salary(extra=[(20,120,'000306 Recupero acconto 300,00')]),
                 presence(CF_B),salary(CF_B,net='800,00'))
    buste=motore.leggi_pdf(original)['buste']
    assert [b['dati_chiave']['netto_provenienza'][0]['pagina'] for b in buste]==[2,4]
    assert buste[0]['dati_chiave']['netto_provenienza'][0]['etichetta']=='NETTOsDELsMESE'
    assert buste[0]['dati_chiave']['netto_provenienza'][0]['importo_testo']=='950,00'


def tfr_document(*, advance=False, prior=False):
    cells=[(20,20,'LIBRO UNICO DEL LAVORO'),(20,50,'DICEMBRE 2020'),(20,65,CF_A),
           (20,200,'ACCONTO :' if advance else 'FINE RAPPORTO'),
           (20,440,'IMPORTI ACCONTI SU TFR' if advance else "TOTALE INDENNITA' LORDA"),
           (520,440,'1295,00+' if advance else '2149,20+'),
           (20,540,'TOTALE TRATTENUTE'),(520,540,'295,59-' if advance else '1584,28-'),
           (510,712,'NETTO'),(520,728,'1.000,00+')]
    if prior: cells.extend([(20,525,"ANTICIPAZIONI GIA' EROGATI"),(440,525,'1292,00-')])
    return pdf(cells)


def test_standalone_tfr_preserves_printed_net_totals_and_prior_advance_as_deduction():
    busta=motore.leggi_pdf(tfr_document(prior=True))['buste'][0]
    assert busta['tipo_cedolino']=='tfr'
    assert (busta['lordo'],busta['totale_trattenute'],busta['netto'])==(2149.2,1584.28,1000)
    assert busta['dati_chiave']['tfr_anticipazioni_gia_erogate']==1292
    assert busta['dati_chiave'].get('anticipo_tfr_busta') is None
    assert busta['dati_chiave']['tfr_documento_natura']=='liquidazione_tfr'
    assert busta['netto_calcolato']==564.92  # Solo scarto da verificare: il netto stampato rimane 1.000.
    assert len(busta['voci'])>=3


def test_standalone_tfr_advance_is_separate_from_an_ordinary_salary_with_tfr_parts():
    busta=motore.leggi_pdf(tfr_document(advance=True))['buste'][0]
    assert busta['tipo_cedolino']=='tfr' and busta['lordo']==1295 and busta['netto']==1000
    assert busta['dati_chiave']['tfr_documento_natura']=='anticipo_tfr'
    ordinary="FINE RAPPORTO\nTOTALE INDENNITA' LORDA 2149,20+\n001 RETRIBUZIONE ORDINARIA 100,00+\nTOTALE COMPETENZE 3000,00"
    assert parser._detect_tipo_cedolino(ordinary)=='mensile'


def test_manager_counts_a_reverified_unknown_net_as_a_successful_hr_update(monkeypatch):
    import asyncio
    import json
    from app.services import cedolini_manager, hr_cedolini_deposito
    class Connection:
        patch=None
        async def execute(self,sql,id_,patch):
            self.patch=json.loads(patch)
    connection=Connection()
    async def deposit(document):
        return await hr_cedolini_deposito._segui_vincitore(connection,
            {'id':'existing','netto':900},document,'same-document',dry_run=False)
    monkeypatch.setattr(hr_cedolini_deposito,'deposita_cedolino_in_hr',deposit)
    results={'buste_senza_netto':0,'errori':[]}
    document={'codice_fiscale':CF_A,'anno':2024,'mese':5,'tipo_cedolino':'mensile',
              'netto':None,'stato_netto':'MULTIPLE_NETS_DA_VERIFICARE'}
    asyncio.run(cedolini_manager._registra_busta(None,document,filename='anonymous.pdf',
        pdf_data=None,pdf_text='',results=results))
    assert connection.patch['netto'] is None
    assert results['buste_senza_netto']==1 and results['errori']==[]


def test_salary_continuation_keeps_all_coded_voices_values_and_pages():
    first=salary(extra=[(20,120,'C00001 Retribuzione 1.500,00')])
    second=[(20,120,'Z50000 13ma Mensilita'),(260,120,'8,04343'),(350,120,'10,83250 ORE'),(500,120,'87,13'),
            (20,145,'Z50022 14ma Mensilita'),(260,145,'8,04343'),(350,145,'75,81250 ORE'),(500,145,'609,79'),
            (20,170,'ZP8130 Fondo T.F.R. al 31/12'),(500,170,'444,33'),
            (20,195,"ZP8134 Quota T.F.R. dell'anno"),(500,195,'96,31'),
            (20,220,'ZPB130 Fondo T.F.R.'),(500,220,'444,33'),
            (20,245,'Z9960 Fondo garanzia'),(500,245,'-16,00')]
    busta=motore.leggi_pdf(pdf(presence(),first,second))['buste'][0]
    by_code={v['codice']:v for v in busta['voci']}
    assert set(by_code)=={'C00001','Z50000','Z50022','ZP8130','ZP8134','ZPB130','Z9960'}
    assert by_code['ZP8130']['valori']==['444,33'] and by_code['ZP8134']['valori']==['96,31']
    assert by_code['Z9960']['valori']==['-16,00']
    assert by_code['Z50000']['valori']==['8,04343','10,83250','87,13']
    assert by_code['ZP8130']['provenienza']['pagina']==3
    assert busta['netto']==950 and busta['tipo_cedolino']=='mensile'
    assert busta['dati_chiave'].get('anticipo_tfr_busta') is None


def test_repeated_voices_preserve_each_page_and_numeric_column_without_summing():
    first=salary(extra=[(20,120,'C00001 Retribuzione'),(260,120,'9,54850'),
                        (350,120,'79,99992 ORE'),(480,120,'763,48')])
    second=[(20,120,'C00001 Retribuzione'),(260,120,'9,54850'),(350,120,'79,99992 ORE'),
            (480,120,'763,48'),(20,150,'Z00000 Contributo IVS'),(260,150,'965,00'),
            (350,150,'9,19000 %'),(480,150,'88,68'),(20,180,'TOTALE TRATTENUTE 9.000,00')]
    busta=motore.leggi_pdf(pdf(first,second))['buste'][0]
    salaries=[v for v in busta['voci'] if v['codice']=='C00001']
    assert len(salaries)==2
    assert [v['provenienza']['pagina'] for v in salaries]==[1,2]
    assert all(v['valori']==['9,54850','79,99992','763,48'] for v in salaries)
    deduction=next(v for v in busta['voci'] if v['codice']=='Z00000')
    assert deduction['valori']==['965,00','9,19000','88,68']
    assert busta['netto']==950


def test_disagreeing_tfr_total_does_not_keep_a_textual_first_candidate():
    document=pdf([(20,20,'LIBRO UNICO DEL LAVORO'),(20,50,'DICEMBRE 2020'),(20,65,CF_A),
                  (20,200,'FINE RAPPORTO'),(20,440,"TOTALE INDENNITA' LORDA"),(520,440,'2149,20+'),
                  (20,500,'TOTALE TRATTENUTE'),(520,500,'1584,28-'),
                  (20,540,'TOTALE TRATTENUTE'),(520,540,'900,00-'),
                  (510,712,'NETTO'),(520,728,'1.000,00+')])
    busta=motore.leggi_pdf(document)['buste'][0]
    assert busta['totale_trattenute'] is None
    assert busta['dati_chiave']['totali_tfr_da_verificare']['trattenute']==[900,1584.28]
    assert busta['netto']==1000


def test_teamsystem_conflicting_continuation_cells_require_review():
    def page(net):
        return [(20,20,'Teamsystem S.p.A.'),(20,40,'MAGGIO 2024'),(20,60,CF_A),
                (400,130,'NETTO BUSTA'),(410,152,net)]
    busta=motore.leggi_pdf(pdf(page('900,00'),page('800,00')))['buste'][0]
    assert busta['netto'] is None
    assert busta['stato_netto']=='MULTIPLE_NETS_DA_VERIFICARE'
    assert [p['pagina'] for p in busta['dati_chiave']['netto_provenienza']]==[1,2]


def test_teamsystem_repeated_identical_cells_remain_one_verified_salary():
    page=[(20,20,'Teamsystem S.p.A.'),(20,40,'MAGGIO 2024'),(20,60,CF_A),
          (400,130,'NETTO BUSTA'),(410,152,'900,00')]
    buste=motore.leggi_pdf(pdf(page,page))['buste']
    assert len(buste)==1 and buste[0]['netto']==900


def test_inline_base_does_not_hide_the_other_coordinate_columns():
    busta=motore.leggi_pdf(pdf(salary(extra=[(20,120,'C00001 Retribuzione 9,54850'),
        (350,120,'79,99992 ORE'),(480,120,'763,48')])))['buste'][0]
    voce=next(v for v in busta['voci'] if v['codice']=='C00001')
    assert voce['valori']==['9,54850','79,99992','763,48']


def test_numeric_classic_codes_require_the_body_code_column_and_keep_raw_uncertainty():
    cells=[(20,20,'LIBRO UNICO DEL LAVORO'),(20,40,'MAGGIO 2024'),(20,60,CF_A),
           (24,85,'850'),(60,85,'RIGA ANAGRAFICA'),
           (20,100,'CODICE'),(260,100,'ORE/GG'),(430,100,'TRATTENUTE'),(510,100,'COMPETENZE'),
           (24,130,'1'),(60,130,'IMPORTO ORDINARIO'),(260,130,'12,50+'),(350,130,'10,12345'),(520,130,'125,00+'),
           (24,150,'34'),(60,150,'FERIE GODUTE'),(520,150,'200,00+'),
           (24,170,'519'),(60,170,'VOCE SENZA IMPORTO'),
           (24,190,'123'),(350,190,'ALTRA QUANTITA'),
           (60,220,'TOTALE COMPETENZE'),(520,220,'325,00+'),
           (24,245,'999'),(60,245,'FUORI CORPO'),
           (510,712,'NETTO'),(520,728,'325,00+')]
    busta=motore.leggi_pdf(pdf(cells))['buste'][0]
    by_code={v['codice']:v for v in busta['voci']}
    assert set(by_code)=={'1','34','519'}
    assert by_code['1']['valori']==['12,50+','10,12345','125,00+']
    assert by_code['519']['valori']==[] and by_code['519']['stato_lettura']=='da_verificare'
    assert by_code['519']['riga_testo']=='519 VOCE SENZA IMPORTO'
    assert by_code['34']['provenienza']['pagina']==1


def test_numeric_teamsystem_body_excludes_parallel_presence_amounts():
    cells=[(20,20,'Teamsystem S.p.A.'),(20,40,'MAGGIO 2024'),(20,60,CF_A),
           (28,100,'CODICE'),(50,100,'DESCRIZIONE'),(250,100,'COMPETENZE'),
           (298,100,'TRATTENUTE'),(356,100,'STATISTICHE'),
           (24,130,'8101'),(50,130,'FERIE GODUTE'),(160,130,'10,00'),(195,130,'7,96535'),
           (270,130,'79,65'),(414,130,'5,00'),
           (24,155,'9117'),(50,155,'ADDIZIONALE REGIONALE'),(320,155,'12,59'),(414,155,'4,00'),
           (28,220,'TOTALE LORDO'),(270,220,'900,00'),
           (24,245,'9714'),(50,245,'FUORI CORPO'),
           (400,700,'NETTO BUSTA'),(410,722,'720,00')]
    busta=motore.leggi_pdf(pdf(cells))['buste'][0]
    by_code={v['codice']:v for v in busta['voci']}
    assert set(by_code)=={'8101','9117'}
    assert by_code['8101']['valori']==['10,00','7,96535','79,65']
    assert by_code['9117']['valori']==['12,59']
    assert busta['netto']==720


def test_glued_numeric_cells_remain_raw_and_marked_for_review():
    content=pdf([(20,20,'LIBRO UNICO DEL LAVORO'),(20,40,'MAGGIO 2024'),(20,60,CF_A),
                 (20,100,'CODICE'),(260,100,'ORE/GG'),(430,100,'TRATTENUTE'),(510,100,'COMPETENZE'),
                 (24,130,'999'),(60,130,'RETRIBUZIONE T.F.R.'),(260,130,'113,22+100,00'),
                 (350,130,'1033,22+'),(60,220,'TOTALE COMPETENZE'),
                 (510,712,'NETTO'),(520,728,'325,00+')])
    busta=motore.leggi_pdf(content)['buste'][0]
    voce=busta['voci'][0]
    assert voce['valori']==['1033,22+']
    assert voce['stato_lettura']=='da_verificare'
    assert any(c['testo']=='113,22+100,00' for c in voce['provenienza']['colonne_raw'])
    assert busta['dati_chiave']['voci_da_verificare']==[{'codice':'999','pagina':1}]
