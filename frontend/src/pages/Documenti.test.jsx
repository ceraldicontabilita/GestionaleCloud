import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import api from '../api';
import Documenti from './Documenti';

vi.mock('../api', () => ({ default: { get: vi.fn() } }));
vi.mock('../contexts/AnnoContext', () => ({
  useAnnoGlobale: () => ({ anno: 2026 }),
}));
vi.mock('../components/DocumentViewerModal', () => ({
  default: ({ title }) => <div data-testid="viewer">{title}</div>,
}));

const response = {
  documents: [
    {
      id: 'doc-1',
      filename: 'quietanza.pdf',
      category: 'quietanza',
      category_label: 'Quietanze',
      source_label: 'email',
      archive_date: '2026-07-10T10:00:00+00:00',
      size_bytes: 1234,
      status: 'processato',
      linked_to: 'quietanze_f24',
      anomalies: [],
    },
  ],
  total: 120,
  skip: 0,
  limit: 50,
  has_more: true,
  by_status: { nuovo: 5, processato: 114, errore: 1 },
  categories: { quietanza: 'Quietanze', f24: 'F24' },
};

const renderPage = () => render(
  <MemoryRouter>
    <Documenti />
  </MemoryRouter>
);

describe('Archivio documenti', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockResolvedValue({ data: response });
  });

  it('usa paginazione server e mostra provenienza e collegamento', async () => {
    renderPage();

    expect(await screen.findByText('quietanza.pdf')).toBeInTheDocument();
    expect(screen.getByText('Email')).toBeInTheDocument();
    expect(screen.getByText('Collegato a: quietanze f24')).toBeInTheDocument();
    expect(screen.getByText('Pagina 1 di 3 · 1–50 di 120')).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith(
      expect.stringContaining('/api/documenti/lista?anno=2026&limit=50&skip=0')
    );

    fireEvent.click(screen.getByRole('button', { name: 'Successiva' }));
    await waitFor(() => expect(api.get).toHaveBeenLastCalledWith(
      expect.stringContaining('skip=50')
    ));
  });

  it('non espone import, riclassificazione o cancellazione', async () => {
    renderPage();
    await screen.findByText('quietanza.pdf');

    expect(screen.queryByText('Scarica da Email')).not.toBeInTheDocument();
    expect(screen.queryByText('Carica documento fiscale')).not.toBeInTheDocument();
    expect(screen.queryByText('Elimina')).not.toBeInTheDocument();
    expect(screen.queryByTitle('Cambia categoria')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Vai a Carica documenti' })).toHaveAttribute(
      'href',
      '/documenti/import'
    );
  });

  it('mostra un errore reale e permette di riprovare', async () => {
    api.get.mockRejectedValueOnce({ response: { data: { detail: 'Database non disponibile' } } });
    renderPage();

    expect(await screen.findByRole('alert')).toHaveTextContent('Database non disponibile');
    expect(screen.getByRole('button', { name: 'Riprova' })).toBeInTheDocument();
  });
});
