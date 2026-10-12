import React from 'react';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import api from '../api';
import DilazioniInps from './DilazioniInps';

vi.mock('../api', () => ({ default: { get: vi.fn() } }));

describe('Dilazioni INPS', () => {
  beforeEach(() => vi.clearAllMocks());

  it('mostra l istanza senza dichiararla accolta o pagata', async () => {
    api.get.mockResolvedValue({ data: {
      regola: "L'istanza non prova l'accoglimento; il piano non prova il pagamento; ogni rata richiede la sua quietanza.",
      sources: { istanze_dilazioni_inps: 1, dilazioni_inps: 0 },
      items: [{
        id: 'i1', rif: 'INPS.5100.21/11/2012.0258155', data_domanda: '2012-11-21',
        matricola: '5124776507', periodo_da: '03/2012', periodo_a: '10/2012',
        totale_richiesto_cents: 1426700, stato_richiesta: 'PRESENTATA_DA_VERIFICARE',
        periodi: [{ periodo: '03/2012', contributi_cents: 45000, sanzioni_cents: 0 }],
      }],
    } });
    render(<DilazioniInps />);
    expect(await screen.findByText('Istanza presentata · accoglimento da verificare')).toBeInTheDocument();
    expect(screen.getByText(/manca il provvedimento INPS di accoglimento/)).toBeInTheDocument();
    expect(screen.getByText(/14.267,00/)).toBeInTheDocument();
    expect(screen.queryByText(/^Pagata$/)).not.toBeInTheDocument();
  });

  it('mostra scadenze e pagamenti solo dal piano accolto e dalle quietanze', async () => {
    api.get.mockResolvedValue({ data: {
      sources: { istanze_dilazioni_inps: 1, dilazioni_inps: 1 },
      items: [{ id: 'i2', rif: 'INPS.5100.X', matricola: '5124776507',
        periodo_da: '03/2012', periodo_a: '10/2012', stato_richiesta: 'ACCOLTA',
        data_accoglimento: '2012-12-01', stato_piano: 'IN_CORSO', periodi: [],
        rate: [
          { numero: 1, scadenza: '2012-12-10', importo_cents: 10000, stato: 'PAGATA', data_pagamento: '2012-12-10' },
          { numero: 2, scadenza: '2013-01-10', importo_cents: 10000, stato: 'SCADUTA_NON_PAGATA' },
        ] }],
    } });
    render(<DilazioniInps />);
    expect(await screen.findByText('Rate del piano accolto')).toBeInTheDocument();
    expect(screen.getByText('Pagata con quietanza il 10/12/2012')).toBeInTheDocument();
    expect(screen.getByText('Scaduta · quietanza non trovata')).toBeInTheDocument();
  });
});
