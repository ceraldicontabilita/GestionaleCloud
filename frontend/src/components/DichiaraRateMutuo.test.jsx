import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import api from '../api';
import DichiaraRateMutuo from './DichiaraRateMutuo';

vi.mock('../api', () => ({ default: { post: vi.fn() } }));

const MUTUO = { mutuo_id: 'mutuo_905217466', tipo_finanziamento: 'MUTUO IMPRESA RETAIL', numero_delibera: '905217466' };
const ANTEPRIMA = {
  dry_run: true, numero_rate: 2, totale_cents: 200000, prima_scadenza: '2021-06-17',
  ultima_scadenza: '2026-01-17', di_cui_anno_attivo: 1, gia_provate: [2, 3], gia_pagate_sul_piano: [1],
  future_escluse: [6], frase_conferma: 'DICHIARO PAGATE 2 RATE',
};

describe('DichiaraRateMutuo', () => {
  beforeEach(() => {
    api.post.mockReset();
    api.post.mockResolvedValue({ data: { data: ANTEPRIMA } });
  });

  it('mostra prima l\'anteprima (dry_run) e non scrive senza conferma', async () => {
    render(<DichiaraRateMutuo mutuo={MUTUO} onChiudi={() => {}} />);
    await waitFor(() => expect(screen.getByTestId('dichiara-rate-anteprima').textContent).toContain('2 rate'));
    expect(api.post).toHaveBeenCalledTimes(1);
    expect(api.post.mock.calls[0][1].dry_run).toBe(true);
    expect(screen.getByTestId('dichiara-rate-anteprima').textContent).toContain('2 già provate');
  });

  it('la conferma forte invia la frase dell\'anteprima e ricarica', async () => {
    const onFatto = vi.fn();
    const onChiudi = vi.fn();
    render(<DichiaraRateMutuo mutuo={MUTUO} onChiudi={onChiudi} onFatto={onFatto} />);
    await waitFor(() => expect(screen.getByTestId('dichiara-rate-conferma')).not.toBeDisabled());
    api.post.mockResolvedValueOnce({ data: { data: { ...ANTEPRIMA, dry_run: false, dichiarate: 2 } } });
    fireEvent.click(screen.getByTestId('dichiara-rate-conferma'));
    await waitFor(() => expect(onFatto).toHaveBeenCalled());
    const corpo = api.post.mock.calls[1][1];
    expect(corpo.dry_run).toBe(false);
    expect(corpo.conferma).toBe('DICHIARO PAGATE 2 RATE');
    expect(corpo.motivo).toBe('estratti_precedenti_non_disponibili');
    expect(onChiudi).toHaveBeenCalled();
  });

  it('con «Altro» serve il testo prima di calcolare l\'anteprima', async () => {
    render(<DichiaraRateMutuo mutuo={MUTUO} onChiudi={() => {}} />);
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByText('Altro (scrivi tu)'));
    expect(screen.getByTestId('dichiara-rate-conferma')).toBeDisabled();
    expect(api.post).toHaveBeenCalledTimes(1);
  });
});
