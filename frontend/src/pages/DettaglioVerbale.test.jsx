import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import api from '../api';
import DettaglioVerbale from './DettaglioVerbale';

vi.mock('../api', () => ({ default: { get: vi.fn(), post: vi.fn() } }));
vi.mock('react-router-dom', async importOriginal => ({
  ...(await importOriginal()),
  useParams: () => ({ numeroVerbale: 'V-TEST-001' }),
  useNavigate: () => vi.fn(),
}));
vi.mock('../components/ModalFattura', () => ({
  default: ({ fatturaId, numero }) => <div data-testid="modal-fattura" data-id={fatturaId}>{numero}</div>,
}));
vi.mock('sonner', () => ({ toast: { error: vi.fn() } }));
vi.mock('../components/DocumentViewerModal', () => ({
  default: ({ title, fetchUrl, onClose }) => (
    <div data-testid="verbale-viewer" data-url={fetchUrl}>
      <span>{title}</span>
      <button type="button" onClick={onClose}>Chiudi viewer</button>
    </div>
  ),
}));

describe('DettaglioVerbale viewer PDF', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    URL.createObjectURL = vi.fn(() => 'blob:verbale-test');
    URL.revokeObjectURL = vi.fn();
  });

  it('apre nel viewer interno il PDF dall endpoint unico, senza passarlo dal payload', async () => {
    api.get.mockImplementation(url => {
      if (url === '/api/dipendenti') return Promise.resolve({ data: [] });
      return Promise.resolve({
        data: {
          numero_verbale: 'V-TEST-001',
          pdf_disponibili: [
            { indice: 1, filename: 'quietanza-test.pdf', tipo: 'quietanza' },
          ],
        },
      });
    });

    render(<DettaglioVerbale />);

    fireEvent.click(await screen.findByTestId('open-verbale-pdf-1'));

    const viewer = await screen.findByTestId('verbale-viewer');
    expect(viewer).toHaveTextContent('quietanza-test.pdf');
    expect(viewer).toHaveAttribute('data-url', '/api/originale/verbale/V-TEST-001?indice=1');
    expect(api.get).not.toHaveBeenCalledWith(expect.stringContaining('/api/verbali-noleggio/pdf/'));

    fireEvent.click(screen.getByRole('button', { name: 'Chiudi viewer' }));
    await waitFor(() => expect(screen.queryByTestId('verbale-viewer')).toBeNull());
  });

  it('mostra le azioni per associare e rileggere il PDF originale', async () => {
    api.get.mockImplementation(url => Promise.resolve({
      data: url === '/api/dipendenti' ? [] : {
        numero_verbale: 'V-TEST-001', targa: 'AB123CD', importo: 51.64,
        pdf_disponibili: [{ indice: 0, filename: 'verbale.pdf' }],
      },
    }));
    render(<DettaglioVerbale />);
    expect(await screen.findByRole('button', { name: 'Associa PDF verbale' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Rileggi importo dal PDF' })).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'Importo corretto dal PDF' })).toBeInTheDocument();
    expect(screen.getByText('Associazione targa e driver')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Modifica associazione driver' }));
    expect(await screen.findByRole('button', { name: 'Trova dalla fattura noleggio' })).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith('/api/dipendenti');
  });

  it('apre i documenti Drive collegati dal foglio con l endpoint unico per id Drive', async () => {
    api.get.mockImplementation(url => Promise.resolve({
      data: url === '/api/dipendenti' ? [] : {
        numero_verbale: 'V-TEST-001', pdf_disponibili: [],
        documenti_drive: [{ drive_id: '1AbCdEfGhIjKlMnOpQrStUv', tipo: 'bonifico', nome: 'Bonifico_12_11_2022.pdf' }],
      },
    }));
    render(<DettaglioVerbale />);
    expect(await screen.findByText('Documenti collegati (Drive)')).toBeInTheDocument();
    expect(screen.getByText('Bonifico_12_11_2022.pdf')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('apri-drive-1AbCdEfGhIjKlMnOpQrStUv'));
    expect((await screen.findByTestId('verbale-viewer')).getAttribute('data-url'))
      .toBe('/api/originale?drive_id=1AbCdEfGhIjKlMnOpQrStUv');
  });

  it('apre la fattura collegata al verbale', async () => {
    api.get.mockImplementation(url => Promise.resolve({
      data: url === '/api/dipendenti' ? [] : {
        numero_verbale: 'V-TEST-001', pdf_disponibili: [], fattura_id: 'f-77', fattura_numero: '0000202610615118',
      },
    }));
    render(<DettaglioVerbale />);
    expect(await screen.findByText('Fattura collegata')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('apri-fattura-collegata'));
    expect((await screen.findByTestId('modal-fattura')).getAttribute('data-id')).toBe('f-77');
  });

  it('mostra i documenti Drive nella casella del fascicolo del loro tipo', async () => {
    api.get.mockImplementation(url => Promise.resolve({
      data: url === '/api/dipendenti' ? [] : {
        numero_verbale: 'V-TEST-001', pdf_disponibili: [],
        fascicolo: {
          verbale: { presente: false, documento: null, documenti_drive: [] },
          notifica: { presente: false, documento: null, documenti_drive: [] },
          pagamento_banca: { presente: false },
          quietanza: { presente: true, documento: null, documenti_drive: [{ drive_id: '1QuietanzaAbCdEfGhIjKl', tipo: 'quietanza', nome: 'Attestazione.pdf' }] },
        },
      },
    }));
    render(<DettaglioVerbale />);
    expect(await screen.findByTestId('fascicolo-drive-1QuietanzaAbCdEfGhIjKl')).toBeInTheDocument();
  });
});
