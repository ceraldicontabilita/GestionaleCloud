import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import api from '../api';
import LibroGiornale from './LibroGiornale';

vi.mock('../api', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}));
vi.mock('../contexts/AnnoContext', () => ({
  useAnnoGlobale: () => ({ anno: 2026 }),
}));
vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}));

const giornale = {
  totale: 1,
  totale_disponibile: 1,
  troncato: false,
  totale_dare: 84,
  totale_avere: 84,
  quadratura: true,
  qualita_registro: {
    registro_valido: true,
    scritture_sbilanciate: 0,
    protocolli_duplicati: 0,
    scritture_senza_protocollo: 0,
    righe_non_numeriche: 0,
    righe_senza_conto: 0,
  },
  scritture: [{
    id: 's1', numero_registrazione: 1, data: '2026-01-02', tipo: 'fattura',
    descrizione: 'Registrazione test', totale_dare: 84, totale_avere: 84, righe: [],
  }],
};

const mastro = {
  totale_conti: 1,
  totale_dare: 84,
  totale_avere: 84,
  quadratura: true,
  mastrini: [],
};

function mockResponses({ controlloFallisce = false } = {}) {
  api.get.mockImplementation(url => {
    if (url.includes('/libro-giornale?')) return Promise.resolve({ data: giornale });
    if (url.includes('/libro-mastro?')) return Promise.resolve({ data: mastro });
    if (url.endsWith('/controllo-60-giorni')) {
      return controlloFallisce
        ? Promise.reject(new Error('controllo non disponibile'))
        : Promise.resolve({ data: { conforme: true } });
    }
    return Promise.reject(new Error(`Chiamata inattesa: ${url}`));
  });
}

describe('LibroGiornale', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockResponses();
    window.confirm = vi.fn(() => false);
  });

  it('mostra il registro anche se il controllo accessorio dei 60 giorni fallisce', async () => {
    mockResponses({ controlloFallisce: true });

    render(<LibroGiornale />);

    expect(await screen.findByText('1 scritture')).toBeInTheDocument();
    expect(screen.getByText('Registrazione test')).toBeInTheDocument();
  });

  it('mostra un errore esplicito senza dati obsoleti se Giornale o Mastro falliscono', async () => {
    api.get.mockRejectedValue(new Error('servizio non disponibile'));

    render(<LibroGiornale />);

    expect(await screen.findByText(/Impossibile caricare Libro Giornale e Libro Mastro/)).toBeInTheDocument();
    expect(screen.queryByText('Registrazione test')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Riprova' })).toBeInTheDocument();
  });

  it('segnala qualita non valida e vista troncata', async () => {
    api.get.mockImplementation(url => {
      if (url.includes('/libro-giornale?')) {
        return Promise.resolve({
          data: {
            ...giornale,
            troncato: true,
            totale_disponibile: 9,
            quadratura: false,
            qualita_registro: {
              ...giornale.qualita_registro,
              registro_valido: false,
              scritture_sbilanciate: 1,
            },
          },
        });
      }
      if (url.includes('/libro-mastro?')) return Promise.resolve({ data: mastro });
      return Promise.resolve({ data: { conforme: true } });
    });

    render(<LibroGiornale />);

    expect(await screen.findByText(/mostrate 1 scritture su 9/)).toBeInTheDocument();
    expect(screen.getByTestId('alert-qualita-giornale')).toHaveTextContent('1 scritture sbilanciate');
  });

  it('non espone il reimport dalla pagina del registro definitivo', async () => {
    render(<LibroGiornale />);
    await screen.findByText('1 scritture');
    expect(screen.queryByTestId('import-giornale')).not.toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });
});
