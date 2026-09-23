/**
 * Le riparazioni una tantum esistevano solo come chiamate API: dal pannello
 * del titolare non erano lanciabili affatto. Qui si prova cio' che le rende
 * sicure una volta che un bottone c'e': **prima si conta, poi si scrive**, e
 * il conteggio non deve mai poter scrivere.
 */
import React from 'react';
import { render, screen, waitFor, fireEvent, act } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

import api from '../api';
import PannelloRiparazioni, { RIPARAZIONI } from './PannelloRiparazioni';

vi.mock('../api', async (importOriginal) => ({
  messaggioErrore: (await importOriginal()).messaggioErrore,
  default: { get: vi.fn(), post: vi.fn() },
}));

let confermaRisposta = true;
vi.mock('./ui/ConfirmDialog', () => ({
  useConfirm: () => vi.fn(async () => confermaRisposta),
}));

const clic = async (el) => { await act(async () => { fireEvent.click(el); }); };

const monta = () =>
  render(
    <MemoryRouter>
      <PannelloRiparazioni />
    </MemoryRouter>
  );

describe('Riparazioni una tantum', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    confermaRisposta = true;
  });

  it('ogni lavoro chiama il backend sotto /api (senza, la SPA rispondeva 405)', () => {
    RIPARAZIONI.forEach((l) => {
      expect(l.esegui.startsWith('/api/')).toBe(true);
      if (l.stato) expect(l.stato.startsWith('/api/')).toBe(true);
    });
  });

  it('elenca tutti i lavori, col pregresso per primo', () => {
    monta();
    expect(RIPARAZIONI[0].id).toBe('pregresso');
    RIPARAZIONI.forEach((l) => {
      expect(screen.getByText(l.titolo)).toBeInTheDocument();
    });
  });

  it('«Esegui» nasce spento: senza contare non si scrive', () => {
    monta();
    screen.getAllByRole('button', { name: /Esegui/i }).forEach((b) => {
      expect(b).toBeDisabled();
    });
  });

  it('«Conta» chiama sempre in dry_run', async () => {
    api.post.mockResolvedValue({ data: { dry_run: true, candidate: 296 } });
    monta();

    await clic(screen.getAllByRole('button', { name: /Conta/i })[0]);

    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1));
    expect(api.post.mock.calls[0][0]).toContain('dry_run=true');
    expect(api.post.mock.calls[0][0]).toContain(RIPARAZIONI[0].esegui);
  });

  it('mostra i numeri del conteggio, cosi\' si decide guardandoli', async () => {
    api.post.mockResolvedValue({ data: { dry_run: true, candidate: 296 } });
    monta();

    await clic(screen.getAllByRole('button', { name: /Conta/i })[0]);

    await waitFor(() =>
      expect(screen.getByTestId('esito-pregresso')).toHaveTextContent('296')
    );
  });

  it('dopo il conteggio «Esegui» si accende e scrive con dry_run=false', async () => {
    api.post.mockResolvedValue({ data: { dry_run: true, candidate: 296 } });
    monta();

    await clic(screen.getAllByRole('button', { name: /Conta/i })[0]);
    const esegui = screen.getAllByRole('button', { name: /Esegui/i })[0];
    await waitFor(() => expect(esegui).toBeEnabled());

    api.post.mockResolvedValue({ data: { avviato: true } });
    await clic(esegui);

    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(2));
    expect(api.post.mock.calls[1][0]).toContain('dry_run=false');
  });

  it('se la conferma viene annullata non parte nessuna scrittura', async () => {
    api.post.mockResolvedValue({ data: { dry_run: true, candidate: 296 } });
    monta();

    await clic(screen.getAllByRole('button', { name: /Conta/i })[0]);
    const esegui = screen.getAllByRole('button', { name: /Esegui/i })[0];
    await waitFor(() => expect(esegui).toBeEnabled());

    confermaRisposta = false;
    await clic(esegui);

    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1));
  });

  it('un conteggio fallito lascia «Esegui» spento', async () => {
    api.post.mockRejectedValue({ response: { data: { detail: 'Authentication required' } } });
    monta();

    await clic(screen.getAllByRole('button', { name: /Conta/i })[0]);

    await waitFor(() =>
      expect(screen.getByTestId('esito-pregresso')).toHaveTextContent(
        'Authentication required'
      )
    );
    expect(screen.getAllByRole('button', { name: /Esegui/i })[0]).toBeDisabled();
  });

  it('ogni lavoro ha il suo bottone: nessuno resta senza', () => {
    monta();
    expect(screen.getAllByRole('button', { name: /Conta/i })).toHaveLength(
      RIPARAZIONI.length
    );
  });

  it('l\'ordine obbligato fra pregresso e registrazione e\' scritto a schermo', () => {
    monta();
    // Compare due volte: come titolo del secondo lavoro e come avvertenza
    // sul primo. E' l'avvertenza che conta: dice l'ordine.
    expect(screen.getByText(/Dopo questo, lancia/)).toBeInTheDocument();
    expect(screen.getAllByText(/Registra il pregresso/).length).toBeGreaterThan(1);
  });
});
