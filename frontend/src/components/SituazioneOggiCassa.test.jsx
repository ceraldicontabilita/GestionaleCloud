import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

import api from '../api';
import SituazioneOggiCassa from './SituazioneOggiCassa';

vi.mock('../api', () => ({
  default: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

function monta(giorno = '2026-09-23') {
  return render(
    <MemoryRouter>
      <SituazioneOggiCassa giorno={giorno} />
    </MemoryRouter>,
  );
}

describe('SituazioneOggiCassa',
  () => {
    beforeEach(() => vi.clearAllMocks());

    it('legge solo /api/prima-nota/cassa del giorno e mostra i totali', async () => {
      api.get.mockResolvedValue({
        data: {
          saldo: 70,
          movimenti: [
            { data: '2026-09-23', tipo: 'entrata', categoria: 'Corrispettivi', importo: 100 },
            { data: '2026-09-23', tipo: 'uscita', categoria: 'POS Verso Banca', importo: 30 },
            { data: '2026-09-22', tipo: 'entrata', categoria: 'Corrispettivi', importo: 999 },
          ],
        },
      });

      monta('2026-09-23');

      await waitFor(() => expect(api.get).toHaveBeenCalledTimes(1));
      expect(api.get).toHaveBeenCalledWith(
        '/api/prima-nota/cassa?anno=2026&data_da=2026-09-23&data_a=2026-09-23&limit=500',
      );
      expect(api.post).not.toHaveBeenCalled();
      expect(api.put).not.toHaveBeenCalled();
      expect(api.delete).not.toHaveBeenCalled();

      const blocco = await screen.findByTestId('situazione-oggi');
      await waitFor(() => expect(blocco).toHaveTextContent('Cassa di oggi'));
      expect(blocco).toHaveTextContent('Corrispettivi');
      expect(blocco).toHaveTextContent('POS verso banca');
      expect(screen.getByRole('link', { name: 'Apri registro' })).toHaveAttribute(
        'href',
        '/prima-nota#sezione=cassa',
      );
    });

    it('con lista vuota resta a zero e non inventa movimenti', async () => {
      api.get.mockResolvedValue({ data: { movimenti: [], saldo: 0 } });
      monta('2026-09-23');
      const blocco = await screen.findByTestId('situazione-oggi');
      await waitFor(() => expect(blocco).toHaveTextContent('Cassa di oggi'));
      expect(api.post).not.toHaveBeenCalled();
    });

    it('se la cassa non risponde mostra l\'errore e non scrive', async () => {
      api.get.mockRejectedValue({ response: { data: { detail: 'Cassa non disponibile' } } });
      monta('2026-09-23');
      expect(await screen.findByRole('alert')).toHaveTextContent('Cassa non disponibile');
      expect(api.post).not.toHaveBeenCalled();
    });
  });
