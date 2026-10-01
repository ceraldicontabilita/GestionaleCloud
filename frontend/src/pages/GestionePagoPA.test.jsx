import React from 'react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import api from '../api';
import GestionePagoPA, { paymentAmountParts, paymentKindLabel } from './GestionePagoPA';

vi.mock('../api', () => ({
  default: { get: vi.fn(), post: vi.fn(), put: vi.fn() },
}));

describe('Ricevuta associata: link al movimento', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('apre il movimento in Riconciliazione Banca quando la ricevuta è associata', async () => {
    api.get.mockImplementation(url => {
      if (url === '/api/pagopa/stats') return Promise.resolve({ data: {} });
      if (url === '/api/pagopa/ricevute') {
        return Promise.resolve({
          data: [{
            id: 'ric-1', iuv: 'IUV1', data_pagamento: '2026-04-28',
            beneficiario: 'ADER', movimento_id: 'ec-42',
          }],
        });
      }
      return Promise.resolve({ data: {} });
    });

    render(<MemoryRouter><GestionePagoPA /></MemoryRouter>);

    const link = await screen.findByTestId('vedi-movimento-0');
    expect(link).toHaveAttribute('href', '/riconciliazione/banca?movimento=ec-42');
  });

  it('non mostra il link quando la ricevuta non è ancora associata', async () => {
    api.get.mockImplementation(url => {
      if (url === '/api/pagopa/stats') return Promise.resolve({ data: {} });
      if (url === '/api/pagopa/ricevute') {
        return Promise.resolve({
          data: [{ id: 'ric-2', iuv: 'IUV2', beneficiario: 'ADER', movimento_id: null }],
        });
      }
      return Promise.resolve({ data: {} });
    });

    render(<MemoryRouter><GestionePagoPA /></MemoryRouter>);

    await waitFor(() => expect(screen.getByText('Da Associare')).toBeInTheDocument());
    expect(screen.queryByTestId('vedi-movimento-0')).not.toBeInTheDocument();
  });
});

describe('Ricevuta: che cosa hai pagato', () => {
  it('salva la natura scelta dalla tendina e la mostra subito', async () => {
    api.get.mockImplementation(url => {
      if (url === '/api/pagopa/nature') {
        return Promise.resolve({ data: { nature: [
          { id: 'tributo', label: 'Tributo' }, { id: 'sanzione_interessi', label: 'Sanzione o interessi' },
        ] } });
      }
      if (url === '/api/pagopa/ricevute') {
        return Promise.resolve({ data: [{ id: 'ric-9', iuv: 'IUV9', beneficiario: 'ADER' }] });
      }
      return Promise.resolve({ data: {} });
    });
    api.put.mockResolvedValue({ data: { success: true } });

    render(<MemoryRouter><GestionePagoPA /></MemoryRouter>);

    const tendina = await screen.findByTestId('natura-ric-9');
    fireEvent.change(tendina, { target: { value: 'sanzione_interessi' } });

    await waitFor(() => expect(api.put).toHaveBeenCalledWith(
      '/api/pagopa/ricevute/ric-9/natura', { natura: 'sanzione_interessi' },
    ));
    await waitFor(() => expect(screen.getByTestId('natura-ric-9')).toHaveValue('sanzione_interessi'));
  });
});

describe('GestionePagoPA - semantica documentale', () => {
  it('distingue le famiglie CBILL, MAV, RAV e bollettino postale', () => {
    expect(paymentKindLabel('RICEVUTA_CBILL')).toBe('CBILL');
    expect(paymentKindLabel('RICEVUTA_MAV')).toBe('MAV');
    expect(paymentKindLabel('RICEVUTA_RAV')).toBe('RAV');
    expect(paymentKindLabel('RICEVUTA_BOLLETTINO_POSTALE')).toBe('Bollettino postale');
  });

  it('mostra separati importo obbligo, commissione e totale banca', () => {
    expect(paymentAmountParts({
      operation_amount: 126.68, fee_amount: 2.85, bank_debit_total: 129.53,
    })).toEqual({ operation: 126.68, fee: 2.85, bankTotal: 129.53 });
  });

  it('un importo assente resta assente, non diventa zero', () => {
    expect(paymentAmountParts({})).toEqual({ operation: null, fee: null, bankTotal: null });
  });
});
