import React from 'react';
import { MemoryRouter } from 'react-router-dom';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../api', () => ({ default: { get: vi.fn(), post: vi.fn() } }));
import api from '../api';
import CollegaQuietanzaF24 from './CollegaQuietanzaF24';

const proposta = {
  f24_id: 'm1', file_name: 'modello agosto 2025.pdf', gia_collegato: false,
  motivi: { ravvedimento_stesso_tributo: 'Ravvedimento: stesso tributo e periodo', altro: 'Altro (scrivi tu)' },
  candidati: [{
    quietanza_id: 'q1', data: '2025-09-22', protocollo: '25092200000000001', saldo_cents: 710000,
    copertura: '3/3', pdf_url: '/api/originale/quietanza/q1', differenza_totale_cents: 1399,
    collegata_ad_altro_modello: [],
    righe_corrispondenti: [
      { codice: '1001', periodo: '07/2025', importo_modello_cents: 167601, importo_quietanza_cents: 168000, differenza_cents: 399 },
    ],
    righe_non_trovate: [],
  }],
};

describe('Quietanza trovata per tributo e periodo', () => {
  beforeEach(() => { api.get.mockReset(); api.post.mockReset(); });

  it('mostra modello e quietanza con le differenze e collega solo con un motivo', async () => {
    api.get.mockResolvedValue({ data: proposta });
    api.post.mockResolvedValue({ data: { collegato: true } });
    render(<MemoryRouter><CollegaQuietanzaF24 f24Id="m1" /></MemoryRouter>);
    expect(await screen.findByTestId('quietanza-candidata')).toBeInTheDocument();
    expect(screen.getByText('Apri il modello F24')).toBeInTheDocument();       // i due originali, a portata di clic
    expect(screen.getByText('Apri la quietanza trovata')).toBeInTheDocument();
    expect(screen.getByTestId('righe-candidata')).toHaveTextContent('1001');
    fireEvent.click(screen.getByTestId('collega-q1'));
    expect(screen.getByTestId('conferma-collegamento-q1')).toBeDisabled();       // senza motivo non si conferma
    fireEvent.click(screen.getByTestId('motivo-collegamento-ravvedimento_stesso_tributo'));
    fireEvent.click(screen.getByTestId('conferma-collegamento-q1'));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      '/api/f24-riconciliazione/modello/m1/quietanze-candidate/conferma',
      { quietanza_id: 'q1', motivo: 'ravvedimento_stesso_tributo', motivo_testo: undefined },
    ));
  });

  it('senza candidate lo dice, senza inventare', async () => {
    api.get.mockResolvedValue({ data: { ...proposta, candidati: [] } });
    render(<MemoryRouter><CollegaQuietanzaF24 f24Id="m1" /></MemoryRouter>);
    expect(await screen.findByTestId('candidate-vuote')).toBeInTheDocument();
  });
});
