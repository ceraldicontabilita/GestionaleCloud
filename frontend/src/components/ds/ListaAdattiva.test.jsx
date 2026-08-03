import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ListaAdattiva } from './ListaAdattiva';

const colonne = [
  { key: 'nome', label: 'Fornitore', ruoloCard: 'titolo' },
  { key: 'email', label: 'Email', ruoloCard: 'omesso', hideDesktop: true },
  { key: 'totale', label: 'Totale', ruoloCard: 'importo' },
];

const dati = [
  { id: 'f-1', nome: 'Fornitore completo', email: 'test@example.it', totale: '10,00 €' },
];

function setViewport(width) {
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: width });
  fireEvent(window, new Event('resize'));
}

describe('ListaAdattiva responsive', () => {
  it('nasconde sul desktop le colonne secondarie marcate hideDesktop', () => {
    setViewport(1600);
    const { container } = render(
      <ListaAdattiva colonne={colonne} dati={dati} cardBreakpoint={1180} testId="lista" />
    );

    expect(container.querySelector('table')).not.toBeNull();
    expect(screen.getByText('Fornitore')).toBeInTheDocument();
    expect(screen.queryByText('Email')).not.toBeInTheDocument();
  });

  it('usa le card su tablet', () => {
    setViewport(1024);
    const { container } = render(
      <ListaAdattiva colonne={colonne} dati={dati} cardBreakpoint={1180} testId="lista" />
    );

    expect(container.querySelector('table')).toBeNull();
    expect(screen.getByText('Fornitore completo')).toBeInTheDocument();
    expect(screen.getByText('10,00 €')).toBeInTheDocument();
  });

  it('azzera lo scroll orizzontale quando cambia il filtro', () => {
    setViewport(1600);
    const { getByTestId, rerender } = render(
      <ListaAdattiva
        colonne={colonne}
        dati={dati}
        cardBreakpoint={1180}
        testId="lista"
        resetKey="prima-ricerca"
      />
    );
    const primoWrap = getByTestId('lista').querySelector('.table-scroll');
    primoWrap.scrollLeft = 120;

    rerender(
      <ListaAdattiva
        colonne={colonne}
        dati={dati}
        cardBreakpoint={1180}
        testId="lista"
        resetKey="nuova-ricerca"
      />
    );

    const nuovoWrap = getByTestId('lista').querySelector('.table-scroll');
    expect(nuovoWrap).not.toBe(primoWrap);
    expect(nuovoWrap.scrollLeft).toBe(0);
  });
});
