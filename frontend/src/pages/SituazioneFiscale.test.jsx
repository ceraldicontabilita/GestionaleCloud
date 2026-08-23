import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import api from '../api';
import SituazioneFiscale from './SituazioneFiscale';

vi.mock('../api', () => ({ default: { get: vi.fn(), post: vi.fn() } }));
describe('Situazione fiscale collegata all indice Drive', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockImplementation(path => {
      if (path === '/api/fiscal/summary') return Promise.resolve({ data: {
        counts: { documents: 0, obligations: 0, payments: 0, collection_claims: 0, ader_snapshots: 0 },
        requires_review: 0,
        drive_index: { available: true, verified: true, counts: {
          f24_documents: 320, f24_rows: 1297, tax_debit_rows: 973,
          documentary_payment_documents: 320, declarations: 60,
        } },
      } });
      if (path === '/api/fiscal/declarations/DOC-770/field-certainty') return Promise.resolve({ data: {
        source: { sha256: 'abcdef1234567890' },
        extraction: { field_level_status: 'ESTRATTO_CON_CERTEZZA', extracted_with_certainty: 1 },
        reconciliation: { all_certain: true, requires_review: 0, counts: { CONCORDANTE: 1 }, items: [{
          id: 'match-1', status: 'CONCORDANTE', candidate_count: 1,
          declaration_row: { page_number: 7, tax_code: '1001', reference_period: '2024-08', paid_amount: 1446.57, interest_amount: 0, certainty_reason: 'versamento_ordinario_importi_uguali', source_text: '08 2024 1.446,57 1.446,57' },
        }] },
      } });
      if (path.startsWith('/api/fiscal/declarations')) return Promise.resolve({ data: {
        items: [{
          id: 'DOC-770', document_id: 'DOC-770', source_kind: 'DRIVE_EXCEL_INDEX_DECLARATION',
          document_type: 'MODELLO_770', filing_year: 2026, tax_year: 2025,
          filename: '770_2026.pdf', f24_links: [],
        }],
        sources: { drive_excel_index: 1, canonical: 'google_drive' },
      } });
      if (path === '/api/fiscal/source-certainty') return Promise.resolve({ data: {
        items: [{
          id: 'certainty:COMM-F24-1', status: 'CONCORDANTE', requires_review: false,
          candidate_count: 1,
          accountant_document: { document_id: 'COMM-F24-1', filename: 'f24-commercialista.pdf', row_count: 2 },
          official_document: { document_id: 'DRIVE-Q-1', filename: 'quietanza-drive.pdf', row_count: 2 },
        }],
        certain: 1, requires_review: 0,
        sources: { commercialista_f24_documents: 1, quietanza_drive_rows: 2 },
        declarations: { documents: 60, field_level_reconciled: 0, requires_review: true },
        declaration_items: [{
          document_id: 'DOC-770', document_type: 'MODELLO_770', filing_year: 2025,
          filename: '770_2025.pdf', relation_state: 'CONFERMATA_NOME_UNIVOCO_E_INDICE_VERIFICATO',
          field_check_status: 'PRONTO_PER_VERIFICA_CAMPI',
        }],
      } });
      return Promise.resolve({ data: { items: [] } });
    });
  });

  it('mostra conteggi e dichiarazioni usando esclusivamente Drive', async () => {
    render(<MemoryRouter initialEntries={['/situazione-fiscale/dichiarazioni']}><SituazioneFiscale /></MemoryRouter>);

    expect(await screen.findByText('770_2026.pdf')).toBeInTheDocument();
    expect(screen.getAllByText('320')).toHaveLength(2);
    expect(screen.getByText('1297')).toBeInTheDocument();
    expect(screen.getByText('973')).toBeInTheDocument();
    expect(screen.getByText('60')).toBeInTheDocument();
    expect(screen.getByText((_content, node) => node?.textContent === 'Archivio canonico: Google Drive · indice 1')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Apri originale Drive' })).toBeEnabled();
  });

  it('mostra i tributi documentati dalle quietanze Drive senza inventare la verifica bancaria', async () => {
    api.get.mockImplementation(path => {
      if (path === '/api/fiscal/summary') return Promise.resolve({ data: {
        counts: {}, drive_index: { available: true, counts: { documentary_payment_documents: 320 } },
      } });
      if (path.includes('/api/fiscal/obligations')) return Promise.resolve({ data: {
        items: [{
          id: 'drive-paid-1', document_id: 'DOC-Q', source_kind: 'DRIVE_EXCEL_INDEX_F24_ROW',
          tax_code: '1001', description: 'Ritenute su retribuzioni', reference_period: '10/2024',
          debit_amount: 1455.21, credit_amount: 0, payment_date: '2024-11-18',
          filename: 'quietanza.pdf', protocol: '24111809324228190',
          payment_status: 'DOCUMENTATO_DA_QUIETANZA',
          documentary_payment_status: 'QUIETANZA_PRESENTE', bank_status: 'DA_VERIFICARE',
        }, {
          id: 'drive-paid-2', document_id: 'DOC-Q', source_kind: 'DRIVE_EXCEL_INDEX_F24_ROW',
          tax_code: '3802', description: 'Addizionale regionale IRPEF', reference_period: '10/2024',
          debit_amount: 44.79, credit_amount: 0, payment_date: '2024-11-18',
          filename: 'quietanza.pdf', protocol: '24111809324228190',
          payment_status: 'DOCUMENTATO_DA_QUIETANZA',
          documentary_payment_status: 'QUIETANZA_PRESENTE', bank_status: 'DA_VERIFICARE',
        }],
        sources: { drive_excel_index: 1, canonical: 'google_drive' },
      } });
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
    expect(screen.getAllByRole('button', { name: 'Apri PDF Drive' })).toHaveLength(1);
    fireEvent.change(screen.getByLabelText('Cerca nella sezione'), { target: { value: 'inesistente' } });
    expect(screen.getByText('Nessun risultato con questi filtri.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Azzera filtri' }));
    expect(screen.getByText(/Ritenute su retribuzioni/)).toBeInTheDocument();
  });

  it('non dipende dal vecchio servizio di revisione', async () => {
    api.get.mockImplementation(path => {
      if (path === '/api/fiscal/summary') return Promise.resolve({ data: {
        counts: {}, drive_index: { available: true, counts: { declarations: 60 } },
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
    expect(screen.getByText(/Il solo importo non conferma mai un collegamento/)).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith('/api/fiscal/source-certainty');

    fireEvent.click(screen.getByRole('button', { name: 'Verifica campi e F24' }));
    expect(await screen.findByText('Pag. 7')).toBeInTheDocument();
    expect(screen.getByText(/446,57/)).toBeInTheDocument();
    expect(screen.getAllByText('CONCORDANTE')).toHaveLength(3);
    expect(api.get).toHaveBeenCalledWith('/api/fiscal/declarations/DOC-770/field-certainty');
  });

  it('mostra LIPE, crediti e confronto gestionale senza creare un falso F24', async () => {
    api.get.mockImplementation(path => {
      if (path === '/api/fiscal/summary') return Promise.resolve({ data: { drive_index: { available: true, counts: {} } } });
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
});
