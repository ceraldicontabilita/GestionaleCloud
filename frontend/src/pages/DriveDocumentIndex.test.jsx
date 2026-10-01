import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import api from '../api';
import DriveDocumentIndex from './DriveDocumentIndex';

vi.mock('../api', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}));
vi.mock('../components/DocumentViewerModal', () => ({
  default: ({ title, fetchUrl, onClose }) => (
    <div data-testid="viewer-finto" data-url={fetchUrl}>{title}<button onClick={onClose}>chiudi</button></div>
  ),
}));

const documento = {
  document_id: 'DRIVE-A', subject: 'Pane Giuseppina', year: '2023',
  display_title: 'Domanda Rottamazione-quater', document_type_label: 'Definizione agevolata AdeR',
  filename: 'PNAGPP58D48F839K_R-DA-2023.pdf', summary: 'Richiesta presentata ad AdeR',
  status: 'VERIFICATO', drive_path: 'CARTELLE ESATTORIALI/file.pdf',
};

describe('Archivio Drive: solo il protocollo vivo, originale dall endpoint unico', () => {
  const renderIndex = (route = '/documenti/drive') => render(
    <MemoryRouter initialEntries={[route]}>
      <Routes>
        <Route path="/documenti/drive" element={<DriveDocumentIndex />} />
        <Route path="/noleggio/verbali" element={<div>Sezione Verbali Noleggio</div>} />
      </Routes>
    </MemoryRouter>
  );
  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockImplementation(url => {
      if (url.endsWith('/status')) return Promise.resolve({ data: { documents: 941 } });
      if (url.endsWith('/search')) return Promise.resolve({ data: { results: [documento] } });
      return Promise.resolve({ data: {} });
    });
  });

  it('non legge piu l indice Excel: F24 e dichiarazioni stanno in Situazione fiscale', async () => {
    renderIndex();
    expect(await screen.findByText('Pane Giuseppina')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /F24 e tributi/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /Dichiarazioni/i })).toBeNull();
    const chiamate = api.get.mock.calls.map(([url]) => url);
    expect(chiamate.some(url => url.includes('/drive/index/'))).toBe(false);
    expect(api.post).not.toHaveBeenCalled();
  });

  it('apre l originale per id Drive dall endpoint unico, mai un indirizzo Drive da fuori', async () => {
    const aperta = vi.spyOn(window, 'open').mockImplementation(() => null);
    renderIndex();
    fireEvent.click(await screen.findByRole('button', { name: /Apri originale/ }));
    expect(screen.getByTestId('viewer-finto')).toHaveAttribute('data-url', '/api/originale?drive_id=DRIVE-A');
    expect(aperta).not.toHaveBeenCalled();
    aperta.mockRestore();
  });

  it('mostra un errore esplicito quando l archivio Drive non e configurato', async () => {
    api.get.mockRejectedValue({ response: { data: { detail: 'Indice Drive non configurato' } } });
    renderIndex();
    expect(await screen.findAllByRole('alert')).not.toHaveLength(0);
    expect((await screen.findAllByRole('alert'))[0]).toHaveTextContent('Indice Drive non configurato');
  });

  it('apre una cartella cliccata come indice tabellare leggibile', async () => {
    renderIndex('/documenti/drive?folder=CARTELLE%20ESATTORIALI');
    expect(await screen.findByText(/Contenuto cartella:/)).toBeInTheDocument();
    expect(await screen.findByText('Pane Giuseppina')).toBeInTheDocument();
    expect(screen.getByText('Domanda Rottamazione-quater')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Correggi / associa' })).toBeInTheDocument();
  });

  it('manda i verbali alla sezione Noleggi senza interrogare gli indici Drive', async () => {
    renderIndex('/documenti/drive?folder=VERBALI%20AUTO');

    expect(await screen.findByText('Sezione Verbali Noleggio')).toBeInTheDocument();
    await waitFor(() => expect(api.get).not.toHaveBeenCalled());
  });
});
