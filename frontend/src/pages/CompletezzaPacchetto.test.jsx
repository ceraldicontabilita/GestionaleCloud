import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { CompletezzaPacchetto } from './Commercialista.jsx';

describe('CompletezzaPacchetto', () => {
  it('dice cosa manca con parole, non solo colori', () => {
    render(<CompletezzaPacchetto esito={{
      dal: '2026-09-01', al: '2026-09-26', completo: false,
      rt: { mancanti: ['2026-09-19', '2026-09-20'], completo: false },
      fatture: { totale: 40, senza_originale: [{ id: 'x', numero: '12', fornitore: 'Alfa', data: '2026-09-03' }], completo: false },
      estratto_bpm: { movimenti: 30, primo: '2026-09-01', ultimo: '2026-09-12', completo: false },
    }} />);
    expect(screen.getByText('Pacchetto incompleto')).toBeTruthy();
    expect(screen.getByTestId('completezza-rt').textContent).toContain('19/09/2026, 20/09/2026');
    expect(screen.getByTestId('completezza-fatture').textContent).toContain('1 su 40 senza originale');
    expect(screen.getByTestId('completezza-estratto').textContent).toContain('Solo dal 01/09/2026 al 12/09/2026');
    expect(screen.getAllByText('Manca')).toHaveLength(3);
  });

  it('pacchetto completo', () => {
    render(<CompletezzaPacchetto esito={{
      dal: '2026-08-01', al: '2026-08-31', completo: true,
      rt: { mancanti: [], completo: true },
      fatture: { totale: 5, senza_originale: [], completo: true },
      estratto_bpm: { movimenti: 90, completo: true },
    }} />);
    expect(screen.getByText('Pacchetto completo')).toBeTruthy();
    expect(screen.getAllByText('Completo')).toHaveLength(3);
  });
});
