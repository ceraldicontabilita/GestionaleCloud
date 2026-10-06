import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import api from '../api';
import SituazioneFiscale, { endpointFor, resolveDeclarationVersions } from './SituazioneFiscale';

vi.mock('../api', () => ({ default: { get: vi.fn(), post: vi.fn() } }));
vi.mock('../contexts/AnnoContext', () => ({ useAnnoGlobale: () => ({ anno: 2026 }) }));
describe('Situazione fiscale dal registro F24', () => {
  it('la scheda «Da pagare» elenca i tributi da pagare', async () => {
    api.get.mockImplementation(path => Promise.resolve({ data: path === '/api/fiscal/summary'
      ? { counts: {} }
      : { items: [] } }));

    render(<MemoryRouter initialEntries={['/situazione-fiscale/tributi']}><SituazioneFiscale /></MemoryRouter>);

    expect(await screen.findByRole('heading', { name: 'Da pagare' })).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith('/api/fiscal/obligations?status=TO_PAY&raggruppa=true&limit=200&offset=0');
    expect(screen.getByRole('tab', { name: 'Pagati con quietanza' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Tutti i tributi F24' })).toBeInTheDocument();
  });

  it('Piano tributi, Tributi e Ritenute sono schede della stessa pagina', async () => {
    api.get.mockImplementation(path => Promise.resolve({ data: path === '/api/fiscal/summary' ? { counts: {} } : { items: [] } }));
    render(<MemoryRouter initialEntries={['/situazione-fiscale/tributi']}><SituazioneFiscale /></MemoryRouter>);
    await screen.findByRole('heading', { name: 'Da pagare' });
    expect(screen.getByRole('tab', { name: 'Piano tributi' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Tributi' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Ritenute' })).toBeInTheDocument();
  });

  it('aprendo Situazione fiscale senza scheda si arriva sul Piano tributi', async () => {
    api.get.mockImplementation(path => Promise.resolve({ data: path.startsWith('/api/f24/piano-tributi')
      ? { anno: 2026, voci: [], conteggi: {}, etichette: {}, mancano: [], fuori_piano: [], modelli_doppi: 0 }
      : { counts: {}, items: [] } }));
    render(<MemoryRouter initialEntries={['/situazione-fiscale']}><SituazioneFiscale /></MemoryRouter>);
    await waitFor(() => expect(api.get).toHaveBeenCalledWith(expect.stringContaining('/api/f24/piano-tributi')));
    expect(screen.getByRole('link', { name: 'Tributi' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Ritenute' })).toBeInTheDocument();
  });

  it('la scheda Piano tributi mostra il piano senza passare dagli elenchi F24', async () => {
    api.get.mockImplementation(path => Promise.resolve({ data: path.startsWith('/api/f24/piano-tributi')
      ? { anno: 2026, voci: [], conteggi: {}, etichette: {}, mancano: [], fuori_piano: [], modelli_doppi: 0 }
      : {} }));
    render(<MemoryRouter initialEntries={['/situazione-fiscale/piano']}><SituazioneFiscale /></MemoryRouter>);
    expect(await screen.findByRole('button', { name: 'Scarica Excel' })).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith(expect.stringMatching(/^\/api\/f24\/piano-tributi\?anno=\d{4}$/));
    expect(api.get).not.toHaveBeenCalledWith(expect.stringContaining('/api/fiscal/obligations'));
  });

  beforeEach(() => {
    vi.clearAllMocks();
    api.post.mockResolvedValue({ data: { success: true, duplicate: false, payment_proven: false } });
    api.get.mockImplementation(path => {
      if (path === '/api/fiscal/summary') return Promise.resolve({ data: {
        counts: {
          f24_documents: 320, f24_rows: 1297, tax_debit_rows: 973,
          documentary_payment_documents: 320, declarations: 60,
        },
        requires_review: 0,
      } });
      if (path === '/api/fiscal/declarations/DOC-770/field-certainty') return Promise.resolve({ data: {
        source: { sha256: 'abcdef1234567890' },
        extraction: { field_level_status: 'ESTRATTO_CON_CERTEZZA', extracted_with_certainty: 1 },
        reconciliation: { all_certain: true, requires_review: 0, counts: { CONCORDANTE: 1 }, erario_counts: { NULLA_DOVUTO_ERARIO_DOCUMENTATO: 1 }, items: [{
          id: 'match-1', status: 'CONCORDANTE', candidate_count: 1,
          erario_state: 'NULLA_DOVUTO_ERARIO_DOCUMENTATO', documentary_payment_proven: true,
          accountant_f24_present: true,
          declaration_row: { id: 'DECL-ROW-1', page_number: 7, tax_code: '1040', reference_period: '2024-08', paid_amount: 1446.57, interest_amount: 0, certainty_reason: 'versamento_ordinario_importi_uguali', source_text: '08 2024 1.446,57 1.446,57' },
        }] },
        management_reconciliation: { all_certain: true, items: [{
          declaration_tax_row_id: 'DECL-ROW-1', tax_code: '1040', period: '2024-08',
          declared_cents: 144657, management_cents: 144657, status: 'CONCORDANTE',
        }] },
      } });
      if (path.startsWith('/api/fiscal/declarations')) return Promise.resolve({ data: {
        items: [{
          id: 'DOC-770', document_id: 'DOC-770',
          document_type: 'MODELLO_770', filing_year: 2026, tax_year: 2025,
          filename: '770_2026.pdf', f24_links: [],
        }],
        sources: { fiscal_documents: 1, canonical: 'fiscal_documents' },
      } });
      if (path === '/api/fiscal/source-certainty') return Promise.resolve({ data: {
        items: [{
          id: 'certainty:COMM-F24-1', status: 'CONCORDANTE', requires_review: false,
          erario_state: 'NULLA_DOVUTO_ERARIO_DOCUMENTATO',
          candidate_count: 1,
          accountant_document: { document_id: 'COMM-F24-1', filename: 'f24-commercialista.pdf', row_count: 2 },
          official_document: { document_id: 'DRIVE-Q-1', filename: 'quietanza-drive.pdf', row_count: 2 },
        }],
        certain: 1, requires_review: 0,
        sources: { commercialista_f24_documents: 1, quietanza_drive_rows: 2, unattributed_f24_model_documents: 19 },
        declarations: { documents: 60, field_level_reconciled: 0, requires_review: true, identity_or_version_review: 2 },
        declaration_items: [{
          document_id: 'DOC-770', document_type: 'MODELLO_770', filing_year: 2025,
          filename: '770_2025.pdf', relation_state: 'CONFERMATA_NOME_UNIVOCO_E_INDICE_VERIFICATO',
          field_check_status: 'PRONTO_PER_VERIFICA_CAMPI',
        }],
      } });
      return Promise.resolve({ data: { items: [] } });
    });
  });

  it('mostra conteggi del registro e dichiarazioni senza avvisi Drive', async () => {
    render(<MemoryRouter initialEntries={['/situazione-fiscale/dichiarazioni']}><SituazioneFiscale /></MemoryRouter>);

    expect(await screen.findByText('770_2026.pdf')).toBeInTheDocument();
    expect(screen.getAllByText('320')).toHaveLength(2);
    expect(screen.getByText('1297')).toBeInTheDocument();
    expect(screen.getByText('973')).toBeInTheDocument();
    expect(screen.getByText('60')).toBeInTheDocument();
    expect(screen.queryByText(/Indice Drive non disponibile/)).not.toBeInTheDocument();
    expect(screen.getByText('Modelli F24')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Apri dichiarazione' })).toBeEnabled();
  });

  it('mostra i tributi documentati dalle quietanze senza inventare la verifica bancaria', async () => {
    api.get.mockImplementation(path => {
      if (path === '/api/fiscal/summary') return Promise.resolve({ data: {
        counts: { documentary_payment_documents: 320 },
      } });
      if (path.includes('/api/fiscal/obligations') && path.includes('cerca=inesistente')) {
        return Promise.resolve({ data: {
          items: [], total: 0, total_groups: 1, total_rows: 2,
          totali: { debit_amount: 0, credit_amount: 0, net_amount: 0 },
          facets: { anni: ['2024'], stati: ['QUIETANZA_PRESENTE'] },
        } });
      }
      if (path.includes('/api/fiscal/obligations')) {
        // Il server rende il documento intero, con le sue righe tributo.
        const righe = [{
          id: 'drive-paid-1', document_id: 'DOC-Q', source_kind: 'F24_REGISTRO_ROW',
          tax_code: '1001', description: 'Ritenute su retribuzioni', reference_period: '10/2024',
          debit_amount: 1455.21, credit_amount: 0, payment_date: '2024-11-18',
          filename: 'quietanza.pdf', protocol: '24111809324228190',
          payment_status: 'DOCUMENTATO_DA_QUIETANZA',
          documentary_payment_status: 'QUIETANZA_PRESENTE', bank_status: 'DA_VERIFICARE',
        }, {
          id: 'drive-paid-2', document_id: 'DOC-Q', source_kind: 'F24_REGISTRO_ROW',
          tax_code: '3802', description: 'Addizionale regionale IRPEF', reference_period: '10/2024',
          debit_amount: 44.79, credit_amount: 0, payment_date: '2024-11-18',
          filename: 'quietanza.pdf', protocol: '24111809324228190',
          payment_status: 'DOCUMENTATO_DA_QUIETANZA',
          documentary_payment_status: 'QUIETANZA_PRESENTE', bank_status: 'DA_VERIFICARE',
        }];
        return Promise.resolve({ data: {
          items: [{ ...righe[0], id: 'f24-group-DOC-Q', is_f24_group: true, rows: righe,
            debit_amount: 1500, credit_amount: 0, net_amount: 1500 }],
          total: 1, total_groups: 1, total_rows: 2,
          totali: { debit_amount: 1500, credit_amount: 0, net_amount: 1500 },
          facets: { anni: ['2024'], stati: ['QUIETANZA_PRESENTE'] },
          sources: { registro_f24: 2, canonical: 'registro_f24' },
        } });
      }
      return Promise.resolve({ data: { items: [] } });
    });

    render(<MemoryRouter initialEntries={['/situazione-fiscale/tributi-pagati']}><SituazioneFiscale /></MemoryRouter>);

    expect(await screen.findByText(/Ritenute su retribuzioni/)).toBeInTheDocument();
    expect(screen.getByText('Protocollo 24111809324228190')).toBeInTheDocument();
    expect(screen.getAllByText('2 righe tributo', { exact: false }).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('Addizionale regionale IRPEF')).toBeInTheDocument();
    expect(screen.queryByText('drive-paid-1')).not.toBeInTheDocument();
    expect(screen.getByLabelText('Cerca nella sezione')).toBeInTheDocument();
    expect(screen.getByText('Quietanza documentale presente · riscontro bancario da verificare')).toBeInTheDocument();
    // la quietanza non ha un PDF nel registro: nessun bottone che fallirebbe
    expect(screen.queryByRole('button', { name: 'Apri PDF' })).not.toBeInTheDocument();
    expect(screen.getByTestId('fiscal-conteggio')).toHaveTextContent('1 documenti su 1 · 2 righe tributo');
    fireEvent.change(screen.getByLabelText('Cerca nella sezione'), { target: { value: 'inesistente' } });
    // La ricerca la fa il server: il testo parte dopo una breve pausa.
    expect(await screen.findByText('Nessun risultato con questi filtri.')).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith(
      '/api/fiscal/obligations?status=PAID_ON_TIME&raggruppa=true&limit=200&offset=0&cerca=inesistente',
    );
    fireEvent.click(screen.getByRole('button', { name: 'Azzera filtri' }));
    expect(await screen.findByText(/Ritenute su retribuzioni/)).toBeInTheDocument();
  });

  it('non dipende dal vecchio servizio di revisione', async () => {
    api.get.mockImplementation(path => {
      if (path === '/api/fiscal/summary') return Promise.resolve({ data: {
        counts: { declarations: 60 },
      } });
      if (path.includes('/api/fiscal/obligations')) return Promise.resolve({ data: {
        items: [{ id: 'tributo-1', document_number: 'Tributo pagato verificato', payment_status: 'PAID_ON_TIME' }],
      } });
      return Promise.resolve({ data: { items: [] } });
    });

    render(<MemoryRouter initialEntries={['/situazione-fiscale/tributi-pagati']}><SituazioneFiscale /></MemoryRouter>);

    expect(await screen.findByText('Tributo pagato verificato')).toBeInTheDocument();
    expect(api.get).not.toHaveBeenCalledWith('/api/fiscal/review');
  });

  it('mantiene la sezione utilizzabile quando il riepilogo risponde 502', async () => {
    api.get.mockImplementation(path => {
      if (path === '/api/fiscal/summary') return Promise.reject({ response: { status: 502 } });
      if (path.includes('/api/fiscal/obligations')) return Promise.resolve({ data: {
        items: [{ id: 'tributo-2', document_number: 'Pagamento ancora consultabile', payment_status: 'PAID_ON_TIME' }],
      } });
      return Promise.resolve({ data: { items: [] } });
    });

    render(<MemoryRouter initialEntries={['/situazione-fiscale/tributi-pagati']}><SituazioneFiscale /></MemoryRouter>);

    expect(await screen.findByText('Pagamento ancora consultabile')).toBeInTheDocument();
    expect(screen.getByText('Riepilogo temporaneamente non disponibile; i dati della sezione restano consultabili.')).toBeInTheDocument();
  });

  it('mostra il confronto bidirezionale senza certificare corrispondenze per solo importo', async () => {
    render(<MemoryRouter initialEntries={['/situazione-fiscale/confronto-fonti']}><SituazioneFiscale /></MemoryRouter>);

    expect(await screen.findByText('f24-commercialista.pdf')).toBeInTheDocument();
    expect(screen.getByText('COMM-F24-1')).toBeInTheDocument();
    expect(screen.getByText('DRIVE-Q-1')).toBeInTheDocument();
    expect(screen.getAllByText('CONCORDANTE')).toHaveLength(2);
    expect(screen.getByText(/Verifica dichiarazioni disponibile per i modelli supportati/)).toBeInTheDocument();
    expect(screen.getByText(/2 dichiarazioni escluse dal totale automatico/)).toBeInTheDocument();
    expect(screen.getByText(/Il solo importo non conferma mai un collegamento/)).toBeInTheDocument();
    expect(screen.getByText('Modelli F24 senza provenienza')).toBeInTheDocument();
    expect(screen.getByText('19')).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith('/api/fiscal/source-certainty');

    fireEvent.click(screen.getByRole('button', { name: 'Verifica campi e F24' }));
    expect(await screen.findByText('Pag. 7')).toBeInTheDocument();
    expect(screen.getAllByText(/446,57/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('CONCORDANTE').length).toBeGreaterThanOrEqual(3);
    expect(screen.getAllByText('NULLA DOVUTO ERARIO DOCUMENTATO').length).toBeGreaterThanOrEqual(2);
    expect(api.get).toHaveBeenCalledWith('/api/fiscal/declarations/DOC-770/field-certainty');
  });

  it('costruisce con un solo comando il registro dovuto pagato di tutte le dichiarazioni', async () => {
    render(<MemoryRouter initialEntries={['/situazione-fiscale/confronto-fonti']}><SituazioneFiscale /></MemoryRouter>);

    fireEvent.click(await screen.findByRole('button', { name: 'Verifica tutte le dichiarazioni' }));

    expect(await screen.findByRole('heading', { name: 'Registro automatico dovuto / pagato' })).toBeInTheDocument();
    expect((await screen.findAllByText(/MODELLO_770/)).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('NULLA DOVUTO ERARIO DOCUMENTATO').length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText('CONCORDANTE CON GESTIONALE')).toBeInTheDocument();
    expect(screen.getByText('PRESENTE')).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith('/api/fiscal/declarations/DOC-770/field-certainty');
  });

  it('acquisisce un F24 del commercialista come modello atteso e non come pagamento', async () => {
    const { container } = render(<MemoryRouter initialEntries={['/situazione-fiscale/confronto-fonti']}><SituazioneFiscale /></MemoryRouter>);

    expect(await screen.findByRole('button', { name: 'Inserisci F24 commercialista' })).toBeEnabled();
    const input = container.querySelector('input[type="file"]');
    fireEvent.change(input, { target: { files: [new File(['%PDF-1.4 model'], 'f24-commercialista.pdf', { type: 'application/pdf' })] } });

    expect(api.post).toHaveBeenCalledWith(
      '/api/documenti-fiscali/upload-f24-commercialista', expect.any(FormData),
      { headers: { 'Content-Type': 'multipart/form-data' } },
    );
    const form = api.post.mock.calls[0][1];
    expect(form.get('anno')).toBe('2026');
    expect(form.get('file').name).toBe('f24-commercialista.pdf');
  });

  it('mostra LIPE, crediti e confronto gestionale senza creare un falso F24', async () => {
    api.get.mockImplementation(path => {
      if (path === '/api/fiscal/summary') return Promise.resolve({ data: { counts: {} } });
      if (path === '/api/fiscal/source-certainty') return Promise.resolve({ data: {
        items: [], certain: 0, requires_review: 0,
        sources: { commercialista_f24_documents: 0, quietanza_drive_rows: 0 },
        declarations: { documents: 1, requires_review: true },
        declaration_items: [{ document_id: 'DOC-LIPE', document_type: 'LIPE', filing_year: 2026, filename: 'LIPE_2026.pdf', field_check_status: 'PRONTO_PER_VERIFICA_CAMPI' }],
      } });
      if (path === '/api/fiscal/declarations/DOC-LIPE/field-certainty') return Promise.resolve({ data: {
        source: { sha256: '1234567890abcdef' },
        extraction: { document_type: 'LIPE', field_level_status: 'ESTRATTO_CON_CERTEZZA', extracted_with_certainty: 1, declared_fields: [{
          id: 'M1', reference_period: '2026-01', page_number: 2,
          values: { vp4_cents: 504743, vp5_cents: 1277961, vp6_cents: 773218, vp6_side: 'credito', vp14_cents: 773218, vp14_side: 'credito' },
          f24_expectation: 'NESSUN_F24_A_DEBITO_ATTESO_CREDITO_LIPE',
        }] },
        reconciliation: { items: [], counts: {}, requires_review: 0, all_certain: false },
        management_reconciliation: { items: [{ id: 'G1', period: '2026-01', field: 'VP4', declared_cents: 504743, management_cents: 504743, status: 'CONCORDANTE' }] },
      } });
      return Promise.resolve({ data: { items: [] } });
    });

    render(<MemoryRouter initialEntries={['/situazione-fiscale/confronto-fonti']}><SituazioneFiscale /></MemoryRouter>);
    fireEvent.click(await screen.findByRole('button', { name: 'Verifica campi e F24' }));

    expect((await screen.findAllByText('2026-01')).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/NESSUN F24 A DEBITO ATTESO CREDITO LIPE/)).toBeInTheDocument();
    expect(screen.getAllByText(/732,18/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('CONCORDANTE')).toHaveLength(1);
  });

  it('mostra saldo e credito Redditi con prova RN/RX senza inventare un F24', async () => {
    api.get.mockImplementation(path => {
      if (path === '/api/fiscal/summary') return Promise.resolve({ data: { counts: {} } });
      if (path === '/api/fiscal/source-certainty') return Promise.resolve({ data: {
        items: [], sources: {}, declarations: { documents: 1, requires_review: false },
        declaration_items: [{ document_id: 'DOC-REDDITI', document_type: 'REDDITI_SC', filing_year: 2025, filename: '760_2025.pdf', field_check_status: 'PRONTO_PER_VERIFICA_CAMPI' }],
      } });
      if (path === '/api/fiscal/declarations/DOC-REDDITI/field-certainty') return Promise.resolve({ data: {
        source: { sha256: 'abcdef1234567890' },
        extraction: {
          document_type: 'REDDITI_SC', field_level_status: 'ESTRATTO_CON_CERTEZZA',
          extracted_with_certainty: 4, f24_expectation: 'NESSUN_F24_2003_A_DEBITO_ATTESO_CREDITO_IRES',
          version_warning: 'Verificare eventuali dichiarazioni successive dello stesso periodo d’imposta',
          declared_fields: [
            { id: 'RN24', field: 'RN24', value: 7, page_number: 6, source_text: 'RN24 7,00' },
            { id: 'RX1C', field: 'RX1_CREDITO', value: 7, page_number: 22, source_text: 'RX1_CREDITO 7,00' },
          ],
        },
        reconciliation: { items: [], counts: {}, requires_review: 0, all_certain: true },
      } });
      return Promise.resolve({ data: { items: [] } });
    });

    render(<MemoryRouter initialEntries={['/situazione-fiscale/confronto-fonti']}><SituazioneFiscale /></MemoryRouter>);
    fireEvent.click(await screen.findByRole('button', { name: 'Verifica campi e F24' }));

    expect(await screen.findByText('RN24')).toBeInTheDocument();
    expect(screen.getByText('RX1_CREDITO')).toBeInTheDocument();
    expect(screen.getByText(/NESSUN F24 2003 A DEBITO ATTESO CREDITO IRES/)).toBeInTheDocument();
    expect(screen.getByText(/dichiarazioni successive/)).toBeInTheDocument();
  });
});

describe('selezione probatoria della versione dichiarativa', () => {
  const declarations = [
    { document_id: 'ORD', document_type: 'REDDITI_SC', tax_year: 2022 },
    { document_id: 'INT', document_type: 'REDDITI_SC', tax_year: 2022 },
  ];

  it('seleziona solo l integrativa successiva quando identita e date sono provate', () => {
    const common = { declaration_identity_proven: true, taxpayer_tax_code: '04523831214' };
    const result = resolveDeclarationVersions(declarations, {
      ORD: { extraction: { ...common, document_id: 'ORD', declaration_identifier: 'A-1', declaration_filing_date: '2023-11-29', submission_kind: 'ORDINARIA_O_NON_DETERMINATA' } },
      INT: { extraction: { ...common, document_id: 'INT', declaration_identifier: 'B-1', declaration_filing_date: '2024-08-05', submission_kind: 'DICHIARAZIONE_INTEGRATIVA_CODICE_2' } },
    });

    expect([...result.selectedIds]).toEqual(['INT']);
    expect(result.states.ORD).toBe('SOSTITUITA_DA_INTEGRATIVA_PIU_RECENTE');
    expect(result.resolvedGroups).toBe(1);
  });

  it('non sceglie una versione se il codice fiscale non coincide', () => {
    const result = resolveDeclarationVersions(declarations, {
      ORD: { extraction: { document_id: 'ORD', declaration_identity_proven: true, taxpayer_tax_code: '04523831214', declaration_identifier: 'A-1', declaration_filing_date: '2023-11-29' } },
      INT: { extraction: { document_id: 'INT', declaration_identity_proven: true, taxpayer_tax_code: '99999999999', declaration_identifier: 'B-1', declaration_filing_date: '2024-08-05', submission_kind: 'DICHIARAZIONE_INTEGRATIVA_CODICE_2' } },
    });

    expect(result.selectedIds.size).toBe(0);
    expect(result.unresolvedGroups).toBe(1);
  });
});

describe('Situazione fiscale a pagine di 200 documenti', () => {
  const documento = n => ({
    id: `f24-group-DOC-${n}`, document_id: `DOC-${n}`, source_kind: 'F24_REGISTRO_ROW',
    is_f24_group: true, tax_code: '1001', description: `Tributo ${n}`, payment_date: '2026-01-16',
    filename: `f24-${n}.pdf`, debit_amount: 10, credit_amount: 0, net_amount: 10,
    documentary_payment_status: 'DA_VERIFICARE',
    rows: [{ id: `DOC-${n}:1`, tax_code: '1001', description: `Tributo ${n}`, debit_amount: 10, credit_amount: 0 }],
  });

  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockImplementation(path => {
      if (path === '/api/fiscal/summary') return Promise.resolve({ data: { counts: {} } });
      if (path.startsWith('/api/fiscal/obligations?status=TO_PAY&raggruppa=true&limit=200&offset=200')) {
        return Promise.resolve({ data: { items: [documento(200)], total: 201 } });
      }
      if (path.startsWith('/api/fiscal/obligations?status=TO_PAY&raggruppa=true&limit=200&offset=0')) {
        return Promise.resolve({ data: {
          items: Array.from({ length: 200 }, (_, i) => documento(i)),
          total: 201, total_groups: 201, total_rows: 201,
          totali: { debit_amount: 2010, credit_amount: 0, net_amount: 2010 },
          facets: { anni: ['2026'], stati: ['DA_VERIFICARE'] },
        } });
      }
      return Promise.resolve({ data: { items: [] } });
    });
  });

  it('endpoint dei documenti F24: raggruppati, a pagine e filtrati sul server', () => {
    expect(endpointFor('f24', { year: '2025', creditsOnly: true }, {}, { cerca: ' 1001 ', offset: 200 }))
      .toBe('/api/fiscal/f24-rows?year=2025&credits_only=true&raggruppa=true&limit=200&offset=200&cerca=1001');
    expect(endpointFor('tutti-tributi', {}, {}, { anno: '2024', stato: 'QUIETANZA_PRESENTE' }))
      .toBe('/api/fiscal/obligations?raggruppa=true&limit=200&offset=0&anno_documento=2024&stato_documento=QUIETANZA_PRESENTE');
  });

  it('«Mostra altre» accoda i documenti successivi, i totali restano del server', async () => {
    render(<MemoryRouter initialEntries={['/situazione-fiscale/tributi']}><SituazioneFiscale /></MemoryRouter>);

    const bottone = await screen.findByTestId('fiscal-mostra-altre');
    expect(bottone).toHaveTextContent('Mostra altre 1 · 1 rimanenti');
    expect(screen.getByTestId('fiscal-conteggio')).toHaveTextContent('201 documenti su 201 · 201 righe tributo');
    expect(screen.getByTestId('fiscal-conteggio')).toHaveTextContent('debiti');
    expect(screen.queryByText('Tributo 200')).not.toBeInTheDocument();

    fireEvent.click(bottone);
    await waitFor(() => expect(api.get).toHaveBeenCalledWith(
      '/api/fiscal/obligations?status=TO_PAY&raggruppa=true&limit=200&offset=200',
    ));
    expect((await screen.findAllByText(/Tributo 200/)).length).toBeGreaterThan(0);
    await waitFor(() => expect(screen.queryByTestId('fiscal-mostra-altre')).not.toBeInTheDocument());
  });
});
