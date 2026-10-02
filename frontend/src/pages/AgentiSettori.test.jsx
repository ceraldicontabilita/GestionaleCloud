import React from 'react';
import { MemoryRouter } from 'react-router-dom';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import api from '../api';
import AgentiSettori, { numeroOppure } from './AgentiSettori';

vi.mock('../api', () => ({ default: { get: vi.fn(), post: vi.fn(), put: vi.fn() } }));

const SETTORI = {
  agenti_ai: {
    attivo: true, chiave_presente: false, tetto: 200, chiamate_oggi: 3, ultimo_giro: '2026-10-02T06:11:00+00:00',
    non_riconosciuti_errori: 12, inbox_non_classificata: null, arretrato: 40, ultimo_esito: { motivo: 'ANTHROPIC_API_KEY non configurata' },
  },
  settori: [
    {
      id: 'f24', nome: 'F24 e tributi',
      giri: [{ chiave: 'riconciliazione_ultimo_giro', etichetta: 'Riconciliazione (30 min)', at: '2026-10-02T05:30:00+00:00', conteggi: { associati: 4 }, errore: null, mai_eseguito: false }],
      code_ferme: [
        { nome: 'File in ERRORI su Drive', conteggio: 175, rotta_pagina: '/documenti/drive', motivo: 'riconosciuti ma non registrati' },
        { nome: 'F24 non quadrati', conteggio: 54, rotta_pagina: '/documenti/drive', motivo: 'saldo stampato diverso dalle righe lette' },
      ],
      proposte_in_attesa: 2,
    },
    {
      id: 'cedolini', nome: 'Cedolini',
      giri: [{ chiave: 'cedolini_versioni', etichetta: 'Versioni della stessa busta', at: null, conteggi: {}, errore: null, mai_eseguito: true }],
      code_ferme: [{ nome: 'Buste senza netto verificato', conteggio: null, rotta_pagina: '/hr/', motivo: 'cella del netto vuota' }],
      proposte_in_attesa: 0,
    },
  ],
};

const PROPOSTE = [
  {
    id: 'prop_1', settore: 'f24', confidenza: 'alta', stato: 'proposta',
    documento: { origine: 'drive', drive_id: 'DRV1', nome: 'F24_marzo.pdf', sha256: 'a'.repeat(64) },
    proposta: { tipo_documento: 'quietanza_f24', campi: { data: '2026-03-16', importo_cents: 123456, codici_tributo: ['6002'] }, confidenza: 'alta', prove: ['QUIETANZA F24'], motivo: 'intestazione di quietanza' },
  },
  {
    id: 'prop_2', settore: 'f24', confidenza: 'bassa', stato: 'proposta',
    documento: { origine: 'inbox', inbox_id: 'upload_1', nome: 'scansione.pdf', sha256: 'b'.repeat(64) },
    proposta: { tipo_documento: 'non_riconosciuto', campi: {}, confidenza: 'bassa', prove: [], motivo: 'pagina bianca' },
  },
];

function rispostaGet(url) {
  if (url.includes('/api/agenti/settori')) return Promise.resolve({ data: SETTORI });
  if (url.includes('/api/agenti/proposte')) return Promise.resolve({ data: { proposte: PROPOSTE } });
  return Promise.resolve({ data: {} });
}

function monta() {
  return render(<MemoryRouter><AgentiSettori onMessaggio={() => {}} /></MemoryRouter>);
}

describe('Scheda Settori del cruscotto Agenti', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockImplementation(rispostaGet);
    api.post.mockResolvedValue({ data: { gia_decisa: false, esito: { success: true } } });
  });

  it('un numero che manca e\' «Dato non disponibile», mai zero', () => {
    expect(numeroOppure(null)).toBe('Dato non disponibile');
    expect(numeroOppure(undefined)).toBe('Dato non disponibile');
    expect(numeroOppure(0)).toBe('0');
  });

  it('mostra una card per settore con giri, code ferme col link e lo stato dell\'agente AI', async () => {
    monta();
    expect(await screen.findByTestId('settore-f24')).toBeInTheDocument();
    expect(screen.getByText('F24 non quadrati')).toBeInTheDocument();
    expect(screen.getByText('54')).toBeInTheDocument();
    expect(screen.getByText('F24 non quadrati').closest('a')).toHaveAttribute('href', '/documenti/drive');
    expect(screen.getByText(/associati 4/)).toBeInTheDocument();
    // cedolini: conteggio assente e giro mai eseguito
    const cedolini = screen.getByTestId('settore-cedolini');
    expect(cedolini).toHaveTextContent('Dato non disponibile');
    expect(cedolini).toHaveTextContent('mai eseguito');
    expect(cedolini.querySelector('a[href="/hr/"]')).not.toBeNull();
    // riquadro agente: senza chiave lo dice
    const riquadro = screen.getByTestId('riquadro-agenti-ai');
    expect(riquadro).toHaveTextContent('Senza chiave');
    expect(riquadro).toHaveTextContent('Chiamate oggi: 3 su 200');
    expect(riquadro).toHaveTextContent('Inbox senza categoria: Dato non disponibile');
  });

  it('le proposte: Vedi apre l\'originale, Conferma chiama il motore, non riconosciuta non si conferma', async () => {
    monta();
    const card = await screen.findByTestId('proposta-prop_1');
    expect(card).toHaveTextContent('quietanza f24');
    expect(card).toHaveTextContent('1.234,56');
    expect(screen.getByTestId('vedi-prop_1')).toBeInTheDocument();
    expect(screen.getByTestId('conferma-prop_2')).toBeDisabled();

    fireEvent.click(screen.getByTestId('conferma-prop_1'));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/agenti/proposte/prop_1/conferma'));
  });

  it('il rifiuto chiede un motivo a chip e «altro» vuole il testo', async () => {
    monta();
    await screen.findByTestId('proposta-prop_2');
    fireEvent.click(screen.getByTestId('rifiuta-prop_2'));
    const conferma = screen.getByTestId('conferma-rifiuto-prop_2');
    expect(conferma).toBeDisabled();
    fireEvent.click(screen.getByTestId('motivo-prop_2-altro'));
    expect(conferma).toBeDisabled();
    fireEvent.click(screen.getByTestId('motivo-prop_2-doppione'));
    expect(conferma).not.toBeDisabled();
    fireEvent.click(conferma);
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/agenti/proposte/prop_2/rifiuta', { motivo: 'doppione', nota: '' }));
  });

  it('«Conferma tutte le sicure» conta solo la confidenza alta del settore', async () => {
    monta();
    const bottone = await screen.findByTestId('conferma-sicure-f24');
    expect(bottone).toHaveTextContent('(1)');
    fireEvent.click(bottone);
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/agenti/proposte/conferma-sicure?settore=f24'));
  });
});
