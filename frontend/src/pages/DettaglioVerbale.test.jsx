import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import api from '../api';
import DettaglioVerbale from './DettaglioVerbale';

vi.mock('../api', () => ({ default: { get: vi.fn() } }));
vi.mock('react-router-dom', () => ({
  useParams: () => ({ numeroVerbale: 'V-TEST-001' }),
  useNavigate: () => vi.fn(),
}));
vi.mock('sonner', () => ({ toast: { error: vi.fn() } }));
vi.mock('../components/DocumentViewerModal', () => ({
  default: ({ title, onClose }) => (
    <div data-testid="verbale-viewer">
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

  it('apre nel viewer interno anche i PDF senza url nel payload dettaglio', async () => {
    api.get
      .mockResolvedValueOnce({
        data: {
          numero_verbale: 'V-TEST-001',
          pdf_disponibili: [
            { indice: 1, filename: 'quietanza-test.pdf', tipo: 'quietanza' },
          ],
        },
      })
      .mockResolvedValueOnce({
        data: { content_base64: 'JVBERi0xLjQ=' },
      });

    render(<DettaglioVerbale />);

    const open = await screen.findByTestId('open-verbale-pdf-1');
    fireEvent.click(open);

    await waitFor(() => {
      expect(api.get).toHaveBeenLastCalledWith(
        '/api/verbali-noleggio/pdf/V-TEST-001?indice=1'
      );
    });
    expect(await screen.findByTestId('verbale-viewer')).toHaveTextContent('quietanza-test.pdf');
    expect(URL.createObjectURL).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole('button', { name: 'Chiudi viewer' }));
    await waitFor(() => expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:verbale-test'));
  });
});
