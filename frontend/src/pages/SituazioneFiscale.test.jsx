import React from 'react';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import api from '../api';
import SituazioneFiscale from './SituazioneFiscale';

vi.mock('../api', () => ({ default: { get: vi.fn(), post: vi.fn() } }));
vi.mock('../components/LinkedEvidencePanel', () => ({ default: () => <div>Prove collegate</div> }));

describe('Situazione fiscale collegata all indice Drive', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockImplementation(path => {
      if (path === '/api/fiscal/summary') return Promise.resolve({ data: {
        counts: { documents: 0, obligations: 0, payments: 0, collection_claims: 0, ader_snapshots: 0 },
        requires_review: 0,
        drive_index: { available: true, verified: true, counts: {
          f24_documents: 320, f24_rows: 1297, declarations: 60,
        } },
      } });
      if (path.startsWith('/api/fiscal/declarations')) return Promise.resolve({ data: {
        items: [{
          id: 'DOC-770', document_id: 'DOC-770', source_kind: 'DRIVE_EXCEL_INDEX_DECLARATION',
          document_type: 'MODELLO_770', filing_year: 2026, tax_year: 2025,
          filename: '770_2026.pdf', f24_links: [],
        }],
        sources: { drive_excel_index: 1, database: 0 },
      } });
      if (path === '/api/fiscal/review') return Promise.resolve({ data: { findings: [] } });
      return Promise.resolve({ data: { items: [] } });
    });
  });

  it('mostra conteggi Drive e dichiarazioni anche con Mongo transitorio vuoto', async () => {
    render(<MemoryRouter initialEntries={['/situazione-fiscale/dichiarazioni']}><SituazioneFiscale /></MemoryRouter>);

    expect(await screen.findByText('770_2026.pdf')).toBeInTheDocument();
    expect(screen.getByText('320')).toBeInTheDocument();
    expect(screen.getByText('1297')).toBeInTheDocument();
    expect(screen.getByText('60')).toBeInTheDocument();
    expect(screen.getByText((_content, node) => node?.textContent === 'Archivio canonico: Google Drive · indice 1')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Apri originale Drive' })).toBeEnabled();
  });

  it('mantiene la sezione utilizzabile quando i controlli di revisione rispondono 502', async () => {
    api.get.mockImplementation(path => {
      if (path === '/api/fiscal/summary') return Promise.resolve({ data: {
        counts: {}, drive_index: { available: true, counts: { declarations: 60 } },
      } });
      if (path === '/api/fiscal/review') return Promise.reject({ response: { status: 502 } });
      if (path.includes('/api/fiscal/obligations')) return Promise.resolve({ data: {
        items: [{ id: 'tributo-1', document_number: 'Tributo pagato verificato', payment_status: 'PAID_ON_TIME' }],
      } });
      return Promise.resolve({ data: { items: [] } });
    });

    render(<MemoryRouter initialEntries={['/situazione-fiscale/tributi-pagati']}><SituazioneFiscale /></MemoryRouter>);

    expect(await screen.findByText('Tributo pagato verificato')).toBeInTheDocument();
    expect(screen.getByText('Controlli di revisione temporaneamente non disponibili.')).toBeInTheDocument();
  });

  it('mantiene la sezione utilizzabile quando il riepilogo risponde 502', async () => {
    api.get.mockImplementation(path => {
      if (path === '/api/fiscal/summary') return Promise.reject({ response: { status: 502 } });
      if (path === '/api/fiscal/review') return Promise.resolve({ data: { findings: [] } });
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
