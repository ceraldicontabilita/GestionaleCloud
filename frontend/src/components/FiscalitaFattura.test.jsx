import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import FiscalitaFattura from './FiscalitaFattura';
import api from '../api';

const ruolo = vi.hoisted(() => ({ isAdmin: true }));
vi.mock('../contexts/AuthContext', () => ({ useAuth: () => ruolo }));
vi.mock('../api', () => ({ default: { get: vi.fn(), put: vi.fn() } }));
afterEach(cleanup);
const fattura = { id: 'f1', invoice_date: '2026-09-30', iva_detraibile: null,
  percentuale_detraibilita_iva: null, stato_detrazione_iva: 'DA_VERIFICARE' };
beforeEach(() => {
  vi.clearAllMocks(); ruolo.isAdmin = true;
  api.get.mockResolvedValue({ data: { fattura } });
});

describe('condizioni IVA documentate', () => {
  it('richiede documento e inerenza, converte percentuali in frazioni senza un attore client', async () => {
    api.put.mockResolvedValue({ data: { fattura: { ...fattura, iva_detraibile: 16.5, percentuale_detraibilita_iva: .75 }, iva_da_verificare: false } });
    render(<FiscalitaFattura fatturaId="f1" />);
    await screen.findByRole('button', { name: 'Conferma condizioni e ricalcola IVA' });
    expect(screen.getByLabelText('Acquisto inerente all’attività').value).toBe('');
    expect(screen.getByLabelText('Documento che prova l’uso').required).toBe(true);
    fireEvent.change(screen.getByLabelText('Acquisto inerente all’attività'), { target: { value: 'true' } });
    fireEvent.change(screen.getByLabelText('Documento che prova l’uso'), { target: { value: 'Contratto ufficio' } });
    fireEvent.change(screen.getByLabelText('Utilizzo aziendale telefonia (%)'), { target: { value: '75' } });
    fireEvent.change(screen.getByLabelText('Pro rata IVA'), { target: { value: 'true' } });
    fireEvent.change(screen.getByLabelText('Quota pro rata (%)'), { target: { value: '50' } });
    fireEvent.submit(screen.getByRole('button', { name: 'Conferma condizioni e ricalcola IVA' }).closest('form'));
    await waitFor(() => expect(api.put).toHaveBeenCalledOnce());
    expect(api.put.mock.calls[0][1].percentuale_utilizzo_aziendale).toBe(.75);
    expect(api.put.mock.calls[0][1].pro_rata).toBe(.5);
    expect(api.put.mock.calls[0][1]).not.toHaveProperty('confermato_da');
    expect(await screen.findByRole('status')).toHaveTextContent('Condizioni salvate e IVA ricalcolata');
  });

  it('mostra il40% documentato e distingue IVA da deducibilità70%', async () => {
    api.get.mockResolvedValue({ data: { fattura: { ...fattura, iva_detraibile: 8.8, percentuale_detraibilita_iva: .4 } } });
    render(<FiscalitaFattura fatturaId="f1" />);
    expect(await screen.findByText('40%')).toBeTruthy();
    expect(screen.getByText(/il 70% riguarda il costo deducibile/)).toBeTruthy();
  });

  it('normalizza anche una percentuale storica100 senza mostrare10000%', async () => {
    api.get.mockResolvedValue({ data: { fattura: { ...fattura, iva_detraibile: 22, percentuale_detraibilita_iva: 100 } } });
    render(<FiscalitaFattura fatturaId="f1" />);
    expect(await screen.findByText('100%')).toBeTruthy();
    expect(screen.queryByText('10000%')).toBeNull();
  });

  it('lettura e IVA utilizzata non presentano il modulo di conferma', async () => {
    ruolo.isAdmin = false;
    const { unmount } = render(<FiscalitaFattura fatturaId="f1" />);
    await screen.findByText(/richiede un amministratore/);
    expect(screen.queryByRole('button', { name: 'Conferma condizioni e ricalcola IVA' })).toBeNull();
    unmount(); ruolo.isAdmin = true;
    api.get.mockResolvedValue({ data: { fattura: { ...fattura, iva_utilizzata: true } } });
    render(<FiscalitaFattura fatturaId="f1" />);
    await screen.findByText(/occorre la riapertura della liquidazione/);
    expect(screen.queryByRole('button', { name: 'Conferma condizioni e ricalcola IVA' })).toBeNull();
  });
});
