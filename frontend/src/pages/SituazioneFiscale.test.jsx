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
});
