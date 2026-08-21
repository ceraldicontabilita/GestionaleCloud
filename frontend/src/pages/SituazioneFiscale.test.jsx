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
      if (path.startsWith('/api/fiscal/declarations')) return Promise.resolve({ data: {
        items: [{
          id: 'DOC-770', document_id: 'DOC-770', source_kind: 'DRIVE_EXCEL_INDEX_DECLARATION',
          document_type: 'MODELLO_770', filing_year: 2026, tax_year: 2025,
          filename: '770_2026.pdf', f24_links: [],
        }],
        sources: { drive_excel_index: 1, canonical: 'google_drive' },
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
        }],
        sources: { drive_excel_index: 1, canonical: 'google_drive' },
      } });
      return Promise.resolve({ data: { items: [] } });
    });

    render(<MemoryRouter initialEntries={['/situazione-fiscale/tributi-pagati']}><SituazioneFiscale /></MemoryRouter>);

    expect(await screen.findByText(/Ritenute su retribuzioni/)).toBeInTheDocument();
    expect(screen.queryByText('drive-paid-1')).not.toBeInTheDocument();
    expect(screen.getByLabelText('Cerca nella sezione')).toBeInTheDocument();
    expect(screen.getByText('Quietanza documentale presente · riscontro bancario da verificare')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Apri PDF Drive' })).toBeEnabled();
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
});
