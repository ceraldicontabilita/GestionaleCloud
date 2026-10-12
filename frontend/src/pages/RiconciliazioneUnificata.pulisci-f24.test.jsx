import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi } from 'vitest';
import api from '../api';
import { TabellaAnalisiF24 } from './RiconciliazioneUnificata';
vi.mock('../api', () => ({ default: { get: vi.fn(), post: vi.fn() } }));

it('Pulisci F24 conserva entrambi i modelli finche il titolare conferma', async () => {
  const base = { periodo_competenza: '05/2026', codici_tributo: ['1001'], causali_inps: [],
    righe_tributo: [], tipo_versamento: 'ordinario', possibile_duplicazione: 'no', motivazione: 'Rivedere le versioni',
    documento_collegato: {}, ravvedimento_di: [] };
  api.get.mockResolvedValue({ data: { righe: [
    { ...base, f24_id: 'old', file: 'Maggio (2).pdf', saldo_cents: 1006622, stato_pagamento: 'importi_discordanti',
      verifica_importi_originale: { confronto_f24_id: 'paid', motivo: 'Versione discordante' } },
    { ...base, f24_id: 'paid', file: 'Maggio (3).pdf', saldo_cents: 813963, stato_pagamento: 'pagato',
      documento_collegato: { quietanza_url: '/api/originale/quietanza/q' } },
  ] } });
  api.post.mockResolvedValue({ data: { success: true } });
  render(<MemoryRouter><TabellaAnalisiF24 anno={2026} /></MemoryRouter>);
  await screen.findByTestId('pulisci-f24');
  expect(api.post).not.toHaveBeenCalled();
  fireEvent.click(screen.getByText('Pulisci F24 · versioni discordanti da controllare'));
  expect(screen.getByTestId('pulisci-f24')).toHaveTextContent('10.066,22');
  expect(screen.getByTestId('pulisci-f24')).toHaveTextContent(/8\.?139,63/);
  fireEvent.click(screen.getByRole('button', { name: 'Questo modello è superato' }));
  expect(api.post).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Annulla' }));
  expect(api.post).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Questo modello è superato' }));
  fireEvent.click(screen.getByRole('button', { name: 'Conferma modello superato' }));
  await waitFor(() => expect(api.post).toHaveBeenCalledOnce());
  expect(api.post.mock.calls[0][0]).toBe('/api/f24-riconciliazione/commercialista/old/escludi-versione');
  expect(api.post.mock.calls[0][1]).toMatchObject({ conferma: true, vigente_id: 'paid' });
});
