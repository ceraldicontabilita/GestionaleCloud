import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import api from '../api';
import ChiusuraEsercizio from './ChiusuraEsercizio';

vi.mock('../api', () => ({ default: { get: vi.fn(), post: vi.fn() } }));
vi.mock('../contexts/AnnoContext', () => ({
  useAnnoGlobale: () => ({ anno: 2025 }),
}));
vi.mock('../components/ui/ConfirmDialog', () => ({
  useConfirm: () => vi.fn().mockResolvedValue(true),
}));

const verificaPronta = {
  anno: 2025,
  pronto_per_chiusura: true,
  punteggio_completezza: 100,
  problemi_bloccanti: [],
  avvisi: [],
  completamenti: ['Registro definitivo completo e quadrato'],
};

const bilancinoPronto = {
  anno: 2025,
  disponibile: true,
  fonte: 'movimenti_contabili',
  registro: {
    quadratura: true,
    completezza: { scritture_registrate: 24, documenti_da_registrare: 0 },
  },
  bilancino: {
    ricavi: { totale: 1000, conti: [{ codice: '04.01.02' }] },
    costi: { totale: 600, conti: [{ codice: '05.01.01' }] },
    risultato: { utile_perdita: 400, tipo: 'utile', margine_percentuale: 40 },
  },
};

function configuraApi({ verifica = verificaPronta, bilancino = bilancinoPronto } = {}) {
  api.get.mockImplementation(url => {
    if (url.includes('/stato/')) return Promise.resolve({ data: { anno: 2025, stato: 'aperto' } });
    if (url.includes('/verifica-preliminare/')) return Promise.resolve({ data: verifica });
    if (url.includes('/bilancino-verifica/')) return Promise.resolve({ data: bilancino });
    if (url.endsWith('/storico')) return Promise.resolve({ data: [] });
    return Promise.reject(new Error(`Endpoint inatteso: ${url}`));
  });
}

describe('ChiusuraEsercizio', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    configuraApi();
  });

  it('non abilita la chiusura senza la frase esatta', async () => {
    render(<ChiusuraEsercizio />);

    const button = await screen.findByTestId('chiudi-esercizio-button');
    expect(button).toBeDisabled();

    fireEvent.change(screen.getByTestId('conferma-chiusura-input'), {
      target: { value: 'CHIUDI 2025' },
    });
    expect(button).toBeEnabled();
  });

  it('mostra esplicitamente il bilancino non disponibile senza importi inventati', async () => {
    configuraApi({
      verifica: { ...verificaPronta, pronto_per_chiusura: false },
      bilancino: {
        anno: 2025,
        disponibile: false,
        motivo: 'Registro incompleto',
        registro: {
          quadratura: true,
          completezza: { scritture_registrate: 3, documenti_da_registrare: 18 },
        },
        bilancino: null,
      },
    });
    render(<ChiusuraEsercizio />);

    expect(await screen.findByTestId('bilancino-non-disponibile')).toHaveTextContent(
      'Registro incompleto'
    );
    expect(screen.getByTestId('bilancino-non-disponibile')).toHaveTextContent(
      'Documenti da registrare: 18'
    );
    expect(screen.getByTestId('chiudi-esercizio-button')).toBeDisabled();
  });
});
