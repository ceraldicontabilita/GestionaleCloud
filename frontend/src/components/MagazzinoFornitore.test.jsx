import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import api from '../api';
import MagazzinoFornitore, { descriviDecisione } from './MagazzinoFornitore';

vi.mock('../api', () => ({ default: { get: vi.fn(), put: vi.fn() } }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const fornitore = {
  id: 381,
  ragione_sociale: 'BIG FOOD SRL',
  esclude_magazzino: false,
  magazzino_origine: 'non_deciso',
};

const anteprimaEsclusione = {
  escludi: true,
  gia_cosi: false,
  fatture_contabili: 21,
  fatture_in_lotti: 4,
  lotti_creati: 12,
  lotti_con_giacenza: 3,
  fatture_da_prendere: 0,
  effetto: ['Le 21 fatture restano contabili: IVA, giornale e pagamenti non cambiano.'],
  motivi: [
    { id: 'servizi_utenze', etichetta: 'Servizi, utenze o noleggi (niente merce)' },
    { id: 'altro', etichetta: 'Altro (scrivi tu)' },
  ],
};

describe('Nel magazzino / fuori dal magazzino', () => {
  beforeEach(() => vi.clearAllMocks());

  it('lo stato non deciso si dice a parole e non e\' un «escluso»', () => {
    const d = descriviDecisione(fornitore);
    expect(d.escluso).toBe(false);
    expect(d.testo).toContain('nessuna scelta');
  });

  it('mostra motivo, data e chi ha deciso', () => {
    const d = descriviDecisione({
      esclude_magazzino: true,
      magazzino_origine: 'erp',
      magazzino_deciso_il: '2026-09-30T10:00:00+00:00',
      magazzino_motivo_testo: 'Consumo diretto, non passa dal magazzino',
      magazzino_deciso_da: 'titolare',
    });
    expect(d.testo).toBe('dal 30/09/2026 · Consumo diretto, non passa dal magazzino · titolare');
  });

  it('il tocco apre l\'anteprima coi numeri e non scrive finche\' non scegli il motivo', async () => {
    api.get.mockResolvedValue({ data: anteprimaEsclusione });
    render(<MagazzinoFornitore fornitore={fornitore} id={381} onFatto={vi.fn()} />);

    fireEvent.click(screen.getByTestId('magazzino-fuori-381'));

    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith('/api/suppliers/381/magazzino/anteprima', {
        params: { escludi: true },
      })
    );
    expect(await screen.findByText(/restano contabili/)).toBeInTheDocument();
    expect(screen.getByText('fatture in Lotti')).toBeInTheDocument();
    const conferma = screen.getByRole('button', { name: 'Escludi' });
    expect(conferma).toBeDisabled();
    expect(api.put).not.toHaveBeenCalled();
  });

  it('con un motivo scelto a chip salva e riporta lo stato nuovo', async () => {
    api.get.mockResolvedValue({ data: anteprimaEsclusione });
    api.put.mockResolvedValue({
      data: { supplier: { ...fornitore, esclude_magazzino: true }, fatture_accodate_a_lotti: 0 },
    });
    const onFatto = vi.fn();
    render(<MagazzinoFornitore fornitore={fornitore} id={381} onFatto={onFatto} />);

    fireEvent.click(screen.getByTestId('magazzino-fuori-381'));
    fireEvent.click(await screen.findByTestId('motivo-servizi_utenze'));
    fireEvent.click(screen.getByRole('button', { name: 'Escludi' }));

    await waitFor(() =>
      expect(api.put).toHaveBeenCalledWith('/api/suppliers/381/magazzino', {
        escludi: true,
        motivo: 'servizi_utenze',
        motivo_testo: '',
      })
    );
    await waitFor(() => expect(onFatto).toHaveBeenCalledWith(expect.objectContaining({ esclude_magazzino: true })));
  });

  it('«Altro» chiede il testo: senza, la conferma resta spenta', async () => {
    api.get.mockResolvedValue({ data: anteprimaEsclusione });
    render(<MagazzinoFornitore fornitore={fornitore} id={381} onFatto={vi.fn()} />);

    fireEvent.click(screen.getByTestId('magazzino-fuori-381'));
    fireEvent.click(await screen.findByTestId('motivo-altro'));
    expect(screen.getByRole('button', { name: 'Escludi' })).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Scrivi il motivo'), { target: { value: 'solo per prova' } });
    expect(screen.getByRole('button', { name: 'Escludi' })).not.toBeDisabled();
  });

  it('un fornitore fuori dal magazzino offre di rimetterlo dentro e dice quante fatture entrano', async () => {
    api.get.mockResolvedValue({
      data: {
        ...anteprimaEsclusione,
        escludi: false,
        fatture_da_prendere: 5,
        effetto: ['5 fatture ancora da prendere entrano in Lotti subito (quelle gia\' presenti non si duplicano).'],
        motivi: [{ id: 'escluso_per_errore', etichetta: 'Era escluso per errore' }],
      },
    });
    render(
      <MagazzinoFornitore
        fornitore={{ ...fornitore, esclude_magazzino: true, magazzino_origine: 'erp' }}
        id={381}
        onFatto={vi.fn()}
      />
    );

    expect(screen.getByTestId('magazzino-fuori-381')).toHaveAttribute('aria-checked', 'true');
    fireEvent.click(screen.getByTestId('magazzino-dentro-381'));
    expect(await screen.findByText(/5 fatture ancora da prendere/)).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith('/api/suppliers/381/magazzino/anteprima', {
      params: { escludi: false },
    });
  });
});
