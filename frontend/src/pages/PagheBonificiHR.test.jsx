import React from 'react';
import { fireEvent, render, screen, cleanup } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import PagheBonificiPage from '../../../frontend_hr/src/PagheBonificiPage.jsx';
import { filtraPaghe } from '../../../frontend_hr/src/pagheView.js';

const year = new Date().getFullYear();
const rows = [
  { dipendente_id: 'a', dipendente: 'Persona corrente', anno: year, mese: 1, busta: 100.01,
    bonifico: 0, saldo: 100.01, stato: 'da_pagare', bonifici: [] },
  { dipendente_id: 'b', dipendente: 'Persona precedente', anno: year - 1, mese: 2, busta: 99.99,
    bonifico: 99.99, saldo: 0, stato: 'pagato', associato: true, bonifici: [] },
];
const Badge = ({ children }) => <span>{children}</span>;
const mount = () => render(<PagheBonificiPage Badge={Badge} notify={vi.fn()} />);

beforeEach(() => {
  sessionStorage.clear();
  vi.spyOn(axios, 'get').mockResolvedValue({ data: { righe: rows } });
  vi.spyOn(axios, 'post').mockResolvedValue({ data: {} });
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe('Cedolini HR già acquisiti', () => {
  it('cambia anno e torna indietro senza ulteriori richieste o import', async () => {
    mount();
    await screen.findByText('Persona corrente');
    fireEvent.change(screen.getByLabelText('Anno cedolini'), { target: { value: year - 1 } });
    expect(screen.getByText('Persona precedente')).toBeInTheDocument();
    expect(screen.queryByText('Persona corrente')).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Anno cedolini'), { target: { value: year } });
    expect(screen.getByText('Persona corrente')).toBeInTheDocument();
    expect(axios.get).toHaveBeenCalledTimes(1);
    expect(axios.post).not.toHaveBeenCalled();
  });

  it('conserva righe visibili se un aggiornamento fallisce', async () => {
    mount();
    await screen.findByText('Persona corrente');
    axios.get.mockRejectedValueOnce(new Error('offline'));
    fireEvent.click(screen.getByRole('button', { name: 'Aggiorna' }));
    await screen.findByRole('alert');
    expect(screen.getByText('Persona corrente')).toBeInTheDocument();
  });

  it('ricorda il periodo e offre un solo ingresso centrale di caricamento', async () => {
    sessionStorage.setItem('hr-paghe-filtri', JSON.stringify({ anno: year - 1, mese: 2, stato: '' }));
    mount();
    await screen.findByText('Persona precedente');
    expect(screen.getByRole('link', { name: 'Carica documenti' })).toHaveAttribute('href', '/documenti/import');
    expect(screen.queryByText(/Sincronizza da cedolini|Recupera bonifici storici|Importa bonifici da Drive/)).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Mese cedolini'), { target: { value: 1 } });
    expect(screen.getByText('Nessuna busta per il periodo selezionato.')).toBeInTheDocument();
    expect(axios.get).toHaveBeenCalledTimes(1);
  });

  it('aggiorna i riepiloghi sulle sole righe filtrate senza cambiare gli stati', () => {
    const result = filtraPaghe(rows, year, 0, 'da_pagare');
    expect(result.count).toBe(1);
    expect(result.totali).toMatchObject({ buste: 100.01, saldo: 100.01, pagati: 0, da_pagare: 1 });
    expect(rows[0].stato).toBe('da_pagare');
  });
});
