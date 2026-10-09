import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

vi.mock('../api', () => ({ default: { get: vi.fn(), post: vi.fn() } }));

import api from '../api';
import ConfermaAddebitoF24 from './ConfermaAddebitoF24';

const MOTIVI = {
  unico_addebito_compatibile: 'È l\'unico addebito di delega compatibile per data e importo',
  altro: 'Altro (scrivi tu)',
};
const CANDIDATI = [
  { movimento_id: 'm1', data: '2026-01-16', importo: 500 },
  { movimento_id: 'm2', data: '2026-01-16', importo: 500 },
];

describe('Conferma questo addebito', () => {
  it('non compare su un certo', () => {
    const { container } = render(<ConfermaAddebitoF24 f24Id="f1" livello="CERTO" candidati={CANDIDATI} motivi={MOTIVI} />);
    expect(container.innerHTML).toBe('');
  });

  it('sceglie candidato e motivo a chip, poi scrive sul backend e ricarica', async () => {
    api.post.mockResolvedValueOnce({ data: { livello: 'PROBABILE' } });
    const onConfermato = vi.fn();
    render(<ConfermaAddebitoF24 f24Id="f1" livello="PROBABILE" candidati={CANDIDATI} motivi={MOTIVI} onConfermato={onConfermato} />);

    fireEvent.click(screen.getByTestId('conferma-addebito-f1'));
    const invia = screen.getByTestId('conferma-invia-f1');
    expect(invia.disabled).toBe(true);
    fireEvent.click(screen.getByTestId('candidato-m2'));
    fireEvent.click(screen.getByTestId('motivo-unico_addebito_compatibile'));
    expect(invia.disabled).toBe(false);
    fireEvent.click(invia);

    await waitFor(() => expect(onConfermato).toHaveBeenCalled());
    expect(api.post).toHaveBeenCalledWith('/api/f24-riconciliazione/quietanze-banca/f1/conferma', {
      movimento_id: 'm2', motivo: 'unico_addebito_compatibile', motivo_testo: undefined,
    });
  });

  it('«altro» vuole il testo e un 409 si legge', async () => {
    api.post.mockRejectedValueOnce({ response: { data: { code: 'MOVIMENTO_NON_CANDIDATO', message: 'Non candidato' } } });
    render(<ConfermaAddebitoF24 f24Id="q1" livello="PARZIALE" candidati={[CANDIDATI[0]]} motivi={MOTIVI} />);
    fireEvent.click(screen.getByTestId('conferma-addebito-q1'));
    expect(screen.getByText(/nessun conguaglio/)).toBeTruthy();
    fireEvent.click(screen.getByTestId('motivo-altro'));
    const invia = screen.getByTestId('conferma-invia-q1');
    expect(invia.disabled).toBe(true);
    fireEvent.change(screen.getByTestId('motivo-testo-q1'), { target: { value: 'Visto sul cartaceo' } });
    expect(invia.disabled).toBe(false);
    fireEvent.click(invia);
    await waitFor(() => expect(screen.getByRole('alert').textContent).toBe('Non candidato'));
    expect(api.post).toHaveBeenLastCalledWith('/api/f24-riconciliazione/quietanze-banca/q1/conferma', {
      movimento_id: 'm1', motivo: 'altro', motivo_testo: 'Visto sul cartaceo',
    });
  });
});
