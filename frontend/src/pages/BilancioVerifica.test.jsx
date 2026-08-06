import React from 'react';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import api from '../api';
import BilancioVerifica from './BilancioVerifica';

vi.mock('../api', () => ({
  default: { get: vi.fn() },
}));
vi.mock('../contexts/AnnoContext', () => ({
  useAnnoGlobale: () => ({ anno: 2026 }),
}));

const baseResponse = {
  conti: [
    {
      codice: '03.01.01',
      nome: 'Capitale sociale',
      tipo: 'patrimonio_netto',
      dare: 0,
      avere: 100,
      saldo_dare: 0,
      saldo_avere: 100,
      n_movimenti: 1,
    },
  ],
  totali: { dare: 100, avere: 100, saldo_dare: 100, saldo_avere: 100, sbilancio: 0 },
  quadratura: true,
  qualita_registro: {
    quadratura_totali: true,
    registro_valido: true,
    scritture_sbilanciate: 0,
    scritture_senza_righe: 0,
    righe_non_numeriche: 0,
    righe_senza_conto: 0,
  },
  completezza_registro: {
    scritture_registrate: 1,
    fatture_da_registrare: 0,
    corrispettivi_da_registrare: 0,
    documenti_da_registrare: 0,
    completo: true,
  },
  riepilogo: {
    n_conti: 1,
    n_conti_attivo: 0,
    n_conti_passivo: 0,
    n_conti_patrimonio_netto: 1,
    n_conti_ricavo: 0,
    n_conti_costo: 0,
  },
  data_generazione: '2026-08-06T00:00:00Z',
};

describe('BilancioVerifica', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockResolvedValue({ data: baseResponse });
  });

  it('mostra patrimonio netto e dichiara la fonte contabile unica', async () => {
    render(<BilancioVerifica />);

    expect(await screen.findByText(/1 PN/)).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Patrimonio netto' })).toBeInTheDocument();
    expect(screen.getByText('movimenti_contabili')).toBeInTheDocument();
    expect(screen.getByText(/non vengono sommati una seconda volta/)).toBeInTheDocument();
  });

  it('non presenta come quadrato un registro con anomalie compensate', async () => {
    api.get.mockResolvedValue({
      data: {
        ...baseResponse,
        quadratura: false,
        qualita_registro: {
          ...baseResponse.qualita_registro,
          registro_valido: false,
          scritture_sbilanciate: 2,
        },
        completezza_registro: { ...baseResponse.completezza_registro, completo: false },
      },
    });

    render(<BilancioVerifica />);

    expect(await screen.findByText(/2 scritture sbilanciate/)).toBeInTheDocument();
    expect(screen.getByText(/totali annuali coincidono solo per compensazione/)).toBeInTheDocument();
    expect(screen.getByText(/REGISTRO NON VALIDO/)).toBeInTheDocument();
  });

  it('rimuove i dati precedenti se il caricamento fallisce', async () => {
    api.get.mockRejectedValue(new Error('servizio non disponibile'));

    render(<BilancioVerifica />);

    expect(await screen.findByText(/Errore nel caricamento del bilancio di verifica/)).toBeInTheDocument();
    expect(screen.queryByText('Capitale sociale')).not.toBeInTheDocument();
  });
});
