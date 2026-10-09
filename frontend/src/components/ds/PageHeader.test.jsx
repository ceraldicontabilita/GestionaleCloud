import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { PageHeader } from './PageHeader';

describe('PageHeader', () => {
  it('senza pastiglie resta la testata di sempre', () => {
    render(<PageHeader title="Fornitori" subtitle="Anagrafiche" />);
    expect(screen.getByRole('heading', { name: 'Fornitori' })).toBeTruthy();
    expect(screen.queryByTestId('pastiglia')).toBeNull();
    expect(screen.queryByTestId('testata-famiglia')).toBeNull();
  });

  it('mostra famiglia, perché e pastiglie con etichetta, valore e nota', () => {
    render(
      <PageHeader
        title="Prima nota"
        subtitle="Ogni euro entrato o uscito."
        famiglia={{ titolo: 'IL REGISTRO', colore: '#3f5a4e' }}
        pastiglie={[
          { etichetta: 'Entrate 2026', valore: '€ 10,00', nota: 'Cassa, Dare' },
          { etichetta: 'Saldo Cassa', valore: '-€ 5,00', tono: 'male' },
        ]}
      />,
    );
    expect(screen.getByTestId('testata-famiglia').textContent).toBe('IL REGISTRO');
    expect(screen.getByText('Ogni euro entrato o uscito.')).toBeTruthy();
    const pastiglie = screen.getAllByTestId('pastiglia');
    expect(pastiglie).toHaveLength(2);
    expect(pastiglie[0].dataset.tono).toBe('neutro');
    expect(pastiglie[1].dataset.tono).toBe('male');
    expect(screen.getByText('Cassa, Dare')).toBeTruthy();
  });

  it("l'azione di una pastiglia è un bottone con nome e bersaglio di 44px", () => {
    const onClick = vi.fn();
    render(
      <PageHeader
        title="Prima nota"
        pastiglie={[{ etichetta: 'Riporto', valore: '€ 0,00', azione: { etichetta: 'Modifica il riporto', onClick, testId: 'mod' } }]}
      />,
    );
    const bottone = screen.getByRole('button', { name: 'Modifica il riporto' });
    expect(bottone.style.width).toBe('44px');
    fireEvent.click(bottone);
    expect(onClick).toHaveBeenCalledTimes(1);
  });
});
